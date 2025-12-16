from __future__ import annotations

from src.domain.models import Message
from src.services.language_service import LanguageService

from tests.fakes_routing import InMemoryConversations, FakeTenantsRepo


def _build_msg(body: str, tenant_id: str = "tenant-1", phone: str = "+48123123123", lang: str | None = None):
    return Message(
        tenant_id=tenant_id,
        from_phone=phone,
        to_phone="bot",
        body=body,
        channel="whatsapp",
        channel_user_id=phone,
        language_code=lang,
    )


def test_resolve_language_uses_detected_language(monkeypatch):
    conv = InMemoryConversations()
    tenants = FakeTenantsRepo(lang="pl")
    svc = LanguageService(conv=conv, tenants=tenants)

    monkeypatch.setattr(svc, "_detect_language", lambda text: "de")

    lang = svc.resolve_and_persist_language(_build_msg("Hallo, ich habe eine Frage."))
    assert lang == "de"


def test_resolve_language_uses_existing_conversation_when_detection_none(monkeypatch):
    conv = InMemoryConversations()
    tenants = FakeTenantsRepo(lang="pl")
    svc = LanguageService(conv=conv, tenants=tenants)

    # istniejąca rozmowa ma już język
    conv.upsert_conversation("tenant-1", "whatsapp", "+48123123123", language_code="en")

    monkeypatch.setattr(svc, "_detect_language", lambda text: None)

    lang = svc.resolve_and_persist_language(_build_msg("ok"))
    assert lang == "en"


def test_resolve_language_uses_tenant_language_when_no_detection_and_no_existing(monkeypatch):
    conv = InMemoryConversations()
    tenants = FakeTenantsRepo(lang="es")
    svc = LanguageService(conv=conv, tenants=tenants)

    monkeypatch.setattr(svc, "_detect_language", lambda text: None)

    lang = svc.resolve_and_persist_language(_build_msg("Hola"))
    assert lang == "es"


def test_resolve_language_persists_in_conversation(monkeypatch):
    conv = InMemoryConversations()
    tenants = FakeTenantsRepo(lang="pl")
    svc = LanguageService(conv=conv, tenants=tenants)

    calls: list[str] = []

    def fake_detect(text: str):
        calls.append(text)
        return "pl" if len(calls) == 1 else "en"

    monkeypatch.setattr(svc, "_detect_language", fake_detect)

    msg1 = _build_msg("Cześć")
    lang1 = svc.resolve_and_persist_language(msg1)
    assert lang1 == "pl"

    key1 = conv.conversation_pk(msg1.tenant_id, msg1.channel, msg1.channel_user_id)
    assert conv.data[key1]["language_code"] == "pl"

    msg2 = _build_msg("Hi")
    lang2 = svc.resolve_and_persist_language(msg2)
    assert lang2 == "en"

    key2 = conv.conversation_pk(msg2.tenant_id, msg2.channel, msg2.channel_user_id)
    assert conv.data[key2]["language_code"] == "en"


def test_explicit_language_code_from_message_overrides(monkeypatch):
    conv = InMemoryConversations()
    tenants = FakeTenantsRepo(lang="pl")
    svc = LanguageService(conv=conv, tenants=tenants)

    # nawet gdyby detekcja zwróciła coś innego, źródłem prawdy jest msg.language_code
    monkeypatch.setattr(svc, "_detect_language", lambda text: "de")

    msg = _build_msg("Hallo", lang="fr")
    lang = svc.resolve_and_persist_language(msg)
    assert lang == "fr"

    key = conv.conversation_pk(msg.tenant_id, msg.channel, msg.channel_user_id)
    assert conv.data[key]["language_code"] == "fr"

def test_does_not_override_language_on_verification_code(monkeypatch):
    conv = InMemoryConversations()
    tenants = FakeTenantsRepo(lang="pl")
    svc = LanguageService(conv=conv, tenants=tenants)
    conv.upsert_conversation("tenant-1", "whatsapp", "+48123123123", language_code="pl", state_machine_status="awaiting_verification")
    monkeypatch.setattr(svc, "_detect_language", lambda text: "pl")
    lang = svc.resolve_and_persist_language(_build_msg("KOD:ABC123"))
    assert lang == "pl"
