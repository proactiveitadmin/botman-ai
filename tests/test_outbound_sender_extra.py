import json

from src.lambdas.outbound_sender import handler


class DummyTwilio:
    def __init__(self, should_fail=False):
        self.calls = []
        self.should_fail = should_fail

    def send_text(self, to, body):
        self.calls.append({"to": to, "body": body})
        if self.should_fail:
            raise RuntimeError("Twilio error")
        return {"status": "OK", "sid": "sid-1"}


def test_lambda_no_records(monkeypatch):
    event = {}
    res = handler.lambda_handler(event, None)
    assert res["statusCode"] == 200
    assert res["body"] == "no-records"


def test_lambda_bad_json_is_skipped(monkeypatch):
    twilio = DummyTwilio()
    monkeypatch.setattr(handler, "twilio", twilio)

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
    assert len(twilio.calls) == 1
    assert twilio.calls[0]["to"] == "whatsapp:+48123"


def test_lambda_invalid_payload_missing_to(monkeypatch):
    twilio = DummyTwilio()
    monkeypatch.setattr(handler, "twilio", twilio)

    event = {
        "Records": [
            {"body": json.dumps({"body": "no recipient"})},  # brak 'to'
        ]
    }

    res = handler.lambda_handler(event, None)
    assert res["statusCode"] == 200
    # nie powinno być prób wysyłki
    assert twilio.calls == []


def test_lambda_twilio_exception_is_caught(monkeypatch):
    twilio = DummyTwilio(should_fail=True)
    monkeypatch.setattr(handler, "twilio", twilio)

    event = {
        "Records": [
            {"body": json.dumps({"to": "whatsapp:+48123", "body": "hello"})},
        ]
    }

    res = handler.lambda_handler(event, None)
    assert res["statusCode"] == 200
    # mimo wyjątku nie ma crasha, a Twilio było wywołane
    assert len(twilio.calls) == 1
