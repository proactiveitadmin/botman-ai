

import time

import pytest

from src.services.routing_service import RoutingService
from src.domain.models import Message


class InMemoryConversations:
    """
    Minimalny in-memory odpowiednik ConversationsRepo używany
    tylko w testach RoutingService (bez Dynama).
    """

    def __init__(self):
        self.data: dict[tuple[str, str, str], dict] = {}
        self.pending: dict[str, dict] = {}
        self.cleared_calls: list[tuple[str, str, str]] = []

    # --- API kompatybilne z ConversationsRepo używanym w RoutingService ---

    def conversation_pk(self, tenant_id: str, channel: str, channel_user_id: str):
        return (tenant_id, channel, channel_user_id)

    def get_conversation(self, tenant_id: str, channel: str, channel_user_id: str):
        return self.data.get(self.conversation_pk(tenant_id, channel, channel_user_id))

    def upsert_conversation(self, tenant_id: str, channel: str, channel_user_id: str, **attrs):
        key = self.conversation_pk(tenant_id, channel, channel_user_id)
        conv = self.data.setdefault(key, {})
        conv.update(attrs)
        # w prawdziwym repo ustawiany jest updated_at – symulujemy to, bo RoutingService z niego korzysta
        conv.setdefault("updated_at", int(time.time()))
        return conv

    # pending rezerwacje / lista klas
    def get(self, pk: str, sk: str):
        # w testach ignorujemy sk (pending/classes) – klucz jest w pk
        return self.pending.get(pk)

    def put(self, item: dict):
        key = item["pk"]
        self.pending[key] = dict(item)

    def delete(self, pk: str, sk: str):
        self.pending.pop(pk, None)

    # inne metody używane z RoutingService
    def set_language(self, tenant_id: str, phone: str, new_lang: str):
        key = self.conversation_pk(tenant_id, "whatsapp", phone)
        conv = self.data.setdefault(key, {})
        conv["language_code"] = new_lang
        return conv

    def find_by_verification_code(self, tenant_id: str, verification_code: str):
        # nie używane w tych testach
        return None

    def clear_pg_challenge(self, tenant_id: str, channel: str, channel_user_id: str):
        """Nowa metoda używana po udanym challenge – tu tylko logujemy wywołanie i czyścimy pola."""
        key = self.conversation_pk(tenant_id, channel, channel_user_id)
        conv = self.data.get(key, {})
        for field in ("pg_challenge_type", "pg_challenge_attempts", "pg_post_intent", "pg_post_slots"):
            conv.pop(field, None)
        self.cleared_calls.append((tenant_id, channel, channel_user_id))


class FakeTenantsRepo:
    def __init__(self, lang: str = "pl"):
        self.lang = lang

    def get(self, tenant_id: str):
        return {"tenant_id": tenant_id, "language_code": self.lang}


class FakeTemplateService:
    """
    Prosta implementacja TemplateService, która obsługuje tylko
    template'y potrzebne w testach flow PG.
    """

    def __init__(self, default_lang: str = "pl"):
        self.default_lang = default_lang

    def render_named(self, tenant_id: str, template_code: str, language_code: str, ctx: dict):
        # lista zajęć
        if template_code == "pg_available_classes_item":
            idx = ctx.get("index")
            date = ctx.get("date", "?")
            time_ = ctx.get("time", "?")
            name = ctx.get("name", "Zajęcia")
            capacity = ctx.get("capacity", "")
            return f"{idx}. {name} {date} {time_} {capacity}".strip()

        if template_code == "pg_available_classes":
            classes_block = ctx.get("classes", "")
            return "Dostępne zajęcia:\n" + classes_block if classes_block else "Brak dostępnych zajęć."

        if template_code == "pg_available_classes_invalid_index":
            return "Nieprawidłowy numer zajęć (max {max_index}).".format(**ctx)

        # rezerwacja
        if template_code == "reserve_class_confirm":
            return f"Czy potwierdzasz rezerwację zajęć {ctx.get('class_id')}?"

        if template_code == "reserve_class_confirmed":
            return (
                "Rezerwacja potwierdzona: {class_name} "
                "{class_date} {class_time}"
            ).format(**ctx)

        if template_code == "reserve_class_failed":
            return "Nie udało się zarezerwować zajęć."

        if template_code == "reserve_class_declined":
            return "Anulowano rezerwację."

        if template_code == "reserve_class_missing_id":
            return "Nie znam ID zajęć."

        # słowa TAK / NIE do pending rezerwacji
        if template_code == "reserve_class_confirm_words":
            return "tak ok potwierdzam"

        if template_code == "reserve_class_decline_words":
            return "nie rezygnuję"

        # challenge PG
        if template_code == "pg_challenge_success":
            return "Weryfikacja zakończona sukcesem."

        if template_code == "pg_member_balance":
            return f"Twoje saldo to {ctx.get('balance')}."

        if template_code == "pg_member_not_linked":
            return "Nie znaleziono powiązanego członka PG."

        if template_code == "pg_challenge_retry":
            return f"Spróbuj ponownie, pozostało prób: {ctx.get('attempts_left')}."

        if template_code == "pg_challenge_fail_handover":
            return "Nie udało się potwierdzić tożsamości – przekazuję do pracownika."

        if template_code == "handover_to_staff":
            return "Łączę Cię z pracownikiem."

        # fallback – dla innych template'ów zwracamy ich kod (ułatwia debug)
        return template_code


