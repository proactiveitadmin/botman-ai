import json


def test_answer_ai_uses_vector_retrieval_when_enabled(monkeypatch):
    from src.common.config import settings
    from src.services.kb_service import KBService

    # w testach nie zależy nam od S3 – wstawiamy FAQ do cache
    monkeypatch.setattr(settings, "kb_bucket", "", raising=False)

    svc = KBService(bucket=None, openai_client=None)
    svc._cache[svc._cache_key("t1", "pl")] = {"hours": "8-20"}
    monkeypatch.setattr(svc, "_tenant_default_lang", lambda *_: "en", raising=False)
    # jeśli vector-retrieval zadziała, stary keyword selection NIE powinien być użyty
    def _boom(*a, **k):
        raise AssertionError("legacy _select_relevant_faq_entries should not be called")

    monkeypatch.setattr(svc, "_select_relevant_faq_entries", _boom, raising=False)

    # Mock KBVectorService: enabled + zwróć chunk
    class DummyVector:
        def enabled(self):
            return True

        def retrieve(self, *, tenant_id, language_code, question):
            return [
                type(
                    "RC",
                    (),
                    {"score": 0.9, "text": "Q: Hours\nA: 8-20", "faq_key": "Hours", "chunk_id": "c1"},
                )
            ]

    svc._vector = DummyVector()

    class DummyClient:
        def __init__(self):
            self.last_messages = None

        def chat(self, messages, max_tokens=None):
            self.last_messages = messages
            return json.dumps({"answer": "We are open 8-20"})

    svc._client = DummyClient()

    ans = svc.answer_ai(question="What are your hours?", tenant_id="t1", language_code="pl")
    assert "8-20" in ans

    # prompt powinien zawierać nowy template (Knowledge snippets) i treść chunk-a
    sys = svc._client.last_messages[0]["content"]
    assert "Knowledge snippets" in sys
    assert "Q: Hours" in sys

