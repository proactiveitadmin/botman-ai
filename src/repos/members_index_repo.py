import os, time
from ..common.aws import ddb_resource
from ..common.security import phone_hmac, normalize_phone
from boto3.dynamodb.conditions import Key

class MembersIndexRepo:
    def __init__(self):
        self.table = ddb_resource().Table(
            os.environ.get("DDB_TABLE_MEMBERS_INDEX", "MembersIndex")
        )

    def find_by_phone(self, tenant_id: str, phone: str) -> dict | None:
        ph = phone_hmac(tenant_id, phone)
        resp = self.table.query(
            IndexName="tenant_phone_hmac_idx",
            KeyConditionExpression=Key("tenant_id").eq(tenant_id)
                                   & Key("phone_hmac").eq(ph),
            Limit=1,
        )
        items = resp.get("Items") or []
        return items[0] if items else None

    def get_member(self, tenant_id: str, phone: str) -> dict | None:
        """
        Wrapper zgodny z tym, co woła RoutingService.
        """
        # Normalizujemy phone, żeby był spójny z tym co zapisujesz w indeksie
        normalized = normalize_phone(phone)
        return self.find_by_phone(tenant_id, normalized)
