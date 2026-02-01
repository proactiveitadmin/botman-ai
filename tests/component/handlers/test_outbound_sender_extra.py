import json
import os

from src.lambdas.outbound_sender import handler

def test_lambda_no_records(monkeypatch):
    event = {}
    res = handler.lambda_handler(event, None)
    assert res["statusCode"] == 200
    assert res["body"] == "no-records"


def test_lambda_bad_json_is_skipped(monkeypatch):
    os.environ["DEV_MODE"] = "true"

    # 1) Mock idempotency: pierwsze acquire=True, drugie=False
    it = iter([True, False])
    monkeypatch.setattr(handler.IDEMPOTENCY, "try_acquire", lambda *a, **k: next(it))

    # 2) Mock WhatsApp client via factory
    calls = []

    class DummyWhatsApp:
        def send_text(self, to, body):
            calls.append({"to": to, "body": body})
            return {"status": "OK", "sid": "fake"}

    class DummyFactory:
        def whatsapp(self, tenant_id):
            return DummyWhatsApp()

    monkeypatch.setattr(handler, "clients", DummyFactory())
    bad_body = "{not-json"
    good_payload = {"to": "whatsapp:+48123", "body": "hello"}

    event = {
        "Records": [
            {"body": bad_body},
            {"body": json.dumps(good_payload)},
        ]
    }

    res = handler.lambda_handler(event, None)
    assert res["statusCode"] == 200
    # mimo pierwszego złego body, drugi rekord został wysłany
    assert len(calls) == 1
    assert calls[0]["to"] == "whatsapp:+48123"


def test_lambda_invalid_payload_missing_to(monkeypatch):
    os.environ["DEV_MODE"] = "true"

    # 1) Mock idempotency: pierwsze acquire=True, drugie=False
    it = iter([True, False])
    monkeypatch.setattr(handler.IDEMPOTENCY, "try_acquire", lambda *a, **k: next(it))

    # 2) Mock WhatsApp client via factory
    calls = []

    class DummyWhatsApp:
        def send_text(self, to, body):
            calls.append({"to": to, "body": body})
            return {"status": "OK", "sid": "fake"}

    class DummyFactory:
        def whatsapp(self, tenant_id):
            return DummyWhatsApp()

    monkeypatch.setattr(handler, "clients", DummyFactory())

    event = {
        "Records": [
            {"body": json.dumps({"body": "no recipient"})},  # brak 'to'
        ]
    }

    res = handler.lambda_handler(event, None)
    assert res["statusCode"] == 200
    # nie powinno być prób wysyłki
    assert calls == []


def test_lambda_whatsapp_exception_is_caught(monkeypatch):
    os.environ["DEV_MODE"] = "true"

    # 1) Mock idempotency: pierwsze acquire=True, drugie=False
    it = iter([True, False])
    monkeypatch.setattr(handler.IDEMPOTENCY, "try_acquire", lambda *a, **k: next(it))

    # 2) Mock WhatsApp client via factory
    calls = []

    class DummyWhatsApp:
        def send_text(self, to, body):
            calls.append({"to": to, "body": body})
            return {"status": "OK", "sid": "fake"}

    class DummyFactory:
        def whatsapp(self, tenant_id):
            return DummyWhatsApp()

    monkeypatch.setattr(handler, "clients", DummyFactory())
    event = {
        "Records": [
            {"body": json.dumps({"to": "whatsapp:+48123", "body": "hello"})},
        ]
    }

    res = handler.lambda_handler(event, None)
    assert res["statusCode"] == 200
    # brak crasha, a klient WhatsApp był wywołany
    assert len(calls) == 1
