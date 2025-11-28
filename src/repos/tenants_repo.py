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
