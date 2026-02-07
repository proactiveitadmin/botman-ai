"""
Serwis wiedzy/FAQ.

Odpowiada za pobieranie odpowiedzi FAQ dla danego tenanta:
- w pierwszej kolejności próbuje odczytać dane z S3 (jeśli skonfigurowano bucket),
- jeśli nie ma pliku lub nie ma konfiguracji, korzysta z domyślnego DEFAULT_FAQ.
"""

import os
import json
import re
import time  
import random
from typing import Dict, Optional, List

from botocore.exceptions import ClientError
from .kb_vector_service import KBVectorService, build_kb_prompt
from .clients_factory import ClientsFactory
from .tenant_config_service import default_tenant_config_service
from ..common.logging import logger
from ..repos.tenants_repo import TenantsRepo
from ..domain.templates import DEFAULT_FAQ
from ..common.aws import s3_client
from ..common.config import settings
from ..adapters.openai_client import OpenAIClient
from ..common.timing import timed


class KBService:
    """
    Prosty serwis FAQ z opcjonalnym wsparciem S3.

    Przechowuje cache w pamięci (per proces Lambdy) dla zminimalizowania liczby odczytów z S3
    oraz cache gotowych odpowiedzi na najczęściej powtarzające się pytania.
    """

    def __init__(
        self,
        bucket: Optional[str] = None,
        openai_client: Optional[OpenAIClient] = None,
        clients_factory: ClientsFactory | None = None
    ) -> None:
        #tenants repo
        self.tenants = TenantsRepo()
        # bucket z ENV / Settings
        self.bucket = bucket or settings.kb_bucket

        # cache FAQ z S3: { "tenant#lang": {topic: answer, ...} }
        self._cache: Dict[str, Dict[str, str] | None] = {}
        
        # klient OpenAI – opcjonalny, żeby w dev/offline dalej działało
        self._client = openai_client or OpenAIClient()
        # vector retrieval (Pinecone). If not configured, KBService falls back to legacy retrieval.
        self._clients_factory = clients_factory or ClientsFactory()
        self._vector = KBVectorService(
            openai_client=self._client,
            clients_factory=self._clients_factory,
        )
    # -------------------------------------------------------------------------
    # Helpery cache
    # -------------------------------------------------------------------------
    def _tenant_default_lang(self, tenant_id: str) -> str:
        tenant = self.tenants.get(tenant_id) or {}
        return tenant.get("language_code") or settings.get_default_language()

    def _faq_key(self, tenant_id: str, language_code: str | None) -> str:
        # np. "tenantA/faq_pl.json" albo "tenantA/faq_en.json"
        lang = language_code or "en"
        if "-" in lang:
            lang = lang.split("-", 1)[0]
        return f"{tenant_id}/faq_{lang}.json"

    def _cache_key(self, tenant_id: str, language_code: str | None) -> str:
        return f"{tenant_id}#{language_code or 'en'}"


    # -------------------------------------------------------------------------
    # FAQ z S3
    # -------------------------------------------------------------------------

    def _load_tenant_faq(
        self, tenant_id: str, language_code: str | None
    ) -> Optional[Dict[str, str]]:
        """
        Ładuje FAQ dla podanego tenanta z S3 (jeśli skonfigurowano bucket).

        Zwraca:
            dict topic -> answer, jeśli plik istnieje i poprawnie się wczyta,
            None w pozostałych przypadkach.
        """
        if not self.bucket:
            logger.warning(
                {
                    "component": "kb_service",
                    "tenant_id": tenant_id,
                    "warn": "FAQ bucket not found",
                }
            )
            return None

        cache_key = self._cache_key(tenant_id, language_code)
        if cache_key in self._cache:
            return self._cache[cache_key]

        key = self._faq_key(tenant_id, language_code)

        try:
            resp = s3_client().get_object(Bucket=self.bucket, Key=key)
            body = resp["Body"].read().decode("utf-8")
            data = json.loads(body) or {}
            if not isinstance(data, dict):
                data = {}
            # normalizujemy klucze
            normalized = {(k or "").strip().lower(): v for k, v in data.items()}
            self._cache[cache_key] = normalized
            return normalized
        except ClientError as e:
            if e.response["Error"]["Code"] != "NoSuchKey":
                logger.warning(
                    {
                        "component": "kb_service",
                        "tenant_id": tenant_id,
                        "key": key,
                        "err": "s3_get_failed",
                        "error details": str(e),
                    }
                )
            self._cache[cache_key] = None
            return None

    # -------------------------------------------------------------------------
    # Prosty retrieval po FAQ
    # -------------------------------------------------------------------------

    def _select_relevant_faq_entries(
        self,
        question: str,
        tenant_faq: Dict[str, str],
        k: int = 3,
    ) -> Dict[str, str]:
        """
        Bardzo prosty retrieval: wybiera do K najbardziej pasujących wpisów FAQ
        bazując na overlapie słów z pytaniem użytkownika.

        Zwraca:
            dict topic -> answer (maksymalnie K wpisów).
            Jeśli nic sensownego nie pasuje, zwraca pusty dict (caller powinien obsłużyć brak dopasowania).
        """
        q = (question or "").lower()
        q_tokens = set(re.findall(r"\w+", q))

        scored: list[tuple[int, str, str]] = []

        for key, answer in tenant_faq.items():
            if not answer:
                continue

            text = f"{key} {answer}".lower()
            t_tokens = set(re.findall(r"\w+", text))
            overlap = len(q_tokens & t_tokens)

            # mały fallback: pełne pytanie w tekście
            if overlap == 0 and q and q in text:
                overlap = 1

            if overlap > 0:
                scored.append((overlap, key, answer))

        if not scored:
            # brak dopasowania → zachowujemy się jak wcześniej: całe FAQ
            return {}

        scored.sort(key=lambda x: (-x[0], x[1]))

        selected: Dict[str, str] = {}
        for _, key, answer in scored[:k]:
            selected[key] = answer

        return selected

    # -------------------------------------------------------------------------
    # Publiczne API
    # -------------------------------------------------------------------------

    def answer(
        self, topic: str, tenant_id: str, language_code: str | None = None
    ) -> Optional[str]:
        """
        Zwraca odpowiedź FAQ dla danego tematu i tenanta.

        Kolejność źródeł:
          1. FAQ z S3 (jeśli skonfigurowano i plik istnieje),
          2. domyślne DEFAULT_FAQ,
          3. None, jeśli odpowiedź nie została znaleziona.
        """
        topic = (topic or "").strip().lower()
        if not topic:
            return None

        tenant_faq = self._load_tenant_faq(tenant_id, language_code)
        if not tenant_faq:
            tenant_language = self._tenant_default_lang(tenant_id)
            tenant_faq = self._load_tenant_faq(tenant_id, tenant_language)
        if tenant_faq and topic in tenant_faq:
            return tenant_faq[topic]

        # fallback na domyślne (na razie bez wariantów językowych)
        return DEFAULT_FAQ.get(topic)
        
    def answer_by_key(
        self,
        *,
        tenant_id: str,
        language_code: str,
        faq_key: str,
    ) -> str | None:
        """
        Deterministic FAQ answer from Pinecone by metadata faq_key.
        No KB LLM.
        """
        try:
            return self._vector.get_faq_by_key(
                tenant_id=tenant_id,
                language_code=language_code,
                faq_key=faq_key,
            )
        except Exception as e:
            logger.error(
                {
                    "component": "kb_service",
                    "event": "answer_by_key_failed",
                    "tenant_id": tenant_id,
                    "lang": language_code,
                    "faq_key": faq_key,
                    "err": str(e),
                }
            )
            return None

    def answer_ai(
        self,
        *,
        question: str,
        tenant_id: str,
        language_code: Optional[str] = None,
        history: list[dict] | None = None,
    ) -> Optional[str]:
        """
        Generuje odpowiedź na pytanie użytkownika na podstawie FAQ tenanta
        z użyciem LLM (OpenAIClient).

        - wybiera kilka najbardziej pasujących wpisów FAQ (retrieval),
        - opcjonalnie dokleja historię rozmowy (user/assistant),
        - oczekuje JSON-a {"answer": "..."} i zwraca sam tekst odpowiedzi.
        """
        question = (question or "").strip()
        if not question:
            return None
           
        top1 = 0.0
        top2 = 0.0
        gap = 0.0
        strict_mode = False
            
        # 2) retrieval: prefer Pinecone (vector DB) when configured.
        vector_enabled = self._vector.enabled(tenant_id)
        retrieved_chunks = []
        if vector_enabled:
            retrieved_chunks = self._vector.retrieve(
                tenant_id=tenant_id,
                language_code=language_code,
                question=question,
            )

            # Vector confidence gating:
            # - no matches OR very low score -> deterministic fallback WITHOUT calling the KB LLM
            # - mid score -> call LLM in a STRICT mode (must return a sentinel when unsure)
            # - high score -> normal KB LLM (still constrained to provided snippets)
            try:
                low_threshold = float(os.getenv("KB_VECTOR_MIN_SCORE_LOW", "0.3"))
            except Exception:
                low_threshold = 0.3

            try:
                high_threshold = float(os.getenv("KB_VECTOR_MIN_SCORE", "0.72"))
            except Exception:
                high_threshold = 0.72

            # NEW: gap thresholds (tunable)
            try:
                gap_high = float(os.getenv("KB_VECTOR_GAP_HIGH", "0.10"))
            except Exception:
                gap_high = 0.10

            try:
                gap_strict = float(os.getenv("KB_VECTOR_GAP_STRICT", "0.12"))
            except Exception:
                gap_strict = 0.12

            try:
                top1_high_min = float(os.getenv("KB_VECTOR_TOP1_HIGH_MIN", "0.65"))
            except Exception:
                top1_high_min = 0.65

            try:
                top1_strict_min = float(os.getenv("KB_VECTOR_TOP1_STRICT_MIN", "0.55"))
            except Exception:
                top1_strict_min = 0.55

        
            if retrieved_chunks:
                try:
                    top1 = float(getattr(retrieved_chunks[0], "score", 0.0) or 0.0)
                except Exception:
                    top1 = 0.0
                if len(retrieved_chunks) > 1:
                    try:
                        top2 = float(getattr(retrieved_chunks[1], "score", 0.0) or 0.0)
                    except Exception:
                        top2 = 0.0
                gap = max(0.0, top1 - top2)

            if (not retrieved_chunks):
                return None

            if top1 < low_threshold:
                strict_mode = True

            #treat as high confidence even if top1 < high_threshold
            force_high = (top1 >= top1_high_min and gap >= gap_high)

            # if it would fall below_low, but it's clearly the best vs #2,
            # do NOT return None; instead go strict LLM.
            force_strict = (top1 >= top1_strict_min and gap >= gap_strict)

            logger.info({
                "component": "kb_service",
                "event": "vector_scores",
                "tenant_id": tenant_id,
                "lang": language_code,
                "matches": len(retrieved_chunks) if retrieved_chunks else 0,
                "top1": top1,
                "top2": top2,
                "gap": gap,
                "low_threshold": low_threshold,
                "high_threshold": high_threshold,
                "force_high": force_high,
                "force_strict": force_strict,
            })

            # Decide strict_mode:
            # - If force_high -> not strict
            # - Else strict if top1 < high_threshold OR force_strict explicitly
            if force_high:
                strict_mode = False
            else:
                strict_mode = (strict_mode or force_strict or (top1 < high_threshold))


        # FAST PATH: if vector retrieval returns chunks that already include "A: ...",
        # return the best-match answer directly and avoid an extra LLM call.
        if retrieved_chunks:
            # FAST-PATH safety: only return a direct FAQ answer when similarity is high.
            # Otherwise fall back to LLM synthesis / explicit "no info" response.
            try:
                min_score = float(os.getenv("KB_VECTOR_FASTPATH_MIN_SCORE", "0.70"))
            except Exception:
                min_score = 0.70

            max_fastpath = 2  # keep latency predictable
            for idx, best in enumerate((retrieved_chunks or [])[:max_fastpath]):  
                best_score = getattr(best, "score", 0.0) or 0.0
                # reuse gap computed earlier
                if best_score < min_score:
                    continue

                # Extract the answer portion from the chunk (chunk_faq uses "Q:" and "A:").
                txt = (best.text or "").strip()
                if not txt:
                    continue
                    
                m = re.search(r"\n\s*A:\s*(.*)$", txt, flags=re.IGNORECASE | re.DOTALL)
                if m:
                    ans = (m.group(1) or "").strip()
                else:
                    # Fallback: try split on 'A:' if newlines differ
                    parts = re.split(r"\bA:\s*", txt, maxsplit=1, flags=re.IGNORECASE)
                    ans = parts[1].strip() if len(parts) == 2 else ""
                if not ans:
                    continue
                if ans == "__NO_INFO__":
                    logger.info(
                        {
                            "component": "kb_service",
                            "event": "fastpath_skip_no_info_chunk",
                            "tenant_id": tenant_id,
                            "lang": language_code,
                            "band": "mid",
                        }
                    )
                    continue
                logger.info(
                    {
                        "component": "kb_service",
                        "event": "returns fastpath answer",
                        "tenant_id": tenant_id,
                        "lang": language_code,
                        "ans": ans,
                    }
                )
                if ans and ans != "__NO_INFO__":
                    return ans

            system_prompt = build_kb_prompt(chunks=retrieved_chunks, language_code=language_code)
            if strict_mode:
                system_prompt += (        
                    "\n\nThe user's message may contain multiple questions or topics. "
                    "Answer using ONLY the provided snippets.\n"
                    "- If you can answer at least one part, provide an answer for the part(s) supported by snippets and ignore unsupported parts.\n"
                    "- If none of the snippets support any part of the user's message, respond with the exact JSON "
                    "{\"answer\": \"__NO_INFO__\"} and nothing else."
                )
        else:
            # legacy retrieval (backward-compatible)
            logger.warning(
                {
                    "component": "kb_service",
                    "event": "no retrieved_chunks",
                    "tenant_id": tenant_id,
                    "lang": language_code,
                    "vector_enabled": vector_enabled,
                }
            )
            
            # 1) FAQ z S3 lub domyślne
            tenant_faq = self._load_tenant_faq(tenant_id, language_code)
            if not tenant_faq:
                tenant_language = self._tenant_default_lang(tenant_id)
                tenant_faq = self._load_tenant_faq(tenant_id, tenant_language)
            if not tenant_faq:
                logger.warning(
                    {
                        "component": "kb_service",
                        "event": "no FAQ used default",
                        "tenant_id": tenant_id,
                        "lang": language_code,
                    }
                )
                tenant_faq = DEFAULT_FAQ

            if not tenant_faq:
                return None
                
            relevant_faq = self._select_relevant_faq_entries(
                question=question,
                tenant_faq=tenant_faq,
                k=3,
            )

            # build Q/A context
            lines: list[str] = []
            for key, answer in relevant_faq.items():
                if not answer:
                    continue
                lines.append(f"Q: {key}")
                lines.append(f"A: {answer}")
            faq_context = "\n".join(lines)

            if not faq_context:
                # brak dopasowania w FAQ -> nie przekazujemy całej bazy do modelu
                # (to powoduje halucynacje lub odpowiedzi grzecznościowe).
                faq_context = ""

            system_prompt = (
                "You are a helpful customer-support assistant.\n"
                "Answer the user's question ONLY using the FAQ entries below.\n"
                "Always respond as a JSON object with a single key \"answer\".\n"
                "In the \"answer\" value, paraphrase the relevant information. "
                "If the FAQ does not contain the information needed to answer the question, "
                "reply that you don't know AND ask the user if there is anything else you can help with.\n"
                "FAQ entries:\n"
                f"{faq_context}\n"
            )

            if language_code:
                system_prompt += (
                    f"\nAnswer in the language {language_code} (ISO language code)."
                )
            else:
                system_prompt += "\nAnswer in the same language as the user's question."
 
        with timed(
            "prompt_build",
            logger=logger,
            component="kb_service",
            extra={
                "tenant_id": tenant_id,
                "lang": language_code,
            },
        ):
            messages: list[dict] = [
                {"role": "system", "content": system_prompt},
            ]
            # 4) opcjonalna historia rozmowy (user / assistant)
            if history:
                history = [m for m in history if m.get("role") == "user"]
            if history:
                messages.extend(history)

            # 5) aktualne pytanie
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"{question}\n\n"
                        'Respond strictly in JSON with a single key "answer".'
                    ),
                }
            )

        # Emit prompt_size as a separate log field (measured after building messages).
        try:
            prompt_chars = sum(len(str(m.get("content") or "")) for m in messages)
            logger.warning(
                {
                    "component": "kb_service",
                    "event": "prompt_size",
                    "tenant_id": tenant_id,
                    "lang": language_code,
                    "prompt_size_chars": prompt_chars,
                    "prompt_messages": len(messages),
                }
            )
        except Exception:
            pass

        # 6) Wołamy LLM – max_tokens mniejsze niż wcześniej, żeby odpowiedź była szybsza
        try:
            raw = self._client.chat(messages=messages, max_tokens=512)  # było 512
        except Exception as e:
            logger.error(
                {
                    "sender": "kb_ai_failed",
                    "tenant_id": tenant_id,
                    "err": str(e),
                }
            )
            return None
        
        if not raw:
            return None

        raw = raw.strip()
        if raw == "__NO_INFO__":
            logger.info(
                {
                    "component": "kb_service",
                    "event": "kb_llm_no_info",
                    "tenant_id": tenant_id,
                    "lang": language_code,
                    "band": "mid",
                }
            )
            return None

        # 7) próbujemy wyciągnąć "answer" z JSON-a
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                if "answer" in data:
                    ans = data.get("answer")
                    if isinstance(ans, str):
                        ans = ans.strip()
                        if ans == "__NO_INFO__":
                            return None
                        return ans
                    return None
                parts = []
                for v in data.values():
                    if isinstance(v, str):
                        v = v.strip()
                        if v and v != "__NO_INFO__":
                            parts.append(v)
                if parts:
                    return "\n".join(parts)
                return None

        except Exception:
            return None

        return None
        
    def list_faq_keys(self, tenant_id: str, language_code: str) -> set[str]:
        faq = self._load_tenant_faq(tenant_id, language_code) or {}
        if not faq:
            tenant_language = self._tenant_default_lang(tenant_id)
            faq = self._load_tenant_faq(tenant_id, tenant_language) or {}
        if not faq:
            faq = DEFAULT_FAQ or {}
        return set(faq.keys())
    
    
    # -------------------------------------------------------------------------
    # Vector indexing helpers (optional)
    # -------------------------------------------------------------------------
    def reindex_faq(
        self,
        *,
        tenant_id: str,
        language_code: Optional[str] = None,
    ) -> bool:
        """Load tenant FAQ and push it to Pinecone (chunking + embeddings + upsert).

        Safe to call multiple times. If vector mode is disabled, returns False.
        """
        if not self._vector.enabled(tenant_id):
            return False
        tenant_faq = self._load_tenant_faq(tenant_id=tenant_id, language_code=language_code)
        if not tenant_faq:
            tenant_language = self._tenant_default_lang(tenant_id)
            tenant_faq = self._load_tenant_faq(tenant_id, tenant_language)
            return self._vector.index_faq(tenant_id=tenant_id, language_code=tenant_language, faq=tenant_faq)
        return self._vector.index_faq(tenant_id=tenant_id, language_code=language_code, faq=tenant_faq)
      