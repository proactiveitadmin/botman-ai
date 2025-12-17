import json

from ...adapters.twilio_client import TwilioClient
from ...common.aws import sqs_client, resolve_optional_queue_url
from ...common.logging import logger
from ...common.logging_utils import mask_phone, shorten_body
from ...services.metrics_service import MetricsService


twilio = TwilioClient()
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
        channel = payload.get("channel", "whatsapp")
        text = payload.get("body")

        # --- Kanał WWW ---
        if channel == "web":
            # Jeśli jest zdefiniowana osobna kolejka dla WWW – wyślij tam
            web_q_url = resolve_optional_queue_url("WebOutboundEventsQueueUrl")
            web_msg = {
                "tenant_id": payload.get("tenant_id", "default"),
                "channel_user_id": payload.get("channel_user_id"),
                "body": text,
            }

            if web_q_url:
                sqs_client().send_message(
                    QueueUrl=web_q_url,
                    MessageBody=json.dumps(web_msg),
                )
                metrics.incr("message_sent", channel="web", status="QUEUED")
                logger.info(
                    {
                        "handler": "outbound_sender",
                        "event": "web_outbound_queued",
                        "tenant_id": web_msg["tenant_id"],
                        "channel_user_id": web_msg["channel_user_id"],
                        "body": shorten_body(text),
                    }
                )
            else:
                # fallback: tylko log – ale nie próbujemy Twilio
                metrics.incr("message_sent", channel="web", status="NO_QUEUE")
                logger.info(
                    {
                        "handler": "outbound_sender",
                        "event": "web_outbound_no_queue",
                        "tenant_id": web_msg["tenant_id"],
                        "channel_user_id": web_msg["channel_user_id"],
                        "body": shorten_body(text),
                    }
                )

            continue  # nic więcej dla kanału web

        # --- Kanał WhatsApp (Twilio) ---
        to = payload.get("to")
        if not to or not text:
            logger.warning({"sender": "invalid_payload", "payload": payload})
            continue

        try:
            res = twilio.send_text(to=to, body=text)
            res_status = res.get("status", "UNKNOWN")
            tenant_id = payload.get("tenant_id", "default")

            metrics.incr("message_sent", channel="whatsapp", status=res_status)

            logger.info(
                {
                    "handler": "outbound_sender",
                    "event": "sent",
                    "to": mask_phone(to),
                    "body": shorten_body(text),
                    "tenant_id": tenant_id,
                    "result": res_status,
                }
            )
        except Exception as e:
            logger.error({
                "sender": "twilio_fail", 
                "err": str(e), 
                "to": mask_phone(to)})

    return {"statusCode": 200}