import pytest

from src.services.campaign_service import CampaignService


class FakeTemplates:
    def render(self, template, ctx):
        return f"TEMPLATE:{template}:{ctx}"


class FakeConversations:
    def __init__(self, conv=None):
        self.conv = conv

    def get_conversation(self, tenant_id, channel, channel_user_id):
        return self.conv


class FakeTenants:
    def __init__(self, tenant=None):
        self.tenant = tenant or {}

    def get(self, tenant_id):
        return self.tenant
        
    def get_language(self, tenant_id: str):
         return self.tenant["language_code"]


def make_service(conv=None, tenant=None):
    return CampaignService(
        template_service=FakeTemplates(),
        conversations_repo=FakeConversations(conv),
        tenants_repo=FakeTenants(tenant),
    )


def test_build_message_renders_body_with_context():
    svc = make_service(tenant={"language_code": "pl"})

    msg = svc.build_message(
        campaign={
            "campaign_id": "camp-birthday-template",
            "body": "campaign_birthday",
        },
        tenant_id="tenant-a",
        recipient_phone="whatsapp:+48111111111",
        context={"first_name": "Jan"},
    )

    assert msg["body"] == "TEMPLATE:campaign_birthday:{'first_name': 'Jan'}"
    assert msg["language_code"] == "pl"


def test_build_message_uses_literal_body_without_context():
    svc = make_service(tenant={"language_code": "pl"})

    msg = svc.build_message(
        campaign={
            "campaign_id": "camp-plain",
            "body": "Cześć! Mamy promocję.",
        },
        tenant_id="tenant-a",
        recipient_phone="whatsapp:+48111111111",
    )

    assert msg["body"] == "Cześć! Mamy promocję."
    assert msg["language_code"] == "pl"


def test_build_message_language_from_campaign_has_priority():
    svc = make_service(
        conv={"language_code": "pl"},
        tenant={"language_code": "de"},
    )

    msg = svc.build_message(
        campaign={
            "body": "Hello",
            "language_code": "en",
        },
        tenant_id="tenant-a",
        recipient_phone="whatsapp:+48111111111",
    )

    assert msg["language_code"] == "en"


def test_build_message_language_from_conversation_when_no_campaign_lang():
    svc = make_service(
        conv={"language_code": "uk"},
        tenant={"language_code": "pl"},
    )

    msg = svc.build_message(
        campaign={"body": "Hej"},
        tenant_id="tenant-a",
        recipient_phone="whatsapp:+48111111111",
    )

    assert msg["language_code"] == "uk"


def test_build_message_language_from_tenant_when_no_campaign_or_conversation_lang():
    svc = make_service(
        conv=None,
        tenant={"language_code": "pl"},
    )

    msg = svc.build_message(
        campaign={"body": "Hej"},
        tenant_id="tenant-a",
        recipient_phone="whatsapp:+48111111111",
    )

    assert msg["language_code"] == "pl"


def test_select_recipients_accepts_strings_and_tokens_only():
    svc = make_service()

    result = svc.select_recipients({
        "recipients": [
            "token-1",
            {"token": "token-2", "phone": "should-not-leak"},
            {"phone": "whatsapp:+48123"},
            {},
            None,
        ]
    })

    assert result == [
        "token-1",
        {"token": "token-2"},
    ]


def test_select_include_tags_filters_only_strings():
    svc = make_service()

    result = svc.select_include_tags({
        "include_tags": ["vip", {"bad": "tag"}, None, "active"]
    })

    assert result == ["vip", "active"]


def test_select_exclude_tags_filters_only_strings():
    svc = make_service()

    result = svc.select_exclude_tags({
        "exclude_tags": ["blocked", {"bad": "tag"}, None, "inactive"]
    })

    assert result == ["blocked", "inactive"]