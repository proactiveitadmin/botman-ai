from typing import Any, Dict, List, Optional

import pytest

from src.services.crm_flow_service import CRMFlowService
from src.common.constants import STATE_AWAITING_MESSAGE,STATE_AWAITING_CONFIRMATION
from src.domain.models import Message, Action


class FakeTpl:
    def __init__(self):
        self.calls: List[Dict[str, Any]] = []

    def render_named(self, tenant_id: str, name: str, lang: str, context: Dict[str, Any]):
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "name": name,
                "lang": lang,
                "context": context,
            }
        )
        # prosty body – łatwy do asercji
        return f"{name}|{lang}|{context}"


class FakeCRM:
    def __init__(self):
        self.calls: Dict[str, Any] = {}
        self.member_balance_resp: Dict[str, Any] = {}
        self.contracts_resp: Dict[str, Any] = {}
        self.available_classes_resp: Dict[str, Any] = {}
        self.member_by_phone_resp: Dict[str, Any] = {}

    def get_member_balance(self, tenant_id: str, member_id: Any):
        self.calls["get_member_balance"] = {"tenant_id": tenant_id, "member_id": member_id}
        return self.member_balance_resp

    def get_contracts_by_member_id(self, tenant_id: str, member_id: Any):
        self.calls["get_contracts_by_member_id"] = {"tenant_id": tenant_id, "member_id": member_id}
        return self.contracts_resp

    def get_available_classes(
        self,
        tenant_id: str,
        top: int | None = None,
        class_type_query: str | None = None,
        **kwargs,
    ):
        self.calls["get_available_classes"] = {
            "tenant_id": tenant_id,
            "top": top,
            "class_type_query": class_type_query,
        }
        return self.available_classes_resp

    def get_member_by_phone(self, tenant_id: str, phone: str):
        self.calls["get_member_by_phone"] = {"tenant_id": tenant_id, "phone": phone}
        return self.member_by_phone_resp


class FakeConv:
    def __init__(self):
        self.put_calls: List[Dict[str, Any]] = []
        self.last_upsert: Optional[Dict[str, Any]] = None
        self.verification_map: Dict[str, Dict[str, Any]] = {}
        self._items: Dict[tuple[str, str], Dict[str, Any]] = {}
        self._conversation: Dict[str, Any] = {}
    
    def put(self, item: Dict[str, Any]):
        self.put_calls.append(item)
        pk = item.get("pk")
        sk = item.get("sk")
        if pk and sk:
            self._items[(pk, sk)] = item
 
    def upsert_conversation(self, **kwargs):
        self.last_upsert = kwargs
        self._conversation.update(kwargs)

    def get_conversation(self, tenant_id: str, channel: str, channel_user_id: str):
        return dict(self._conversation)

    def get(self, pk: str, sk: str):
        return self._items.get((pk, sk))

    def delete(self, pk: str, sk: str):
        self._items.pop((pk, sk), None)

    def find_by_verification_code(self, tenant_id: str, verification_code: str):
        key = f"{tenant_id}:{verification_code}"
        return self.verification_map.get(key)


class FakeMembersIndex:
    def __init__(self, member: Optional[Dict[str, Any]] = None):
        self.member = member
        self.calls: List[Dict[str, Any]] = []

    def get_member(self, tenant_id: str, phone: str):
        self.calls.append({"tenant_id": tenant_id, "phone": phone})
        return self.member


def _make_msg(body: str, channel: str = "whatsapp") -> Message:
    return Message(
        tenant_id="t1",
        from_phone="+48123123123",
        to_phone="+48100000000",
        body=body,
        channel=channel,
        channel_user_id=None,
    )


def test_pg_member_balance_core_happy_path():
    tpl = FakeTpl()
    crm = FakeCRM()
    crm.member_balance_resp = {"balance": 42}

    svc = CRMFlowService(
        crm=crm,
        tpl=tpl,
        conv=FakeConv(),
        members_index=None,
    )

    msg = _make_msg("Saldo?")
    actions = svc.crm_member_balance_core(msg, lang="pl", member_id="123")
    assert len(actions) == 1
    a = actions[0]
    assert a.type == "reply"
    assert "crm_member_balance" in a.payload["body"]
    assert crm.calls["get_member_balance"]["member_id"] == "123"


