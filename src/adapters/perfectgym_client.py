import requests
import time
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote
import logging

from ..common.logging_utils import mask_phone
from ..common.config import settings
from ..common.timing import timed

logger = logging.getLogger("botman-ai")


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
    def __init__(
        self,
        *,
        base_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        # np. "https://<club>.perfectgym.com/api/v2.2/odata"
        self.base_url: str = ((base_url or "")).rstrip("/")
        self.client_id: str = (client_id or "")
        self.client_secret: str = (client_secret or "")
        self.logger = logger
    
    @classmethod
    def from_tenant_config(cls, tenant_cfg: dict) -> "PerfectGymClient":
        pg = (tenant_cfg or {}).get("pg") or {}
        if not isinstance(pg, dict):
            pg = {}
        return cls(
            base_url=pg.get("base_url"),
            client_id=pg.get("client_id"),
            client_secret=pg.get("client_secret"),
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _headers(self) -> Dict[str, str]:
        return {
            "X-Client-id": self.client_id,
            "X-Client-Secret": self.client_secret,
            "Content-Type": "application/json",
        }

    def _ensure_base_url(self) -> bool:
        if not self.base_url:
            self.logger.warning({"pg": "base_url_missing"})
            return False
        return True

    def _compute_backoff(self, resp: requests.Response | None, attempt: int) -> float:
        base = float(getattr(settings, "pg_retry_base_delay_s", 0.2))
        max_d = float(getattr(settings, "pg_retry_max_delay_s", 2.0))
        # exponential backoff: base * 2^(attempt-1)
        delay = min(max_d, base * (2 ** max(0, attempt - 1)))

        # Retry-After header (if present) overrides if shorter than max_d
        if resp is not None:
            ra = resp.headers.get("Retry-After") if hasattr(resp, "headers") else None
            if ra:
                try:
                    ra_f = float(ra)
                    if 0 <= ra_f <= max_d:
                        delay = ra_f
                except ValueError:
                    pass

        # jitter
        delay *= random.uniform(0.9, 1.1)
        return delay

    def _request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make an HTTP request with retry/backoff for transient errors.

        Notes:
        - For GET we call requests.get(...) to stay compatible with our lightweight test fixture
          that monkeypatches requests.get.
        - For POST/other verbs we call requests.request(...) to stay compatible with tests that
          monkeypatch requests.request.
        - This helper DOES NOT call raise_for_status(); callers decide how to handle 4xx.
        """
        max_attempts = int(getattr(settings, "pg_retry_max_attempts", 3))
        kwargs.setdefault("timeout", 10)

        method_u = method.upper()
        for attempt in range(1, max_attempts + 1):
            resp: requests.Response | None = None
            try:
                resp = requests.request(method_u, url, **kwargs)

                if resp is not None and resp.status_code in (429, 500, 502, 503, 504) and attempt < max_attempts:
                    time.sleep(self._compute_backoff(resp=resp, attempt=attempt))
                    continue

                return resp

            except requests.RequestException:
                if attempt >= max_attempts:
                    raise
                time.sleep(self._compute_backoff(resp=resp, attempt=attempt))

        # should be unreachable, but keep mypy happy
        raise requests.RequestException("exhausted retries")


    # ------------------------------------------------------------------ #
    # Members
    # ------------------------------------------------------------------ #

    def get_member(self, member_id: str) -> Dict[str, Any]:
        if not self._ensure_base_url():
            return {"member_id": member_id, "status": "Current", "balance": 0}

        url = (
            f"{self.base_url}/Members({member_id})"
            "?$expand=Contracts($filter=Status eq 'Current'),memberbalance"
        )
        resp = self._request_with_retry("GET", url, headers=self._headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()
        
    def get_member_type_by_phone(self, phone: str) -> Optional[str]:
        """Zwraca memberType dla numeru telefonu (PerfectGym-specific).

        W PG pobieramy memberów z endpointu /Members filtrowanego po phoneNumber,
        a następnie odczytujemy pole memberType (czasem zwracane jako membertype).
        """
        try:
            resp = self.get_member_by_phone(phone=phone)
            items = (resp or {}).get("value") or []
            if not items:
                return None
            mt = items[0].get("memberType") or items[0].get("membertype")
            return (str(mt).strip() if mt is not None else None)
        except Exception:
            return None

    def get_member_by_phone(self, phone: str) -> Dict[str, Any]:
        """
        Zwraca listę memberów dopasowanych po numerze telefonu.

        GET /Members?$expand=MemberBalance&$filter=phoneNumber eq '<phone-url-encoded>'
        """
        if not self._ensure_base_url():
            return {"value": []}

        # PerfectGym oczekuje numeru w formacie %2B48..., więc url-encode
        quoted = quote(phone, safe="")  # '+48123...' → '%2B48123...'

        url = (
            f"{self.base_url}/Members"
            f"?$expand=MemberBalance"
            f"&$filter=phoneNumber eq '{quoted}'"
        )

        try:
            resp = self._request_with_retry("GET", url, headers=self._headers(), timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            self.logger.error(
                {
                    "pg": "get_member_by_phone_error",
                    "phone": mask_phone(phone),
                    "error": str(e),
                }
            )
            return {"value": []}
    @staticmethod
    def _extract_pg_business_error(payload: Any) -> dict | None:
        """Wyciąga pierwszy business error z odpowiedzi PG.

        Oczekiwany format:
        {
            "errors": [
                {
                    "message": "Classes already booked.",
                    "code": "ClassesAlreadyBooked",
                    ...
                }
            ]
        }
        """
        if not isinstance(payload, dict):
            return None
        errors = payload.get("errors")
        if not isinstance(errors, list) or not errors:
            return None
        first = errors[0]
        if not isinstance(first, dict):
            return None
        return {
            "message": first.get("message"),
            "code": first.get("code"),
            "property": first.get("property"),
        }

    @staticmethod
    def _map_pg_error_to_internal(pg_error: dict | None) -> str | None:
        """Mapuje znane błędy PG na stabilne kody wewnętrzne."""
        if not pg_error:
            return None
        code = pg_error.get("code")
        if code == "ClassesAlreadyBooked":
            return "classes_already_booked"
        return None

    # ------------------------------------------------------------------ #
    # Classes / rezerwacje
    # ------------------------------------------------------------------ #

    def reserve_class(
        self,
        member_id: str,
        class_id: str | int,
        idempotency_key: Optional[str] = None,
        comments: Optional[str] = None,
        allow_overlap: bool = False,
    ) -> Dict[str, Any]:
        """
        Rezerwacja zajęć w PerfectGym – endpoint:
        POST /api/v2.2/ClassBooking/BookClass

        Zakładamy, że pg_base_url wskazuje na /api/v2.2/odata
        → dlatego usuwamy /odata na potrzeby BookClass.
        """
        if not self._ensure_base_url():
            # Fallback w trybie "dev" bez PG – udajemy sukces          
            logger.warning({
                "msg": "PG disabled (dev mode)", 
                "class_id": class_id, 
                "member_id": member_id})
            return {
                "ok": True,
                "status_code": 200,
                "data": {"fake": True, "classId": class_id, "memberId": member_id},
            }

        # API BookClass zwykle jest pod /api/v2.2, bez /odata
        api_root = self.base_url.replace("/odata", "")
        url = f"{api_root}/ClassBooking/BookClass"

        payload = {
            "memberId": int(member_id),
            "classId": int(class_id),
            "bookDespiteOtherBookingsAtTheSameTime": bool(allow_overlap),
            "comments": comments or "booked by Botman WhatsApp",
        }

        headers = self._headers()
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            resp = self._request_with_retry("POST", url, json=payload, headers=headers, timeout=10)
        except requests.RequestException as e:
            self.logger.error(
                {
                    "pg": "reserve_class_error",
                    "member_id": member_id,
                    "class_id": class_id,
                    "error": str(e),
                }
            )
            return {
                "ok": False,
                "status_code": None,
                "error": str(e),
                "body": None,
            }

        # PG czasem zwraca business-error w JSON nawet dla 4xx.
        # Parsujemy JSON przed raise_for_status, żeby móc go zmapować i dać lepszy UX.
        try:
            data = resp.json()
        except ValueError:
            data = None

        if resp.status_code >= 400:
            pg_error = self._extract_pg_business_error(data)
            mapped = self._map_pg_error_to_internal(pg_error)

            # nadal wywołaj raise_for_status() żeby error był spójny w logach
            try:
                resp.raise_for_status()
            except requests.HTTPError as e:
                self.logger.error(
                    {
                        "pg": "reserve_class_error",
                        "member_id": member_id,
                        "error": "HTTP error",
                    }
                )
                return {
                    "ok": False,
                    "status_code": resp.status_code,
                    "error": "HTTP error",
                    "body": resp.text,
                    "data": data,
                    "pg_error": pg_error,
                    "mapped_error": mapped,
                }

            # teoretycznie nie powinno się zdarzyć, ale zostawiamy bezpieczny fallback
            self.logger.error(
                {
                    "pg": "reserve_class_error",
                    "member_id": member_id,
                    "error": "HTTP error",
                }
            )
            return {
                "ok": False,
                "status_code": resp.status_code,
                "error": str(e),
                "body": resp.text,
            }

        try:
            data = resp.json()
        except ValueError:
            data = None

        return {
            "ok": True,
            "status_code": resp.status_code,
            "data": data,
        }

   
    def get_available_classes(
        self,
        club_id: int | None = None,
        from_iso: datetime | None = None,
        to_iso: datetime | None = None,
        member_id: int | None = None,
        class_type_query: str | None = None,
        fields: list[str] | None = None,
        top: int | None = None,
    ) -> Dict[str, Any]:
        """
        Pobiera listę klas w formacie identycznym jak działający curl.
        """

        if not self._ensure_base_url():
            return {"value": []}

        url = f"{self.base_url}/Classes"
        
        # Uproszczony tryb (bez OData query params) — używany w testach i w prostych integracjach,
        # gdy base_url nie wskazuje na /odata.
        if "odata" not in self.base_url.lower():
            try:
                resp = self._request_with_retry("GET", url, headers=self._headers(), timeout=10)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                self.logger.error({"pg": "get_available_classes_error", "error": str(e)})
                return {"value": []}
                
        # --- FORMATOWANIE DATY DOKŁADNIE JAK W CURLU --- #
        if from_iso is None:
            from_iso = datetime.utcnow()
            
        if to_iso is None:
            to_iso = from_iso + timedelta(days=2)

        # Format: 2025-11-22T19:33:10.201Z
        # PG wymaga milisekund oraz "Z" na końcu
        start_str = (
            from_iso.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]  # mikrosekundy → milisekundy
            + "Z"
        )
        end_str = (
            to_iso.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]  # mikrosekundy → milisekundy
            + "Z"
        )
        filter_expr = f"isDeleted eq false and startdate gt {start_str} and startdate lt {end_str}"
        # dodatkowy filtr po typie zajęć (np. 'pilates')
        # wymaganie: and contains(tolower(classType/name),'pilates')
        if class_type_query:
            q = class_type_query.strip().lower().replace("'", "''")
            if q:
                filter_expr += f" and contains(tolower(classType/name),'{q}')"
        # --- PARAMETRY IDENTYCZNE JAK W TWOIM CURLU --- #
        params = {
            "$filter": filter_expr,
            "$expand": "classType",
            "$orderby": "startdate",
        }

        if top is not None:
            params["$top"] = str(top)

        try:
            resp = self._request_with_retry("GET", url, headers=self._headers(), params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            self.logger.info(
                {
                    "pg": "get_available_classes_ok",
                    "count": len(data.get('value', [])),
                }
            )
            return data

        except requests.RequestException as e:
            self.logger.error({
                "pg": "get_available_classes_error",
                "error": str(e),
            })
            return {"value": []}
    # ------------------------------------------------------------------ #
    # Contracts / balance
    # ------------------------------------------------------------------ #

    def get_contracts_by_email_and_phone(
        self,
        email: str,
        phone_number: str,
    ) -> Dict[str, Any]:
        """
        GET /Contracts?
            $expand=Member,PaymentPlan
            &$filter=Member/email eq '<email>' and Member/phoneNumber eq '<phone>'
        """
        if not self._ensure_base_url():
            return {"value": []}

        url = f"{self.base_url}/Contracts"

        filter_expr = (
            f"Member/email eq '{email}' and Member/phoneNumber eq '{phone_number}'"
        )

        params = {
            "$expand": "Member,PaymentPlan",
            "$filter": filter_expr,
        }

        try:
            resp = self._request_with_retry("GET", url, headers=self._headers(), params=params, timeout=10)
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
            self.logger.error(
                {"pg": "get_contracts_by_email_and_phone_error", "error": str(e)}
            )
            return {"value": []}

    def get_contracts_by_member_id(self, member_id: str) -> Dict[str, Any]:
        """
        Zwraca listę kontraktów dla członka PerfectGym.

        Używa:
          GET /Members({member_id})?$expand=Contracts($filter=Status eq 'Current'),memberbalance

        Zwracamy ujednolicony kształt:
          {"value": [ ...lista kontraktów... ]}
        """
        if not self._ensure_base_url():
            return {"value": []}

        # dokładnie taki URL, jak w logu, który działał
        url = (
            f"{self.base_url}/Members({member_id})"
            "?$expand=Contracts($filter=Status eq 'Current'),memberbalance"
        )

        try:
            resp = self._request_with_retry("GET", url, headers=self._headers(), timeout=10)
            resp.raise_for_status()
            data = resp.json()

            # PerfectGym w takim zapytaniu zwraca pojedynczego membera z polem Contracts
            contracts = data.get("Contracts") or data.get("contracts") or []

            return {"value": contracts}

        except requests.RequestException as e:
            self.logger.error(
                {
                    "pg": "get_contracts_by_member_id_error",
                    "member_id": member_id,
                    "error": str(e),
                }
            )
            return {"value": []}


    def get_member_balance(self, member_id: int) -> Dict[str, Any]:
        """
        GET /Members({id})?$expand=memberBalance
        """
        if not self._ensure_base_url():
            return {
                "prepaidBalance": 0,
                "prepaidBonusBalance": 0,
                "currentBalance": 0,
                "negativeBalanceSince": None,
                "raw": {},
            }

        url = f"{self.base_url}/Members({member_id})?$expand=memberBalance"
        try:
            resp = self._request_with_retry("GET", url, headers=self._headers(), timeout=10)
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
            return {
                "prepaidBalance": 0,
                "prepaidBonusBalance": 0,
                "currentBalance": 0,
                "negativeBalanceSince": None,
                "raw": {},
            }

    # ------------------------------------------------------------------ #
    # Classes – pojedyncza klasa po ID
    # ------------------------------------------------------------------ #

    def get_class(self, class_id: int | str) -> Dict[str, Any]:
        """
        Zwraca pojedyncze zajęcia (klasę) po ID.

        GET /Classes({id})?$expand=classType
        """
        if not self._ensure_base_url():
            # brak konfiguracji PG → zwracamy pusty obiekt, żeby nie wywalić flow
            return {}

        # dopuszczamy zarówno int, jak i str z cyframi
        if isinstance(class_id, str) and class_id.isdigit():
            cid = int(class_id)
        else:
            cid = class_id

        url = f"{self.base_url}/Classes({cid})?$expand=classType"

        try:
            resp = self._request_with_retry("GET", url, headers=self._headers(), timeout=10)
            resp.raise_for_status()
            data = resp.json()

            # na wszelki wypadek – gdyby ktoś jednak zrobił redirect na kolekcję
            if isinstance(data, dict) and "value" in data:
                items = data.get("value") or []
                data = items[0] if items else {}

            self.logger.info(
                {
                    "pg": "get_class_ok",
                    "class_id": cid,
                }
            )
            return data

        except requests.RequestException as e:
            self.logger.error(
                {
                    "pg": "get_class_error",
                    "class_id": cid,
                    "error": str(e),
                }
            )
            return {}
