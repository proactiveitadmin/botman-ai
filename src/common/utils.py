import json, uuid
import secrets
import string
from typing import Any
from .config import settings

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