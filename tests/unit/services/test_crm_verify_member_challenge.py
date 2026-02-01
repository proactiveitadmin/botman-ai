
from src.services.crm_service import CRMService
       
class DummyPGClient:
    def __init__(self, member_payload: dict):
        self.member_payload = member_payload
        self.calls: list[str] = []
        self.challenge_calls: list[tuple[str, str, str, str]] = []

    def get_member_by_phone(self, phone: str) -> dict:
        self.calls.append(phone)
        return {"value": self.member_payload}

    def verify_member_challenge(
        self,
        tenant_id: str,
        phone: str,
        challenge_type: str,
        answer: str,
    ) -> bool:
        """
        Używane przez RoutingService._verify_challenge_answer.

        W testach chcemy, żeby challenge DOB przeszedł, jeśli użytkownik poda
        konkretną datę, np. 01-05-1990 (z różnymi separatorami).
        """
        self.challenge_calls.append((tenant_id, phone, challenge_type, answer))

        if challenge_type not in ("dob", "email"):
            return False

        norm = (answer or "").strip().replace(".", "-").replace("/", "-").lower()

        # DOB – akceptujemy dokładnie 01-05-1990 po normalizacji
        if challenge_type == "dob":
            return norm == "01-05-1990"

        # EMAIL – akceptujemy user@example.com w dowolnym case
        if challenge_type == "email":
            return "user@example.com" in norm

        return False



class DummyMembersIndex:
    def __init__(self, member_id: str = "123"):
        self.member_id = member_id
        self.calls = []

    def get_member(self, tenant_id: str, phone: str):
        self.calls.append((tenant_id, phone))
        return {"id": self.member_id}


def test_verify_member_challenge_email_ok():
    """
    verify_member_challenge('email') zwraca True, gdy email z PerfectGym
    zgadza się z odpowiedzią użytkownika.
    """
    pg_members = [
        {"email": "USER@example.com"}
    ]
    client = DummyPGClient(pg_members)

    svc = CRMService(client=client)

    result = svc.verify_member_challenge(
        tenant_id="tenantA",
        phone="whatsapp:+48123123123",
        challenge_type="email",
        answer="user@example.com",
    )

    assert result is True

    # upewniamy się, że faktycznie zawołaliśmy PG po numerze telefonu
    # (CRMService powinien odciąć prefix 'whatsapp:')
    assert client.calls == ["+48123123123"]


def test_verify_member_challenge_dob_ok():
    """
    verify_member_challenge('dob') zwraca True, gdy dzień i miesiąc
    z odpowiedzi użytkownika zgadzają się z datą urodzenia w PerfectGym.
    """
    pg_members = [
        {"birthDate": "1990-05-01T00:00:00"}  # CRMService używa birthDate/birthdate
    ]
    client = DummyPGClient(pg_members)
    svc = CRMService(client=client)

    # format z pełną datą
    assert svc.verify_member_challenge(
        tenant_id="tenantA",
        phone="whatsapp:+48123123123",
        challenge_type="dob",
        answer="01-05-1990",
    ) is True

    # krótszy format z kropką
    assert svc.verify_member_challenge(
        tenant_id="tenantA",
        phone="whatsapp:+48123123123",
        challenge_type="dob",
        answer="1.5",
    ) is True


def test_verify_member_challenge_invalid_answer_returns_false():
    """
    Dla złej odpowiedzi verify_member_challenge zwraca False.
    """
    pg_members = [
        {"birthDate": "1990-05-01T00:00:00"}
    ]
    client = DummyPGClient(pg_members)
    svc = CRMService(client=client)

    assert svc.verify_member_challenge(
        tenant_id="tenantA",
        phone="whatsapp:+48123123123",
        challenge_type="dob",
        answer="31-12",
    ) is False
