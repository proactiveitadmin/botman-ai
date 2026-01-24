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
from ..common.config import settings
from ..common.timing import timed



@dataclass
class PineconeMatch:
    id: str
    score: float
    metadata: Dict[str, Any]


class PineconeClient:
    def __init__(
        self, 
        *, 
        api_key: str | None = None,
        index_host: str | None = None,
        timeout_s: float = 10.0
    ) -> None:
        self.api_key = api_key or getattr(settings, "pinecone_api_key", None)
        self.index_host = (index_host or "").replace("https://", "").replace("http://", "").strip("/")
        self.timeout_s = timeout_s
        self.enabled = bool(self.api_key and self.index_host)
    
    @classmethod
    def from_tenant_config(cls, tenant_cfg: dict) -> "PineconeClient":
        pc = (tenant_cfg or {}).get("pinecone") or {}
        if not isinstance(pc, dict):
            pc = {}
        return cls(
            api_key=pc.get("api_key") or getattr(settings, "pinecone_api_key", None),
            index_host=pc.get("index_host") or getattr(settings, "pinecone_index_host", None),
            timeout_s=float(getattr(settings, "pinecone_timeout_s", 10.0) or 10.0),
        )
        
    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #        
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

        with timed(
            "pinecone_upsert_total",
            logger=logger, 
            component="pinecone_client",
            extra={"namespace": namespace, "vectors": len(vectors), "max_attempts": max_attempts},
        ):
            for attempt in range(max_attempts):
                try:
                    with timed(
                        "pinecone_upsert_http",
                        logger=logger, 
                        component="pinecone_client",
                        extra={"attempt": attempt + 1, "timeout_s": self.timeout_s},
                    ):
                        r = requests.post(url, headers=self._headers(), json=payload, timeout=self.timeout_s)

                    if 200 <= r.status_code < 300:
                        return True

                    logger.info({"component": "pinecone_client","event": "pinecone_upsert_http", "status": r.status_code, "body": r.text[:500]})
                except Exception as e:
                    logger.error({"component": "pinecone_client","event": "pinecone_upsert_err", "err": str(e)})

                sleep_s = min(2.0, 0.2 * (2**attempt) + random.random() * 0.2)
                with timed("pinecone_retry_sleep", logger=logger, component="pinecone_client", extra={"attempt": attempt + 1, "sleep_s": round(sleep_s, 3)}):
                    time.sleep(sleep_s)

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

        with timed(
            "pinecone_query_total",
            logger=logger, 
            component="pinecone_client",
            extra={"namespace": namespace, "top_k": top_k, "include_metadata": include_metadata, "max_attempts": max_attempts},
        ):
            for attempt in range(max_attempts):
                try:
                    with timed(
                        "pinecone_query_http",
                        logger=logger, 
                        component="pinecone_client",
                        extra={"attempt": attempt + 1, "timeout_s": self.timeout_s},
                    ):
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
                        logger.info({"component": "pinecone_client", "event": "pinecone_query_ok", "attempt": attempt + 1, "returned": len(matches)})
                        return matches

                    logger.info({"component": "pinecone_client","event": "pinecone_query_http", "status": r.status_code, "body": r.text[:500]})
                except Exception as e:
                    logger.error({"component": "pinecone_client","event": "pinecone_query_err", "err": str(e)})

                sleep_s = min(2.0, 0.2 * (2**attempt) + random.random() * 0.2)
                with timed("pinecone_retry_sleep",logger=logger,  component="pinecone_client", extra={"attempt": attempt + 1, "sleep_s": round(sleep_s, 3)}):
                    time.sleep(sleep_s)

        return []
