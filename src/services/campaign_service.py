from typing import List, Dict, Optional, Any
from datetime import datetime, time
import os

from ..common.logging import logger
from .template_service import TemplateService
from ..repos.tenants_repo import TenantsRepo
from ..repos.conversations_repo import ConversationsRepo
from ..common.config import settings

# Domyślne okno wysyłki – zgodnie z dokumentacją (9:00–20:00)
DEFAULT_SEND_FROM = os.getenv("CAMPAIGN_SEND_FROM", "09:00")
DEFAULT_SEND_TO = os.getenv("CAMPAIGN_SEND_TO", "20:00")


class CampaignService:
    def __init__(
        self,
        now_fn=None,
        template_service: Optional[TemplateService] = None,
        tenants_repo: Optional[TenantsRepo] = None,
        conversations_repo: Optional[ConversationsRepo] = None,
    ) -> None:
        self._now_fn = now_fn or datetime.utcnow
        self.tpl = template_service or TemplateService()
        self.tenants = tenants_repo or TenantsRepo()
        self.conversations = conversations_repo or ConversationsRepo()
        # cache na listy słów, gdybyś kiedyś chciał używać templatek do słówek TAK/NIE w kampaniach
        self._words_cache: dict[tuple[str, str, str], set[str]] = {}

    def select_recipients(self, campaign: Dict) -> List[str]:
        """
        Zwraca listę numerów telefonu dla kampanii.

        Obsługiwane formaty:
          1) Proste: ["whatsapp:+48...", ...]
          2) Z tagami:
             [
               {"phone": "whatsapp:+48...", "tags": ["vip", "active"]},
               ...
             ]

        Filtry:
          - include_tags: jeżeli niepuste, bierzemy tylko odbiorców posiadających
            przynajmniej jeden z tagów
          - exclude_tags: jeżeli odbiorca ma którykolwiek z tych tagów, jest pomijany
        """
        raw_recipients = campaign.get("recipients", []) or []
        include_tags = set(campaign.get("include_tags") or [])
        exclude_tags = set(campaign.get("exclude_tags") or [])

        result: List[str] = []

        # tryb: brak filtrów -> zachowaj się jak dotychczas
        if not include_tags and not exclude_tags:
            for r in raw_recipients:
                if isinstance(r, dict):
                    phone = r.get("phone")
                else:
                    phone = r
                if phone:
                    result.append(phone)
            logger.info(
                {
                    "campaign": "recipients",
                    "mode": "simple",
                    "count": len(result),
                }
            )
            return result

        # tryb z filtrami / tagami
        for r in raw_recipients:
            if isinstance(r, dict):
                phone = r.get("phone")
                tags = set(r.get("tags") or [])
            else:
                # brak struktury -> nie umiemy ocenić tagów,
                # więc traktujemy tags = empty set
                phone = r
                tags = set()

            if not phone:
                continue

            # include_tags: musi być przecięcie
            if include_tags and not (tags & include_tags):
                continue

            # exclude_tags: jeśli przecięcie niepuste -> skip
            if exclude_tags and (tags & exclude_tags):
                continue

            result.append(phone)

        logger.info(
            {
                "campaign": "recipients",
                "mode": "filtered",
                "count": len(result),
                "include_tags": list(include_tags),
                "exclude_tags": list(exclude_tags),
            }
        )
        return result

    @staticmethod
    def _parse_hhmm(value: str) -> time:
        """
        Parsuje 'HH:MM' do obiektu time.
        Jeżeli format jest niepoprawny – użyjemy bezpiecznego defaultu.
        """
        try:
            hh, mm = value.split(":")
            return time(hour=int(hh), minute=int(mm))
        except Exception:
            # Fallback: 9:00 lub 20:00 w razie błędu
            if value == DEFAULT_SEND_FROM:
                return time(9, 0)
            if value == DEFAULT_SEND_TO:
                return time(20, 0)
            return time(9, 0)

    def _resolve_window(self, campaign: Dict) -> tuple[time, time]:
        """
        Używamy wartości z kampanii, a jeśli ich nie ma – globalnych envów.
        """
        send_from_str = campaign.get("send_from") or DEFAULT_SEND_FROM
        send_to_str = campaign.get("send_to") or DEFAULT_SEND_TO
        return self._parse_hhmm(send_from_str), self._parse_hhmm(send_to_str)

    def is_within_send_window(self, campaign: Dict) -> bool:
        """
        Sprawdza, czy aktualny czas (UTC) mieści się w oknie wysyłki.
        Wspiera także okna „przez północ” (np. 22:00–06:00).
        """
        now = self._now_fn().time()
        start, end = self._resolve_window(campaign)

        # Zwykłe okno, np. 09:00–20:00
        if start <= end:
            return start <= now <= end

        # Okno przez północ, np. 22:00–06:00
        return now >= start or now <= end

    # ---------- I18N DLA KAMPANII ----------

    def _resolve_language_for_recipient(
        self,
        tenant_id: str,
        phone: str,
        campaign_lang: Optional[str] = None,
    ) -> str:
        """
        Kolejność:
        1. language_code z kampanii (jeśli ustawione),
        2. language_code z Conversations dla danego numeru,
        3. language_code tenanta,
        4. globalny default z settings.
        """
        if campaign_lang:
            return campaign_lang

        conv = self.conversations.get_conversation(
            tenant_id=tenant_id,
            channel="whatsapp",
            channel_user_id=phone,
        )
        if conv and conv.get("language_code"):
            return conv["language_code"]

        tenant = self.tenants.get(tenant_id) or {}
        return tenant.get("language_code") or settings.get_default_language()

    def build_message(
        self,
        campaign: Dict[str, Any],
        tenant_id: str,
        recipient_phone: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Buduje finalną wiadomość kampanii dla konkretnego odbiorcy.

        Jeśli kampania ma:
          - campaign["template_name"] -> użyj TemplateService (i18n, parametry),
          - tylko campaign["body"]    -> użyj literalnego body (już przetłumaczonego).
        """
        context = context or {}

        lang = self._resolve_language_for_recipient(
            tenant_id,
            recipient_phone,
            campaign_lang=campaign.get("language_code"),
        )

        template_name = campaign.get("template_name")

        if template_name:
            body = self.tpl.render_named(
                tenant_id,
                template_name,
                lang,
                context,
            )
        else:
            # fallback – zachowanie zgodne z dotychczasowym kodem
            body = campaign.get("body", "Nowa oferta klubu!")

        return {
            "body": body,
            "language_code": lang,
        }
