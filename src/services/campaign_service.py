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

    
    def select_recipients(self, campaign: Dict) -> List[Any]:
        """Zwraca listę odbiorców dla kampanii (bez jawnych telefonów w storage).

        Obsługiwane formaty danych w Campaigns (legacy + nowy):
          1) Legacy: ["whatsapp:+48...", ...]
          2) Legacy z tagami: [{"phone": "whatsapp:+48...", "tags": [...]}, ...]
          3) Nowy (bez PII): [{"phone_hmac": "<hmac>", "phone_last4": "6789", "tags": [...]}, ...]

        Ta funkcja **nie** rozwiązuje phone_hmac → raw phone. To robimy dopiero w runtime
        (np. w campaign_runner) przez MembersIndex.
        """
        recipients = campaign.get("recipients") or []
        include_tags = set(campaign.get("include_tags") or [])
        exclude_tags = set(campaign.get("exclude_tags") or [])

        result: List[Any] = []

        def tags_ok(rec_tags: set[str]) -> bool:
            if include_tags and rec_tags.isdisjoint(include_tags):
                return False
            if exclude_tags and not rec_tags.isdisjoint(exclude_tags):
                return False
            return True

        for r in recipients:
            if isinstance(r, str):
                # legacy: raw phone
                rec_tags = set()
                if not tags_ok(rec_tags):
                    continue
                result.append(r)
                continue

            if isinstance(r, dict):
                rec_tags = set(r.get("tags") or [])
                if not tags_ok(rec_tags):
                    continue

                if r.get("phone_hmac"):
                    # new format (hashed)
                    result.append(
                        {
                            "phone_hmac": r.get("phone_hmac"),
                            "phone_last4": r.get("phone_last4"),
                            "tags": list(rec_tags) if rec_tags else [],
                        }
                    )
                    continue

                phone = r.get("phone")
                if phone:
                    # legacy dict
                    result.append(phone)
                    continue

            # unknown / empty recipient entry -> skip
            continue

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
            # fallback – neutral language: require explicit campaign body
            body = campaign.get("body") or ""

        return {
            "body": body,
            "language_code": lang,
        }
