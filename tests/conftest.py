import pathlib
import pytest

import botocore.session

import src.common.http_client as http_client


# ----------------------------
#  Auto-mark tests by folder
# ----------------------------

def pytest_collection_modifyitems(config, items):
    for item in items:
        p = pathlib.Path(str(item.fspath)).as_posix()
        if "/tests/unit/" in p:
            item.add_marker(pytest.mark.unit)
        elif "/tests/component/" in p:
            item.add_marker(pytest.mark.component)
        elif "/tests/integration/" in p:
            item.add_marker(pytest.mark.integration)
        elif "/tests/e2e/" in p:
            item.add_marker(pytest.mark.e2e)
        elif "/tests/security/" in p:
            item.add_marker(pytest.mark.security)
        elif "/tests/perf/" in p:
            item.add_marker(pytest.mark.perf)


# ----------------------------
#  Global test safety: do not use custom AWS endpoints
# ----------------------------

@pytest.fixture(autouse=True)
def force_aws_no_endpoint_url(monkeypatch):
    """Prevent tests from forcing endpoint_url (e.g. LocalStack 4566).

    Works even if someone passes endpoint_url=... explicitly.
    """
    orig_create_client = botocore.session.Session.create_client

    def create_client_no_endpoint(self, service_name, *args, **kwargs):
        kwargs.pop("endpoint_url", None)
        return orig_create_client(self, service_name, *args, **kwargs)

    monkeypatch.setattr(
        botocore.session.Session,
        "create_client",
        create_client_no_endpoint,
        raising=True,
    )


@pytest.fixture(autouse=True)
def reset_http_session_singleton():
    http_client._SESSION = None


@pytest.fixture(autouse=True)
def disable_custom_aws_endpoints(monkeypatch):
    """Ignore all custom AWS endpoints in tests (LocalStack, *_ENDPOINT vars)."""
    for var in (
        "AWS_ENDPOINT_URL",
        "AWS_ENDPOINT_URL_DYNAMODB",
        "AWS_ENDPOINT_URL_SQS",
        "DYNAMODB_ENDPOINT",
        "SQS_ENDPOINT",
        "S3_ENDPOINT",
        "LOCALSTACK_URL",
        "LOCALSTACK_HOST",
        "LOCALSTACK_HOSTNAME",
        "LOCALSTACK_ENDPOINT",
    ):
        monkeypatch.delenv(var, raising=False)

    def _no_endpoint(service: str):
        return None

    monkeypatch.setattr("src.common.aws._endpoint_for", _no_endpoint, raising=False)


@pytest.fixture(autouse=True)
def force_boto3_without_endpoint_url(monkeypatch):
    import boto3

    _orig_client = boto3.client
    _orig_resource = boto3.resource

    def client(service_name, *args, **kwargs):
        kwargs.pop("endpoint_url", None)
        return _orig_client(service_name, *args, **kwargs)

    def resource(service_name, *args, **kwargs):
        kwargs.pop("endpoint_url", None)
        return _orig_resource(service_name, *args, **kwargs)

    monkeypatch.setattr(boto3, "client", client, raising=True)
    monkeypatch.setattr(boto3, "resource", resource, raising=True)


# ----------------------------
#  ENV setup (AWS + APP)
# ----------------------------

