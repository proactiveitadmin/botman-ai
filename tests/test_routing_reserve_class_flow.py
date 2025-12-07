import time

import pytest

from src.services.routing_service import (
    RoutingService,
    STATE_AWAITING_CLASS_SELECTION,
    STATE_AWAITING_CONFIRMATION,
)
from src.domain.models import Message


class FakeNLUService:
    def __init__(self):
        self.calls = []

    def classify_intent(self, text: str, lang: str):
        self.calls.append((text, lang))
        # pierwsza wiadomość -> rezerwacja zajęć
        if "zapis" in text.lower() or "zaję" in text.lower():
            return {"intent": "reserve_class", "slots": {}, "confidence": 0.99}
        # cała reszta jako clarify (dla "1" nie powinno się w ogóle wywołać)
        return {"intent": "clarify", "slots": {}, "confidence": 0.99}


class FakeTemplateService:
    def __init__(self):
        self.calls = []

    def render_named(self, tenant_id: str, template_name: str, lang: str | None, ctx: dict):
        self.calls.append((tenant_id, template_name, lang, ctx))
        # W treści zwracamy nazwę templata, żeby łatwo asertować:
        return f"{template_name}|{ctx}"


class FakeCRMService:
    def __init__(self):
        self.reserve_calls = []
        self.available_classes_calls = []

    def get_available_classes(self, tenant_id: str, top: int = 10):
        self.available_classes_calls.append((tenant_id, top))
        # 2 przykładowe zajęcia
        return {
            "value": [
                {
                    "id": "class-1",
                    "startDate": "2025-01-01T10:00:00",
                    "classType": {"name": "Joga"},
                    "attendeesCount": 0,
                    "attendeesLimit": 10,
                },
                {
                    "id": "class-2",
                    "startDate": "2025-01-02T11:00:00",
                    "classType": {"name": "Crossfit"},
                    "attendeesCount": 5,
                    "attendeesLimit": 5,
                },
            ]
        }

    def reserve_class(self, tenant_id: str, member_id: str, class_id: str, idempotency_key: str, comments: str):
        self.reserve_calls.append(
            {
                "tenant_id": tenant_id,
                "member_id": member_id,
                "class_id": class_id,
                "idempotency_key": idempotency_key,
                "comments": comments,
            }
        )
        return {"ok": True}


class FakeTenantsRepo:
    def get(self, tenant_id: str):
        # domyślny język „pl”
        return {"language_code": "pl"}


class FakeConversationsRepo:
    """
    Bardzo prosty in-memory odpowiednik ConversationsRepo.
    Wystarcza na potrzeby testu (bez DynamoDB).
    """

    def __init__(self):
        self.convs: dict[tuple[str, str, str], dict] = {}
        self.items: dict[tuple[str, str], dict] = {}

    # --- rozmowy ---

    def get_conversation(self, tenant_id: str, channel: str, channel_user_id: str):
        return self.convs.get((tenant_id, channel, channel_user_id))

    def upsert_conversation(
        self,
        tenant_id: str,
        channel: str,
        channel_user_id: str,
        **fields,
    ):
        key = (tenant_id, channel, channel_user_id)
        conv = self.convs.get(key, {}).copy()
        conv.update(fields)
        conv["updated_at"] = int(time.time())
        self.convs[key] = conv
        return conv

    def assign_agent(self, tenant_id: str, channel: str, channel_user_id: str, agent_id: str):
        pass  # niepotrzebne w tym teście

    def clear_pg_challenge(self, tenant_id: str, channel: str, channel_user_id: str):
        key = (tenant_id, channel, channel_user_id)
        conv = self.convs.get(key, {})
        for k in ["pg_challenge_type", "pg_challenge_attempts", "pg_post_intent", "pg_post_slots"]:
            conv.pop(k, None)
        self.convs[key] = conv

    # --- itemy (pending, classes) ---

    def put(self, item: dict):
        pk = item["pk"]
        sk = item["sk"]
        self.items[(pk, sk)] = item

    def get(self, pk: str, sk: str):
        return self.items.get((pk, sk))

    def delete(self, pk: str, sk: str):
        self.items.pop((pk, sk), None)


class FakeMetricsService:
    pass


class FakeKBService:
    pass


class FakeTicketingService:
    pass


class FakeMessagesRepo:
    pass


class FakeMembersIndexRepo:
    pass


TENANT_ID = "tenant-1"
PHONE = "+48123123123"


