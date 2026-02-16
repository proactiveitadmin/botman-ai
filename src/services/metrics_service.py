from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from ..common.logging import logger


class MetricsService:
    """Emits CloudWatch metrics using Embedded Metric Format (EMF).

    Why EMF:
      - No extra AWS API calls per invocation (metrics are extracted from logs).
      - Easy to dimension metrics by tenant_id / function / component.

    Naming:
      - Namespace is configurable via METRICS_NAMESPACE (default: BotmanAI).
      - Dimensions always include tenant_id and function.
    """

    def __init__(self, *, namespace: Optional[str] = None) -> None:
        self.namespace = (namespace or os.getenv("METRICS_NAMESPACE") or "BotmanAI").strip() or "BotmanAI"
        self.function = (os.getenv("AWS_LAMBDA_FUNCTION_NAME") or "").strip() or "unknown"

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
        """Emit a single metric datapoint (EMF).

        - `fields` are additional structured log fields (not dimensions unless in extra_dims).
        """
        dims: Dict[str, str] = {
            "tenant_id": (tenant_id or "unknown"),
            "function": self.function,
        }
        if component:
            dims["component"] = str(component)
        if extra_dims:
            for k, v in extra_dims.items():
                if v is None:
                    continue
                dims[str(k)] = str(v)

        # Dimensions list must match the keys we attach in the log.
        dim_keys = list(dims.keys())

        payload: Dict[str, Any] = {
            **dims,
            name: value,
            **fields,
            "_aws": {
                "Timestamp": int(time.time() * 1000),
                "CloudWatchMetrics": [
                    {
                        "Namespace": self.namespace,
                        "Dimensions": [dim_keys],
                        "Metrics": [{"Name": name, "Unit": unit}],
                    }
                ],
            },
        }
        logger.info(payload)

    def timing_ms(
        self,
        name: str,
        duration_ms: float,
        *,
        tenant_id: Optional[str] = None,
        component: Optional[str] = None,
        extra_dims: Optional[Dict[str, str]] = None,
        **fields: Any,
    ) -> None:
        self.incr(
            name,
            value=float(duration_ms),
            unit="Milliseconds",
            tenant_id=tenant_id,
            component=component,
            extra_dims=extra_dims,
            **fields,
        )
