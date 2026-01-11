import os, time, json
from boto3.dynamodb.conditions import Key
from ..common.aws import ddb_resource, s3_client
from ..common.security import phone_hmac, phone_last4

class MessagesRepo:
    def __init__(self):
        self.table = ddb_resource().Table(os.environ.get("DDB_TABLE_MESSAGES", "Messages"))
        self.retention_days: int = int(os.getenv("CONVERSATIONS_RETENTION_DAYS", "365"))
        self.archive_bucket: str | None = os.getenv("ARCHIVE_BUCKET")
        self.archive_prefix: str = os.getenv("ARCHIVE_PREFIX", "archive/")
        
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
        user_phone = from_phone if direction == "inbound" else to_phone
        ph = phone_hmac(tenant_id, user_phone) if user_phone else None
        last4 = phone_last4(user_phone) if user_phone else None
        conv_key = conversation_id or ph or "unknown"
        ttl_ts = ts + self.retention_days * 86400
        item = {
            "pk": f"{tenant_id}#{conv_key}",
            "sk": f"{ts}#{direction}#{msg_id}",
            "tenant_id": tenant_id,
            "conversation_id": conversation_id,
            "msg_id": msg_id,
            "direction": direction,
            "body": body,
            "phone_hmac": ph,
            "phone_last4": last4,
            "channel": channel,
            "created_at": ts,
            "ttl_ts": ttl_ts
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
        
    def _hydrate_archived(self, item: dict) -> dict:
        """Jeśli wiadomość jest zarchiwizowana i nie ma treści, dociąga ją z S3 (read-only)."""
        if not item:
            return item
        if item.get("archived_status") != "Archived":
            return item
        if item.get("body"):
            return item
        bucket = item.get("archive_bucket") or self.archive_bucket
        key = item.get("archive_key")
        if not bucket or not key:
            return item
        try:
            s3 = s3_client()
            resp = s3.get_object(Bucket=bucket, Key=key)
            data = resp["Body"].read()
            doc = json.loads(data.decode("utf-8"))
            # w DDB trzymamy tylko "szkielet"; do wyniku wstrzykujemy pełną wersję
            hydrated = dict(item)
            hydrated["body"] = doc.get("body")
            hydrated["archived_payload"] = {k: v for k, v in doc.items() if k not in ("body",)}
            return hydrated
        except Exception:
            # Nie blokujemy krytycznych ścieżek (ticketing/router) – w razie błędu zwracamy "szkielet"
            return item
    
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
        items = resp.get("Items") or []
        return [self._hydrate_archived(it) for it in items]
