from twilio.rest import Client
from ..common.config import settings
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
        # Fallback to global settings for backward compatibility
        self.account_sid = (account_sid or settings.twilio_account_sid or "").strip()
        self.auth_token = (auth_token or settings.twilio_auth_token or "").strip()
        self.messaging_service_sid = (messaging_service_sid or getattr(settings, "twilio_messaging_sid", None) or "").strip() or None
        self.whatsapp_number = (whatsapp_number or settings.twilio_whatsapp_number or "").strip()

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
            messaging_service_sid=tw.get("messaging_service_sid") or tw.get("messaging_sid") or tw.get("messaging_service_sid"),
            whatsapp_number=tw.get("whatsapp_number") or (tenant_cfg or {}).get("twilio_to"),
        )
 
    def send_text(self, to: str, body: str):
        """
        Wysyła wiadomość WhatsApp przez Twilio.
        Automatycznie używa Messaging Service SID, jeśli jest skonfigurowany.
        """
        if not self.enabled:
            logger.info({
                "msg": "Twilio disabled (dev mode)", 
                "to": mask_phone(to), 
                "body": body})
            return {"status": "DEV_OK"}

        try:
            send_args = {
                "to": to,
                "body": body,
            }

            # Jeśli Messaging Service SID jest ustawiony — używamy go zamiast from_
            if self.messaging_service_sid:
                send_args["messaging_service_sid"] = self.messaging_service_sid
            else:
                send_args["from_"] = self.whatsapp_number
            message = self.client.messages.create(**send_args)

            logger.info({
                "msg": "Twilio sent",
                "sid": message.sid,
                "from": mask_twilio_messaging_sid(self.messaging_service_sid) if "messaging_service_sid" in send_args else mask_phone(self.whatsapp_number),
                "to": mask_phone(to),
                "used": "messaging_service_sid" if "messaging_service_sid" in send_args else "from_"
            })
            return {"status": "OK", "sid": message.sid}

        except Exception as e:
            logger.error({
                "msg": "Twilio send failed", 
                "error": str(e), 
                "to": mask_phone(to)})
            return {"status": "ERROR", "error": str(e)}
