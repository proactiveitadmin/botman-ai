from __future__ import annotations

from typing import Optional
from datetime import datetime
from urllib.parse import quote

from ..adapters.perfectgym_client import PerfectGymClient
from ..common.logging import logger
from ..common.logging_utils import mask_phone
from ..common.rate_limiter import InMemoryRateLimiter
from .clients_factory import ClientsFactory
from ..common.constants import (
    ENUM_CRM_RETURN_OK,
    ENUM_CRM_RETURN_ALREADY_BOOKED,
    ENUM_CRM_RETURN_FAIL,
    CRM_MARKETING_AGREEMENT_ID,
)

class CRMService:
    """
    Warstwa usługowa dla integracji CRM (PerfectGym + inne w przyszłości).

    Routing i inne serwisy nie korzystają bezpośrednio z PerfectGymClient,
    tylko z tej klasy. Dzięki temu łatwo podmienić CRM w przyszłości.
    """

    def __init__(
        self,
        client: Optional[PerfectGymClient] = None,
        *,
        clients_factory: ClientsFactory | None = None,
        limiter: InMemoryRateLimiter | None = None,
    ) -> None:
        # Backward-compatible: if factory not provided, use a single global client
        self._factory = clients_factory
        self._client = client or (None if self._factory else PerfectGymClient())
        self._limiter = limiter or InMemoryRateLimiter()

    def _client_for(self, tenant_id: str) -> PerfectGymClient:
        if self._factory:
            return self._factory.perfectgym(tenant_id)
        if self._client:
            return self._client
        raise RuntimeError("CRMService misconfigured: missing clients_factory or client")

    def _crm_gate(self, tenant_id: str) -> None:
        """Rate-limit calls to PG per tenant (per invoke)."""
        from ..common.config import settings
        self._limiter.acquire(
            f"pg:tenant:{tenant_id}",
            rate=float(getattr(settings, "pg_rate_limit_rps", 30.0)),
            burst=float(getattr(settings, "pg_rate_limit_burst", 30.0)),
        )
        
    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """
        Normalizuje telefon z kanałów (WhatsApp itp.) do formatu akceptowanego przez PG,
        np. 'whatsapp:+48123123123' -> '+48123123123'.
        """
        if not phone:
            return ""
        phone = phone.strip()
        if phone.startswith("whatsapp:"):
            phone = phone.split(":", 1)[1]
        return phone

    # ------------------------------------------------------------------ #
    # Metody delegujące do PerfectGymClient
    # ------------------------------------------------------------------ #

    def get_member_by_phone(self, tenant_id: str, phone: str) -> dict:
        """
        Prosty wrapper na PerfectGymClient.get_member_by_phone.

        Normalizuje numer (usuwa prefix 'whatsapp:').
        """
        norm_phone = self._normalize_phone(phone)
        self._crm_gate(tenant_id)
        return self._client_for(tenant_id).get_member_by_phone(phone=norm_phone)

    def get_email_by_msg(self, tenant_id: str, msg: str) -> str | None:
        try:
            members_resp = self.get_member_by_phone(tenant_id, msg.from_phone)
            items = (members_resp or {}).get("value") or []
            if items:
                return (items[0].get("email") or "").strip()
        except Exception:
            logger.warning(
                {
                    "crm": "get_email_by_msg failed",
                    "tenant_id": tenant_id,
                    "msg.from_phone": msg.from_phone,
                }
            )
            return None

    def get_member_id_by_msg(self, tenant_id: str, msg: str) -> str | None:
        try:
            members_resp = self.get_member_by_phone(tenant_id, msg.from_phone)
            items = (members_resp or {}).get("value") or []
            if items:
                return str(items[0].get("id") or items[0].get("Id"))
        except Exception:
            logger.warning(
                {
                    "crm": "get_member_id_by_msg failed",
                    "tenant_id": tenant_id,
                    "msg.from_phone": msg.from_phone,
                }
            )
            return None

    def get_available_classes(
        self,
        tenant_id: str,
        club_id: int | None = None,
        from_iso: str | None = None,
        to_iso: str | None = None,
        member_id: int | None = None,
        class_type_query: str | None = None,
        fields: list[str] | None = None,
        top: int | None = None,
    ) -> dict:
        """
        Zwraca raw JSON z PG (dict z kluczem 'value').
        """
        self._crm_gate(tenant_id)
        return self._client_for(tenant_id).get_available_classes(
            club_id=club_id,
            from_iso=from_iso,
            to_iso=to_iso,
            member_id=member_id,
            class_type_query=class_type_query,
            fields=fields,
            top=top,
        )
        
    def get_member_type_by_phone(self, tenant_id: str, phone: str) -> Optional[str]:
        """Zwraca typ użytkownika w CRM (dla PerfectGym: memberType).

        Logika specyficzna dla danego CRM powinna być zaimplementowana po stronie klienta,
        np. PerfectGymClient.get_member_type_by_phone().
        """
        norm_phone = self._normalize_phone(phone)
        self._crm_gate(tenant_id)
        client = self._client_for(tenant_id)
        getter = getattr(client, "get_member_type_by_phone", None)
        if callable(getter):
            return getter(phone=norm_phone)
        # Inne CRM-y powinny dostarczyć analogiczną metodę w swoim kliencie.
        return None
        
    def get_class_by_id(
        self,
        tenant_id: str,
        class_id: str | int,
    ) -> dict:
        """
        Zwraca pojedyncze zajęcia po ID.

        ale zostawiamy go w sygnaturze na przyszłość.
        """
        self._crm_gate(tenant_id)
        return self._client_for(tenant_id).get_class(class_id)


    def get_contracts_by_email_and_phone(
        self,
        tenant_id: str,
        email: str,
        phone_number: str,
    ) -> dict:
        self._crm_gate(tenant_id)
        return self._client_for(tenant_id).get_contracts_by_email_and_phone(
            email=email,
            phone_number=phone_number,
        )

    def get_contracts_by_member_id(
        self,
        tenant_id: str,
        member_id: str,
    ) -> dict:
        """
        Zwraca raw JSON z PG (dict z 'value').
        """
        self._crm_gate(tenant_id)
        return self._client_for(tenant_id).get_contracts_by_member_id(member_id=member_id)

    def get_member_balance(
        self,
        tenant_id: str,
        member_id: int,
    ) -> dict:
        self._crm_gate(tenant_id)
        return self._client_for(tenant_id).get_member_balance(member_id=member_id)

    def get_marketing_consent_for_member(self, tenant_id: str, *, member_id: int) -> bool:
        """
        Sprawdza w PerfectGym czy member ma zgodę marketingową (agreed = true).
        memberAgreementId traktujemy jako stałą (1).
        """
        self._crm_gate(tenant_id)
        pg = self._client_for(tenant_id)

        odata_filter = (
            f"memberId eq {int(member_id)} "
            f"and memberAgreementId eq {CRM_MARKETING_AGREEMENT_ID} "
            f"and agreed eq true"
        )

        url = (
            f"{pg.base_url}/MemberAgreementAnswers"
            f"?$filter={quote(odata_filter, safe=' =$andtruefalse')}"
        )

        try:
            resp = pg._request_with_retry(
                "GET",
                url,
                headers=pg._headers(),
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json() or {}
            return bool(data.get("value"))
        except Exception as e:
            logger.error(
                {
                    "crm": "pg_marketing_consent_check_failed",
                    "tenant_id": tenant_id,
                    "member_id": member_id,
                    "error": str(e),
                }
            )
            # fail-safe: jak nie wiemy, to NIE wysyłamy
            return False
    
    #stub cofniecia zgody, TODO: zaimplementowac cofniecie zgody
    def revoke_marketing_consent_for_member(
        self,
        tenant_id: str,
        *,
        member_id: int,
        reason: str | None = None,
    ):
        logger.warning(
            {
                "crm": "pg_revoke_marketing_consent_not_implemented",
                "tenant_id": tenant_id,
                "member_id": member_id,
                "reason": reason,
            }
        )
        raise NotImplementedError(
            "PerfectGym revoke consent endpoint not implemented yet"
        ) 
    
    #stub dodania zgody, TODO: zaimplementowac cofniecie zgody
    def grant_marketing_consent_for_member(
        self,
        tenant_id: str,
        *,
        member_id: int,
        reason: str | None = None,
    ):
        logger.warning(
            {
                "crm": "pg_grant_marketing_consent_not_implemented",
                "tenant_id": tenant_id,
                "member_id": member_id,
                "reason": reason,
            }
        )
        raise NotImplementedError(
            "PerfectGym grant consent endpoint not implemented yet"
        )  
        
    def reserve_class(
        self,
        tenant_id: str,
        member_id: str,
        class_id: str | int,
        idempotency_key: str | None = None,
        comments: str | None = None,
        allow_overlap: bool = False,
    ) -> int:
        """
        Rezerwacja zajęć w CRM – zawija PerfectGymClient.reserve_class.
        RoutingService oczekuje, że zwrócony dict będzie miał pole "ok" (True/False).
        """
        self._crm_gate(tenant_id)
        res = self._client_for(tenant_id).reserve_class(
            member_id=member_id,
            class_id=class_id,
            idempotency_key=idempotency_key,
            comments=comments,
            allow_overlap=allow_overlap,
        )
        if (res or {}).get("ok", True):
            return  ENUM_CRM_RETURN_OK
        else:
            mapped_error = (res or {}).get("mapped_error")
            crm_code = ((res or {}).get("pg_error") or {}).get("code")

            if mapped_error == "classes_already_booked" or crm_code == "ClassesAlreadyBooked":
                return ENUM_CRM_RETURN_ALREADY_BOOKED
        return ENUM_CRM_RETURN_FAIL
