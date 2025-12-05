"""
Serwis wiedzy/FAQ.

Odpowiada za pobieranie odpowiedzi FAQ dla danego tenanta:
- w pierwszej kolejności próbuje odczytać dane z S3 (jeśli skonfigurowano bucket),
- jeśli nie ma pliku lub nie ma konfiguracji, korzysta z domyślnego DEFAULT_FAQ.
"""

import json
import re
from typing import Dict, Optional

from botocore.exceptions import ClientError

from ..common.logging import logger
from ..domain.templates import DEFAULT_FAQ
from ..common.aws import s3_client
from ..common.config import settings
from ..adapters.openai_client import OpenAIClient



class KBService:
    """
    Prosty serwis FAQ z opcjonalnym wsparciem S3.

    Przechowuje cache w pamięci (per proces Lambdy) dla zminimalizowania liczby odczytów z S3.
    """

    def __init__(
        self,
        bucket: Optional[str] = None,
        openai_client: Optional[OpenAIClient] = None,
    ) -> None:
        # bucket z ENV / Settings
        self.bucket = bucket or settings.kb_bucket
        self._cache: Dict[str, Dict[str, str]] = {}

        # klient OpenAI – opcjonalny, żeby w dev/offline dalej działało
        self._client = openai_client or OpenAIClient() 
    
    def _faq_key(self, tenant_id: str, language_code: str | None) -> str:
        # np. "tenantA/faq_pl.json" albo "tenantA/faq_en.json"
        lang = language_code or "en"
        if "-" in lang:
            lang = lang.split("-", 1)[0]
        return f"{tenant_id}/faq_{lang}.json"

    def _cache_key(self, tenant_id: str, language_code: str | None) -> str:
        return f"{tenant_id}/{language_code or 'default'}"
        
    def _load_tenant_faq(self, tenant_id: str, language_code: str | None) -> Optional[Dict[str, str]]:
        """
        Ładuje FAQ dla podanego tenanta z S3 (jeśli skonfigurowano bucket).

        Zwraca:
            dict topic -> answer, jeśli plik istnieje i poprawnie się wczyta,
            None w pozostałych przypadkach.
        """
        if not self.bucket:
            return None

        cache_key = f"{tenant_id}#{language_code or 'en'}"
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
            normalized = { (k or "").strip().lower(): v for k, v in data.items() }
            self._cache[cache_key] = normalized
            return normalized
        except ClientError as e:
            if e.response["Error"]["Code"] != "NoSuchKey":
                logger.warning(
                    {"kb_error": "s3_get_failed", "tenant_id": tenant_id, "key": key, "err": str(e)}
                )
            self._cache[cache_key] = None
            return None
            
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

    def answer(self, topic: str, tenant_id: str, language_code: str | None = None) -> Optional[str]:
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

        # 1) FAQ z S3 lub domyślne
        tenant_faq = self._load_tenant_faq(tenant_id, language_code)
        if not tenant_faq:
            tenant_faq = DEFAULT_FAQ

        if not tenant_faq:
            return None

        # 2) wybierz kilka wpisów FAQ pasujących do pytania
        relevant_faq = self._select_relevant_faq_entries(
            question=question,
            tenant_faq=tenant_faq,
            k=3,
        )

        # 3) zbuduj kontekst FAQ jako Q/A
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
            "in the same language as the user's question.\n"
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
            system_prompt += (
                "\nAnswer in the same language as the user's question."
            )

        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
        ]

        # 4) opcjonalna historia rozmowy (user / assistant)
        if history:
            messages.extend(history)

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

        # 6) Wołamy LLM – UWAGA: BEZ self.model
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

        # 7) próbujemy wyciągnąć "answer" z JSON-a
        try:
            data = json.loads(raw)
            ans = data.get("answer")
            if isinstance(ans, str):
                return ans.strip()
        except Exception:
            pass

        # fallback: jeśli model jednak zwrócił czysty tekst
        return raw


