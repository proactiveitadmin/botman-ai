"""Vector-based KB retrieval and indexing (FAQ -> embeddings -> Pinecone)."""

from __future__ import annotations
import re

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

        # enabled() cache (per warm runtime)
        # tenant_id -> (expires_at_epoch, enabled_bool)
        import os, time
        self._enabled_cache_ttl_s = float(os.getenv("KB_VECTOR_ENABLED_CACHE_TTL", "300") or 300)
        self._enabled_cache: dict[str, tuple[float, bool]] = {}

        # question embedding cache is handled in OpenAIClient (embed cache).
    
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
        # enabled_check can be surprisingly expensive if it triggers tenant config
        # loads (DDB/SSM) on a cold runtime. Cache the result with a TTL.
        if not tenant_id:
            return False
        import time
        now = time.time()
        cached = self._enabled_cache.get(tenant_id)
        if cached:
            exp, val = cached
            if exp > now:
                return val

        val = self._enabled_for(tenant_id)
        self._enabled_cache[tenant_id] = (now + self._enabled_cache_ttl_s, bool(val))
        return bool(val)

    def _namespace(self, tenant_id: str, language_code: Optional[str]) -> str:
        lang = (language_code or "").strip() or "default"
        prefix = getattr(settings, "pinecone_namespace_prefix", "kb") or "kb"
        return f"{prefix}:{tenant_id}:{lang}"
        
    def _extract_answer_from_text(self, text: str) -> str | None:
        """
        Stored FAQ chunk format:
          Q: <faq_key>
          A: <answer...>
        Return the answer part after 'A:'.
        """
        if not text:
            return None
        m = re.search(r"\bA:\s*(.+)$", text, flags=re.IGNORECASE | re.DOTALL)
        if not m:
            return None
        ans = (m.group(1) or "").strip()
        return ans or None

    def _embed_text(self, text: str) -> list[float]:
        """
        Use the same embedding config as the retrieval flow.
        Falls back safely if config is missing.
        """
        embed_model = getattr(settings, "embedding_model", None) or getattr(settings, "openai_embed_model", None) or "text-embedding-3-small"
        dims = getattr(settings, "embedding_dimensions", None)
        try:
            vecs = self._openai.embed([text], model=embed_model, dimensions=dims)
            return (vecs[0] if vecs else None) or []
        except Exception:
            return []
            
    def _split_question(self, question: str) -> list[str]:
        q = (question or "").strip()
        if not q:
            return []
        parts = [q]

        raw_parts = re.split(r"[\n\r;|/]+|\s+[,]+\s+|\?+|\.+", q)
        for p in raw_parts:
            p = (p or "").strip()
            if len(p) < 4:
                continue

            # avoid near-duplicate that only differs by trailing punctuation
            if re.sub(r"[^\w]+$", "", p.lower()) == re.sub(r"[^\w]+$", "", q.lower()):
                continue
            parts.append(p)

        # de-dup (case-insensitive) + cap
        out, seen = [], set()
        for p in parts:
            k = p.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(p)
        return out[:3]
                
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
            logger.info({"event":"embed_dim", "dim": len(vectors[0]) if vectors else 0, "dims_param": emb_dims})

        if not vectors or len(vectors) != len(chunks):
            logger.error({...})
            return False

        ns = self._namespace(tenant_id, language_code)
        batch_size = 100
        ok_all = True

        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_vecs = vectors[i:i + batch_size]
            payload_vectors: list[dict[str, Any]] = []
            for ch, vec in zip(batch_chunks, batch_vecs):
                payload_vectors.append(
                    {
                        "id": ch.chunk_id,
                        "values": vec,
                        "metadata": {
                            "text": ch.text,
                            "faq_key": ch.faq_key,
                            "chunk_id": ch.chunk_id,
                        },
                    }
                )

            with timed(
                "pinecone_upsert_batch",
                logger=logger, 
                component="kb_vector_service",
                extra={"tenant_id": tenant_id, "namespace": ns, "batch_size": len(payload_vectors)},
            ):
                ok = self._client_for(tenant_id).upsert(vectors=payload_vectors, namespace=ns)
            ok_all = ok_all and ok

        logger.info({
            "component": "kb_vector_service",
            "event": "index_faq ok",})
        return ok_all

    def retrieve(
        self,
        *,
        tenant_id: str,
        language_code: Optional[str],
        question: str,
        top_k: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        if not self.enabled(tenant_id):
            logger.warning({...})
            return []

        q = (question or "").strip()
        if not q:
            return []

        emb_model = getattr(settings, "embedding_model", "text-embedding-3-small")
        emb_dims = getattr(settings, "embedding_dimensions", None)

        queries = self._split_question(q)
        if not queries:
            return []
        with timed(
            "embed_question",
            logger=logger, 
            component="kb_vector_service",
            extra={"tenant_id": tenant_id, "model": emb_model, "queries": len(queries)},
        ):
            q_vecs = self._openai.embed(queries, model=emb_model, dimensions=emb_dims)

        if not q_vecs:
            return []

        ns = self._namespace(tenant_id, language_code)
        k = int(top_k or getattr(settings, "pinecone_top_k", 6) or 6)

        # Run Pinecone queries for each segment and merge matches.
        all_matches = []
        with timed(
            "pinecone_query",
            logger=logger,
            component="kb_vector_service",
            extra={"tenant_id": tenant_id, "namespace": ns, "top_k": k, "queries": len(q_vecs)},
        ):
            for vec in q_vecs:
                if not vec:
                    continue
                matches = self._client_for(tenant_id).query(
                    vector=vec,
                    namespace=ns,
                    top_k=k,
                    include_metadata=True,
                )
                all_matches.extend(matches or [])

        with timed(
            "postprocess_matches",
            logger=logger,
            component="kb_vector_service",
            extra={"tenant_id": tenant_id, "matches": len(all_matches) if all_matches else 0, "queries": len(queries)},
        ):
            # Keep best match per FAQ key to increase result diversity.
            best_by_faq: dict[str, RetrievedChunk] = {}
            for m in all_matches or []:
                md = m.metadata or {}
                txt = (md.get("text") or "").strip()
                if not txt:
                    continue

                faq_key = str(md.get("faq_key") or "").strip()
                chunk_id = str(m.id or "").strip()
                rc = RetrievedChunk(
                    score=float(m.score or 0.0),
                    text=txt,
                    faq_key=faq_key,
                    chunk_id=chunk_id,
                )

                dedupe_key = faq_key or chunk_id
                prev = best_by_faq.get(dedupe_key)
                if (prev is None) or (rc.score > prev.score):
                    best_by_faq[dedupe_key] = rc

            out = sorted(best_by_faq.values(), key=lambda x: x.score, reverse=True)[:k]
 
        logger.info({
            "component": "kb_vector_service",
            "event": "KBVector: retrieved",
            "tenant_id": tenant_id,
            "lang": language_code,
            "queries_used": len(queries),
            "returned": len(out),
        })
        return out
            
    def get_faq_by_key(
        self,
        *,
        tenant_id: str,
        language_code: str,
        faq_key: str,
    ) -> str | None:
        """
        Deterministic lookup by metadata.faq_key (no KB LLM).
        Still uses Pinecone /query, but filtered, so it does not depend on question semantics.
        """
        faq_key = (faq_key or "").strip()
        if not faq_key:
            logger.warning({
                "component": "kb_vector_service",
                "event": "KBVector: get_faq_by_key",
                "tenant_id": tenant_id,
                "language_code": language_code,
                "reason": "faq_key missing",
            })
            return None

        namespace = self._namespace(tenant_id, language_code)
        qvec = self._embed_text(faq_key)
        if not qvec:
            logger.warning({
                "component": "kb_vector_service",
                "event": "KBVector: get_faq_by_key",
                "tenant_id": tenant_id,
                "language_code": language_code,
                "faq_key": faq_key,
                "reason": "no qvec",
            })
            return None

        with timed(
            "faq_by_key_query",
            logger=logger,
            component="kb_vector_service",
            extra={"tenant_id": tenant_id, "lang": language_code, "faq_key": faq_key},
        ):
            matches = self._client_for(tenant_id).query(
                namespace=namespace,
                vector=qvec,
                top_k=1,
                include_metadata=True,
                filter={"faq_key": {"$eq": faq_key}},  # patrz pkt 2
            )

        if not matches:
            logger.warning({
                "component": "kb_vector_service",
                "event": "KBVector: get_faq_by_key",
                "tenant_id": tenant_id,
                "language_code": language_code,
                "faq_key": faq_key,
                "reason": "no match",
            })
            return None
        first = matches[0]
        md = getattr(first, "metadata", {}) or {}
        txt = md.get("text") or ""
        return self._extract_answer_from_text(txt)
        
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
        "You are a helpful customer-support assistant.\n"
        "The user's message may contain multiple questions or topics.\n"
        "Answer ONLY using the knowledge snippets below.\n"
        "- If you can answer at least one part using the snippets, answer the supported part(s) and ignore unsupported parts.\n"
        "- If none of the snippets support any part of the user's message, respond with the exact JSON {\"answer\":\"__NO_INFO__\"} and nothing else.\n"
        "Output MUST be valid JSON with exactly one key: \"answer\". No other keys.\n"
        "Knowledge snippets:\n"
        f"{context}\n"
    )
    if language_code:
        sys += f"\nAnswer in the language {language_code} (ISO language code)."
    else:
        sys += "\nAnswer in the same language as the user's question."
    return sys
