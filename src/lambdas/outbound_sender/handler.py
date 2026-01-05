import json

from ...adapters.twilio_client import TwilioClient
from ...common.aws import sqs_client, resolve_optional_queue_url
from ...common.logging import logger
from ...common.logging_utils import mask_phone, shorten_body
from ...services.metrics_service import MetricsService
from ...repos.idempotency_repo import IdempotencyRepo


twilio = TwilioClient()
metrics = MetricsService()
IDEMPOTENCY = IdempotencyRepo()


def lambda_handler(event, context):
    records = event.get("Records", [])
    if not records:
        logger.info({"sender": "no_records"})
        return {"statusCode": 200, "body": "no-records"}

    batch_failures = []

    for r in records:
        msg_id = r.get("messageId")
        try:
            raw = r.get("body", "")
            try:
                payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception as e:
                logger.error({"sender": "bad_json", "err": str(e), "raw": raw})
                # treat as processed (do not retry)
                continue

            channel = payload.get("channel", "whatsapp")
            text = payload.get("body")
            tenant_id = payload.get("tenant_id", "default")

            # Idempotency for outbound send (Twilio / web queue)
            idem_key = payload.get("idempotency_key") or (f"out#{tenant_id}#{msg_id}" if msg_id else None)
            if idem_key:
                acquired = IDEMPOTENCY.try_acquire(f"snd#{idem_key}", meta={"scope": "outbound", "channel": channel})
                if not acquired:
                    logger.info({"handler": "outbound_sender", "event": "duplicate_outbound", "tenant_id": tenant_id})
                    metrics.incr("message_sent_duplicate", channel=channel, status="DUPLICATE")
                    continue
            else:
                logger.warning({"handler": "outbound_sender", "event": "missing_idempotency_key", "tenant_id": tenant_id})

            # --- Kanał WWW ---
            if channel == "web":
                web_q_url = resolve_optional_queue_url("WebOutboundEventsQueueUrl")
                web_msg = {
                    "tenant_id": tenant_id,
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
                continue

            # --- Kanał WhatsApp (Twilio) ---
            to = payload.get("to")
            if not to or not text:
                logger.warning({"sender": "invalid_payload", "payload": payload})
                continue

            res = twilio.send_text(to=to, body=text)
            res_status = res.get("status", "UNKNOWN")

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
            # retry only this message
            logger.error({"handler": "outbound_sender", "event": "fail", "err": str(e)})
            if msg_id:
                batch_failures.append({"itemIdentifier": msg_id})

    if batch_failures:
        return {"batchItemFailures": batch_failures}
    return {"statusCode": 200}
