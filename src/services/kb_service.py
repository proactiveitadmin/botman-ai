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


class KBService:
    """
    Prosty serwis FAQ z opcjonalnym wsparciem S3.

    Przechowuje cache w pamięci (per proces Lambdy) dla zminimalizowania liczby odczytów z S3.
    """

    def __init__(self) -> None:
        """Inicjalizuje serwis, zapisując konfigurację bucketa i pusty cache w pamięci."""
        self.bucket: str = settings.kb_bucket
        # cache: { "tenant/lang": {topic: answer} }
        self._cache: Dict[str, Dict[str, str]] = {}       
    
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