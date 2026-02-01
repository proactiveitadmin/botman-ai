from src.services.routing_service import RoutingService
from src.domain.models import Message
from tests.conftest import wire_subservices


class DummyNLU:
    """
    Bardzo prosty NLU – zawsze zwraca to, co dostanie w konstruktorze.
    """
    def __init__(self, result: dict):
        self._result = result
        self.calls: list[tuple[str, str | None]] = []

    def classify_intent(self, text: str, lang: str | None):
        # logujemy wywołania na wszelki wypadek
        self.calls.append((text, lang))
        return self._result


class DummyKB:
    """
    KB nie jest tu używane – ale RoutingService wymaga instancji.
    """
    def answer(self, *args, **kwargs):
        return "KB answer"

    def answer_ai(self, *args, **kwargs):
        return None

    def stylize_answer(self, base_answer, *args, **kwargs):
        return base_answer


class DummyTpl:
    """
    Zastępujemy TemplateService – nie korzystamy z DDB/Templates.
    """
    def render_named(self, tenant_id: str, template_name: str, lang: str, ctx: dict):
        # Interesuje nas tylko clarify_generic – resztę możemy zwrócić "po nazwie".
        if template_name == "clarify_generic":
            # tekst jak w realnym szablonie (zawiera "doprec")
            return "Czy możesz doprecyzować, w czym pomóc?"
        return template_name


class DummyConv:
    """
    In-memory ConversationsRepo – minimalna implementacja do tego testu.
    """
    def __init__(self):
        self.data = {}

    def get_conversation(self, tenant_id: str, channel: str, channel_user_id: str):
        key = (tenant_id, channel, channel_user_id)
        return self.data.get(key)

    def upsert_conversation(self, tenant_id: str, channel: str, channel_user_id: str, **kwargs):
        key = (tenant_id, channel, channel_user_id)
        existing = self.data.get(key, {})
        existing.update(kwargs)
        self.data[key] = existing

    # używane w innych ścieżkach, ale w tym teście nic tam nie ma
    def get(self, pk: str, sk: str):
        return None

    def put(self, item: dict):
        pass

    def delete(self, pk: str, sk: str):
        pass

    def find_by_verification_code(self, tenant_id: str, verification_code: str):
        return None


class DummyTenants:
    """
    Prosty zamiennik TenantsRepo – zwraca fixed language_code.
    """
    def __init__(self, default_lang: str = "pl"):
        self.default_lang = default_lang

    def get(self, tenant_id: str):
        return {
            "tenant_id": tenant_id,
            "language_code": self.default_lang,
        }


def make_routing_service(nlu_result: dict) -> RoutingService:
    """
    Buduje RoutingService z podanym wynikiem NLU i w pełni lokalnymi dummy serwisami.
    """
    nlu = DummyNLU(nlu_result)
    kb = DummyKB()
    tpl = DummyTpl()
    conv = DummyConv()
    tenants = DummyTenants(default_lang="pl")
    svc = RoutingService(nlu=nlu, kb=kb, tpl=tpl, conv=conv, tenants=tenants)
    wire_subservices(svc)

    return svc


def test_low_confidence_triggers_clarify(monkeypatch):
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
    wire_subservices(svc)

    # wyłączamy prawdziwą detekcję języka, żeby test nie dotykał Comprehend
    monkeypatch.setattr(svc.language, "_detect_language", lambda text: "pl")

    actions = svc.handle(msg)

    assert len(actions) == 1
    action = actions[0]
    assert action.type == "reply"

    body = action.payload["body"].lower()
    # DummyTpl zwraca "Czy możesz doprecyzować, w czym pomóc?"
    assert "doprec" in body
