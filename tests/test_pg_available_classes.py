import json
from src.services.routing_service import RoutingService
from src.domain.models import Message
from src.common.config import settings

def test_pg_available_classes_happy_path(requests_mock, mock_ai, monkeypatch):
    # 1) Ustaw bazowy URL PerfectGym w settings
    monkeypatch.setattr(settings, "pg_base_url", "https://example.perfectgym.com")

    # 2) Mock dokładnie tego URL, który wywołuje PerfectGymClient
    url = settings.pg_base_url.rstrip("/") + "/Classes"
    mock_payload = {
        "value": [
            {
                "startDate": "2025-11-23T10:00:00+01:00",
                "attendeesCount": 3,
                "attendeesLimit": 10,
                "classType": {"name": "Zumba"},
            }
        ]
    }
    requests_mock.get(url, json=mock_payload, status_code=200)

    # 3) In-memory ConversationsRepo – bez DynamoDB
    class InMemoryConversations:
        def __init__(self):
            self.data = {}
            self.pending = {}

        def conversation_pk(self, tenant_id, channel, channel_user_id):
            return (tenant_id, channel, channel_user_id)

        def get_conversation(self, tenant_id, channel, channel_user_id):
            return self.data.get(
                self.conversation_pk(tenant_id, channel, channel_user_id)
            )

        def upsert_conversation(self, tenant_id, channel, channel_user_id, **attrs):
            key = self.conversation_pk(tenant_id, channel, channel_user_id)
            self.data.setdefault(key, {}).update(attrs)

        # używane w handle() przy pending rezerwacji
        def _pending_key(self, phone):
            return f"pending#{phone}"

        def get(self, key, sk):
            return self.pending.get(key)

        def put(self, item: dict):
            key = item.get("pk")
            if key:
                self.pending[key] = item

        def delete(self, key):
            self.pending.pop(key, None)

        def set_language(self, tenant_id, phone, new_lang):
            return None

        def find_by_verification_code(self, tenant_id, verification_code):
            return None

    # 4) Fake TenantsRepo, żeby TemplateService NIE wołał DynamoDB po tenant
    class FakeTenantsRepo:
        def __init__(self, lang="pl"):
            self.lang = lang

        def get(self, tenant_id):
            return {"tenant_id": tenant_id, "language_code": self.lang}

    # 5) Fake TemplateService – przejmuje renderowanie pg_available_classes
    class FakeTemplateService:
        def __init__(self, tenants):
            self.tenants = tenants

        def render_named(self, tenant_id, template_code, language_code, ctx):
            # 1) pojedyncza linia dla jednej klasy
            if template_code == "pg_available_classes_item":
                name = ctx.get("name", "Zajęcia")
                date = ctx.get("date", "?")
                time = ctx.get("time", "?")
                capacity = ctx.get("capacity", "")
                # prosta reprezentacja, testowi wystarczy
                return f"{name} {date} {time} {capacity}"

            # 2) “nagłówek” + już zrenderowany blok klas jako string
            if template_code == "pg_available_classes":
                classes_block = ctx.get("classes", "")
                if not classes_block:
                    return "Brak dostępnych zajęć."

                if language_code == "pl":
                    return "Dostępne zajęcia:\n" + classes_block
                return "Available classes:\n" + classes_block

            # fallback dla innych szablonów
            return template_code



    router = RoutingService()
    router.conv = InMemoryConversations()
    router.tenants = FakeTenantsRepo(lang="en")
    router.tpl = FakeTemplateService(router.tenants)   # <-- KLUCZOWA LINIA

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
    
    #sprawdzamy, że stan i pending są ustawione
    pk = "pending#" + msg.from_phone
    pending_item = router.conv.pending.get(pk)
    assert pending_item is not None
    assert pending_item["sk"] == "classes"

    key = router.conv.conversation_pk(msg.tenant_id, msg.channel, msg.channel_user_id)
    stored_conv = router.conv.data[key]
    assert stored_conv["state_machine_status"] == "awaiting_class_selection"

