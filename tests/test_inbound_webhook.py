from src.lambdas.inbound_webhook.handler import lambda_handler

def test_inbound_pushes_to_sqs(aws_stack):
    event = {
        "headers": {"Host": "localhost"},
        "requestContext": {"path": "/webhooks/twilio", "requestTimeEpoch": 0},
        "body": "From=whatsapp%3A%2B48123123123&To=whatsapp%3A%2B48000000000&Body=godziny",
    }
    res = lambda_handler(event, None)
    assert res["statusCode"] == 200

def test_inbound_rate_limited_returns_429(aws_stack, monkeypatch):
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
        "body": "From=whatsapp%3A%2B48123123123&To=whatsapp%3A%2B48000000000&Body=godziny",
    }

    res = lambda_handler(event, None)
    assert res["statusCode"] == 429
