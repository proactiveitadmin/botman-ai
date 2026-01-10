import os, hmac, hashlib, base64
from typing import Dict
from .config import settings
from .logging import logger

def verify_twilio_signature(
    url: str,
    params: Dict[str, str],
    signature: str,
    auth_token: str | None = None,
) -> bool:
    dev_mode = os.getenv("DEV_MODE", "false").lower() == "true" or settings.dev_mode
    if dev_mode:
        logger.info({"security": "twilio_signature_skipped_dev"})
        return True

    token = (auth_token or "").strip() or (settings.twilio_auth_token or "").strip()
    if not token:
        logger.error({"security": "twilio_token_missing"})
        return False

    s = url + "".join([k + params[k] for k in sorted(params.keys())])
    mac = hmac.new(token.encode(), s.encode(), hashlib.sha1)
    computed = base64.b64encode(mac.digest()).decode()
    return hmac.compare_digest(computed, signature)



# ---------------------------------------------------------------------------
# Deterministic pseudonymization / hashing utilities (PII-safe lookups)
# ---------------------------------------------------------------------------

_cached_peppers: dict[str, str] = {}

def _load_secure_parameter(param_name: str) -> str | None:
    """Loads SSM SecureString/plain parameter once per cold start."""
    if not param_name:
        return None
    try:
        from .aws import ssm_client
        resp = ssm_client().get_parameter(Name=param_name, WithDecryption=True)
        return (resp.get("Parameter") or {}).get("Value")
    except Exception as e:
        logger.error({"security": "ssm_get_parameter_failed", "param": param_name, "error": str(e)})
        return None

def _get_pepper(env_value_name: str, env_param_name: str) -> str:
    # Priority: explicit env secret -> SSM param -> empty (will break comparisons safely)
    cache_key = f"{env_value_name}|{env_param_name}"
    if cache_key in _cached_peppers:
        return _cached_peppers[cache_key]

    direct = os.getenv(env_value_name, "").strip()
    if direct:
        _cached_peppers[cache_key] = direct
        return direct

    param = os.getenv(env_param_name, "").strip()
    if param:
        val = (_load_secure_parameter(param) or "").strip()
        _cached_peppers[cache_key] = val
        return val

    _cached_peppers[cache_key] = ""
    return ""

def normalize_phone(phone: str) -> str:
    p = (phone or "").strip()
    if p.startswith("whatsapp:"):
        p = p.split(":", 1)[1]
    # NOTE: dla pelnego E.164, warto tu użyć libphonenumbers.
    return p

def _hmac_b64url(key: str, msg: str) -> str:
    mac = hmac.new(key.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode("utf-8").rstrip("=")

def phone_hmac(tenant_id: str, phone: str) -> str:
    pepper = _get_pepper("PHONE_HASH_PEPPER", "PHONE_HASH_PEPPER_PARAM")
    msg = f"{tenant_id}|{normalize_phone(phone)}"
    return _hmac_b64url(pepper, msg)

def user_hmac(tenant_id: str, channel: str, channel_user_id: str) -> str:
    pepper = _get_pepper("USER_HASH_PEPPER", "USER_HASH_PEPPER_PARAM")
    msg = f"{tenant_id}|{channel}|{channel_user_id}"
    return _hmac_b64url(pepper, msg)

def otp_hash(tenant_id: str, purpose: str, otp_code: str) -> str:
    """Hashes OTP for storage/compare (never store raw OTP)."""
    pepper = _get_pepper("OTP_HASH_PEPPER", "OTP_HASH_PEPPER_PARAM") or _get_pepper("PHONE_HASH_PEPPER","PHONE_HASH_PEPPER_PARAM")
    msg = f"{tenant_id}|{purpose}|{(otp_code or '').strip()}"
    return _hmac_b64url(pepper, msg)

def phone_last4(phone: str) -> str:
    if not phone:
        return ""
    digits = "".join(c for c in phone if c.isdigit())
    return digits[-4:] if len(digits) >= 4 else digits
