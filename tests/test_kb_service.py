import json

from botocore.exceptions import ClientError

from src.services.kb_service import KBService
from src.domain.templates import DEFAULT_FAQ
from src.common.config import settings
import src.services.kb_service as kb_mod

class DummyBody:
    def __init__(self, text: str):
        self._text = text

    def read(self):
        return self._text.encode("utf-8")


class DummyS3:
    def __init__(self, payload: str, raise_no_such_key: bool = False):
        self.payload = payload
        self.raise_no_such_key = raise_no_such_key
        self.calls = []

    def get_object(self, Bucket, Key):
        self.calls.append({"Bucket": Bucket, "Key": Key})
        if self.raise_no_such_key:
            raise ClientError(
                {
                    "Error": {
                        "Code": "NoSuchKey",
                        "Message": "not found",
                    }
                },
                "GetObject",
            )
        return {"Body": DummyBody(self.payload)}


def test_load_tenant_faq_without_bucket_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "kb_bucket", "", raising=False)
    svc = KBService(bucket=None, openai_client=None)
    faq = svc._load_tenant_faq("t1", "pl")
    assert faq is None


def test_load_tenant_faq_from_s3_and_cache(monkeypatch):
    monkeypatch.setattr(settings, "kb_bucket", "kb-bucket", raising=False)
    payload = json.dumps({"hours": "9-18", "Price ": "cheap"})
    dummy = DummyS3(payload)
    monkeypatch.setattr(kb_mod, "s3_client", lambda: dummy)

    svc = KBService(bucket=None, openai_client=None)
    faq1 = svc._load_tenant_faq("tenant", "pl")
    assert faq1["hours"] == "9-18"
    # klucze są normalizowane (trim + lower)
    assert "price" in faq1

    # drugi raz – z cache, bez kolejnego wywołania S3
    dummy.calls.clear()
    faq2 = svc._load_tenant_faq("tenant", "pl")
    assert faq2 is faq1
    assert dummy.calls == []


def test_load_tenant_faq_no_such_key_sets_none(monkeypatch):
    monkeypatch.setattr(settings, "kb_bucket", "kb-bucket", raising=False)
    dummy = DummyS3("{}", raise_no_such_key=True)
    monkeypatch.setattr(kb_mod, "s3_client", lambda: dummy)

    svc = KBService(bucket=None, openai_client=None)
    faq = svc._load_tenant_faq("tenant", "pl")
    # brak pliku → None + cache
    assert faq is None
    cached = svc._cache[svc._cache_key("tenant", "pl")]
    assert cached is None


def test_select_relevant_faq_entries_overlap_and_fallback():
    svc = KBService(bucket=None, openai_client=None)
    tenant_faq = {
        "hours": "We are open from 8 to 20",
        "location": "City center",
        "price": "",
    }

    # pytanie z overlapem słów
    selected = svc._select_relevant_faq_entries("What are your opening hours?", tenant_faq, k=1)
    assert list(selected.keys()) == ["hours"]

    # pytanie bez overlapu → fallback: całe FAQ
    selected2 = svc._select_relevant_faq_entries("completely unrelated", tenant_faq, k=1)
    assert selected2 == tenant_faq


def test_answer_uses_s3_and_fallback(monkeypatch):
    monkeypatch.setattr(settings, "kb_bucket", "kb-bucket", raising=False)

    class DummyKB(KBService):
        def __init__(self):
            super().__init__(bucket="kb-bucket", openai_client=None)
            self._cache[self._cache_key("t1", None)] = {"hours": "from s3"}

    svc = DummyKB()
    assert svc.answer("hours", tenant_id="t1") == "from s3"

    # brak w S3 → fallback na DEFAULT_FAQ
    assert svc.answer("price", tenant_id="t1") == DEFAULT_FAQ.get("price")


def test_answer_ai_returns_none_for_empty_question():
    svc = KBService(bucket=None, openai_client=None)
    assert svc.answer_ai(question="", tenant_id="t1") is None

def test_answer_ai_happy_path_with_json(monkeypatch):
    monkeypatch.setattr(settings, "kb_bucket", "", raising=False)
    # prosty FAQ – tylko jedna odpowiedź
    svc = KBService(bucket=None, openai_client=None)
    svc._cache[svc._cache_key("t1", "pl")] = {"hours": "8-20"}
    monkeypatch.setattr(svc, "_tenant_default_lang", lambda *_: "en", raising=False) 
    
    class DummyClient:
        def __init__(self):
            self.last_messages = None

        def chat(self, messages, max_tokens=None):
            self.last_messages = messages
            return json.dumps({"answer": "We are open 8-20"})

    svc._client = DummyClient()
    ans = svc.answer_ai(question="What are your opening hours?", tenant_id="t1", language_code="pl")
    assert "8-20" in ans

def test_answer_ai_llm_failure_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "kb_bucket", "", raising=False)
    svc = KBService(bucket=None, openai_client=None)
    svc._cache[svc._cache_key("t1", None)] = {"hours": "8-20"}
    monkeypatch.setattr(svc, "_tenant_default_lang", lambda *_: "en", raising=False) 
    
    class DummyClient:
        def chat(self, *a, **k):
            raise RuntimeError("boom")

    svc._client = DummyClient()
    ans = svc.answer_ai(question="q", tenant_id="t1")
    assert ans is None
