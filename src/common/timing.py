from __future__ import annotations
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional

SLOW_THRESHOLD_MS=3 #300

@contextmanager
def timed(name: str, *, logger, component: str, extra: Optional[Dict[str, Any]] = None):
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = int((time.perf_counter() - start) * 1000)
        payload: Dict[str, Any] = {
            "component": component,
            "event": "timing",
            "name": name,
            "duration_ms": duration_ms,
        }
        if extra:
            payload.update(extra)
        if duration_ms >= SLOW_THRESHOLD_MS:
            logger.warning(payload)
