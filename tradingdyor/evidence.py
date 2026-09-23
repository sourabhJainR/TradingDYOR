from __future__ import annotations
from datetime import datetime, timezone
import hashlib
from .models import Evidence

def normalize_browser_observation(payload: dict, source: str) -> Evidence:
    excerpt=" ".join(str(payload.get("excerpt","")).split())
    title=str(payload.get("title",""))
    return Evidence(
        source=source,
        url=str(payload.get("url","")),
        retrieved_at=datetime.now(timezone.utc),
        title=title,
        excerpt=excerpt[:12000],
        confidence=0.60 if excerpt else 0.0,
        extraction_method=payload.get("extraction_method","browser"),
    )

def evidence_hash(e: Evidence) -> str:
    raw="|".join([e.source,e.url,e.title,e.excerpt])
    return hashlib.sha256(raw.encode()).hexdigest()
