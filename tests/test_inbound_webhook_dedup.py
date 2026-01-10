import json
import urllib.parse

from src.lambdas.inbound_webhook import handler


def test_inbound_webhook_sets_fifo_dedup_id_to_twilio_message_sid(monkeypatch):
    sent = {}

    class DummySQS:
        def send_message(self, **kwargs):
            sent.update(kwargs)
            return {"MessageId": "m-1"}

    # --- stuby zależności ---
    monkeypatch.setattr(handler, "resolve_queue_url", lambda name: "https://sqs.local/inbound.fifo")
    monkeypatch.setattr(handler, "sqs_client", lambda: DummySQS())

    # tenant resolution (po To)
    monkeypatch.setattr(
        handler.tenants_repo,
        "find_by_twilio_to",
        lambda to_number: {"tenant_id": "t1"},
    )

    # tenant cfg (token per tenant) – nieistotne, bo signature i tak stubujemy na True
    monkeypatch.setattr(handler.tenant_cfg, "get", lambda tenant_id: {"twilio": {"auth_token": "tok"}})

    # signature always OK
    monkeypatch.setattr(handler, "verify_twilio_signature", lambda *args, **kwargs: True)

    # spam not blocked
    monkeypatch.setattr(handler.spam_service, "is_blocked", lambda **kwargs: False)

    # deterministic hmac + ids
    monkeypatch.setattr(handler, "user_hmac", lambda tenant_id, channel, channel_user_id: "UID123")
    monkeypatch.setattr(handler, "new_id", lambda prefix="": f"{prefix}X")

    # --- event (form-urlencoded jak Twilio) ---
    params = {
        "From": "whatsapp:+48123456789",
        "To": "whatsapp:+48000111222",
        "Body": "hej",
        "MessageSid": "SM123456",
    }
    body = urllib.parse.urlencode(params)

    event = {
        "body": body,
        "isBase64Encoded": False,
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": "example.com",
            "X-Forwarded-Proto": "https",
            "X-Twilio-Signature": "dummy",
        },
        "requestContext": {"path": "/webhooks/twilio", "requestTimeEpoch": 1234567890},
        "path": "/webhooks/twilio",
    }

    res = handler.lambda_handler(event, None)
    assert res["statusCode"] == 200

    # --- asercje SQS ---
    assert sent["QueueUrl"] == "https://sqs.local/inbound.fifo"

    msg = json.loads(sent["MessageBody"])
    assert msg["tenant_id"] == "t1"
    assert msg["message_sid"] == "SM123456"

    # FIFO: per conversation ordering
    assert sent["MessageGroupId"] == "conv#whatsapp#UID123"

    # FIFO: dedup po MessageSid
    assert sent["MessageDeduplicationId"] == "SM123456"


def test_inbound_webhook_dedup_falls_back_when_message_sid_missing(monkeypatch):
    sent = {}

    class DummySQS:
        def send_message(self, **kwargs):
            sent.update(kwargs)
            return {"MessageId": "m-2"}

    monkeypatch.setattr(handler, "resolve_queue_url", lambda name: "https://sqs.local/inbound.fifo")
    monkeypatch.setattr(handler, "sqs_client", lambda: DummySQS())
    monkeypatch.setattr(handler.tenants_repo, "find_by_twilio_to", lambda to_number: {"tenant_id": "t1"})
    monkeypatch.setattr(handler.tenant_cfg, "get", lambda tenant_id: {"twilio": {"auth_token": "tok"}})
    monkeypatch.setattr(handler, "verify_twilio_signature", lambda *args, **kwargs: True)
    monkeypatch.setattr(handler.spam_service, "is_blocked", lambda **kwargs: False)
    monkeypatch.setattr(handler, "user_hmac", lambda tenant_id, channel, channel_user_id: "UID123")

    # new_id w handlerze tworzy event_id; użyjemy deterministycznie
    monkeypatch.setattr(handler, "new_id", lambda prefix="": f"{prefix}EVT1" if prefix.startswith("evt-") else f"{prefix}X")

    params = {
        "From": "whatsapp:+48123456789",
        "To": "whatsapp:+48000111222",
        "Body": "hej",
        # brak MessageSid
    }
    body = urllib.parse.urlencode(params)

    event = {
        "body": body,
        "isBase64Encoded": False,
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": "example.com",
            "X-Forwarded-Proto": "https",
            "X-Twilio-Signature": "dummy",
        },
        "requestContext": {"path": "/webhooks/twilio", "requestTimeEpoch": 1234567890},
        "path": "/webhooks/twilio",
    }

    res = handler.lambda_handler(event, None)
    assert res["statusCode"] == 200

    # fallback na event_id
    assert sent["MessageDeduplicationId"] == "evt-EVT1"
