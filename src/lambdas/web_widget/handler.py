import json
import os
import time
from ...common.aws import sqs_client, resolve_queue_url
from ...common.utils import new_id
from ...common.logging import logger

def lambda_handler(event, context):
    """
    Inbound z widgetu WWW (REST/HTTP).
    Zakładam body JSON:
    {
        "tenant_id": "default",
        "channel_user_id": "<session-id / user-id z widgetu>",
        "body": "Treść wiadomości"
    }
    """
    try:
        body = json.loads(event.get("body") or "{}")
        tenant_id = body.get("tenant_id", "default")
        channel_user_id = body.get("channel_user_id")
        text = body.get("body", "")
        language_code = body.get("language_code")

        if not channel_user_id or not text:
            return {"statusCode": 400, "body": "Missing channel_user_id or body"}

        msg = {
            "event_id": new_id("evt-web-"),
            "from": None,  # brak telefonu
            "to": None,
            "body": text,
            "tenant_id": tenant_id,
            "channel": "web",
            "channel_user_id": channel_user_id,
            "language_code": language_code,
            "ts": int(time.time() * 1000),
            "ip": (event.get("requestContext") or {}).get("identity", {}).get("sourceIp"),
        }

        q_url = resolve_queue_url("InboundEventsQueueUrl")
        sqs_client().send_message(QueueUrl=q_url, MessageBody=json.dumps(msg))

        logger.info(
            {
                "web_widget": "ok",
                "tenant_id": tenant_id,
                "channel_user_id": channel_user_id,
                "language_code": language_code,
            }
        )
        return {"statusCode": 200, "body": "{}"}

    except Exception as e:
        logger.error({"web_widget_error": str(e)})
        return {"statusCode": 500, "body": "error"}
