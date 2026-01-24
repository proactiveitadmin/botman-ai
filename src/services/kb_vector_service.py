"""Vector-based KB retrieval and indexing (FAQ -> embeddings -> Pinecone)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..common.config import settings
from ..common.logging_utils import logger
from ..common.text_chunking import chunk_faq
from ..adapters.openai_client import OpenAIClient
from ..adapters.pinecone_client import PineconeClient
from .clients_factory import ClientsFactory

from ..common.timing import timed


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
        clients_factory: ClientsFactory | None = None,
        pinecone_client: Optional[PineconeClient] = None,
    ) -> None:
        self._openai = openai_client or OpenAIClient()
        self._factory = clients_factory
        self._pinecone = pinecone_client or (None if self._factory else PineconeClient())
    
    def _client_for(self, tenant_id: str) -> PineconeClient:
        if self._factory:
            return self._factory.pinecone(tenant_id)
        if self._pinecone:
            return self._pinecone
        raise RuntimeError("KBVectorService misconfigured: missing clients_factory or client")

    def _enabled_for(self, tenant_id: str) -> bool:
        with timed("enabled_check", logger=logger, component="kb_vector_service", extra={"tenant_id": tenant_id}):
            if not getattr(settings, "kb_vector_enabled", True):
                return False
            pc = self._client_for(tenant_id)          
            logger.warning({
              "component": "kb_vector_service",
              "event": "enabled_check",
              "tenant_id": tenant_id,
              "has_api_key": bool(getattr(pc, "api_key", "")),
              "index_host": bool(getattr(pc, "index_host", "")),
              "pc_enabled": bool(getattr(pc, "enabled", False)),
            })
            return bool(self._openai and pc and pc.enabled)

    def enabled(self, tenant_id) -> bool:
        return self._enabled_for(tenant_id)

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
        with timed(
        "index_faq_total",
        logger=logger, 
        component="kb_vector_service",
        extra={"tenant_id": tenant_id, "lang": language_code},
        ):
            if not self.enabled(tenant_id):
                return False

            with timed(
                "chunk_faq",
                logger=logger, 
                component="kb_vector_service",
                extra={"tenant_id": tenant_id, "max_chars": max_chars},
            ):
                chunks = chunk_faq(faq, max_chars=max_chars)

            if not chunks:
                return False

            texts = [c.text for c in chunks]
            emb_model = getattr(settings, "embedding_model", "text-embedding-3-small")
            emb_dims = getattr(settings, "embedding_dimensions", None)

            with timed(
                "embed_faq_chunks",
                logger=logger, 
                component="kb_vector_service",
                extra={"tenant_id": tenant_id, "chunks": len(texts), "model": emb_model},
            ):
                vectors = self._openai.embed(texts, model=emb_model, dimensions=emb_dims)

            if not vectors or len(vectors) != len(chunks):
                logger.error({...})
                return False

            ns = self._namespace(tenant_id, language_code)
            batch_size = 100
            ok_all = True

            for i in range(0, len(chunks), batch_size):
                batch_chunks = chunks[i:i + batch_size]
                batch_vecs = vectors[i:i + batch_size]
                payload_vectors = [...]
                with timed(
                    "pinecone_upsert_batch",
                    logger=logger, 
                    component="kb_vector_service",
                    extra={"tenant_id": tenant_id, "namespace": ns, "batch_size": len(payload_vectors)},
                ):
                    ok = self._client_for(tenant_id).upsert(vectors=payload_vectors, namespace=ns)
                ok_all = ok_all and ok

            logger.info({...})
            return ok_all

    def retrieve(
        self,
        *,
        tenant_id: str,
        language_code: Optional[str],
        question: str,
        top_k: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        with timed(
            "retrieve_total",
            logger=logger, 
            component="kb_vector_service",
            extra={"tenant_id": tenant_id, "lang": language_code},
        ):
            if not self.enabled(tenant_id):
                logger.warning({...})
                return []

            q = (question or "").strip()
            if not q:
                return []

            emb_model = getattr(settings, "embedding_model", "text-embedding-3-small")
            emb_dims = getattr(settings, "embedding_dimensions", None)

            with timed(
                "embed_question",
                logger=logger, 
                component="kb_vector_service",
                extra={"tenant_id": tenant_id, "model": emb_model},
            ):
                q_vecs = self._openai.embed([q], model=emb_model, dimensions=emb_dims)

            if not q_vecs:
                return []

            ns = self._namespace(tenant_id, language_code)
            k = int(top_k or getattr(settings, "pinecone_top_k", 6) or 6)

            with timed(
                "pinecone_query",
                logger=logger, 
                component="kb_vector_service",
                extra={"tenant_id": tenant_id, "namespace": ns, "top_k": k},
            ):
                matches = self._client_for(tenant_id).query(
                    vector=q_vecs[0],
                    namespace=ns,
                    top_k=k,
                    include_metadata=True,
                )

            with timed(
                "postprocess_matches",
                logger=logger, 
                component="kb_vector_service",
                extra={"tenant_id": tenant_id, "matches": len(matches) if matches else 0},
            ):
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

            logger.info({
                "component": "kb_vector_service",
                "event": "KBVector: retrieved",
                "tenant_id": tenant_id,
                "lang": language_code,
                "requested_top_k": k,
                "returned": len(out),
            })
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
        "If the snippets do not contain the needed information, say you don't know AND ask the user if there is anything else you can help with.\n"
        "Always respond as a JSON object with a single key \"answer\".\n"
        "Knowledge snippets:\n"
        f"{context}\n"
    )
    if language_code:
        sys += f"\nAnswer in the language {language_code} (ISO language code)."
    else:
        sys += "\nAnswer in the same language as the user's question."
    return sys
