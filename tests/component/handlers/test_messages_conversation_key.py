import os

from src.common.security import conversation_key
from src.repos.messages_repo import MessagesRepo


def test_messages_get_last_messages_uses_canonical_conv_key(aws_stack, monkeypatch):
    """Regression: after PII-protection, Messages are stored under a hashed
    conversation key (conv#<channel>#<uid>). get_last_messages must be called
    with the same key, otherwise history becomes empty."""

    # Make HMAC deterministic in tests (and avoid empty-key surprises)
    monkeypatch.setenv("USER_HASH_PEPPER", "test-pepper")

    repo = MessagesRepo()

    tenant_id = "tenantA"
    channel = "whatsapp"
    channel_user_id = "whatsapp:+48123456789"

    conv_key = conversation_key(tenant_id, channel, channel_user_id)

    repo.log_message(
        tenant_id=tenant_id,
        conversation_id=None,
        msg_id="m1",
        direction="inbound",
        body="hello",
        from_phone=channel_user_id,
        to_phone="whatsapp:+48000000000",
        channel=channel,
        channel_user_id=channel_user_id,
    )

    history = repo.get_last_messages(tenant_id, conv_key, limit=10)
    assert len(history) == 1
    assert history[0]["body"] == "hello"