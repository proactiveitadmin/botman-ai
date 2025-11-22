"""
Lambda odpowiedzialna za uruchamianie kampanii marketingowych.

Działa w trybie batch:
- czyta aktywne kampanie z tabeli DDB,
- wybiera odbiorców,
- wrzuca wiadomości do kolejki outbound.
"""

import os
import json

from ...services.campaign_service import CampaignService
from ...common.aws import sqs_client, ddb_resource, resolve_queue_url
from ...services.consent_service import ConsentService
from ...common.logging import logger

OUTBOUND_QUEUE_URL = os.getenv("OutboundQueueUrl")
CAMPAIGNS_TABLE = os.getenv("DDB_TABLE_CAMPAIGNS", "Campaigns")

svc = CampaignService()
consents = ConsentService()


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
    - skanuje tabelę kampanii,
    - dla każdej aktywnej kampanii wysyła wiadomości do odbiorców
      o ile nie jesteśmy w quiet hours.
    """
    table = ddb_resource().Table(CAMPAIGNS_TABLE)
    resp = table.scan()
    out_q_url = _resolve_outbound_queue_url()

    for item in resp.get("Items", []):
        if not item.get("active", False):
            continue

        # QUIET HOURS – jeśli teraz jest poza oknem wysyłki, pomijamy kampanię
        if not svc.is_within_send_window(item):
            logger.info(
                {
                    "campaign": "skipped_quiet_hours",
                    "campaign_id": item.get("campaign_id"),
                    "tenant_id": item.get("tenant_id", "default"),
                }
            )
            continue

        tenant_id = item.get("tenant_id", "default")

        for phone in svc.select_recipients(item):
            if not consents.has_opt_in(tenant_id, phone):
                continue

            body = item.get("body", "Nowa oferta klubu!")
            payload = {
                "to": phone,
                "body": body,
                "tenant_id": tenant_id,
            }
            sqs_client().send_message(
                QueueUrl=out_q_url,
                MessageBody=json.dumps(payload),
            )

    return {"statusCode": 200}
