import json
import base64

import pytest

from src.adapters.jira_client import JiraClient


class DummyResponseOK:
    def __init__(self, payload=None, status_code=200, ok=True):
        self._payload = payload or {"key": "JIRA-123"}
        self.status_code = status_code
        self.ok = ok
        self.text = json.dumps(self._payload)

    def raise_for_status(self):
        # symulujemy brak wyjątku
        return None

    def json(self):
        return self._payload


class DummyResponseError(DummyResponseOK):
    def __init__(self):
        super().__init__(payload={"key": "JIRA-ERR"}, status_code=500, ok=False)


def test_auth_header_with_basic_token(monkeypatch):
    client = JiraClient()
    monkeypatch.setattr(client, "token", "user:pass", raising=False)
    
    hdr = client._auth_header()
    assert "Authorization" in hdr
    # sprawdźmy, że to faktycznie Basic + base64
    assert hdr["Authorization"].startswith("Basic ")
    encoded = hdr["Authorization"].split(" ", 1)[1]
    decoded = base64.b64decode(encoded.encode()).decode()
    assert decoded == "user:pass"


def test_auth_header_without_colon_returns_empty(monkeypatch):
    client = JiraClient()
    monkeypatch.setattr(client, "token", "no_colon_here", raising=False)
    assert client._auth_header() == {}


def test_build_description_adf_handles_none_description(monkeypatch):
    client = JiraClient()
    monkeypatch.setattr(client, "token", "t:t", raising=False)

    adf = client._build_description_adf(None)
    assert adf["type"] == "doc"
    assert adf["version"] == 1
    # przy None powinna być jedna pusta linia
    assert len(adf["content"]) == 1
    assert adf["content"][0]["content"][0]["text"] == ""


def test_build_description_adf_multiple_lines(monkeypatch):
    client = JiraClient()
    adf = client._build_description_adf("line1\nline2\nline3")
    lines = [p["content"][0]["text"] for p in adf["content"]]
    assert lines == ["line1", "line2", "line3"]


def test_create_ticket_dev_mode(monkeypatch):
    """
    Brak url -> ścieżka DEV (bez requestów HTTP).
    """
    client = JiraClient()
    monkeypatch.setattr(client, "url", "", raising=False)
    monkeypatch.setattr(client, "project_key", "GI", raising=False)
    monkeypatch.setattr(client, "issue_type_name", "Task", raising=False)

    # gdyby jednak create_ticket próbował zrobić POST, to chcemy od razu faila
    import src.adapters.jira_client as jira_mod

    def _unexpected_post(*args, **kwargs):
        raise AssertionError("requests.post nie powinien być wołany w trybie dev")

    monkeypatch.setattr(jira_mod, "requests", type("R", (), {"post": _unexpected_post}))

    res = client.create_ticket(
        summary="Test ticket",
        description="Desc",
        tenant_id="t1",
        meta={"foo": "bar"},
    )
    assert res["ok"] is True
    assert res["ticket"] == "JIRA-DEV"


def test_create_ticket_success(monkeypatch):
    """
    Normalny przypadek z prawdziwym URL – symulujemy udane utworzenie ticketa.
    """
    import src.adapters.jira_client as jira_mod
    client = JiraClient()

    monkeypatch.setattr(client, "url", "https://example.atlassian.net", raising=False)
    monkeypatch.setattr(client, "project_key", "GI", raising=False)
    monkeypatch.setattr(client, "issue_type_name", "Task", raising=False)
    monkeypatch.setattr(client, "token", "user:pass", raising=False)

    monkeypatch.setattr(
        jira_mod,
        "requests",
        type("R", (), {"post": staticmethod(lambda *a, **k: DummyResponseOK())}),
    )

    res = client.create_ticket(
        summary="Test",
        description="something",
        tenant_id="tenant-1",
        meta={"priority": "high"},
    )
    assert res["ok"] is True
    assert res["ticket"] == "JIRA-123"


def test_create_ticket_logs_non_ok_but_returns_key(monkeypatch, capsys):
    """
    Ścieżka: r.ok == False -> wypisywane są logi błędu, ale funkcja nie rzuca wyjątku
    (bo raise_for_status w stubie nic nie robi).
    """
    import src.adapters.jira_client as jira_mod
    client = JiraClient()

    monkeypatch.setattr(client, "url", "https://example.atlassian.net", raising=False)
    monkeypatch.setattr(client, "project_key", "GI", raising=False)
    monkeypatch.setattr(client, "issue_type_name", "Task", raising=False)
    monkeypatch.setattr(client, "token", "user:pass", raising=False)

    monkeypatch.setattr(
        jira_mod,
        "requests",
        type("R", (), {"post": staticmethod(lambda *a, **k: DummyResponseError())}),
    )

    res = client.create_ticket(
        summary="Test err",
        description="desc",
        tenant_id="tenant-err",
        meta=None,
    )

    captured = capsys.readouterr()
    combined = (captured.out or "") + (captured.err or "")
    assert "Jira error status" in combined
    assert res["ok"] is True
    assert res["ticket"] == "JIRA-ERR"
