from __future__ import annotations

from dataclasses import dataclass


@dataclass
class _UpsertCall:
    namespace: str
    vectors: list


class DummyOpenAI:
    def __init__(self):
        self.calls = []

    def embed(self, texts: list[str], *, model: str, dimensions: int):
        # deterministyczne "wektory" (tylko do testów)
        self.calls.append({"texts": list(texts), "model": model, "dimensions": dimensions})
        return [[float(len(t)), 1.0, 0.0] for t in texts]


class DummyPinecone:
    def __init__(self):
        self.enabled = True
        self.upserts: list[_UpsertCall] = []
        self.queries = []
        self._query_matches = []

    def upsert(self, *, vectors: list[dict], namespace: str, max_attempts: int = 3):
        self.upserts.append(_UpsertCall(namespace=namespace, vectors=vectors))
        return True

    def query(
        self,
        *,
        vector: list[float],
        namespace: str,
        top_k: int = 6,
        include_metadata: bool = True,
        max_attempts: int = 3,
    ):
        self.queries.append({"vector": vector, "namespace": namespace, "top_k": top_k})
        return self._query_matches


def test_kb_vector_index_faq_upserts_chunks(monkeypatch):
    from src.common.config import settings
    from src.services.kb_vector_service import KBVectorService

    pc = DummyPinecone()
    monkeypatch.setattr(settings, "kb_vector_enabled", True, raising=False)
    monkeypatch.setattr(settings, "pinecone_api_key", "x", raising=False)
    monkeypatch.setattr(pc, "index_host", "my-index.svc.test.pinecone.io", raising=False)
    monkeypatch.setattr(settings, "embedding_model", "text-embedding-3-small", raising=False)
    monkeypatch.setattr(settings, "pinecone_namespace_prefix", "kb", raising=False)

    oa = DummyOpenAI()
    svc = KBVectorService(openai_client=oa, pinecone_client=pc)

    faq = {"Hours": "We are open from 8 to 20", "Location": "City center"}
    ok = svc.index_faq(tenant_id="t1", language_code="pl", faq=faq, max_chars=1000)
    assert ok is True

    # embeddings zrobione w jednym batchu
    assert len(oa.calls) == 1

    # spójność: liczba embeddingów = liczba wektorów w upsercie
    assert len(pc.upserts) == 1
    assert pc.upserts[0].namespace == "kb:t1:pl"

    n_texts = len(oa.calls[0]["texts"])
    n_vectors = len(pc.upserts[0].vectors)
    assert n_texts == n_vectors
    assert n_vectors >= 1  # nie zakładamy strategii chunkowania

    # metadane dla chunków
    md0 = pc.upserts[0].vectors[0]["metadata"]
    assert md0["tenant_id"] == "t1"
    assert md0["language_code"] == "pl"
    assert "text" in md0 and md0["text"].startswith("Q:")


def test_kb_vector_retrieve_queries_pinecone_and_maps_matches(monkeypatch):
    from src.common.config import settings
    from src.services.kb_vector_service import KBVectorService
    from src.adapters.pinecone_client import PineconeMatch

    monkeypatch.setattr(settings, "kb_vector_enabled", True, raising=False)
    monkeypatch.setattr(settings, "pinecone_api_key", "x", raising=False)
    monkeypatch.setattr(settings, "pinecone_index_host", "my-index.svc.test.pinecone.io", raising=False)
    monkeypatch.setattr(settings, "embedding_model", "text-embedding-3-small", raising=False)
    monkeypatch.setattr(settings, "pinecone_namespace_prefix", "kb", raising=False)
    monkeypatch.setattr(settings, "pinecone_top_k", 5, raising=False)

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

    # query poszło do właściwego namespace
    assert pc.queries[0]["namespace"] == "kb:t1:pl"
    assert pc.queries[0]["top_k"] == 5
