import json


def test_kb_reindexer_parses_s3_key_and_triggers_reindex(monkeypatch):
    # import dopiero w teście, żeby patchowanie zadziałało niezależnie od kolejności
    from src.lambdas.kb_reindexer import handler as mod

    calls = []

    class DummyKB:
        def reindex_faq(self, *, tenant_id, language_code=None):
            calls.append({"tenant_id": tenant_id, "language_code": language_code})
            return True

    monkeypatch.setattr(mod, "KBService", lambda: DummyKB(), raising=False)

    # event z S3: tenantA/faq_pl.json
    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "kb"},
                    "object": {"key": "tenantA/faq_pl.json"},
                }
            }
        ]
    }

    resp = mod.lambda_handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["mode"] == "s3"
    assert body["indexed"][0]["tenant_id"] == "tenantA"
    assert body["indexed"][0]["language_code"] == "pl"
    assert body["indexed"][0]["ok"] is True
    assert calls == [{"tenant_id": "tenantA", "language_code": "pl"}]


def test_kb_reindexer_normalizes_lang_region_variant(monkeypatch):
    from src.lambdas.kb_reindexer import handler as mod

    calls = []

    class DummyKB:
        def reindex_faq(self, *, tenant_id, language_code=None):
            calls.append({"tenant_id": tenant_id, "language_code": language_code})
            return True

    monkeypatch.setattr(mod, "KBService", lambda: DummyKB(), raising=False)

    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "kb"},
                    "object": {"key": "tenantB/faq_pl-PL.json"},
                }
            }
        ]
    }

    mod.lambda_handler(event, None)
    assert calls == [{"tenant_id": "tenantB", "language_code": "pl"}]