@pytest.fixture(autouse=True)
def env_setup(monkeypatch):
    # peppers used by security helpers
    monkeypatch.setenv("PHONE_HASH_PEPPER", "test-phone")
    monkeypatch.setenv("USER_HASH_PEPPER", "test-user")
    monkeypatch.setenv("OTP_HASH_PEPPER", "test-otp")

    # AWS fake env
    monkeypatch.setenv("AWS_REGION", "eu-central-1")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-central-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("MOTO_ALLOW_NONEXISTENT_REGION", "true")
    monkeypatch.delenv("AWS_PROFILE", raising=False)

    # disable requests session reuse to avoid cross-test leakage
    monkeypatch.setenv("HTTP_USE_SESSION", "0")

    # ensure tests never use real vendor secrets
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
    monkeypatch.setenv("DDB_TABLE_INTENTS_STATS", "IntentsStats")
    monkeypatch.setenv("DDB_TABLE_IDEMPOTENCY", "Idempotency")

    # default (overriden by aws_stack)
    monkeypatch.setenv("OutboundQueueUrl", "http://localhost/queue/outbound")
    monkeypatch.setenv("InboundEventsQueueUrl", "http://localhost/queue/inbound")
    monkeypatch.setenv("WebOutboundEventsQueueUrl", "http://localhost/queue/outbound")


# ----------------------------
#  Mock integrations (AI, Twilio, PG, Jira)
# ----------------------------

@pytest.fixture()
def mock_ai(monkeypatch):
    """Mock NLU classification so unit tests do not call OpenAI."""

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

    monkeypatch.setattr(
        "src.services.nlu_service.NLUService.classify_intent",
        fake_classify_intent,
        raising=False,
    )
    return fake_classify_intent


@pytest.fixture()
def mock_twilio(monkeypatch):
    """Backward-compatible fixture name.

    W kodzie outbound_sender wysyłka idzie przez ClientsFactory.whatsapp(...).
    """
    sent = []

    class FakeWhatsAppClient:
        def send_text(self, to: str, body: str):
            sent.append({"to": to, "body": body})
            return {"status": "OK", "sid": "fake-sid"}

    monkeypatch.setattr(
        "src.lambdas.outbound_sender.handler.clients.whatsapp",
        lambda tenant_id: FakeWhatsAppClient(),
        raising=False,
    )
    return sent


@pytest.fixture()
def mock_pg(monkeypatch):
    """Mock PerfectGymClient – rezerwacja zawsze OK."""

    class FakePG:
        def reserve_class(self, member_id: str, class_id: str, idempotency_key: str):
            return {"ok": True, "reservation_id": f"r-{class_id}"}

        def get_member(self, member_id: str):
            return {"member_id": member_id, "status": "Current", "balance": 0}

    monkeypatch.setattr(
        "src.services.routing_service.PerfectGymClient",
        lambda *a, **k: FakePG(),
        raising=False,
    )
    return FakePG()


@pytest.fixture()
def mock_jira(monkeypatch):
    """Mock JiraClient – udaje utworzenie ticketa."""

    class FakeJira:
        def create_ticket(self, summary: str, description: str, tenant_id: str):
            return {"ok": True, "ticket": "JIRA-TEST-1"}

    monkeypatch.setattr(
        "src.adapters.jira_client.JiraClient",
        lambda *a, **k: FakeJira(),
        raising=False,
    )
    return FakeJira()


# ----------------------------
#  AWS stack (Moto: SQS + DDB)
# ----------------------------

