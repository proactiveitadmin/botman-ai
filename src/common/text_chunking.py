"""Utilities for chunking knowledge-base texts (FAQ) into embedding-friendly pieces.

The goal is stable, deterministic chunk IDs so that re-indexing overwrites
previous vectors in Pinecone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Union, Iterable, Tuple
import re
import hashlib


@dataclass(frozen=True)
class FAQChunk:
    """Single chunk derived from an FAQ entry."""

    chunk_id: str
    faq_key: str
    category: str
    text: str


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _stable_id(*parts: str) -> str:
    raw = "|".join([p or "" for p in parts])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


    

def chunk_faq(
    faq: Union[Dict[str, str], Dict[str, Any]],
    *,
    max_chars: int = 1200,
    overlap_chars: int = 150,
    include_q_prefix: bool = True,
) -> List[FAQChunk]:
    """Chunk FAQ dict into a list of FAQChunk.

    Strategy:
    - Each FAQ entry is a document: "Q: ...\nA: ...".
    - If it exceeds max_chars, we split on paragraph/sentence boundaries,
      falling back to hard splits.
    - We add small character overlap to preserve context across boundaries.

    Args:
        faq: mapping question/topic -> answer
        max_chars: maximum characters per chunk (safe for embedding models)
        overlap_chars: number of chars to overlap between adjacent chunks
        include_q_prefix: include "Q:" and "A:" labels in the chunk body

    Returns:
        List of FAQChunk with deterministic chunk_id.
    """
    
    chunks: List[FAQChunk] = []
    
    def _iter_entries(obj: Union[Dict[str, str], Dict[str, Any]]) -> Iterable[Tuple[str, str, List[str], str]]:
        """
        Yields (faq_key, questions[], answer) for both formats:
          - legacy: { "key": "answer" }
          - new: { "entries": [ { "key": ..., "questions": [...], "answer": ... }, ... ] }
        """
        if not obj:
            return []
        if isinstance(obj, dict) and isinstance(obj.get("entries"), list):
            out: List[Tuple[str, str, List[str], str]] = []
            for e in obj.get("entries") or []:
                if not isinstance(e, dict):
                    continue
                key = _normalize_ws(str(e.get("key") or ""))
                ans = _normalize_ws(str(e.get("answer") or ""))
                cat = _normalize_ws(str(e.get("category") or "kb")).lower()
                if cat not in ("kb", "smalltalk"):
                    cat = "kb"
                qs_raw = e.get("questions") or []
                qs: List[str] = []
                if isinstance(qs_raw, list):
                    for q in qs_raw:
                        qn = _normalize_ws(str(q or ""))
                        if qn:
                            qs.append(qn)
                if key and ans:
                    out.append((key, cat, qs, ans))
            return out
        # legacy
        if isinstance(obj, dict):
            out2: List[Tuple[str, str, List[str], str]] = []
            for k, v in obj.items():
                key = _normalize_ws(str(k or ""))
                ans = _normalize_ws(str(v or ""))
                if key and ans:
                    out2.append((key, "kb", [], ans))
            return out2
        return []
        
    for faq_key, category, questions, answer in _iter_entries(faq):
        # Build one or multiple "documents" per entry:
        # - if questions[] is provided -> chunk per natural question
        # - else -> fallback to key as question (legacy)
        q_list = questions if questions else [faq_key]

        for q_item in q_list:
            q = _normalize_ws(str(q_item))
            a = _normalize_ws(str(answer))

            doc = f"Q: {q}\nA: {a}" if include_q_prefix else f"{q}\n{a}"

            doc = doc.strip()
            if not doc:
                continue

            if len(doc) <= max_chars:
                cid = _stable_id(faq_key, q, a)
                chunks.append(FAQChunk(chunk_id=cid, faq_key=faq_key, category=category, text=doc))

                continue

            # Prefer splitting on paragraphs, then sentences.
            parts: List[str] = []
            paras = [p.strip() for p in re.split(r"\n\n+", doc) if p.strip()]
            if len(paras) > 1:
                parts = paras
            else:
                # sentence-ish split
                parts = [p.strip() for p in re.split(r"(?<=[\.!\?])\s+", doc) if p.strip()]

            buf = ""
            for part in parts:
                if not buf:
                    buf = part
                    continue
                if len(buf) + 1 + len(part) <= max_chars:
                    buf = f"{buf} {part}"
                else:
                    buf = buf.strip()
                    if buf:
                        cid = _stable_id(faq_key,q, buf)
                        chunks.append(FAQChunk(chunk_id=cid, faq_key=faq_key, category=category, text=buf))
                    buf = part

            if buf.strip():
                cid = _stable_id(faq_key, q, buf.strip())
                chunks.append(FAQChunk(chunk_id=cid, faq_key=faq_key, category=category, text=buf.strip()))

            # If still any chunk exceeds max_chars (rare), hard-split with overlap.
            final: List[FAQChunk] = []
            for ch in chunks:
                if ch.faq_key != faq_key or len(ch.text) <= max_chars:
                    final.append(ch)
                    continue
                t = ch.text
                start = 0
                while start < len(t):
                    end = min(len(t), start + max_chars)
                    piece = t[start:end].strip()
                    if piece:
                        cid = _stable_id(faq_key, q, piece)
                        final.append(FAQChunk(chunk_id=cid, faq_key=faq_key, category=category, text=piece))
                    if end >= len(t):
                        break
                    start = max(0, end - overlap_chars)
            chunks = final

    return chunks
