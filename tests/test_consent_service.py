from typing import Optional, Dict

from src.services.consent_service import ConsentService


class DummyConsentsRepo:
    """
    Prościutkie repo zgód w pamięci, żeby nie dotykać DynamoDB w unit testach.
    Klucz: (tenant_id, phone)
    Wartość: dict z polem "opt_in": True/False
    """

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], Dict] = {}

    def set_opt_in(self, tenant_id: str, phone: str) -> None:
        self._store[(tenant_id, phone)] = {
            "tenant_id": tenant_id,
            "phone": phone,
            "opt_in": True,
        }

    def set_opt_out(self, tenant_id: str, phone: str) -> None:
        self._store[(tenant_id, phone)] = {
            "tenant_id": tenant_id,
            "phone": phone,
            "opt_in": False,
        }

    def get(self, tenant_id: str, phone: str) -> Optional[Dict]:
        return self._store.get((tenant_id, phone))


def test_has_opt_in_false_when_no_record():
    repo = DummyConsentsRepo()
    svc = ConsentService(repo=repo)

    # nic nie zapisujemy w repo → brak rekordu
    assert svc.has_opt_in("default", "whatsapp:+48123123123") is False


def test_has_opt_in_true_when_opt_in_record():
    repo = DummyConsentsRepo()
    svc = ConsentService(repo=repo)

    repo.set_opt_in("default", "whatsapp:+48123123123")

    assert svc.has_opt_in("default", "whatsapp:+48123123123") is True


def test_has_opt_in_false_when_opt_out_record():
    repo = DummyConsentsRepo()
    svc = ConsentService(repo=repo)

    repo.set_opt_out("default", "whatsapp:+48123123123")

    assert svc.has_opt_in("default", "whatsapp:+48123123123") is False


def test_has_opt_in_true_when_no_repo_provided_keeps_old_behaviour():
    """
    Ten test zabezpiecza kompatybilność wsteczną:
    ConsentService() bez repo ma zachowywać się jak dotąd (zawsze True),
    bo tak obecnie używa go campaign_runner.
    """
    svc = ConsentService(repo=None)

    assert svc.has_opt_in("t-1", "whatsapp:+48123123123") is True
    assert svc.has_opt_in("any", "any") is True
