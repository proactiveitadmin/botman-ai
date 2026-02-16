"""
Lambda message_router.

Odbiera komunikaty z kolejki inbound, zamienia je na obiekty domenowe
i przekazuje do RoutingService, a następnie wrzuca odpowiedzi do kolejki outbound.
"""

import json
import time
import os

from ...services.routing_service import RoutingService
from ...services.template_service import TemplateService
from ...services.kb_service import KBService
from ...repos.idempotency_repo import IdempotencyRepo
from ...adapters.openai_client import OpenAIClient
from ...repos.conversations_repo import ConversationsRepo
from ...repos.messages_repo import MessagesRepo
from ...repos.tenants_repo import TenantsRepo 
from ...common.aws import resolve_queue_url, sqs_client 
from ...domain.models import Message
from ...common.logging import logger
from ...common.logging_utils import mask_phone, shorten_body
from ...common.utils import new_id
from ...common.security import conversation_key
from ...services.metrics_service import MetricsService
from ...services.tenant_config_service import default_tenant_config_service
from ...common.rate_limiter import InMemoryRateLimiter

IDEMPOTENCY = IdempotencyRepo()

ROUTER = RoutingService()
MESSAGES = MessagesRepo()

metrics = MetricsService()
tenant_cfg = default_tenant_config_service()
tenant_limiter = InMemoryRateLimiter()

metrics = MetricsService()
tenant_cfg = default_tenant_config_service()
tenant_limiter = InMemoryRateLimiter()


def _parse_record(record: dict) -> dict | None:
    raw_body = record.get("body", "")
    try:
        if isinstance(raw_body, str):
            return json.loads(raw_body)
        return raw_body or {}
    except Exception as e:
        logger.error(
            {
                "sender": "message_router_bad_json",
                "err": str(e),
                "raw": raw_body,
            }
        )
        return None


def _build_message(body: dict) -> Message:
    return Message(
        tenant_id=body.get("tenant_id", "default"),
        from_phone=body.get("from"),
        to_phone=body.get("to"),
        body=body.get("body", ""),
        conversation_id=body.get("conversation_id") or body.get("event_id"),
        channel=body.get("channel", "whatsapp"),
        channel_user_id=body.get("channel_user_id") or body.get("from"),
        language_code=body.get("language_code"),
        intent=body.get("intent"),    
        slots=body.get("slots") or {}, 
    )


def _publish_actions(actions, original_body: dict):
    outbound_url = resolve_queue_url("OutboundQueueUrl")
    tickets_url = (
        resolve_queue_url("TicketsQueueUrl")
        if "TicketsQueueUrl" in os.environ
        else None
    )

    for idx, a in enumerate(actions or []):
        # akcje ticket – do kolejki ticketów, nie wysyłamy do klienta
        if a.type == "ticket":
            if tickets_url:
                sqs_client().send_message(
                    QueueUrl=tickets_url,
                    MessageBody=json.dumps(a.payload),
                )
            continue

        # interesują nas tylko reply (odpowiedzi do użytkownika)
        if a.type != "reply":
            continue

        payload = a.payload

        # Canonical Messages conversation key (no PII): if caller doesn't provide
        # a conversation_id, derive stable key from (tenant, channel, user).
        conv_key = conversation_key(
            original_body.get("tenant_id", "default"),
            original_body.get("channel", "whatsapp"),
            original_body.get("channel_user_id") or original_body.get("from"),
            original_body.get("conversation_id"),
        )
        
        from_phone = payload.get("from") or original_body.get("to")
        to_phone = payload.get("to") or original_body.get("from")

        # logujemy OUTBOUND do Messages (historia dla FAQ itd.)
        try:
            MESSAGES.log_message(
                tenant_id=payload.get(
                    "tenant_id", original_body.get("tenant_id", "default")
                ),
                conversation_id=conv_key,
                msg_id=new_id("out-"),
                direction="outbound",
                body=payload.get("body") or "",
                from_phone=from_phone,
                to_phone=to_phone,
                template_id=payload.get("template_id"),
                ai_confidence=None,
                channel=payload.get("channel")
                    or original_body.get("channel", "whatsapp"),
                    channel_user_id=original_body.get("channel_user_id") or original_body.get("from"),
                language_code=payload.get("language_code")
                    or original_body.get("language_code"),
            )
        except Exception:
            pass

        # zapewnij idempotency_key dla outbound (unikamy podwójnych wysyłek przy retry)
        if "idempotency_key" not in payload:
            # NOTE:
            # W ramach jednego inbound eventu router potrafi wygenerować *kilka* reply (np.
            # "Zweryfikowaliśmy Twoje konto" + kolejny krok flow).
            # OutboundSender ma idempotencję po idempotency_key, więc klucz musi być unikalny
            # per wiadomość, a jednocześnie stabilny przy retry tego samego inbound eventu.
            base = (
                original_body.get("event_id")
                or original_body.get("message_sid")
                or original_body.get("conversation_id")
            )
            if base:
                payload["idempotency_key"] = f"out#{base}#{a.type}#{idx}"

        t0 = time.perf_counter()
        # wysyłka do kolejki outbound
        sqs_client().send_message(
            QueueUrl=outbound_url,
            MessageBody=json.dumps(payload),
        )

        logger.info(
            {
                "handler": "message_router",
                "event": "queued_outbound",
                "from": mask_phone(original_body.get("from")),
                "to": mask_phone(payload.get("to")),
                "body": shorten_body(payload.get("body")),
                "enqueue_ms": int((time.perf_counter() - t0) * 1000),
                "tenant_id": payload.get("tenant_id", original_body.get("tenant_id")),
            }
        )



