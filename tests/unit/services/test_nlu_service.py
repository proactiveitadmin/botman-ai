import pytest


def test_nlu_fast_classify_empty_and_emoji():
    from src.services.nlu_service import NLUService

    svc = NLUService()

    assert svc._fast_classify("") == {
        "intent": "clarify",
        "confidence": 0.4,
        "slots": {"reason": "empty"},
    }

    assert svc._fast_classify("👍") == {"intent": "ack", "confidence": 0.9, "slots": {}}


def test_nlu_classify_calls_openai_when_not_fast(monkeypatch):
    from src.services.nlu_service import NLUService

    svc = NLUService()

    called = {}

    def fake_classify(text: str, lang: str):
        called["args"] = (text, lang)
        return {"intent": "faq", "confidence": 0.9, "slots": {"x": 1}}

    monkeypatch.setattr(svc.client, "classify", fake_classify)

    out = svc.classify_intent("hello", lang="en")
    assert out["intent"] == "faq"
    assert called["args"] == ("hello", "en")
