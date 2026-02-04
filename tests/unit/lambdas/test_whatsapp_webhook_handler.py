import json

import pytest

import src.lambdas.whatsapp_webhook.handler as wh


def test_normalize_and_internal_from():
    assert wh._normalize_wa_id(" +48 123  ") == "48123"
    assert wh._to_internal_from("+48123") == "whatsapp:+48123"


def test_verify_signature_dev_skips(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    assert wh._verify_signature("{}", "sha256=dead", "secret") is True


def test_verify_signature_real(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "false")
    raw = "{\"a\":1}"
    secret = "s"
    import hmac, hashlib
    good = hmac.new(secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()
    assert wh._verify_signature(raw, f"sha256={good}", secret) is True
    assert wh._verify_signature(raw, f"sha256={'0'*64}", secret) is False


def test_handle_get_success(monkeypatch):
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "t")
    event = {
        "queryStringParameters": {
            "hub.mode": "subscribe",
            "hub.verify_token": "t",
            "hub.challenge": "123",
        }
    }
    res = wh._handle_get(event, tenant_id=None)
    assert res == {"statusCode": 200, "body": "123"}


def test_lambda_handler_post_invalid_json():
    event = {"httpMethod": "POST", "body": "not-json"}
    res = wh.lambda_handler(event, None)
    assert res["statusCode"] == 400


def test_lambda_handler_post_missing_tenant(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    # shared endpoint: no tenant in path and repo returns nothing - we must switch to Twilio, returns "OK"
    monkeypatch.setattr(wh.tenants_repo, "find_by_whatsapp_phone_number_id", lambda _pnid: None)
    event = {"httpMethod": "POST", "body": json.dumps({"entry": []})}
    res = wh.lambda_handler(event, None)
    assert res["statusCode"] == 200


def test_lambda_handler_post_enqueues_messages(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")

    # resolve tenant by phone_number_id
    monkeypatch.setattr(wh.tenants_repo, "find_by_whatsapp_phone_number_id", lambda _pnid: {"tenant_id": "t1"})
    monkeypatch.setattr(wh.tenant_cfg, "get", lambda tenant_id: {"whatsapp_cloud": {"app_secret": ""}})
    monkeypatch.setattr(wh.spam_service, "is_blocked", lambda **kwargs: False)
    monkeypatch.setattr(wh, "resolve_queue_url", lambda _env: "q")

    sent = []

    class FakeSQS:
        def send_message(self, **kwargs):
            sent.append(kwargs)
            return {"MessageId": "1"}

    monkeypatch.setattr(wh, "sqs_client", lambda: FakeSQS())
    monkeypatch.setattr(wh, "new_id", lambda prefix="": prefix + "1")
    monkeypatch.setattr(wh, "user_hmac", lambda *a, **k: "U")

    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "pn"},
                            "messages": [
                                {"from": "48123", "type": "text", "text": {"body": "hi"}, "id": "m1"}
                            ],
                        }
                    }
                ]
            }
        ]
    }

    event = {"httpMethod": "POST", "body": json.dumps(payload), "headers": {}}
    res = wh.lambda_handler(event, None)
    assert res["statusCode"] == 200
    assert sent
    assert json.loads(sent[0]["MessageBody"])["tenant_id"] == "t1"
