import os
from ..common.aws import ddb_resource

class TemplatesRepo:
    def __init__(self):
        self.table = ddb_resource().Table(os.environ.get("DDB_TABLE_TEMPLATES", "Templates"))

    def pk(self, tenant_id: str, name: str, language_code: str) -> str:
        return f"{tenant_id}#{name}#{language_code}"

    def get_template(self, tenant_id: str, name: str, language_code: str) -> dict | None:
        pk = self.pk(tenant_id, name, language_code)
        return self.table.get_item(Key={"pk": pk}).get("Item")