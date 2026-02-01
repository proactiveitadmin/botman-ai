import base64
import hmac
import hashlib

from src.common.security import verify_twilio_signature
from src.common.config import settings


def test_verify_twilio_signature_dev_mode_via_env(monkeypatch):
    # DEV_MODE w env albo settings.dev_mode -> zawsze True
    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.setattr(settings, "dev_mode", False, raising=False)

    ok = verify_twilio_signature(
        url="https://example.com/webhook",
        params={"Body": "hello"},
        signature="anything",
    )
    assert ok is True


def test_verify_twilio_signature_missing_token(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.setattr(settings, "dev_mode", False, raising=False)
    monkeypatch.setattr(settings, "twilio_auth_token", "", raising=False)

    ok = verify_twilio_signature(
        url="https://example.com/webhook",
        params={"Body": "hello"},
        signature="sig",
    )
    assert ok is False


def _compute_sig(token: str, url: str, params: dict) -> str:
    s = url + "".join([k + params[k] for k in sorted(params.keys())])
    mac = hmac.new(token.encode(), s.encode(), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode()


def test_verify_twilio_signature_valid(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.setattr(settings, "dev_mode", False, raising=False)
    monkeypatch.setattr(settings, "twilio_auth_token", "secret", raising=False)

    url = "https://example.com/webhook"
    params = {"Body": "hello", "From": "+48123"}
    sig = _compute_sig("secret", url, params)

    assert verify_twilio_signature(url, params, sig) is True
    assert verify_twilio_signature(url, params, "bad-signature") is False
