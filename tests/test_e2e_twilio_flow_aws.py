import pytest
import json

def _read_all(q_url, max_msgs=10):
    """
    Pomocniczo – czytamy wiadomości z kolejki (Moto SQS).
    WaitTimeSeconds=0, żeby test nie blokował.
    """
    import boto3

    sqs = boto3.client("sqs", region_name="eu-central-1")
    resp = sqs.receive_message(
        QueueUrl=q_url,
        MaxNumberOfMessages=max_msgs,
        WaitTimeSeconds=0,
    )
    return resp.get("Messages", [])


@pytest.mark.slow
def test_e2e_twilio_to_outbound_queue_aws(aws_stack, mock_ai):
    """
    E2E: Twilio → inbound_webhook → InboundEventsQueue → message_router → OutboundQueue.

    Wejście: przykładowy event Twilio z tests/events/inbound.json (body: "chcę się zapisać")
    Oczekujemy: w OutboundQueue pojawia się wiadomość z prośbą o potwierdzenie rezerwacji.
    """
    from src.lambdas.inbound_webhook import handler as inbound_lambda
    from src.lambdas.message_router import handler as router_lambda

    event = json.load(open("tests/events/inbound.json", "r", encoding="utf-8"))

    # 1) Twilio → webhook → inbound SQS
    res = inbound_lambda.lambda_handler(event, None)
    assert res["statusCode"] == 200

    inbound_msgs = _read_all(aws_stack["inbound"])
    assert inbound_msgs, "Brak wiadomości w kolejce inbound po webhooku"

    # 2) inbound SQS → router
    router_event = {"Records": [{"body": m["Body"]} for m in inbound_msgs]}
    router_lambda.lambda_handler(router_event, None)

    # 3) router → outbound SQS
    outbound_msgs = _read_all(aws_stack["outbound"])
    assert outbound_msgs, "Brak wiadomości w kolejce outbound po przejściu przez router"

    bodies = [json.loads(m["Body"]) for m in outbound_msgs]
    assert any(
        "potwierdzasz rezerwacj" in b.get("body", "").lower()
        for b in bodies
    )


def test_e2e_twilio_to_outbound_queue(monkeypatch, mock_ai):
    """
    Szybki E2E (logika): Twilio → inbound_webhook → message_router → outbound.

    - Bez Moto/LocalStack
    - Bez prawdziwego boto3 do SQS/Dynamo
    """

    # wczytujemy przykładowy event Twilio jak wcześniej
    event = json.load(open("tests/events/inbound.json", "r", encoding="utf-8"))

    # "kolejki" w pamięci
    inbound_msgs: list[dict] = []
    outbound_msgs: list[dict] = []

    # --- FAKE AWS: SQS -------------------------------------------------------

    class FakeSQS:
        def send_message(self, QueueUrl, MessageBody, **kwargs):
            # rozróżniamy kolejki po URL/fragmencie
            if "inbound" in QueueUrl:
                inbound_msgs.append({"Body": MessageBody})
            elif "outbound" in QueueUrl:
                outbound_msgs.append({"Body": MessageBody})
            return {"MessageId": "fake-msg"}

    fake_sqs = FakeSQS()

    def fake_sqs_client():
        # uwaga: handler wywołuje sqs_client() bez argumentów
        return fake_sqs

    # --- FAKE DDB (na wszelki wypadek, gdyby coś jeszcze chciało użyć ddb) ---

    class FakeTable:
        def update_item(self, *a, **k):
            return {"Attributes": {}}

        def get_item(self, *a, **k):
            return {}

        def put_item(self, *a, **k):
            return {}

        def scan(self, *a, **k):
            return {"Items": []}

        def delete_item(self, *a, **k):
            return {}

    class FakeDDBResource:
        def Table(self, name):
            return FakeTable()

    # --- FAKE SpamService – żadnych odwołań do DDB --------------------------

    class FakeSpamService:
        def __init__(self, *a, **k):
            pass

        def is_blocked(self, tenant_id, phone):
            return False

    # ustaw env-y na "fejkowe" URL-e kolejek
    monkeypatch.setenv("InboundEventsQueueUrl", "https://fake/local/inbound")
    monkeypatch.setenv("OutboundMessagesQueueUrl", "https://fake/local/outbound")
    monkeypatch.setenv("DEV_MODE", "true")

    # PATCH: ddb_resource używane przez serwisy (Tenants, Conversations, Spam itp.)
    monkeypatch.setattr(
        "src.common.aws.ddb_resource",
        lambda: FakeDDBResource(),
        raising=False,
    )
    
    monkeypatch.setattr(
        "src.storage.ddb.ddb_resource",
        lambda: FakeDDBResource(),
        raising=False,
    )
    
    monkeypatch.setattr(
        "src.storage.tenants_repo.ddb_resource",
        lambda: FakeDDBResource(),
        raising=False,
    )

    # najpierw importujemy moduły, żeby monkeypatch mógł je znaleźć
    from src.lambdas.inbound_webhook import handler as inbound_handler
    from src.lambdas.message_router import handler as router_handler

    # podmieniamy funkcje w samych handlerach
    monkeypatch.setattr(
        inbound_handler, "sqs_client", fake_sqs_client, raising=False
    )
    monkeypatch.setattr(
        router_handler, "sqs_client", fake_sqs_client, raising=False
    )

    # oraz globalny spam_service w inbound_webhook
    monkeypatch.setattr(
        inbound_handler, "spam_service", FakeSpamService(), raising=False
    )
       
    # --- 1) Twilio → inbound_webhook → inbound "queue" ----------------------

    res = inbound_handler.lambda_handler(event, None)
    assert res["statusCode"] == 200
    assert inbound_msgs, "Brak wiadomości 'na inbound queue' po webhooku"

    # --- 2) inbound "queue" → router → outbound "queue" ---------------------

    router_event = {"Records": [{"body": m["Body"]} for m in inbound_msgs]}
    router_handler.lambda_handler(router_event, None)

    assert outbound_msgs, "Brak wiadomości 'na outbound queue' po przejściu przez router"

    bodies = [json.loads(m["Body"]) for m in outbound_msgs]
    assert any(
        "potwierdzasz rezerwacj" in b.get("body", "").lower()
        for b in bodies
    )