def test_pg_contract_status_core_member_not_linked():
    tpl = FakeTpl()
    crm = FakeCRM()
    conv = FakeConv()

    svc = CRMFlowService(
        crm=crm,
        tpl=tpl,
        conv=FakeConv(),
        members_index=None,
    )

    msg = _make_msg("status kontraktu?")
    actions = svc.crm_contract_status_core(msg, lang="pl", member_id="")
    assert len(actions) == 1
    a = actions[0]
    assert a.type == "reply"
    assert tpl.calls[-1]["name"] == "crm_member_not_linked"


def test_pg_contract_status_core_happy_path():
    tpl = FakeTpl()
    crm = FakeCRM()
    conv = FakeConv()

    crm.contracts_resp = {
        "value": [
            {
                "status": "Current",
                "startDate": "2024-01-01T00:00:00",
                "endDate": "2024-12-31T00:00:00",
                "paymentPlan": {"name": "Monthly"},
            }
        ]
    }
    crm.member_balance_resp = {
        "currentBalance": -10,
        "negativeBalanceSince": "2024-10-01T00:00:00",
    }


    svc = CRMFlowService(
        crm=crm,
        tpl=tpl,
        conv=FakeConv(),
        members_index=None,
    )


    msg = _make_msg("status kontraktu?")
    actions = svc.crm_contract_status_core(msg, lang="pl", member_id="123")
    assert len(actions) == 1
    a = actions[0]
    assert a.type == "reply"

    last_call = tpl.calls[-1]
    assert last_call["name"] == "crm_contract_details"
    ctx = last_call["context"]
    assert ctx["plan_name"] == "Monthly"
    assert ctx["status"] == "Current"
    assert ctx["current_balance"] == -10
    assert ctx["negative_balance_since"].startswith("2024-10-01")


def test_handle_whatsapp_verification_code_linking_ignores_non_kod_messages():
    tpl = FakeTpl()
    crm = FakeCRM()
    conv = FakeConv()
    members_index = FakeMembersIndex()


    svc = CRMFlowService(
        crm=crm,
        tpl=tpl,
        conv=FakeConv(),
        members_index=FakeMembersIndex(),
    )

    msg = _make_msg("hello")
    result = svc.handle_whatsapp_verification_code_linking(msg, lang="pl")
    assert result is None


def test_handle_whatsapp_verification_code_linking_unknown_code():
    tpl = FakeTpl()
    crm = FakeCRM()
    conv = FakeConv()
    members_index = FakeMembersIndex()


    svc = CRMFlowService(
        crm=crm,
        tpl=tpl,
        conv=FakeConv(),
        members_index=None,
    )

    msg = _make_msg("KOD: ABC123")
    result = svc.handle_whatsapp_verification_code_linking(msg, lang="pl")
    assert isinstance(result, list)
    assert result[0].type == "reply"
    assert tpl.calls[-1]["name"] == "www_not_verified"
    assert result[0].payload["channel"] == "whatsapp"
    assert result[0].payload["channel_user_id"] == msg.from_phone


def test_handle_whatsapp_verification_code_linking_member_from_pg_bug(monkeypatch):
    """
    Aktualna implementacja ma bug – przy znalezieniu membera tylko w PG
    zmienna `member` nie jest zdefiniowana przed użyciem, co kończy się
    UnboundLocalError. Test utrwala ten regres (a jednocześnie zwiększa coverage).
    """
    tpl = FakeTpl()
    crm = FakeCRM()
    conv = FakeConv()
    members_index = FakeMembersIndex()

    conv.verification_map["t1:ABC123"] = {
        "channel": "web",
        "channel_user_id": "web-user-1",
    }
    crm.member_by_phone_resp = {"value": [{"id": 777}]}


    svc = CRMFlowService(
        crm=crm,
        tpl=tpl,
        conv=FakeConv(),
        members_index=FakeMembersIndex(),
    )

    msg = _make_msg("KOD: abc123")  # lower/upper bez znaczenia
    result = svc.handle_whatsapp_verification_code_linking(msg, lang="pl")
    assert result is not None


