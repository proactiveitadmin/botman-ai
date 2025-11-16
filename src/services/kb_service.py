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
        # cache: {tenant_id: {topic: answer}}
        self._cache: Dict[str, Dict[str, str]] = {}

    def _load_tenant_faq(self, tenant_id: str) -> Optional[Dict[str, str]]:
        """
        Ładuje FAQ dla podanego tenanta z S3 (jeśli skonfigurowano bucket).

        Zwraca:
            dict topic -> answer, jeśli plik istnieje i poprawnie się wczyta,
            None w pozostałych przypadkach.
        """
        if not self.bucket:
            return None

        if tenant_id in self._cache:
            return self._cache[tenant_id]

        key = f"kb/{tenant_id}/faq.json"
        try:
            obj = s3_client().get_object(Bucket=self.bucket, Key=key)
            data = json.loads(obj["Body"].read())
            if isinstance(data, dict):
                # zapamiętujemy w cache
                self._cache[tenant_id] = data
                logger.info({"kb": "loaded", "bucket": self.bucket, "key": key})
                return data
            logger.warning({"kb": "invalid_format", "bucket": self.bucket, "key": key})
            return None
        except ClientError:
            logger.info({"kb": "miss", "bucket": self.bucket, "key": key})
            return None

    def answer(self, topic: str, tenant_id: str) -> Optional[str]:
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

        # 1) S3 (jeśli skonfigurowane)
        tenant_faq = self._load_tenant_faq(tenant_id)
        if tenant_faq and topic in tenant_faq:
            return tenant_faq[topic]

        # 2) fallback do domyślnej listy
        return DEFAULT_FAQ.get(topic)
