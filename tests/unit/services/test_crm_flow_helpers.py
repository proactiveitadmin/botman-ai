from types import SimpleNamespace
import time

import pytest

import src.services.crm_flow_service as cfs
from src.common.constants import (
    DEFAULT_CHANNEL,
    WEB_CHANNEL,
    STATE_AWAITING_CONFIRMATION,
    STATE_AWAITING_MESSAGE,
    STATE_AWAITING_CHALLENGE,
    INTENT_RESERVE_CLASS,
    INTENT_AVAILABLE_CLASSES,
    INTENT_MARKETING_OPTIN,
    INTENT_MARKETING_OPTOUT,
    ENUM_CRM_RETURN_OK,
    ENUM_CRM_RETURN_ALREADY_BOOKED,
)
from src.common.security import otp_hash


class TestableCRMFlowService(cfs.CRMFlowService):
    """Unit-test version: do not depend on domain Action/build_reply_action shape."""

    def _reply(self, msg, lang, body, channel=None, channel_user_id=None):
        return {
            "body": body,
            "language_code": lang,
            "channel": channel or getattr(msg, "channel", None),
            "channel_user_id": channel_user_id or getattr(msg, "channel_user_id", None),
        }


class FakeTpl:
    def __init__(self, mapping=None):
        self.mapping = mapping or {}
        self.calls = []

    def render_named(self, tenant_id, template_name, lang, context):
        ctx = context or {}
        self.calls.append((tenant_id, template_name, lang, ctx))

        value = self.mapping.get((tenant_id, template_name, lang))
        if value is None:
            value = self.mapping.get(template_name)
        if value is None:
            return f"{template_name}:{ctx}"
        if callable(value):
            return value(ctx)
        try:
            return value.format(**ctx)
        except Exception:
            return value


class FakeCRM:
    def __init__(self):
        self.available_classes = []
        self.class_details = {}
        self.reserve_result = ENUM_CRM_RETURN_OK
        self.reserve_calls = []
        self.member_type = "member"
        self.email = "user@example.com"
        self.member_id = "105"
        self.balance = {"currentBalance": 0}
        self.contracts = {"value": []}
        self.marketing_calls = []

    def get_available_classes(self, **kwargs):
        self.last_available_kwargs = kwargs
        return {"value": self.available_classes}

    def get_class_by_id(self, tenant_id, class_id):
        return self.class_details.get(class_id, {})

    def reserve_class(self, **kwargs):
        self.reserve_calls.append(kwargs)
        return self.reserve_result

    def get_member_type_by_phone(self, tenant_id, phone):
        return self.member_type

    def get_email_by_msg(self, tenant_id, msg):
        return self.email

    def get_member_id_by_msg(self, tenant_id, msg):
        return self.member_id

    def get_member_balance(self, **kwargs):
        return self.balance

    def get_contracts_by_member_id(self, **kwargs):
        return self.contracts

    def grant_marketing_consent_for_member(self, **kwargs):
        self.marketing_calls.append(("grant", kwargs))

    def revoke_marketing_consent_for_member(self, **kwargs):
        self.marketing_calls.append(("revoke", kwargs))


class FakeConv:
    def __init__(self, conversation=None):
        self.items = {}
        self.upserts = []
        self.deleted = []
        self.conversation = dict(conversation or {})
        self.cleared = []

    def put(self, *args, **kwargs):
        if len(args) == 1 and isinstance(args[0], dict):
            item = dict(args[0])
            self.items[(item["pk"], item["sk"])] = item
            return
        if len(args) == 3:
            pk, sk, item = args
            self.items[(pk, sk)] = {"pk": pk, "sk": sk, **dict(item)}
            return
        raise AssertionError(f"Unexpected put args={args!r} kwargs={kwargs!r}")

    def get(self, pk, sk):
        return self.items.get((pk, sk))

    def delete(self, pk, sk):
        self.deleted.append((pk, sk))
        self.items.pop((pk, sk), None)

    def upsert_conversation(self, **kwargs):
        self.upserts.append(kwargs)
        self.conversation.update(kwargs)

    def get_conversation(self, tenant_id, channel, channel_user_id):
        return dict(self.conversation)

    def clear_crm_challenge(self, tenant_id, channel, channel_user_id):
        self.cleared.append((tenant_id, channel, channel_user_id))


@pytest.fixture(autouse=True)
def patch_unit_dependencies(monkeypatch):
    monkeypatch.setattr(cfs, "ClientsFactory", lambda *a, **k: object())


