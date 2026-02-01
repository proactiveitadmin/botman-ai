import hashlib
import logging

logger = logging.getLogger(__name__)

def mask_phone(phone: str | None) -> str | None:
    if not phone:
        return phone
    # końcówka + hash
    suffix = phone[-4:]
    digest = hashlib.sha256(phone.encode("utf-8")).hexdigest()[:8]
    return f"...{suffix}#{digest}"

def shorten_body(body: str | None, max_len: int = 40) -> str | None:
    if body is None:
        return None
    return body if len(body) <= max_len else body[:max_len] + "..."

def mask_email(email: str | None) -> str | None:
    if not email:
        return email

    try:
        local, domain = email.split("@", 1)
    except ValueError:
        # niepoprawny format emaila
        return email

    if not local:
        return email

    return f"{local[0]}...@{domain}"

def mask_twilio_messaging_sid(sid: str | None) -> str | None:
    if not sid:
        return sid

    if len(sid) <= 6:
        return sid  # za krótki, żeby sensownie maskować

    prefix = sid[:2]
    suffix = sid[-4:]
    return f"{prefix}...{suffix}"
