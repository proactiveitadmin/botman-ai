from src.services.routing_service import RoutingService
from src.domain.models import Message


class DummyNLU:
    def __init__(self, result):
        self._result = result

    def classify_intent(self, text: str, lang: str | None):
        return self._result


class DummyKB:
    def answer(self, *args, **kwargs):
        return " KB answer "


class DummyTemplateService:
    def render(self, tenant_id: str, language_code: str | None):
        return "Czy możesz doprecyzować, o co dokładnie chodzi?"


class DummyRepos:
    class DummyConversations:
        def __init__(self):
            self._store = {}

        def upsert_conversation(self, *a, **k):
            return {}

        def get_conversation(self, tenant_id, phone):
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
        
def make_routing_service(nlu_result):
    repos = DummyRepos()
    nlu = DummyNLU(nlu_result)
    kb = DummyKB()
    templates = DummyTemplateService()

    svc = RoutingService()
    svc.nlu = nlu
    svc.kb = kb
    svc.tpl = templates
    svc.conv = repos.conversations
    svc.messages = repos.messages
    svc.tenants = repos.tenants 
    return svc


def test_low_confidence_triggers_clarify():
    msg = Message(
        tenant_id="t-1",
        from_phone="+48123123123",
        to_phone="+48123123123",
        body="Chyba chodzi mi o coś z grafikiem",
    )

    svc = make_routing_service(
        {
            "intent": "reserve_class",  # model niby myśli, że to rezerwacja
            "confidence": 0.2,          # ale z bardzo niską pewnością
            "slots": {},
        }
    )

    actions = svc.handle(msg)

    assert len(actions) == 1
    action = actions[0]
    assert action.type == "reply"
    assert "doprecyz" in action.payload["body"].lower()
