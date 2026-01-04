# src/lambdas/housekeeping/handler.py
"""Housekeeping (TTL) + GDPR delete.

Cel:
- retencja danych realizowana przez DynamoDB TTL (ttl_ts) w tabelach:
  Messages, Conversations, IntentsStats.
- możliwość GDPR delete po user_hmac (+ opcjonalnie phone dla IntentsStats).

Uwagi implementacyjne:
- Retencji (Scan+delete po czasie) NIE robimy tutaj — TTL jest źródłem prawdy.
- GDPR delete:
  - Messages: Query po PK (paginacja) + Batch delete (25)
  - Conversations: delete_item po kluczu (pk, sk)
  - IntentsStats: bez GSI nie da się Query po sk => Scan po sk==phone_hmac (paginacja) + Batch delete
"""

import os
import time
from typing import Iterable

import boto3
from boto3.dynamodb.conditions import Attr, Key

from ...common.aws import ddb_resource
from ...common.logging import logger
from ...common.security import phone_hmac, normalize_phone


INTENTS_STATS_TABLE = os.getenv("DDB_TABLE_INTENTS_STATS", "IntentsStats")
MESSAGES_TABLE = os.getenv("DDB_TABLE_MESSAGES", "Messages")
CONVERSATIONS_TABLE = os.getenv("DDB_TABLE_CONVERSATIONS", "Conversations")


def _chunks(items: list[dict], size: int) -> Iterable[list[dict]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _batch_delete(table_name: str, keys: list[dict]) -> int:
    """Deletes items by key using DynamoDB Table.batch_writer()."""
    if not keys:
        return 0

    table = ddb_resource().Table(table_name)
    deleted = 0

    # batch_writer robi batching + retry automatycznie
    with table.batch_writer() as batch:
        for k in keys:
            batch.delete_item(Key=k)
            deleted += 1

    return deleted

def _query_all_keys(table_name: str, *, pk: str) -> list[dict]:
    """Query all items for a given PK (with pagination)."""
    table = ddb_resource().Table(table_name)

    keys: list[dict] = []
    last_evaluated_key = None

    while True:
        kwargs = {
            "KeyConditionExpression": Key("pk").eq(pk),
            "ProjectionExpression": "pk, sk",
        }
        if last_evaluated_key:
            kwargs["ExclusiveStartKey"] = last_evaluated_key

        resp = table.query(**kwargs)
        items = resp.get("Items") or []
        keys.extend({"pk": i["pk"], "sk": i["sk"]} for i in items)

        last_evaluated_key = resp.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break

    return keys


def _scan_intentsstats_by_phone_hmac(*, tenant_id: str, phone: str) -> list[dict]:
    """Scan IntentsStats for all buckets where sk == phone_hmac(tenant_id, normalize_phone(phone))."""
    stats_table = ddb_resource().Table(INTENTS_STATS_TABLE)

    canonical_phone = normalize_phone(phone)
    ph = phone_hmac(tenant_id, canonical_phone)

    keys: list[dict] = []
    last_evaluated_key = None

    while True:
        kwargs = {
            "FilterExpression": Attr("sk").eq(ph),
            "ProjectionExpression": "pk, sk",
        }
        if last_evaluated_key:
            kwargs["ExclusiveStartKey"] = last_evaluated_key

        resp = stats_table.scan(**kwargs)
        items = resp.get("Items") or []
        keys.extend({"pk": i["pk"], "sk": i["sk"]} for i in items)

        last_evaluated_key = resp.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break

    return keys


def _gdpr_delete(
    *,
    tenant_id: str,
    user_hmac_value: str,
    channels: list[str] | None = None,
    phone: str | None = None,
) -> dict:
    """Deletes all data for a user.

    - Conversations: pk = tenant#<tenant_id>, sk = conv#<channel>#<user_hmac>
    - Messages: pk = <tenant_id>#conv#<channel>#<user_hmac> (Query + batch delete)
    - IntentsStats: sk == phone_hmac(tenant_id, normalize_phone(phone)) (Scan + batch delete) if phone provided
    """
    channels = channels or ["whatsapp", "web"]
    ddb = ddb_resource()

    conv_table = ddb.Table(CONVERSATIONS_TABLE)

    deleted_conversations = 0
    deleted_messages = 0
    deleted_intentsstats = 0

    # 1) Conversations + Messages
    conv_pk = f"tenant#{tenant_id}"
    for ch in channels:
        conv_sk = f"conv#{ch}#{user_hmac_value}"

        # Conversations: delete (idempotentnie)
        try:
            conv_table.delete_item(Key={"pk": conv_pk, "sk": conv_sk})
            deleted_conversations += 1
        except Exception:
            pass

        # Messages: query po PK i batch delete
        msg_pk = f"{tenant_id}#conv#{ch}#{user_hmac_value}"
        msg_keys = _query_all_keys(MESSAGES_TABLE, pk=msg_pk)
        deleted_messages += _batch_delete(MESSAGES_TABLE, msg_keys)

    # 2) IntentsStats (opcjonalnie, jeśli mamy phone)
    if phone:
        try:
            stats_keys = _scan_intentsstats_by_phone_hmac(tenant_id=tenant_id, phone=phone)
            deleted_intentsstats = _batch_delete(INTENTS_STATS_TABLE, stats_keys)
        except Exception as e:
            logger.error(
                {
                    "housekeeping": "gdpr_intentsstats_delete_failed",
                    "tenant_id": tenant_id,
                    "error": str(e),
                }
            )

    return {
        "tenant_id": tenant_id,
        "user_hmac": user_hmac_value,
        "channels": channels,
        "deleted_conversations": deleted_conversations,
        "deleted_messages": deleted_messages,
        "deleted_intentsstats": deleted_intentsstats,
    }


def lambda_handler(event, context):
    # Retencję robi TTL, więc housekeeping nie skanuje tabel.
    gdpr_payload = (event or {}).get("gdpr_delete")
    gdpr_result = None

    if isinstance(gdpr_payload, dict):
        tenant_id = gdpr_payload.get("tenant_id")
        user_hmac_value = gdpr_payload.get("user_hmac")

        if tenant_id and user_hmac_value:
            gdpr_result = _gdpr_delete(
                tenant_id=str(tenant_id),
                user_hmac_value=str(user_hmac_value),
                channels=gdpr_payload.get("channels"),
                phone=gdpr_payload.get("phone"),
            )
            logger.info({"housekeeping": "gdpr_delete", **gdpr_result})
        else:
            logger.warning(
                {
                    "housekeeping": "gdpr_delete_invalid_payload",
                    "payload_keys": list(gdpr_payload.keys()),
                }
            )

    return {
        "statusCode": 200,
        "mode": "ttl_enabled",
        "timestamp": int(time.time()),
        "gdpr_delete": gdpr_result,
    }
