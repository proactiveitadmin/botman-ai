from __future__ import annotations

from typing import Optional, Dict, Any

from ..adapters.jira_client import JiraClient
from .clients_factory import ClientsFactory
from ..domain.models import Message
from .template_service import TemplateService
from ..common.constants import INTENT_TICKET


class TicketingService:
    """
    Warstwa usługowa dla systemów ticketowych (Jira + inne w przyszłości).

    Routing i inne serwisy wołają tylko tę klasę, a nie JiraClient bezpośrednio.
    """

    def __init__(
        self,
        tpl: TemplateService | None = None,
        client: Optional[JiraClient] = None,
        *,
        clients_factory: ClientsFactory | None = None,
    ) -> None:
        self.tpl = tpl or TemplateService()
        self._client = client or JiraClient()
        self._factory = clients_factory

    def _client_for(self, tenant_id: str) -> JiraClient:
        if self._factory:
            return self._factory.jira(tenant_id)
        return self._client

    # W przyszłości możesz brać tu pod uwagę tenant_id i wybierać inny backend.

    def _create_ticket(
        self,
        tenant_id: str,
        summary: str,
        description: str,
        meta: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        return self._client_for(tenant_id).create_ticket(
            summary=summary,
            description=description,
            tenant_id=tenant_id,
            meta=meta or {},
        )

    def create_data_and_ticket(
        self,
        msg: Message,
        lang: str,
        conv_key: str,
        history_block: str,
    ) -> Dict[str, Any]:


        summary = self.tpl.render_named(
            msg.tenant_id,
            "ticket_summary",
            lang,
            {},
        )

        description = self.tpl.render_named(
            msg.tenant_id,
            "ticket_description",
            lang,
            {
                "body": msg.body, 
                "history_block": history_block
            },
        )

        meta = {
            "conversation_id": conv_key,
            "phone": msg.from_phone,
            "channel": msg.channel,
            "channel_user_id": msg.channel_user_id,
            "intent": INTENT_TICKET,
            "language_code": lang,
        }

        return self._create_ticket(
            tenant_id=msg.tenant_id,
            summary=summary,
            description=description,
            meta=meta,
        )