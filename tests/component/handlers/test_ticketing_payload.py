from src.services.routing_service import RoutingService
from src.domain.models import Message
from tests.conftest import wire_subservices
import src.services.routing_service as routing_module
from src.common.constants import (
    CRM_CONFIRM_WORDS,
    CRM_REJECT_WORDS,
    STATE_AWAITING_TICKET_CONFIRMATION,
    STATE_AWAITING_TICKET_COMMENT,
    STATE_AWAITING_MESSAGE,
)

def test_ticket_payload_contains_history_and_meta(monkeypatch):
    class DummyNLU:
        def classify_intent(self, text: str, lang: str | None):
            return {
                "intent": "ticket",
                "confidence": 0.99,
                "slots": {
                    "summary": "Problem z karnetem",
                    "description": "Użytkownik zgłasza problem z karnetem.",
                },
            }

    class DummyKB:
        def answer(self, *args, **kwargs):
            return "KB answer"

    class DummyTpl:
        def render_named(self, tenant, template_name, lang, ctx):
            if template_name == "ticket_more_info":
                return "Doprecyzuj proszę zgłoszenie."
            if template_name == "ticket_created_ok":
                return f"OK {ctx.get('ticket', ctx.get('key', ''))}"
            if template_name == "ticket_created_failed":
                return "FAILED"
            return "x"

    class DummyConvRepo:
        def __init__(self):
            # żeby _require_member_id nie “blokowało” flow
            self.conv = {"crm_member_id": "m-1"}

        def get_conversation(self, tenant_id, channel, channel_user_id):
            return self.conv or {}

        def upsert_conversation(self, **kwargs):
            self.conv.update(kwargs)

        def get(self, key, sk):
            return None

        def put(self, item: dict):
            pass

        def delete(self, key):
            pass

    class DummyMessagesRepo:
        def get_last_messages(self, tenant_id, conv_key, limit=None):
            return [
                {"direction": "in", "body": "Cześć"},
                {"direction": "out", "body": "W czym mogę pomóc?"},
                {"direction": "in", "body": "Mam problem z karnetem."},
            ]

    class DummyTenants:
        def get(self, tenant_id):
            return {"language_code": "pl"}

    class DummyTicketing:
        def __init__(self):
            self.calls = []

        def create_data_and_ticket(self, msg, lang, conv_key, history_block):
            self.calls.append(
                {
                    "tenant_id": getattr(msg, "tenant_id", None),
                    "body": getattr(msg, "body", None),
                    "conv_key": conv_key,
                    "history_block": history_block,
                }
            )
            return {"key": "KEY-1"}

    svc = RoutingService()
    svc.nlu = DummyNLU()
    svc.kb = DummyKB()
    svc.tpl = DummyTpl()
    svc.messages = DummyMessagesRepo()
    svc.ticketing = DummyTicketing()
    svc.conv = DummyConvRepo()
    svc.tenants = DummyTenants()
    wire_subservices(svc)

    monkeypatch.setattr(svc.language, "_detect_language", lambda text: "pl")
    monkeypatch.setattr(svc.crm_flow, "ensure_crm_verification", lambda *a, **k: None)
    monkeypatch.setattr(routing_module, "history_fetch_limit", 10, raising=False)
    
    def fake_get_words_set(tenant_id, key, lang):
        if key == CRM_CONFIRM_WORDS:
            return {"tak", "t", "yes"}
        if key == CRM_REJECT_WORDS:
            return {"nie", "n", "no"}
        return set()
    monkeypatch.setattr(svc.crm_flow, "_get_words_set", fake_get_words_set)
        
    # --- krok 1: intent=ticket -> bot prosi o komentarz, NIE tworzy ticketa ---
    msg1 = Message(
        tenant_id="t-1",
        from_phone="+48123123123",
        to_phone="+48xxx",
        body="Zgłoś ticket",
        channel="whatsapp",
        channel_user_id="whatsapp:+48123123123",
        intent="ticket",
        slots={"summary": "Problem z karnetem", "description": "Użytkownik zgłasza problem z karnetem."},
    )

    actions1 = svc.handle(msg1)

    assert actions1
    assert len(svc.ticketing.calls) == 0, "Ticket nie powinien być tworzony w 1. kroku (bot prosi o zgodę)."

    # --- krok 2: zgoda - bot czeka na komentarz ---
    msg2 = Message(
        tenant_id="t-1",
        from_phone="+48123123123",
        to_phone="+48xxx",
        body="tak",
        channel="whatsapp",
        channel_user_id="whatsapp:+48123123123",
    )
    actions2 = svc.handle(msg2)

    assert actions2
    assert len(svc.ticketing.calls) == 0, "Ticket nie powinien być tworzony w 2. kroku (bot prosi o komentarz)."
    
    # --- krok 3: komentarz -> dopiero teraz tworzy się ticket ---
    msg3 = Message(
        tenant_id="t-1",
        from_phone="+48123123123",
        to_phone="+48xxx",
        body="Komentarz: nie działa przedłużenie w aplikacji",
        channel="whatsapp",
        channel_user_id="whatsapp:+48123123123",
    )
    actions3 = svc.handle(msg3)

    assert actions3
    assert actions3[0].type == "reply"
    assert len(svc.ticketing.calls) == 1, "Ticket powinien być utworzony po komentarzu (3. krok)."

    call = svc.ticketing.calls[0]

    assert "conv#whatsapp#" in call["conv_key"]

    hb = call["history_block"]
    assert "in: Cześć" in hb
    assert "out: W czym mogę pomóc?" in hb
    assert "in: Mam problem z karnetem." in hb