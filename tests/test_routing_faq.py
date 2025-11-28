from src.services.routing_service import RoutingService
from src.domain.models import Message

def test_faq_intent_uses_kb_service_answer():
    class DummyNLU:
        def classify_intent(self, text: str, lang: str | None):
            return {
                "intent": "faq",
                "confidence": 0.9,
                "slots": {"topic": "hours"},
            }

    class DummyKB:
        def answer(self, *args, **kwargs):
            return " KB answer "

    class DummyTemplateService:
        """
        Dummy szablonów na potrzeby testów routingu.
        Nie korzysta z żadnego DDB – tylko stałe stringi.
        """

        def render(self, template: str, context: dict):
            # Używane przy CONFIRM_TEMPLATE: np. "Potwierdź rezerwację %{class_id}"
            text = template
            for k, v in (context or {}).items():
                placeholder = f"%{{{k}}}"
                text = text.replace(placeholder, str(v))
            return text

        def render_named(self, tenant_id: str, name: str, language_code: str, context: dict):
            # Szablony, których używa RoutingService
            if name == "clarify_generic":
                return "Czy możesz doprecyzować, w czym pomóc?"

            if name == "handover_to_staff":
                return "Łączę Cię z pracownikiem klubu (wkrótce stałe przełączenie)."

            if name == "ticket_summary":
                return "Zgłoszenie klienta"

            if name == "ticket_created_ok":
                ticket = context.get("ticket", "XXX")
                return f"Utworzyłem zgłoszenie. Numer: {ticket}."

            if name == "ticket_created_failed":
                return "Nie udało się utworzyć zgłoszenia. Spróbuj później."

            # Fallback – przydatny w debugowaniu
            return name

    class DummyRepos:
        class DummyConversations:
            def __init__(self):
                self._store = {}

            def upsert_conversation(self, *a, **k):
                return {}

            def get_conversation(self, tenant_id, channel, channel_user_id):
                return None

            def get(self, pk):
                return self._store.get(pk)

            def put(self, item):
                pk = item.get("pk")
                if pk:
                    self._store[pk] = item

        class DummyMessages:
            def save_inbound(self, *args, **kwargs):
                return {}              
        
        class DummyTenants:
            def get(self, tenant_id: str):
                # w tym teście nie interesują nas ustawienia tenanta
                # zwracamy pusty dict, żeby _resolve_and_persist_language się nie wywalił
                return {}
                
        def __init__(self):
            self.conversations = self.DummyConversations()
            self.messages = self.DummyMessages()
            self.tenants = self.DummyTenants()

    repos = DummyRepos()

    svc = RoutingService()
    svc.nlu = DummyNLU()
    svc.kb = DummyKB()
    svc.tpl = DummyTemplateService()
    svc.conv = repos.conversations
    svc.messages = repos.messages
    svc.tenants = repos.tenants 


    msg = Message(
        tenant_id="t-1",
        from_phone="+48123123123",
        to_phone="+48123123123",
        body="Jakie macie godziny otwarcia?",
    )

    actions = svc.handle(msg)

    assert len(actions) == 1
    action = actions[0]
    assert action.type == "reply"
    assert "kb answer" in action.payload["body"].lower()
    