@pytest.fixture
def msg():
    return SimpleNamespace(
        tenant_id="t1",
        from_phone="whatsapp:+48111111111",
        channel=DEFAULT_CHANNEL,
        channel_user_id="whatsapp:+48111111111",
        body="",
        conversation_id=None,
    )


def action_body(action):
    assert isinstance(action, dict), f"Expected test reply dict, got: {type(action)!r} {action!r}"
    return action["body"]


def make_service(*, tpl=None, crm=None, conv=None):
    return TestableCRMFlowService(
        crm=crm or FakeCRM(),
        tpl=tpl or FakeTpl(),
        conv=conv or FakeConv(),
    )


def test_get_words_set_splits_and_caches():
    tpl = FakeTpl({("t1", "yes_words", "pl"): "TAK,  yes ; ok"})
    svc = make_service(tpl=tpl)

    words1 = svc._get_words_set("t1", "yes_words", "pl")
    assert words1 == {"tak", "yes", "ok"}

    words2 = svc._get_words_set("t1", "yes_words", "pl")
    assert words2 == words1
    assert [c[:3] for c in tpl.calls].count(("t1", "yes_words", "pl")) == 1


def test_pending_key_and_channel_context_defaults(msg):
    msg.channel = None
    msg.channel_user_id = None
    svc = make_service()

    assert svc._pending_key("whatsapp:+48123") == "pending#whatsapp:+48123"
    assert svc._channel_ctx(msg) == (DEFAULT_CHANNEL, msg.from_phone)


def test_reserve_class_with_id_core_stores_pending_and_sets_confirmation_state(msg):
    tpl = FakeTpl({"reserve_class_confirm": "Czy potwierdzasz {class_name} {class_date} {class_time}?"})
    conv = FakeConv()
    svc = make_service(tpl=tpl, conv=conv)

    actions = svc.reserve_class_with_id_core(
        msg,
        "pl",
        class_id="77",
        member_id="105",
        class_meta={"class_name": "Pilates", "class_date": "2026-06-10", "class_time": "18:00"},
    )

    pending = conv.get("pending#whatsapp:+48111111111", "pending")
    assert pending["class_id"] == "77"
    assert pending["member_id"] == "105"
    assert pending["class_name"] == "Pilates"
    assert pending["idempotency_key"].startswith("idem-")
    assert conv.upserts[-1]["state_machine_status"] == STATE_AWAITING_CONFIRMATION
    assert conv.upserts[-1]["last_intent"] == INTENT_RESERVE_CLASS
    assert "Pilates" in action_body(actions[0])


def test_build_available_classes_response_empty(msg):
    crm = FakeCRM()
    crm.available_classes = []
    tpl = FakeTpl({"crm_available_classes_empty": "Brak zajęć"})
    svc = make_service(crm=crm, tpl=tpl)

    actions = svc.build_available_classes_response(msg, "pl")

    assert action_body(actions[0]) == "Brak zajęć"


def test_build_available_classes_response_lists_and_saves_selection(msg):
    crm = FakeCRM()
    crm.available_classes = [
        {
            "id": "101",
            "startDate": "2026-06-10T18:30:00",
            "classType": {"name": "Pilates"},
            "attendeesCount": 3,
            "attendeesLimit": 10,
        },
        {
            "id": "102",
            "startDate": "2026-06-11T19:00:00",
            "classType": {"name": "Yoga"},
            "attendeesCount": 10,
            "attendeesLimit": 10,
        },
    ]
    conv = FakeConv()
    tpl = FakeTpl({
        "crm_available_classes_capacity_free": "{free}/{limit} wolnych",
        "crm_available_classes_capacity_full": "brak miejsc ({limit})",
        INTENT_AVAILABLE_CLASSES: "Zajęcia:\n{classes}",
        "crm_available_classes_item": "{index}. {date} {time} {name} [{capacity}]",
        "crm_available_classes_select_by_number": "Odpisz numerem.",
    })
    svc = make_service(crm=crm, tpl=tpl, conv=conv)

    actions = svc.build_available_classes_response(msg, "pl", auto_confirm_single=False)

    body = action_body(actions[0])
    assert "1. 2026-06-10 18:30 Pilates [7/10 wolnych]" in body
    assert "2. 2026-06-11 19:00 Yoga [brak miejsc (10)]" in body
    assert "Odpisz numerem." in body

    classes = conv.get("pending#whatsapp:+48111111111", "classes")
    assert classes["items"] == [
        {"index": 1, "class_id": "101", "date": "2026-06-10", "time": "18:30", "name": "Pilates", "start": "2026-06-10T18:30:00"},
        {"index": 2, "class_id": "102", "date": "2026-06-11", "time": "19:00", "name": "Yoga", "start": "2026-06-11T19:00:00"},
    ]


