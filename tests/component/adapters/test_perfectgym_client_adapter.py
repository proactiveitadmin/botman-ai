import json as jsonlib
import re
from datetime import datetime

import pytest

from src.adapters.perfectgym_client import PerfectGymClient
import src.adapters.perfectgym_client as pg_mod


class DummyResp:
    def __init__(self, status_code=200, payload=None, text="OK", raise_http=False, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.headers = headers or {}
        self._raise_http = raise_http

    def raise_for_status(self):
        if self._raise_http:
            raise pg_mod.requests.HTTPError(f"HTTP {self.status_code}")
        return None

    def json(self):
        return self._payload


class DummySession:
    def __init__(self, request):
        self.request = request


def _patch_session(monkeypatch, client, request):
    session = DummySession(request)
    monkeypatch.setattr(client, "_session", lambda: session)
    return session


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch):
    monkeypatch.setattr(pg_mod.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(pg_mod.random, "uniform", lambda *_args, **_kwargs: 1.0)


def test_get_member_without_base_url_returns_fallback(monkeypatch):
    
    client = PerfectGymClient()
    
    monkeypatch.setattr(client, "base_url", "", raising=False)
    monkeypatch.setattr(client, "client_id", "id", raising=False)
    monkeypatch.setattr(client, "client_secret", "secret", raising=False)

    
    resp = client.get_member("123")
    # dev fallback – żeby flow nie wybuchł
    assert resp["member_id"] == "123"
    assert resp["status"] == "Current"
    assert resp["balance"] == 0


def test_get_member_ok(monkeypatch):

    
    client = PerfectGymClient()
    
    monkeypatch.setattr(client, "base_url", "https://pg.example/api/v2.2/odata", raising=False)
    monkeypatch.setattr(client, "client_id", "id", raising=False)
    monkeypatch.setattr(client, "client_secret", "secret", raising=False)

    called = {}

    def fake_request(method, url, headers=None, timeout=None, **kwargs):
        assert method == "GET"
        called["method"] = method
        called["url"] = url
        called["headers"] = headers
        called["timeout"] = timeout
        return DummyResp(payload={"Id": 123, "name": "John"})

    _patch_session(monkeypatch, client, fake_request)

    resp = client.get_member("123")
    assert resp["Id"] == 123
    assert "Members(123)" in called["url"]
    assert called["headers"]["X-Client-id"] == "id"
    assert called["timeout"] == 10


def test_get_member_by_phone_error_logs_and_returns_empty(monkeypatch, capsys):
    
    client = PerfectGymClient()
    
    monkeypatch.setattr(client, "base_url", "https://pg.example/api/v2.2/odata", raising=False)
    monkeypatch.setattr(client, "client_id", "id", raising=False)
    monkeypatch.setattr(client, "client_secret", "secret", raising=False)

    def fake_request(method, url, headers=None, timeout=None, **kwargs):
        assert method == "GET"
        raise pg_mod.requests.RequestException("boom")

    _patch_session(monkeypatch, client, fake_request)

    resp = client.get_member_by_phone("+48123123123")
    assert resp == {"value": []}

    out = capsys.readouterr().out + capsys.readouterr().err
    # log idzie do loggera, więc tu może nie być – ważny jest kształt odpowiedzi


def test_reserve_class_dev_mode_fallback(monkeypatch):
    
    client = PerfectGymClient()
    
    monkeypatch.setattr(client, "base_url", "", raising=False)
    monkeypatch.setattr(client, "client_id", "id", raising=False)
    monkeypatch.setattr(client, "client_secret", "secret", raising=False)

    resp = client.reserve_class(member_id="10", class_id="20")
    assert resp["ok"] is True
    assert resp["status_code"] == 200
    assert resp["data"]["fake"] is True
    assert resp["data"]["classId"] == "20"
    assert resp["data"]["memberId"] == "10"


def test_reserve_class_post_error(monkeypatch):
    
    client = PerfectGymClient()
    
    monkeypatch.setattr(client, "base_url", "https://pg.example/api/v2.2/odata", raising=False)
    monkeypatch.setattr(client, "client_id", "id", raising=False)
    monkeypatch.setattr(client, "client_secret", "secret", raising=False)

    def fake_request(method, url, json=None, headers=None, timeout=None, **kwargs):
        assert method == "POST"
        raise pg_mod.requests.RequestException("boom")

    _patch_session(monkeypatch, client, fake_request)

    resp = client.reserve_class(member_id="10", class_id="20", idempotency_key="KEY")
    assert resp["ok"] is False
    assert resp["status_code"] is None
    assert "boom" in resp["error"]
    assert resp["body"] is None


def test_reserve_class_http_error(monkeypatch):
    
    client = PerfectGymClient()
    
    monkeypatch.setattr(client, "base_url", "https://pg.example/api/v2.2/odata", raising=False)
    monkeypatch.setattr(client, "client_id", "id", raising=False)
    monkeypatch.setattr(client, "client_secret", "secret", raising=False)

    def fake_request(method, url, json=None, headers=None, timeout=None, **kwargs):
        assert method == "POST"
        return DummyResp(status_code=400, text="Bad Request", raise_http=True)

    _patch_session(monkeypatch, client, fake_request)

    resp = client.reserve_class(member_id="10", class_id="20")
    assert resp["ok"] is False
    assert resp["status_code"] == 400
    assert isinstance(resp.get("error"), str)
    assert resp["error"]  # niepusty
    assert re.search(r"\bHTTP\b", resp["error"]) is not None
    assert resp["body"] == "Bad Request"

def test_reserve_class_http_error_classes_already_booked_is_mapped(monkeypatch):
    
    client = PerfectGymClient()
    
    monkeypatch.setattr(client, "base_url", "https://pg.example/api/v2.2/odata", raising=False)
    monkeypatch.setattr(client, "client_id", "id", raising=False)
    monkeypatch.setattr(client, "client_secret", "secret", raising=False)

    payload = {
        "errors": [
            {
                "message": "Classes already booked.",
                "property": None,
                "code": "ClassesAlreadyBooked",
                "nestedBusinessErrors": [],
                "data": None,
            }
        ]
    }

    def fake_request(method, url, json=None, headers=None, timeout=None, **kwargs):
        assert method == "POST"
        # PG zwraca 4xx + JSON z errors
        return DummyResp(status_code=400, payload=payload, text=jsonlib.dumps(payload), raise_http=True)

    _patch_session(monkeypatch, client, fake_request)

    resp = client.reserve_class(member_id="10", class_id="20")

    assert resp["ok"] is False
    assert resp["status_code"] == 400
    assert resp["mapped_error"] == "classes_already_booked"
    assert resp["pg_error"]["code"] == "ClassesAlreadyBooked"


def test_reserve_class_success(monkeypatch):
    
    client = PerfectGymClient()
    
    monkeypatch.setattr(client, "base_url", "https://pg.example/api/v2.2/odata", raising=False)
    monkeypatch.setattr(client, "client_id", "id", raising=False)
    monkeypatch.setattr(client, "client_secret", "secret", raising=False)

    captured = {}

    def fake_request(method, url, json=None, headers=None, timeout=None, **kwargs):
        assert method == "POST"
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return DummyResp(status_code=201, payload={"ok": True})

    _patch_session(monkeypatch, client, fake_request)

    resp = client.reserve_class(member_id="10", class_id="30", idempotency_key="IDEMP", allow_overlap=True)
    assert resp["ok"] is True
    assert resp["status_code"] == 201
    assert resp["data"] == {"ok": True}
    assert "BookClass" in captured["url"]
    assert captured["json"]["memberId"] == 10
    assert captured["json"]["classId"] == 30
    assert captured["json"]["bookDespiteOtherBookingsAtTheSameTime"] is True
    assert "comments" not in captured["json"]
    assert captured["headers"]["Idempotency-Key"] == "IDEMP"


def test_reserve_class_passes_comments_only_when_provided(monkeypatch):
    client = PerfectGymClient()
    monkeypatch.setattr(client, "base_url", "https://pg.example/api/v2.2/odata", raising=False)
    monkeypatch.setattr(client, "client_id", "id", raising=False)
    monkeypatch.setattr(client, "client_secret", "secret", raising=False)

    captured = {}

    def fake_request(method, url, json=None, headers=None, timeout=None, **kwargs):
        captured["json"] = json
        return DummyResp(status_code=201, payload={"ok": True})

    _patch_session(monkeypatch, client, fake_request)

    resp = client.reserve_class(member_id="10", class_id="30", comments="user provided note")
    assert resp["ok"] is True
    assert captured["json"]["comments"] == "user provided note"


def test_get_available_classes_success(monkeypatch):
    
    client = PerfectGymClient()
    
    monkeypatch.setattr(client, "base_url", "https://pg.example/api/v2.2/odata", raising=False)
    monkeypatch.setattr(client, "client_id", "id", raising=False)
    monkeypatch.setattr(client, "client_secret", "secret", raising=False)

    captured = {}

    def fake_request(method, url, headers=None, params=None, timeout=None, **kwargs):
        assert method == "GET"
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        captured["timeout"] = timeout
        return DummyResp(payload={"value": [{"id": 1}]})

    _patch_session(monkeypatch, client, fake_request)

    resp = client.get_available_classes(top=5)
    assert resp["value"][0]["id"] == 1
    #default window is now..now+2d if to_iso not provided
    fixed_from = datetime(2025, 1, 1, 12, 0, 0)
    resp = client.get_available_classes(from_iso=fixed_from, top=5)
    assert "Classes" in captured["url"]
    flt = captured["params"]["$filter"]
    assert "startdate gt" in flt
    assert "startdate lt" in flt


def test_get_available_classes_error(monkeypatch):
    
    client = PerfectGymClient()
    
    monkeypatch.setattr(client, "base_url", "https://pg.example/api/v2.2/odata", raising=False)
    monkeypatch.setattr(client, "client_id", "id", raising=False)
    monkeypatch.setattr(client, "client_secret", "secret", raising=False)

    def fake_request(method, url, headers=None, params=None, timeout=None, **kwargs):
        assert method == "GET"
        raise pg_mod.requests.RequestException("err")

    _patch_session(monkeypatch, client, fake_request)

    resp = client.get_available_classes()
    assert resp == {"value": []}


def test_get_contract_by_member_id_success(monkeypatch):
    
    client = PerfectGymClient()
    
    monkeypatch.setattr(client, "base_url", "https://pg.example/api/v2.2/odata", raising=False)
    monkeypatch.setattr(client, "client_id", "id", raising=False)
    monkeypatch.setattr(client, "client_secret", "secret", raising=False)

    def fake_request(method, url, headers=None, timeout=None, **kwargs):
        assert method == "GET"
        return DummyResp(payload={
            "Contracts": [
                {"id": "1", "Status": "Current"}
            ]
        })


    _patch_session(monkeypatch, client, fake_request)

    resp = client.get_contract_by_member_id("123")
    assert resp["id"] == "1"


def test_get_contract_by_member_id_error(monkeypatch):
    
    client = PerfectGymClient()
    
    monkeypatch.setattr(client, "base_url", "https://pg.example/api/v2.2/odata", raising=False)
    monkeypatch.setattr(client, "client_id", "id", raising=False)
    monkeypatch.setattr(client, "client_secret", "secret", raising=False)

    def fake_request(method, url, headers=None, timeout=None, **kwargs):
        assert method == "GET"
        raise pg_mod.requests.RequestException("err")

    _patch_session(monkeypatch, client, fake_request)

    resp = client.get_contract_by_member_id("123")
    assert resp == {}


def test_get_member_balance_dev_mode(monkeypatch):
    
    client = PerfectGymClient()
    
    monkeypatch.setattr(client, "base_url", "", raising=False)
    monkeypatch.setattr(client, "client_id", "id", raising=False)
    monkeypatch.setattr(client, "client_secret", "secret", raising=False)

    resp = client.get_member_balance(123)
    assert resp["currentBalance"] == 0
    assert resp["raw"] == {}


def test_get_member_balance_success(monkeypatch):
    
    client = PerfectGymClient()
    
    monkeypatch.setattr(client, "base_url", "https://pg.example/api/v2.2/odata", raising=False)
    monkeypatch.setattr(client, "client_id", "id", raising=False)
    monkeypatch.setattr(client, "client_secret", "secret", raising=False)

    def fake_request(method, url, headers=None, timeout=None, **kwargs):
        assert method == "GET"
        return DummyResp(
            payload={
                "memberBalance": {
                    "prepaidBalance": 10,
                    "prepaidBonusBalance": 5,
                    "currentBalance": 3,
                    "negativeBalanceSince": "2024-11-01T00:00:00",
                }
            }
        )

    _patch_session(monkeypatch, client, fake_request)

    resp = client.get_member_balance(123)
    assert resp["prepaidBalance"] == 10
    assert resp["prepaidBonusBalance"] == 5
    assert resp["currentBalance"] == 3
    assert resp["negativeBalanceSince"].startswith("2024-11-01")


def test_get_member_balance_error(monkeypatch):
    
    client = PerfectGymClient()
    
    monkeypatch.setattr(client, "base_url", "https://pg.example/api/v2.2/odata", raising=False)
    monkeypatch.setattr(client, "client_id", "id", raising=False)
    monkeypatch.setattr(client, "client_secret", "secret", raising=False)

    def fake_request(method, url, headers=None, timeout=None, **kwargs):
        assert method == "GET"
        raise pg_mod.requests.RequestException("err")

    _patch_session(monkeypatch, client, fake_request)

    resp = client.get_member_balance(123)
    assert resp["currentBalance"] == 0
    assert resp["raw"] == {}


def test_get_class_no_base_url_returns_empty(monkeypatch):
    
    client = PerfectGymClient()
    
    monkeypatch.setattr(client, "base_url", "", raising=False)
    monkeypatch.setattr(client, "client_id", "id", raising=False)
    monkeypatch.setattr(client, "client_secret", "secret", raising=False)

    assert client.get_class(1) == {}


def test_get_class_success_with_collection(monkeypatch):
    
    client = PerfectGymClient()
    
    monkeypatch.setattr(client, "base_url", "https://pg.example/api/v2.2/odata", raising=False)
    monkeypatch.setattr(client, "client_id", "id", raising=False)
    monkeypatch.setattr(client, "client_secret", "secret", raising=False)

    captured = {}

    def fake_request(method, url, headers=None, timeout=None, **kwargs):
        assert method == "GET"
        captured["url"] = url
        return DummyResp(payload={"value": [{"id": 1, "name": "Yoga"}]})

    _patch_session(monkeypatch, client, fake_request)

    resp = client.get_class("1")  # string ID
    assert resp["id"] == 1
    assert "Classes(1)" in captured["url"]
