from __future__ import annotations

from typing import Optional, Dict, Any

from ..adapters.jira_client import JiraClient
from .clients_factory import ClientsFactory


class TicketingService:
    """
    Warstwa usługowa dla systemów ticketowych (Jira + inne w przyszłości).

    Routing i inne serwisy wołają tylko tę klasę, a nie JiraClient bezpośrednio.
    """

    def __init__(
        self,
        client: Optional[JiraClient] = None,
        *,
        clients_factory: ClientsFactory | None = None,
    ) -> None:
        self._client = client or JiraClient()
        self._factory = clients_factory

    def _client_for(self, tenant_id: str) -> JiraClient:
        if self._factory:
            return self._factory.jira(tenant_id)
        return self._client

    # W przyszłości możesz brać tu pod uwagę tenant_id i wybierać inny backend.

    def create_ticket(
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
