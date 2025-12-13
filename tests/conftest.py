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
        if "dostępne" in t or "zajęć" in t or "zajęcia" in t:
            return {
                "intent": "crm_available_classes",
                "confidence": 0.95,
                "slots": {},
            }
        return {"intent": "clarify", "confidence": 0.4, "slots": {}}

    # Patch na poziomie serwisu, a nie klienta OpenAI
    monkeypatch.setattr(
        "src.services.nlu_service.NLUService.classify_intent",
        fake_classify_intent,
        raising=False,
    )
    return fake_classify_intent

@pytest.fixture(autouse=True)
def disable_custom_aws_endpoints(monkeypatch):
    """
    W testach ignorujemy wszystkie custom endpointy AWS
    (LocalStack, DYNAMODB_ENDPOINT itp.), żeby nie próbował
    łączyć się z http://localhost:4566.
    """
    # 1) czyścimy env-y, które mogą wymuszać LocalStack
    for var in (
        "AWS_ENDPOINT_URL",
        "AWS_ENDPOINT_URL_DYNAMODB",
        "AWS_ENDPOINT_URL_SQS",
        "DYNAMODB_ENDPOINT",
        "SQS_ENDPOINT",
        "S3_ENDPOINT",
        "LOCALSTACK_HOST",
        "LOCALSTACK_HOSTNAME",
        "LOCALSTACK_ENDPOINT",
    ):
        monkeypatch.delenv(var, raising=False)

    # 2) a dodatkowo nadpisujemy helpera z src.common.aws
    def _no_endpoint(service: str) -> str | None:
        return None

    monkeypatch.setattr(
        "src.common.aws._endpoint_for",
        _no_endpoint,
        raising=False,
    )

    
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

    for var in [
        "AWS_ENDPOINT_URL",
        "LOCALSTACK_ENDPOINT",
        "SQS_ENDPOINT",
        "S3_ENDPOINT",
        "DYNAMODB_ENDPOINT",
    ]:
        monkeypatch.delenv(var, raising=False)
        
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
    monkeypatch.setenv("WebOutboundEventsQueueUrl", "http://localhost/queue/outbound")


# ============================
#  AWS STACK (Moto: SQS + DDB)
# ============================

def ensure_table(name, key_schema, attr_defs):
    ddb = boto3.client("dynamodb", region_name="eu-central-1")
    try:
        ddb.describe_table(TableName=name)
    except ddb.exceptions.ResourceNotFoundException:
        ddb.create_table(
            TableName=name,
            KeySchema=key_schema,
            AttributeDefinitions=attr_defs,
            BillingMode="PAY_PER_REQUEST",
        )
