from src.services.routing_service import RoutingService
from src.domain.models import Message
from tests.conftest import wire_subservices


def test_handover_reply_contains_language_code(monkeypatch):
    class DummyNLU:
        def classify_intent(self, text: str, lang: str | None):
            return {"intent": "handover", "confidence": 0.99, "slots": {}}

    class DummyTpl:
        def render_named(self, tenant, template_name, lang, ctx):
            return f"handover_to_staff:{lang}"

    class DummyConvRepo:
        def __init__(self):
            self.pending = {}

        def get_conversation(self, *args, **kwargs):
            # brak stanu rozmowy -> nowa
            return {}

        def upsert_conversation(self, *args, **kwargs):
            # w tym teście nic nie asercikujemy na zapis
            pass

        # używane przez RoutingService do obsługi pending rezerwacji
        def get(self, key, sk):
            return self.pending.get(key)

        def put(self, item: dict):
            pk = item.get("pk")
            if pk:
                self.pending[pk] = item

        def delete(self, key):
            self.pending.pop(key, None)
        
        def assign_agent(self, tenant_id, channel, channel_user_id, agent_id):
            self.assigned = {
                "tenant_id": tenant_id,
                "channel": channel,
                "channel_user_id": channel_user_id,
                "agent_id": agent_id,
            }

    class DummyTenants:
        def get(self, tenant_id):
            return {"language_code": "pl"}

    svc = RoutingService()
    svc.nlu = DummyNLU()
    svc.tpl = DummyTpl()
    svc.conv = DummyConvRepo()
    svc.tenants = DummyTenants()
    wire_subservices(svc)


    monkeypatch.setattr(svc.language, "_detect_language", lambda text: "pl")
     
    msg = Message(
        tenant_id="t-1",
        from_phone="+48123123123",
        to_phone="+48xxx",
        body="Porozmawiaj z konsultantem",
    )

    actions = svc.handle(msg)
    assert actions
    payload = actions[0].payload
    assert payload.get("language_code") == "pl"
