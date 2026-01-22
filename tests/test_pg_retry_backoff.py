import pytest
from src.adapters.perfectgym_client import PerfectGymClient
from src.common.config import settings
import src.adapters.perfectgym_client as pg_mod


class DummyResp:
    def __init__(self, status_code=200, payload=None, text="OK", headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise pg_mod.requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_pg_retries_on_429_then_succeeds(monkeypatch):
    
    client = PerfectGymClient()
    monkeypatch.setattr(client, "base_url", "https://pg.example/api/v2.2/odata", raising=False)
    monkeypatch.setattr(client, "client_id", "id", raising=False)
    monkeypatch.setattr(client, "client_secret", "secret", raising=False)

    monkeypatch.setattr(settings, "pg_retry_max_attempts", 3, raising=False)
    monkeypatch.setattr(settings, "pg_retry_base_delay_s", 0.01, raising=False)
    monkeypatch.setattr(settings, "pg_retry_max_delay_s", 0.05, raising=False)

    calls = {"n": 0}
    sleeps = []

    def fake_sleep(t):
        sleeps.append(t)

    def fake_uniform(a, b):
        return 1.0

    def fake_request(method, url, **kwargs):
        assert method == "GET"
        calls["n"] += 1
        if calls["n"] == 1:
            # 429, bez Retry-After
            return DummyResp(status_code=429, payload={"error": "rate"})
        return DummyResp(status_code=200, payload={"Id": 1})

    monkeypatch.setattr(pg_mod.time, "sleep", fake_sleep)
    monkeypatch.setattr(pg_mod.random, "uniform", fake_uniform)
    monkeypatch.setattr(pg_mod.requests, "request", fake_request)

    resp = client.get_member("1")
    assert resp["Id"] == 1
    assert calls["n"] == 2
    assert len(sleeps) == 1
