from src.domain.models import Message
from src.adapters.perfectgym_client import PerfectGymClient
from src.services.crm_service import CRMService
from src.services.language_service import LanguageService
from src.services.routing_service import RoutingService

from tests.helpers.fakes_routing import InMemoryConversations, FakeTenantsRepo, FakeTemplateServicePG


class DummyResp:
    def __init__(self, status_code=200, payload=None, text="OK", headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class DummySession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.response


def test_crm_available_classes_happy_path(mock_ai, monkeypatch):
    client = PerfectGymClient()
    monkeypatch.setattr(client, "base_url", "https://example.perfectgym.com", raising=False)

    mock_payload = {
        "value": [
            {
                "id": "CLASS-1",
                "startDate": "2025-11-23T10:00:00+01:00",
                "attendeesCount": 3,
                "attendeesLimit": 10,
                "classType": {"name": "Zumba"},
            }
        ]
    }
    session = DummySession(DummyResp(payload=mock_payload))
    monkeypatch.setattr(client, "_session", lambda: session)

    conv = InMemoryConversations()
    tenants = FakeTenantsRepo(lang="en")
    tpl = FakeTemplateServicePG()
    crm = CRMService(client=client)
    language = LanguageService(conv=conv, tenants=tenants)
    router = RoutingService(conv=conv, tenants=tenants, tpl=tpl, crm=crm, language=language)

    # stub detekcji języka (unikamy AWS Comprehend)
    monkeypatch.setattr(router.language, "_detect_language", lambda text: "pl")
    monkeypatch.setattr(router.crm_flow, "is_crm_member", lambda tenant_id, phone: True)

    msg = Message(
        tenant_id="tenantA",
        from_phone="whatsapp:+48123123123",
        to_phone="whatsapp:+48000000000",
        body="jakie są dostępne zajęcia?",
        channel="whatsapp",
        channel_user_id="whatsapp:+48123123123",
    )
    actions = router.handle(msg)

    assert len(actions) == 1
    assert actions[0].type == "reply"
    assert "Zumba" in actions[0].payload["body"]

    assert session.calls
    assert session.calls[0]["method"] == "GET"
    assert session.calls[0]["url"] == client.base_url.rstrip("/") + "/Classes"

    # sprawdzamy, że stan i pending są ustawione
    pk = "pending#" + msg.from_phone
    pending_item = conv.pending.get(pk)
    assert pending_item is not None
    assert pending_item["sk"] == "classes"

    key = conv.conversation_pk(msg.tenant_id, msg.channel, msg.channel_user_id)
    stored_conv = conv.data[key]
    assert stored_conv["state_machine_status"] == "awaiting_class_selection"
