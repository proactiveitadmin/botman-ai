from __future__ import annotations

import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

from ..common.config import settings
from ..common.constants import CRM_MARKETING_AGREEMENT_ID
from ..common.logging import logger
from ..common.logging_utils import mask_phone

JsonDict = Dict[str, Any]


class PerfectGymClient:
    """Client do integracji z PerfectGym API.

    `base_url` powinien zwykle wskazywać na endpoint OData, np.:
    `https://<club>.perfectgym.com/api/v2.2/odata`.
    """

    DEFAULT_TIMEOUT_S = 10
    TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        *,
        base_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.client_id = client_id or ""
        self.client_secret = client_secret or ""
        self.logger = logger

    @classmethod
    def from_tenant_config(cls, tenant_cfg: dict | None) -> "PerfectGymClient":
        pg_cfg = (tenant_cfg or {}).get("pg") or {}
        if not isinstance(pg_cfg, dict):
            pg_cfg = {}

        return cls(
            base_url=pg_cfg.get("base_url"),
            client_id=pg_cfg.get("client_id"),
            client_secret=pg_cfg.get("client_secret"),
        )

    # ------------------------------------------------------------------ #
    # HTTP helpers
    # ------------------------------------------------------------------ #

    @property
    def api_root(self) -> str:
        """Base URL bez końcowego `/odata` dla endpointów nie-OData."""
        suffix = "/odata"
        if self.base_url.lower().endswith(suffix):
            return self.base_url[: -len(suffix)]
        return self.base_url

    @property
    def is_odata_url(self) -> bool:
        return self.base_url.lower().endswith("/odata")

    def _headers(self) -> dict[str, str]:
        return {
            "X-Client-id": self.client_id,
            "X-Client-Secret": self.client_secret,
            "Content-Type": "application/json",
        }

    def _ensure_base_url(self) -> bool:
        if self.base_url:
            return True
        self.logger.warning({"pg": "base_url_missing"})
        return False

    def _odata_url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _api_url(self, path: str) -> str:
        return f"{self.api_root}/{path.lstrip('/')}"

    @staticmethod
    def _escape_odata_string(value: str) -> str:
        return value.replace("'", "''")

    @staticmethod
    def _safe_json(resp: requests.Response) -> Any:
        try:
            return resp.json()
        except ValueError:
            return None

    @staticmethod
    def _first_value(payload: Any) -> JsonDict:
        if isinstance(payload, list):
            return payload[0] if payload else {}
        if isinstance(payload, dict) and "value" in payload:
            items = payload.get("value") or []
            return items[0] if items else {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _coerce_int(value: int | str, field_name: str) -> int:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid_{field_name}") from exc

    @staticmethod
    def _format_pg_datetime(dt: datetime) -> str:
        """Format wymagany przez PG/OData: `YYYY-MM-DDTHH:MM:SS.mmmZ`."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def _compute_backoff(self, resp: requests.Response | None, attempt: int) -> float:
        base_delay = float(getattr(settings, "pg_retry_base_delay_s", 0.2))
        max_delay = float(getattr(settings, "pg_retry_max_delay_s", 2.0))
        delay = min(max_delay, base_delay * (2 ** max(0, attempt - 1)))

        retry_after = resp.headers.get("Retry-After") if resp is not None else None
        if retry_after:
            try:
                retry_after_s = float(retry_after)
            except ValueError:
                retry_after_s = None
            if retry_after_s is not None and 0 <= retry_after_s <= max_delay:
                delay = retry_after_s

        return delay * random.uniform(0.9, 1.1)

    def _request_with_retry(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        """HTTP request z retry/backoff dla transient errorów.

        Nie wywołuje `raise_for_status()`. Callery decydują, które błędy
        mają być wyjątkiem, a które business-error zwracanym do wyższej warstwy.
        """
        max_attempts = int(getattr(settings, "pg_retry_max_attempts", 3))
        kwargs.setdefault("timeout", self.DEFAULT_TIMEOUT_S)

        method = method.upper()
        for attempt in range(1, max_attempts + 1):
            response: requests.Response | None = None
            try:
                response = requests.request(method, url, **kwargs)
                if (
                    response.status_code in self.TRANSIENT_STATUS_CODES
                    and attempt < max_attempts
                ):
                    time.sleep(self._compute_backoff(response, attempt))
                    continue
                return response
            except requests.RequestException:
                if attempt >= max_attempts:
                    raise
                time.sleep(self._compute_backoff(response, attempt))

        raise requests.RequestException("exhausted retries")

    def _get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        fallback: Any,
        log_event: str,
        log_context: dict[str, Any] | None = None,
        root: str = "odata",
    ) -> Any:
        if not self._ensure_base_url():
            return fallback

        url = self._odata_url(path) if root == "odata" else self._api_url(path)
        try:
            response = self._request_with_retry(
                "GET",
                url,
                headers=self._headers(),
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            self.logger.error(
                {
                    "pg": log_event,
                    "error": str(exc),
                    **(log_context or {}),
                }
            )
            return fallback

    # ------------------------------------------------------------------ #
    # PerfectGym business errors
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_pg_business_error(payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None

        errors = payload.get("errors")
        if not isinstance(errors, list) or not errors:
            return None

        first_error = errors[0]
        if not isinstance(first_error, dict):
            return None

        return {
            "message": first_error.get("message"),
            "code": first_error.get("code"),
            "property": first_error.get("property"),
        }

    @staticmethod
    def _map_pg_error_to_internal(pg_error: dict[str, Any] | None) -> str | None:
        if not pg_error:
            return None

        return {
            "ClassesAlreadyBooked": "classes_already_booked",
        }.get(pg_error.get("code"))

    # ------------------------------------------------------------------ #
    # Members
    # ------------------------------------------------------------------ #

    def get_member(self, member_id: str) -> JsonDict:
        if not self._ensure_base_url():
            return {"member_id": member_id, "status": "Current", "balance": 0}

        response = self._request_with_retry(
            "GET",
            self._odata_url(f"Members({member_id})"),
            headers=self._headers(),
            params={"$expand": "Contracts($filter=Status eq 'Current'),memberbalance"},
        )
        response.raise_for_status()
        return response.json()

    def get_member_by_phone(self, phone: str) -> JsonDict:
        return self._get_json(
            "Members",
            params={
                "$expand": "MemberBalance",
                "$filter": f"phoneNumber eq '{self._escape_odata_string(phone)}'",
            },
            fallback={"value": []},
            log_event="get_member_by_phone_error",
            log_context={"phone": mask_phone(phone)},
        )

    def _get_first_member_field_by_phone(self, phone: str, *field_names: str) -> str | None:
        try:
            payload = self.get_member_by_phone(phone)
            items = (payload or {}).get("value") or []
            if not items:
                return None

            member = items[0]
            for field_name in field_names:
                value = member.get(field_name)
                if value is not None:
                    return str(value).strip()
            return None
        except Exception as exc:  # defensive: to są helpery UX, nie krytyczna ścieżka
            self.logger.warning(
                {
                    "pg": "get_member_field_by_phone_error",
                    "phone": mask_phone(phone),
                    "fields": field_names,
                    "error": str(exc),
                }
            )
            return None

    def get_member_type_by_phone(self, phone: str) -> str | None:
        return self._get_first_member_field_by_phone(phone, "memberType", "membertype")

    def get_member_1st_name_by_phone(self, phone: str) -> str | None:
        return self._get_first_member_field_by_phone(phone, "firstName", "firstname")

    def get_member_balance(self, member_id: int) -> JsonDict:
        empty_balance = {
            "club_id": None,
            "prepaidBalance": 0,
            "prepaidBonusBalance": 0,
            "currentBalance": 0,
            "negativeBalanceSince": None,
            "raw": {},
        }

        payload = self._get_json(
            f"Members({member_id})",
            params={"$expand": "memberBalance"},
            fallback=None,
            log_event="get_member_balance_error",
            log_context={"member_id": member_id},
        )
        if payload is None:
            return empty_balance

        data = self._first_value(payload)
        member_balance = data.get("memberBalance") or data.get("MemberBalance") or {}
        club_id = data.get("homeClubId")

        self.logger.info({"pg": "get_member_balance_ok", "member_id": member_id})
        return {
            "club_id": club_id,
            "prepaidBalance": member_balance.get("prepaidBalance", 0),
            "prepaidBonusBalance": member_balance.get("prepaidBonusBalance", 0),
            "currentBalance": member_balance.get("currentBalance", 0),
            "negativeBalanceSince": member_balance.get("negativeBalanceSince"),
            "raw": member_balance,
        }

    def get_marketing_consent_for_member(self, member_id: int) -> bool:
        if not self._ensure_base_url():
            return False

        odata_filter = (
            f"memberId eq {int(member_id)} "
            f"and memberAgreementId eq {CRM_MARKETING_AGREEMENT_ID} "
            "and agreed eq true"
        )

        payload = self._get_json(
            "MemberAgreementAnswers",
            params={"$filter": odata_filter},
            fallback={"value": []},
            log_event="pg_marketing_consent_check_failed",
            log_context={"member_id": member_id},
        )
        return bool((payload or {}).get("value"))

    # ------------------------------------------------------------------ #
    # Classes / reservations
    # ------------------------------------------------------------------ #

    def reserve_class(
        self,
        member_id: str,
        class_id: str | int,
        idempotency_key: Optional[str] = None,
        comments: Optional[str] = None,
        allow_overlap: bool = False,
    ) -> JsonDict:
        if not self._ensure_base_url():
            self.logger.warning(
                {
                    "msg": "PG disabled (dev mode)",
                    "class_id": class_id,
                    "member_id": member_id,
                }
            )
            return {
                "ok": True,
                "status_code": 200,
                "data": {"fake": True, "classId": class_id, "memberId": member_id},
            }

        try:
            payload = {
                "memberId": self._coerce_int(member_id, "member_id"),
                "classId": self._coerce_int(class_id, "class_id"),
                "bookDespiteOtherBookingsAtTheSameTime": bool(allow_overlap),
                "comments": comments or "booked by Dialo WhatsApp",
            }
        except ValueError as exc:
            return {
                "ok": False,
                "status_code": None,
                "error": str(exc),
                "body": None,
            }

        headers = self._headers()
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        try:
            response = self._request_with_retry(
                "POST",
                self._api_url("ClassBooking/BookClass"),
                json=payload,
                headers=headers,
            )
        except requests.RequestException as exc:
            self.logger.error(
                {
                    "pg": "reserve_class_error",
                    "member_id": member_id,
                    "class_id": class_id,
                    "error": str(exc),
                }
            )
            return {
                "ok": False,
                "status_code": None,
                "error": str(exc),
                "body": None,
            }

        data = self._safe_json(response)
        if response.status_code >= 400:
            pg_error = self._extract_pg_business_error(data)
            mapped_error = self._map_pg_error_to_internal(pg_error)
            self.logger.error(
                {
                    "pg": "reserve_class_error",
                    "member_id": member_id,
                    "class_id": class_id,
                    "status_code": response.status_code,
                    "pg_error": pg_error,
                    "mapped_error": mapped_error,
                }
            )
            return {
                "ok": False,
                "status_code": response.status_code,
                "error": "HTTP error",
                "body": response.text,
                "data": data,
                "pg_error": pg_error,
                "mapped_error": mapped_error,
            }

        return {"ok": True, "status_code": response.status_code, "data": data}

    def get_available_classes(
        self,
        club_id: int | None = None,
        from_iso: datetime | None = None,
        to_iso: datetime | None = None,
        member_id: int | None = None,
        class_type_query: str | None = None,
        fields: list[str] | None = None,
        top: int | None = None,
    ) -> JsonDict:
        # Zachowuję argumenty `club_id`, `member_id`, `fields` dla kompatybilności API.
        # `club_id` i `member_id` nie były używane w oryginalnym kodzie.
        if not self._ensure_base_url():
            return {"value": []}

        if not self.is_odata_url:
            return self._get_json(
                "Classes",
                fallback={"value": []},
                log_event="get_available_classes_error",
            )

        start = from_iso or datetime.now(timezone.utc)
        end = to_iso or start + timedelta(days=2)

        filter_parts = [
            "isDeleted eq false",
            f"startdate gt {self._format_pg_datetime(start)}",
            f"startdate lt {self._format_pg_datetime(end)}",
        ]

        if class_type_query:
            query = self._escape_odata_string(class_type_query.strip().lower())
            if query:
                filter_parts.append(f"contains(tolower(classType/name),'{query}')")

        params: dict[str, Any] = {
            "$filter": " and ".join(filter_parts),
            "$expand": "classType",
            "$orderby": "startdate",
        }
        if fields:
            params["$select"] = ",".join(fields)
        if top is not None:
            params["$top"] = str(top)

        payload = self._get_json(
            "Classes",
            params=params,
            fallback={"value": []},
            log_event="get_available_classes_error",
        )
        self.logger.info(
            {
                "pg": "get_available_classes_ok",
                "count": len((payload or {}).get("value", [])),
            }
        )
        return payload

    def get_class(self, class_id: int | str) -> JsonDict:
        try:
            class_id_int = self._coerce_int(class_id, "class_id")
        except ValueError as exc:
            self.logger.error({"pg": "get_class_error", "class_id": class_id, "error": str(exc)})
            return {}

        payload = self._get_json(
            f"Classes({class_id_int})",
            params={"$expand": "classType"},
            fallback={},
            log_event="get_class_error",
            log_context={"class_id": class_id_int},
        )
        data = self._first_value(payload)
        if data:
            self.logger.info({"pg": "get_class_ok", "class_id": class_id_int})
        return data

    # ------------------------------------------------------------------ #
    # Contracts / payment plans / debt
    # ------------------------------------------------------------------ #

    def get_contract_by_member_id(self, member_id: str) -> JsonDict:
        payload = self._get_json(
            f"Members({member_id})",
            params={"$expand": "Contracts($filter=Status eq 'Current'),memberbalance"},
            fallback={},
            log_event="get_contract_by_member_id_error",
            log_context={"member_id": member_id},
        )
        data = self._first_value(payload)
        contracts = data.get("Contracts") or data.get("contracts") or []
        return next(
            (
                contract
                for contract in contracts
                if contract.get("Status") == "Current" or contract.get("status") == "Current"
            ),
            {},
        )

    def get_paymentplan_by_member_id(self, member_id: str) -> JsonDict:
        payload = self._get_json(
            "contracts",
            params={
                "$filter": f"memberId eq {member_id}",
                "$expand": "paymentPlan($expand=allowedPaymentTypes)",
            },
            fallback={},
            log_event="get_paymentplan_by_member_id_error",
            log_context={"member_id": member_id},
        )
        contracts = payload.get("value", []) if isinstance(payload, dict) else payload
        if not contracts:
            return {}
        return contracts[0].get("paymentPlan") or {}

    def _build_current_debt_items(self, charges: list[JsonDict]) -> tuple[list[JsonDict], list[JsonDict], float]:
        now = datetime.now().astimezone()
        payment_items: list[JsonDict] = []
        customer_items: list[JsonDict] = []
        total_amount = 0.0

        for charge in charges:
            try:
                left_to_pay = float(charge.get("leftToPay") or 0)
            except (TypeError, ValueError):
                continue

            if left_to_pay <= 0:
                continue

            due_date_raw = charge.get("dueDate")
            if due_date_raw:
                try:
                    due_date = datetime.fromisoformat(str(due_date_raw).replace("Z", "+00:00"))
                    if due_date.tzinfo is None:
                        due_date = due_date.replace(tzinfo=now.tzinfo)
                    if due_date > now:
                        continue
                except ValueError:
                    self.logger.warning(
                        {
                            "pg": "get_debt_payment_link_invalid_due_date",
                            "charge_id": charge.get("id"),
                            "dueDate": due_date_raw,
                        }
                    )
                    continue

            transaction_id = charge.get("id")
            if transaction_id is None:
                continue

            amount = round(left_to_pay, 2)
            payment_items.append(
                {
                    "membershipTransactionId": int(transaction_id),
                    "amount": amount,
                }
            )
            customer_items.append(
                {
                    "membershipTransactionId": int(transaction_id),
                    "amount": amount,
                    "dueDate": due_date_raw,
                    "description": charge.get("description"),
                }
            )
            total_amount += amount

        return payment_items, customer_items, round(total_amount, 2)

    def get_debt_payment_link(
        self,
        member_id: int | str,
        club_id: int | str,
        return_url: str,
        save_payment_source_after_success: bool = False,
    ) -> JsonDict:
        if not self._ensure_base_url():
            return {
                "ok": False,
                "status_code": None,
                "error": "base_url_missing",
                "url": None,
                "items": [],
                "totalAmount": 0,
            }

        try:
            member_id_int = self._coerce_int(member_id, "member_id")
            club_id_int = self._coerce_int(club_id, "club_id")
        except ValueError as exc:
            self.logger.error(
                {
                    "pg": "get_debt_payment_link_charges_error",
                    "member_id": member_id,
                    "club_id": club_id,
                    "error": str(exc),
                }
            )
            return {
                "ok": False,
                "status_code": None,
                "error": "invalid_member_or_club_id",
                "url": None,
                "items": [],
                "totalAmount": 0,
            }

        charges_payload = self._get_json(
            "ContractCharges",
            params={
                "$filter": (
                    f"memberid eq {member_id_int} "
                    "and isCancelled eq false "
                    "and isDeleted eq false"
                ),
                "$select": "id,memberId,dueDate,leftToPay,description",
            },
            fallback=None,
            log_event="get_debt_payment_link_charges_error",
            log_context={"member_id": member_id_int},
        )
        if charges_payload is None:
            return {
                "ok": False,
                "status_code": None,
                "error": "failed_to_fetch_charges",
                "url": None,
                "items": [],
                "totalAmount": 0,
            }

        payment_items, customer_items, total_amount = self._build_current_debt_items(
            charges_payload.get("value") or []
        )
        if not payment_items:
            return {
                "ok": True,
                "status_code": 200,
                "url": None,
                "items": [],
                "totalAmount": 0,
                "message": "no_current_debt",
            }

        payload = {
            "returnUrl": return_url,
            "savePaymentSourceAfterSuccess": bool(save_payment_source_after_success),
            "memberId": member_id_int,
            "clubId": club_id_int,
            "membershipTransactionItems": payment_items,
            "totalAmount": total_amount,
        }

        payment_response: requests.Response | None = None
        payment_data: Any = None
        try:
            payment_response = self._request_with_retry(
                "POST",
                self._api_url("CreditCards/PayWithRedirect"),
                json=payload,
                headers=self._headers(),
            )
            payment_data = self._safe_json(payment_response)
            payment_response.raise_for_status()

            self.logger.info(
                {
                    "pg": "get_debt_payment_link_ok",
                    "member_id": member_id_int,
                    "items_count": len(payment_items),
                    "total_amount": total_amount,
                }
            )
            return {
                "ok": True,
                "status_code": payment_response.status_code,
                "url": (payment_data or {}).get("url"),
                "processKey": (payment_data or {}).get("processKey"),
                "paymentProviderName": (payment_data or {}).get("paymentProviderName"),
                "items": customer_items,
                "totalAmount": total_amount,
                "data": payment_data,
            }
        except requests.RequestException as exc:
            self.logger.error(
                {
                    "pg": "get_debt_payment_link_payment_error",
                    "member_id": member_id_int,
                    "error": str(exc),
                }
            )
            return {
                "ok": False,
                "status_code": getattr(payment_response, "status_code", None),
                "error": str(exc),
                "url": None,
                "items": customer_items,
                "totalAmount": total_amount,
                "data": payment_data,
            }

    # ------------------------------------------------------------------ #
    # Products
    # ------------------------------------------------------------------ #

    def get_product(self, product_id: int | str) -> JsonDict:
        try:
            product_id_int = self._coerce_int(product_id, "product_id")
        except ValueError as exc:
            self.logger.error(
                {"pg": "get_product_error", "product_id": product_id, "error": str(exc)}
            )
            return {}

        payload = self._get_json(
            "Products",
            params={"$filter": f"Id eq {product_id_int} and isDeleted eq false"},
            fallback={},
            log_event="get_product_error",
            log_context={"product_id": product_id_int},
        )
        product = self._first_value(payload)
        if product:
            self.logger.info({"pg": "get_product_ok", "product_id": product_id_int})
        return product

    def get_product_payment_link(self, member_id: int, product_id: int | str) -> JsonDict:
        """TODO: implementacja generowania linku produktu.

        Oryginalna metoda pobierała produkt, ale finalnie zawsze zwracała `{}`.
        Zostawiam publiczną sygnaturę i obecny kontrakt zwrotki, żeby nie zepsuć
        istniejących callerów. Dane produktu są pobierane i logowane diagnostycznie.
        """
        product = self.get_product(product_id)
        self.logger.warning(
            {
                "pg": "get_product_payment_link_not_implemented",
                "member_id": member_id,
                "product_id": product_id,
                "product_found": bool(product),
            }
        )
        return {}
