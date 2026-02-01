import src.repos.members_index_repo as mir


class FakeTable:
    def __init__(self, items=None):
        self.items = items or []
        self.queries = []

    def query(self, **kwargs):
        self.queries.append(kwargs)
        return {"Items": list(self.items)}


class FakeDdb:
    def __init__(self, table):
        self._t = table

    def Table(self, name):
        return self._t


def test_find_by_phone_returns_first_or_none(monkeypatch):
    t = FakeTable(items=[{"pk": "x"}, {"pk": "y"}])
    monkeypatch.setattr(mir, "ddb_resource", lambda: FakeDdb(t))
    monkeypatch.setattr(mir, "phone_hmac", lambda tenant, phone: "H")

    repo = mir.MembersIndexRepo()
    assert repo.find_by_phone("t1", "+48111")["pk"] == "x"

    t.items = []
    assert repo.find_by_phone("t1", "+48111") is None


def test_get_member_normalizes_phone(monkeypatch):
    t = FakeTable(items=[{"member_id": "m1"}])
    monkeypatch.setattr(mir, "ddb_resource", lambda: FakeDdb(t))
    monkeypatch.setattr(mir, "normalize_phone", lambda p: "+481234")
    monkeypatch.setattr(mir, "phone_hmac", lambda tenant, phone: f"H:{phone}")

    repo = mir.MembersIndexRepo()
    got = repo.get_member("t1", " 123 ")
    assert got["member_id"] == "m1"
    # Ensure the query happened (we don't depend on boto3 condition repr).
    assert t.queries[-1]["IndexName"] == "tenant_phone_hmac_idx"


def test_find_by_phone_hmac(monkeypatch):
    t = FakeTable(items=[{"member_id": "m2"}])
    monkeypatch.setattr(mir, "ddb_resource", lambda: FakeDdb(t))

    repo = mir.MembersIndexRepo()
    got = repo.find_by_phone_hmac("t1", "HMAC")
    assert got["member_id"] == "m2"