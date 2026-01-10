from __future__ import annotations

from typing import Optional
from datetime import datetime

from ..adapters.perfectgym_client import PerfectGymClient
from ..common.logging import logger
from ..common.logging_utils import mask_phone
from ..common.rate_limiter import InMemoryRateLimiter
from .clients_factory import ClientsFactory


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
        self._client = client or PerfectGymClient()
        self._factory = clients_factory
        self._limiter = limiter or InMemoryRateLimiter()

    def _client_for(self, tenant_id: str) -> PerfectGymClient:
        if self._factory:
            return self._factory.perfectgym(tenant_id)
        return self._client

    def _pg_gate(self, tenant_id: str) -> None:
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
        self._pg_gate(tenant_id)
        return self._client_for(tenant_id).get_member_by_phone(phone=norm_phone)

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
        self._pg_gate(tenant_id)
        return self._client_for(tenant_id).get_available_classes(
            club_id=club_id,
            from_iso=from_iso,
            to_iso=to_iso,
            member_id=member_id,
            class_type_query=class_type_query,
            fields=fields,
            top=top,
        )

    def get_class_by_id(
        self,
        tenant_id: str,
        class_id: str | int,
    ) -> dict:
        """
        Zwraca pojedyncze zajęcia po ID.

        tenant_id na razie jest ignorowany (konfiguracja PG jest globalna),
        ale zostawiamy go w sygnaturze na przyszłość.
        """
        self._pg_gate(tenant_id)
        return self._client_for(tenant_id).get_class(class_id)


    def get_contracts_by_email_and_phone(
        self,
        tenant_id: str,
        email: str,
        phone_number: str,
    ) -> dict:
        self._pg_gate(tenant_id)
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
        self._pg_gate(tenant_id)
        return self._client_for(tenant_id).get_contracts_by_member_id(member_id=member_id)

    def get_member_balance(
        self,
        tenant_id: str,
        member_id: int,
    ) -> dict:
        self._pg_gate(tenant_id)
        return self._client_for(tenant_id).get_member_balance(member_id=member_id)

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
        Rezerwacja zajęć w CRM – zawija PerfectGymClient.reserve_class.
        RoutingService oczekuje, że zwrócony dict będzie miał pole "ok" (True/False).
        """
        self._pg_gate(tenant_id)
        return self._client_for(tenant_id).reserve_class(
            member_id=member_id,
            class_id=class_id,
            idempotency_key=idempotency_key,
            comments=comments,
            allow_overlap=allow_overlap,
        )

    # ------------------------------------------------------------------ #
    # verify_member_challenge – prawdziwa logika
    # ------------------------------------------------------------------ #


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
                    "phone": mask_phone(phone),
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
