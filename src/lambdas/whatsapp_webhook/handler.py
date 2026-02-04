"""
Lambda webhook for WhatsApp Business Platform (Cloud API).

Supports:
- GET verification (hub.challenge) using per-tenant verify_token
- POST message ingestion:
  - signature verification (X-Hub-Signature-256) using per-tenant app_secret
  - parsing incoming messages and enqueueing internal inbound events

Multi-tenant:
- preferred: /webhooks/whatsapp (shared endpoint). Optional: /webhooks/whatsapp/{tenant}
"""

from __future__ import annotations

import json
import os
import re
import hmac
import hashlib

from ...services.spam_service import SpamService
from ...services.tenant_config_service import default_tenant_config_service
from ...repos.tenants_repo import TenantsRepo
from ...common.aws import sqs_client, resolve_queue_url
from ...common.utils import new_id
from ...common.logging import logger
from ...common.logging_utils import mask_phone, shorten_body
from ...common.security import user_hmac


spam_service = SpamService()
tenant_cfg = default_tenant_config_service()
tenants_repo = TenantsRepo()


def _normalize_wa_id(wa_id: str | None) -> str | None:
    if not wa_id:
        return None
    s = str(wa_id).strip()
    s = re.sub(r"\s+", "", s)
    # WhatsApp wa_id is usually digits without '+'
    if s.startswith("+"):
        s = s[1:]
    return s or None


def _to_internal_from(wa_id: str | None) -> str | None:
    """Return `whatsapp:+<digits>` to keep parity with Twilio channel_user_id."""
    n = _normalize_wa_id(wa_id)
    if not n:
        return None
    return f"whatsapp:+{n}"


def _verify_signature(raw_body: str, header_sig: str, app_secret: str) -> bool:
    """Verify Meta webhook signature.

    Header format: 'sha256=<hex>'.
    """
    dev_mode = os.getenv("DEV_MODE", "false").lower() == "true"
    if dev_mode:
        logger.info({"security": "whatsapp_signature_skipped_dev"})
        return True

    if not app_secret:
        logger.error({"security": "whatsapp_app_secret_missing"})
        return False

    if not header_sig:
        return False

    hs = header_sig.strip()
    if hs.startswith("sha256="):
        hs = hs.split("=", 1)[1]

    mac = hmac.new(app_secret.encode("utf-8"), raw_body.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, hs)


def _tenant_from_path(event: dict) -> str | None:
    path_params = event.get("pathParameters") or {}
    return (
        path_params.get("tenant")
        or path_params.get("tenantId")
        or path_params.get("tenant_id")
        or None
    )


def _handle_get(event: dict, tenant_id: str | None) -> dict:
    qs = event.get("queryStringParameters") or {}
    mode = qs.get("hub.mode") or qs.get("hub_mode") or qs.get("mode")
    token = qs.get("hub.verify_token") or qs.get("hub_verify_token") or qs.get("verify_token")
    challenge = qs.get("hub.challenge") or qs.get("hub_challenge") or qs.get("challenge")

    if mode != "subscribe" or not challenge:
        return {"statusCode": 400, "body": "Bad Request"}

    if tenant_id:
        cfg = tenant_cfg.get(tenant_id)
        wa = (cfg.get("whatsapp_cloud") or cfg.get("whatsapp") or {})
    verify_token = (os.getenv("WHATSAPP_VERIFY_TOKEN") or "").strip()

    if verify_token and token == verify_token:
        return {"statusCode": 200, "body": str(challenge)}
    return {"statusCode": 403, "body": "Forbidden"}


def _extract_messages(payload: dict) -> list[dict]:
    """Extracts message objects from standard Cloud API webhook payload."""
    out: list[dict] = []
    try:
        for entry in (payload.get("entry") or []):
            for change in (entry.get("changes") or []):
                value = (change or {}).get("value") or {}
                msgs = value.get("messages") or []
                for m in msgs:
                    if isinstance(m, dict):
                        out.append(m)
    except Exception:
        return []
    return out

def _extract_phone_number_id(payload: dict) -> str | None:
    """Extract metadata.phone_number_id from standard Cloud API webhook payload."""
    try:
        for entry in (payload.get("entry") or []):
            for change in (entry.get("changes") or []):
                value = (change or {}).get("value") or {}
                meta = value.get("metadata") or {}
                pnid = (meta.get("phone_number_id") or "").strip()
                if pnid:
                    return pnid
    except Exception:
        return None
    return None


