import json
import time

from ...common.aws import sqs_client, resolve_optional_queue_url
from ...common.logging import logger
from ...common.logging_utils import mask_phone, shorten_body
from ...services.metrics_service import MetricsService
from ...repos.idempotency_repo import IdempotencyRepo
from ...services.clients_factory import ClientsFactory
from ...services.tenant_config_service import default_tenant_config_service
from ...common.rate_limiter import InMemoryRateLimiter


clients = ClientsFactory()
metrics = MetricsService()
IDEMPOTENCY = IdempotencyRepo()
tenant_cfg = default_tenant_config_service()
tenant_limiter = InMemoryRateLimiter()
tenant_cfg = default_tenant_config_service()
tenant_limiter = InMemoryRateLimiter()

def _queue_delay_ms(record: dict) -> int | None:
    try:
        attrs = record.get("attributes") or {}
        sent = int(attrs.get("SentTimestamp"))  # ms
        now = int(time.time() * 1000)
        return now - sent
    except Exception:
        return None

def _normalize_whatsapp_channel_user_id(to: str | None) -> str | None:
    """Converts Twilio 'to' into channel_user_id format used by ConversationsRepo."""
    if not to:
        return None
    t = str(to).strip()
    if not t:
        return None
    return t if t.startswith("whatsapp:") else f"whatsapp:{t}"
        
def lambda_handler(event, context):
    try:
        tenant_limiter.reset()
    except Exception:
        pass

    records = event.get("Records", [])
    if not records:
        logger.info({"sender": "no_records"})
        return {"statusCode": 200, "body": "no-records"}

    batch_failures = []

    sqs = sqs_client()
    web_q_url = resolve_optional_queue_url("WebOutboundEventsQueueUrl")

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

            # --- per-tenant soft limiter (no sleep; retry via batch failure) ---
            try:
                cfg = tenant_cfg.get(tenant_id)
            except Exception:
                cfg = {}
            lim = (cfg.get("limits") or {}).get("outbound") or {}
            try:
                rate = float(lim.get("per_tenant_rps") or 0)
                burst = float(lim.get("per_tenant_burst") or max(1.0, rate))
            except Exception:
                rate, burst = 0.0, 0.0

            if rate > 0 and not tenant_limiter.try_acquire(f"out#{tenant_id}", rate=rate, burst=burst):
                logger.warning({"handler": "outbound_sender", "event": "tenant_throttled", "tenant_id": tenant_id})
                metrics.incr("TenantOutboundThrottled", tenant_id=tenant_id, component="outbound_sender")
                if msg_id:
                    batch_failures.append({"itemIdentifier": msg_id})
                continue

            # Idempotency for outbound send (Twilio / web queue)
            idem_key = payload.get("idempotency_key") or (f"out#{tenant_id}#{msg_id}" if msg_id else None)
            if idem_key:
                acquired = IDEMPOTENCY.try_acquire(f"snd#{idem_key}", meta={"scope": "outbound", "channel": channel})
                if not acquired:
                    logger.info({"handler": "outbound_sender", "event": "duplicate_outbound", "tenant_id": tenant_id})
                    metrics.incr("TenantOutboundDuplicate", tenant_id=tenant_id, component="outbound_sender", channel=channel)
                    metrics.incr("message_sent_duplicate", tenant_id=tenant_id, component="outbound_sender", channel=channel, status="DUPLICATE")
                    continue
            else:
                logger.warning({"handler": "outbound_sender", "event": "missing_idempotency_key", "tenant_id": tenant_id})

            # --- Kanał WWW ---
            if channel == "web":
                web_msg = {
                    "tenant_id": tenant_id,
                    "channel_user_id": payload.get("channel_user_id"),
                    "body": text,
                }

                if web_q_url:
                    sqs.send_message(
                        QueueUrl=web_q_url,
                        MessageBody=json.dumps(web_msg),
                    )
                    metrics.incr("TenantOutboundQueued", tenant_id=tenant_id, component="outbound_sender", channel="web")
                    metrics.incr("TenantOutboundQueued", tenant_id=tenant_id, component="outbound_sender", channel="web")
                    metrics.incr("message_sent", tenant_id=tenant_id, component="outbound_sender", channel="web", status="QUEUED")
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
                    metrics.incr("TenantOutboundQueued", tenant_id=tenant_id, component="outbound_sender", channel="web", status="NO_QUEUE")
                    metrics.incr("message_sent", tenant_id=tenant_id, component="outbound_sender", channel="web", status="NO_QUEUE")
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

            metrics.incr("TenantOutboundSent", tenant_id=tenant_id, component="outbound_sender", channel="whatsapp", status=res_status)
            metrics.incr("TenantOutboundSent", tenant_id=tenant_id, component="outbound_sender", channel="whatsapp", status=res_status)
            metrics.incr("TenantOutboundSent", tenant_id=tenant_id, component="outbound_sender", channel="whatsapp", status=res_status)
            metrics.incr("message_sent", tenant_id=tenant_id, component="outbound_sender", channel="whatsapp", status=res_status)

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