@pytest.fixture
def routing_service(monkeypatch):
    nlu = FakeNLUService()
    crm = FakeCRMService()
    tpl = FakeTemplateService()
    conv = FakeConversationsRepo()
    tenants = FakeTenantsRepo()

    # Załóżmy, że user jest już zweryfikowany w PG,
    # żeby nie mieszać do testu całego flow challenge.
    now_ts = int(time.time())
    conv.upsert_conversation(
        TENANT_ID,
        "whatsapp",
        PHONE,
        pg_member_id="member-123",
        pg_verification_level="strong",
        pg_verified_until=now_ts + 3600,
        language_code="pl",
        state_machine_status=None,
    )

    routing = RoutingService(
        nlu=nlu,
        kb=FakeKBService(),
        tpl=tpl,
        metrics=FakeMetricsService(),
        crm=crm,
        ticketing=FakeTicketingService(),
        conv=conv,
        tenants=tenants,
        messages=FakeMessagesRepo(),
        members_index=FakeMembersIndexRepo(),
    )
    monkeypatch.setattr(routing, "_detect_language", lambda text: "pl")
    # udostępniamy fakes na obiekcie do asercji
    routing._test_nlu = nlu
    routing._test_crm = crm
    routing._test_tpl = tpl
    routing._test_conv = conv

    return routing


def _make_msg(text: str) -> Message:
    return Message(
        tenant_id=TENANT_ID,
        from_phone=PHONE,
        to_phone="bot",
        body=text,
        channel="whatsapp",
    )


def test_reserve_class_e2e_list_then_index_selection(routing_service: RoutingService):
    """
    1. Użytkownik: "chcę się zapisać na zajęcia"
    2. Bot: wyświetla listę zajęć (PG)
    3. Użytkownik: "1"
    4. Bot: traktuje to jako wybór zajęć (pending + confirm),
       NIE jako clarify.

    Ten test zabezpiecza buga, w którym po wpisaniu numeru
    flow wpadał w intent 'clarify'.
    """
    routing = routing_service

    # --- Krok 1: user prosi o rezerwację ---
    msg1 = _make_msg("Chciałbym się zapisać na zajęcia")
    actions1 = routing.handle(msg1)

    # NLU powinno zostać wywołane dla pierwszej wiadomości
    assert routing._test_nlu.calls
    text1, lang1 = routing._test_nlu.calls[0]
    assert "zapis" in text1.lower() or "zaję" in text1.lower()

    # Bot powinien odesłać listę zajęć (template pg_available_classes), a nie clarify
    assert len(actions1) == 1
    assert actions1[0].type == "reply"
    body1 = actions1[0].payload["body"]
    assert body1.startswith("pg_available_classes|")

    # Stan rozmowy musi być ustawiony na oczekiwanie wyboru numeru
    conv = routing._test_conv.get_conversation(TENANT_ID, "whatsapp", PHONE)
    assert conv["state_machine_status"] == STATE_AWAITING_CLASS_SELECTION

    # W "pending#phone" musi być zapisany snapshot listy zajęć
    pending_key = routing._pending_key(PHONE)
    classes_item = routing._test_conv.get(pending_key, "classes")
    assert classes_item is not None
    assert len(classes_item["items"]) == 2

    # --- Krok 2: user wpisuje numer z listy ---
    msg2 = _make_msg("1")
    actions2 = routing.handle(msg2)

    # KLUCZOWE: druga wiadomość nie powinna trafić do NLU
    # (stan STATE_AWAITING_CLASS_SELECTION przechwytuje ją wcześniej)
    assert len(routing._test_nlu.calls) == 1, "NLU nie powinno być wywołane dla '1'"

    # Bot powinien zainicjować pending rezerwację (template reserve_class_confirm)
    assert len(actions2) == 1
    assert actions2[0].type == "reply"
    body2 = actions2[0].payload["body"]
    assert body2.startswith("reserve_class_confirm|")

    # Stan rozmowy => oczekiwanie na TAK/NIE
    conv2 = routing._test_conv.get_conversation(TENANT_ID, "whatsapp", PHONE)
    assert conv2["state_machine_status"] == STATE_AWAITING_CONFIRMATION

    # W storage powinna istnieć pending rezerwacja dla class-1 i member-123
    pending_item = routing._test_conv.get(pending_key, "pending")
    assert pending_item is not None
    assert pending_item["class_id"] == "class-1"
    assert pending_item["member_id"] == "member-123"
