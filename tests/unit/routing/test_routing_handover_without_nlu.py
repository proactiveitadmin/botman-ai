from src.services.routing_service import RoutingService
from src.domain.models import Message, Action
from tests.conftest import wire_subservices


def test_handover_without_nlu_uses_precomputed_intent(monkeypatch):
    called = {"nlu_called": False}

    class DummyNLU:
        def classify_intent(self, text: str, lang: str | None):
            called["nlu_called"] = True
            return {
                "intent": "faq",
                "confidence": 0.9,
                "slots": {},
            }

    class DummyConvRepo:
        def __init__(self):
            self.pending = {}
            self.last_upsert = None
            self.assigned = None

        def get_conversation(self, *args, **kwargs):
            return {}

        def upsert_conversation(self, *args, **kwargs):
            # symulacja zapisania handoveru
            self.last_upsert = kwargs

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


    class DummyKB:
        def answer(self, *args, **kwargs):
            return "KB answer "       
        
        def answer_ai(self, *args, **kwargs):
            return " KB AI answer "
    class DummyTpl:
        def render_named(self, tenant, template_name, lang, ctx):
            if template_name == "handover_to_staff":
                return f"handover:{lang}"
            return "x"

    class DummyTenants:
        def get(self, tenant_id):
            return {"language_code": "pl"}
    class DummyTicketing:
        def __init__(self):
            self.calls = []

        def create_ticket(self, tenant_id, summary, description, meta=None):
            self.calls.append(
                {
                    "tenant_id": tenant_id,
                    "summary": summary,
                    "description": description,
                    "meta": meta or {},
                }
            )
            # RoutingService oczekuje dict-a z kluczem 'ticket' lub 'key'
            return {"ticket": "ABC-123"}
    
    svc = RoutingService()
    svc.nlu = DummyNLU()
    svc.conv = DummyConvRepo()
    svc.kb = DummyKB()
    svc.tpl = DummyTpl()
    svc.tenants = DummyTenants()
    svc.ticketing = DummyTicketing()
    wire_subservices(svc)

    
    monkeypatch.setattr(svc.language, "_detect_language", lambda text: "pl")

    msg = Message(
        tenant_id="t-1",
        from_phone="+48123123123",
        to_phone="+48xxx",
        body="",
        intent="handover",   # <--- kluczowe
        slots={"agent_id": "agent-123"},
    )

    actions = svc.handle(msg)

    # 1) NLU NIE zostało wywołane
    assert not called["nlu_called"]
    
    # Sprawdzamy, że TicketingService zostało zawołane
    assert svc.ticketing.calls, "TicketingService.create_ticket powinno zostać wywołane"

    # 2) Zwrócona akcja reply (handover_to_staff)
    assert len(actions) == 1
    action = actions[0]
    assert action.type == "reply"
