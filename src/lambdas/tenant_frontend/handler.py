from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from ...common.aws import ddb_resource
from ...common.logging import logger
from ...common.security import encrypt_phone, normalize_phone
from ...common.utils import new_id
from ...services.metrics_service import MetricsService

CAMPAIGNS_TABLE = os.getenv("DDB_TABLE_CAMPAIGNS", "Campaigns")
_ALLOWED_METHODS = "GET,POST,OPTIONS"
_ALLOWED_HEADERS = "Content-Type,Authorization,X-Tenant-Id,X-Tenant"
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _headers(status_code: int = 200) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": os.getenv("FRONTEND_CORS_ORIGIN", "*"),
        "Access-Control-Allow-Methods": _ALLOWED_METHODS,
        "Access-Control-Allow-Headers": _ALLOWED_HEADERS,
    }


def _response(status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": _headers(status_code),
        "body": json.dumps(payload, ensure_ascii=False, default=_json_default),
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body") or "{}"
    if isinstance(raw, dict):
        return raw
    return json.loads(raw)


def _method(event: dict[str, Any]) -> str:
    return (event.get("httpMethod") or (event.get("requestContext") or {}).get("http", {}).get("method") or "").upper()


def _path(event: dict[str, Any]) -> str:
    return event.get("path") or event.get("rawPath") or ""


def _query(event: dict[str, Any]) -> dict[str, str]:
    return event.get("queryStringParameters") or {}


def _tenant_id(event: dict[str, Any], body: dict[str, Any] | None = None) -> str | None:
    body = body or {}
    path_params = event.get("pathParameters") or {}
    tenant_id = path_params.get("tenant_id") or path_params.get("tenantId")
    if tenant_id:
        return str(tenant_id).strip() or None
    headers = event.get("headers") or {}
    for k, v in headers.items():
        if k.lower() in {"x-tenant-id", "x-tenant"} and v:
            return str(v).strip() or None
    tenant_id = body.get("tenant_id") or body.get("tenant")
    if tenant_id:
        return str(tenant_id).strip() or None
    return None




def _authorizer_claims(event: dict[str, Any]) -> dict[str, Any]:
    request_context = event.get("requestContext") or {}
    authorizer = request_context.get("authorizer") or {}

    # REST API Cognito User Pools authorizer
    claims = authorizer.get("claims")
    if isinstance(claims, dict):
        return claims

    # HTTP API JWT authorizer shape, useful for local tests or future migration.
    jwt_claims = ((authorizer.get("jwt") or {}).get("claims") or {})
    return jwt_claims if isinstance(jwt_claims, dict) else {}


def _claim_tenant_id(claims: dict[str, Any]) -> str | None:
    for key in ("custom:tenant_id", "tenant_id", "custom:tenantId", "tenantId"):
        value = claims.get(key)
        if value:
            return str(value).strip()

    groups = claims.get("cognito:groups") or ""
    if isinstance(groups, str):
        for group in groups.replace("[", "").replace("]", "").replace('"', "").split(","):
            group = group.strip()
            if group.startswith("tenant:"):
                return group.split(":", 1)[1].strip() or None
    return None


def _require_auth(event: dict[str, Any], tenant_id: str) -> dict[str, Any] | None:
    claims = _authorizer_claims(event)
    if not claims:
        return None

    claim_tenant_id = _claim_tenant_id(claims)
    require_tenant_claim = os.getenv("COGNITO_REQUIRE_TENANT_CLAIM", "1") != "0"
    if require_tenant_claim and claim_tenant_id != tenant_id:
        return None

    return claims


def _handle_me(event: dict[str, Any]) -> dict[str, Any]:
    tenant_id = _tenant_id(event, {})
    if not tenant_id:
        return _response(400, {"error": "tenant_id_required"})
    claims = _require_auth(event, tenant_id)
    if not claims:
        return _response(401, {"error": "unauthorized"})

    email = claims.get("email") or claims.get("cognito:username") or claims.get("username")
    return _response(200, {"user": {"email": email, "tenant_id": tenant_id}})

def _metric_names(payload: dict[str, Any], query: dict[str, str]) -> list[str] | None:
    raw = payload.get("metrics") or query.get("metrics")
    if not raw:
        return None
    if isinstance(raw, str):
        return [x.strip() for x in raw.split(",") if x.strip()]
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return None


def _handle_monthly_metrics(event: dict[str, Any]) -> dict[str, Any]:
    query = _query(event)
    payload = _body(event) if _method(event) == "POST" else {}
    tenant_id = _tenant_id(event, payload)
    if not tenant_id:
        return _response(400, {"error": "tenant_id_required"})

    month = str(payload.get("month") or query.get("month") or datetime.now(timezone.utc).strftime("%Y-%m")).strip()
    if not _MONTH_RE.match(month):
        return _response(400, {"error": "invalid_month", "expected": "YYYY-MM"})

    if not _require_auth(event, tenant_id):
        return _response(401, {"error": "unauthorized"})

    metrics = MetricsService().monthly_stats(
        tenant_id=tenant_id,
        month=month,
        metric_names=_metric_names(payload, query),
    )
    return _response(200, {"tenant_id": tenant_id, "month": month, "metrics": metrics})


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _clean_tags(value: Any) -> list[str]:
    return [str(x).strip() for x in _as_list(value) if str(x).strip()]


def _clean_phones(value: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in _as_list(value):
        phone = normalize_phone(str(raw))
        if not phone or phone in seen:
            continue
        seen.add(phone)
        out.append(phone)
    return out


def _campaign_item(tenant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    campaign_id = str(payload.get("campaign_id") or new_id("cmp-"))
    body = payload.get("body")
    template = payload.get("template") or {}
    template_body = template.get("body") if isinstance(template, dict) else None
    final_body = body if body is not None else template_body
    if not isinstance(final_body, str) or not final_body.strip():
        raise ValueError("body_required")

    phones = _clean_phones(payload.get("phones") or payload.get("phone_numbers") or payload.get("recipients"))
    if not phones:
        raise ValueError("recipients_required")

    recipients = [{"token": encrypt_phone(tenant_id, phone)} for phone in phones]
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    next_run_time = str(payload.get("next_run_time") or now).strip()

    item: dict[str, Any] = {
        "pk": f"TENANT#{tenant_id}#CAMPAIGN#{campaign_id}",
        "campaign_id": campaign_id,
        "tenant_id": tenant_id,
        "active": bool(payload.get("active", True)),
        "next_run_time": next_run_time,
        "body": final_body,
        "recipients": recipients,
        "created_at": now,
        "source": "tenant_frontend",
    }

    optional_str = ["language_code", "template_name", "send_from", "send_to"]
    for key in optional_str:
        value = payload.get(key) or (template.get(key) if isinstance(template, dict) else None)
        if value is not None and str(value).strip():
            item[key] = str(value).strip()

    include_tags = _clean_tags(payload.get("include_tags"))
    exclude_tags = _clean_tags(payload.get("exclude_tags"))
    if include_tags:
        item["include_tags"] = include_tags
    if exclude_tags:
        item["exclude_tags"] = exclude_tags

    placeholders = payload.get("placeholders") or (template.get("placeholders") if isinstance(template, dict) else None)
    if isinstance(placeholders, list):
        item["placeholders"] = [str(x) for x in placeholders if str(x).strip()]

    context = payload.get("context")
    if isinstance(context, dict):
        item["context"] = context

    product_id = payload.get("payment_product_id")
    if product_id is not None and str(product_id).strip():
        item["payment_product_id"] = str(product_id).strip()

    return item


def _handle_create_campaign(event: dict[str, Any]) -> dict[str, Any]:
    payload = _body(event)
    tenant_id = _tenant_id(event, payload)
    if not tenant_id:
        return _response(400, {"error": "tenant_id_required"})

    if not _require_auth(event, tenant_id):
        return _response(401, {"error": "unauthorized"})

    try:
        item = _campaign_item(tenant_id, payload)
    except ValueError as e:
        return _response(400, {"error": str(e)})

    ddb_resource().Table(CAMPAIGNS_TABLE).put_item(Item=item)
    logger.info(
        {
            "component": "tenant_frontend",
            "event": "campaign_created",
            "tenant_id": tenant_id,
            "campaign_id": item["campaign_id"],
            "recipient_count": len(item.get("recipients") or []),
        }
    )
    return _response(
        201,
        {
            "tenant_id": tenant_id,
            "campaign_id": item["campaign_id"],
            "next_run_time": item["next_run_time"],
            "active": item["active"],
            "recipient_count": len(item.get("recipients") or []),
        },
    )


def lambda_handler(event, context):
    try:
        if _method(event) == "OPTIONS":
            return {"statusCode": 204, "headers": _headers(), "body": ""}

        path = _path(event)
        method = _method(event)
        resource = event.get("resource") or ""

        if method == "GET" and (path.endswith("/auth/me") or resource.endswith("/auth/me")):
            return _handle_me(event)

        if method in {"GET", "POST"} and (path.endswith("/metrics/monthly") or resource.endswith("/metrics/monthly")):
            return _handle_monthly_metrics(event)
        if method == "POST" and (path.endswith("/campaigns") or resource.endswith("/campaigns")):
            return _handle_create_campaign(event)

        return _response(404, {"error": "not_found"})
    except json.JSONDecodeError:
        return _response(400, {"error": "invalid_json"})
    except Exception as e:
        logger.exception({"component": "tenant_frontend", "error": str(e)})
        return _response(500, {"error": "internal_error"})
