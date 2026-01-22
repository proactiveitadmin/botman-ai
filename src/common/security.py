import os, hmac, hashlib, base64, time
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
        if not (os.getenv("DEV_MODE", "false").lower() == "true") and direct.startswith("/"):
            val = (_load_secure_parameter(direct) or "").strip()
            _cached_peppers[cache_key] = val
            return val
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

# ---------------------------------------------------------------------------
#  Opt-out link signing (WWW link flow)
# ---------------------------------------------------------------------------

def _hmac_b64url_raw(secret: str, msg: str) -> str:
    """Internal: base64url(HMAC-SHA256(secret, msg)) without padding."""
    mac = hmac.new(secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode("utf-8").rstrip("=")

def sign_optout_token(tenant_id: str, channel: str, user_id: str, action: str, ts: int) -> str:
    """Signs opt-out / opt-in link parameters.

    Token is derived from USER_HASH_PEPPER (same secret family as user_hmac).
    It does NOT reveal PII and can be safely used as a query param.
    """
    pepper = _get_pepper("USER_HASH_PEPPER", "USER_HASH_PEPPER_PARAM")
    payload = f"{tenant_id}|{channel}|{user_id}|{action}|{int(ts)}"
    return _hmac_b64url_raw(pepper, payload)

def verify_optout_token(tenant_id: str, channel: str, user_id: str, action: str, ts: int, token: str, *, max_age_seconds: int = 86400 * 30) -> bool:
    """Verifies opt-out / opt-in token with replay window."""
    try:
        ts_int = int(ts)
    except Exception:
        return False

    now = int(time.time())
    if ts_int <= 0 or abs(now - ts_int) > int(max_age_seconds):
        return False

    expected = sign_optout_token(tenant_id, channel, user_id, action, ts_int)
    # constant-time compare
    try:
        return hmac.compare_digest(expected, (token or "").strip())
    except Exception:
        return False

def phone_last4(phone: str) -> str:
    if not phone:
        return ""
    digits = "".join(c for c in phone if c.isdigit())
    return digits[-4:] if len(digits) >= 4 else digits


# ---------------------------------------------------------------------------
# Conversation key (PII-safe) helper
# ---------------------------------------------------------------------------

def conversation_key(
    tenant_id: str,
    channel: str,
    channel_user_id: str | None,
    conversation_id: str | None = None,
) -> str:
    """Builds the canonical conversation key used in Messages PK.

    We avoid putting PII (phone/session id) directly into DynamoDB keys.
    If a stable conversation_id exists (e.g. external conversation/thread id),
    we use it. Otherwise we derive a salted id from (tenant, channel, user).

    Returned format (when derived): "conv#<channel>#<uid>".
    """

    if conversation_id:
        return conversation_id
    # channel_user_id is required to create a stable key; fall back to empty
    # string so the resulting key remains deterministic (and clearly invalid).
    cuid = channel_user_id or ""
    uid = user_hmac(tenant_id, channel or "whatsapp", cuid)
    return f"conv#{channel or 'whatsapp'}#{uid}"