def test_build_available_classes_response_does_not_save_selection_when_disallowed(msg):
    crm = FakeCRM()
    crm.available_classes = [
        {"id": "101", "startDate": "2026-06-10T18:30:00", "classType": {"name": "Pilates"}},
    ]
    conv = FakeConv()
    tpl = FakeTpl({
        "crm_available_classes_capacity_no_limit": "bez limitu",
        INTENT_AVAILABLE_CLASSES: "Zajęcia:\n{classes}",
        "crm_available_classes_item": "{index}. {name}",
    })
    svc = make_service(crm=crm, tpl=tpl, conv=conv)

    actions = svc.build_available_classes_response(msg, "pl", allow_selection=False)

    assert "1. Pilates" in action_body(actions[0])
    assert conv.get("pending#whatsapp:+48111111111", "classes") is None


def test_handle_class_selection_invalid_index(msg):
    conv = FakeConv()
    conv.put({
        "pk": "pending#whatsapp:+48111111111",
        "sk": "classes",
        "items": [{"index": 1, "class_id": "101", "date": "2026-06-10", "time": "18:30", "name": "Pilates"}],
    })
    tpl = FakeTpl({"crm_available_classes_invalid_index": "Wybierz numer 1-{max_index}"})
    svc = make_service(conv=conv, tpl=tpl)
    msg.body = "2"

    actions = svc.handle_class_selection(msg, "pl")

    assert action_body(actions[0]) == "Wybierz numer 1-1"


def test_handle_class_selection_by_number_starts_reservation(msg):
    conv = FakeConv({"crm_verification_level": "strong", "crm_verified_until": int(time.time()) + 3600, "crm_member_id": "105"})
    conv.put({
        "pk": "pending#whatsapp:+48111111111",
        "sk": "classes",
        "items": [{"index": 1, "class_id": "101", "date": "2026-06-10", "time": "18:30", "name": "Pilates"}],
    })
    tpl = FakeTpl({"reserve_class_confirm": "Potwierdź {class_name}"})
    svc = make_service(conv=conv, tpl=tpl)
    msg.body = "nr 1"

    actions = svc.handle_class_selection(msg, "pl")

    assert "Potwierdź Pilates" in action_body(actions[0])
    pending = conv.get("pending#whatsapp:+48111111111", "pending")
    assert pending["class_id"] == "101"
    assert pending["member_id"] == "105"


def test_handle_pending_confirmation_reserves_class_on_confirm(msg):
    crm = FakeCRM()
    crm.reserve_result = ENUM_CRM_RETURN_OK
    conv = FakeConv()
    conv.put({
        "pk": "pending#whatsapp:+48111111111",
        "sk": "pending",
        "class_id": "101",
        "member_id": "105",
        "idempotency_key": "idem-1",
        "class_name": "Pilates",
        "class_date": "2026-06-10",
        "class_time": "18:30",
    })
    tpl = FakeTpl({"confirm_words": "tak, ok", "reserve_class_confirmed": "Zarezerwowano {class_name}"})
    svc = make_service(crm=crm, conv=conv, tpl=tpl)
    msg.body = "tak"

    actions = svc.handle_pending_confirmation(msg, "pl")

    assert crm.reserve_calls == [{
        "tenant_id": "t1",
        "member_id": "105",
        "class_id": "101",
        "idempotency_key": "idem-1",
        "comments": "booked on whatsapp",
    }]
    assert ("pending#whatsapp:+48111111111", "pending") in conv.deleted
    assert action_body(actions[0]) == "Zarezerwowano Pilates"


def test_handle_pending_confirmation_returns_already_booked(msg):
    crm = FakeCRM()
    crm.reserve_result = ENUM_CRM_RETURN_ALREADY_BOOKED
    conv = FakeConv()
    conv.put({"pk": "pending#whatsapp:+48111111111", "sk": "pending", "class_id": "101", "member_id": "105", "idempotency_key": "idem-1"})
    tpl = FakeTpl({"confirm_words": "tak", "reserve_class_already_booked": "Już masz rezerwację"})
    svc = make_service(crm=crm, conv=conv, tpl=tpl)
    msg.body = "tak"

    actions = svc.handle_pending_confirmation(msg, "pl")

    assert action_body(actions[0]) == "Już masz rezerwację"


