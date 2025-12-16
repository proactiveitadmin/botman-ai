import os
from ..common.aws import ddb_resource

class TenantsRepo:
    def __init__(self):
        self.table = ddb_resource().Table(os.environ.get("DDB_TABLE_TENANTS", "Tenants"))

    def get(self, tenant_id: str) -> dict | None:
        return self.table.get_item(Key={"tenant_id": tenant_id}).get("Item")

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
