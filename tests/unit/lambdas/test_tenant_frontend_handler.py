import json

from src.lambdas.tenant_frontend import handler as h


class FakeTable:
    def __init__(self):
        self.items = []

    def put_item(self, Item):
        self.items.append(Item)
        return {}


class FakeDdb:
    def __init__(self, table):
        self.table = table

    def Table(self, name):
        return self.table


def authed_event(event, tenant_id="t1"):
    event.setdefault("requestContext", {})["authorizer"] = {
        "claims": {"email": "admin@example.com", "custom:tenant_id": tenant_id}
    }
    return event


def test_create_campaign_stores_encrypted_recipient_tokens(monkeypatch):
    table = FakeTable()
    monkeypatch.setattr(h, "ddb_resource", lambda: FakeDdb(table))
    monkeypatch.setattr(h, "encrypt_phone", lambda tenant_id, phone: f"enc:{tenant_id}:{phone}")
    monkeypatch.setattr(h, "new_id", lambda prefix="": prefix + "1")

    event = authed_event({
        "httpMethod": "POST",
        "path": "/frontend/tenants/t1/campaigns",
        "pathParameters": {"tenant_id": "t1"},
        "body": json.dumps(
            {
                "body": "{{first_name}} {{payment_link}}",
                "phone_numbers": ["whatsapp:+48123123123", "+48123123123", "+48999888777"],
                "language_code": "pl",
                "include_tags": ["vip"],
                "payment_product_id": "p1",
            }
        ),
    })

    res = h.lambda_handler(event, None)

    assert res["statusCode"] == 201
    assert json.loads(res["body"])["recipient_count"] == 2
    item = table.items[0]
    assert item["tenant_id"] == "t1"
    assert item["body"] == "{{first_name}} {{payment_link}}"
    assert item["recipients"] == [
        {"token": "enc:t1:+48123123123"},
        {"token": "enc:t1:+48999888777"},
    ]
    assert "phone_numbers" not in item
    assert item["payment_product_id"] == "p1"


def test_create_campaign_requires_explicit_body(monkeypatch):
    event = authed_event({
        "httpMethod": "POST",
        "path": "/frontend/tenants/t1/campaigns",
        "pathParameters": {"tenant_id": "t1"},
        "body": json.dumps({"phone_numbers": ["+48123123123"]}),
    })

    res = h.lambda_handler(event, None)

    assert res["statusCode"] == 400
    assert json.loads(res["body"])["error"] == "body_required"


def test_monthly_metrics_uses_metrics_service(monkeypatch):
    class FakeMetrics:
        def monthly_stats(self, *, tenant_id, month, metric_names=None):
            assert tenant_id == "t1"
            assert month == "2026-05"
            assert metric_names == ["TenantOutboundSent"]
            return {"TenantOutboundSent": 12.0}

    monkeypatch.setattr(h, "MetricsService", lambda: FakeMetrics())

    event = authed_event({
        "httpMethod": "GET",
        "path": "/frontend/tenants/t1/metrics/monthly",
        "pathParameters": {"tenant_id": "t1"},
        "queryStringParameters": {"month": "2026-05", "metrics": "TenantOutboundSent"},
    })

    res = h.lambda_handler(event, None)

    assert res["statusCode"] == 200
    payload = json.loads(res["body"])
    assert payload["metrics"] == {"TenantOutboundSent": 12.0}
