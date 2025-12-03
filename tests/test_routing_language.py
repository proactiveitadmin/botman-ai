import pytest

from src.domain.models import Message
from src.services.routing_service import RoutingService


class FakeConvRepo:
    def __init__(self, existing=None):
        # existing: symulacja już istniejącej rozmowy z language_code
        self._existing = existing
        self.last_upsert = None

    def get_conversation(self, tenant_id: str, channel: str, channel_user_id: str):
        return self._existing

    def upsert_conversation(self, tenant_id: str,  channel: str, channel_user_id: str, **kwargs):
        self.last_upsert = {"tenant_id": tenant_id, "channel": channel, "channel_user_id":channel_user_id, **kwargs}
        return self.last_upsert

    def put(self, item: dict):
        key = item["pk"]
        self.pending[key] = dict(item)
        
    def get(self, pk: str, sk: str):
        return None

    def delete(self, key: str):
        self.deleted.append(key)
        self.pending.pop(key, None)

    def find_by_verification_code(self, tenant_id, verification_code):
        return None

class FakeTenantsRepo:
    def __init__(self, lang: str | None):
        self.lang = lang

    def get(self, tenant_id: str):
        # minimalny model: tenant ma język lang
        return {"tenant_id": tenant_id, "language_code": self.lang}


def test_routing_uses_tenant_language_for_nlu_and_kb(monkeypatch):
    """
    Nowa rozmowa, brak language_code na Conversation:
    - lang wzięty z Tenanta,
    - NLU i KB dostają ten sam lang,
    - upsert_conversation zapisuje language_code.
    """
    # 1) Patch NLUService.classify_intent i KBService.answer, żeby zebrać użyte lang
    called = {}

    def fake_classify_intent(self, text: str, lang: str):
        called["nlu_lang"] = lang
        return {"intent": "faq", "confidence": 0.9, "slots": {"topic": "hours"}}

    def fake_answer(self, topic: str, tenant_id: str, language_code: str | None = None):
        called["kb_lang"] = language_code
        return f"FAQ-{language_code}"

    monkeypatch.setattr(
        "src.services.nlu_service.NLUService.classify_intent",
        fake_classify_intent,
        raising=False,
    )
    monkeypatch.setattr(
        "src.services.kb_service.KBService.answer",
        fake_answer,
        raising=False,
    )

    # 2) RoutingService z podmienionymi repozytoriami
    router = RoutingService()
    router.tenants = FakeTenantsRepo(lang="en")
    router.conv = FakeConvRepo(existing=None)  # brak zapisanej rozmowy

    msg = Message(
        tenant_id="default",
        from_phone="whatsapp:+48123123123",
        to_phone="whatsapp:+48000000000",
        body="Godziny otwarcia?",
    )

    actions = router.handle(msg)
    assert actions, "Router powinien zwrócić co najmniej jedną akcję reply"

    # 3) Assert – język użyty w NLU i KB
    assert called.get("nlu_lang") == "en"
    assert called.get("kb_lang") == "en"

    # 4) Assert – język zapisany w Conversation
    assert router.conv.last_upsert is not None
    assert router.conv.last_upsert.get("language_code") == "en"


def test_routing_prefers_existing_conversation_language(monkeypatch):
    """
    Jeżeli istnieje już Conversation z language_code,
    router powinien używać właśnie tego języka, a nie języka z Tenanta.
    """
    called = {}

    def fake_classify_intent(self, text: str, lang: str):
        called["nlu_lang"] = lang
        return {"intent": "faq", "confidence": 0.9, "slots": {"topic": "hours"}}

    def fake_answer(self, topic: str, tenant_id: str, language_code: str | None = None):
        called["kb_lang"] = language_code
        return f"FAQ-{language_code}"

    monkeypatch.setattr(
        "src.services.nlu_service.NLUService.classify_intent",
        fake_classify_intent,
        raising=False,
    )
    monkeypatch.setattr(
        "src.services.kb_service.KBService.answer",
        fake_answer,
        raising=False,
    )

    # Conversation ma już language_code="de"
    existing_conv = {"pk": "conv#default#whatsapp:+48123123123", "language_code": "de"}

    router = RoutingService()
    router.tenants = FakeTenantsRepo(lang="en")           # tenant mówi "en"
    router.conv = FakeConvRepo(existing=existing_conv)    # ale rozmowa ma już "de"

    msg = Message(
        tenant_id="default",
        from_phone="whatsapp:+48123123123",
        to_phone="whatsapp:+48000000000",
        body="Godziny otwarcia?",
    )

    actions = router.handle(msg)
    assert actions, "Router powinien zwrócić akcję reply"

    # użyty język = ten z conversation (de), a nie z Tenanta (en)
    assert called.get("nlu_lang") == "de"
    assert called.get("kb_lang") == "de"

    # (opcjonalnie) sprawdzamy, że upsert nie zmienił języka
    assert router.conv.last_upsert is not None
    assert router.conv.last_upsert.get("language_code") == "de"