def lambda_handler(event, context):
    """
    Główny handler AWS Lambda dla message_routera.

    Dla każdej wiadomości z eventu:
    - deserializuje payload,
    - buduje obiekt Message,
    - wywołuje RoutingService.handle,
    - dla akcji typu "reply" publikuje komunikat do kolejki outbound.
    """
    # limiter w CRMService jest w pamięci procesu (warm container),
    # więc resetujemy go na początku invokacji żeby działał "per invoke"
    try:
        ROUTER.crm.reset_invocation_limits()
    except Exception:
        pass

    # soft per-tenant limiter for this invocation (demo-safe)
    try:
        tenant_limiter.reset()
    except Exception:
        pass

    records = event.get("Records") or []
    
    # Defensive ordering: SQS FIFO guarantees ordering per MessageGroupId,
    # but event source mapping may deliver Records[] in arbitrary order within a batch.
    # If SequenceNumber is present, sort by (MessageGroupId, SequenceNumber).
    def _fifo_sort_key(rec: dict):
        attrs = rec.get("attributes") or {}
        gid = attrs.get("MessageGroupId") or ""
        seq = attrs.get("SequenceNumber")
        try:
            seq_i = int(seq) if seq is not None else -1
        except Exception:
            seq_i = -1
        return (gid, seq_i)

    if any(((r.get("attributes") or {}).get("SequenceNumber") is not None) for r in records):
        records = sorted(records, key=_fifo_sort_key)

    if not records:
        logger.info({"handler": "message_router", "event": "no_records"})
        return {"statusCode": 200, "body": "no-records"}

    batch_failures = []

    for r in records:
        try:
            msg_body = _parse_record(r)
        except Exception as e:
            logger.error({"handler": "message_router", "event": "bad_record", "err": str(e)})
            batch_failures.append({"itemIdentifier": r.get("messageId")})
            continue

        if not msg_body:
            continue
            
        # FIFO validation (ordering key + deduplication id)
        attrs = r.get("attributes") or {}
        gid = attrs.get("MessageGroupId")
        dedup_id = attrs.get("MessageDeduplicationId")

        # ordering key: MessageGroupId should match conversation_id when present
        conv_id = msg_body.get("conversation_id")
        if gid and conv_id and gid != conv_id:
            logger.error(
                {
                    "handler": "message_router",
                    "event": "ordering_key_mismatch",
                    "messageId": r.get("messageId"),
                    "MessageGroupId": gid,
                    "conversation_id": conv_id,
                }
            )
            batch_failures.append({"itemIdentifier": r.get("messageId")})
            continue

        # deduplication: if FIFO dedup id is set and we can derive expected, enforce it
        expected_dedup = msg_body.get("message_sid") or msg_body.get("event_id")
        if dedup_id and expected_dedup and dedup_id != expected_dedup:
            logger.error(
                {
                    "handler": "message_router",
                    "event": "deduplication_id_mismatch",
                    "messageId": r.get("messageId"),
                    "MessageDeduplicationId": dedup_id,
                    "expected": expected_dedup,
                }
            )
            batch_failures.append({"itemIdentifier": r.get("messageId")})
            continue

        # inbound idempotency
        base = msg_body.get("event_id") or msg_body.get("message_sid") or r.get("messageId")
        tenant_id = msg_body.get("tenant_id", "default")
        if base:
            inbound_key = f"in#{tenant_id}#{base}"
            if not IDEMPOTENCY.try_acquire(inbound_key, meta={"scope": "inbound"}):
                logger.info({"handler": "message_router", "event": "duplicate_inbound", "tenant_id": tenant_id})
                continue
        logger.info(
            {
                "handler": "message_router",
                "event": "received",
                "from": mask_phone(msg_body.get("from")),
                "to": mask_phone(msg_body.get("to")),
                "body": shorten_body(msg_body.get("body")),
                "tenant_id": msg_body.get("tenant_id"),
                "channel": msg_body.get("channel", "whatsapp"),
            }
        )

        # --- per-tenant soft limiter (no sleep; retry via batch failure) ---
        try:
            cfg = tenant_cfg.get(tenant_id)
        except Exception:
            cfg = {}
        lim = (cfg.get("limits") or {}).get("router") or {}
        try:
            rate = float(lim.get("per_tenant_rps") or 0)
            burst = float(lim.get("per_tenant_burst") or max(1.0, rate))
        except Exception:
            rate, burst = 0.0, 0.0

        if rate > 0 and not tenant_limiter.try_acquire(f"router#{tenant_id}", rate=rate, burst=burst):
            logger.warning({"handler": "message_router", "event": "tenant_throttled", "tenant_id": tenant_id})
            metrics.incr("TenantRoutedThrottled", tenant_id=tenant_id, component="message_router")
            # Let SQS retry later
            batch_failures.append({"itemIdentifier": r.get("messageId")})
            continue

        metrics.incr("TenantRoutedInbound", tenant_id=tenant_id, component="message_router")

        t_msg = time.perf_counter()

        msg = _build_message(msg_body)
        # Canonical conversation key for Messages history (no PII).
        conv_key = conversation_key(
            msg.tenant_id,
            msg.channel or "whatsapp",
            msg.channel_user_id or msg.from_phone,
            msg.conversation_id,
        )
        # logujemy inbound do Messages
        try:
            MESSAGES.log_message(
                tenant_id=msg.tenant_id,
                conversation_id=conv_key,
                msg_id=new_id("in-"),
                direction="inbound",
                body=msg.body or "",
                from_phone=msg.from_phone,
                to_phone=msg.to_phone,
                channel=msg.channel or "whatsapp",
                channel_user_id=msg.channel_user_id or msg.from_phone,
                language_code=None,
            )
        except Exception:
            # nie blokujemy flow jeśli logowanie padnie
            pass

        try:
            actions = ROUTER.handle(msg)
            _publish_actions(actions, msg_body)
            metrics.incr("TenantRoutedOk", tenant_id=tenant_id, component="message_router")
        except Exception as e:
            logger.error({"handler": "message_router", "event": "route_fail", "tenant_id": tenant_id, "err": str(e)})
            metrics.incr("TenantRoutedError", tenant_id=tenant_id, component="message_router")
            if r.get("messageId"):
                batch_failures.append({"itemIdentifier": r.get("messageId")})
            continue
        finally:
            metrics.timing_ms(
                "TenantRoutingLatencyMs",
                (time.perf_counter() - t_msg) * 1000,
                tenant_id=tenant_id,
                component="message_router",
            )

    logger.info({"handler": "message_router", "event": "done", "failures": len(batch_failures)})
    # partial batch response for SQS event source mapping
    if batch_failures:
        return {"batchItemFailures": batch_failures}
    return {"statusCode": 200}
