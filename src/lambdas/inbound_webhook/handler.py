"""
Lambda obsługująca webhook Twilio (przychodzące wiadomości WhatsApp).

Zadania:
- walidacja sygnatury Twilio,
- sparsowanie parametrów z body,
- zamiana na zdarzenie wewnętrzne i wysłanie do kolejki inbound.
"""

import os
import json
import urllib.parse

from ...services.spam_service import SpamService
from ...common.utils import new_id
from ...common.aws import sqs_client, resolve_queue_url
from ...common.security import verify_twilio_signature
from ...common.logging import logger
from ...common.logging_utils import mask_phone, shorten_body
from ...common.security import user_hmac


NGROK_HOST_HINTS = (".ngrok-free.app", ".ngrok.io")
spam_service = SpamService()


def _build_public_url(event, headers_in) -> str:
    """
    Buduje publiczny URL widziany przez Twilio, używany do weryfikacji sygnatury.

    Uwzględnia:
    - nagłówki Host / X-Forwarded-Proto,
    - zmienną TWILIO_PUBLIC_URL, jeśli jest ustawiona,
    - query string z eventu.
    """
    host = headers_in.get("Host", "localhost")
    raw_path = (
        (event.get("requestContext", {}) or {}).get("path")
        or event.get("path")
        or "/webhooks/twilio"
    )
    public_base = os.getenv("TWILIO_PUBLIC_URL")

    if public_base:
        base = public_base.split("?")[0]
    else:
        # Jeżeli tunel (ngrok), zakładamy HTTPS
        proto = (
            "https"
            if any(host.endswith(suf) for suf in NGROK_HOST_HINTS)
            else headers_in.get("X-Forwarded-Proto", "http")
        )
        base = f"{proto}://{host}{raw_path}"

    mv_qs = event.get("multiValueQueryStringParameters")
    qs = event.get("queryStringParameters")
    query = (
        urllib.parse.urlencode(mv_qs, doseq=True)
        if mv_qs
        else (urllib.parse.urlencode(qs) if qs else "")
    )
    return f"{base}?{query}" if query else base


def _parse_params(body_raw: str, content_type: str) -> dict:
    """
    Parsuje parametry z body na słownik.

    Obsługiwane formaty:
    - application/x-www-form-urlencoded (domyślny format Twilio),
    - application/json.
    """
    ctype = (content_type or "").lower()

    # Domyślnie traktujemy brak Content-Type jak form-encoded (ułatwia testy)
    if "application/x-www-form-urlencoded" in ctype or not ctype:
        pairs = urllib.parse.parse_qsl(body_raw, keep_blank_values=True)
        return {k: v for k, v in pairs}

    try:
        return json.loads(body_raw) if body_raw else {}
    except json.JSONDecodeError:
        logger.warning({"webhook": "invalid_json"})
        return {}


def lambda_handler(event, context):
    """
    Główny handler AWS Lambda dla webhooka Twilio.

    Waliduje sygnaturę (chyba że DEV_MODE=true), a następnie:
    - buduje obiekt zdarzenia wewnętrznego,
    - wysyła go do kolejki InboundEventsQueueUrl.
    """
    try:
        body_raw = event.get("body") or ""
        if event.get("isBase64Encoded"):
            import base64

            body_raw = base64.b64decode(body_raw).decode("utf-8", errors="ignore")

        if len(body_raw) > 8 * 1024:
            return {"statusCode": 413, "body": "Payload too large"}

        headers_in = event.get("headers") or {}
        content_type = headers_in.get("Content-Type") or headers_in.get("content-type") or ""

        params = _parse_params(body_raw, content_type)
        
        url = _build_public_url(event, headers_in)
        signature = headers_in.get("X-Twilio-Signature", "")
        
        # Weryfikacja sygnatury Twilio (jeśli nie wyłączona flagą)
        if not verify_twilio_signature(url, params, signature):
            logger.warning({"webhook": "invalid_signature"})
            return {"statusCode": 403, "body": "Forbidden"}

        tenant_id = "default"  # TODO: w przyszłości mapowanie po numerze / endpointcie
        from_phone = params.get("From")
        channel_user_id = from_phone
        uid = user_hmac(tenant_id, "whatsapp", channel_user_id)
        conv_id = f"conv#whatsapp#{uid}"

        # --- SPAM / RATE LIMIT ---
        if spam_service.is_blocked(tenant_id=tenant_id, phone=from_phone):
            logger.warning(
                {
                    "webhook": "rate_limited",
                    "from": mask_phone(from_phone),
                    "tenant_id": tenant_id,
                }
            )
            # Twilio akceptuje dowolne body, ważny jest status HTTP
            return {"statusCode": 429, "body": "Too Many Requests"}

        msg = {
            "event_id": new_id("evt-"),
            "from": from_phone,
            "to": params.get("To"),
            "body": params.get("Body", ""),
            "tenant_id": tenant_id,
            "ts": (event.get("requestContext") or {}).get("requestTimeEpoch"),
            "message_sid": params.get("MessageSid"),
            "channel": "whatsapp",
            "channel_user_id": from_phone,
            "conversation_id": conv_id,
        }


        queue_url = resolve_queue_url("InboundEventsQueueUrl")
        sqs_client().send_message(
            QueueUrl=queue_url, 
            MessageBody=json.dumps(msg),            
            MessageGroupId=msg.get('conversation_id') or 'default',
            MessageDeduplicationId=msg.get('event_id') or new_id('dedup-'),
        )

        logger.info({
            "webhook": "ok",
            "from": mask_phone(msg.get("from")),
            "to": mask_phone(msg.get("to")),
            "body": shorten_body(msg.get("body")),
            "tenant_id": msg.get("tenant_id"),
        })
        
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "text/xml"},
            "body": "<Response></Response>",
        }

    except Exception as e:
        logger.error({"inbound_error": str(e)})
        return {"statusCode": 200, "body": "<Response></Response>"}
