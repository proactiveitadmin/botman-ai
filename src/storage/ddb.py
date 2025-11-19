import os, time
from ..common.aws import ddb_resource

class MessagesRepo:
    def __init__(self):
        self.table = ddb_resource().Table(os.environ.get("DDB_TABLE_MESSAGES", "Messages"))

    def put(self, item: dict):
        self.table.put_item(Item=item)

    def log_message(
        self,
        *,
        tenant_id: str,
        conversation_id: str | None,
        msg_id: str,
        direction: str,          # "inbound" / "outbound"
        body: str,
        from_phone: str,
        to_phone: str,
        template_id: str | None = None,
        ai_confidence: float | None = None,
        delivery_status: str | None = None,
        channel: str = "whatsapp",
        language_code: str | None = None,
    ):
        ts = int(time.time())
        conv_key = conversation_id or from_phone
        item = {
            "pk": f"{tenant_id}#{conv_key}",
            "sk": f"{ts}#{direction}#{msg_id}",
            "tenant_id": tenant_id,
            "conversation_id": conversation_id,
            "msg_id": msg_id,
            "direction": direction,
            "body": body,
            "from": from_phone,
            "to": to_phone,
            "channel": channel,
            "created_at": ts,
        }
        if template_id:
            item["template_id"] = template_id
        if ai_confidence is not None:
            item["ai_confidence"] = ai_confidence
        if delivery_status:
            item["delivery_status"] = delivery_status
        if language_code:
            item["language_code"] = language_code

        self.table.put_item(Item=item)

    def update_delivery_status(
        self,
        tenant_id: str,
        conv_key: str,
        msg_id: str,
        ts: int,
        delivery_status: str,
    ):
        sk = f"{ts}#outbound#{msg_id}"
        self.table.update_item(
            Key={"pk": f"{tenant_id}#{conv_key}", "sk": sk},
            UpdateExpression="SET delivery_status = :ds",
            ExpressionAttributeValues={":ds": delivery_status},
        )

class ConversationsRepo:
    def __init__(self):
        self.table = ddb_resource().Table(os.environ.get("DDB_TABLE_CONVERSATIONS", "Conversations"))

    def get(self, pk: str):
        return self.table.get_item(Key={"pk": pk}).get("Item")

    def put(self, item: dict):
        self.table.put_item(Item=item)

    def delete(self, pk: str):
        self.table.delete_item(Key={"pk": pk})

    # --- NOWE API ---

    def conversation_pk(self, tenant_id: str, phone: str) -> str:
        return f"conv#{tenant_id}#{phone}"

    def get_conversation(self, tenant_id: str, phone: str) -> dict | None:
        return self.get(self.conversation_pk(tenant_id, phone))

    def upsert_conversation(
        self,
        tenant_id: str,
        phone: str,
        *,
        last_intent: str | None = None,
        state_machine_status: str | None = None,
        assigned_agent: str | None = None,
        language_code: str | None = None,
    ) -> dict:
        pk = self.conversation_pk(tenant_id, phone)
        now = int(time.time())

        update_expr = ["SET updated_at = :now"]
        expr_vals = {":now": now}

        if last_intent is not None:
            update_expr.append("last_intent = :li")
            expr_vals[":li"] = last_intent
        if state_machine_status is not None:
            update_expr.append("state_machine_status = :sm")
            expr_vals[":sm"] = state_machine_status
        if assigned_agent is not None:
            update_expr.append("assigned_agent = :aa")
            expr_vals[":aa"] = assigned_agent
        if language_code is not None:
            update_expr.append("language_code = :lang")
            expr_vals[":lang"] = language_code

        # created_at tylko przy pierwszym zapisie
        update_expr.append("created_at = if_not_exists(created_at, :now)")

        res = self.table.update_item(
            Key={"pk": pk},
            UpdateExpression=" , ".join(update_expr),
            ExpressionAttributeValues=expr_vals,
            ReturnValues="ALL_NEW",
        )
        return res.get("Attributes", {})

    def set_language(self, tenant_id: str, phone: str, language_code: str) -> dict:
        pk = self.conversation_pk(tenant_id, phone)
        res = self.table.update_item(
            Key={"pk": pk},
            UpdateExpression="SET language_code = :lang",
            ExpressionAttributeValues={":lang": language_code},
            ReturnValues="ALL_NEW",
        )
        return res.get("Attributes", {})

    
class MembersIndexRepo:
    def __init__(self):
        self.table = ddb_resource().Table(os.environ.get("DDB_TABLE_MEMBERS_INDEX", "MembersIndex"))
    def find_by_phone(self, tenant_id: str, phone: str):
        # np. query po pk = f"{tenant_id}#{member_id}", secondary index po phone
        ...
