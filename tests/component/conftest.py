import pytest

@pytest.fixture(autouse=True)
def stub_tenant_config_service_get(monkeypatch):
    """
    Component tests should not depend on DDB/SSM tenant config.
    Patch TenantConfigService.get so handlers always receive a valid tenant config.
    """
    from src.services import tenant_config_service as tcs

    def _fake_get(self, tenant_id: str):
        # Minimal config needed by handlers/flows
        return {
            "tenant_id": tenant_id,
            # jeśli gdzieś wymagacie flags/feature toggles:
            "features": {
                "kb_vector_mode": True,
            },
            # jeśli gdzieś wymagacie branding/templates:
            "branding": {"name": "TestTenant"},
        }

    monkeypatch.setattr(tcs.TenantConfigService, "get", _fake_get, raising=True)

@pytest.fixture(autouse=True)
def stub_tenant_config(monkeypatch):
    import src.services.tenant_config_service as tcs

    class Dummy:
        def get(self, tenant_id: str) -> dict:
            return {
                "tenant_id": tenant_id,
                "language_code": "pl",
                "twilio": {},
                "whatsapp_cloud": {},
                "pg": {},
                "jira": {},
                "pinecone": {},
            }

    dummy = Dummy()
    monkeypatch.setattr(tcs, "default_tenant_config_service", lambda: dummy, raising=True)
    yield


@pytest.fixture()
def requests_mock(monkeypatch):
    """Lightweight requests mock for component tests.

    Provides an API compatible with tests that do: requests_mock.get(url, json=..., status_code=...).
    It also monkeypatches requests.request() so production code using `requests` is intercepted.
    """
    import requests

    class _Response:
        def __init__(self, payload, status_code=200, headers=None):
            self._payload = payload
            self.status_code = status_code
            self.headers = headers or {}
            self.text = "" if payload is None else str(payload)

        def json(self):
            return self._payload

        def raise_for_status(self):
            if 400 <= self.status_code < 600:
                raise requests.HTTPError(f"HTTP {self.status_code}")

    class _RequestsMock:
        def __init__(self):
            self._mappings = {}  # (method, url) -> (payload, status_code, headers)

        def get(self, url, json=None, status_code=200, headers=None, **kwargs):
            self._mappings[("GET", url)] = (json, status_code, headers or {})

        def request(self, method, url, **kwargs):
            m = (method or "").upper()
            key = (m, url)
            if key not in self._mappings:
                raise AssertionError(f"Unexpected {m} {url!r} in requests_mock")
            payload, status, headers = self._mappings[key]
            return _Response(payload, status_code=status, headers=headers)

    mock = _RequestsMock()
    monkeypatch.setattr(requests, "request", mock.request, raising=True)
    return mock
