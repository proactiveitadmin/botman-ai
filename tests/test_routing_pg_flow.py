import time
import pytest
from src.common.security import otp_hash
from src.domain.models import Message
from src.services.language_service import LanguageService
from src.services.routing_service import RoutingService
from src.common.constants import STATE_AWAITING_MESSAGE

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


def test_crm_available_classes_sets_state_and_pending(mock_ai, monkeypatch):
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
        body="jakie są dostępne zajęcia?",  # mock_ai -> intent crm_available_classes
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

def test_pending_reservation_confirmation_yes_when_already_booked_returns_dedicated_message(monkeypatch, mock_ai):
    """Jeśli PG zwróci business error 'ClassesAlreadyBooked', użytkownik dostaje dedykowany komunikat."""
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

    def fake_reserve_class(*args, **kwargs):
        # zachowujemy log rezerwacji dla asercji, ale zwracamy mapped_error
        crm.reservations.append(
            {
                "tenant_id": kwargs.get("tenant_id"),
                "member_id": kwargs.get("member_id"),
                "class_id": kwargs.get("class_id"),
                "idem": kwargs.get("idempotency_key"),
                "comments": kwargs.get("comments"),
            }
        )
        return {
            "ok": False,
            "status_code": 400,
            "mapped_error": "classes_already_booked",
            "pg_error": {"code": "ClassesAlreadyBooked"},
        }

    monkeypatch.setattr(crm, "reserve_class", fake_reserve_class)

    msg = Message(
        tenant_id=tenant_id,
        from_phone=phone,
        to_phone="whatsapp:+48000000000",
        body="tak",
        channel=channel,
        channel_user_id=channel_user_id,
    )

    actions = router.handle(msg)

    assert len(actions) == 1
    assert actions[0].type == "reply"
    assert "już" in actions[0].payload["body"].lower()
    assert "zarezerw" in actions[0].payload["body"].lower()

    # pending wyczyszczony nawet w przypadku business erroru
    assert pk not in conv.pending

    # CRM został wywołany
    assert len(crm.reservations) == 1

def test_email_otp_success_clears_state_and_runs_post_intent(monkeypatch):
    router, conv = _build_router(monkeypatch)

    tenant_id = "tenantA"
    phone = "whatsapp:+48123123123"
    channel = "whatsapp"
    channel_user_id = phone

    key = conv.conversation_pk(tenant_id, channel, channel_user_id)

    code = "A1B2C3"   # dopasuj do realnego formatu (A-Z0-9) lub 6 cyfr
    now = int(time.time())
    conv.data[key] = {
        "language_code": "pl",
        "state_machine_status": "awaiting_challenge",
        "crm_challenge_type": "email_otp",
        "crm_challenge_attempts": 0,  # opcjonalnie
        "crm_post_intent": "crm_member_balance",
        "crm_post_slots": {},
        "crm_verification_level": "none",
        "crm_verified_until": 0,

        # OTP fields
        "crm_otp_hash": otp_hash(tenant_id, "crm_email_otp", code),
        "crm_otp_expires_at": now + 300,
        "crm_otp_attempts_left": 3,
        "crm_otp_last_sent_at": now,
        "crm_otp_email": "user@example.com",
    }

    msg = Message(
        tenant_id=tenant_id,
        from_phone=phone,
        to_phone="whatsapp:+48000000000",
        body=code,                 # user wpisuje OTP
        channel=channel,
        channel_user_id=channel_user_id,
    )

    actions = router.handle(msg)

    # 1) Sukces + post_intent (saldo)
    assert len(actions) >= 1
    assert actions[0].type == "reply"
    assert "Weryfikacja zakończona sukcesem" in actions[0].payload["body"]

    # (jeśli w tym routerze po sukcesie zawsze leci saldo jako drugi reply)
    assert any(
        a.type == "reply" and "saldo" in (a.payload.get("body") or "").lower()
        for a in actions
    )

    stored_conv = conv.data[key]
    assert stored_conv["state_machine_status"] == "awaiting_message"
    assert stored_conv["crm_verification_level"] == "strong"
    assert stored_conv.get("crm_verified_until", 0) > now

    # 2) challenge state wyczyszczony
    assert (tenant_id, channel, channel_user_id) in conv.cleared_calls
    for field in (
        "crm_challenge_type",
        "crm_challenge_attempts",
        "crm_post_intent",
        "crm_post_slots",
        "crm_otp_hash",
        "crm_otp_expires_at",
        "crm_otp_attempts_left",
        "crm_otp_last_sent_at",
        "crm_otp_email",
    ):
        assert field not in stored_conv
        
