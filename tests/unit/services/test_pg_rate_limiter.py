from src.services.crm_service import CRMService


class FakeLimiter:
    def __init__(self):
        self.calls = []

    def reset(self):
        self.calls.append(("reset",))

    def acquire(self, key: str, *, rate: float, burst: float, cost: float = 1.0):
        self.calls.append(("acquire", key, rate, burst, cost))


class FakePG:
    def __init__(self):
        self.called = 0

    def get_member_by_phone(self, phone: str):
        self.called += 1
        return {"value": [{"Id": 123, "phoneNumber": phone}]}


def test_crm_service_calls_rate_limiter_per_tenant():
    limiter = FakeLimiter()
    crm = CRMService(client=FakePG(), limiter=limiter)

    resp = crm.get_member_by_phone("tenantA", "+48123123123")
    assert resp["value"][0]["Id"] == 123

    # acquire powinno zostać wywołane przed call do PG
    acquires = [c for c in limiter.calls if c[0] == "acquire"]
    assert len(acquires) == 1
    assert acquires[0][1].startswith("pg:tenant:tenantA")
