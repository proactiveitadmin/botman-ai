"""
Serwis wiedzy/FAQ.

Odpowiada za pobieranie odpowiedzi FAQ dla danego tenanta:
- w pierwszej kolejności próbuje odczytać dane z S3 (jeśli skonfigurowano bucket),
- jeśli nie ma pliku lub nie ma konfiguracji, korzysta z domyślnego DEFAULT_FAQ.
"""

import json
import re
import time  
import random
from typing import Dict, Optional, List

from botocore.exceptions import ClientError
from .kb_vector_service import KBVectorService, build_kb_prompt

from ..common.logging import logger
from ..repos.tenants_repo import TenantsRepo
from ..domain.templates import DEFAULT_FAQ
from ..common.aws import s3_client
from ..common.config import settings
from ..adapters.openai_client import OpenAIClient


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
        qa_cache_ttl_seconds: int = 3600,
        style_variants_per_answer: int = 3,
    ) -> None:
        #tenants repo
        self.tenants = TenantsRepo()
        # bucket z ENV / Settings
        self.bucket = bucket or settings.kb_bucket

        # cache FAQ z S3: { "tenant#lang": {topic: answer, ...} }
        self._cache: Dict[str, Dict[str, str] | None] = {}

        # cache odpowiedzi Q->A
        # klucz: tenant|lang|normalized_question -> (timestamp, answer)
        self._answer_cache: Dict[str, tuple[float, str]] = {}
        self._answer_cache_ttl = qa_cache_ttl_seconds

        #cache wariantów stylizowanych odpowiedzi per (tenant, lang, tag)
        # key: "tenant|lang|tag" -> ["wersja 1", "wersja 2", ...]
        self._style_variants: Dict[str, List[str]] = {}
        self._style_variants_per_answer = style_variants_per_answer
        
        # klient OpenAI – opcjonalny, żeby w dev/offline dalej działało
        self._client = openai_client or OpenAIClient()
        # vector retrieval (Pinecone). If not configured, KBService falls back to legacy retrieval.
        self._vector = KBVectorService(openai_client=self._client)
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

    # klucz do cache odpowiedzi
    def _answer_cache_key(
        self,
        tenant_id: str,
        language_code: Optional[str],
        question: str,
    ) -> str:
        # mocno znormalizowane pytanie – żeby „Godziny otwarcia?” i „godziny  otwarcia”
        # trafiały pod ten sam klucz
        normalized = re.sub(r"\s+", " ", (question or "").strip().lower())
        lang = (language_code or "unknown").lower()
        return f"{tenant_id}|{lang}|{normalized}"

    # pobranie z cache Q->A z TTL
    def _get_cached_answer(
        self,
        tenant_id: str,
        language_code: Optional[str],
        question: str,
    ) -> Optional[str]:
        if not self._answer_cache_ttl:
            return None

        key = self._answer_cache_key(tenant_id, language_code, question)
        item = self._answer_cache.get(key)
        if not item:
            return None

        ts, answer = item
        if ts + self._answer_cache_ttl < time.time():
            # wygasło – czyścimy
            self._answer_cache.pop(key, None)
            return None

        logger.debug(
            {
                "component": "kb_service",
                "event": "qa_cache_hit",
                "tenant_id": tenant_id,
                "lang": language_code,
            }
        )
        return answer

    # zapis do cache Q->A
    def _store_cached_answer(
        self,
        tenant_id: str,
        language_code: Optional[str],
        question: str,
        answer: str,
    ) -> None:
        if not self._answer_cache_ttl or not answer:
            return
        key = self._answer_cache_key(tenant_id, language_code, question)
        self._answer_cache[key] = (time.time(), answer)
    # -------------------------------------------------------------------------
    #  cache wariantów stylizowanych odpowiedzi
    # -------------------------------------------------------------------------

    def _variants_key(
        self,
        tenant_id: str,
        language_code: Optional[str],
        tag: Optional[str],
    ) -> Optional[str]:
        if not tag:
            return None
        lang = (language_code or "unknown").lower()
        t = tag.strip().lower()
        return f"{tenant_id}|{lang}|{t}"

    def _get_style_variant(
        self,
        tenant_id: str,
        language_code: Optional[str],
        tag: Optional[str],
    ) -> Optional[str]:
        key = self._variants_key(tenant_id, language_code, tag)
        if not key:
            return None

        variants = self._style_variants.get(key)
        if not variants:
            return None

        # losujemy jedną wersję
        return random.choice(variants)

    def _store_style_variants(
        self,
        tenant_id: str,
        language_code: Optional[str],
        tag: Optional[str],
        variants: List[str],
    ) -> None:
        key = self._variants_key(tenant_id, language_code, tag)
        if not key or not variants:
            return

        clean_variants = [v.strip() for v in variants if isinstance(v, str) and v.strip()]
        if not clean_variants:
            return

        # prosty limit globalny
        if len(self._style_variants) > 500:
            self._style_variants.clear()

        self._style_variants[key] = clean_variants
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
            Jeśli nic sensownego nie pasuje, zwraca pełne tenant_faq (fallback).
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
            return tenant_faq

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

        # NEW: szybka ścieżka — powtarzające się pytanie
        cached = self._get_cached_answer(tenant_id, language_code, question)
        if cached is not None:
            logger.info(
                {
                    "component": "kb_service",
                    "event": "cached answer",
                    "cached": cached,
                    "tenant_id": tenant_id,
                    "lang": language_code,
                }
            )
            return cached

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

        # 2) retrieval: prefer Pinecone (vector DB) when configured;
        #    otherwise fall back to legacy keyword-overlap retrieval.
        retrieved_chunks = []
        if self._vector.enabled():
            retrieved_chunks = self._vector.retrieve(
                tenant_id=tenant_id,
                language_code=language_code,
                question=question,
            )

        if retrieved_chunks:
            system_prompt = build_kb_prompt(chunks=retrieved_chunks, language_code=language_code)
        else:
            logger.warning(
                {
                    "component": "kb_service",
                    "event": "no retrieved_chunks",
                    "tenant_id": tenant_id,
                    "lang": language_code,
                    "vector enabled": self._vector.enabled(),
                }
            )
            # legacy retrieval (backward-compatible)
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
                return None

            system_prompt = (
                "You are a helpful assistant for a fitness club.\n"
                "You answer the user's question ONLY using the FAQ entries below.\n"
                "Always respond as a json object with a single key \"answer\".\n"
                "In the \"answer\" value, explain the information in your own words, "
                "If the FAQ does not contain the information needed to answer the question,"
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
 
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
        ]
        logger.info(
            {
                "sender": "temp kb answer ai",
                "tenant_id": tenant_id,
                "history": history,
            }
        )
        # 4) opcjonalna historia rozmowy (user / assistant)
        if history:
            messages.extend(history)
            logger.info(
                {
                    "sender": "temp kb answer ai history",
                    "tenant_id": tenant_id,
                    "history": history,
                }
            )

        # 5) aktualne pytanie
        messages.append(
            {
                "role": "user",
                "content": (
                    f"{question}\n\n"
                    'Respond strictly in json with a single key "answer".'
                ),
            }
        )

        # 6) Wołamy LLM – max_tokens mniejsze niż wcześniej, żeby odpowiedź była szybsza
        try:
            raw = self._client.chat(messages=messages, max_tokens=256)  # było 512
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

        # 7) próbujemy wyciągnąć "answer" z JSON-a
        try:
            data = json.loads(raw)
            ans = data.get("answer")
            if isinstance(ans, str):
                ans = ans.strip()
                # NEW: zapisujemy do cache Q->A
                self._store_cached_answer(tenant_id, language_code, question, ans)
                return ans
        except Exception:
            pass

        # fallback: jeśli model jednak zwrócił czysty tekst
        self._store_cached_answer(tenant_id, language_code, question, raw)
        return raw
   
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
        if not self._vector.enabled():
            return False
        tenant_faq = self._load_tenant_faq(tenant_id=tenant_id, language_code=language_code)
        if not tenant_faq:
            tenant_language = self._tenant_default_lang(tenant_id)
            tenant_faq = self._load_tenant_faq(tenant_id, tenant_language)
            return self._vector.index_faq(tenant_id=tenant_id, language_code=tenant_language, faq=tenant_faq)
        return self._vector.index_faq(tenant_id=tenant_id, language_code=language_code, faq=tenant_faq)
      