class FakeCRM:
    """
    Bardzo prosty fake CRM – rejestruje wywołania reserve_class
    i zwraca stałe dane dla salda.
    """

    def __init__(self):
        self.reservations: list[dict] = []
        self.verify_calls: list[dict] = []

    def get_available_classes(self, tenant_id: str, club_id=None, from_iso=None, to_iso=None,
                              member_id=None, fields=None, top=None):
        return {
            "value": [
                {
                    "id": "CLASS-1",
                    "startDate": "2025-11-23T10:00:00+01:00",
                    "attendeesCount": 3,
                    "attendeesLimit": 10,
                    "classType": {"name": "Zumba"},
                }
            ]
        }

    def reserve_class(self, tenant_id: str, member_id: str, class_id: str, idempotency_key: str, comments: str):
        self.reservations.append(
            {
                "tenant_id": tenant_id,
                "member_id": member_id,
                "class_id": class_id,
                "idem": idempotency_key,
                "comments": comments,
            }
        )
        return {"ok": True}

    def get_member_balance(self, tenant_id: str, member_id: int):
        return {"balance": 123.45}

    def get_contracts_by_email_and_phone(self, tenant_id: str, email: str, phone_number: str):
        return {"value": []}

    # używane w _verify_challenge_answer
    def verify_member_challenge(self, tenant_id: str, phone: str, challenge_type: str, answer: str) -> bool:
        self.verify_calls.append(
            {
                "tenant_id": tenant_id,
                "phone": phone,
                "challenge_type": challenge_type,
                "answer": answer,
            }
        )
        # w tych testach nie wywołujemy bezpośrednio tej metody (symulujemy już zweryfikowaną rozmowę),
        # ale zostawiamy prosty stub na przyszłość
        return True
    
    def get_member_by_phone(self, tenant_id: str, phone: str) -> dict:
        return {"value":[]}

class FakeMembersIndex:
    def __init__(self, member_id: str = "999"):
        self.member_id = member_id
        self.calls: list[dict] = []

    def get_member(self, tenant_id: str, phone: str):
        self.calls.append({"tenant_id": tenant_id, "phone": phone})
        return {"id": self.member_id}


def _build_router() -> tuple[RoutingService, InMemoryConversations]:
    router = RoutingService()
    conv = InMemoryConversations()
    router.conv = conv
    router.tenants = FakeTenantsRepo(lang="pl")
    router.tpl = FakeTemplateService()
    router.crm = FakeCRM()
    router.members_index = FakeMembersIndex()
    return router, conv


def test_pg_available_classes_sets_state_and_pending(mock_ai, monkeypatch):
    """
    Wiadomość o dostępnych zajęciach:
    - zwraca listę zajęć,
    - zapisuje listę w pending (DDB) pod kluczem pending#<phone>,
    - ustawia state_machine_status=awaiting_class_selection.
    """
    router, conv = _build_router()

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
    assert stored_conv["last_intent"] == "pg_available_classes"
    assert stored_conv["state_machine_status"] == "awaiting_class_selection"


def test_class_selection_creates_pending_reservation_without_challenge(mock_ai):
    """
    Mając listę zajęć i zweryfikowane konto PG:
    - wybór numeru zajęć '1' tworzy pending rezerwację,
    - użytkownik dostaje prośbę o potwierdzenie.
    """
    router, conv = _build_router()

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
        "pg_verification_level": "strong",
        "pg_verified_until": int(time.time()) + 60,
        "pg_member_id": "222",
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


def test_pending_reservation_confirmation_yes_triggers_crm_and_clears_pending(mock_ai):
    """
    Jeśli istnieje pending rezerwacja i użytkownik odpowie słowem z listy 'TAK':
    - RoutingService woła CRM.reserve_class,
    - pending zostaje usunięty,
    - użytkownik dostaje komunikat o potwierdzeniu.
    """
    router, conv = _build_router()
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
      przez clear_pg_challenge.
    """
    router, conv = _build_router()
    crm: FakeCRM = router.crm  # type: ignore[assignment]

    # zamiast pełnej integracji verify_member_challenge, patchujemy helper w RoutingService
    monkeypatch.setattr(
        "src.services.routing_service.RoutingService._verify_challenge_answer",
        lambda self, tenant_id, phone, challenge_type, answer: True,
    )

    tenant_id = "tenantA"
    phone = "whatsapp:+48123123123"
    channel = "whatsapp"
    channel_user_id = phone

    key = conv.conversation_pk(tenant_id, channel, channel_user_id)
    conv.data[key] = {
        "language_code": "pl",
        "state_machine_status": "awaiting_challenge",
        "pg_challenge_type": "dob",
        "pg_challenge_attempts": 0,
        "pg_post_intent": "pg_member_balance",
        "pg_post_slots": {},
        "pg_verification_level": "none",
        "pg_verified_until": 0,
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
    assert stored_conv["pg_verification_level"] == "strong"
    assert stored_conv["pg_member_id"] == "999"

    # 3) clear_pg_challenge zostało wywołane i pola zostały wyczyszczone
    assert (tenant_id, channel, channel_user_id) in conv.cleared_calls
    for field in ("pg_challenge_type", "pg_challenge_attempts", "pg_post_intent", "pg_post_slots"):
        assert field not in stored_conv
