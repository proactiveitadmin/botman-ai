import json

from src.lambdas.message_router import handler


class DummyAction:
    def __init__(self, payload: dict):
        self.type = "reply"
        self.payload = payload


class DummyRouter:
    def __init__(self, actions):
        self.actions_to_return = actions
        self.calls = []

    def handle(self, msg):
        self.calls.append(msg)
        return self.actions_to_return


def test_message_router_no_records():
    result = handler.lambda_handler({}, None)
    assert result["statusCode"] == 200
    assert result["body"] == "no-records"


def test_message_router_faq_to_outbound(monkeypatch):
    """
    Sprawdzamy glue:
    - event SQS -> Message -> ROUTER.handle
    - reply trafia do sqs_client().send_message z właściwą kolejką/payloadem
    """

    actions = [
        DummyAction(
            {
                "to": "whatsapp:+48123123123",
                "body": "Klub jest otwarty w godzinach 6-23...",
                "tenant_id": "default",
            }
        )
    ]
    dummy_router = DummyRouter(actions)
    monkeypatch.setattr(handler, "ROUTER", dummy_router)

    sent_messages = []

    class DummySQS:
        def send_message(self, QueueUrl, MessageBody):
            sent_messages.append({"QueueUrl": QueueUrl, "MessageBody": MessageBody})

    # jeśli handler używa aws.sqs_client():
    if hasattr(handler, "aws"):
        monkeypatch.setattr(handler.aws, "sqs_client", lambda: DummySQS(), raising=False)
    # a gdyby importował funkcję lokalnie:
    monkeypatch.setattr(handler, "sqs_client", lambda: DummySQS(), raising=False)
    monkeypatch.setenv("OutboundQueueUrl", "dummy-outbound-url")

    event = {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "event_id": "evt-1",
                        "from": "whatsapp:+48123123123",
                        "to": "whatsapp:+48000000000",
                        "body": "Jakie są godziny otwarcia?",
                        "tenant_id": "default",
                        "channel": "whatsapp",
                    }
                )
            }
        ]
    }

    result = handler.lambda_handler(event, None)

    assert result["statusCode"] == 200
    assert len(dummy_router.calls) == 1
    assert len(sent_messages) == 1
    assert sent_messages[0]["QueueUrl"] == "dummy-outbound-url"

    payload = json.loads(sent_messages[0]["MessageBody"])
    assert payload["to"] == "whatsapp:+48123123123"
    assert "godzin" in payload["body"].lower() or "otwar" in payload["body"].lower()
