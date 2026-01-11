import json
import os
import time

from src.lambdas.outbound_sender import handler
from src.repos.conversations_repo import ConversationsRepo


def test_outbound_sender_blocks_campaign_when_opted_out(aws_stack, monkeypatch):
    # mark user as opted out (tenant+channel+user)
    repo = ConversationsRepo()
    repo.upsert_conversation(
        tenant_id="default",
        channel="whatsapp",
        channel_user_id="whatsapp:+48111111111",
        opt_out=True,
        opt_out_at=int(time.time()),
        opt_out_source="test",
    )

    sent = {"n": 0}

    class DummyTwilio:
        def send_text(self, *args, **kwargs):
            sent["n"] += 1
            return {"status": "OK", "sid": "fake"}

    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.setattr(handler.clients, "twilio", lambda tenant_id: DummyTwilio())

    event = {
        "Records": [
            {
                "messageId": "m1",
                "body": json.dumps(
                    {
                        "tenant_id": "default",
                        "to": "+48111111111",
                        "body": "promo",
                        "message_type": "campaign",
                    }
                ),
            }
        ]
    }

    res = handler.lambda_handler(event, None)
    assert res["statusCode"] == 200
    assert sent["n"] == 0


def test_outbound_sender_does_not_block_reply(aws_stack, monkeypatch):
    sent = {"n": 0}

    class DummyTwilio:
        def send_text(self, *args, **kwargs):
            sent["n"] += 1
            return {"status": "OK", "sid": "fake"}

    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.setattr(handler.clients, "twilio", lambda tenant_id: DummyTwilio())

    # reply messages carry channel_user_id and message_type=reply
    event = {
        "Records": [
            {
                "messageId": "m1",
                "body": json.dumps(
                    {
                        "tenant_id": "default",
                        "channel": "whatsapp",
                        "channel_user_id": "whatsapp:+48111111111",
                        "to": "whatsapp:+48111111111",
                        "body": "hello",
                        "message_type": "reply",
                    }
                ),
            }
        ]
    }
    res = handler.lambda_handler(event, None)
    assert res["statusCode"] == 200
    assert sent["n"] == 1