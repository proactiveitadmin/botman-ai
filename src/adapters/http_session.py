"""Shared HTTP session pool for outbound adapter integrations.

The adapters in this package are used in short request/response flows where the
same external hosts are called repeatedly. Reusing `requests.Session` lets
urllib3 keep TCP/TLS connections alive between calls in a warm process.

The pool is intentionally small and dependency-free:
- no automatic retries here; adapter-level business retry logic stays in clients,
- sessions are thread-local, so we avoid sharing mutable Session state between
  concurrent worker threads,
- headers/auth are still passed per request to avoid tenant credential leakage.
"""

from __future__ import annotations

import threading
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter

_DEFAULT_POOL_CONNECTIONS = 16
_DEFAULT_POOL_MAXSIZE = 32

_THREAD_LOCAL = threading.local()


_POOL_BLOCK = False


def _sessions() -> dict[str, requests.Session]:
    sessions = getattr(_THREAD_LOCAL, "sessions", None)
    if sessions is None:
        sessions = {}
        _THREAD_LOCAL.sessions = sessions
    return sessions


def session_key_for_url(url: str, *, prefix: str | None = None) -> str:
    """Build a stable session-pool key from an outbound URL/base URL."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.netloc or parsed.path or "default").strip().lower()
    return f"{prefix}:{host}" if prefix else host


def get_pooled_session(pool_key: str = "default") -> requests.Session:
    """Return a thread-local Session configured for HTTP connection pooling."""
    sessions = _sessions()
    session = sessions.get(pool_key)
    if session is not None:
        return session

    adapter = HTTPAdapter(
        pool_connections=_DEFAULT_POOL_CONNECTIONS,
        pool_maxsize=_DEFAULT_POOL_MAXSIZE,
        pool_block=_POOL_BLOCK,
    )

    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    sessions[pool_key] = session
    return session


def close_pooled_sessions() -> None:
    """Close sessions for the current thread; useful in tests or graceful shutdown."""
    sessions = _sessions()
    for session in sessions.values():
        session.close()
    sessions.clear()
