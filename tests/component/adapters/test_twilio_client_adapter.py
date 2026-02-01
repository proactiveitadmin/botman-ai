import pytest

from src.adapters.twilio_client import TwilioClient
from src.common.config import settings
import src.adapters.twilio_client as twilio_mod


class DummyMessage:
    def __init__(self, sid="SID-123"):
        self.sid = sid


class DummyMessages:
    def __init__(self):
        self.last_kwargs = None
        self.should_fail = False

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self.should_fail:
            raise RuntimeError("send failed")
        return DummyMessage()


class DummyClient:
    def __init__(self, *args, **kwargs):
        self.messages = DummyMessages()


def test_send_text_dev_mode_when_disabled(monkeypatch):
    """
    Brak SID / TOKEN -> client.disabled, zwracamy DEV_OK i nie dzwonimy do Twilio.
    """
    client = TwilioClient()
    monkeypatch.setattr(client, "account_sid", "", raising=False)
    monkeypatch.setattr(client, "auth_token", "", raising=False)
    client._ensure_client()
    assert client.enabled is False

    res = client.send_text("whatsapp:+48123123123", "hello")
    assert res == {"status": "DEV_OK"}


def test_send_text_uses_messaging_service_sid_when_configured(monkeypatch):
    client = TwilioClient()
    monkeypatch.setattr(client, "account_sid", "AC123", raising=False)
    monkeypatch.setattr(client, "auth_token", "secret", raising=False)
    monkeypatch.setattr(client, "messaging_service_sid", "MG123", raising=False)
    monkeypatch.setattr(client, "whatsapp_number", "whatsapp:+48000000000", raising=False)

    dummy_client = DummyClient()
    monkeypatch.setattr(twilio_mod, "Client", lambda sid, token: dummy_client)
    client._ensure_client()
    assert client.enabled is True

    res = client.send_text("whatsapp:+48123123123", "hello world")
    assert res["status"] == "OK"
    assert dummy_client.messages.last_kwargs["to"] == "whatsapp:+48123123123"
    # messaging_service_sid ma być użyty zamiast from_
    assert "messaging_service_sid" in dummy_client.messages.last_kwargs
    assert "from_" not in dummy_client.messages.last_kwargs


def test_send_text_uses_from_when_no_messaging_service(monkeypatch):
    client = TwilioClient()
    monkeypatch.setattr(client, "account_sid", "AC123", raising=False)
    monkeypatch.setattr(client, "auth_token", "secret", raising=False)
    monkeypatch.setattr(client, "messaging_service_sid", "", raising=False)
    monkeypatch.setattr(client, "whatsapp_number", "whatsapp:+48000000000", raising=False)

    dummy_client = DummyClient()
    monkeypatch.setattr(twilio_mod, "Client", lambda sid, token: dummy_client)
    client._ensure_client()
    res = client.send_text("whatsapp:+48123123123", "hi")
    assert res["status"] == "OK"
    assert dummy_client.messages.last_kwargs["from_"] == "whatsapp:+48000000000"


def test_send_text_handles_exception(monkeypatch):
    client = TwilioClient()
    monkeypatch.setattr(client, "account_sid", "AC123", raising=False)
    monkeypatch.setattr(client, "auth_token", "secret", raising=False)
    monkeypatch.setattr(client, "messaging_service_sid", "", raising=False)
    monkeypatch.setattr(client, "whatsapp_number", "whatsapp:+48000000000", raising=False)

    dummy_client = DummyClient()
    dummy_client.messages.should_fail = True
    monkeypatch.setattr(twilio_mod, "Client", lambda sid, token: dummy_client)
    client._ensure_client()
    res = client.send_text("whatsapp:+48123123123", "hi")
    assert res["status"] == "ERROR"
    assert "error" in res
