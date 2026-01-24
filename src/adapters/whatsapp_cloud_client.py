from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass

from ..common.logging import logger
from ..common.logging_utils import mask_phone, shorten_body


def _strip_whatsapp_prefix(v: str) -> str:
    if not v:
        return ""
    s = str(v).strip()
    if s.startswith("whatsapp:"):
        s = s[len("whatsapp:") :]
    return s.strip()


def _normalize_to_msisdn(to: str) -> str:
    """Normalize destination to digits without leading '+'.

    WhatsApp Cloud API expects `to` as phone number in international format,
    typically without the leading '+'.
    """
    s = _strip_whatsapp_prefix(to)
    s = s.replace(" ", "")
    if s.startswith("+"):
        s = s[1:]
    return s


@dataclass
class WhatsAppCloudConfig:
    access_token: str
    phone_number_id: str
    # optional metadata
    api_version: str = "v20.0"


class WhatsAppCloudClient:
    """Minimal client for WhatsApp Business Platform (Cloud API).

    Docs: https://developers.facebook.com/docs/whatsapp/cloud-api/
    """

    def __init__(
        self,
        *,
        access_token: str | None = None,
        phone_number_id: str | None = None,
        api_version: str | None = None,
    ):
        self.access_token = (access_token or "").strip()
        self.phone_number_id = (phone_number_id or "").strip()
        self.api_version = (api_version or "v20.0").strip()  # keep as string

        self.enabled = bool(self.access_token and self.phone_number_id)

    @classmethod
    def from_tenant_config(cls, tenant_cfg: dict) -> "WhatsAppCloudClient":
        wa = (tenant_cfg or {}).get("whatsapp_cloud") or (tenant_cfg or {}).get("whatsapp") or {}
        if not isinstance(wa, dict):
            wa = {}
        return cls(
            access_token=wa.get("access_token"),
            phone_number_id=wa.get("phone_number_id"),
            api_version=wa.get("api_version") or wa.get("version") or "v20.0",
        )

    def send_text(self, to: str, body: str) -> dict:
        """Send a WhatsApp text message via Cloud API."""
        if not self.enabled:
            logger.warning(
                {
                    "msg": "WhatsApp Cloud API disabled (dev/misconfig)",
                    "to": mask_phone(to),
                    "body": shorten_body(body),
                }
            )
            return {"status": "DEV_OK"}

        to_msisdn = _normalize_to_msisdn(to)
        if not to_msisdn:
            return {"status": "ERROR", "error": "Missing destination"}

        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to_msisdn,
            "type": "text",
            "text": {"body": body},
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
                try:
                    parsed = json.loads(raw) if raw else {}
                except Exception:
                    parsed = {"raw": raw}
        except urllib.error.HTTPError as e:
            err_raw = ""
            try:
                err_raw = e.read().decode("utf-8", errors="ignore")
            except Exception:
                err_raw = str(e)
            logger.error(
                {
                    "msg": "WhatsApp Cloud send failed",
                    "to": mask_phone(to),
                    "status": getattr(e, "code", None),
                    "error": err_raw,
                }
            )
            return {"status": "ERROR", "http_status": getattr(e, "code", None), "error": err_raw}
        except Exception as e:
            logger.error(
                {
                    "msg": "WhatsApp Cloud send failed",
                    "to": mask_phone(to),
                    "error": str(e),
                }
            )
            return {"status": "ERROR", "error": str(e)}

        # Cloud API returns `messages: [{id: ...}]`
        msg_id = None
        try:
            msgs = (parsed or {}).get("messages") or []
            if msgs and isinstance(msgs, list):
                msg_id = (msgs[0] or {}).get("id")
        except Exception:
            msg_id = None

        logger.info(
            {
                "msg": "WhatsApp Cloud sent",
                "to": mask_phone(to),
                "message_id": msg_id,
            }
        )

        return {"status": "OK", "message_id": msg_id, "raw": parsed}
