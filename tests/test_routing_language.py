from src.domain.models import Message
from src.services.routing_service import RoutingService


class DummyConvRepo:
    def __init__(self, existing=None):
        self._existing = existing
        self.last_upsert = None

    def get_conversation(self, tenant_id: str, channel: str, channel_user_id: str):
        return self._existing

    def upsert_conversation(self, tenant_id: str, channel: str, channel_user_id: str, **kwargs):
        self.last_upsert = {
            "tenant_id": tenant_id,
            "channel": channel,
            "channel_user_id": channel_user_id,
            **kwargs,
        }


class DummyTenantsRepo:
    def __init__(self, lang: str = "pl"):
        self._lang = lang

    def get(self, tenant_id: str):
        return {"tenant_id": tenant_id, "language_code": self._lang}


def _build_msg(body: str = "hello") -> Message:
    return Message(
        tenant_id="t-1",
        from_phone="whatsapp:+48123123123",
        to_phone="whatsapp:+48000000000",
        body=body,
        channel="whatsapp",
    )


def test_resolve_language_uses_detected_language(monkeypatch):
    svc = RoutingService()
    svc.conv = DummyConvRepo(existing=None)
    svc.tenants = DummyTenantsRepo(lang="pl")

    # stub Comprehend-owej detekcji
    monkeypatch.setattr(svc, "_detect_language", lambda text: "de")

    lang = svc._resolve_and_persist_language(_build_msg("Hallo, ich habe eine Frage."))

    assert lang == "de"
    assert svc.conv.last_upsert is not None
    assert svc.conv.last_upsert.get("language_code") == "de"


def test_resolve_language_uses_existing_conversation_when_detection_none(monkeypatch):
    existing_conv = {"language_code": "fr"}
    svc = RoutingService()
    svc.conv = DummyConvRepo(existing=existing_conv)
    svc.tenants = DummyTenantsRepo(lang="pl")

    monkeypatch.setattr(svc, "_detect_language", lambda text: None)

    lang = svc._resolve_and_persist_language(_build_msg("ok"))

    # powinien zostać język z istniejącej rozmowy
    assert lang == "fr"
    # albo w ogóle brak nowego upsertu, albo upsert nie zmieni języka
    assert svc.conv.last_upsert is None or svc.conv.last_upsert.get("language_code") == "fr"


def test_resolve_language_uses_tenant_language_when_no_detection_and_no_existing(monkeypatch):
    svc = RoutingService()
    svc.conv = DummyConvRepo(existing=None)
    svc.tenants = DummyTenantsRepo(lang="es")  # język tenanta to hiszpański

    monkeypatch.setattr(svc, "_detect_language", lambda text: None)

    lang = svc._resolve_and_persist_language(_build_msg("Hola"))

    assert lang == "es"
    assert svc.conv.last_upsert is not None
    assert svc.conv.last_upsert.get("language_code") == "es"
