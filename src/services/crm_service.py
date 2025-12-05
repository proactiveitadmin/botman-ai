from __future__ import annotations

from typing import Optional, Dict, Any
from datetime import datetime
import re
import requests

from ..adapters.perfectgym_client import PerfectGymClient
from ..repos.members_index_repo import MembersIndexRepo
from ..common.logging import logger


class CRMService:
    """
    Warstwa usługowa dla integracji CRM (PerfectGym + inne w przyszłości).

    Routing i inne serwisy nie korzystają bezpośrednio z PerfectGymClient,
    tylko z tej klasy. Dzięki temu łatwo podmienić CRM w przyszłości.
    """

    def __init__(self, client: Optional[PerfectGymClient] = None) -> None:
        self.client = client or PerfectGymClient()

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

    def get_member_by_phone(self, tenant_id: str, phone: str) -> dict:
        """
        Prosty wrapper na PerfectGymClient.get_member_by_phone.

        Normalizuje numer (usuwa prefix 'whatsapp:').
        """
        if phone.startswith("whatsapp:"):
            phone = phone.split(":", 1)[1]
        return self.client.get_member_by_phone(phone=phone)
        
    def get_available_classes(
        self,
        tenant_id: str,
        club_id: int | None = None,
        from_iso: str | None = None,
        to_iso: str | None = None,
        member_id: int | None = None,
        fields: list[str] | None = None,
        top: int | None = None,
    ) -> list[dict]:
        return self.client.get_available_classes(
            club_id=club_id,
            from_iso=from_iso,
            to_iso=to_iso,
            member_id=member_id,
            fields=fields,
            top=top,
        )

    def get_contracts_by_email_and_phone(
        self,
        tenant_id: str,
        email: str,
        phone_number: str,
    ) -> dict:
        return self.client.get_contracts_by_email_and_phone(
            email=email,
            phone_number=phone_number,
        )
    
    def get_contracts_by_member_id(
        self, 
        tenant_id: str, 
        member_id: str
    ) -> dict:
        return self.client.get_contracts_by_member_id(
            member_id=member_id,
        )
        
        
    def get_member_balance(
        self,
        tenant_id: str,
        member_id: int,
    ) -> dict:
        return self.client.get_member_balance(member_id=member_id)

    def verify_member_challenge(
        self,
        tenant_id: str,
        phone: str,
        challenge_type: str,
        answer: str,
    ) -> bool:
        """
        Sprawdza odpowiedź użytkownika na challenge na bazie danych PerfectGym.

        challenge_type:
        - "dob"   → sprawdź dzień i miesiąc urodzenia (DD-MM),
        - "email" → sprawdź email case-insensitive.

        Zwraca True/False.
        """
        answer = (answer or "").strip()
        if not answer:
            return False

        # 1) pobierz membera z PG po numerze telefonu
        try:
            members_resp = self.get_member_by_phone(tenant_id, phone)
        except Exception as e:
            logger.error(
                {
                    "crm": "verify_member_challenge_members_index_error",
                    "tenant_id": tenant_id,
                    "phone": phone,
                    "error": str(e),
                }
            )
            return False

        items = (members_resp or {}).get("value") or []
        if not items:
            return False

        # zazwyczaj 1 member, jak będzie więcej – bierzemy pierwszego
        member = items[0]

        if challenge_type == "dob":
            # PerfectGym zwraca zwykle birthDate w formacie ISO 'YYYY-MM-DD...'
            dob_raw = member.get("birthDate") or member.get("birthdate")
            if not dob_raw:
                return False

            from datetime import datetime

            try:
                dob = datetime.fromisoformat(dob_raw[:10])
            except Exception:
                return False

            # normalizacja odpowiedzi: obsługujemy "01-05", "1.5", "01/05/1990" itd.
            norm = (
                answer.replace(" ", "")
                .replace(".", "-")
                .replace("/", "-")
            )
            parts = norm.split("-")
            try:
                day = int(parts[0])
                month = int(parts[1])
            except (ValueError, IndexError):
                return False

            return day == dob.day and month == dob.month

        if challenge_type == "email":
            expected = (member.get("email") or "").strip().lower()
            given = answer.strip().lower()
            return bool(expected) and expected == given

        # inne typy challenge na razie nieobsługiwane
        return False

    def reserve_class(
        self,
        tenant_id: str,
        member_id: str,
        class_id: str | int,
        idempotency_key: str | None = None,
        comments: str | None = None,
        allow_overlap: bool = False,
    ) -> dict:
        """
        Rezerwacja zajęć w PerfectGym – nowy endpoint:
        POST /api/v2.2/ClassBooking/BookClass
        """

        url = f"{self.base_url}/ClassBooking/BookClass"

        payload = {
            "memberId": int(member_id),
            "classId": int(class_id),
            "bookDespiteOtherBookingsAtTheSameTime": bool(allow_overlap),
            "comments": comments or "booked by Botman WhatsApp",
        }

        headers = self._build_pg_headers(tenant_id)
        headers["Content-Type"] = "application/json"

        # Idempotencja (zgodnie z dokumentacją systemu):contentReference[oaicite:1]{index=1}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        resp = self.session.post(url, json=payload, headers=headers, timeout=10)

        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            # logowanie + zwrot struktury, którą oczekuje RoutingService
            return {
                "ok": False,
                "status_code": resp.status_code,
                "error": str(e),
                "body": resp.text,
            }

        data = None
        try:
            data = resp.json()
        except ValueError:
            data = None

        return {
            "ok": True,
            "status_code": resp.status_code,
            "data": data,
        }

    def _build_pg_headers(self, tenant_id: str) -> dict:
        """
        Helper: buduje nagłówki dla PerfectGym.
        Jeśli masz multi-tenant, tutaj możesz wstrzyknąć inne client-id/secret na tenant.
        """
        return {
            "X-Client-id": settings.pg_client_id,
            "X-Client-Secret": settings.pg_client_secret,
            # plus ew. Authorization, jeśli używacie tokenów
        }