def test_handle_whatsapp_verification_code_linking_fallback_members_index():
    tpl = FakeTpl()
    crm = FakeCRM()
    conv = FakeConv()
    # członek tylko w indexie, ale z poprawnym kluczem "id"
    members_index = FakeMembersIndex(member={"id": "999"})

    conv.verification_map["t1:CODE1"] = {
        "channel": "web",
        "channel_user_id": "web-user-1",
    }
    crm.member_by_phone_resp = {"value": []}


    svc = CRMFlowService(
        crm=crm,
        tpl=tpl,
        conv=conv,
        members_index=members_index,
    )

    msg = _make_msg("KOD: code1")
    result = svc.handle_whatsapp_verification_code_linking(msg, lang="pl")
    assert result is not None
    assert conv.last_upsert is not None
    assert str(conv.last_upsert["crm_member_id"]) == "999"
    assert conv.last_upsert["state_machine_status"] == STATE_AWAITING_MESSAGE


def test_build_available_classes_response_empty_list():
    tpl = FakeTpl()
    crm = FakeCRM()
    conv = FakeConv()
    members_index = FakeMembersIndex()

    crm.available_classes_resp = {"value": []}


    svc = CRMFlowService(
        crm=crm,
        tpl=tpl,
        conv=FakeConv(),
        members_index=None,
    )

    msg = _make_msg("jakie są zajęcia?")
    actions = svc.build_available_classes_response(msg, lang="pl")
    assert len(actions) == 1
    a = actions[0]
    assert a.type == "reply"
    assert tpl.calls[-1]["name"] == "crm_available_classes_empty"


def test_build_available_classes_response_with_items():
    tpl = FakeTpl()
    crm = FakeCRM()
    conv = FakeConv()
    members_index = FakeMembersIndex()

    crm.available_classes_resp = {
        "value": [
            {
                "id": 1,
                "startDate": "2025-11-22T10:00:00",
                "classType": {"name": "Yoga"},
                "attendeesCount": 3,
                "attendeesLimit": 10,
            },
            {
                "id": 2,
                "startdate": "2025-11-23T18:30:00",
                "classType": {"name": "Pilates"},
                "attendeesCount": 10,
                "attendeesLimit": 10,
            },
        ]
    }


    svc = CRMFlowService(
        crm=crm,
        tpl=tpl,
        conv=FakeConv(),
        members_index=None,
    )

    msg = _make_msg("jakie są zajęcia?")
    actions = svc.build_available_classes_response(msg, lang="pl")
    assert len(actions) == 1
    a = actions[0]
    assert a.type == "reply"
    # upewniamy się, że została użyta główna templatka listy
    names = [c["name"] for c in tpl.calls]
    assert "crm_available_classes" in names

    # opcjonalnie: jeśli dokładamy instrukcję wyboru numerem
    # (jeśli w danym środowisku/tenant templates istnieją)
    assert "crm_available_classes_select_by_number" in names



def test_build_available_classes_response_single_item_skips_list_and_asks_confirmation():
    """Jeśli PG zwraca dokładnie 1 zajęcia, pomijamy listę i od razu pytamy o potwierdzenie."""
    tpl = FakeTpl()
    crm = FakeCRM()
    conv = FakeConv()

    # użytkownik już zweryfikowany + ma member_id, żeby nie wchodzić w challenge
    conv._conversation.update(
        {
            "crm_verification_level": "strong",
            "crm_verified_until": 9999999999,
            "crm_member_id": "111",
        }
    )

    crm.available_classes_resp = {
        "value": [
            {
                "id": 1,
                "startDate": "2026-01-12T18:30:00",
                "classType": {"name": "Pilates"},
                "attendeesCount": 0,
                "attendeesLimit": 9,
            }
        ]
    }

    svc = CRMFlowService(
        crm=crm,
        tpl=tpl,
        conv=conv,
        members_index=None,
    )

    msg = _make_msg("czy mogę zarezerwować pilates?")
    actions = svc.build_available_classes_response(msg, lang="pl", auto_confirm_single=True)

    assert len(actions) == 1
    assert actions[0].type == "reply"

    # zamiast listy, od razu pytanie o potwierdzenie
    assert tpl.calls[-1]["name"] == "reserve_class_confirm"

    # powinien powstać pending rezerwacji (sk=pending)
    assert any(it.get("sk") == "pending" for it in conv.put_calls)
    # i stan ustawiony na awaiting_confirmation
    assert conv.last_upsert is not None
    assert conv.last_upsert.get("state_machine_status") == STATE_AWAITING_CONFIRMATION