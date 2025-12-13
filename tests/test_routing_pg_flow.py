import time

import pytest

from src.domain.models import Message
from src.services.language_service import LanguageService
from src.services.routing_service import RoutingService

from tests.fakes_routing import (
    InMemoryConversations,
    FakeTenantsRepo,
    FakeTemplateServicePG,
    FakeCRM,
    FakeMembersIndex,
)

def _build_router(monkeypatch) -> tuple[RoutingService, InMemoryConversations]:
    conv = InMemoryConversations()
    tenants = FakeTenantsRepo(lang="pl")
    tpl = FakeTemplateServicePG()
    crm = FakeCRM()
    members_index = FakeMembersIndex()
    language = LanguageService(conv=conv, tenants=tenants)

    router = RoutingService(
        conv=conv,
        tenants=tenants,
        tpl=tpl,
        crm=crm,
        members_index=members_index,
        language=language,
    )

    # stubujemy detekcję języka, żeby testy nie wołały AWS Comprehend
    monkeypatch.setattr(router.language, "_detect_language", lambda text: "pl")
    return router, conv


def test_pg_available_classes_sets_state_and_pending(mock_ai, monkeypatch):
    """
    Wiadomość o dostępnych zajęciach:
    - zwraca listę zajęć,
    - zapisuje listę w pending (DDB) pod kluczem pending#<phone>,
    - ustawia state_machine_status=awaiting_class_selection.
    """
    router, conv = _build_router(monkeypatch)

    msg = Message(
        tenant_id="tenantA",
        from_phone="whatsapp:+48123123123",
        to_phone="whatsapp:+48000000000",
        body="jakie są dostępne zajęcia?",  # mock_ai -> intent pg_available_classes
        channel="whatsapp",
        channel_user_id="whatsapp:+48123123123",
    )

    actions = router.handle(msg)

    assert len(actions) == 1
    assert actions[0].type == "reply"
    body = actions[0].payload["body"]
    assert "Zumba" in body

    # lista klas trafia do pending
    pk = "pending#" + msg.from_phone
    pending_item = conv.pending.get(pk)
    assert pending_item is not None
    assert pending_item["sk"] == "classes"
    assert pending_item["items"][0]["class_id"] == "CLASS-1"

    # rozmowa jest w stanie wyboru zajęć
    key = conv.conversation_pk(msg.tenant_id, msg.channel, msg.channel_user_id)
    stored_conv = conv.data[key]
    assert stored_conv["last_intent"] == "crm_available_classes"
    assert stored_conv["state_machine_status"] == "awaiting_class_selection"


def test_class_selection_creates_pending_reservation_without_challenge(monkeypatch,mock_ai):
    """
    Mając listę zajęć i zweryfikowane konto PG:
    - wybór numeru zajęć '1' tworzy pending rezerwację,
    - użytkownik dostaje prośbę o potwierdzenie.
    """
    router, conv = _build_router(monkeypatch)

    tenant_id = "tenantA"
    phone = "whatsapp:+48123123123"
    channel = "whatsapp"
    channel_user_id = phone

    # symulujemy wcześniej wygenerowaną listę zajęć
    pk = "pending#" + phone
    conv.pending[pk] = {
        "pk": pk,
        "sk": "classes",
        "items": [
            {
                "index": 1,
                "class_id": "CLASS-1",
                "date": "2025-11-23",
                "time": "10:00",
                "name": "Zumba",
            }
        ],
    }

    # rozmowa jest zweryfikowana i w stanie wyboru zajęć
    key = conv.conversation_pk(tenant_id, channel, channel_user_id)
    conv.data[key] = {
        "language_code": "pl",
        "state_machine_status": "awaiting_class_selection",
        "crm_verification_level": "strong",
        "crm_verified_until": int(time.time()) + 60,
        "crm_member_id": "222",
    }

    msg = Message(
        tenant_id=tenant_id,
        from_phone=phone,
        to_phone="whatsapp:+48000000000",
        body="1",
        channel=channel,
        channel_user_id=channel_user_id,
    )

    actions = router.handle(msg)

    assert len(actions) == 1
    assert actions[0].type == "reply"
    assert "Czy potwierdzasz rezerwację" in actions[0].payload["body"]

    # powinna powstać pending rezerwacja, a conversation przejść w awaiting_confirmation
    pending_after = conv.pending.get(pk)
    assert pending_after is not None
    assert pending_after["sk"] == "pending"
    assert pending_after["class_id"] == "CLASS-1"
    assert pending_after["member_id"] == "222"

    stored_conv = conv.data[key]
    assert stored_conv["state_machine_status"] == "awaiting_confirmation"
    assert stored_conv["last_intent"] == "reserve_class"


