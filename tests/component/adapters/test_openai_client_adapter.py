import json
import asyncio

import pytest

from src.adapters import openai_client as oa_mod
from src.common.config import settings


def test_chat_once_offline_fallback_uses_last_user_message(monkeypatch):
    """
    Brak API key -> self.enabled = False -> _chat_once zwraca fallback JSON.
    """
    monkeypatch.setattr(settings, "openai_api_key", "", raising=False)
    client = oa_mod.OpenAIClient(api_key=None, model="gpt-test")

    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello world"},
    ]
    content = client._chat_once(messages)
    data = json.loads(content)
    assert data["intent"] == "clarify"
    assert data["confidence"] == 0.49
    assert data["slots"]["echo"] == "hello world"


def test_parse_classification_handles_invalid_json():
    client = oa_mod.OpenAIClient(api_key=None, model="gpt-test")
    res = client._parse_classification("not-a-json")
    assert res["intent"] == "clarify"
    assert res["confidence"] == 0.3
    assert res["slots"] == {}


def test_parse_classification_normalizes_fields():
    client = oa_mod.OpenAIClient(api_key=None, model="gpt-test")
    payload = {
        "intent": "unknown_intent",
        "confidence": "2.5",  # wyjdzie >1, powinno być przycięte
        "slots": ["not-a-dict"],
    }
    res = client._parse_classification(json.dumps(payload))
    assert res["intent"] == "clarify"           # nieznany intent -> clarify
    assert 0.0 <= res["confidence"] <= 1.0      # przycięte do zakresu
    assert res["slots"] == {}                   # nie-dict -> pusty dict


def test_classify_builds_prompt_and_uses_chat(monkeypatch):
    calls = {}

    def fake_chat(messages, model=None, max_tokens=None):
        calls["messages"] = messages
        calls["model"] = model
        calls["max_tokens"] = max_tokens
        return json.dumps({"intent": "faq", "confidence": 0.9, "slots": {"topic": "hours"}})

    monkeypatch.setattr(settings, "openai_api_key", "dummy", raising=False)
    client = oa_mod.OpenAIClient(api_key="dummy", model="gpt-4o-mini")
    monkeypatch.setattr(client, "chat", fake_chat)

    res = client.classify("Jakie są godziny otwarcia?", lang="pl")
    assert res["intent"] == "faq"
    assert res["slots"]["topic"] == "hours"

    user_msg = calls["messages"][1]["content"]
    assert "LANG=pl" in user_msg
    assert "TEXT=Jakie są godziny otwarcia?" in user_msg
    assert calls["model"] == client.model
    assert calls["max_tokens"] == 256


def test_classify_async_uses_chat_async(monkeypatch):
    """
    Testujemy classify_async bez potrzeby pluginu pytest-asyncio –
    sami odpalamy pętlę eventów.
    """
    async_calls = {}

    async def fake_chat_async(messages, model=None, max_tokens=None):
        async_calls["messages"] = messages
        async_calls["model"] = model
        async_calls["max_tokens"] = max_tokens
        return json.dumps({"intent": "reserve_class", "confidence": 0.8, "slots": {"class_id": 1}})

    monkeypatch.setattr(settings, "openai_api_key", "dummy", raising=False)
    client = oa_mod.OpenAIClient(api_key="dummy", model="gpt-4o-mini")
    monkeypatch.setattr(client, "chat_async", fake_chat_async)

    async def _run():
        res = await client.classify_async("Chcę się zapisać na zajęcia", lang="pl")
        assert res["intent"] == "reserve_class"
        assert res["slots"]["class_id"] == 1
        assert async_calls["model"] == client.model
        assert async_calls["max_tokens"] == 256

    asyncio.run(_run())


def test_chat_retries_and_returns_fallback_on_api_error(monkeypatch):
    """
    Symulujemy błąd API (APIError / RateLimitError / etc) – powinna zadziałać ścieżka fallbacku.
    """
    class DummyAPIError(Exception):
        pass

    monkeypatch.setattr(oa_mod, "APIError", DummyAPIError)
    monkeypatch.setattr(oa_mod, "RateLimitError", DummyAPIError)
    monkeypatch.setattr(oa_mod, "APIStatusError", DummyAPIError)
    monkeypatch.setattr(oa_mod, "APIConnectionError", DummyAPIError)
    monkeypatch.setattr(oa_mod.time, "sleep", lambda *_a, **_k: None)

    monkeypatch.setattr(settings, "openai_api_key", "dummy", raising=False)
    client = oa_mod.OpenAIClient(api_key="dummy", model="gpt-4o-mini")

    def always_fail(*args, **kwargs):
        raise DummyAPIError("boom")

    monkeypatch.setattr(client, "_chat_once", always_fail)

    content = client.chat([{"role": "user", "content": "hi"}])
    data = json.loads(content)
    assert data["intent"] == "clarify"
    assert data["confidence"] == 0.3
    note = data["slots"].get("note", "")
    # Akceptujemy oba możliwe warianty komunikatu (w zależności od implementacji)
    assert "LLM unavailable" in note or "LLM error" in note
