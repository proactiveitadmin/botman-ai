from __future__ import annotations

from typing import Optional, Dict, Any

from ..adapters.jira_client import JiraClient


class TicketingService:
    """
    Warstwa usługowa dla systemów ticketowych (Jira + inne w przyszłości).

    Routing i inne serwisy wołają tylko tę klasę, a nie JiraClient bezpośrednio.
    """

    def __init__(self, client: Optional[JiraClient] = None) -> None:
        self.client = client or JiraClient()

    # W przyszłości możesz brać tu pod uwagę tenant_id i wybierać inny backend.

    def create_ticket(
        self,
        tenant_id: str,
        summary: str,
        description: str,
        meta: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        return self.client.create_ticket(
            summary=summary,
            description=description,
            tenant_id=tenant_id,
            meta=meta or {},
        )
