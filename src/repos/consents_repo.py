# src/storage/consents_repo.py
import os
import time
from typing import Optional, Dict

from ..common.aws import ddb_resource  # uwaga: ścieżka względem storage
from ..common.security import phone_hmac, phone_last4

class ConsentsRepo:
    """
    Prosty repozytorium zgód marketingowych.

    Klucz:
      pk = "{tenant_id}#{phone_hmac}"

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
    def _pk(tenant_id: str, phone_hmac_value: str) -> str:
        return f"{tenant_id}#{phone_hmac_value}"

    def get(self, tenant_id: str, phone: str) -> Optional[Dict]:
        ph = phone_hmac(tenant_id, phone)
        resp = self.table.get_item(Key={"pk": self._pk(tenant_id, ph)})
        return resp.get("Item")

    def set_opt_in(self, tenant_id: str, phone: str, source: str | None = None) -> Dict:
        ph = phone_hmac(tenant_id, phone)
        item = {
            "pk": self._pk(tenant_id, ph),
            "tenant_id": tenant_id,
            "phone_hmac": ph,
            "phone_last4": phone_last4(phone),
            "opt_in": False,
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
        ph = phone_hmac(tenant_id, phone)
        self.table.delete_item(Key={"pk": self._pk(tenant_id, ph)})