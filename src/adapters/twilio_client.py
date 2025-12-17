from twilio.rest import Client
from ..common.config import settings
from ..common.logging import logger
from ..common.logging_utils import mask_phone, mask_twilio_messaging_sid

class TwilioClient:
    def __init__(self):
        # Klient jest aktywny tylko jeśli oba klucze są ustawione
        self.enabled = bool(settings.twilio_account_sid and settings.twilio_auth_token)
        self.client = Client(settings.twilio_account_sid, settings.twilio_auth_token) if self.enabled else None

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
            if getattr(settings, "twilio_messaging_sid", None):
                send_args["messaging_service_sid"] = settings.twilio_messaging_sid
            else:
                send_args["from_"] = settings.twilio_whatsapp_number

            message = self.client.messages.create(**send_args)

            logger.info({
                "msg": "Twilio sent",
                "sid": message.sid,
                "from": mask_twilio_messaging_sid(settings.twilio_messaging_sid) if "messaging_service_sid" in send_args else mask_phone(settings.twilio_whatsapp_number),
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
