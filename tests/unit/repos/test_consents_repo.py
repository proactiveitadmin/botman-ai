import src.repos.consents_repo as cr


class FakeTable:
    def __init__(self):
        self.put = []
        self.deleted = []
        self.gets = []

    def put_item(self, Item):
        self.put.append(Item)

    def get_item(self, Key):
        self.gets.append(Key)
        return {"Item": {"pk": Key["pk"], "opt_in": True}}

    def delete_item(self, Key):
        self.deleted.append(Key)


class FakeDdb:
    def __init__(self, table):
        self._t = table

    def Table(self, _name):
        return self._t


def test_consents_pk_uses_hmac(monkeypatch):
    t = FakeTable()
    monkeypatch.setattr(cr, "ddb_resource", lambda: FakeDdb(t))
    monkeypatch.setattr(cr, "phone_hmac", lambda tenant, phone: "HMAC")
    monkeypatch.setattr(cr, "phone_last4", lambda phone: "1234")

    repo = cr.ConsentsRepo()

    item = repo.set_opt_in("t1", "+48111111111", source="x")
    assert item["pk"] == "t1#HMAC"
    assert item["opt_in"] is True
    assert item["phone_last4"] == "1234"
    assert item["source"] == "x"

    got = repo.get("t1", "+48111111111")
    assert got["pk"] == "t1#HMAC"

    repo.delete("t1", "+48111111111")
    assert t.deleted[-1]["pk"] == "t1#HMAC"
