import os
from typing import Any
from boto3.dynamodb.conditions import Key
from ..common.aws import ddb_resource
from ..common.logging import logger


class TenantsRepo:
    def __init__(self):
        self.table = ddb_resource().Table(os.environ.get("DDB_TABLE_TENANTS", "Tenants"))

    def get(self, tenant_id: str) -> dict | None:
        return self.table.get_item(Key={"tenant_id": tenant_id}).get("Item")

    def find_by_twilio_to(self, to_number: str) -> dict | None:
        """
        Resolve tenant by Twilio destination number (To) using GSI TwilioToIndex.

        Expected tenant item shape:
          - tenant_id: str (PK)
          - twilio_to: str (indexed, exact match, e.g. "whatsapp:+48....")

        Backward-compatible fallback: removed!!!
          - if you used 'twilio_numbers': [..] historically, we do a scan for that.
            Prefer migrating data to 'twilio_to' (or separate mapping table if many-to-one).
        """
        if not to_number:
            return None

        # Primary path: query GSI
        try:
            resp = self.table.query(
                IndexName="TwilioToIndex",
                KeyConditionExpression=Key("twilio_to").eq(to_number),
                Limit=1,
            )
            items = resp.get("Items") or []
            if items:
                return items[0]
        except Exception as e:
            logger.exception({"tenants_repo": "query_failed", "error": str(e), "to": to_number})

        
        #do not scan if not found - scan is not allowed!
        return None

    
    def find_by_whatsapp_phone_number_id(self, phone_number_id: str) -> dict | None:
        """Resolve tenant by WhatsApp Cloud API phone_number_id using GSI WhatsAppPhoneNumberIdIndex."""
        if not phone_number_id:
            return None
        try:
            resp = self.table.query(
                IndexName="WhatsAppPhoneNumberIdIndex",
                KeyConditionExpression=Key("whatsapp_phone_number_id").eq(phone_number_id),
                Limit=1,
            )
            items = resp.get("Items") or []
            if items:
                return items[0]
        except Exception as e:
            logger.exception({"tenants_repo": "query_failed", "error": str(e), "phone_number_id": phone_number_id})
        return None

    def find_by_pg_api_key(self, api_key: str) -> dict | None:
        """Resolve tenant by PerfectGym API key using GSI PgApiKeyIndex."""
        if not api_key:
            return None
        try:
            resp = self.table.query(
                IndexName="PgApiKeyIndex",
                KeyConditionExpression=Key("pg_api_key").eq(api_key),
                Limit=1,
            )
            items = resp.get("Items") or []
            if items:
                return items[0]
        except Exception as e:
            logger.exception({"tenants_repo": "query_failed", "error": str(e), "pg_api_key": "***"})
        return None

    def set_language(self, tenant_id: str, language_code: str):
            self.table.update_item(
                Key={"tenant_id": tenant_id},
                UpdateExpression="SET language_code = :lang",
                ExpressionAttributeValues={":lang": language_code},
            )

    def get_email_config(self, tenant_id: str) -> dict | None:
        """Zwraca konfigurację email dla tenanta (lub None jeśli brak/wyłączona)."""
        item = self.get(tenant_id) or {}
        email_cfg = item.get("email")
        if not email_cfg or not isinstance(email_cfg, dict):
            return None
        if email_cfg.get("enabled") is False:
            return None
        return email_cfg

    def set_email_config(
        self,
        tenant_id: str,
        *,
        from_email: str | None = None,
        from_name: str | None = None,
        region: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        """Ustawia (merge) mapę `email` w rekordzie tenanta."""
        current = (self.get(tenant_id) or {}).get("email") or {}
        if not isinstance(current, dict):
            current = {}

        if from_email is not None:
            current["from_email"] = from_email
        if from_name is not None:
            current["from_name"] = from_name
        if region is not None:
            current["region"] = region
        if enabled is not None:
            current["enabled"] = enabled

        self.table.update_item(
            Key={"tenant_id": tenant_id},
            UpdateExpression="SET #email = :email",
            ExpressionAttributeNames={"#email": "email"},
            ExpressionAttributeValues={":email": current},
        )
