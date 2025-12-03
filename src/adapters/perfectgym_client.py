import requests
from ..common.config import settings
from ..common.logging import logger
from datetime import datetime
from typing import Any, Dict, List, Optional
# src/adapters/perfectgym_client.py

BASE_MEMBER_FIELDS = [
    "Id",
    "FirstName",
    "LastName",
    "Email",
    "MobilePhone",
    "Status",
]

BASE_CLASS_FIELDS = [
    "Id",
    "Name",
    "StartDate",
    "EndDate",
    "Capacity",
    "ReservedSpots",
    "ClubId",
]

class PerfectGymClient:
    def __init__(self):
        self.base_url = settings.pg_base_url  # np. "https://<club>.perfectgym.com/api/v2.2/odata"
        self.client_id = settings.pg_client_id
        self.client_secret = settings.pg_client_secret
        self.logger = logger

    def _headers(self):
        return {
            "X-Client-id": settings.pg_client_id or "",
            "X-Client-Secret": settings.pg_client_secret or "",
            "Content-Type": "application/json"
        }

    def get_member(self, member_id: str):
        if not self.base_url:
            return {"member_id": member_id, "status": "Current", "balance": 0}
        url = f"{self.base_url}/Members({member_id})?$expand=Contracts($filter=Status eq 'Current'),memberbalance"
        r = requests.get(url, headers=self._headers(), timeout=10)
        r.raise_for_status()
        return r.json()

    def reserve_class(self, member_id: str, class_id: str, idempotency_key: str):
        if not self.base_url:
            return {"ok": True, "reservation_id": f"r-{class_id}"}
        url = f"{self.base_url}/Classes({class_id})/Reserve"
        payload = {"MemberId": member_id}
        headers = self._headers()
        headers["Idempotency-Key"] = idempotency_key
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()
        
    def get_available_classes(
        self,
        club_id: int | None = None,
        from_iso: str | None = None,
        to_iso: str | None = None,
        member_id: int | None = None,
        fields: list[str] | None = None,
        top: int | None = None, 
    ) -> list[dict]:
        """
        Pobiera listę zaplanowanych zajęć z PerfectGym.

        Odpowiada mniej więcej curle'owi:

        GET /Classes?
            $filter=isDeleted eq false and startdate gt <ISO>
            &$expand=classType
            &$orderby=startdate

        Wrzucamy minimalną logikę – w przyszłości możesz tu dorzucić
        dodatkowe filtry (typ zajęć, klub, zakres dat).
        """
        select_fields = fields or BASE_CLASS_FIELDS
        params: dict[str, str] = {
            "$select": ",".join(select_fields),
        }
        if not settings.pg_base_url:
            logger.warning({"pg": "pg_base_url_missing"})
        if not self.base_url:
            self.logger.warning({"pg": "base_url_missing"})
            return {"value": []}

        url = f"{self.base_url}/Classes"

        # domyślnie – od teraz
        if from_iso is None:
            from_iso = datetime.utcnow()

        # OData oczekuje formatu bez "Z" – dokładnie jak w Twoim curlu.
        # Przykład: 2025-11-22T19:33:10.201Z
        # Tu robimy prosty ISO bez mikrosekund; możesz ewentualnie dopracować.
        start_str = from_iso.replace(microsecond=0).isoformat() + "Z"

        filter_expr = f"isDeleted eq false and startdate gt {start_str}"

        params: Dict[str, Any] = {
            "$filter": filter_expr,
            "$expand": "classType",
            "$orderby": "startdate",
        }
        if top is not None:
            params["$top"] = str(top)

        try:
            resp = requests.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            self.logger.info(
                {
                    "pg": "get_available_classes_ok",
                    "count": len(data.get("value", [])),
                }
            )
            return data
        except requests.RequestException as e:
            self.logger.error({"pg": "get_available_classes_error", "error": str(e)})
            # Bezpieczny fallback – pusta lista
            return {"value": []}

    def get_contracts_by_email_and_phone(
        self,
        email: str,
        phone_number: str,
    ) -> Dict[str, Any]:
        """
        Pobiera kontrakty członka po emailu + numerze telefonu.

        Odpowiada curle'owi:

        GET /Contracts?
            $expand=Member,PaymentPlan
            &$filter=Member/email eq '<email>' and Member/phoneNumber eq '<phone>'

        Zwraca raw JSON z PG – routing sam zdecyduje, jak to sformatować.
        """
        if not self.base_url:
            self.logger.warning({"pg": "base_url_missing"})
            return {"value": []}

        url = f"{self.base_url}/Contracts"

        # Uwaga: w OData stringi muszą być w pojedynczych cudzysłowach.
        # requests zajmie się URL-encodingiem.
        filter_expr = (
            f"Member/email eq '{email}' and Member/phoneNumber eq '{phone_number}'"
        )

        params = {
            "$expand": "Member,PaymentPlan",
            "$filter": filter_expr,
        }

        try:
            resp = requests.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            self.logger.info(
                {
                    "pg": "get_contracts_by_email_and_phone_ok",
                    "count": len(data.get("value", [])),
                }
            )
            return data
        except requests.RequestException as e:
            self.logger.error({"pg": "get_contracts_by_email_and_phone_error", "error": str(e)})
            return {"value": []}

    def get_member_balance(self, member_id: int) -> dict:
        """
        Zwraca informację o saldzie membera.

        Używa:
          GET /Members({id})?$expand=memberBalance

        Oczekiwany kształt:
          {
            "memberBalance": {
                "prepaidBalance": ...,
                "prepaidBonusBalance": ...,
                "currentBalance": ...,
                "memberId": ...,
                "negativeBalanceSince": ...
            },
            ...
          }
        """
        url = f"{self.base_url}/Members({member_id})?$expand=memberBalance"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=10)
            resp.raise_for_status()
            data = resp.json()

            # jeśli to /Members?filter=... przypadkiem:
            if "value" in data:
                items = data.get("value") or []
                data = items[0] if items else {}

            mb = data.get("memberBalance") or {}
            self.logger.info(
                {"pg": "get_member_balance_ok", "member_id": member_id}
            )
            # zwracamy uproszczony słownik
            return {
                "prepaidBalance": mb.get("prepaidBalance", 0),
                "prepaidBonusBalance": mb.get("prepaidBonusBalance", 0),
                "currentBalance": mb.get("currentBalance", 0),
                "negativeBalanceSince": mb.get("negativeBalanceSince"),
                "raw": mb,
            }
        except requests.RequestException as e:
            self.logger.error(
                {"pg": "get_member_balance_error", "member_id": member_id, "error": str(e)}
            )
            # fallback – zero zaległości
            return {
                "prepaidBalance": 0,
                "prepaidBonusBalance": 0,
                "currentBalance": 0,
                "negativeBalanceSince": None,
                "raw": {},
            }
