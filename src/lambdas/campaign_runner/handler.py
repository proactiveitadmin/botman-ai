"""
Lambda odpowiedzialna za uruchamianie kampanii marketingowych.

Tryb batch:
- pobiera aktywnych tenantów albo tenant_id z eventu,
- pobiera kampanie due z DDB po GSI tenant_id + next_run_time,
- atomowo claimuje kampanię przez ustawienie active=False,
- wybiera i waliduje odbiorców,
- wrzuca wiadomości do kolejki outbound SQS,
- best-effort loguje wysłaną wiadomość w repozytorium konwersacji.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Iterable, Iterator, Mapping, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from ...common.aws import ddb_resource, resolve_queue_url, sqs_client
from ...common.constants import (
    CAMPAIGNS_1ST_NAME_PLACEHOLDER,
    CAMPAIGNS_PAYMENT_URL_PLACEHOLDER,
    CAMPAIGNS_PRODUCT_ID_PLACEHOLDER,
    CAMPAIGNS_TENANT_NEXT_RUN_INDEX,
    CAMPAIGNS_TIME_ZONE,
)
from ...common.logging import logger
from ...common.security import conversation_key, decrypt_phone
from ...common.utils import normalize_whatsapp_channel_user_id
from ...repos.conversations_repo import ConversationsRepo
from ...repos.tenants_repo import TenantsRepo
from ...services.campaign_service import CampaignService
from ...services.clients_factory import ClientsFactory
from ...services.metrics_service import MetricsService

CAMPAIGNS_TABLE_NAME = os.getenv("DDB_TABLE_CAMPAIGNS", "Campaigns")
OUTBOUND_QUEUE_ENV_NAME = "OutboundQueueUrl"
MESSAGE_TYPE_CAMPAIGN = "campaign"
WHATSAPP_CHANNEL = "whatsapp"


class PerfectGymClient(Protocol):
    def get_member_1st_name_by_phone(self, *, phone: str) -> str | None: ...

    def get_product_payment_link(self, *, member_id: int, product_id: str) -> str | None: ...

    def get_member_by_phone(self, phone: str) -> Mapping[str, Any] | None: ...

    def get_marketing_consent_for_member(self, *, member_id: int) -> bool: ...

    def get_member_type_by_phone(self, *, phone: str) -> str | None: ...


class CampaignRunner:
    def __init__(
        self,
        *,
        campaign_service: CampaignService | None = None,
        conversations_repo: ConversationsRepo | None = None,
        clients_factory: ClientsFactory | None = None,
        tenants_repo: TenantsRepo | None = None,
        metrics_service: MetricsService | None = None,
        table: Any | None = None,
        outbound_queue_url: str | None = None,
        sqs: Any | None = None,
    ) -> None:
        self.campaign_service = campaign_service or CampaignService()
        self.conversations_repo = conversations_repo or ConversationsRepo()
        self.clients_factory = clients_factory or ClientsFactory()
        self.tenants_repo = tenants_repo or TenantsRepo()
        self.metrics = metrics_service or MetricsService()
        self.table = table or ddb_resource().Table(CAMPAIGNS_TABLE_NAME)
        self.outbound_queue_url = outbound_queue_url or resolve_queue_url(OUTBOUND_QUEUE_ENV_NAME)
        self.sqs = sqs or sqs_client()

    def run(self, event: Mapping[str, Any] | None) -> dict[str, Any]:
        processed_campaigns = 0
        sent_messages = 0

        for tenant_id in self._resolve_tenant_ids(event):
            for campaign in self._iter_due_campaigns(tenant_id):
                if not campaign.get("active", False):
                    self._log_campaign_skip(campaign, tenant_id, "item_not_active")
                    continue

                if not self._claim_campaign(campaign):
                    self._log_campaign_skip(campaign, tenant_id, "already_claimed")
                    continue

                processed_campaigns += 1
                sent_messages += self._process_campaign(campaign, fallback_tenant_id=tenant_id)

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "processed_campaigns": processed_campaigns,
                    "sent_messages": sent_messages,
                }
            ),
        }

    def _resolve_tenant_ids(self, event: Mapping[str, Any] | None) -> list[str]:
        tenant_id = (event or {}).get("tenant_id")
        if tenant_id and tenant_id not in {"*", "all", "ALL"}:
            return [str(tenant_id)]

        return [
            tenant["tenant_id"]
            for tenant in self.tenants_repo.list_all()
            if tenant.get("tenant_id")
        ]

    def _iter_due_campaigns(self, tenant_id: str) -> Iterator[dict[str, Any]]:
        # Zachowujemy format oryginalnego pola next_run_time: YYYY-MM-DDTHH:MM:SS.
        # Porównanie leksykograficzne działa poprawnie tylko wtedy, gdy wszystkie wartości
        # są zapisane w tym samym timezone i dokładnie tym samym formacie.
        now_iso = datetime.now(ZoneInfo(CAMPAIGNS_TIME_ZONE)).strftime("%Y-%m-%dT%H:%M:%S")
        query_kwargs = {
            "IndexName": CAMPAIGNS_TENANT_NEXT_RUN_INDEX,
            "KeyConditionExpression": Key("tenant_id").eq(tenant_id)
            & Key("next_run_time").lte(now_iso),
        }

        while True:
            response = self.table.query(**query_kwargs)
            yield from response.get("Items", [])

            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                return

            query_kwargs["ExclusiveStartKey"] = last_key

    def _claim_campaign(self, campaign: Mapping[str, Any]) -> bool:
        """Atomowo oznacza kampanię jako obsłużoną.

        Chroni przed podwójną wysyłką, gdy dwie Lambdy równolegle pobiorą tę samą
        kampanię z GSI. Jeśli druga Lambda próbuje claimować już nieaktywną kampanię,
        DynamoDB zwróci ConditionalCheckFailedException.
        """
        try:
            self.table.update_item(
                Key={"pk": campaign["pk"]},
                UpdateExpression="SET #active = :inactive",
                ConditionExpression="#active = :active",
                ExpressionAttributeNames={"#active": "active"},
                ExpressionAttributeValues={":active": True, ":inactive": False},
            )
            return True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code == "ConditionalCheckFailedException":
                return False
            raise

    def _process_campaign(self, campaign: Mapping[str, Any], *, fallback_tenant_id: str) -> int:
        tenant_id = str(campaign.get("tenant_id") or fallback_tenant_id)
        perfectgym = self.clients_factory.perfectgym(tenant_id)
        sent = 0

        for recipient in self.campaign_service.select_recipients(campaign):
            if self._process_recipient(campaign, tenant_id, perfectgym, recipient):
                sent += 1

        logger.info(
            {
                "campaign": "processed",
                "campaign_id": campaign.get("campaign_id"),
                "tenant_id": tenant_id,
                "sent_messages": sent,
            }
        )
        return sent

    def _process_recipient(
        self,
        campaign: Mapping[str, Any],
        tenant_id: str,
        perfectgym: PerfectGymClient,
        recipient: Any,
    ) -> bool:
        phone = self._decrypt_recipient_phone(campaign, tenant_id, recipient)
        if not phone:
            return False

        member_id = self._get_member_id(campaign, tenant_id, perfectgym, phone)
        if member_id is None:
            return False

        if not self._has_marketing_consent(campaign, tenant_id, perfectgym, member_id):
            return False

        if not self._matches_member_type_filters(campaign, tenant_id, perfectgym, phone):
            return False

        context = self._build_campaign_context(
            tenant_id=tenant_id,
            member_id=member_id,
            phone_number=phone,
            product_id=campaign.get(CAMPAIGNS_PRODUCT_ID_PLACEHOLDER),
            perfectgym=perfectgym,
        )
        message = self.campaign_service.build_message(
            campaign=campaign,
            tenant_id=tenant_id,
            recipient_phone=phone,
            context=context,
        )

        channel_user_id = normalize_whatsapp_channel_user_id(phone)
        payload = self._build_outbound_payload(message, tenant_id, channel_user_id)
        self._send_to_outbound_queue(payload)
        self._log_outbound_message(message, tenant_id, channel_user_id)

        self.metrics.incr(
            "TenantCampaignSendOk",
            tenant_id=tenant_id,
            component="campaign_runner",
        )
        return True

    def _decrypt_recipient_phone(
        self,
        campaign: Mapping[str, Any],
        tenant_id: str,
        recipient: Any,
    ) -> str | None:
        if not isinstance(recipient, Mapping) or not recipient.get("token"):
            self._log_campaign_skip(campaign, tenant_id, "no_phone_token")
            return None

        phone = decrypt_phone(tenant_id, recipient["token"])
        if not phone:
            self._log_campaign_skip(campaign, tenant_id, "no_phone_mapping")
            return None

        return phone

    def _get_member_id(
        self,
        campaign: Mapping[str, Any],
        tenant_id: str,
        perfectgym: PerfectGymClient,
        phone: str,
    ) -> int | None:
        members_response = perfectgym.get_member_by_phone(phone)
        members = (members_response or {}).get("value") or []
        if not members:
            self._log_campaign_skip(campaign, tenant_id, "no_member")
            return None

        raw_id = members[0].get("Id") or members[0].get("id")
        try:
            return int(raw_id)
        except (TypeError, ValueError):
            logger.warning(
                {
                    "campaign": "get_member_id_failed",
                    "campaign_id": campaign.get("campaign_id"),
                    "tenant_id": tenant_id,
                    "raw_id": raw_id,
                }
            )
            return None

    def _has_marketing_consent(
        self,
        campaign: Mapping[str, Any],
        tenant_id: str,
        perfectgym: PerfectGymClient,
        member_id: int,
    ) -> bool:
        if perfectgym.get_marketing_consent_for_member(member_id=member_id):
            return True

        self._log_campaign_skip(campaign, tenant_id, "no_marketing_consent_for_member")
        return False

    def _matches_member_type_filters(
        self,
        campaign: Mapping[str, Any],
        tenant_id: str,
        perfectgym: PerfectGymClient,
        phone: str,
    ) -> bool:
        include_tags = self._normalize_tags(self.campaign_service.select_include_tags(campaign))
        exclude_tags = self._normalize_tags(self.campaign_service.select_exclude_tags(campaign))

        if not include_tags and not exclude_tags:
            return True

        member_type = perfectgym.get_member_type_by_phone(phone=phone)
        normalized_member_type = self._normalize_tag(member_type)

        if include_tags and normalized_member_type not in include_tags:
            logger.warning(
                {
                    "campaign": "not_included",
                    "campaign_id": campaign.get("campaign_id"),
                    "tenant_id": tenant_id,
                    "include_tags": sorted(include_tags),
                    "member_type": member_type,
                }
            )
            return False

        if exclude_tags and normalized_member_type in exclude_tags:
            logger.warning(
                {
                    "campaign": "excluded",
                    "campaign_id": campaign.get("campaign_id"),
                    "tenant_id": tenant_id,
                    "exclude_tags": sorted(exclude_tags),
                    "member_type": member_type,
                }
            )
            return False

        return True

    def _build_campaign_context(
        self,
        *,
        tenant_id: str,
        member_id: int,
        phone_number: str,
        product_id: Any,
        perfectgym: PerfectGymClient,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {}
        first_name = perfectgym.get_member_1st_name_by_phone(phone=phone_number)
        context[str(CAMPAIGNS_1ST_NAME_PLACEHOLDER)] = first_name

        if not product_id:
            return context

        payment_url = perfectgym.get_product_payment_link(
            member_id=member_id,
            product_id=str(product_id),
        )
        if payment_url:
            context[str(CAMPAIGNS_PAYMENT_URL_PLACEHOLDER)] = {
                "type": "link",
                "url": payment_url,
            }
        else:
            logger.warning(
                {
                    "campaign": "missing_payment_url",
                    "tenant_id": tenant_id,
                    "member_id": member_id,
                    "product_id": str(product_id),
                }
            )

        return context

    def _build_outbound_payload(
        self,
        message: Any,
        tenant_id: str,
        channel_user_id: str,
    ) -> dict[str, Any]:
        payload = {
            "to": channel_user_id,
            "body": self._message_value(message, "body", ""),
            "tenant_id": tenant_id,
            "message_type": MESSAGE_TYPE_CAMPAIGN,
        }

        language_code = self._message_value(message, "language_code")
        if language_code:
            payload["language_code"] = language_code

        return payload

    def _send_to_outbound_queue(self, payload: Mapping[str, Any]) -> None:
        self.sqs.send_message(
            QueueUrl=self.outbound_queue_url,
            MessageBody=json.dumps(payload, ensure_ascii=False),
        )

    def _log_outbound_message(self, message: Any, tenant_id: str, channel_user_id: str) -> None:
        conversation_id = conversation_key(
            tenant_id,
            WHATSAPP_CHANNEL,
            channel_user_id,
            None,
        )
        try:
            self.conversations_repo.log_message(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                msg_id=f"out-{uuid4().hex}",
                direction="outbound",
                body=self._message_value(message, "body", ""),
                from_phone=self._message_value(message, "from_phone"),
                to_phone=self._message_value(message, "to_phone", channel_user_id),
                channel=self._message_value(message, "channel", WHATSAPP_CHANNEL),
                channel_user_id=self._message_value(message, "channel_user_id", channel_user_id),
                language_code=self._message_value(message, "language_code"),
                tag=MESSAGE_TYPE_CAMPAIGN,
            )
        except Exception:
            # Logowanie konwersacji nie może blokować wysyłki kampanii.
            logger.exception(
                {
                    "campaign": "log_outbound_message_failed",
                    "tenant_id": tenant_id,
                    "conversation_id": conversation_id,
                }
            )

    @staticmethod
    def _message_value(message: Any, key: str, default: Any = None) -> Any:
        if isinstance(message, Mapping):
            return message.get(key, default)
        return getattr(message, key, default)

    @staticmethod
    def _normalize_tag(value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().casefold()
        return normalized or None

    @classmethod
    def _normalize_tags(cls, tags: Iterable[Any] | None) -> set[str]:
        return {
            normalized
            for tag in tags or []
            if (normalized := cls._normalize_tag(tag)) is not None
        }

    @staticmethod
    def _log_campaign_skip(campaign: Mapping[str, Any], tenant_id: str, reason: str) -> None:
        logger.warning(
            {
                "campaign": reason,
                "campaign_id": campaign.get("campaign_id"),
                "tenant_id": campaign.get("tenant_id") or tenant_id,
            }
        )


_RUNNER: CampaignRunner | None = None


def get_runner() -> CampaignRunner:
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = CampaignRunner()
    return _RUNNER


def lambda_handler(event: Mapping[str, Any] | None, context: Any) -> dict[str, Any]:
    return get_runner().run(event)
