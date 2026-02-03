import pytest

from src.domain.models import Message
from src.services.crm_flow_service import CRMFlowService
from tests.helpers.fakes_routing import InMemoryConversations


class FakeTemplateService:
    """
    Minimalny TemplateService:
    - confirm_words: słowa akceptacji (TAK)
    - decline_words: słowa odmowy (NIE) - dla marketingu nieużywane, ale CRMFlow tego oczekuje dla rezerwacji
    - pozostałe template: zwracamy po prostu nazwę templata dla łatwych asercji
    """
    def render_named(self, tenant_id: str, template_name: str, lang: str | None, ctx: dict):
        if template_name == "confirm_words":
            return "tak yes ok"
        if template_name == "decline_words":
            return "nie no"
        return template_name


class FakeCRMService:
    def __init__(self):
        self.revoke_calls = []
        self.grant_calls = []
        self.raise_not_impl_revoke = False
        self.raise_not_impl_grant = False

    def revoke_marketing_consent_for_member(self, tenant_id: str, *, member_id: int, reason: str | None = None):
        if self.raise_not_impl_revoke:
            raise NotImplementedError("not implemented")
        self.revoke_calls.append({"tenant_id": tenant_id, "member_id": int(member_id), "reason": reason})

    def grant_marketing_consent_for_member(self, tenant_id: str, *, member_id: int, reason: str | None = None):
        if self.raise_not_impl_grant:
            raise NotImplementedError("not implemented")
        self.grant_calls.append({"tenant_id": tenant_id, "member_id": int(member_id), "reason": reason})


@pytest.fixture
def conv():
    return InMemoryConversations()


@pytest.fixture
def tpl():
    return FakeTemplateService()


@pytest.fixture
def crm():
    return FakeCRMService()


@pytest.fixture
def crm_flow(conv, tpl, crm):
    svc = CRMFlowService(crm=crm, tpl=tpl, conv=conv)
    # W tych testach omijamy weryfikację (zakładamy, że jest już zrobiona)
    svc.ensure_crm_verification = lambda *args, **kwargs: None
    return svc


def _setup_conv_with_member(conv: InMemoryConversations, tenant_id: str, phone: str, member_id: int):
    conv.upsert_conversation(
        tenant_id=tenant_id,
        channel="whatsapp",
        channel_user_id=phone,
        crm_member_id=member_id,
    )


def _put_pending(conv: InMemoryConversations, pk: str, kind: str, member_id: int | None = None):
    item = {"pk": pk, "sk": "pending", "kind": kind}
    if member_id is not None:
        item["member_id"] = member_id
    conv.put(item)


def test_marketing_optout_confirm_yes_calls_crm_and_clears_pending(crm_flow, conv, crm):
    tenant_id = "t1"
    phone = "+48123123123"
    member_id = 123

    # stan rozmowy: member podlinkowany
    _setup_conv_with_member(conv, tenant_id, phone, member_id)

    # pending marketing optout
    pk = f"pending#{phone}"
    _put_pending(conv, pk, kind="marketing_optout")

    msg = Message(
        tenant_id=tenant_id,
        from_phone=phone,
        to_phone="bot",
        body="TAK",
        channel="whatsapp",
        channel_user_id=phone,
    )

    actions = crm_flow.handle_pending_confirmation(msg, lang="pl")
    assert actions is not None
    assert len(actions) == 1
    assert actions[0].type == "reply"
    assert actions[0].payload["body"] == "system_marketing_optout_done"

    # CRM called
    assert crm.revoke_calls == [{"tenant_id": tenant_id, "member_id": member_id, "reason": "text_command_confirmed"}]
    assert crm.grant_calls == []

    # pending cleared
    assert conv.get(pk, "pending") is None


def test_marketing_optin_confirm_yes_calls_crm_and_clears_pending(crm_flow, conv, crm):
    tenant_id = "t1"
    phone = "+48123123123"
    member_id = 456

    _setup_conv_with_member(conv, tenant_id, phone, member_id)

    pk = f"pending#{phone}"
    _put_pending(conv, pk, kind="marketing_optin")

    msg = Message(
        tenant_id=tenant_id,
        from_phone=phone,
        to_phone="bot",
        body="tak",
        channel="whatsapp",
        channel_user_id=phone,
    )

    actions = crm_flow.handle_pending_confirmation(msg, lang="pl")
    assert actions is not None
    assert len(actions) == 1
    assert actions[0].payload["body"] == "system_marketing_optin_done"

    assert crm.grant_calls == [{"tenant_id": tenant_id, "member_id": member_id, "reason": "text_command_confirmed"}]
    assert crm.revoke_calls == []

    assert conv.get(pk, "pending") is None


def test_marketing_confirm_anything_else_cancels_and_clears_pending(crm_flow, conv, crm):
    tenant_id = "t1"
    phone = "+48123123123"
    member_id = 789

    _setup_conv_with_member(conv, tenant_id, phone, member_id)

    pk = f"pending#{phone}"
    _put_pending(conv, pk, kind="marketing_optout")

    msg = Message(
        tenant_id=tenant_id,
        from_phone=phone,
        to_phone="bot",
        body="hmm nie jestem pewien",
        channel="whatsapp",
        channel_user_id=phone,
    )

    actions = crm_flow.handle_pending_confirmation(msg, lang="pl")
    assert actions is not None
    assert len(actions) == 1
    assert actions[0].payload["body"] == "system_confirm_cancelled"

    # no CRM calls
    assert crm.revoke_calls == []
    assert crm.grant_calls == []

    # pending cleared
    assert conv.get(pk, "pending") is None


def test_marketing_confirm_yes_when_pg_update_not_implemented_returns_failed_and_clears_pending(crm_flow, conv, crm):
    tenant_id = "t1"
    phone = "+48123123123"
    member_id = 111

    _setup_conv_with_member(conv, tenant_id, phone, member_id)

    pk = f"pending#{phone}"
    _put_pending(conv, pk, kind="marketing_optout")

    crm.raise_not_impl_revoke = True

    msg = Message(
        tenant_id=tenant_id,
        from_phone=phone,
        to_phone="bot",
        body="tak",
        channel="whatsapp",
        channel_user_id=phone,
    )

    actions = crm_flow.handle_pending_confirmation(msg, lang="pl")
    assert actions is not None
    assert len(actions) == 1
    assert actions[0].payload["body"] == "system_marketing_change_failed"

    # pending cleared even on error
    assert conv.get(pk, "pending") is None
