# src/storage/consents_repo.py
import os
import time
from typing import Optional, Dict

from ..common.aws import ddb_resource  # uwaga: ścieżka względem storage
# jeśli common.aws jest w src/common/aws.py, to:
# from ..common.aws import ddb_resource

class ConsentsRepo:
    """
    Prosty repozytorium zgód marketingowych.

    Klucz:
      pk = "{tenant_id}#{phone}"

    Atrybuty:
      - tenant_id
      - phone
      - opt_in: bool
      - updated_at: int (unix timestamp)
      - source: opcjonalnie skąd pochodzi zgoda/opt-out
    """

    def __init__(self) -> None:
        table_name = os.getenv("DDB_TABLE_CONSENTS", "Consents")
        self.table = ddb_resource().Table(table_name)

    @staticmethod
    def _pk(tenant_id: str, phone: str) -> str:
        return f"{tenant_id}#{phone}"

    def get(self, tenant_id: str, phone: str) -> Optional[Dict]:
        resp = self.table.get_item(
            Key={"pk": self._pk(tenant_id, phone)}
        )
        return resp.get("Item")

    def set_opt_in(self, tenant_id: str, phone: str, source: str | None = None) -> Dict:
        item = {
            "pk": self._pk(tenant_id, phone),
            "tenant_id": tenant_id,
            "phone": phone,
            "opt_in": True,
            "updated_at": int(time.time()),
        }
        if source:
            item["source"] = source
        self.table.put_item(Item=item)
        return item

    def set_opt_out(self, tenant_id: str, phone: str, source: str | None = None) -> Dict:
        item = {
            "pk": self._pk(tenant_id, phone),
            "tenant_id": tenant_id,
            "phone": phone,
            "opt_in": False,
            "updated_at": int(time.time()),
        }
        if source:
            item["source"] = source
        self.table.put_item(Item=item)
        return item

    def delete(self, tenant_id: str, phone: str) -> None:
        self.table.delete_item(Key={"pk": self._pk(tenant_id, phone)})
