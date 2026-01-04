import os
import pytest
import json

def test_inbound_pushes_to_sqs_aws(aws_stack):
    from src.lambdas.inbound_webhook.handler import lambda_handler  # <- import dopiero tu

    os.environ["InboundEventsQueueUrl"] = aws_stack["inbound"]
    event = {
        "headers": {"Host": "localhost"},
        "requestContext": {"path": "/webhooks/twilio", "requestTimeEpoch": 0},
        "pathParameters": {"tenant": "default"},
        "body": "From=whatsapp%3A%2B48123123123&To=whatsapp%3A%2B48000000000&Body=godziny",
    }
    res = lambda_handler(event, None)
    assert res["statusCode"] == 200

def test_inbound_rate_limited_returns_429(aws_stack, monkeypatch):
    monkeypatch.setenv("InboundEventsQueueUrl", aws_stack["inbound"])
    monkeypatch.setenv("TWILIO_SKIP_SIGNATURE", "true")
    
    # erzatz SpamService, który zawsze blokuje
    class FakeSpam:
        def is_blocked(self, tenant_id, phone):
            return True

    monkeypatch.setattr(
        "src.lambdas.inbound_webhook.handler.spam_service",
        FakeSpam(),
        raising=False,
    )

    from src.lambdas.inbound_webhook.handler import lambda_handler

    event = {
        "headers": {"Host": "localhost"},
        "requestContext": {"path": "/webhooks/twilio", "requestTimeEpoch": 0},
        "pathParameters": {"tenant": "default"},
        "body": "From=whatsapp%3A%2B48123123123&To=whatsapp%3A%2B48000000000&Body=godziny",
    }

    res = lambda_handler(event, None)
    assert res["statusCode"] == 429


def test_inbound_pushes_to_sqs(monkeypatch):
    """
    Szybki test: sprawdzamy, że inbound_webhook:
    - zwraca 200
    - wywołuje send_message na SQS z jakimś body.

    Nie używamy Moto ani aws_stack – SQS i SpamService stubujemy w pamięci.
    """

    # 1) przygotuj "pudełko" na wysłane wiadomości
    sent_messages = []

    class FakeSQS:
        def send_message(self, QueueUrl, MessageBody, **kwargs):
            sent_messages.append({"QueueUrl": QueueUrl, "Body": MessageBody})
            return {"MessageId": "fake-1"}

    def fake_sqs_client():
        # inbound_webhook.handler wywołuje sqs_client(), więc zwracamy naszego fake'a
        return FakeSQS()

    # 2) stub SpamService, żeby nie dotykać DDB i żeby NIE blokował
    class FakeSpam:
        def is_blocked(self, tenant_id, phone):
            return False

    # 3) ustaw env dla URL kolejki (jeśli handler z niego korzysta)
    monkeypatch.setenv("InboundEventsQueueUrl", "https://example.com/fake-inbound-queue")
    
    # 4) podmień zależności w module handlera
    monkeypatch.setattr(
        "src.lambdas.inbound_webhook.handler.sqs_client",
        fake_sqs_client,
        raising=False,
    )
    monkeypatch.setattr(
        "src.lambdas.inbound_webhook.handler.spam_service",
        FakeSpam(),
        raising=False,
    )

    # 5) dopiero teraz importujemy handler – już po patchach/env
    from src.lambdas.inbound_webhook.handler import lambda_handler

    event = {
        "headers": {"Host": "localhost"},
        "requestContext": {"path": "/webhooks/twilio", "requestTimeEpoch": 0},
        "pathParameters": {"tenant": "default"},
        "body": "From=whatsapp%3A%2B48123123123&To=whatsapp%3A%2B48000000000&Body=godziny",
    }

    res = lambda_handler(event, None)
    assert res["statusCode"] == 200
    assert sent_messages, "Handler nie wysłał żadnej wiadomości na SQS"
