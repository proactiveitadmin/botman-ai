from twilio.rest import Client
from ..common.logging import logger
from ..common.logging_utils import mask_phone, mask_twilio_messaging_sid

class TwilioClient:
    def __init__(
        self,
        *,
        account_sid: str | None = None,
        auth_token: str | None = None,
        messaging_service_sid: str | None = None,
        whatsapp_number: str | None = None,
    ):
        self.account_sid = (account_sid or "").strip()
        self.auth_token = (auth_token or "").strip()
        self.messaging_service_sid = (messaging_service_sid or "").strip() or None
        self.whatsapp_number = (whatsapp_number or "").strip()

        self.enabled = bool(self.account_sid and self.auth_token)
        self.client = Client(self.account_sid, self.auth_token) if self.enabled else None

    @classmethod
    def from_tenant_config(cls, tenant_cfg: dict) -> "TwilioClient":
        tw = (tenant_cfg or {}).get("twilio") or {}
        if not isinstance(tw, dict):
            tw = {}
        return cls(
            account_sid=tw.get("account_sid"),
            auth_token=tw.get("auth_token"),
            messaging_service_sid=tw.get("messaging_service_sid") or tw.get("messaging_sid"),
            whatsapp_number=tw.get("whatsapp_number") or (tenant_cfg or {}).get("twilio_to"),
        )
        
    def _ensure_client(self) -> None:
        self.enabled = bool((self.account_sid or "").strip() and (self.auth_token or "").strip())
        if self.enabled and self.client is None:
            self.client = Client(self.account_sid, self.auth_token)

    def send_text(self, to: str, body: str):
        """
        Wysyła wiadomość WhatsApp przez Twilio.
        Automatycznie używa Messaging Service SID, jeśli jest skonfigurowany.
        """
        self._ensure_client()
        if not self.enabled:
            logger.warning({
                "msg": "Twilio disabled (dev mode)",
                "to": mask_phone(to),
                "body": body,
            })
            return {"status": "DEV_OK"}

        send_args = {"to": to, "body": body}

        if self.messaging_service_sid:
            send_args["messaging_service_sid"] = self.messaging_service_sid
        else:
            # jeśli nie ma Messaging Service SID, MUSI być from_
            if not self.whatsapp_number:
                logger.error({
                    "msg": "Twilio misconfigured: missing whatsapp_number",
                    "to": mask_phone(to),
                })
                return {"status": "ERROR", "error": "Missing whatsapp_number"}
            send_args["from_"] = self.whatsapp_number

        # 1) tylko wysyłka w try/except
        try:
            message = self.client.messages.create(**send_args)
        except Exception as e:
            logger.error({
                "msg": "Twilio send failed",
                "error": str(e),
                "to": mask_phone(to),
            })
            return {"status": "ERROR", "error": str(e)}

        # 2) logowanie best-effort (nie może zmieniać wyniku na ERROR)
        try:
            logger.info({
                "msg": "Twilio sent",
                "sid": getattr(message, "sid", None),
                "from": (
                    mask_twilio_messaging_sid(self.messaging_service_sid)
                    if "messaging_service_sid" in send_args
                    else mask_phone(self.whatsapp_number)
                ),
                "to": mask_phone(to),
                "used": "messaging_service_sid" if "messaging_service_sid" in send_args else "from_",
            })
        except Exception:
            pass

        return {"status": "OK", "sid": getattr(message, "sid", None)}
