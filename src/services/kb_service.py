"""
Serwis wiedzy/FAQ.

Odpowiada za pobieranie odpowiedzi FAQ dla danego tenanta:
- w pierwszej kolejności próbuje odczytać dane z S3 (jeśli skonfigurowano bucket),
- jeśli nie ma pliku lub nie ma konfiguracji, korzysta z domyślnego DEFAULT_FAQ.
"""

import json
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
        question: str,
        tenant_id: str,
        language_code: Optional[str] = None,
    ) -> Optional[str]:
        """
        Generuje odpowiedź na pytanie użytkownika na podstawie FAQ tenanta
        z użyciem LLM (OpenAIClient).

        Zwraca:
          - wygenerowaną odpowiedź (str), jeśli się uda,
          - None, jeśli nie ma FAQ albo LLM nie jest dostępne.
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

        # 2) Zbuduj kontekst FAQ jako lista Q/A
        lines: list[str] = []
        for key, answer in tenant_faq.items():
            if not answer:
                continue
            # key traktujemy jak "temat" / pytanie nagłówkowe
            lines.append(f"Q: {key}")
            lines.append(f"A: {answer}")
        faq_context = "\n".join(lines)

        if not faq_context:
            return None

        # 3) System prompt – twarde ograniczenie do FAQ
        system_prompt = (
            "You are a helpful assistant for a fitness club.\n"
            "You answer the user's question ONLY using the FAQ entries below.\n"
            "Always respond as a json object with a single key \"answer\".\n"
            "In the \"answer\" value, explain the information in your own words, "
            "based on the FAQ, and do not copy any FAQ entry verbatim unless absolutely necessary.\n"
            "If the FAQ does not contain the information, set \"answer\" to a brief sentence "
            "that the information is not available and suggest contacting staff.\n\n"
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

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"{question}\n\n"
                    "Respond strictly in json with a single key \"answer\"."
                ),
            },
        ]


        # 4) Wołamy LLM z retry (OpenAIClient.chat ma w sobie retry + fallback)
        try:
            raw = self._client.chat(messages, max_tokens=512)
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
        try:
            data = json.loads(raw)
            # Oczekujemy {"answer": "..."}
            ans = data.get("answer")
            if isinstance(ans, str):
                return ans.strip()
        except Exception:
            # jeśli model wypluje jednak czysty tekst, nie-json – użyj jak jest
            pass

        return raw
