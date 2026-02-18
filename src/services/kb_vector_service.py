"""Vector-based KB retrieval and indexing (FAQ -> embeddings -> Pinecone)."""

from __future__ import annotations
import re
import os, time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..common.config import settings
from ..common.logging_utils import logger
from ..common.text_chunking import chunk_faq
from ..adapters.openai_client import OpenAIClient
from ..adapters.pinecone_client import PineconeClient
from .clients_factory import ClientsFactory

from ..common.timing import timed
from ..common.constants import (
    QUESTION_SPLIT_REGEX,
    QUESTION_NO_OF_PARTS,
    PC_NAME_KB,
)


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
                logger.warning({
                  "component": "kb_vector_service",
                  "event": "kb_vector_enabled False",
                })
                return False
            pc = self._client_for(tenant_id)          
            logger.warning({
              "component": "kb_vector_service",
              "event": "enabled_check",
              "tenant_id": tenant_id,
              "has_api_key": bool(getattr(pc, "api_key", "")),
              "index_host": (getattr(pc, "index_host", "") or ""),
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
        lang = (language_code or "").strip() or "en"
        prefix = getattr(settings, "pinecone_namespace_prefix", PC_NAME_KB) or PC_NAME_KB
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
            logger.warning({
              "component": "kb_vector_service",
              "event": "openai embed failed",
              "text": text,
            })
            return []
            
    def _split_question(self, question: str) -> list[str]:
        q = (question or "").strip()
        if not q:
            return []

        # zawsze zachowaj pełne pytanie
        parts: List[str] = [q]

        norm = re.sub(r"\s+", " ", q).strip()

        # split po mocnych separatorach; przecinek zostawiamy jako "miękki"
        split_re = re.compile(
            r"(?:[\n\r]+)|(?:\s*[;|/]\s*)|(?:\s*(?:\?+|!+|\.{2,})\s*)",
            re.UNICODE,
        )
        raw = [p.strip() for p in split_re.split(norm) if (p or "").strip()]

        def token_count(s: str) -> int:
            return len(re.findall(r"\w+", s, flags=re.UNICODE))

        def too_thin(s: str) -> bool:
            # "cienkie" = słabe jako osobne zapytanie wektorowe; nie usuwamy, tylko scalamy
            tc = token_count(s)
            if tc == 0:
                return True
            if tc == 1:
                w = re.findall(r"\w+", s, flags=re.UNICODE)[0]
                has_digit = any(ch.isdigit() for ch in w)
                is_acronymish = (len(w) <= 6 and w.upper() == w and any(ch.isalpha() for ch in w))
                longish = len(w) >= 6
                return not (has_digit or is_acronymish or longish)
            return False

        merged: List[str] = []
        for seg in raw:
            if not merged:
                merged.append(seg)
                continue
            if too_thin(seg):
                merged[-1] = f"{merged[-1]} {seg}".strip()
            else:
                merged.append(seg)

        # de-dup + cap
        out, seen = [], set()
        for seg in [q] + merged:
            k = seg.lower()
            k = re.sub(r"[^\w]+$", "", k, flags=re.UNICODE).strip()
            if not k or k in seen:
                continue
            seen.add(k)
            out.append(seg)
            if seg != q:
                logger.warning({"event": "_split_question", "part": seg})

        return out[:QUESTION_NO_OF_PARTS]    
        
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
            logger.warning({
              "component": "kb_vector_service",
              "event": "vector service not enabled",
              "tenant_id": tenant_id,
              "language_code": language_code,
            })
            return False

        with timed(
            "chunk_faq",
            logger=logger, 
            component="kb_vector_service",
            extra={"tenant_id": tenant_id, "max_chars": max_chars},
        ):
            chunks = chunk_faq(faq, max_chars=max_chars)
        
        logger.warning({"event":"chunk_faq_done","chunks":len(chunks),"sample":chunks[0].text[:80] if chunks else None})

        if not chunks:
            logger.warning({
              "component": "kb_vector_service",
              "event": "index FAQ no chunks",
              "tenant_id": tenant_id,
              "language_code": language_code,
            })
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
            logger.error({
                "event": "index_faq error",
                "len(vectors)": len(vectors),
                "len(chunks)": len(chunks),
            })
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
                            "lang": ((language_code or "").strip() or "en"),
                            "category": getattr(ch, "category", PC_NAME_KB),
                            # Optional: helps prevent mixing when you migrate embedding models
                            "embed_model": getattr(settings, "embedding_model", "") or "",

                        },
                    }
                )
            logger.warning({
              "event": "upsert_payload_meta_sample",
              "namespace": ns,
              "meta": payload_vectors[0].get("metadata") if payload_vectors else None,
            })
            with timed(
                "pinecone_upsert_batch",
                logger=logger, 
                component="kb_vector_service",
                extra={"tenant_id": tenant_id, "namespace": ns, "batch_size": len(payload_vectors)},
            ):
                logger.warning({
                  "event": "upsert_sample_meta",
                  "namespace": ns,
                  "chunk_id": chunks[0].chunk_id if chunks else None,
                  "faq_key": chunks[0].faq_key if chunks else None,
                  "category": getattr(chunks[0], "category", None) if chunks else None,
                })

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
        category: str | None = None,
        top_k: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        if not self.enabled(tenant_id):
            logger.warning({
              "component": "kb_vector_service",
              "event": "vector service not enabled",
              "tenant_id": tenant_id,
              "language_code": language_code,
            })
            return []

        q = (question or "").strip()
        if not q:
            logger.warning({
              "component": "kb_vector_service",
              "event": "strip question empty",
              "tenant_id": tenant_id,
              "language_code": language_code,
              "question": question,
            })
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
            logger.warning({
              "component": "kb_vector_service",
              "event": "embed returns nothing",
              "tenant_id": tenant_id,
              "language_code": language_code,
              "question": question,
            })
            return []

        ns = self._namespace(tenant_id, language_code)
        k = int(top_k or getattr(settings, "pinecone_top_k", 6) or 6)
        lang = (language_code or "").strip() or "en"

        # Run Pinecone queries for each segment and merge matches.
        all_matches = []
        with timed(
            "pinecone_query",
            logger=logger,
            component="kb_vector_service",
            extra={"tenant_id": tenant_id, "namespace": ns, "top_k": k, "queries": len(q_vecs)},
        ):
            for vec in q_vecs:
                logger.info({
                    "component": "kb_vector_service",
                    "event": "retrieve_debug",
                    "namespace": ns,
                    "category": category,
                })
                if vec is None:
                    continue
                filtr = {"lang": {"$eq": lang}}

                if category:
                    filtr["category"] = {"$eq": category}
                matches = self._client_for(tenant_id).query(
                    vector=vec,
                    namespace=ns,
                    top_k=k,
                    include_metadata=True,
                    filter=filtr
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
                logger.info({
                    "faq_key": faq_key,
                })
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
            
    def build_kb_prompt( self, 
        chunks: List[RetrievedChunk],
        language_code: Optional[str],
        strict_mode: bool,
    ) -> str:
        """Prompt template for KB answering.

        We keep the legacy contract: assistant must return JSON {"answer": "..."}.
        """
        if chunks:
            lines: List[str] = []
            for i, ch in enumerate(chunks, start=1):
                lines.append(f"[C{i}] {ch.text}")

            context = "\n\n".join(lines).strip()
        else:
            context = ""
        
        return self._openai.build_kb_prompt(strict_mode, language_code, context)
        
