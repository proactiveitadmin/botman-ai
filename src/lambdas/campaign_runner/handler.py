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
    - dla każdej aktywnej kampanii wysyła wiadomość do każdego odbiorcy.
    """
    table = ddb_resource().Table(CAMPAIGNS_TABLE)
    resp = table.scan()
    out_q_url = _resolve_outbound_queue_url()

    for item in resp.get("Items", []):
        if not item.get("active", False):
            continue

        for phone in svc.select_recipients(item):
            if not consents.has_opt_in(tenant_id, phone):
                continue
            body = item.get("body", "Nowa oferta klubu!")
            payload = {"to": phone, "body": body}
            sqs_client().send_message(QueueUrl=out_q_url, MessageBody=json.dumps(payload))

    return {"statusCode": 200}
