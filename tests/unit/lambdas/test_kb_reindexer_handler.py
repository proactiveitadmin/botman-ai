import json

import src.lambdas.kb_reindexer.handler as h


class FakeKB:
    def __init__(self):
        self.calls = []

    def reindex_faq(self, *, tenant_id: str, language_code: str | None):
        self.calls.append((tenant_id, language_code))
        return True


def test_parse_s3_records():
    event = {
        "Records": [
            {"s3": {"object": {"key": "tA/faq_pl.json"}}},
            {"s3": {"object": {"key": "tB/faq_pl-PL.json"}}},
            {"s3": {"object": {"key": "ignore.txt"}}},
        ]
    }
    assert h._parse_s3_records(event) == [("tA", "pl"), ("tB", "pl")]


def test_lambda_handler_s3_mode(monkeypatch):
    kb = FakeKB()
    monkeypatch.setattr(h, "KBService", lambda: kb)

    event = {"Records": [{"s3": {"object": {"key": "tA/faq_en.json"}}}]}
    res = h.lambda_handler(event, None)
    assert res["statusCode"] == 200
    body = json.loads(res["body"])
    assert body["mode"] == "s3"
    assert kb.calls == [("tA", "en")]


def test_lambda_handler_manual_mode(monkeypatch):
    kb = FakeKB()
    monkeypatch.setattr(h, "KBService", lambda: kb)

    event = {"tenant_id": "t1", "languages": ["pl", "en"]}
    res = h.lambda_handler(event, None)
    assert res["statusCode"] == 200
    body = json.loads(res["body"])
    assert body["mode"] == "manual"
    assert ("t1", "pl") in kb.calls
    assert ("t1", "en") in kb.calls