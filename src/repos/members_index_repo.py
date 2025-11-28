import os, time
from ..common.aws import ddb_resource

class MembersIndexRepo:
    def __init__(self):
        self.table = ddb_resource().Table(
            os.environ.get("DDB_TABLE_MEMBERS_INDEX", "MembersIndex")
        )

    def find_by_phone(self, tenant_id: str, phone: str) -> dict | None:
        """
        Wersja MVP – scan po tenant_id + phone.
        TODO Docelowo: query po GSI (tenant_id, phone).
        """
        resp = self.table.scan(
            FilterExpression="tenant_id = :t AND phone = :p",
            ExpressionAttributeValues={
                ":t": tenant_id,
                ":p": phone,
            },
        )
        items = resp.get("Items") or []
        return items[0] if items else None

    def get_member(self, tenant_id: str, phone: str) -> dict | None:
        """
        Wrapper zgodny z tym, co woła RoutingService.
        """
        # Normalizujemy phone, żeby był spójny z tym co zapisujesz w indeksie
        normalized = phone
        if normalized.startswith("whatsapp:"):
            normalized = normalized.split(":", 1)[1]
        return self.find_by_phone(tenant_id, normalized)
