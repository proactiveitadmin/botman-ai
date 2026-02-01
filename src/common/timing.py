from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


# Default 300ms; configurable for profiling/alerts
SLOW_THRESHOLD_MS = _env_int("TIMING_SLOW_THRESHOLD_MS", 300)
# If true: log all timings at info, slow ones still at warning
LOG_ALL = os.getenv("TIMING_LOG_ALL", "false").lower() == "true"


@contextmanager
def timed(
    name: str,
    *,
    logger,
    component: str,
    extra: Optional[Dict[str, Any]] = None,
):
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = int((time.perf_counter() - start) * 1000)
        payload: Dict[str, Any] = {
            "component": component,
            "timing": name,
            "duration_ms": duration_ms,
        }
        if extra:
            payload.update(extra)

        if duration_ms >= SLOW_THRESHOLD_MS:
            logger.warning(payload)
        else:
            if LOG_ALL:
                logger.info(payload)