def lambda_handler(event, context):
    try:
        tenant_id = _tenant_from_path(event)

        method = (event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method") or "").upper()
        if method == "GET":
            return _handle_get(event, tenant_id)

        # POST
        raw_body = event.get("body") or ""
        if event.get("isBase64Encoded"):
            import base64
            raw_body = base64.b64decode(raw_body).decode("utf-8", errors="ignore")


        if len(raw_body) > 256 * 1024:
            return {"statusCode": 413, "body": "Payload too large"}

        # Parse JSON early (needed to resolve tenant when endpoint is shared)
        try:
            payload = json.loads(raw_body) if raw_body else {}
        except Exception:
            return {"statusCode": 400, "body": "Invalid JSON"}

        # Resolve tenant when webhook URL is shared (no {tenant} in path)
        if not tenant_id:
            phone_number_id = _extract_phone_number_id(payload)
            tenant_item = tenants_repo.find_by_whatsapp_phone_number_id(phone_number_id) if phone_number_id else None
            tenant_id = (tenant_item or {}).get("tenant_id")
            if not tenant_id:
                logger.error({"webhook": "tenant_missing", "phone_number_id": phone_number_id})
                return {"statusCode": 200, "body": "OK"}

        headers = event.get("headers") or {}
        sig = headers.get("X-Hub-Signature-256") or headers.get("x-hub-signature-256") or ""

        cfg = tenant_cfg.get(tenant_id)
        wa_cfg = (cfg.get("whatsapp_cloud") or cfg.get("whatsapp") or {})
        app_secret = (wa_cfg.get("app_secret") or "").strip()

        if not _verify_signature(raw_body, sig, app_secret):
            logger.warning({"webhook": "invalid_signature", "tenant_id": tenant_id})
            return {"statusCode": 403, "body": "Forbidden"}


        messages = _extract_messages(payload)
        if not messages:
            # Might be statuses/read receipts, etc.
            return {"statusCode": 200, "body": "OK"}

        queue_url = resolve_queue_url("InboundEventsQueueUrl")

        for m in messages:
            wa_id = ((m.get("from") or "").strip())  # digits
            from_phone = _to_internal_from(wa_id)
            if not from_phone:
                continue

            # SPAM / RATE LIMIT
            if spam_service.is_blocked(tenant_id=tenant_id, phone=from_phone):
                logger.warning(
                    {
                        "webhook": "rate_limited",
                        "from": mask_phone(from_phone),
                        "tenant_id": tenant_id,
                    }
                )
                continue

            msg_text = ""
            if m.get("type") == "text":
                msg_text = ((m.get("text") or {}).get("body") or "")
            else:
                # For now ignore non-text; can be extended (image, audio, interactive)
                msg_text = f"[unsupported:{m.get('type')}]" if m.get("type") else ""

            channel_user_id = from_phone
            uid = user_hmac(tenant_id, "whatsapp", channel_user_id)
            conv_id = f"conv#whatsapp#{uid}"

            internal = {
                "event_id": new_id("evt-"),
                "from": from_phone,
                "to": None,
                "body": msg_text,
                "tenant_id": tenant_id,
                "ts": (event.get("requestContext") or {}).get("timeEpoch"),
                "message_sid": m.get("id"),  # keep field name for compatibility
                "channel": "whatsapp",
                "channel_user_id": channel_user_id,
                "conversation_id": conv_id,
                "provider": "whatsapp_cloud",
            }

            dedup_id = (m.get("id") or "").strip() or internal["event_id"]

            sqs_client().send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(internal),
                MessageGroupId=conv_id,
                MessageDeduplicationId=dedup_id,
            )

            logger.info(
                {
                    "webhook": "ok",
                    "provider": "whatsapp_cloud",
                    "from": mask_phone(from_phone),
                    "body": shorten_body(msg_text),
                    "tenant_id": tenant_id,
                }
            )

        return {"statusCode": 200, "body": "OK"}

    except Exception as e:
        logger.error({"whatsapp_webhook_error": str(e)})
        return {"statusCode": 200, "body": "OK"}
