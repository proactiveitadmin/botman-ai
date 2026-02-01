# Test suites

## Layers

- `tests/unit` – pure Python, no AWS, no HTTP
- `tests/component` – single component w/ stubs (e.g., HTTP mocked)
- `tests/integration` – AWS resources (moto/localstack)
- `tests/e2e` – full flows
- `tests/security` – security-as-code tests
- `tests/perf` – performance tests (load/generation scripts)

## Markers

Markers are applied automatically based on folder name (see `tests/conftest.py`).

Important:
- `prod_safe` – tests safe to run against production (read-only, non-colliding).

## Production canary

To run prod canaries locally:

```bash
export API_BASE_URL="https://.../Prod"
pytest -m "prod_safe" -q
```

In GitHub Actions, set secret `PROD_API_BASE_URL`.
