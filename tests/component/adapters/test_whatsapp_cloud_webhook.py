import json
import os
import pytest


def test_whatsapp_cloud_webhook_enqueues_inbound(monkeypatch):
    from src.lambdas.whatsapp_webhook import handler as wa

    inbound_msgs = []

    class FakeSQS:
        def send_message(self, QueueUrl, MessageBody, **kwargs):
            inbound_msgs.append({"Body": MessageBody, "Kwargs": kwargs})
            return {"MessageId": "fake"}

    monkeypatch.setenv("InboundEventsQueueUrl", "inbound-queue")
    monkeypatch.setenv("DEV_MODE", "true")  # skip signature verification

    monkeypatch.setattr(wa, "sqs_client", lambda: FakeSQS(), raising=True)
    monkeypatch.setattr(wa, "resolve_queue_url", lambda name: os.environ["InboundEventsQueueUrl"], raising=True)

    # disable spam
    class NoSpam:
        def is_blocked(self, tenant_id, phone):
            return False

    monkeypatch.setattr(wa, "spam_service", NoSpam(), raising=False)

    # tenant config with minimal whatsapp secrets
    class FakeTenantCfg:
        def get(self, tenant_id):
            return {"tenant_id": tenant_id, "whatsapp_cloud": {"app_secret": "x", "verify_token": "t"}}

    monkeypatch.setattr(wa, "tenant_cfg", FakeTenantCfg(), raising=False)

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "48...", "phone_number_id": "123"},
                            "contacts": [{"wa_id": "48123123123"}],
                            "messages": [
                                {
                                    "from": "48123123123",
                                    "id": "wamid.XYZ",
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": "Hej"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }

    event = {
        "httpMethod": "POST",
        "pathParameters": {"tenant": "default"},
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
        "isBase64Encoded": False,
        "requestContext": {"timeEpoch": 0},
    }

    res = wa.lambda_handler(event, None)
    assert res["statusCode"] == 200
    assert inbound_msgs, "Expected message enqueued to inbound queue"

    internal = json.loads(inbound_msgs[0]["Body"])
    assert internal["channel"] == "whatsapp"
    assert internal["from"] == "whatsapp:+48123123123"
    assert internal["body"] == "Hej"
    assert internal["provider"] == "whatsapp_cloud"
