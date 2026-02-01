"""Utilities for chunking knowledge-base texts (FAQ) into embedding-friendly pieces.

The goal is stable, deterministic chunk IDs so that re-indexing overwrites
previous vectors in Pinecone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List
import re
import hashlib


@dataclass(frozen=True)
class FAQChunk:
    """Single chunk derived from an FAQ entry."""

    chunk_id: str
    faq_key: str
    text: str


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _stable_id(*parts: str) -> str:
    raw = "|".join([p or "" for p in parts])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def chunk_faq(
    faq: Dict[str, str],
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

    for faq_key, answer in (faq or {}).items():
        if not faq_key or not answer:
            continue

        q = _normalize_ws(str(faq_key))
        a = _normalize_ws(str(answer))

        doc = f"Q: {q}\nA: {a}" if include_q_prefix else f"{q}\n{a}"
        doc = doc.strip()
        if not doc:
            continue

        if len(doc) <= max_chars:
            cid = _stable_id(q, doc)
            chunks.append(FAQChunk(chunk_id=cid, faq_key=q, text=doc))
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
                    cid = _stable_id(q, buf)
                    chunks.append(FAQChunk(chunk_id=cid, faq_key=q, text=buf))
                buf = part

        if buf.strip():
            cid = _stable_id(q, buf.strip())
            chunks.append(FAQChunk(chunk_id=cid, faq_key=q, text=buf.strip()))

        # If still any chunk exceeds max_chars (rare), hard-split with overlap.
        final: List[FAQChunk] = []
        for ch in chunks:
            if ch.faq_key != q or len(ch.text) <= max_chars:
                final.append(ch)
                continue
            t = ch.text
            start = 0
            while start < len(t):
                end = min(len(t), start + max_chars)
                piece = t[start:end].strip()
                if piece:
                    cid = _stable_id(q, piece)
                    final.append(FAQChunk(chunk_id=cid, faq_key=q, text=piece))
                if end >= len(t):
                    break
                start = max(0, end - overlap_chars)
        chunks = final

    return chunks
