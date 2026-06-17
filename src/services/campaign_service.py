from typing import List, Dict, Optional, Any
from datetime import datetime, time
import os

from ..common.logging import logger
from .template_service import TemplateService
from ..repos.tenants_repo import TenantsRepo
from ..repos.conversations_repo import ConversationsRepo
from ..common.config import settings

# Domyślne okno wysyłki – zgodnie z dokumentacją (9:00–20:00)
DEFAULT_SEND_FROM = os.getenv("CAMPAIGN_SEND_FROM", "08:00")
DEFAULT_SEND_TO = os.getenv("CAMPAIGN_SEND_TO", "24:00")


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
          3) legacy: [{"token": "<token>", ...]

        Ta funkcja **nie** rozwiązuje token → raw phone. To robimy dopiero w runtime
        (np. w campaign_runner).
        """
        recipients = campaign.get("recipients") or []
        result: List[Any] = []
        
        for r in recipients:
            if isinstance(r, str):
                result.append(r)
                continue

            if isinstance(r, dict):
                if r.get("token"):
                    result.append(
                        {
                            "token": r.get("token"),
                        }
                    )
                    continue
            # unknown / empty recipient entry -> skip
            continue

        logger.info(
            {
                "campaign": "recipients",
                "mode": "filtered",
                "count": len(result),
            }
        )
        return result
    
    def select_include_tags(self, campaign: Dict) -> List[Any]:
        """Zwraca listę include tags.
        """
        tags = campaign.get("include_tags") or []
        result: List[Any] = []
        
        for t in tags:
            if isinstance(t, str):
                result.append(t)
                continue
            # unknown / empty recipient entry -> skip
            continue

        logger.info(
            {
                "campaign": "tags",
                "mode": "filtered",
                "count": len(result),
            }
        )
        return result
        
    def select_exclude_tags(self, campaign: Dict) -> List[Any]:
        """Zwraca listę include tags.
        """
        tags = campaign.get("exclude_tags") or []
        result: List[Any] = []
        
        for t in tags:
            if isinstance(t, str):
                result.append(t)
                continue
            # unknown / empty recipient entry -> skip
            continue

        logger.info(
            {
                "campaign": "tags",
                "mode": "filtered",
                "count": len(result),
            }
        )
        return result

   
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

        return self.tenants.get_language(tenant_id)

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
          - campaign["context"] -> użyj TemplateService (i18n, parametry),
          - tylko campaign["body"]    -> użyj literalnego body (już przetłumaczonego).
        """
        context = context or {}

        lang = self._resolve_language_for_recipient(
            tenant_id,
            recipient_phone,
            campaign_lang=campaign.get("language_code"),
        )

        if context:
            body = self.tpl.render(
                campaign.get("body"),
                context,
            )
        else:
            # fallback – neutral language: require explicit campaign body
            body = campaign.get("body") or ""

        return {
            "body": body,
            "language_code": lang,
        }