def test_reserve_class_with_class_type_name_returns_list_not_confirmation(
    monkeypatch, mock_ai
):
    """
    Użytkownik pyta: 'mogę zarezerwować pilates?'

    Oczekujemy:
    - zapytania do PG o listę zajęć z filtrem classType/name contains 'pilates'
    - odpowiedzi z listą zajęć
    - non-member: brak wejścia w flow wyboru klasy (pozostajemy w awaiting_message)
    - brak pytania o potwierdzenie (TAK/NIE)
    """
    router, conv = _build_router(monkeypatch)
    crm: FakeCRM = router.crm  # type: ignore

    # Fake odpowiedź PG: lista zajęć Pilates
    crm.available_classes_resp = {
        "ok": True,
        "value": [
            {
                "id": "CLASS-1",
                "startDate": "2026-01-12T18:00:00",
                "classType": {"name": "Pilates"},
                "instructor": {"name": "Anna"},
            },
            {
                "id": "CLASS-2",
                "startDate": "2026-01-13T09:00:00",
                "classType": {"name": "Pilates"},
                "instructor": {"name": "Kasia"},
            },
        ],
    }

    # NLU zwraca class_id jako tekst (nazwa typu zajęć!)
    def fake_detect_intent(*args, **kwargs):
        return {
            "intent": "reserve_class",
            "confidence": 0.95,
            "slots": {
                "class_id": "pilates",
            },
        }

    monkeypatch.setattr(router.nlu, "classify_intent", lambda body, lang: fake_detect_intent())

    msg = Message(
        tenant_id="tenantA",
        from_phone="whatsapp:+48123123123",
        to_phone="whatsapp:+48000000000",
        body="mogę zarezerwować pilates?",
        channel="whatsapp",
        channel_user_id="whatsapp:+48123123123",
    )

    actions = router.handle(msg)

    # --- ASSERTY ---

    # 1️⃣ Jedna odpowiedź – lista zajęć
    assert len(actions) == 1
    assert actions[0].type == "reply"

    body = actions[0].payload["body"].lower()

    # 2️⃣ Jest lista zajęć, a nie confirmation
    assert "pilates" in body
    assert "1." in body or "1)" in body
    assert "tak" not in body
    assert "nie" not in body

    # 3️⃣ CRM dostał filtr po typie zajęć
    assert len(crm.available_classes_calls) == 1
    call = crm.available_classes_calls[0]
    assert call["class_type_query"] == "pilates"

    # 4️⃣ Stan rozmowy: wybór klasy z listy
    conv_state = conv.get_conversation(
        tenant_id="tenantA",
        channel="whatsapp",
        channel_user_id="whatsapp:+48123123123",
    )
    assert conv_state["state_machine_status"] == "awaiting_message"

def test_lead_reserve_class_shows_info_list_without_selection(monkeypatch):
    router, conv = _build_router(monkeypatch)

    monkeypatch.setattr(
        router.crm_flow.crm,
        "get_member_by_phone",
        lambda tenant_id, phone: {"value": [{"id": "L-1", "memberType": "Lead"}]},
        raising=False,
    )

    msg = Message(
        tenant_id="tenantA",
        from_phone="whatsapp:+48123123123",
        to_phone="whatsapp:+48000000000",
        body="zapisz mnie na zajęcia",
        channel="whatsapp",
        channel_user_id="whatsapp:+48123123123",
        intent="reserve_class",
        slots={},
    )

    actions = router.handle(msg)
    body = actions[0].payload["body"]

    assert "Dostępne zajęcia:" in body
    assert "wybierz" not in body.lower()

    pk = "pending#" + msg.from_phone
    assert pk not in conv.pending

    stored = conv.get_conversation("tenantA", "whatsapp", msg.channel_user_id)
    assert stored["state_machine_status"] == "awaiting_message"
