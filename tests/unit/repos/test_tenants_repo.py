import src.repos.tenants_repo as tr


class FakeTable:
    def __init__(self):
        self.item = {}
        self.updated = []

    def get_item(self, Key):
        # emulate ddb response
        return {"Item": self.item} if self.item else {}

    def update_item(self, **kwargs):
        self.updated.append(kwargs)
        return {}


class FakeDdb:
    def __init__(self, table):
        self._t = table

    def Table(self, _name):
        return self._t


def test_get_email_config_none_when_missing(monkeypatch):
    t = FakeTable()
    monkeypatch.setattr(tr, "ddb_resource", lambda: FakeDdb(t))

    repo = tr.TenantsRepo()
    assert repo.get_email_config("t1") is None

    t.item = {"tenant_id": "t1", "email": {"enabled": False}}
    assert repo.get_email_config("t1") is None

    t.item = {"tenant_id": "t1", "email": {"enabled": True, "from_email": "x@y"}}
    assert repo.get_email_config("t1")["from_email"] == "x@y"


def test_set_email_config_merges(monkeypatch):
    t = FakeTable()
    t.item = {"tenant_id": "t1", "email": {"from_email": "old@x", "enabled": True}}
    monkeypatch.setattr(tr, "ddb_resource", lambda: FakeDdb(t))

    repo = tr.TenantsRepo()
    repo.set_email_config("t1", from_email="new@x", from_name="Name", enabled=False)

    assert t.updated
    upd = t.updated[-1]
    assert upd["ExpressionAttributeValues"][":email"]["from_email"] == "new@x"
    assert upd["ExpressionAttributeValues"][":email"]["from_name"] == "Name"
    assert upd["ExpressionAttributeValues"][":email"]["enabled"] is False


def test_find_by_twilio_to_returns_none_on_empty(monkeypatch):
    t = FakeTable()
    monkeypatch.setattr(tr, "ddb_resource", lambda: FakeDdb(t))
    repo = tr.TenantsRepo()
    assert repo.find_by_twilio_to("") is None
