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
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from boto3.dynamodb.conditions import Key

from ...services.campaign_service import CampaignService
from ...repos.conversations_repo import ConversationsRepo
from ...common.aws import sqs_client, ddb_resource, resolve_queue_url
from ...common.logging import logger
from ...common.utils import normalize_whatsapp_channel_user_id
from ...services.clients_factory import ClientsFactory
from ...repos.tenants_repo import TenantsRepo
from ...common.security import decrypt_phone, conversation_key
from ...services.metrics_service import MetricsService
from ...common.constants import (
    CAMPAIGNS_TENANT_NEXT_RUN_INDEX, 
    CAMPAIGNS_TIME_ZONE, 
    CAMPAIGNS_1ST_NAME_PLACEHOLDER, 
    CAMPAIGNS_PAYMENT_URL_PLACEHOLDER,
    CAMPAIGNS_PRODUCT_ID_PLACEHOLDER,
)

OUTBOUND_QUEUE_URL = os.getenv("OutboundQueueUrl")
CAMPAIGNS_TABLE = os.getenv("DDB_TABLE_CAMPAIGNS", "Campaigns")

svc = CampaignService()
conv_repo = ConversationsRepo()
clients = ClientsFactory()
tenants_repo = TenantsRepo()
metrics = MetricsService()

def build_campaign_context(tenant_id: str, member_id: int, phone_number: str, product_id: str | None = None) -> dict:
    ctx: dict = {}
    member_1st_name = clients.perfectgym(tenant_id).get_member_1st_name_by_phone(phone=phone_number)
    ctx[str(CAMPAIGNS_1ST_NAME_PLACEHOLDER)] = member_1st_name
    
    if product_id:
        pay_url = clients.perfectgym(tenant_id).get_product_payment_link(
            member_id=member_id,
            product_id=str(product_id),
        )
        logger.warning({
            "temp build_campaign_context": " url",
            "tenant_id": tenant_id,
            "member_id": member_id,
            "product_id": str(product_id),
            "pay_url": pay_url,
            "str(pay_url)": str(pay_url),
        })
        
        if pay_url:
            ctx[str(CAMPAIGNS_PAYMENT_URL_PLACEHOLDER)] = {"type": "link", "url": pay_url}
        else:
            logger.warning({
                "build_campaign_context": "missing url",
                "tenant_id": tenant_id,
                "member_id": member_id,
                "product_id": str(product_id),
            })
    return ctx

def check_member_type(tenant_id: str, tag: str, phone_number: str, exclude: bool = False):  
    member_type = clients.perfectgym(tenant_id).get_member_type_by_phone(
        phone=phone_number,
    )
    if member_type is None:
        return False
    return member_type.lower() != tag.lower() if exclude else member_type.lower() == tag.lower()

