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
from .kb_vector_service import KBVectorService
from .clients_factory import ClientsFactory
from .tenant_config_service import default_tenant_config_service
from ..common.logging import logger
from ..repos.tenants_repo import TenantsRepo
from ..domain.templates import DEFAULT_FAQ
from ..common.aws import s3_client
from ..common.config import settings
from ..adapters.openai_client import OpenAIClient
from ..common.timing import timed
from ..common.constants import (
    STR_CHUNK_SCORE,
    ANSWER_NO_INFO,
    PC_NAME_SMALLTALK,
    PC_NAME_KB,
    FAQ_ANSWER_KEY,
    KB_RETRIEVED_CHUNKS,
    SMALLTALK_RETRIEVED_CHUNKS,
    KB_FETCHED_CHUNKS,
    SMALLTALK_SEARCH_REGEX,
    FAQ_FIND_REGEX,
    SMALLTALK_SUB1_REGEX,
    SMALLTALK_SUB2_REGEX,
    FASTPATCH_SEARCH_REGEX,
    FASTPATCH_SPLIT_REGEX,
    FAQ_MSG_JSON,
    FAQ_ROLE_USER,
    FAQ_NO_KEY_ERR,
)


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
    # Helpery 
    # -------------------------------------------------------------------------
    def _tenant_kb_params(self, tenant_id: str) -> str:
        tenant = self.tenants.get_kb_config(tenant_id)
        return tenant.get("kb_parameters") or settings.get_default_language()
        
    def _tenant_default_lang(self, tenant_id: str) -> str:
        return self.tenants.get_language(tenant_id)

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
            if isinstance(data.get("entries"), list):
                # new format: keep as-is
                self._cache[cache_key] = data
                return data
            normalized = {(k or "").strip().lower(): v for k, v in data.items()}
            self._cache[cache_key] = normalized
            return normalized
        except ClientError as e:
            if e.response["Error"]["Code"] != FAQ_NO_KEY_ERR:
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
            t_tokens = set(re.findall(FAQ_FIND_REGEX, text))
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
        
    def _is_smalltalk_only(self, q: str) -> bool:
        q = (q or "").strip()
        if not q:
            return False
        if "?" in q:
            return False
        tokens = re.findall(FAQ_FIND_REGEX, q, flags=re.UNICODE)
        if len(tokens) > 2:
            return False
        # jeśli są przecinki/średniki i jest więcej treści, to raczej nie smalltalk-only
        if re.search(SMALLTALK_SEARCH_REGEX, q) and len(tokens) > 1:
            return False
        return True

    def _norm(self, s: str) -> str:
        s = (s or "").strip().lower()
        # usuń trailing interpunkcję i zredukuj spacje
        s = re.sub(SMALLTALK_SUB1_REGEX, "", s, flags=re.UNICODE)
        s = re.sub(SMALLTALK_SUB2_REGEX, " ", s).strip()
        return s
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
        - oczekuje JSON-a {FAQ_ANSWER_KEY: "..."} i zwraca sam tekst odpowiedzi.
        """
        question = (question or "").strip()
        if not question:
            return None
           
        top1 = 0.0
        top2 = 0.0
        gap = 0.0
        strict_mode = False
        chunks_for_prompt = []
        retrieved_chunks = []
            
        # 2) retrieval: prefer Pinecone (vector DB) when configured.
        vector_enabled = self._vector.enabled(tenant_id)
        if vector_enabled:
            # 0) smalltalk fast-path (NO LLM)
            #1--------------
            st = self._vector.retrieve(
                tenant_id=tenant_id,
                language_code=language_code,
                question=question,
                category=PC_NAME_SMALLTALK,
                top_k=SMALLTALK_RETRIEVED_CHUNKS,
            )

            if st:
                if self._is_smalltalk_only(question):
                    qn = self._norm(question)
                    txt0 = (st[0].text or "").strip()

                    # 1) deterministic: czy w chunku jest dokładnie takie Q: ?
                    qs = re.findall(r"^\s*Q:\s*(.+)$", txt0, flags=re.IGNORECASE | re.MULTILINE)
                    if any(self._norm(qline) == qn for qline in qs):
                        ans = self._vector._extract_answer_from_text(txt0)  # albo lokalnie ten sam regex na A:
                        if ans:
                            return ans

                    # 2) dopiero potem próg score (fallback)
                    st_top1 = float(getattr(st[0], "score", 0.0) or 0.0)
                    st_min = self.tenants.get_kb_smalltalk_min_score(tenant_id)
                    if st_top1 >= st_min:
                        ans = self._vector._extract_answer_from_text(txt0)
                        if ans:
                            return ans
            #1--------------
                chunks_for_prompt += st[:1]
            if chunks_for_prompt and self._is_smalltalk_only(question):
                retrieved_chunks = []
            else:
                retrieved_chunks = self._vector.retrieve(
                    tenant_id=tenant_id,
                    language_code=language_code,
                    question=question,
                    category=PC_NAME_KB,
                    top_k=KB_RETRIEVED_CHUNKS,
                )

            # Vector confidence gating:
            strict_threshold = self.tenants.get_kb_vector_min_score_low(tenant_id)
       
            if retrieved_chunks:
                try:
                    top1 = float(getattr(retrieved_chunks[0], STR_CHUNK_SCORE, 0.0) or 0.0)
                except Exception:
                    top1 = 0.0
                if len(retrieved_chunks) > 1:
                    try:
                        top2 = float(getattr(retrieved_chunks[1], STR_CHUNK_SCORE, 0.0) or 0.0)
                    except Exception:
                        top2 = 0.0
                gap = max(0.0, top1 - top2)
                if top1 < strict_threshold:
                    strict_mode = True
                logger.info({
                    "component": "kb_service",
                    "event": "vector_scores",
                    "tenant_id": tenant_id,
                    "lang": language_code,
                    "matches": len(retrieved_chunks) if retrieved_chunks else 0,
                    "top1": top1,
                    "top2": top2,
                    "gap": gap,
                    "strict_threshold": strict_threshold,
                })
            if not retrieved_chunks and not chunks_for_prompt:
                logger.info({"component":"kb_service","event":"no_chunks_smalltalk_and_kb"})

            if not retrieved_chunks and chunks_for_prompt:
                logger.info({"component":"kb_service","event":"kb_empty_using_smalltalk_only", })

        # FAST PATH: if vector retrieval returns chunks that already include "A: ...",
        # return the best-match answer directly and avoid an extra LLM call.
        if retrieved_chunks:
            #2--------------
            # FAST-PATH safety: only return a direct FAQ answer when similarity is high.
            # Otherwise fall back to LLM synthesis / explicit "no info" response.
            for i, ch in enumerate(retrieved_chunks[:KB_RETRIEVED_CHUNKS], start=1):
                logger.warning({
                    "component": "kb_service",
                    "event": "retrieved_top",
                    "rank": i,
                    "score": getattr(ch, "score", None),
                    "faq_key": getattr(ch, "faq_key", None),
                    "text[:200]": (getattr(ch, "text", "") or "")[:200],
                })

            min_score  = self.tenants.get_kb_vector_fastpath_min_score(tenant_id)

            for idx, best in enumerate((retrieved_chunks or [])[:KB_FETCHED_CHUNKS]):  

                best_score = getattr(best, STR_CHUNK_SCORE, 0.0) or 0.0
                # reuse gap computed earlier
                if best_score < min_score:
                    continue

                # Extract the answer portion from the chunk (chunk_faq uses "Q:" and "A:").
                txt = (best.text or "").strip()
                if not txt:

                    continue
                    
                m = re.search(FASTPATCH_SEARCH_REGEX, txt, flags=re.IGNORECASE | re.DOTALL)
                if m:
                    ans = (m.group(1) or "").strip()
                else:
                    # Fallback: try split on 'A:' if newlines differ
                    parts = re.split(FASTPATCH_SPLIT_REGEX, txt, maxsplit=1, flags=re.IGNORECASE)
                    ans = parts[1].strip() if len(parts) == 2 else ""
                if not ans:                

                    continue
                if ans == ANSWER_NO_INFO:
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
                if ans and ans != ANSWER_NO_INFO:
                    return ans
            #2--------------        
            chunks_for_prompt += retrieved_chunks
        if chunks_for_prompt and self._is_smalltalk_only(question):
            strict_mode = True
        if chunks_for_prompt:
            system_prompt = self._vector.build_kb_prompt(chunks=chunks_for_prompt, language_code=language_code, strict_mode=strict_mode)
        else:
            return None
            
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
            if history:
                history = [m for m in history if m.get("role") == "user"]
                messages.extend(history)

            # 5) aktualne pytanie
            question_content = f"{question}\n\n"
            question_content += FAQ_MSG_JSON
            
            messages.append(
                {
                    "role": FAQ_ROLE_USER,
                    "content": question_content,
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

        # 6) Wołamy LLM
        try:
            raw = self._client.chat(messages=messages, max_tokens=512)
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
        if raw == ANSWER_NO_INFO:
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

        # 7) próbujemy wyciągnąć FAQ_ANSWER_KEY z JSON-a
        #4--------------
        try:
            logger.info(
                {
                    "component": "kb_service",
                    "event": FAQ_ANSWER_KEY,
                    "raw[:200]": raw[:200],
                }
            )
            data = json.loads(raw)
            if isinstance(data, dict):
                if FAQ_ANSWER_KEY in data:
                    ans = data.get(FAQ_ANSWER_KEY)
                    if isinstance(ans, str):
                        ans = ans.strip()
                        if ans == ANSWER_NO_INFO:
                            return None
                        return ans
                    return None
                parts = []
                for v in data.values():
                    if isinstance(v, str):
                        v = v.strip()
                        if v and v != ANSWER_NO_INFO:
                            parts.append(v)
                if parts:
                    return "\n".join(parts)
                return None

        except Exception:
            return None
        #4--------------
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
      
    def normalize_ai_answer(self, text: str) -> str | None:
        if text.lstrip().startswith("{"):
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    if isinstance(data.get(FAQ_ANSWER_KEY), str):
                        body = data[FAQ_ANSWER_KEY].strip()
                    else:
                        parts = []
                        for v in data.values():
                            if isinstance(v, str):
                                v = v.strip()
                                if v and v != ANSWER_NO_INFO:
                                    parts.append(v)
                        body = "\n".join(parts) if parts else None
            except Exception:
                body = None
        else:    
            body = text
        return body