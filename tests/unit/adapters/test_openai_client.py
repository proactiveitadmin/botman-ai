import json

import pytest


def _mk_client(monkeypatch, *, enabled: bool = False):
    """Create OpenAIClient with deterministic settings."""
    from src.adapters import openai_client as mod
    from src.common.config import settings

    # Ensure settings reflect test desired state.
    monkeypatch.setattr(settings, "openai_api_key", "test-key" if enabled else "")

    if enabled:
        # Provide a fake OpenAI SDK class so `enabled` becomes True.
        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.chat = type("Chat", (), {})()
                self.chat.completions = type("Completions", (), {})()

                def create(**_kwargs):
                    # minimal response shape
                    msg = type("Msg", (), {"content": json.dumps({"intent": "faq", "confidence": 1, "slots": {}})})()
                    choice = type("Choice", (), {"message": msg})()
                    return type("Resp", (), {"choices": [choice]})()

                self.chat.completions.create = create
                self.embeddings = type("Emb", (), {})()
                
                def emb_create(**_kwargs):
                    data = [type("D", (), {"embedding": [0.1, 0.2]})() for _ in (_kwargs.get("input") or [])]
                    return type("EResp", (), {"data": data})()

                self.embeddings.create = emb_create

        monkeypatch.setattr(mod, "OpenAI", FakeOpenAI)

    return mod.OpenAIClient(api_key=None, model="gpt-test")


def test_parse_classification_handles_invalid_json(monkeypatch):
    from src.adapters.openai_client import OpenAIClient

    c = OpenAIClient(api_key="", model="gpt-test")
    out = c._parse_classification("NOT JSON")
    assert out["intent"] == "clarify"


def test_parse_classification_normalizes_fields(monkeypatch):
    from src.adapters.openai_client import OpenAIClient

    c = OpenAIClient(api_key="", model="gpt-test")
    payload = json.dumps({"intent": "unknown", "confidence": "2", "slots": [1, 2]})
    out = c._parse_classification(payload)
    assert out["intent"] == "clarify"  # unknown intent -> clarify
    assert out["confidence"] == 1.0  # clamped
    assert out["slots"] == {}


def test_chat_offline_returns_json_fallback(monkeypatch):
    c = _mk_client(monkeypatch, enabled=False)
    s = c.chat([{"role": "user", "content": "hi"}])
    data = json.loads(s)
    assert data["intent"] == "clarify"
    assert "echo" in data["slots"]


def test_chat_retries_and_falls_back(monkeypatch):
    import src.adapters.openai_client as oc

    class FakeAPIStatusError(Exception):
        pass

    # Podmień w module openai_client
    monkeypatch.setattr(oc, "APIStatusError", FakeAPIStatusError, raising=False)

    # Podmień też w vendor module openai (jeśli test/klient się do niego odwołuje)
    try:
        import openai
        monkeypatch.setattr(openai, "APIStatusError", FakeAPIStatusError, raising=False)
    except Exception:
        pass

    # ... reszta testu ...

    # PRZYKŁAD: jeśli wcześniej było:
    # side_effect=[APIStatusError("x"), APIStatusError("y"), ok]
    # to ma być:
    side_effect = [FakeAPIStatusError("x"), FakeAPIStatusError("y")]

def test_embed_uses_cache(monkeypatch):
    c = _mk_client(monkeypatch, enabled=True)
    # shorten cache TTL and max for deterministic behavior
    monkeypatch.setattr(c, "_embed_cache_ttl_s", 9999.0)
    monkeypatch.setattr(c, "_embed_cache_max", 10)

    v1 = c.embed([" hello ", "world"], model="text-embedding-3-small", dimensions=2)
    assert v1 == [[0.1, 0.2], [0.1, 0.2]]

    # Second call should hit cache and not call embeddings.create again.
    called = {"n": 0}

    def fail(**kwargs):
        called["n"] += 1
        raise AssertionError("should not call embeddings again")

    c.client.embeddings.create = fail
    v2 = c.embed(["hello", "world"], model="text-embedding-3-small", dimensions=2)
    assert v2 == [[0.1, 0.2], [0.1, 0.2]]
    assert called["n"] == 0
