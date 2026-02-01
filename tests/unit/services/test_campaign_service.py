import json
import pytest
from src.services.campaign_service import CampaignService

from pathlib import Path
import json

def load_local_campaigns():
    repo_root = Path(__file__).resolve().parents[3]  # tests/unit/services -> repo root
    path = repo_root / "scripts" / "campaigns.local.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def test_build_message_from_template():
    # Fake TemplateService – bez DDB
    class FakeTemplates:
        def render_named(self, tenant, template_name, lang, ctx):
            return f"TEMPLATE:{template_name}:{lang}:{ctx}"

    # Fake ConversationsRepo – brak języka z rozmowy
    class FakeConversations:
        def get_conversation(self, tenant_id, channel, channel_user_id):
            return None

    # Fake TenantsRepo – ustalony język tenanta
    class FakeTenants:
        def get(self, tenant_id: str):
            return {"tenant_id": tenant_id, "language_code": "pl"}

    svc = CampaignService(
        template_service=FakeTemplates(),
        tenants_repo=FakeTenants(),
        conversations_repo=FakeConversations(),
    )

    campaigns = load_local_campaigns()
    camp = next(c for c in campaigns if c["campaign_id"] == "camp-birthday-template")

    msg = svc.build_message(
        campaign=camp,
        tenant_id="tenant-a",
        recipient_phone="whatsapp:+48111111111",
        context={"first_name": "Jan"},
    )

    assert msg["body"].startswith("TEMPLATE:campaign_birthday")
    # język z FakeTenants
    assert msg["language_code"] == "pl"
