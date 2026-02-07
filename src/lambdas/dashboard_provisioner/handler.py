"""CloudFormation custom resource: per-tenant CloudWatch dashboards.

Creates/updates a dashboard for every tenant found in the Tenants DynamoDB table.

Goals:
  - Multi-tenant observability ready for scale
  - Dashboards include: errors, latency, traffic, and cost proxies

Notes:
  - Dashboards are named deterministically: {DASHBOARD_PREFIX}{tenant_id}
  - Uses CloudWatch EMF metrics emitted by the app (namespace: METRICS_NAMESPACE)
"""

from __future__ import annotations

import json
import os
import traceback
import urllib.request
from typing import Any, Dict, List

import boto3


def _env(name: str, default: str = "") -> str:
    v = (os.getenv(name) or default).strip()
    return v


def _send_cfn_response(
    event: Dict[str, Any],
    *,
    context,
    status: str,
    reason: str | None = None,
    physical_resource_id: str | None = None,
    data: Dict[str, Any] | None = None,
) -> None:
    url = event.get("ResponseURL")
    if not url:
        return

    body = {
        "Status": status,
        "Reason": reason or "",
        "PhysicalResourceId": physical_resource_id or (getattr(context, "log_stream_name", "tenant-dashboards")),
        "StackId": event.get("StackId"),
        "RequestId": event.get("RequestId"),
        "LogicalResourceId": event.get("LogicalResourceId"),
        "NoEcho": False,
        "Data": data or {},
    }

    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="PUT")
    req.add_header("content-type", "")
    req.add_header("content-length", str(len(payload)))
    urllib.request.urlopen(req, timeout=10).read()


def _scan_tenants(table_name: str) -> List[str]:
    ddb = boto3.resource("dynamodb")
    table = ddb.Table(table_name)
    tenant_ids: List[str] = []
    start_key = None
    while True:
        kwargs: Dict[str, Any] = {"ProjectionExpression": "tenant_id"}
        if start_key:
            kwargs["ExclusiveStartKey"] = start_key
        resp = table.scan(**kwargs)
        for it in resp.get("Items", []) or []:
            tid = (it.get("tenant_id") or "").strip()
            if tid:
                tenant_ids.append(tid)
        start_key = resp.get("LastEvaluatedKey")
        if not start_key:
            break
    return sorted(set(tenant_ids))


def _tenant_dashboard_body(*, tenant_id: str, namespace: str, region: str) -> Dict[str, Any]:
    # CloudWatch dashboard body format: https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_PutDashboard.html
    dims = ["tenant_id", tenant_id]

    def m(metric: str, stat: str = "Sum", period: int = 60):
        return [namespace, metric, *dims, {"stat": stat, "period": period, "region": region}]

    widgets = [
        {
            "type": "text",
            "x": 0,
            "y": 0,
            "width": 24,
            "height": 2,
            "properties": {
                "markdown": f"# Tenant: `{tenant_id}`\nNamespace: `{namespace}`"
            },
        },
        {
            "type": "metric",
            "x": 0,
            "y": 2,
            "width": 12,
            "height": 6,
            "properties": {
                "view": "timeSeries",
                "stacked": False,
                "region": region,
                "title": "Inbound / Routing / Outbound Errors",
                "metrics": [
                    m("TenantInboundError"),
                    m("TenantRoutedError"),
                    m("TenantOutboundThrottled"),
                ],
            },
        },
        {
            "type": "metric",
            "x": 12,
            "y": 2,
            "width": 12,
            "height": 6,
            "properties": {
                "view": "timeSeries",
                "stacked": False,
                "region": region,
                "title": "Traffic",
                "metrics": [
                    m("TenantInboundAccepted"),
                    m("TenantRoutedInbound"),
                    m("TenantOutboundQueued"),
                    m("TenantOutboundSent"),
                    m("TenantOutboundDuplicate"),
                ],
            },
        },
        {
            "type": "metric",
            "x": 0,
            "y": 8,
            "width": 12,
            "height": 6,
            "properties": {
                "view": "timeSeries",
                "stacked": False,
                "region": region,
                "title": "Latency (ms)",
                "metrics": [
                    m("TenantInboundLatencyMs", stat="Average"),
                    m("TenantRoutingLatencyMs", stat="Average"),
                ],
            },
        },
        {
            "type": "metric",
            "x": 12,
            "y": 8,
            "width": 12,
            "height": 6,
            "properties": {
                "view": "timeSeries",
                "stacked": False,
                "region": region,
                "title": "Cost proxy (Lambda usage)",
                "metrics": [
                    # If you later add a real EstimatedCostUSD metric, it will show here.
                    m("TenantEstimatedCostUSD", stat="Sum"),
                    # Proxies: route traffic & latency to correlate with costs.
                    m("TenantRoutedInbound", stat="Sum"),
                    m("TenantRoutingLatencyMs", stat="Average"),
                ],
            },
        },
    ]

    return {"widgets": widgets}


def lambda_handler(event: Dict[str, Any], context):
    table_name = _env("DDB_TABLE_TENANTS")
    if not table_name:
        _send_cfn_response(event, context=context, status="FAILED", reason="Missing DDB_TABLE_TENANTS")
        return

    namespace = _env("METRICS_NAMESPACE", "BotmanAI")
    prefix = _env("DASHBOARD_PREFIX", "tenant-")
    region = _env("AWS_REGION", "us-east-1")

    cw = boto3.client("cloudwatch", region_name=region)

    req_type = (event.get("RequestType") or "").strip()
    physical_id = event.get("PhysicalResourceId") or f"tenant-dashboards-{table_name}"

    try:
        tenant_ids = _scan_tenants(table_name)

        if req_type in ("Create", "Update"):
            created = []
            for tid in tenant_ids:
                dash_name = f"{prefix}{tid}"
                body = _tenant_dashboard_body(tenant_id=tid, namespace=namespace, region=region)
                cw.put_dashboard(DashboardName=dash_name, DashboardBody=json.dumps(body))
                created.append(dash_name)

            _send_cfn_response(
                event,
                context=context,
                status="SUCCESS",
                physical_resource_id=physical_id,
                data={"Dashboards": created, "TenantCount": len(tenant_ids)},
            )
            return

        if req_type == "Delete":
            # Best-effort deletion.
            names = [f"{prefix}{tid}" for tid in tenant_ids]
            if names:
                # delete_dashboards supports up to 1000 names in one call
                for i in range(0, len(names), 1000):
                    cw.delete_dashboards(DashboardNames=names[i : i + 1000])

            _send_cfn_response(
                event,
                context=context,
                status="SUCCESS",
                physical_resource_id=physical_id,
                data={"Deleted": len(names)},
            )
            return

        _send_cfn_response(
            event,
            context=context,
            status="FAILED",
            reason=f"Unsupported RequestType={req_type}",
            physical_resource_id=physical_id,
        )
    except Exception as e:
        _send_cfn_response(
            event,
            context=context,
            status="FAILED",
            reason=f"{e}\n{traceback.format_exc()}"[:1024],
            physical_resource_id=physical_id,
        )
