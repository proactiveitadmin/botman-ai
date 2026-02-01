import dataclasses
from typing import Any, Dict, List

from src.adapters.pinecone_client import PineconeMatch

from src.common.text_chunking import chunk_faq

@dataclasses.dataclass
class DummyUpsertCall:
    vectors: list
    namespace: str


class DummyOpenAI:
    def __init__(self):
        self.calls = []

    def embed(self, texts, model=None, dimensions=None):
        self.calls.append({"texts": texts, "model": model, "dimensions": dimensions})
        # stałe wektory 3D, łatwe do asercji
        return [[0.1, 0.2, 0.3] for _ in texts]


class DummyPinecone:
    def __init__(self):
        self.upserts: List[DummyUpsertCall] = []
        self.queries = []
        self._query_matches: List[PineconeMatch] = []
        self.index_host = "my-index.svc.test.pinecone.io"
        self.api_key = "x"
        self.enabled = True

    def upsert(self, *, vectors, namespace):
        self.upserts.append(DummyUpsertCall(vectors=vectors, namespace=namespace))
        return True

    def query(self, *, vector, namespace, top_k, include_metadata, filter=None):
        self.queries.append(
            {
                "namespace": namespace,
                "top_k": top_k,
                "include_metadata": include_metadata,
                "filter": filter,
            }
        )
        return self._query_matches


def test_kb_vector_index_faq_upserts_chunks(monkeypatch):
    from src.common.config import settings
    from src.services.kb_vector_service import KBVectorService
    from src.common.text_chunking import chunk_faq

    monkeypatch.setattr(settings, "kb_vector_enabled", True, raising=False)
    monkeypatch.setattr(settings, "pinecone_namespace_prefix", "kb", raising=False)
    monkeypatch.setattr(settings, "embedding_model", "text-embedding-3-small", raising=False)
    monkeypatch.setattr(settings, "embedding_dimensions", None, raising=False)

    oa = DummyOpenAI()
    pc = DummyPinecone()
    svc = KBVectorService(openai_client=oa, pinecone_client=pc)

    faq = {"Hours": "We are open from 8 to 20", "Location": "City center"}
    expected_chunks = chunk_faq(faq, max_chars=1000)

    ok = svc.index_faq(tenant_id="t1", language_code="pl", faq=faq, max_chars=1000)

    assert ok is True
    assert len(oa.calls) == 1
    assert len(pc.upserts) >= 1

    n_vectors_total = sum(len(u.vectors) for u in pc.upserts)
    assert n_vectors_total == len(expected_chunks)
    assert n_vectors_total >= 1


def test_kb_vector_retrieve_queries_pinecone_and_maps_matches(monkeypatch):
    from src.common.config import settings
    from src.services.kb_vector_service import KBVectorService

    monkeypatch.setattr(settings, "kb_vector_enabled", True, raising=False)
    monkeypatch.setattr(settings, "pinecone_namespace_prefix", "kb", raising=False)
    monkeypatch.setattr(settings, "pinecone_top_k", 5, raising=False)
    monkeypatch.setattr(settings, "embedding_model", "text-embedding-3-small", raising=False)
    monkeypatch.setattr(settings, "embedding_dimensions", None, raising=False)

    oa = DummyOpenAI()
    pc = DummyPinecone()
    pc._query_matches = [
        PineconeMatch(id="c1", score=0.91, metadata={"faq_key": "Hours", "text": "Q: Hours\nA: 8-20"}),
        PineconeMatch(id="c2", score=0.70, metadata={"faq_key": "Location", "text": "Q: Location\nA: City"}),
    ]

    svc = KBVectorService(openai_client=oa, pinecone_client=pc)
    chunks = svc.retrieve(tenant_id="t1", language_code="pl", question="When open?")

    assert len(chunks) == 2
    assert chunks[0].chunk_id == "c1"
    assert chunks[0].score == 0.91
    assert "8-20" in chunks[0].text
    assert pc.queries[0]["namespace"] == "kb:t1:pl"
    assert pc.queries[0]["top_k"] == 5

def test_kb_vector_index_faq_builds_payload_vectors(monkeypatch):
    """
    Regression test: `payload_vectors = [...]` must not be a placeholder.

    Weryfikujemy, że index_faq robi upsert listy wektorów w formacie:
      {id, values, metadata{text, faq_key, chunk_id}}
    oraz że id jest deterministyczne (chunk.chunk_id).
    """
    from src.common.config import settings
    from src.services.kb_vector_service import KBVectorService

    monkeypatch.setattr(settings, "kb_vector_enabled", True, raising=False)
    monkeypatch.setattr(settings, "pinecone_namespace_prefix", "kb", raising=False)
    monkeypatch.setattr(settings, "embedding_model", "text-embedding-3-small", raising=False)
    monkeypatch.setattr(settings, "embedding_dimensions", None, raising=False)

    oa = DummyOpenAI()
    pc = DummyPinecone()
    svc = KBVectorService(openai_client=oa, pinecone_client=pc)

    faq = {"Hours": "We are open from 8 to 20", "Location": "City center"}
    expected_chunks = chunk_faq(faq, max_chars=1000)

    ok = svc.index_faq(tenant_id="t1", language_code="pl", faq=faq, max_chars=1000)
    assert ok is True

    # embeddings wykonane na tych samych tekstach co chunk_faq()
    assert len(oa.calls) == 1
    assert oa.calls[0]["texts"] == [c.text for c in expected_chunks]

    # upsert wykonany
    assert len(pc.upserts) >= 1
    assert pc.upserts[0].namespace == "kb:t1:pl"

    upsert_vectors = pc.upserts[0].vectors
    assert isinstance(upsert_vectors, list)
    assert len(upsert_vectors) == len(expected_chunks)

    # każdy element ma poprawny kształt + deterministyczne id
    for v, ch in zip(upsert_vectors, expected_chunks):
        assert isinstance(v, dict)
        assert set(v.keys()) >= {"id", "values", "metadata"}
        assert v["id"] == ch.chunk_id
        assert v["values"] == [0.1, 0.2, 0.3]

        md = v["metadata"]
        assert md["text"] == ch.text
        assert md["faq_key"] == ch.faq_key
        assert md["chunk_id"] == ch.chunk_id
