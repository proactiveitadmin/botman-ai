import pytest

from tests.helpers.env import require_env
from tests.helpers.http_client import HttpClient


@pytest.mark.prod_safe
@pytest.mark.e2e
def test_prod_health_endpoint_returns_200_and_json():
    """Safe to run on production: read-only GET /health."""

    env = require_env("API_BASE_URL")
    client = HttpClient(env["API_BASE_URL"], timeout_s=10)

    res = client.get("/health")
    assert res.status_code == 200

    # Keep it tolerant: deployments may add more fields.
    data = res.json()
    assert isinstance(data, dict)