def test_pending_reservation_confirmation_yes_triggers_crm_and_clears_pending(monkeypatch,mock_ai):
    """
    Jeśli istnieje pending rezerwacja i użytkownik odpowie słowem z listy 'TAK':
    - RoutingService woła CRM.reserve_class,
    - pending zostaje usunięty,
    - użytkownik dostaje komunikat o potwierdzeniu.
    """
    router, conv = _build_router(monkeypatch)
    crm: FakeCRM = router.crm  # type: ignore[assignment]

    tenant_id = "tenantA"
    phone = "whatsapp:+48123123123"
    channel = "whatsapp"
    channel_user_id = phone
    pk = "pending#" + phone

    conv.pending[pk] = {
        "pk": pk,
        "sk": "pending",
        "class_id": "CLASS-1",
        "member_id": "111",
        "idempotency_key": "idem-123",
        "class_name": "Zumba",
        "class_date": "2025-11-23",
        "class_time": "10:00",
    }

    msg = Message(
        tenant_id=tenant_id,
        from_phone=phone,
        to_phone="whatsapp:+48000000000",
        body="tak",  # jest w reserve_class_confirm_words
        channel=channel,
        channel_user_id=channel_user_id,
    )

    actions = router.handle(msg)

    # powinien zostać wysłany komunikat o potwierdzeniu
    assert len(actions) == 1
    assert actions[0].type == "reply"
    assert "Rezerwacja potwierdzona" in actions[0].payload["body"]

    # pending wyczyszczony
    assert pk not in conv.pending

    # CRM został wywołany z poprawnymi parametrami
    assert len(crm.reservations) == 1
    res_call = crm.reservations[0]
    assert res_call["tenant_id"] == tenant_id
    assert res_call["member_id"] == "111"
    assert res_call["class_id"] == "CLASS-1"


def test_pg_challenge_success_clears_state_and_runs_post_intent(monkeypatch):
    """
    Użytkownik jest w stanie awaiting_challenge, challenge się powiódł:
    - powinien dostać komunikat pg_challenge_success,
    - następnie wykona się post_intent (np. pg_member_balance),
    - pola pg_challenge_type / pg_post_intent / pg_post_slots zostaną wyczyszczone
      przez clear_crm_challenge.
    """
    router, conv = _build_router(monkeypatch)
    crm: FakeCRM = router.crm  # type: ignore[assignment]

    # zamiast pełnej integracji verify_member_challenge, stubujemy wywołanie w CRMFlowService
    monkeypatch.setattr(
        "src.services.crm_flow_service.CRMFlowService._verify_challenge_answer",
        lambda self, tenant_id, phone, challenge_type, answer: True,
        raising=False,
    )


    tenant_id = "tenantA"
    phone = "whatsapp:+48123123123"
    channel = "whatsapp"
    channel_user_id = phone

    key = conv.conversation_pk(tenant_id, channel, channel_user_id)
    conv.data[key] = {
        "language_code": "pl",
        "state_machine_status": "awaiting_challenge",
        "crm_challenge_type": "dob",
        "crm_challenge_attempts": 0,
        "crm_post_intent": "crm_member_balance",
        "crm_post_slots": {},
        "crm_verification_level": "none",
        "crm_verified_until": 0,
    }


    msg = Message(
        tenant_id=tenant_id,
        from_phone=phone,
        to_phone="whatsapp:+48000000000",
        body="01-05-1990",  # treść nie ma znaczenia, fake_verify zawsze zwraca True
        channel=channel,
        channel_user_id=channel_user_id,
    )

    actions = router.handle(msg)

    # 1) Dwie akcje: success + odpowiedź z saldem
    assert len(actions) == 2
    assert actions[0].type == "reply"
    assert "Weryfikacja zakończona sukcesem" in actions[0].payload["body"]

    assert actions[1].type == "reply"
    assert "Twoje saldo to" in actions[1].payload["body"]

    # 2) Rozmowa ma ustawioną silną weryfikację oraz pg_member_id
    stored_conv = conv.data[key]
    assert stored_conv["state_machine_status"] == "awaiting_message"
    assert stored_conv["crm_verification_level"] == "strong"
    assert stored_conv["crm_member_id"] == "999"

    # 3) clear_crm_challenge zostało wywołane i pola zostały wyczyszczone
    assert (tenant_id, channel, channel_user_id) in conv.cleared_calls
    for field in ("crm_challenge_type", "crm_challenge_attempts", "crm_post_intent", "crm_post_slots"):
        assert field not in stored_conv
