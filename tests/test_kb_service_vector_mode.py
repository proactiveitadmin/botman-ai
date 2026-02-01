import json

def test_answer_ai_uses_vector_retrieval_when_enabled(monkeypatch):
    import json
    from src.common.config import settings
    from src.services.kb_service import KBService
        
    monkeypatch.setenv("KB_VECTOR_MIN_SCORE_LOW", "0")
    monkeypatch.setenv("KB_VECTOR_FASTPATH_MIN_SCORE", "0.99") 
    monkeypatch.setenv("KB_VECTOR_MIN_SCORE", "0.72")
    # --- konfiguracja ---
    monkeypatch.setattr(settings, "kb_bucket", "", raising=False)

    svc = KBService(bucket=None, openai_client=None)

    # FAQ w cache (żeby nie dotykać S3)
    svc._cache[svc._cache_key("t1", "pl")] = {"hours": "8-20"}
    monkeypatch.setattr(svc, "_tenant_default_lang", lambda *_: "en", raising=False)

    # jeśli vector-mode działa, legacy keyword path NIE powinna się odpalić
    def _boom(*a, **k):
        raise AssertionError("legacy keyword retrieval should not be used in vector mode")

    monkeypatch.setattr(svc, "_select_relevant_faq_entries", _boom, raising=False)

    # --- mock vector service ---
    class DummyVector:
        def enabled(self, tenant_id):
            return True

        def retrieve(self, *, tenant_id, language_code, question):
            return [
                type(
                    "Chunk",
                    (),
                    {
                        "chunk_id": "c1",
                        "score": 0.4,  # LOW score → fast-path NIE zadziała
                        "text": "Q: Hours\nA: 8-20",
                        "faq_key": "Hours",
                    },
                )
            ]

    svc._vector = DummyVector()

    # --- mock OpenAI client ---
    class DummyOpenAIClient:
        def __init__(self):
            self.last_messages = None

        def chat(self, messages, max_tokens=None):
            self.last_messages = messages
            return json.dumps({"answer": "We are open 8-20"})

    openai_client = DummyOpenAIClient()
    svc._client = openai_client

    # --- execute ---
    result = svc.answer_ai(
        question="What are your hours?",
        tenant_id="t1",
        language_code="pl",
    )

    # --- assertions ---
    assert "8-20" in result

    # fast-path wyłączony → LLM MUSI być użyty
    assert openai_client.last_messages is not None

    system_prompt = openai_client.last_messages[0]["content"]
    assert "Knowledge snippets" in system_prompt
    assert "Q: Hours" in system_prompt
