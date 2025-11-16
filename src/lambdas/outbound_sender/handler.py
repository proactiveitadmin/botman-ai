import json
from ...adapters.twilio_client import TwilioClient
from ...common.aws import sqs_client, resolve_queue_url
from ...common.security import verify_twilio_signature
from ...common.logging import logger
from ...common.logging_utils import mask_phone, shorten_body
from ...services.spam_service import SpamService
from ...services.metrics_service import MetricsService


twilio = TwilioClient()
spam_service = SpamService()
metrics = MetricsService()


def lambda_handler(event, context):
    records = event.get("Records", [])
    if not records:
        logger.info({"sender": "no_records"})
        return {"statusCode": 200, "body": "no-records"}

    for r in records:
        raw = r.get("body", "")
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as e:
            logger.error({"sender": "bad_json", "err": str(e), "raw": raw})
            continue

        to = payload.get("to")
        text = payload.get("body")
        if not to or not text:
            logger.warning({"sender": "invalid_payload", "payload": payload})
            continue

        try:
            res = twilio.send_text(to=to, body=text)
            res_status = res.get("status", "UNKNOWN")
            tenant_id = payload.get("tenant_id", "default")
            
            
            metrics.incr("message_sent", channel="whatsapp", status=res.get("status", "UNKNOWN"))
            
            logger.info({
                "handler": "outbound_sender",
                "event": "sent",
                "to": mask_phone(to),
                "body": shorten_body(text),
                "tenant_id": tenant_id,
                "result": res_status  # np. tylko HTTP status, nie cały response body z PII
            })
        except Exception as e:
            logger.error({"sender": "twilio_fail", "err": str(e), "to": to})

    return {"statusCode": 200}
