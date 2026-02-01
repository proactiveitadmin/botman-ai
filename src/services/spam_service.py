# src/services/spam_service.py
import os
import time
import datetime
from typing import Optional

from ..common.aws import ddb_resource
from ..common.logging import logger
from ..common.logging_utils import mask_phone
from ..common.security import phone_hmac, normalize_phone, phone_last4


TABLE_NAME = os.getenv("DDB_TABLE_INTENTS_STATS", "IntentsStats")


class SpamService:
    """
    Bardzo prosty rate limiter per tenant+numer telefonu.

    Założenia:
    - bucket czasowy = 1 minuta (lub tyle, ile ustawisz w SPAM_BUCKET_SECONDS),
    - limit wiadomości w buckecie = SPAM_MAX_PER_BUCKET (domyślnie 20),
    - dane trzymane w DDB w tabeli IntentsStats:
        pk = "{tenant_id}#{bucket}"
        sk = "{phone_hmac}"   # deterministyczny HMAC z numeru (bez raw numeru jako klucza)
        attrs: cnt, last_ts, blocked_until, ttl_ts, phone_hint
    """

    def __init__(
        self,
        now_fn=None,
        bucket_seconds: Optional[int] = None,
        max_per_bucket: Optional[int] = None,
        tenant_max_per_bucket: Optional[int] = None,
    ) -> None:
        self.table = ddb_resource().Table(TABLE_NAME)
        self._now_fn = now_fn or (lambda: int(time.time()))
        self.bucket_seconds = bucket_seconds or int(os.getenv("SPAM_BUCKET_SECONDS", "60"))
        self.max_per_bucket = max_per_bucket or int(os.getenv("SPAM_MAX_PER_BUCKET", "20"))
        self.tenant_max_per_bucket = tenant_max_per_bucket or int(
            os.getenv("SPAM_TENANT_MAX_PER_BUCKET", "300")  # 300 msg/min/tenant
        )

    def _bucket_for_ts(self, ts: int) -> str:
        """
        Zwraca identyfikator bucketa czasowego.
        Domyślnie: dokładność do minuty (YYYYMMDDHHMM).
        """
        dt = datetime.datetime.utcfromtimestamp(ts)
        return dt.strftime("%Y%m%d%H%M")

    def _key(self, tenant_id: str, canonical_phone: str, ts: int) -> dict:
        bucket = self._bucket_for_ts(ts)
        ph = phone_hmac(tenant_id, canonical_phone)
        return {
            "pk": f"{tenant_id}#{bucket}",
            "sk": ph,
        }

    def is_blocked(self, tenant_id: str, phone: Optional[str]) -> bool:
        """
        Zwiększa licznik wiadomości w aktualnym buckecie
        i zwraca True, jeśli numer powinien być zablokowany.

        Uwaga: wołamy to PRZED wrzuceniem wiadomości do kolejki.
        """
        if not phone:
            logger.warning({"spam": "no_phone_in_event", "tenant_id": tenant_id})
            return False

        now_ts = self._now_fn()

        # Canonicalizacja numeru PRZED HMAC i last4
        canonical_phone = normalize_phone(phone)

        stats_max_age = int(os.getenv("SPAM_STATS_MAX_AGE_SECONDS", "86400"))
        ttl_ts = now_ts + stats_max_age

        phone_hint = f"***{phone_last4(canonical_phone)}"
        key = self._key(tenant_id, canonical_phone, now_ts)

        # --- per phone/bucket ---
        try:
            resp = self.table.update_item(
                Key=key,
                UpdateExpression=(
                    "ADD cnt :one "
                    "SET last_ts = :ts, ttl_ts = :ttl, phone_hint = :hint"
                ),
                ExpressionAttributeValues={
                    ":one": 1,
                    ":ts": now_ts,
                    ":ttl": ttl_ts,
                    ":hint": phone_hint,
                },
                ReturnValues="ALL_NEW",
            )
            attrs = resp.get("Attributes", {}) or {}
        except Exception as e:
            # W razie problemów z DDB wolimy NIE blokować klienta, tylko zalogować błąd.
            logger.error(
                {
                    "spam": "ddb_update_error",
                    "error": str(e),
                    "tenant_id": tenant_id,
                    "phone": mask_phone(phone),
                }
            )
            return False

        cnt = int(attrs.get("cnt", 0))
        blocked_until = int(attrs.get("blocked_until", 0))

        # --- total per tenant/bucket ---
        total_key = {"pk": key["pk"], "sk": "__TOTAL__"}
        total_cnt = 0
        try:
            total_resp = self.table.update_item(
                Key=total_key,
                UpdateExpression="ADD cnt :one SET last_ts = :ts, ttl_ts = :ttl",
                ExpressionAttributeValues={":one": 1, ":ts": now_ts, ":ttl": ttl_ts},
                ReturnValues="ALL_NEW",
            )
            total_attrs = total_resp.get("Attributes", {}) or {}
            total_cnt = int(total_attrs.get("cnt", 0))
        except Exception as e:
            logger.error(
                {
                    "spam": "ddb_update_error_total",
                    "error": str(e),
                    "tenant_id": tenant_id,
                }
            )
            # jeśli padnie total – nie blokujemy z tego powodu
            total_cnt = 0

        # 1) Jeżeli mamy aktywną blokadę czasową – honorujemy ją
        if blocked_until and now_ts < blocked_until:
            logger.info(
                {
                    "spam": "already_blocked",
                    "tenant_id": tenant_id,
                    "phone": mask_phone(phone),
                    "blocked_until": blocked_until,
                }
            )
            return True

        # 2) Jeżeli przekroczono limit w buckecie – ustawiamy blokadę i zwracamy True
        if cnt > self.max_per_bucket:
            new_blocked_until = now_ts + self.bucket_seconds
            try:
                # odświeżamy też ttl_ts, żeby rekord nie żył dłużej niż max_age
                self.table.update_item(
                    Key=key,
                    UpdateExpression="SET blocked_until = :bu, ttl_ts = :ttl",
                    ExpressionAttributeValues={":bu": new_blocked_until, ":ttl": ttl_ts},
                )
            except Exception as e:
                logger.error(
                    {
                        "spam": "set_blocked_until_failed",
                        "error": str(e),
                        "tenant_id": tenant_id,
                        "phone": mask_phone(phone),
                    }
                )

            logger.warning(
                {
                    "spam": "rate_limit_hit",
                    "tenant_id": tenant_id,
                    "phone": mask_phone(phone),
                    "cnt": cnt,
                    "max_per_bucket": self.max_per_bucket,
                    "bucket_seconds": self.bucket_seconds,
                }
            )
            return True

        # 3) Jeżeli przekroczono limit TENANTA w buckecie – też blokujemy ten request
        if self.tenant_max_per_bucket and total_cnt > self.tenant_max_per_bucket:
            logger.warning(
                {
                    "spam": "tenant_bucket_limit_exceeded",
                    "tenant_id": tenant_id,
                    "phone": mask_phone(phone),
                    "total_cnt": total_cnt,
                }
            )
            # nie ustawiamy tu osobnego blocked_until dla wszystkich,
            # po prostu ten konkretny request jest odrzucony
            return True

        # 4) W normalnym przypadku – nie blokujemy
        return False
