import json
import time

from ...common.logging import logger
from ...common.security import verify_optout_token
from ...services.opt_out_service import OptOutService
from ...repos.conversations_repo import ConversationsRepo


OPTOUT = OptOutService(ConversationsRepo())


def _resp(status: int, body: str, content_type: str = "text/plain"):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": content_type,
            "Cache-Control": "no-store",
        },
        "body": body,
    }


def lambda_handler(event, context):
    """HTTP endpoint for opt-out / opt-in by WWW link.

    Query params:
      - tenant_id
      - channel (whatsapp|web|...)
      - uid (hashed user id, from user_hmac)
      - action (optout|optin) [default optout]
      - ts (unix seconds)
      - token (signature)
    """
    try:
        qs = event.get("queryStringParameters") or {}
        tenant_id = (qs.get("tenant_id") or "default").strip()
        channel = (qs.get("channel") or "whatsapp").strip()
        uid = (qs.get("uid") or "").strip()
        action = (qs.get("action") or "optout").strip().lower()
        ts_raw = (qs.get("ts") or "").strip()
        token = (qs.get("token") or "").strip()

        if not uid:
            return _resp(400, "missing uid")

        # Require signed link (except in DEV_MODE)
        dev_mode = (str(qs.get("dev") or "").lower() == "true")
        if not dev_mode:
            if not ts_raw or not token:
                return _resp(400, "missing ts/token")
            if not verify_optout_token(tenant_id, channel, uid, action, int(ts_raw), token):
                return _resp(403, "invalid token")

        if action not in ("optout", "optin"):
            return _resp(400, "invalid action")

        OPTOUT.set_opt_out_by_uid(
            tenant_id=tenant_id,
            channel=channel,
            uid=uid,
            opt_out=(action == "optout"),
            source="web_link",
        )

        # Minimal HTML for human-friendly click
        if action == "optout":
            html = "<html><body><h3>✅ Wypisano</h3><p>Kampanie i powiadomienia zostały wyłączone.</p></body></html>"
        else:
            html = "<html><body><h3>✅ Włączono</h3><p>Kampanie i powiadomienia zostały ponownie włączone.</p></body></html>"

        logger.info({"optout_link": "ok", "tenant_id": tenant_id, "channel": channel, "action": action})
        return _resp(200, html, content_type="text/html; charset=utf-8")

    except Exception as e:
        logger.error({"optout_link_error": str(e)})
        return _resp(500, "error")