# src/lambdas/pg_reservations/handler.py
import json
from ...services.clients_factory import ClientsFactory
from ...repos.tenants_repo import TenantsRepo
from ...common.logging import logger

clients = ClientsFactory()
tenants_repo = TenantsRepo()


def _get_header(headers: dict, name: str) -> str | None:
    if not headers:
        return None
    # case-insensitive lookup
    for k, v in headers.items():
        if k.lower() == name.lower():
            return v
    return None


def _resolve_tenant_id(event: dict, body: dict) -> str | None:
    headers = event.get("headers") or {}

    # 1) explicit tenant header (recommended for internal calls)
    tenant_id = _get_header(headers, "X-Tenant-Id") or _get_header(headers, "X-Tenant")
    if tenant_id:
        return str(tenant_id).strip() or None

    # 2) API key -> tenant (for integrations that cannot call per-tenant URL)
    api_key = _get_header(headers, "X-Api-Key") or _get_header(headers, "X-PG-Api-Key")
    if api_key:
        item = tenants_repo.find_by_pg_api_key(str(api_key).strip())
        return (item or {}).get("tenant_id")

    # 3) optional fallback: tenant_id in request body (manual tests / tools)
    tenant_id = body.get("tenant_id") or body.get("tenant")
    if tenant_id:
        return str(tenant_id).strip() or None

    return None


def lambda_handler(event, context):
    body = json.loads(event.get("body") or "{}")

    tenant_id = _resolve_tenant_id(event, body)
    if not tenant_id:
        logger.error({"pg": "tenant_missing"})
        return {"statusCode": 400, "body": "Missing tenant (use X-Tenant-Id or X-Api-Key)"}

    member_id = body.get("member_id")
    class_id = body.get("class_id")
    idem = body.get("idempotency_key")

    if not (member_id and class_id and idem):
        return {"statusCode": 400, "body": "Missing required fields"}

    res = clients.perfectgym(tenant_id).reserve_class(member_id=member_id, class_id=class_id, idempotency_key=idem)
    return {"statusCode": 200, "body": json.dumps(res)}
