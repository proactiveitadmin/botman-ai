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
from ...common.security import user_hmac

IDEMPOTENCY = IdempotencyRepo()

ROUTER = RoutingService()
MESSAGES = MessagesRepo()


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

        conv_key = (
            original_body.get("conversation_id")
            or original_body.get("channel_user_id")
            or original_body.get("from")
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

    records = event.get("Records") or []
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

        # inbound idempotency
        base = msg_body.get("event_id") or msg_body.get("message_sid") or r.get("messageId")
        tenant_id = msg_body.get("tenant_id", "default")
        if base:
            inbound_key = f"in#{tenant_id}#{base}"
            if not IDEMPOTENCY.try_acquire(inbound_key, meta={"scope": "inbound"}):
                logger.info({"handler": "message_router", "event": "duplicate_inbound", "tenant_id": tenant_id})
                continue
        event_id = msg_body.get("event_id")
        tenant_id = msg_body.get("tenant_id", "default")
        from_phone = msg_body.get("from")
        channel = msg_body.get("channel", "whatsapp")
        channel_user_id = msg_body.get("channel_user_id") or from_phone
        #conversation key used for Messages pk/sk and idempotency markers (no PII)
        uid = user_hmac(tenant_id, channel, channel_user_id)
        conv_key = msg_body.get("conversation_id") or f"conv#{channel}#{uid}"

        # Prosta idempotencja: jeśli ten event już przerobiliśmy, skip
        if event_id:
            # np. pk = tenant_id#from_phone, sk = event#event_id
            existing = MESSAGES.table.get_item(
                Key={
                    "pk": f"{tenant_id}#{conv_key}",
                    "sk": f"event#{event_id}",
                }
            ).get("Item")
            if existing:
                # już było – pomijamy
                continue

            # zapisujemy event jako przetworzony
            MESSAGES.table.put_item(
                Item={
                    "pk": f"{tenant_id}#{conv_key}",
                    "sk": f"event#{event_id}",
                    "created_at": int(time.time()),
                }
            )
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

        msg = _build_message(msg_body)
         # klucz rozmowy – tak jak w ticketach (conversation_id lub user)
        conv_key = msg.conversation_id or (msg.channel_user_id or msg.from_phone)

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
                language_code=None,
            )
        except Exception:
            # nie blokujemy flow jeśli logowanie padnie
            pass

        actions = ROUTER.handle(msg)
        _publish_actions(actions, msg_body)

    logger.info({"handler": "message_router", "event": "done", "failures": len(batch_failures)})
    # partial batch response for SQS event source mapping
    if batch_failures:
        return {"batchItemFailures": batch_failures}
    return {"statusCode": 200}
