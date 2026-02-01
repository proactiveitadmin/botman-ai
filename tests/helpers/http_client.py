from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class HttpClient:
    base_url: str
    timeout_s: float = 10.0

    def get(self, path: str, **kwargs: Any) -> requests.Response:
        url = self.base_url.rstrip("/") + "/" + path.lstrip("/")
        return requests.get(url, timeout=self.timeout_s, **kwargs)

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        url = self.base_url.rstrip("/") + "/" + path.lstrip("/")
        return requests.post(url, timeout=self.timeout_s, **kwargs)
