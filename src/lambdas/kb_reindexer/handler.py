"""Lambda kb_reindexer.

Purpose:
  - Run ETL (load FAQ from S3) -> chunking -> embeddings -> upsert to Pinecone.

Trigger:
  - manual invocation (AWS console), or
  - EventBridge schedule, or
  - S3 PUT on KnowledgeBaseBucket (wired in template.yaml).

Input event examples:
  {"tenant_id": "default", "language_code": "pl"}
  {"tenant_id": "clubA", "languages": ["pl", "en"]}
  S3 event: {"Records":[{"s3":{"bucket":{"name":"..."}, "object":{"key":"tenantA/faq_pl.json"}}}]}
"""

import json
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from ...services.kb_service import KBService
from ...common.logging_utils import logger

FAQ_KEY_RE = re.compile(r"^(?P<tenant>[^/]+)/faq_(?P<lang>[A-Za-z-]+)\.json$")


def _parse_s3_records(event: Dict[str, Any]) -> List[Tuple[str, Optional[str]]]:
    """Extract (tenant_id, language_code) pairs from S3 event records.

    Supports keys like:
      tenantA/faq_pl.json
      tenantB/faq_en.json
      tenantC/faq_pl-PL.json  -> language_code = "pl" (normalized)
    """
    out: List[Tuple[str, Optional[str]]] = []
    records = event.get("Records") or []
    if not isinstance(records, list):
        return out

    for r in records:
        try:
            s3 = (r or {}).get("s3") or {}
            obj = (s3.get("object") or {})
            raw_key = obj.get("key") or ""
            if not raw_key:
                continue
            key = urllib.parse.unquote_plus(raw_key)

            m = FAQ_KEY_RE.match(key)
            if not m:
                continue

            tenant = m.group("tenant")
            lang = m.group("lang")
            if "-" in lang:
                lang = lang.split("-", 1)[0]
            out.append((tenant, lang))
        except Exception:
            continue

    return out

def _parse_eventbridge_s3(event: Dict[str, Any]) -> List[Tuple[str, Optional[str]]]:
    """Extract (tenant_id, language_code) from EventBridge S3 events."""
    try:
        detail = event.get("detail") or {}
        obj = detail.get("object") or {}
        raw_key = obj.get("key") or ""
        if not raw_key:
            return []
        key = urllib.parse.unquote_plus(raw_key)
        m = FAQ_KEY_RE.match(key)
        if not m:
            return []
        tenant = m.group("tenant")
        lang = m.group("lang")
        if "-" in lang:
            lang = lang.split("-", 1)[0]
        return [(tenant, lang)]
    except Exception:
        return []

def lambda_handler(event, context):

    kb = KBService()
    body = event or {}

    # 1) S3-triggered mode: parse Records and reindex only affected tenant/lang pairs
    pairs = []
    if isinstance(body, dict):
        pairs = _parse_s3_records(body)
        if not pairs and body.get("source") == "aws.s3" and body.get("detail-type") in ("Object Created", "Object Created (All)"):
            pairs = _parse_eventbridge_s3(body)

    if pairs:
        indexed = []
        for tenant_id, lang in pairs:
            ok = kb.reindex_faq(tenant_id=tenant_id, language_code=lang)
            indexed.append({"tenant_id": tenant_id, "language_code": lang or "", "ok": bool(ok)})

        results = {"mode": "s3", "indexed": indexed}
        logger.info({"component": "lambda_handler","event": "kb_reindexer_done", **results})
        return {"statusCode": 200, "body": json.dumps(results)}

    # 2) Manual/scheduled mode: explicit tenant_id + language(s)
    tenant_id = body.get("tenant_id") or "default"
    language_code = body.get("language_code")
    languages = body.get("languages")

    results = {"mode": "manual", "tenant_id": tenant_id, "indexed": []}
 
    if isinstance(languages, list) and languages:
        for lang in languages:
            ok = kb.reindex_faq(tenant_id=tenant_id, language_code=str(lang))
            results["indexed"].append({"language_code": str(lang), "ok": bool(ok)})
    else:
        ok = kb.reindex_faq(tenant_id=tenant_id, language_code=language_code)
        results["indexed"].append({"language_code": language_code or "", "ok": bool(ok)})

    log_safe({"event": "kb_reindexer_done", **results})
    return {"statusCode": 200, "body": json.dumps(results)}
