# src/services/consent_service.py
from typing import Optional, Dict

from ..storage.consents_repo import ConsentsRepo  # ścieżka względna

class ConsentService:
    def __init__(self, repo: ConsentsRepo | None = None) -> None:
        self.repo = repo

    def has_opt_in(self, tenant_id: str, phone: str) -> bool:
        """
        Zwraca True, jeżeli użytkownik ma zapisaną zgodę marketingową (opt_in=True).

        Przyjęte założenia (MVP):
          - brak rekordu w Consents => brak zgody (False),
          - opt_in == True => ma zgodę,
          - opt_in == False => brak zgody.
        """
        if not tenant_id or not phone:
            return False
        
        # Backward compatibility: brak repo => nie dotykamy DDB, zawsze True
        if self.repo is None:
            return True

        item: Optional[Dict] = self.repo.get(tenant_id, phone)
        if not item:
            return False

        return bool(item.get("opt_in") is True)
