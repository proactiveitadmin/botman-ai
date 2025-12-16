from src.repos.members_index_repo import MembersIndexRepo


class DummyTable:
    def __init__(self, items):
        self._items = items
        self.last_query_kwargs = None

    def query(self, **kwargs):
        self.last_query_kwargs = kwargs
        return {"Items": self._items}


def test_find_by_phone_returns_first_item(monkeypatch):
    repo = MembersIndexRepo()
    dummy = DummyTable(
        [
            {"tenant_id": "t1", "phone": "+48123", "name": "Alice"},
            {"tenant_id": "t1", "phone": "+48123", "name": "Bob"},
        ]
    )

    monkeypatch.setattr(repo, "table", dummy)

    item = repo.find_by_phone("t1", "+48123")
    assert item["name"] == "Alice"
    assert dummy.last_query_kwargs["IndexName"] == "tenant_phone_hmac_idx"


def test_find_by_phone_empty_items_returns_none(monkeypatch):
    repo = MembersIndexRepo()
    dummy = DummyTable([])
    monkeypatch.setattr(repo, "table", dummy)

    item = repo.find_by_phone("t1", "+000")
    assert item is None


def test_get_member_strips_whatsapp_prefix(monkeypatch):
    repo = MembersIndexRepo()
    dummy = DummyTable([{"tenant_id": "t1", "phone": "+48123"}])
    monkeypatch.setattr(repo, "table", dummy)

    item = repo.get_member("t1", "whatsapp:+48123")
    assert item["phone"] == "+48123"
