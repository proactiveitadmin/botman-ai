"""Minimal Pinecone data-plane client (REST).

We intentionally avoid a hard dependency on the official pinecone SDK so that:
- the Lambda package stays small,
- local tests remain simple.

Requires:
  - PINECONE_API_KEY
  - PINECONE_INDEX_HOST (data-plane host)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import time
import random
import requests

from ..common.logging_utils import logger


@dataclass
class PineconeMatch:
    id: str
    score: float
    metadata: Dict[str, Any]


class PineconeClient:
    def __init__(self, *, api_key: str, index_host: str, timeout_s: float = 10.0) -> None:
        self.api_key = api_key or ""
        self.index_host = (index_host or "").replace("https://", "").replace("http://", "").strip("/")
        self.timeout_s = timeout_s
        self.enabled = bool(self.api_key and self.index_host)

    def _headers(self) -> Dict[str, str]:
        return {
            "Api-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"https://{self.index_host}{path}"

    def upsert(
        self,
        *,
        vectors: List[Dict[str, Any]],
        namespace: str,
        max_attempts: int = 3,
    ) -> bool:
        if not self.enabled:
            return False

        payload = {"vectors": vectors, "namespace": namespace}
        url = self._url("/vectors/upsert")

        for attempt in range(max_attempts):
            try:
                r = requests.post(url, headers=self._headers(), json=payload, timeout=self.timeout_s)
                if r.status_code >= 200 and r.status_code < 300:
                    return True
                logger.info({"component": "pinecone_client","event": "pinecone_upsert_http", "status": r.status_code, "body": r.text[:500]})
            except Exception as e:
                logger.error({"component": "pinecone_client","event": "pinecone_upsert_err", "err": str(e)})
            time.sleep(min(2.0, 0.2 * (2**attempt) + random.random() * 0.2))
        return False

    def query(
        self,
        *,
        vector: List[float],
        namespace: str,
        top_k: int = 6,
        include_metadata: bool = True,
        max_attempts: int = 3,
    ) -> List[PineconeMatch]:
        if not self.enabled:
            return []

        payload = {
            "vector": vector,
            "topK": top_k,
            "namespace": namespace,
            "includeMetadata": include_metadata,
        }
        url = self._url("/query")

        for attempt in range(max_attempts):
            try:
                r = requests.post(url, headers=self._headers(), json=payload, timeout=self.timeout_s)
                if 200 <= r.status_code < 300:
                    data = r.json() or {}
                    matches = []
                    for m in data.get("matches", []) or []:
                        matches.append(PineconeMatch(
                            id=m.get("id", ""),
                            score=float(m.get("score", 0.0) or 0.0),
                            metadata=m.get("metadata") or {},
                        ))
                    return matches
                logger.info({"component": "pnecone_client","event": "pinecone_query_http", "status": r.status_code, "body": r.text[:500]})
            except Exception as e:
                logger.error({"component": "pnecone_client","event": "pinecone_query_err", "err": str(e)})
            time.sleep(min(2.0, 0.2 * (2**attempt) + random.random() * 0.2))
        return []
