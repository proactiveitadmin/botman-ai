from src.services.routing_service import RoutingService
from src.domain.models import Message, Action
from tests.conftest import wire_subservices
import src.services.routing_service as routing_module

def test_handover_without_nlu_uses_precomputed_intent(monkeypatch):
    called = {"nlu_called": False}

    class DummyNLU:
        def classify_intent(self, text: str, lang: str | None):
            called["nlu_called"] = True
            return {"intent": "faq", "confidence": 0.9, "slots": {}}

    class DummyConvRepo:
        def __init__(self):
            self.conv = {"crm_member_id": "m-1"}

        def get_conversation(self, *args, **kwargs):
            return self.conv or {}

        def upsert_conversation(self, **kwargs):
            self.conv.update(kwargs)

        def get(self, key, sk):
            return None

        def put(self, item: dict):
            pass

        def delete(self, key):
            pass

        def assign_agent(self, tenant_id, channel, channel_user_id, agent_id):
            pass

    class DummyKB:
        def answer(self, *args, **kwargs):
            return "KB answer"
        def answer_ai(self, *args, **kwargs):
            return "KB AI answer"
        def normalize_ai_answer(self, *args, **kwargs):
            return "KB AI answer"

    class DummyTpl:
        def render_named(self, tenant, template_name, lang, ctx):
            if template_name == "handover_ask_comment":
                return f"ask_comment:{lang}"
            if template_name == "ticket_created_ok":
                return f"created:{ctx.get('ticket','')}"
            return "x"

    class DummyTenants:
        def get(self, tenant_id):
            return {"language_code": "pl"}

    class DummyTicketing:
        def __init__(self):
            self.calls = []

        def create_data_and_ticket(self, msg,  *args, **kwargs):
            self.calls.append(
                {
                    "tenant_id": getattr(msg, "tenant_id", None),
                    "body": getattr(msg, "body", None),
                }
            )
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
    monkeypatch.setattr(svc.crm_flow, "ensure_crm_verification", lambda *a, **k: None)
    monkeypatch.setattr(routing_module, "history_fetch_limit", 10, raising=False)
    
    # krok 1: intent=handover (precomputed) -> prosba o komentarz, bez ticketa
    msg1 = Message(
        tenant_id="t-1",
        from_phone="+48123123123",
        to_phone="+48xxx",
        body="",
        intent="handover",
        slots={"agent_id": "agent-123"},
        channel="whatsapp",
        channel_user_id="whatsapp:+48123123123",
    )
    actions1 = svc.handle(msg1)

    assert not called["nlu_called"]
    assert not svc.ticketing.calls, "Ticket nie powinien powstać w 1. kroku handover (bot prosi o komentarz)."
    assert len(actions1) == 1
    assert actions1[0].type == "reply"

    # krok 2: komentarz -> tworzymy ticket
    msg2 = Message(
        tenant_id="t-1",
        from_phone="+48123123123",
        to_phone="+48xxx",
        body="Potrzebuję rozmowy z obsługą, problem z płatnością.",
        channel="whatsapp",
        channel_user_id="whatsapp:+48123123123",
    )
    actions2 = svc.handle(msg2)

    assert svc.ticketing.calls, "Ticket powinien powstać po komentarzu (2. krok handover)."
    assert len(actions2) == 1
    assert actions2[0].type == "reply"
