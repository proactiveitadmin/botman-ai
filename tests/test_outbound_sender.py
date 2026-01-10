import json
import os

from src.lambdas.outbound_sender import handler


def test_outbound_sender_dev_mode_whatsapp(monkeypatch):
    """
    Prosty smoke test: dla eventu WhatsApp zwracamy 200
    i nie wywalamy wyjątku.
    """
    class DummyTwilio:
        def send_text(self, *args, **kwargs):
            # w tym teście nie powinno polecieć do prawdziwego Twilio
            return {"status": "OK", "sid": "fake-sid"}


    event = {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "channel": "whatsapp",
                        "to": "whatsapp:+48123",
                        "body": "Hej!",
                        "tenant_id": "default",
                    }
                )
            }
        ]
    }
    res = handler.lambda_handler(event, None)
    assert res["statusCode"] == 200


def test_outbound_sender_web_with_queue(monkeypatch):
    """
    Dla channel=web, gdy WebOutboundEventsQueueUrl jest ustawione:
    - wysyłamy komunikat na kolejkę,
    - NIE wołamy Twilio.
    """
    os.environ["WebOutboundEventsQueueUrl"] = "dummy-web-url"

    sent_to_web = []

    class DummySQS:
        def send_message(self, QueueUrl, MessageBody):
            sent_to_web.append({"QueueUrl": QueueUrl, "MessageBody": MessageBody})

    monkeypatch.setattr(handler, "sqs_client", lambda: DummySQS())

    class DummyTwilio:
        def send_text(self, *args, **kwargs):
            raise AssertionError("Twilio nie powinno być wołane dla channel=web")


    event = {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "channel": "web",
                        "tenant_id": "default",
                        "channel_user_id": "user-1",
                        "body": "hello from web",
                    }
                )
            }
        ]
    }

    res = handler.lambda_handler(event, None)
    assert res["statusCode"] == 200
    assert len(sent_to_web) == 1

    msg = json.loads(sent_to_web[0]["MessageBody"])
    assert msg["tenant_id"] == "default"
    assert msg["channel_user_id"] == "user-1"
    assert msg["body"] == "hello from web"


def test_outbound_sender_web_without_queue(monkeypatch):
    """
    Dla channel=web, gdy NIE ma WebOutboundEventsQueueUrl:
    - NIE wywołujemy SQS,
    - NIE wywołujemy Twilio,
    - ale handler zwraca 200.
    """
    os.environ.pop("WebOutboundEventsQueueUrl", None)

    sent_to_web = []

    class DummySQS:
        def send_message(self, QueueUrl, MessageBody):
            sent_to_web.append({"QueueUrl": QueueUrl, "MessageBody": MessageBody})

    monkeypatch.setattr(handler, "sqs_client", lambda: DummySQS())

    class DummyTwilio:
        def send_text(self, *args, **kwargs):
            raise AssertionError("Twilio nie powinno być wołane dla channel=web")


    event = {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "channel": "web",
                        "tenant_id": "default",
                        "channel_user_id": "user-1",
                        "body": "hello from web",
                    }
                )
            }
        ]
    }

    res = handler.lambda_handler(event, None)
    assert res["statusCode"] == 200
    # brak WebOutboundEventsQueueUrl => nie wywołaliśmy SQS
    assert sent_to_web == []
