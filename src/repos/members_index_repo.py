import os, time
from ..common.aws import ddb_resource
from boto3.dynamodb.conditions import Key

class MembersIndexRepo:
    def __init__(self):
        self.table = ddb_resource().Table(
            os.environ.get("DDB_TABLE_MEMBERS_INDEX", "MembersIndex")
        )

    def find_by_phone(self, tenant_id: str, phone: str) -> dict | None:
        resp = self.table.query(
            IndexName="tenant_phone_idx",
            KeyConditionExpression=Key("tenant_id").eq(tenant_id)
                                   & Key("phone").eq(phone),
            Limit=1,
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
