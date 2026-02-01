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

    class DummyTable:
        def get_item(self, **kwargs):
            return {}  # brak duplikatu eventu

        def put_item(self, **kwargs):
            pass  # ignorujemy logowanie

    class DummyMessages:
        table = DummyTable()

    monkeypatch.setattr(handler, "MESSAGES", DummyMessages(), raising=False)

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
    

def test_message_router_generates_unique_idempotency_key_per_reply(monkeypatch):
    """
    W ramach jednego inbound eventu router może zwrócić kilka reply.
    Każdy reply musi dostać unikalny idempotency_key, bo outbound_sender
    deduplikuje po tym kluczu.
    """

    actions = [
        DummyAction({"to": "whatsapp:+481", "body": "Zweryfikowaliśmy Twoje konto.", "tenant_id": "default"}),
        DummyAction({"to": "whatsapp:+481", "body": "Czy potwierdzasz rezerwację?", "tenant_id": "default"}),
    ]
    dummy_router = DummyRouter(actions)
    monkeypatch.setattr(handler, "ROUTER", dummy_router)

    sent_messages = []

    class DummySQS:
        def send_message(self, QueueUrl, MessageBody):
            sent_messages.append({"QueueUrl": QueueUrl, "MessageBody": MessageBody})

    monkeypatch.setattr(handler, "sqs_client", lambda: DummySQS(), raising=False)
    monkeypatch.setenv("OutboundQueueUrl", "dummy-outbound-url")

    class DummyTable:
        def get_item(self, **kwargs):
            return {}

        def put_item(self, **kwargs):
            pass

    class DummyMessages:
        table = DummyTable()

        @staticmethod
        def log_message(**kwargs):
            pass

    monkeypatch.setattr(handler, "MESSAGES", DummyMessages(), raising=False)

    event = {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "event_id": "evt-otp-1",
                        "message_sid": "SM123",
                        "from": "whatsapp:+481",
                        "to": "whatsapp:+480",
                        "body": "T4KP7F",
                        "tenant_id": "default",
                        "channel": "whatsapp",
                    }
                )
            }
        ]
    }

    res = handler.lambda_handler(event, None)
    assert res["statusCode"] == 200
    assert len(sent_messages) == 2

    p1 = json.loads(sent_messages[0]["MessageBody"])
    p2 = json.loads(sent_messages[1]["MessageBody"])
    assert p1["idempotency_key"] != p2["idempotency_key"]
    assert p1["idempotency_key"].startswith("out#")
    assert p2["idempotency_key"].startswith("out#")