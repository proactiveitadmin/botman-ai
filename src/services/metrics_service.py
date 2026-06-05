from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from aws_embedded_metrics import metric_scope

from ..common.aws import cloudwatch_client


@metric_scope
def emit_metric(
    metrics,
    *,
    namespace: str,
    tenant_id: str,
    metric_name: str,
    value: float = 1.0,
    unit: str = "Count",
    log_fields: Optional[Dict[str, Any]] = None,
) -> None:
    metrics.set_namespace(namespace)

    # TYLKO tenant_id jako dimension
    metrics.set_dimensions({
        "tenant_id": tenant_id or "unknown",
    })

    metrics.put_metric(metric_name, value, unit)

    # dodatkowe pola tylko do logów
    if log_fields:
        for k, v in log_fields.items():
            metrics.set_property(k, v)


class MetricsService:
    def __init__(self, *, namespace: Optional[str] = None) -> None:
        self.namespace = (
            namespace
            or os.getenv("METRICS_NAMESPACE")
            or "Dialo"
        ).strip() or "Dialo"

        self.function = (
            os.getenv("AWS_LAMBDA_FUNCTION_NAME")
            or "unknown"
        ).strip()

    def incr(
        self,
        name: str,
        *,
        value: float = 1.0,
        unit: str = "Count",
        tenant_id: Optional[str] = None,
        component: Optional[str] = None,
        extra_dims: Optional[Dict[str, str]] = None,
        **fields: Any,
    ) -> None:

        log_fields: Dict[str, Any] = {
            "function": self.function,
        }

        if component:
            log_fields["component"] = component

        if extra_dims:
            log_fields.update(extra_dims)

        if fields:
            log_fields.update(fields)

        emit_metric(
            namespace=self.namespace,
            tenant_id=tenant_id or "unknown",
            metric_name=name,
            value=float(value),
            unit=unit,
            log_fields=log_fields,
        )

    def timing_ms(
        self,
        name: str,
        duration_ms: float,
        *,
        tenant_id: Optional[str] = None,
        component: Optional[str] = None,
        **fields: Any,
    ) -> None:
        self.incr(
            name,
            value=float(duration_ms),
            unit="Milliseconds",
            tenant_id=tenant_id,
            component=component,
            **fields,
        )
    def monthly_stats(
        self,
        *,
        tenant_id: str,
        month: str,
        metric_names: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        """Return per-tenant monthly CloudWatch metric sums.

        month: YYYY-MM in UTC. The method intentionally exposes aggregate
        counters only; no phone numbers, message bodies, or user identifiers.
        """
        names = metric_names or [
            "TenantInboundAccepted",
            "TenantInboundBlocked",
            "TenantRoutedInbound",
            "TenantRoutedOk",
            "TenantRoutedError",
            "TenantOutboundQueued",
            "TenantOutboundSent",
            "TenantCampaignSendOk",
        ]
        year, month_no = [int(x) for x in month.split("-", 1)]
        start = datetime(year, month_no, 1, tzinfo=timezone.utc)
        if month_no == 12:
            end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end = datetime(year, month_no + 1, 1, tzinfo=timezone.utc)

        period = max(60, int((end - start).total_seconds()))
        queries = []
        id_to_name: Dict[str, str] = {}
        for idx, name in enumerate(names):
            qid = f"m{idx}"
            id_to_name[qid] = name
            queries.append(
                {
                    "Id": qid,
                    "MetricStat": {
                        "Metric": {
                            "Namespace": self.namespace,
                            "MetricName": name,
                            "Dimensions": [{"Name": "tenant_id", "Value": tenant_id}],
                        },
                        "Period": period,
                        "Stat": "Sum",
                    },
                    "ReturnData": True,
                }
            )

        if not queries:
            return {}

        resp = cloudwatch_client().get_metric_data(
            MetricDataQueries=queries,
            StartTime=start,
            EndTime=end,
            ScanBy="TimestampAscending",
        )
        out: Dict[str, Any] = {}
        for result in resp.get("MetricDataResults", []):
            name = id_to_name.get(result.get("Id", ""), result.get("Label", "unknown"))
            values = result.get("Values") or []
            out[name] = float(sum(values)) if values else 0.0
        return out
