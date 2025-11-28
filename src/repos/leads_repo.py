import os, time
from ..common.aws import ddb_resource

class LeadsRepo:
    def __init__(self):
        self.table = ddb_resource().Table(
            os.environ.get("DDB_TABLE_LEADS", "Leads")
        )

    def _pk(self, tenant_id: str) -> str:
        return f"tenant#{tenant_id}"

    def _sk(self, lead_id: str) -> str:
        return f"lead#{lead_id}"

    def create_lead(
        self,
        *,
        tenant_id: str,
        lead_id: str,
        phone: str,
        channel: str,
        channel_user_id: str,
        source: str,
        notes: str,
        language_code: str | None = None,
    ) -> dict:
        ts = int(time.time())
        item = {
            "pk": self._pk(tenant_id),
            "sk": self._sk(lead_id),
            "tenant_id": tenant_id,
            "lead_id": lead_id,
            "phone": phone,
            "channel": channel,
            "channel_user_id": channel_user_id,
            "source": source,
            "notes": notes,
            "created_at": ts,
            "status": "new",
        }
        if language_code:
            item["language_code"] = language_code
        self.table.put_item(Item=item)
        return item

    def mark_status(self, tenant_id: str, lead_id: str, status: str):
        self.table.update_item(
            Key={"pk": self._pk(tenant_id), "sk": self._sk(lead_id)},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": status},
        )
