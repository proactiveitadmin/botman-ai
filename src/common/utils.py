import json, uuid
import secrets
import string
from typing import Any, Optional
from .config import settings
from ..domain.models import Message, Action

def to_json(o: Any) -> str:
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))

def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex}"

def generate_verification_code(length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

def whatsapp_wa_me_link(code: str) -> str:
    """
    Buduje link https://wa.me/<number>?text=KOD:ABC123
    Zakładam, że settings.twilio_whatsapp_number = "whatsapp:+48..." –
    trzeba zdjąć prefix "whatsapp:".
    """
    raw = settings.twilio_whatsapp_number  # np. "whatsapp:+48000000000"
    phone = raw.replace("whatsapp:", "")
    return f"https://wa.me/{phone}?text=KOD:{code}"
    
def build_reply_action(
    msg: Message,
    lang: str,
    body: str,
    channel: Optional[str] = None,
    channel_user_id: Optional[str] = None,
) -> Action:
    """
    Uniwersalny helper do tworzenia akcji reply.
    Używany przez RoutingService i CRMFlowService.
    """
    return Action(
        "reply",
        {
            "to": msg.from_phone,
            "body": body,
            "tenant_id": msg.tenant_id,
            "channel": channel or msg.channel,
            "channel_user_id": channel_user_id or msg.channel_user_id,
            "language_code": lang,
            "message_type": "reply",
        },
    )