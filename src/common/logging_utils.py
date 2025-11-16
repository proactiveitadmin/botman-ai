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
