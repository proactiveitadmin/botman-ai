# src/common/http_client.py
from __future__ import annotations
import os
import requests
from requests.adapters import HTTPAdapter

_SESSION: requests.Session | None = None

def get_session() -> requests.Session:
    global _SESSION
    if _SESSION is not None:
        return _SESSION

    s = requests.Session()

    pool_conn = int(os.getenv("HTTP_POOL_CONN", "32"))
    pool_max = int(os.getenv("HTTP_POOL_MAX", "32"))

    adapter = HTTPAdapter(
        pool_connections=pool_conn,
        pool_maxsize=pool_max,
        max_retries=0,
    )
    s.mount("https://", adapter)
    s.mount("http://", adapter)

    _SESSION = s
    return s
