import json
import os

from src.lambdas.outbound_sender import handler as outbound_handler

def _sqs_event(messages):
    return {"Records": [{"messageId": f"m{i}", "body": json.dumps(m)} for i, m in enumerate(messages)]}

def test_outbound_sender_idempotency_skips_duplicates(monkeypatch, aws_stack):
    os.environ["DEV_MODE"] = "true"

    # 1) Mock idempotency: pierwsze acquire=True, drugie=False
    it = iter([True, False])
    monkeypatch.setattr(outbound_handler.IDEMPOTENCY, "try_acquire", lambda *a, **k: next(it))

    # 2) Mock WhatsApp via factory
    calls = []

    class DummyWhatsApp:
        def send_text(self, to, body):
            calls.append({"to": to, "body": body})
            return {"status": "OK", "sid": "fake"}

    class DummyFactory:
        def whatsapp(self, tenant_id):
            return DummyWhatsApp()

    monkeypatch.setattr(outbound_handler, "clients", DummyFactory())

    # same idempotency_key twice -> only one send call
    msg = {
        "tenant_id": "t1",
        "to": "whatsapp:+48123456789",
        "body": "hi",
        "channel": "whatsapp",
        "idempotency_key": "k-1",
    }
    event = _sqs_event([msg, msg])
    res = outbound_handler.lambda_handler(event, None)

    assert len(calls) == 1
    assert res.get("batchItemFailures") in (None, [])
    os.environ.pop("DEV_MODE", None)
