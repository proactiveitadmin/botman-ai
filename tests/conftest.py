import os
import pytest
from moto import mock_aws
import boto3

# ============================
#  MOCKI INTEGRACJI (AI, Twilio, PG, Jira)
# ============================

@pytest.fixture()
def mock_ai(monkeypatch):
    """
    Mock AI – zamiast OpenAI:
    - 'godzin' / 'otwar' -> faq(hours)
    - 'zapis' / 'rezerw'  -> reserve_class
    - inne -> clarify
    Patchujemy NLUService.classify_intent, więc nie obchodzi nas kolejność importów.
    """
    def fake_classify_intent(self, text: str, lang: str = "pl"):
        t = (text or "").lower()
        if "godzin" in t or "otwar" in t:
            return {"intent": "faq", "confidence": 0.95, "slots": {"topic": "hours"}}
        if "zapis" in t or "rezerw" in t:
            return {
                "intent": "reserve_class",
                "confidence": 0.96,
                "slots": {"class_id": "777", "member_id": "105"},
            }
        return {"intent": "clarify", "confidence": 0.4, "slots": {}}

    # Patch na poziomie serwisu, a nie klienta OpenAI
    monkeypatch.setattr(
        "src.services.nlu_service.NLUService.classify_intent",
        fake_classify_intent,
        raising=False,
    )
    return fake_classify_intent


@pytest.fixture()
def mock_twilio(monkeypatch):
    """
    Mock TwilioClient używany w outbound_sender.handler:
    - patchujemy modułową zmienną `twilio`,
      więc nie ma znaczenia, kiedy moduł został zaimportowany.
    """
    sent = []

    class FakeTwilioClient:
        def send_text(self, to: str, body: str):
            sent.append({"to": to, "body": body})
            # symulujemy sukces
            return {"status": "OK", "sid": "fake-sid"}

    # kluczowy patch: nadpisujemy instancję twilio w handlerze
    monkeypatch.setattr(
        "src.lambdas.outbound_sender.handler.twilio",
        FakeTwilioClient(),
        raising=False,
    )
    return sent



@pytest.fixture()
def mock_pg(monkeypatch):
    """
    Mock PerfectGymClient – rezerwacja zawsze OK.
    """
    class FakePG:
        def reserve_class(self, member_id: str, class_id: str, idempotency_key: str):
            return {"ok": True, "reservation_id": f"r-{class_id}"}

        def get_member(self, member_id: str):
            return {"member_id": member_id, "status": "Current", "balance": 0}

    # patchujemy PerfectGymClient w module routing_service
    monkeypatch.setattr(
        "src.services.routing_service.PerfectGymClient",
        lambda *a, **k: FakePG(),
        raising=False,
    )
    return FakePG()


@pytest.fixture()
def mock_jira(monkeypatch):
    """
    Mock JiraClient – udaje utworzenie ticketa.
    """
    class FakeJira:
        def create_ticket(self, summary: str, description: str, tenant_id: str):
            return {"ok": True, "ticket": "JIRA-TEST-1"}

    monkeypatch.setattr(
        "src.adapters.jira_client.JiraClient",
        lambda *a, **k: FakeJira(),
        raising=False,
    )
    return FakeJira()


# ============================
#  USTAWIENIA ENV (AWS + APP)
# ============================

@pytest.fixture(autouse=True)
def env_setup(monkeypatch):
    # AWS fake env
    monkeypatch.setenv("AWS_REGION", "eu-central-1")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-central-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("MOTO_ALLOW_NONEXISTENT_REGION", "true")
    monkeypatch.delenv("AWS_PROFILE", raising=False)

    # Zadbajmy, żeby w testach NIGDY nie poszło do prawdziwego OpenAI/Twilio/PG/Jira
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("PG_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_URL", raising=False)

    # App env
    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.setenv("DDB_TABLE_MESSAGES", "Messages")
    monkeypatch.setenv("DDB_TABLE_CONVERSATIONS", "Conversations")
    monkeypatch.setenv("DDB_TABLE_CAMPAIGNS", "Campaigns")
    monkeypatch.setenv("DDB_TABLE_INTENTS_STATS", "IntentsStats")  # DODANE
    
    # domyślne "lokalne" URL-e kolejek – nadpiszemy w aws_stack
    monkeypatch.setenv("OutboundQueueUrl", "http://localhost/queue/outbound")
    monkeypatch.setenv("InboundEventsQueueUrl", "http://localhost/queue/inbound")


# ============================
#  AWS STACK (Moto: SQS + DDB)
# ============================

@pytest.fixture()
def aws_stack(monkeypatch):
    """
    Tworzy lokalny (Moto) stack: kolejki SQS + tabele DDB.
    Zabezpieczone przed ResourceInUseException (idempotentne).
    """
    with mock_aws():
        sqs = boto3.client("sqs", region_name="eu-central-1")
        ddb = boto3.client("dynamodb", region_name="eu-central-1")

        inbound = sqs.create_queue(QueueName="inbound-events")
        outbound = sqs.create_queue(QueueName="outbound-messages")

        monkeypatch.setenv("InboundEventsQueueUrl", inbound["QueueUrl"])
        monkeypatch.setenv("OutboundQueueUrl", outbound["QueueUrl"])

        def ensure_table(name, attrs, keys):
            try:
                ddb.create_table(
                    TableName=name,
                    BillingMode="PAY_PER_REQUEST",
                    AttributeDefinitions=attrs,
                    KeySchema=keys,
                )
            except ddb.exceptions.ResourceInUseException:
                # tabela już istnieje – ignorujemy
                pass

        # Messages
        ensure_table(
            "Messages",
            [
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            [
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
        )

        # Conversations
        ensure_table(
            "Conversations",
            [{"AttributeName": "pk", "AttributeType": "S"}],
            [{"AttributeName": "pk", "KeyType": "HASH"}],
        )

        # Campaigns
        ensure_table(
            "Campaigns",
            [{"AttributeName": "pk", "AttributeType": "S"}],
            [{"AttributeName": "pk", "KeyType": "HASH"}],
        )

        # IntentsStats – pod SpamService
        ensure_table(
            "IntentsStats",
            [
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            [
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
        )
        # Tenants – pod przyszłe repo Tenants / language per klub
        ensure_table(
            "Tenants",
            [{"AttributeName": "tenant_id", "AttributeType": "S"}],
            [{"AttributeName": "tenant_id", "KeyType": "HASH"}],
        )

        # Templates – pod TemplateService z DDB
        ensure_table(
            "Templates",
            [{"AttributeName": "pk", "AttributeType": "S"}],
            [{"AttributeName": "pk", "KeyType": "HASH"}],
        )

        # Consents – pod ConsentService (na razie stub, ale niech będzie)
        ensure_table(
            "Consents",
            [{"AttributeName": "pk", "AttributeType": "S"}],
            [{"AttributeName": "pk", "KeyType": "HASH"}],
        )
        
        # MembersIndex – pod MembersIndexRepo
        ensure_table(
            "MembersIndex",
            [{"AttributeName": "pk", "AttributeType": "S"}],
            [{"AttributeName": "pk", "KeyType": "HASH"}],
        )

        yield {
            "inbound": inbound["QueueUrl"],
            "outbound": outbound["QueueUrl"],
        }
