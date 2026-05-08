from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from aws_embedded_metrics import metric_scope


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