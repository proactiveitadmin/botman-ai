# src/lambdas/housekeeping/handler.py
import os
import time

from ...common.logging import logger
from ...common.aws import ddb_resource

INTENTS_STATS_TABLE = os.getenv("DDB_TABLE_INTENTS_STATS", "IntentsStats")
MESSAGES_TABLE = os.getenv("DDB_TABLE_MESSAGES", "Messages")
CONVERSATIONS_TABLE = os.getenv("DDB_TABLE_CONVERSATIONS", "Conversations")

def _delete_older_than(table_name: str, ts_attr: str, threshold: int):
    """
    Helper:
    - czyści stare rekordy z tabeli Messages/Conversations + GDPR delete.
    """
    ddb = ddb_resource()
    table = ddb.Table(table_name)

    scanned = deleted = 0
    last_evaluated_key = None
    while True:
        resp = table.scan(
            FilterExpression=f"{ts_attr} < :th",
            ExpressionAttributeValues={":th": threshold},
            ExclusiveStartKey=last_evaluated_key or None,
        )
        items = resp.get("Items") or []
        scanned += len(items)

        with table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
                deleted += 1

        last_evaluated_key = resp.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break

    logger.info(
        {
            "housekeeping": "retention_cleanup",
            "table": table_name,
            "scanned": scanned,
            "deleted": deleted,
            "threshold_ts": threshold,
        }
    )

def lambda_handler(event, context):
    """
    Prosty housekeeping:
    - czyści bardzo stare rekordy z tabeli IntentsStats (rate limiter),
    - retention Messages/Conversations + GDPR delete.
    """
    now_ts = int(time.time())
    max_age_seconds = int(os.getenv("SPAM_STATS_MAX_AGE_SECONDS", "86400"))  # domyślnie 1 dzień
    threshold_is = now_ts - max_age_seconds

    table = ddb_resource().Table(INTENTS_STATS_TABLE)

    deleted = 0
    scanned = 0

    # Uwaga: bardzo prosty scan bez paginacji – OK dla małych wolumenów
    resp = table.scan()
    items = resp.get("Items", []) or []
    scanned += len(items)

    for item in items:
        last_ts = int(item.get("last_ts", 0))
        if last_ts < threshold_is:
            table.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
            deleted += 1

    logger.info(
        {
            "housekeeping": "spam_cleanup",
            "scanned": scanned,
            "deleted": deleted,
            "threshold_ts": threshold_is,
        }
    )

    # retention Messages/Conversations + GDPR delete
    threshold_mc = now_ts - 365 * 24 * 3600
    _delete_older_than(MESSAGES_TABLE, "ts", now_ts)
    _delete_older_than(CONVERSATIONS_TABLE, "created_at", now_ts)
    
    return {"statusCode": 200}
