"""
Lambda odpowiedzialna za uruchamianie kampanii marketingowych.

Działa w trybie batch:
- czyta aktywne kampanie z tabeli DDB,
- wybiera odbiorców,
- wrzuca wiadomości do kolejki outbound.
"""

import os
import json
import time

from boto3.dynamodb.conditions import Key

from ...services.campaign_service import CampaignService
from ...repos.conversations_repo import ConversationsRepo
from ...common.aws import sqs_client, ddb_resource, resolve_queue_url
from ...services.consent_service import ConsentService
from ...repos.members_index_repo import MembersIndexRepo
from ...common.logging import logger

OUTBOUND_QUEUE_URL = os.getenv("OutboundQueueUrl")
CAMPAIGNS_TABLE = os.getenv("DDB_TABLE_CAMPAIGNS", "Campaigns")
CAMPAIGNS_TENANT_NEXT_RUN_INDEX = os.getenv("DDB_INDEX_CAMPAIGNS_TENANT_NEXT_RUN", "tenant_next_run_at")

svc = CampaignService()
consents = ConsentService()
members_index = MembersIndexRepo()
conv_repo = ConversationsRepo()


def _resolve_outbound_queue_url() -> str:
    """
    Zwraca URL kolejki outbound.

    Najpierw próbuje użyć zmiennej środowiskowej OutboundQueueUrl,
    a jeśli jest pusta, korzysta z resolve_queue_url.
    """
    if OUTBOUND_QUEUE_URL:
        return OUTBOUND_QUEUE_URL
    return resolve_queue_url("OutboundQueueUrl")


def lambda_handler(event, context):
    """
    Główny handler kampanii:
    - NIE skanuje tabeli kampanii,
    - pobiera kampanie "due" przez GSI tenant_id + next_run_at (<= now),
    - dla każdej aktywnej kampanii wysyła wiadomości do odbiorców
      o ile nie jesteśmy w quiet hours.
    """
    table = ddb_resource().Table(CAMPAIGNS_TABLE)
    out_q_url = _resolve_outbound_queue_url()

    tenant_id = (event or {}).get("tenant_id")
    if not tenant_id or tenant_id in ("*", "all", "ALL"):
        # Bez tenant_id nie da się wykonać Query po GSI => NIE robimy fallback scan.
        logger.error(
            {
                "campaign": "missing_tenant_id",
                "detail": "tenant_id is required to run campaigns without scanning",
                "event_keys": list((event or {}).keys()),
            }
        )
        return {"statusCode": 400, "body": json.dumps({"error": "tenant_id is required"})}

    def iter_due_campaigns():
        """
        Query po GSI (tenant_id + next_run_at), z paginacją.
        Pobiera kampanie, których next_run_at <= teraz.
        """
        now_ts = int(time.time())
        query_kwargs = {
            "IndexName": CAMPAIGNS_TENANT_NEXT_RUN_INDEX,
            "KeyConditionExpression": Key("tenant_id").eq(tenant_id) & Key("next_run_at").lte(now_ts),
        }

        resp = table.query(**query_kwargs)
        for it in resp.get("Items", []):
            yield it

        while "LastEvaluatedKey" in resp:
            resp = table.query(**query_kwargs, ExclusiveStartKey=resp["LastEvaluatedKey"])
            for it in resp.get("Items", []):
                yield it

    for item in iter_due_campaigns():
        if not item.get("active", False):
            continue

        # QUIET HOURS – jeśli teraz jest poza oknem wysyłki, pomijamy kampanię
        if not svc.is_within_send_window(item):
            logger.info(
                {
                    "campaign": "skipped_quiet_hours",
                    "campaign_id": item.get("campaign_id"),
                    "tenant_id": item.get("tenant_id", tenant_id),
                }
            )
            continue

        tenant_id_item = item.get("tenant_id") or tenant_id

        for recipient in svc.select_recipients(item):
            # recipient może być raw phone (legacy) albo dict z phone_hmac (bez PII w Campaigns)
            if isinstance(recipient, str):
                phone = recipient
            elif isinstance(recipient, dict) and recipient.get("phone_hmac"):
                mi = members_index.find_by_phone_hmac(tenant_id_item, recipient.get("phone_hmac"))
                phone = (mi or {}).get("phone")
                if not phone:
                    # brak mapowania w MembersIndex -> pomijamy (nie mamy jak wysłać)
                    continue
            elif isinstance(recipient, dict) and recipient.get("phone"):
                phone = recipient.get("phone")
            else:
                continue
            if not consents.has_opt_in(tenant_id_item, phone):
                continue
 
            # Opt-out per tenant/channel blocks campaigns regardless of opt-in
            wa_uid = phone if str(phone).startswith('whatsapp:') else f"whatsapp:{phone}"
            conv = conv_repo.get_conversation(tenant_id_item, 'whatsapp', wa_uid) or {}
            if conv.get('opt_out') is True:
                continue

            # tutaj w przyszłości możesz zbudować context z danych odbiorcy (imię, saldo, klub itd.)
            msg = svc.build_message(
                campaign=item,
                tenant_id=tenant_id_item,
                recipient_phone=phone,
                context={},  # na razie puste
            )

            payload = {
                "to": phone,
                "body": msg["body"],
                "tenant_id": tenant_id_item,
                "message_type": "campaign",
            }
            if msg.get("language_code"):
                payload["language_code"] = msg["language_code"]

            sqs_client().send_message(
                QueueUrl=out_q_url,
                MessageBody=json.dumps(payload),
            )

    return {"statusCode": 200}