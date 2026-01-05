import os
import time
from typing import Optional

from botocore.exceptions import ClientError
from ..common.aws import ddb_resource
from ..common.logging import logger
from ..common.config import settings

class IdempotencyRepo:
    """Simple idempotency store based on DynamoDB conditional writes.

    Item schema:
      - pk: idempotency key (string)
      - created_at: unix epoch seconds
      - ttl: unix epoch seconds (optional)
      - meta: optional small dict (must be JSON-serializable)
    """

    def __init__(self, table_name_env: str = "DDB_TABLE_IDEMPOTENCY"):
        self.table_name = os.getenv(table_name_env, "Idempotency")
        self.table = ddb_resource().Table(self.table_name)
        self.ttl_seconds = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", str(7 * 24 * 3600)))

    def try_acquire(self, key: str, meta: Optional[dict] = None) -> bool:
        """Return True if key was acquired (first time), False if already exists."""
        dev_mode = os.getenv("DEV_MODE", "false").lower() == "true" or settings.dev_mode
        if dev_mode:
            if not hasattr(self, "_dev_seen"):
                self._dev_seen = set()
            if key in self._dev_seen:
                return False
            self._dev_seen.add(key)
            return True
        now = int(time.time())
        item = {"pk": key, "created_at": now}
        if self.ttl_seconds > 0:
            item["ttl"] = now + self.ttl_seconds
        if meta is not None:
            # keep meta small; avoid PII
            item["meta"] = meta

        try:
            self.table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(pk)",
            )
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            logger.error({"idempotency": "ddb_error", "err": str(e), "table": self.table_name})
            raise
