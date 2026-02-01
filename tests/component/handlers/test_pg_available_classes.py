from src.domain.models import Message
from src.adapters.perfectgym_client import PerfectGymClient
from src.services.crm_service import CRMService
from src.services.language_service import LanguageService
from src.services.routing_service import RoutingService

from tests.helpers.fakes_routing import InMemoryConversations, FakeTenantsRepo, FakeTemplateServicePG


def test_crm_available_classes_happy_path(requests_mock, mock_ai, monkeypatch):
    # 1) Ustaw bazowy URL PerfectGym 
    client = PerfectGymClient()
    monkeypatch.setattr(client, "base_url", "https://example.perfectgym.com")

    # 2) Mock dokładnie tego URL, który wywołuje PerfectGymClient
    url = client.base_url.rstrip("/") + "/Classes"
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


    requests_mock.get(url, json=mock_payload, status_code=200)

    # 3) In-memory ConversationsRepo – bez DynamoDB
    conv = InMemoryConversations()

    # 4) Fake TenantsRepo – żeby LanguageService miało fallback bez DynamoDB
    tenants = FakeTenantsRepo(lang="en")

    # 5) Fake TemplateService – renderuje listę zajęć
    tpl = FakeTemplateServicePG()

    # 6) CRMService używa PerfectGymClient -> requests_mock przechwyci requests.get
    crm = CRMService(client=client)

    # 7) LanguageService z tenants (żeby nie iść do prawdziwego TenantsRepo)
    language = LanguageService(conv=conv, tenants=tenants)

    router = RoutingService(conv=conv, tenants=tenants, tpl=tpl, crm=crm, language=language)

    # stub detekcji języka (unikamy AWS Comprehend)
    monkeypatch.setattr(router.language, "_detect_language", lambda text: "pl")

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

    # sprawdzamy, że stan i pending są ustawione
    pk = "pending#" + msg.from_phone
    pending_item = conv.pending.get(pk)
    assert pending_item is not None
    assert pending_item["sk"] == "classes"

    key = conv.conversation_pk(msg.tenant_id, msg.channel, msg.channel_user_id)
    stored_conv = conv.data[key]
    assert stored_conv["state_machine_status"] == "awaiting_class_selection"
