from src.services.routing_service import RoutingService
from src.domain.models import Message


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
            if template_name == "ticket_summary":
                return "Zgłoszenie klienta"
            return "x"

    class DummyConvRepo:
        def __init__(self):
            self.pending = {}

        def get_conversation(self, *args, **kwargs):
            return {}  # brak wcześniejszej rozmowy

        def upsert_conversation(self, *args, **kwargs):
            pass

        def get(self, key, sk):
            return self.pending.get(key)

        def put(self, item: dict):
            pk = item.get("pk")
            if pk:
                self.pending[pk] = item

        def delete(self, key):
            self.pending.pop(key, None)

    class DummyMessagesRepo:
        def get_last_messages(self, tenant_id, conv_key, limit=10):
            return [
                {"direction": "in", "body": "Cześć"},
                {"direction": "out", "body": "W czym mogę pomóc?"},
                {"direction": "in", "body": "Mam problem z karnetem."},
            ]

    class DummyTenants:
        def get(self, tenant_id):
            return {"language_code": "pl"}

    called = {}

    class DummyTicketing:
        def create_ticket(self, tenant_id, summary, description, meta=None):
            called["summary"] = summary
            called["description"] = description
            called["meta"] = meta or {}
            return {"ok": True, "ticket": "KEY-1"}

    svc = RoutingService()
    svc.nlu = DummyNLU()
    svc.kb = DummyKB()
    svc.tpl = DummyTpl()
    svc.messages = DummyMessagesRepo()
    svc.ticketing = DummyTicketing()
    svc.conv = DummyConvRepo()
    svc.tenants = DummyTenants()

    msg = Message(
        tenant_id="t-1",
        from_phone="+48123123123",
        to_phone="+48xxx",
        body="Zgłoś ticket",
        channel="whatsapp",
        channel_user_id="whatsapp:+48123123123",
    )

    actions = svc.handle(msg)

    # upewniamy się, że TicketingService.create_ticket zostało wywołane
    assert called, "TicketingService.create_ticket powinno zostać wywołane"
    assert "Problem z karnetem" in called["summary"] or "Zgłoszenie klienta" in called["summary"]
    assert "problem z karnetem." in called["description"]

    meta = called["meta"]
    assert meta["phone"] == msg.from_phone
    assert meta["channel"] == msg.channel
    assert meta["channel_user_id"] == msg.channel_user_id
    assert meta["intent"] == "ticket"
    assert isinstance(meta["slots"], dict)
    assert meta["language_code"] == "pl"

    # odpowiedź do użytkownika
    assert actions
    assert actions[0].type == "reply"