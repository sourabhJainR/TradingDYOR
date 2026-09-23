from __future__ import annotations

from dataclasses import dataclass
from .source_policy import source_tier


@dataclass(frozen=True)
class Contradiction:
    claim: str
    values: tuple[str, ...]
    sources: tuple[str, ...]
    severity: str
    resolution: str


def detect_contradictions(claims: list[dict]) -> list[Contradiction]:
    grouped: dict[str, list[dict]] = {}
    for claim in claims:
        key = str(claim.get("claim", "")).strip().lower()
        if key:
            grouped.setdefault(key, []).append(claim)

    out: list[Contradiction] = []
    for key, rows in grouped.items():
        values = {str(r.get("value", "")).strip() for r in rows}
        if len(values) <= 1:
            continue
        ordered = sorted(rows, key=lambda r: source_tier(str(r.get("source", ""))))
        tiers = {source_tier(str(r.get("source", ""))) for r in rows}
        severity = "high" if len(tiers) == 1 and len(values) > 1 else "medium"
        resolution = (
            f"Prefer the lowest source tier number ({min(tiers)}) and retain the conflict for review"
            if len(tiers) > 1 else "No source-tier tie-breaker exists; require verification"
        )
        out.append(Contradiction(
            claim=key,
            values=tuple(sorted(values)),
            sources=tuple(str(r.get("source", "")) for r in ordered),
            severity=severity,
            resolution=resolution,
        ))
    return out