def test_handle_pending_confirmation_declines_on_non_confirm(msg):
    conv = FakeConv()
    conv.put({"pk": "pending#whatsapp:+48111111111", "sk": "pending", "class_id": "101"})
    tpl = FakeTpl({"confirm_words": "tak", "reserve_class_declined": "Anulowano"})
    svc = make_service(conv=conv, tpl=tpl)
    msg.body = "nie"

    actions = svc.handle_pending_confirmation(msg, "pl")

    assert ("pending#whatsapp:+48111111111", "pending") in conv.deleted
    assert action_body(actions[0]) == "Anulowano"


def test_handle_pending_marketing_optin_confirm_grants_consent_after_existing_verification(msg):
    crm = FakeCRM()
    conv = FakeConv({"crm_verification_level": "strong", "crm_verified_until": int(time.time()) + 3600, "crm_member_id": "105"})
    conv.put("pending#whatsapp:+48111111111", "pending", {"kind": INTENT_MARKETING_OPTIN, "member_id": "105"})
    tpl = FakeTpl({"confirm_words": "tak", "system_marketing_optin_done": "Zgoda zapisana"})
    svc = make_service(crm=crm, conv=conv, tpl=tpl)
    msg.body = "tak"

    actions = svc.handle_pending_confirmation(msg, "pl")

    assert crm.marketing_calls[0][0] == "grant"
    assert crm.marketing_calls[0][1]["member_id"] == "105"
    assert ("pending#whatsapp:+48111111111", "pending") in conv.deleted
    assert action_body(actions[0]) == "Zgoda zapisana"


def test_handle_pending_marketing_optout_confirm_revokes_consent_after_existing_verification(msg):
    crm = FakeCRM()
    conv = FakeConv({"crm_verification_level": "strong", "crm_verified_until": int(time.time()) + 3600, "crm_member_id": "105"})
    conv.put("pending#whatsapp:+48111111111", "pending", {"kind": INTENT_MARKETING_OPTOUT, "member_id": "105"})
    tpl = FakeTpl({"confirm_words": "tak", "system_marketing_optout_done": "Zgoda cofnięta"})
    svc = make_service(crm=crm, conv=conv, tpl=tpl)
    msg.body = "tak"

    actions = svc.handle_pending_confirmation(msg, "pl")

    assert crm.marketing_calls[0][0] == "revoke"
    assert action_body(actions[0]) == "Zgoda cofnięta"


def test_handle_pending_marketing_non_confirm_cancels(msg):
    conv = FakeConv()
    conv.put("pending#whatsapp:+48111111111", "pending", {"kind": INTENT_MARKETING_OPTIN, "member_id": "105"})
    tpl = FakeTpl({"confirm_words": "tak", "system_confirm_cancelled": "Anulowano zmianę"})
    svc = make_service(conv=conv, tpl=tpl)
    msg.body = "nie"

    actions = svc.handle_pending_confirmation(msg, "pl")

    assert ("pending#whatsapp:+48111111111", "pending") in conv.deleted
    assert action_body(actions[0]) == "Anulowano zmianę"


def test_ensure_crm_verification_returns_none_when_strong_valid(msg, monkeypatch):
    monkeypatch.setattr(cfs.time, "time", lambda: 1000)
    svc = make_service()

    result = svc.ensure_crm_verification(msg, {"crm_verification_level": "strong", "crm_verified_until": 2000}, "pl")

    assert result is None


def test_ensure_crm_verification_web_channel_returns_not_available(msg):
    msg.channel = WEB_CHANNEL
    msg.channel_user_id = "web-user-1"
    tpl = FakeTpl({"web_crm_not_available": "CRM niedostępny na WWW"})
    svc = make_service(tpl=tpl)

    actions = svc.ensure_crm_verification(msg, {}, "pl")

    assert action_body(actions[0]) == "CRM niedostępny na WWW"


def test_ensure_crm_verification_missing_email_does_not_enter_challenge(msg):
    crm = FakeCRM()
    crm.email = None
    conv = FakeConv()
    tpl = FakeTpl({"crm_challenge_missing_email": "Brak emaila"})
    svc = make_service(crm=crm, conv=conv, tpl=tpl)

    actions = svc.ensure_crm_verification(msg, {}, "pl", post_intent=INTENT_RESERVE_CLASS, post_slots={"class_id": "101"})

    assert action_body(actions[0]) == "Brak emaila"
    assert conv.upserts[-1]["state_machine_status"] == STATE_AWAITING_MESSAGE


