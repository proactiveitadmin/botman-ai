from src.services.routing_service import RoutingService
from src.domain.models import Message
from tests.conftest import wire_subservices

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
            self.conv = {}

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
    assert len(svc.ticketing.calls) == 0, "Ticket nie powinien być tworzony w 1. kroku (bot prosi o komentarz)."

    # --- krok 2: komentarz -> dopiero teraz tworzy się ticket ---
    msg2 = Message(
        tenant_id="t-1",
        from_phone="+48123123123",
        to_phone="+48xxx",
        body="Komentarz: nie działa przedłużenie w aplikacji",
        channel="whatsapp",
        channel_user_id="whatsapp:+48123123123",
    )
    actions2 = svc.handle(msg2)

    assert actions2
    assert actions2[0].type == "reply"
    assert len(svc.ticketing.calls) == 1, "Ticket powinien być utworzony po komentarzu (2. krok)."

    call = svc.ticketing.calls[0]

    # conv_key powinien bazować na tenant/channel/channel_user_id (tak jak w routing_service._conv_key)
    assert "conv#whatsapp#" in call["conv_key"]

    # history_block powinien zawierać historię (routing robi "direction: body")
    hb = call["history_block"]
    assert "in: Cześć" in hb
    assert "out: W czym mogę pomóc?" in hb
    assert "in: Mam problem z karnetem." in hb