def lambda_handler(event, context):
    """
    Główny handler kampanii:
    - NIE skanuje tabeli kampanii,
    - pobiera kampanie "due" przez GSI tenant_id + next_run_time (<= now),
    - dla każdej aktywnej kampanii wysyła wiadomości do odbiorców
    """
    table = ddb_resource().Table(CAMPAIGNS_TABLE)
    out_q_url = resolve_queue_url("OutboundQueueUrl")

    tenant_id = (event or {}).get("tenant_id")

    # Scheduled events may not provide tenant_id. In demo we iterate tenants.
    if not tenant_id or tenant_id in ("*", "all", "ALL"):       
        tenant_ids = [t.get("tenant_id") for t in tenants_repo.list_all() if t.get("tenant_id")]        
    else:     
        tenant_ids = [tenant_id]

    def iter_due_campaigns(tenant_id: str):
        """
        Query po GSI (tenant_id + next_run_time), z paginacją.
        Pobiera kampanie, których next_run_time <= teraz i ustawia 
        pole active na false
        """
        # ISO 8601 UTC (lexicographically sortable)        
        now_dt = datetime.now(ZoneInfo(CAMPAIGNS_TIME_ZONE))
        now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%S")
        

        query_kwargs = {
            "IndexName": CAMPAIGNS_TENANT_NEXT_RUN_INDEX,
            "KeyConditionExpression": Key("tenant_id").eq(tenant_id) & Key("next_run_time").lte(now_iso),
        }

        resp = table.query(**query_kwargs)
        for it in resp.get("Items", []):
            yield it

        while "LastEvaluatedKey" in resp:
            resp = table.query(**query_kwargs, ExclusiveStartKey=resp["LastEvaluatedKey"])

            for it in resp.get("Items", []):
                logger.warning({
                    "checkpoint": "yield_item_next_page",
                    "item_id": it.get("id"),
                    "repr_item": repr(it),
                })
                yield it
              
    for tid in tenant_ids:
        for item in iter_due_campaigns(tid):
            if not item.get("active", False):                
                logger.warning(
                    {
                        "campaign": "item not active",
                        "campaign_id": item.get("campaign_id"),
                        "tenant_id": item.get("tenant_id", tid),
                    }
                )
                continue
            table.update_item(
                Key={
                    "pk": item["pk"],
                },
                UpdateExpression="SET active = :active",
                ExpressionAttributeValues={
                    ":active": False,
                },
            )

            tenant_id_item = item.get("tenant_id") or tid
            for recipient in svc.select_recipients(item):
                # recipient ma byc dict z token (bez PII w Campaigns)
                if isinstance(recipient, dict) and recipient.get("token"):
                    phone_enc = recipient.get("token")   
                    phone = decrypt_phone(tenant_id_item, phone_enc) if phone_enc else ""
                    if not phone:
                        logger.warning(
                            {
                                "campaign": "no_phone_mapping",
                                "campaign_id": item.get("campaign_id"),
                                "tenant_id": tenant_id_item,
                            }
                        )
                        continue
                else:
                    logger.warning(
                        {
                            "campaign": "no_phone",
                            "campaign_id": item.get("campaign_id"),
                            "tenant_id": tenant_id_item,
                        }
                    )
                    continue

                members = clients.perfectgym(tenant_id_item).get_member_by_phone(phone)
                items = (members or {}).get("value") or []
                if not items:
                    logger.warning(
                        {
                            "campaign": "no member",
                            "campaign_id": item.get("campaign_id"),
                            "tenant_id": item.get("tenant_id", tid),
                        }
                    )
                    continue

                raw_id = items[0].get("Id") or items[0].get("id")
                member_id = None

                try:
                    member_id = int(raw_id)
                except (TypeError, ValueError):
                    logger.warning(
                        {
                            "campaign": "get_member_id_failed",
                            "campaign_id": item.get("campaign_id"),
                            "tenant_id": item.get("tenant_id", tid),
                            "raw_id": raw_id,
                        }
                    )
                    continue

                if not clients.perfectgym(tenant_id_item).get_marketing_consent_for_member(
                    member_id=member_id,
                    ):
                    logger.warning(
                        {
                            "campaign": "no marketing_consent_for_member",
                            "campaign_id": item.get("campaign_id"),
                            "tenant_id": item.get("tenant_id", tid),
                        }
                    )
                    continue

                include_tags = svc.select_include_tags(item)

                if include_tags:
                    is_included = any(
                        check_member_type(
                            tenant_id_item,
                            tag,
                            phone,
                            exclude=False,
                        )
                        for tag in include_tags
                    )

                    if not is_included:
                        logger.warning(
                            {
                                "campaign": "not included",
                                "campaign_id": item.get("campaign_id"),
                                "tenant_id": item.get("tenant_id", tid),
                                "include_tags": include_tags,
                            }
                        )
                        continue


                exclude_tags = svc.select_exclude_tags(item)

                if exclude_tags:
                    is_excluded = any(
                        check_member_type(
                            tenant_id_item,
                            tag,
                            phone,
                            exclude=False,
                        )
                        for tag in exclude_tags
                    )

                    if is_excluded:
                        logger.warning(
                            {
                                "campaign": "excluded",
                                "campaign_id": item.get("campaign_id"),
                                "tenant_id": item.get("tenant_id", tid),
                                "exclude_tags": exclude_tags,
                            }
                        )
                        continue
                    
                product_id = item.get(CAMPAIGNS_PRODUCT_ID_PLACEHOLDER)
                context = build_campaign_context(tenant_id_item, member_id, phone, product_id) 

                msg = svc.build_message(
                    campaign=item,
                    tenant_id=tenant_id_item,
                    recipient_phone=phone,
                    context=context,
                )
                to = normalize_whatsapp_channel_user_id(phone)
                
                payload = {
                    "to": to,
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
                
                conv_key = conversation_key(
                    tenant_id_item,
                    "whatsapp",
                    to,
                    None,
                )
                try:
                    MESSAGES.log_message(
                        tenant_id=msg.tenant_id,
                        conversation_id=conv_key,
                        msg_id=new_id("out-"),
                        direction="outbound",
                        body=msg.body or "",
                        from_phone=msg.from_phone,
                        to_phone=msg.to_phone,
                        channel=msg.channel or "whatsapp",
                        channel_user_id=msg.channel_user_id or msg.from_phone,
                        language_code=None,
                        tag="campaign"
                    )
                except Exception:
                    # nie blokujemy flow jeśli logowanie padnie
                    pass
                    
                
                metrics.incr("TenantCampaignSendOk", tenant_id=tenant_id_item, component="campaign_runner")
                
            logger.info(
                {
                    "campaign": "send",
                    "campaign_id": item.get("campaign_id"),
                    "tenant_id": tenant_id_item,
                }
            )
    return {"statusCode": 200}