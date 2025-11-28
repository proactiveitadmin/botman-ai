"""
Lambda message_router.

Odbiera komunikaty z kolejki inbound, zamienia je na obiekty domenowe
i przekazuje do RoutingService, a następnie wrzuca odpowiedzi do kolejki outbound.
"""

import json

from ...services.routing_service import RoutingService
from ...services.template_service import TemplateService
from ...services.kb_service import KBService
from ...adapters.openai_client import OpenAIClient
from ...repos.conversations_repo import ConversationsRepo
from ...repos.messages_repo import MessagesRepo
from ...repos.tenants_repo import TenantsRepo 
from ...common.aws import resolve_queue_url, sqs_client 
from ...domain.models import Message
from ...common.logging import logger
from ...common.logging_utils import mask_phone, shorten_body

ROUTER = RoutingService()

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
        conversation_id=body.get("event_id"),
        channel=body.get("channel", "whatsapp"),
        channel_user_id=body.get("channel_user_id") or body.get("from"),
        language_code=body.get("language_code"),
    )


def _publish_actions(actions, original_body: dict):
    queue_url = resolve_queue_url("OutboundQueueUrl")
    for a in actions or []:
        if a.type != "reply":
            continue

        payload = a.payload
        sqs_client().send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(payload),
        )

        logger.info(
            {
                "handler": "message_router",
                "event": "queued_outbound",
                "from": mask_phone(original_body.get("from")),
                "to": mask_phone(payload.get("to")),
                "body": shorten_body(payload.get("body")),
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
    records = event.get("Records") or []
    if not records:
        logger.info({"handler": "message_router", "event": "no_records"})
        return {"statusCode": 200, "body": "no-records"}

    for r in records:
        msg_body = _parse_record(r)
        if not msg_body:
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

        msg = _build_message(msg_body)
        actions = ROUTER.handle(msg)
        _publish_actions(actions, msg_body)

    logger.info({"handler": "message_router", "event": "done"})
    return {"statusCode": 200}