def test_ensure_crm_verification_sends_otp_and_sets_challenge_state(msg, monkeypatch):
    monkeypatch.setattr(cfs.time, "time", lambda: 1000)
    monkeypatch.setattr(cfs, "generate_verification_code", lambda length: "ABC123")

    sent = {}

    class FakeEmailClient:
        def send_otp(self, **kwargs):
            sent.update(kwargs)
            return True

    monkeypatch.setattr(cfs, "EmailClient", FakeEmailClient)

    conv = FakeConv()
    tpl = FakeTpl({"crm_code_via_email": "Kod ABC123", "crm_challenge_ask_email_code": "Wpisz kod z {email}"})
    svc = make_service(conv=conv, tpl=tpl)

    actions = svc.ensure_crm_verification(msg, {}, "pl", post_intent=INTENT_RESERVE_CLASS, post_slots={"class_id": "101"})

    assert sent["to_email"] == "user@example.com"
    assert sent["body_text"] == "Kod ABC123"
    assert conv.upserts[-1]["state_machine_status"] == STATE_AWAITING_CHALLENGE
    assert conv.upserts[-1]["crm_otp_hash"] == otp_hash("t1", "crm_email_otp", "ABC123")
    assert conv.upserts[-1]["crm_post_intent"] == INTENT_RESERVE_CLASS
    assert action_body(actions[0]) == "Wpisz kod z user@example.com"


def test_handle_crm_challenge_wrong_otp_decrements_attempts(msg, monkeypatch):
    monkeypatch.setattr(cfs.time, "time", lambda: 1000)
    conv_repo = FakeConv()
    tpl = FakeTpl({"crm_challenge_retry": "Zły kod, zostało {attempts_left}"})
    svc = make_service(conv=conv_repo, tpl=tpl)
    msg.body = "BAD999"
    conv = {"crm_otp_hash": otp_hash("t1", "crm_email_otp", "ABC123"), "crm_otp_expires_at": 2000, "crm_otp_attempts_left": 3}

    actions = svc.handle_crm_challenge(msg, conv, "pl")

    assert conv_repo.upserts[-1]["crm_otp_attempts_left"] == 2
    assert action_body(actions[0]) == "Zły kod, zostało 2"


def test_handle_crm_challenge_correct_otp_sets_strong_verification(msg, monkeypatch):
    monkeypatch.setattr(cfs.time, "time", lambda: 1000)
    crm = FakeCRM()
    crm.member_id = "105"
    conv_repo = FakeConv()
    tpl = FakeTpl({"crm_challenge_success": "OK"})
    svc = make_service(crm=crm, conv=conv_repo, tpl=tpl)
    msg.body = "ABC123"
    conv = {"crm_otp_hash": otp_hash("t1", "crm_email_otp", "ABC123"), "crm_otp_expires_at": 2000, "crm_otp_attempts_left": 3}

    actions = svc.handle_crm_challenge(msg, conv, "pl")

    assert conv_repo.upserts[-1]["state_machine_status"] == STATE_AWAITING_MESSAGE
    assert conv_repo.upserts[-1]["crm_member_id"] == "105"
    assert conv_repo.upserts[-1]["crm_verification_level"] == "strong"
    assert conv_repo.cleared == [("t1", DEFAULT_CHANNEL, "whatsapp:+48111111111")]
    assert action_body(actions[0]) == "OK"


def test_is_crm_member_true_only_for_member(msg):
    crm = FakeCRM()
    svc = make_service(crm=crm)

    crm.member_type = "Member"
    assert svc.is_crm_member("t1", "whatsapp:+481") is True

    crm.member_type = "lead"
    assert svc.is_crm_member("t1", "whatsapp:+481") is False


def test_get_contract_status_context_renders_current_contract(msg):
    crm = FakeCRM()
    crm.contracts = {
        "value": [
            {"status": "Expired", "startDate": "2025-01-01T00:00:00", "paymentPlan": {"name": "Old"}},
            {"status": "Current", "startDate": "2026-01-01T00:00:00", "endDate": "2026-12-31T00:00:00", "paymentPlan": {"name": "Gold"}},
        ]
    }
    crm.balance = {"currentBalance": -10, "negativeBalanceSince": "2026-05-01T00:00:00"}
    tpl = FakeTpl({"crm_contract_details": "{plan_name}|{status}|{start_date}|{end_date}|{current_balance}|{negative_balance_since}"})
    svc = make_service(crm=crm, tpl=tpl)

    body = svc.get_contract_status_context(msg, "105", "pl")

    assert body == "Gold|Current|2026-01-01|2026-12-31|-10|2026-05-01"


def test_crm_member_balance_core_without_member(msg):
    tpl = FakeTpl({"crm_member_not_linked": "Brak konta"})
    svc = make_service(tpl=tpl)

    actions = svc.crm_member_balance_core(msg, "pl", member_id="")

    assert action_body(actions[0]) == "Brak konta"
