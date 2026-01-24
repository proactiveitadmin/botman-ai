import json
import time

from ...common.aws import sqs_client, resolve_optional_queue_url
from ...common.logging import logger
from ...common.logging_utils import mask_phone, shorten_body
from ...services.metrics_service import MetricsService
from ...repos.idempotency_repo import IdempotencyRepo
from ...services.clients_factory import ClientsFactory


clients = ClientsFactory()
metrics = MetricsService()
IDEMPOTENCY = IdempotencyRepo()

def _queue_delay_ms(record: dict) -> int | None:
    try:
        attrs = record.get("attributes") or {}
        sent = int(attrs.get("SentTimestamp"))  # ms
        now = int(time.time() * 1000)
        return now - sent
    except Exception:
        return None
def _get_optout_service():
    from ...services.opt_out_service import OptOutService
    from ...repos.conversations_repo import ConversationsRepo
    return OptOutService(ConversationsRepo()) 

def _normalize_whatsapp_channel_user_id(to: str | None) -> str | None:
    """Converts Twilio 'to' into channel_user_id format used by ConversationsRepo."""
    if not to:
        return None
    t = str(to).strip()
    if not t:
        return None
    return t if t.startswith("whatsapp:") else f"whatsapp:{t}"

def _should_enforce_opt_out(payload: dict) -> bool:
    """Backward compatible enforcement.

    We only enforce opt-out for messages that explicitly declare themselves as
    campaign/notification.

    Legacy payloads (no message_type) MUST behave as before this change,
    i.e., never blocked and never requiring DynamoDB access.
    """
    mt = (payload or {}).get("message_type")
    return mt in ("campaign", "notification")
        
def lambda_handler(event, context):
    records = event.get("Records", [])
    if not records:
        logger.info({"sender": "no_records"})
        return {"statusCode": 200, "body": "no-records"}

    batch_failures = []

    for r in records:

        msg_id = r.get("messageId")
        delay_ms = _queue_delay_ms(r)
        logger.info({
            "handler": "outbound_sender",
            "event": "record_received",
            "sqs_delay_ms": delay_ms,
            "message_id": msg_id,
        })
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
 
            # Opt-out enforcement (campaign/notification only, backward compatible)
            if _should_enforce_opt_out(payload):
                try:
                    optout = _get_optout_service()
                    if channel == "whatsapp":
                        channel_user_id = payload.get("channel_user_id") or _normalize_whatsapp_channel_user_id(payload.get("to"))
                    else:
                        channel_user_id = payload.get("channel_user_id")

                    if channel_user_id and optout.is_opted_out(tenant_id, channel, channel_user_id):
                        metrics.incr("message_blocked_opt_out", channel=channel, status="OPT_OUT")
                        logger.info(
                            {
                                "handler": "outbound_sender",
                                "event": "blocked_opt_out",
                                "tenant_id": tenant_id,
                                "channel": channel,
                            }
                        )
                        # treat as processed
                        continue
                except Exception as e:
                    # Never break core outbound flow on opt-out check failure
                    logger.error({"handler": "outbound_sender", "event": "optout_check_failed", "err": str(e)})


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

            res = clients.whatsapp(tenant_id).send_text(to=to, body=text)
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