def ensure_table(ddb, name, key_schema, attr_defs):
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
    """Creates a local Moto stack: SQS queues + DDB tables."""
    from moto import mock_aws
    import boto3

    with mock_aws():
        sqs = boto3.client("sqs", region_name="eu-central-1")
        ddb = boto3.client("dynamodb", region_name="eu-central-1")

        inbound = sqs.create_queue(
            QueueName="inbound-events.fifo",
            Attributes={"FifoQueue": "true", "ContentBasedDeduplication": "true"},
        )
        outbound = sqs.create_queue(QueueName="outbound-messages")

        monkeypatch.setenv("InboundEventsQueueUrl", inbound["QueueUrl"])
        monkeypatch.setenv("OutboundQueueUrl", outbound["QueueUrl"])
        monkeypatch.setenv("WebOutboundEventsQueueUrl", outbound["QueueUrl"])

        # Tables used by tests
        ensure_table(
            ddb,
            "Messages",
            key_schema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            attr_defs=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
        )

        ensure_table(
            ddb,
            "Conversations",
            key_schema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            attr_defs=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
        )

        ensure_table(
            ddb,
            "Campaigns",
            key_schema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            attr_defs=[{"AttributeName": "pk", "AttributeType": "S"}],
        )

        ensure_table(
            ddb,
            "IntentsStats",
            key_schema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            attr_defs=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
        )

        ensure_table(
            ddb,
            "Idempotency",
            key_schema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            attr_defs=[{"AttributeName": "pk", "AttributeType": "S"}],
        )

        ensure_table(
            ddb,
            "Tenants",
            key_schema=[{"AttributeName": "tenant_id", "KeyType": "HASH"}],
            attr_defs=[{"AttributeName": "tenant_id", "AttributeType": "S"}],
        )

        try:
            ddb.put_item(
                TableName="Tenants",
                Item={"tenant_id": {"S": "default"}, "language_code": {"S": "pl"}},
            )
        except Exception:
            pass

        ensure_table(
            ddb,
            "Templates",
            key_schema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            attr_defs=[{"AttributeName": "pk", "AttributeType": "S"}],
        )

        ensure_table(
            ddb,
            "Consents",
            key_schema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            attr_defs=[{"AttributeName": "pk", "AttributeType": "S"}],
        )

        ensure_table(
            ddb,
            "MembersIndex",
            key_schema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            attr_defs=[{"AttributeName": "pk", "AttributeType": "S"}],
        )

        # Reset singletons in handlers to Moto-backed repos
        from src.lambdas.message_router import handler as router_handler
        from src.services.routing_service import RoutingService
        from src.repos.messages_repo import MessagesRepo

        router_handler.ROUTER = RoutingService()
        router_handler.MESSAGES = MessagesRepo()
        router_handler.ROUTER.language._detect_language = lambda text: "pl"

        yield {"inbound": inbound["QueueUrl"], "outbound": outbound["QueueUrl"]}


# ----------------------------
#  Small helper used by one test (replacement for requests-mock)
# ----------------------------

@pytest.fixture()
def requests_mock(monkeypatch):
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
            self._mappings[("GET", url)] = (json, status_code)

        def _fake_get(self, url, **kwargs):
            key = ("GET", url)
            if key not in self._mappings:
                raise AssertionError(f"Unexpected GET {url!r} in requests_mock fixture")
            payload, status = self._mappings[key]
            return _Response(payload, status)

        def _fake_request(self, method, url, **kwargs):
            m = (method or "").upper()
            if m == "GET":
                return self._fake_get(url, **kwargs)
            raise AssertionError(f"Unexpected {m} {url!r} in requests_mock fixture")

    return _RequestsMock()


def wire_subservices(svc):
    """Utility used by some tests to rewire internal sub-services to fakes."""
    if getattr(svc, "language", None):
        svc.language.conv = getattr(svc, "conv", None)
        svc.language.tenants = getattr(svc, "tenants", None)

    if getattr(svc, "crm_flow", None):
        svc.crm_flow.conv = getattr(svc, "conv", None)
        svc.crm_flow.tpl = getattr(svc, "tpl", None)
        svc.crm_flow.crm = getattr(svc, "crm", None)
        svc.crm_flow.members_index = getattr(svc, "members_index", None)

    return svc


@pytest.fixture(autouse=True)
def _dev_and_idempotency(monkeypatch):
    """Ensure handler modules use test IdempotencyRepo."""
    monkeypatch.setenv("DEV_MODE", "true")

    from src.lambdas.message_router import handler as router_handler
    from src.lambdas.outbound_sender import handler as outbound_handler
    from src.repos.idempotency_repo import IdempotencyRepo

    monkeypatch.setattr(router_handler, "IDEMPOTENCY", IdempotencyRepo(table_name_env=""), raising=False)
    monkeypatch.setattr(outbound_handler, "IDEMPOTENCY", IdempotencyRepo(table_name_env=""), raising=False)
    yield
