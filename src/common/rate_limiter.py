from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Dict


@dataclass
class _Bucket:
    rate: float     # tokens per second
    burst: float    # max tokens
    tokens: float
    ts: float       # last refill timestamp (monotonic)


class InMemoryRateLimiter:
    """
    Prosty limiter token-bucket działający w pamięci procesu.

    Uwaga dot. AWS Lambda:
    - obiekt może żyć dłużej niż 1 invokacja (warm container),
      dlatego jeśli limiter ma działać "per invoke",
      wywołaj reset() na początku lambda_handler.
    """

    def __init__(self) -> None:
        self._buckets: Dict[str, _Bucket] = {}

    def reset(self) -> None:
        self._buckets.clear()

    def acquire(self, key: str, *, rate: float, burst: float, cost: float = 1.0) -> None:
        if rate <= 0:
            return

        now = time.monotonic()
        b = self._buckets.get(key)
        if b is None:
            b = _Bucket(rate=rate, burst=burst, tokens=burst, ts=now)
            self._buckets[key] = b

        # refill
        elapsed = max(0.0, now - b.ts)
        b.tokens = min(b.burst, b.tokens + elapsed * b.rate)
        b.ts = now

        if b.tokens >= cost:
            b.tokens -= cost
            return

        missing = cost - b.tokens
        wait_s = missing / b.rate

        # drobny jitter, żeby nie synchronizować sleepów wewnątrz batcha
        wait_s *= random.uniform(0.9, 1.1)
        time.sleep(wait_s)

        # refill po sleep i pobierz
        now2 = time.monotonic()
        elapsed2 = max(0.0, now2 - b.ts)
        b.tokens = min(b.burst, b.tokens + elapsed2 * b.rate)
        b.ts = now2
        b.tokens = max(0.0, b.tokens - cost)

    def try_acquire(self, key: str, *, rate: float, burst: float, cost: float = 1.0) -> bool:
        """Non-blocking acquire.

        Returns True if tokens were available, False otherwise.
        """
        if rate <= 0:
            return True

        now = time.monotonic()
        b = self._buckets.get(key)
        if b is None:
            b = _Bucket(rate=rate, burst=burst, tokens=burst, ts=now)
            self._buckets[key] = b

        elapsed = max(0.0, now - b.ts)
        b.tokens = min(b.burst, b.tokens + elapsed * b.rate)
        b.ts = now

        if b.tokens >= cost:
            b.tokens -= cost
            return True
        return False