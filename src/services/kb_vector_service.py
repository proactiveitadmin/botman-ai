"""Vector-based KB retrieval and indexing (FAQ -> embeddings -> Pinecone)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..common.config import settings
from ..common.logging_utils import logger
from ..common.text_chunking import chunk_faq
from ..adapters.openai_client import OpenAIClient
from ..adapters.pinecone_client import PineconeClient


@dataclass(frozen=True)
class RetrievedChunk:
    score: float
    text: str
    faq_key: str
    chunk_id: str


class KBVectorService:
    """Handles indexing FAQ documents into Pinecone and retrieving relevant chunks."""

    def __init__(
        self,
        *,
        openai_client: Optional[OpenAIClient] = None,
        pinecone_client: Optional[PineconeClient] = None,
    ) -> None:
        self._openai = openai_client or OpenAIClient()
        self._pc = pinecone_client or PineconeClient(
            api_key=getattr(settings, "pinecone_api_key", ""),
            index_host=getattr(settings, "pinecone_index_host", ""),
        )

    def enabled(self) -> bool:
        return bool(getattr(settings, "kb_vector_enabled", True) and self._openai and self._pc and self._pc.enabled)

    def _namespace(self, tenant_id: str, language_code: Optional[str]) -> str:
        lang = (language_code or "").strip() or "default"
        prefix = getattr(settings, "pinecone_namespace_prefix", "kb") or "kb"
        return f"{prefix}:{tenant_id}:{lang}"

    def index_faq(
        self,
        *,
        tenant_id: str,
        language_code: Optional[str],
        faq: Dict[str, str],
        max_chars: int = 1200,
    ) -> bool:
        """Chunk + embed + upsert FAQ into Pinecone.

        This is idempotent: chunk IDs are deterministic so re-running updates vectors.
        """
        if not self.enabled():
            return False

        chunks = chunk_faq(faq, max_chars=max_chars)
        if not chunks:
            return False

        texts = [c.text for c in chunks]
        emb_model = getattr(settings, "embedding_model", "text-embedding-3-small")
        emb_dims = getattr(settings, "embedding_dimensions", None)
        vectors = self._openai.embed(texts, model=emb_model, dimensions=emb_dims)
        if not vectors or len(vectors) != len(chunks):
            logger.error({"component": "kb_vector_service","event": "kb_index_embed_failed", "tenant_id": tenant_id, "lang": language_code})
            return False

        ns = self._namespace(tenant_id, language_code)
        batch_size = 100
        ok_all = True
        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i : i + batch_size]
            batch_vecs = vectors[i : i + batch_size]
            payload_vectors: List[Dict[str, Any]] = []
            for ch, vec in zip(batch_chunks, batch_vecs):
                payload_vectors.append(
                    {
                        "id": ch.chunk_id,
                        "values": vec,
                        "metadata": {
                            "tenant_id": tenant_id,
                            "language_code": language_code or "",
                            "faq_key": ch.faq_key,
                            "text": ch.text,
                        },
                    }
                )
            ok = self._pc.upsert(vectors=payload_vectors, namespace=ns)
            ok_all = ok_all and ok

        logger.info(
            {
                "component": "kb_vector_service",
                "event": "kb_index_done",
                "tenant_id": tenant_id,
                "lang": language_code,
                "chunks": len(chunks),
                "ok": ok_all,
            }
        )
        return ok_all

    def retrieve(
        self,
        *,
        tenant_id: str,
        language_code: Optional[str],
        question: str,
        top_k: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        """Retrieve relevant FAQ chunks for the user question."""
        if not self.enabled():
            logger.warning(
                {
                    "component": "kb_vector_service",
                    "event": "KBVector: disabled -> skip retrieve",
                    "tenant_id": tenant_id,
                    "lang": language_code,
                }
            )
            return []

        q = (question or "").strip()
        if not q:
            return []

        emb_model = getattr(settings, "embedding_model", "text-embedding-3-small")
        emb_dims = getattr(settings, "embedding_dimensions", None)
        q_vecs = self._openai.embed([q], model=emb_model, dimensions=emb_dims)
        if not q_vecs:
            return []

        ns = self._namespace(tenant_id, language_code)
        k = int(top_k or getattr(settings, "pinecone_top_k", 6) or 6)

        matches = self._pc.query(vector=q_vecs[0], namespace=ns, top_k=k, include_metadata=True)
        out: List[RetrievedChunk] = []
        for m in matches:
            md = m.metadata or {}
            txt = (md.get("text") or "").strip()
            if not txt:
                continue
            out.append(
                RetrievedChunk(
                    score=float(m.score or 0.0),
                    text=txt,
                    faq_key=str(md.get("faq_key") or ""),
                    chunk_id=str(m.id or ""),
                )
            )
        logger.info(
            {
                "component": "kb_vector_service",
                "event": "KBVector: retrieved ",
                "tenant_id": tenant_id,
                "lang": language_code,
            }
        )
        return out


def build_kb_prompt(
    *,
    chunks: List[RetrievedChunk],
    language_code: Optional[str],
) -> str:
    """Prompt template for KB answering.

    We keep the legacy contract: assistant must return JSON {"answer": "..."}.
    """
    lines: List[str] = []
    for i, ch in enumerate(chunks, start=1):
        lines.append(f"[C{i}] {ch.text}")

    context = "\n\n".join(lines).strip()

    sys = (
        "You are a helpful assistant for a fitness club.\n"
        "Answer the user's question ONLY using the knowledge snippets below.\n"
        "If the snippets do not contain the needed information, say you don't know and ask a follow-up question.\n"
        "Always respond as a JSON object with a single key \"answer\".\n"
        "Knowledge snippets:\n"
        f"{context}\n"
    )
    if language_code:
        sys += f"\nAnswer in the language {language_code} (ISO language code)."
    else:
        sys += "\nAnswer in the same language as the user's question."
    return sys
