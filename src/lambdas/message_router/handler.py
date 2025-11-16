"""
Lambda message_router.

Odbiera komunikaty z kolejki inbound, zamienia je na obiekty domenowe
i przekazuje do RoutingService, a następnie wrzuca odpowiedzi do kolejki outbound.
"""

import json

from ...domain.models import Message
from ...services.routing_service import RoutingService
from ...common.aws import sqs_client, resolve_queue_url
from ...common.logging import logger
from ...common.logging_utils import mask_phone, shorten_body


def lambda_handler(event, context):
    """
    Główny handler AWS Lambda dla message_routera.

    Dla każdej wiadomości z eventu:
    - deserializuje payload,
    - buduje obiekt Message,
    - wywołuje RoutingService.handle,
    - dla akcji typu "reply" publikuje komunikat do kolejki outbound.
    """
    router = RoutingService()
    out_queue = resolve_queue_url("OutboundQueueUrl")

    records = event.get("Records", []) or []
    logger.info({"sender": "message_router_start", "records": len(records)})

    for r in records:
        raw_body = r.get("body", "")
        try:
            msg_body = json.loads(raw_body) if isinstance(raw_body, str) else raw_body
        except Exception as e:
            logger.error({"sender": "message_router_bad_json", "err": str(e), "raw": raw_body})
            continue
        
        logger.info({
            "handler": "message_router",
            "event": "received",
            "from": mask_phone(msg_body.get("from")),
            "to": mask_phone(msg_body.get("to")),
            "body": shorten_body(msg_body.get("body")),
            "tenant_id": msg_body.get("tenant_id"),
        })

        msg = Message(
            tenant_id=msg_body.get("tenant_id", "default"),
            from_phone=msg_body.get("from"),
            to_phone=msg_body.get("to"),
            body=msg_body.get("body", ""),
            conversation_id=msg_body.get("event_id"),
        )

        actions = router.handle(msg) or []
        for a in actions:
            if a.type == "reply":
                sqs_client().send_message(
                    QueueUrl=out_queue,
                    MessageBody=json.dumps(a.payload),
                )

    logger.info({"sender": "message_router_done"})
    return {"statusCode": 200}