@pytest.fixture()
def aws_stack(monkeypatch):
    """
    Tworzy lokalny (Moto) stack: kolejki SQS + tabele DDB.
    Zabezpieczone przed ResourceInUseException (idempotentne).
    """
    with mock_aws():
        for name in [
            "AWS_ENDPOINT_URL",
            "LOCALSTACK_ENDPOINT",
            "LOCALSTACK_HOSTNAME",
            "SQS_ENDPOINT",
            "DYNAMODB_ENDPOINT",
        ]:
            monkeypatch.delenv(name, raising=False)

        sqs = boto3.client("sqs", region_name="eu-central-1")
        ddb = boto3.client("dynamodb", region_name="eu-central-1")
        print("TABLES:", ddb.list_tables()["TableNames"])

        inbound = sqs.create_queue(QueueName="inbound-events")
        outbound = sqs.create_queue(QueueName="outbound-messages")

        monkeypatch.setenv("InboundEventsQueueUrl", inbound["QueueUrl"])
        monkeypatch.setenv("OutboundQueueUrl", outbound["QueueUrl"])
        monkeypatch.setenv("WebOutboundEventsQueueUrl", outbound["QueueUrl"])

       # Messages
        ensure_table(
            "Messages",
            attr_defs=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            key_schema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
        )

        # Conversations
        ensure_table(
            "Conversations",
            attr_defs=[
                {"AttributeName": "pk", "AttributeType": "S"},
            ],
            key_schema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
            ],
        )

        # Campaigns
        ensure_table(
            "Campaigns",
            attr_defs=[
                {"AttributeName": "pk", "AttributeType": "S"},
            ],
            key_schema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
            ],
        )

        # IntentsStats – pod SpamService
        ensure_table(
            "IntentsStats",
            attr_defs=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            key_schema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
        )

        # Tenants – pod przyszłe repo Tenants / language per klub
        ensure_table(
            "Tenants",
            attr_defs=[
                {"AttributeName": "tenant_id", "AttributeType": "S"},
            ],
            key_schema=[
                {"AttributeName": "tenant_id", "KeyType": "HASH"},
            ],
        )

        # Templates – pod TemplateService z DDB
        ensure_table(
            "Templates",
            attr_defs=[
                {"AttributeName": "pk", "AttributeType": "S"},
            ],
            key_schema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
            ],
        )

        # Consents – pod ConsentService
        ensure_table(
            "Consents",
            attr_defs=[
                {"AttributeName": "pk", "AttributeType": "S"},
            ],
            key_schema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
            ],
        )

        # MembersIndex – pod MembersIndexRepo
        ensure_table(
            "MembersIndex",
            attr_defs=[
                {"AttributeName": "pk", "AttributeType": "S"},
            ],
            key_schema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
            ],
        )

        # SpamService – SpamService
        ensure_table(
            "SpamService",
            attr_defs=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            key_schema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
        )

        # na końcu, po ensure_table:
        from src.lambdas.message_router import handler as router_handler
        from src.services.routing_service import RoutingService
        from src.repos.messages_repo import MessagesRepo

        # świeży RoutingService działający na Moto
        router_handler.ROUTER = RoutingService()
        # świeży MessagesRepo, też na Moto
        router_handler.MESSAGES = MessagesRepo()
        
        # po inicjalizacji ROUTER – stubujemy detekcję języka,
        # żeby testy e2e nie wołały AWS Comprehend
        router_handler.ROUTER.language._detect_language = lambda text: "pl"

        yield {
            "inbound": inbound["QueueUrl"],
            "outbound": outbound["QueueUrl"],
        }
        
@pytest.fixture()
def requests_mock(monkeypatch):
    """
    Bardzo prosty substytut pluginu requests-mock,
    wystarczający do testu test_pg_available_classes_happy_path.
    """
    class _Response:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code

        def json(self):
            return self._payload

        def raise_for_status(self):
            if 400 <= self.status_code < 600:
                raise Exception(f"HTTP {self.status_code}")

    class _RequestsMock:
        def __init__(self):
            self._mappings = {}  # (method, url) -> (payload, status_code)

        def get(self, url, json=None, status_code=200, **kwargs):
            # API jak w pluginie: requests_mock.get(url, json=..., status_code=...)
            self._mappings[("GET", url)] = (json, status_code)

        def _fake_get(self, url, **kwargs):
            key = ("GET", url)
            if key not in self._mappings:
                raise AssertionError(f"Unexpected GET {url!r} in test_pg_available_classes")
            payload, status = self._mappings[key]
            return _Response(payload, status)

    mock = _RequestsMock()
    monkeypatch.setattr("requests.get", mock._fake_get)
    return mock
    
def wire_subservices(svc):
    """
    Przepiecie też svc.language i svc.crm_flow, inaczej testy lecą do DDB.
    """
    # language
    if getattr(svc, "language", None):
        svc.language.conv = getattr(svc, "conv", None)
        svc.language.tenants = getattr(svc, "tenants", None)

    # crm_flow
    if getattr(svc, "crm_flow", None):
        svc.crm_flow.conv = getattr(svc, "conv", None)
        svc.crm_flow.tpl = getattr(svc, "tpl", None)
        svc.crm_flow.crm = getattr(svc, "crm", None)
        svc.crm_flow.members_index = getattr(svc, "members_index", None)

    return svc