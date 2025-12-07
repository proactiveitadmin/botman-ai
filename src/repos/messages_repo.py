import os, time
from ..common.aws import ddb_resource
from boto3.dynamodb.conditions import Key

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
    
    def get_last_messages(
        self,
        tenant_id: str,
        conv_key: str,
        limit: int = 10,
    ) -> list[dict]:
        """
        Zwraca ostatnie N wiadomości w rozmowie (sort desc po SK).
        conv_key = conversation_id lub from_phone – tak jak w log_message.
        """
        pk = f"{tenant_id}#{conv_key}"
        resp = self.table.query(
            KeyConditionExpression=Key("pk").eq(pk),
            ScanIndexForward=False,  # od najnowszych
            Limit=limit,
        )
        return resp.get("Items") or []
