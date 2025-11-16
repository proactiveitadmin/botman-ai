# src/lambdas/housekeeping/handler.py
import os
import time

from ...common.logging import logger
from ...common.aws import ddb_resource

INTENTS_STATS_TABLE = os.getenv("DDB_TABLE_INTENTS_STATS", "IntentsStats")


def lambda_handler(event, context):
    """
    Prosty housekeeping:
    - czyści bardzo stare rekordy z tabeli IntentsStats (rate limiter),
    - docelowo: retention Messages/Conversations + GDPR delete.
    """
    now_ts = int(time.time())
    max_age_seconds = int(os.getenv("SPAM_STATS_MAX_AGE_SECONDS", "86400"))  # domyślnie 1 dzień
    threshold = now_ts - max_age_seconds

    table = ddb_resource().Table(INTENTS_STATS_TABLE)

    deleted = 0
    scanned = 0

    # Uwaga: bardzo prosty scan bez paginacji – OK dla małych wolumenów
    resp = table.scan()
    items = resp.get("Items", []) or []
    scanned += len(items)

    for item in items:
        last_ts = int(item.get("last_ts", 0))
        if last_ts < threshold:
            table.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
            deleted += 1

    logger.info(
        {
            "housekeeping": "spam_cleanup",
            "scanned": scanned,
            "deleted": deleted,
            "threshold_ts": threshold,
        }
    )

    # TODO (Etap 2): retention Messages/Conversations + GDPR delete
    return {"statusCode": 200}
