import os
import json
import time
from typing import Any
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr

from ...common.aws import ddb_resource, s3_client
from ...common.logging import logger


def _now_ts() -> int:
    return int(time.time())

def _json_default(o):
    """JSON serializer for objects not serializable by default json code.
    DynamoDB via boto3 represents numbers as Decimal.
    """
    if isinstance(o, Decimal):
        # preserve integers as int, otherwise float
        if o % 1 == 0:
            return int(o)
        return float(o)
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")

def _cutoff_ts(now_ts: int) -> int:
    hot_days = int(os.getenv("ARCHIVE_HOT_DAYS", "30"))
    return now_ts - hot_days * 86400


def _archive_key(prefix: str, tenant_id: str, pk: str, sk: str) -> str:
    # Prefix powinien kończyć się "/"
    p = prefix if prefix.endswith("/") else prefix + "/"
    safe_pk = pk.replace("#", "_")
    safe_sk = sk.replace("#", "_")
    return f"{p}tenant_id={tenant_id}/pk={safe_pk}/sk={safe_sk}.json"


def lambda_handler(event: dict, context) -> dict:
    """Scheduled archiver: przenosi stare Messages do S3 i odchudza rekordy w DDB.

    - Eksport: 1 obiekt S3 per message (JSON).
    - DDB: SET archived_status + wskaźnik do S3; REMOVE body.
    - Przywracanie (read-only): MessagesRepo.get_last_messages() dociąga body z S3, gdy potrzeba.
    """
    table_name = os.environ.get("DDB_TABLE_MESSAGES", "Messages")
    bucket = os.getenv("ARCHIVE_BUCKET")
    prefix = os.getenv("ARCHIVE_PREFIX", "archive/")
    if not bucket:
        raise RuntimeError("Missing ARCHIVE_BUCKET env var")

    max_items = int(os.getenv("ARCHIVE_MAX_ITEMS", "1000"))
    page_limit = int(os.getenv("ARCHIVE_SCAN_PAGE_LIMIT", "500"))

    ddb = ddb_resource()
    table = ddb.Table(table_name)
    s3 = s3_client()

    now_ts = _now_ts()
    cutoff = _cutoff_ts(now_ts)
    cutoff_sk = f"{cutoff}#"

    scanned = 0
    archived = 0
    last_evaluated_key: dict[str, Any] | None = None

    while archived < max_items:
        kwargs: dict[str, Any] = {
            "Limit": page_limit,
            "ProjectionExpression": "#pk, #sk, tenant_id, conversation_id, msg_id, direction, #body, from_phone_last4, to_phone_last4, channel, template_id, ai_confidence, delivery_status, ttl_ts, archived_status, archive_bucket, archive_key",
            "ExpressionAttributeNames": {"#pk": "pk", "#sk": "sk", "#body": "body"},
            "FilterExpression": Attr("sk").lt(cutoff_sk) & (Attr("archived_status").not_exists() | Attr("archived_status").ne("Archived")),
        }
        if last_evaluated_key:
            kwargs["ExclusiveStartKey"] = last_evaluated_key

        resp = table.scan(**kwargs)
        items = resp.get("Items") or []
        scanned += resp.get("ScannedCount") or 0

        for it in items:
            if archived >= max_items:
                break

            pk = it["pk"]
            sk = it["sk"]
            tenant_id = it.get("tenant_id") or pk.split("#", 1)[0]
            key = _archive_key(prefix, tenant_id, pk, sk)

            # 1) zapis do S3 (pełny rekord)
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=json.dumps(it, ensure_ascii=False, default=_json_default).encode("utf-8"),
                ContentType="application/json",
            )

            # 2) update w DDB: oznacz + wskaźnik + usuń body (odchudzenie)
            table.update_item(
                Key={"pk": pk, "sk": sk},
                UpdateExpression="SET archived_status = :a, archive_bucket = :b, archive_key = :k, archived_at = :t REMOVE #body",
                ExpressionAttributeNames={"#body": "body"},
                ExpressionAttributeValues={
                    ":a": "Archived",
                    ":b": bucket,
                    ":k": key,
                    ":t": now_ts,
                },
            )
            archived += 1

        last_evaluated_key = resp.get("LastEvaluatedKey")
        if not last_evaluated_key or not items:
            break

    logger.info(
        {
            "archiver": "messages_to_s3",
            "table": table_name,
            "bucket": bucket,
            "prefix": prefix,
            "cutoff_ts": cutoff,
            "scanned": scanned,
            "archived": archived,
        }
    )

    return {
        "statusCode": 200,
        "scanned": scanned,
        "archived": archived,
        "cutoff_ts": cutoff,
        "bucket": bucket,
        "prefix": prefix,
    }