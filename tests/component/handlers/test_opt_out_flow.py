import json
import time

from src.domain.models import Message
from src.services.routing_service import RoutingService
from src.repos.conversations_repo import ConversationsRepo
from src.common.security import sign_optout_token, verify_optout_token


def test_opt_out_command_sets_flag(aws_stack, mock_ai):
    repo = ConversationsRepo()
    svc = RoutingService()

    msg = Message(
        tenant_id="default",
        from_phone="whatsapp:+48111111111",
        to_phone="whatsapp:+48222222222",
        body="STOP",
        channel="whatsapp",
        channel_user_id="whatsapp:+48111111111",
    )
    actions = svc.handle(msg)
    assert actions and actions[0].type == "reply"

    conv = repo.get_conversation("default", "whatsapp", "whatsapp:+48111111111") or {}
    assert conv.get("opt_out") is True
    assert isinstance(conv.get("opt_out_at"), int)


def test_opt_in_command_clears_flag(aws_stack, mock_ai):
    repo = ConversationsRepo()
    svc = RoutingService()

    # set opt-out first
    repo.upsert_conversation(
        tenant_id="default",
        channel="whatsapp",
        channel_user_id="whatsapp:+48111111111",
        opt_out=True,
        opt_out_at=int(time.time()),
        opt_out_source="test",
    )

    msg = Message(
        tenant_id="default",
        from_phone="whatsapp:+48111111111",
        to_phone="whatsapp:+48222222222",
        body="START",
        channel="whatsapp",
        channel_user_id="whatsapp:+48111111111",
    )
    actions = svc.handle(msg)
    assert actions and actions[0].type == "reply"

    conv = repo.get_conversation("default", "whatsapp", "whatsapp:+48111111111") or {}
    assert conv.get("opt_out") is False
    assert isinstance(conv.get("opt_out_at"), int)


def test_optout_link_token_roundtrip():
    tenant_id = "default"
    channel = "web"
    uid = "fake-uid"
    ts = int(time.time())
    token = sign_optout_token(tenant_id, channel, uid, "optout", ts)
    assert verify_optout_token(tenant_id, channel, uid, "optout", ts, token) is True
    assert verify_optout_token(tenant_id, channel, uid, "optin", ts, token) is False