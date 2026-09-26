from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256

from .evidence_graph import EvidenceGraph
from .source_policy import source_tier, source_weight


@dataclass(frozen=True)
class Claim:
    id: str
    text: str
    value: str
    source: str
    evidence_id: str
    confidence: float
    status: str = "supported"


class ClaimGraph:
    """Auditable claim -> evidence provenance with deterministic IDs and conflict status."""
    def __init__(self, evidence: EvidenceGraph | None = None):
        self.evidence = evidence or EvidenceGraph()
        self.claims: list[Claim] = []

    def add_claim(self, text: str, value: object, source: str, url: str = "", observed_at: str | None = None,
                  available_at: str = "", confidence: float = 0.5, relevance: float = 0.5) -> Claim:
        value_text = str(value)
        evidence_text = f"{text}|{value_text}|{source}|{url}|{observed_at or ''}"
        evidence_id = sha256(evidence_text.encode()).hexdigest()
        self.evidence.add(
            kind="claim-evidence",
            source=source,
            url=url,
            available_at=available_at or observed_at or "",
            observed_at=observed_at,
            content=evidence_text,
            confidence=max(0.0, min(1.0, confidence * source_weight(source))),
            relevance=relevance,
        )
        claim_id = sha256(f"{text}|{value_text}|{source}".encode()).hexdigest()[:16]
        claim = Claim(claim_id, text, value_text, source, evidence_id,
                      max(0.0, min(1.0, confidence * source_weight(source))))
        self.claims.append(claim)
        return claim

    def reconcile(self) -> list[dict]:
        grouped: dict[str, list[Claim]] = {}
        for claim in self.claims:
            grouped.setdefault(claim.text.strip().lower(), []).append(claim)
        reconciled=[]
        for text, claims in grouped.items():
            values={c.value for c in claims}
            if len(values) == 1:
                reconciled.append({"claim": text, "value": claims[0].value, "status": "supported",
                                   "claim_ids": [c.id for c in claims]})
                continue
            ordered=sorted(claims, key=lambda c:(source_tier(c.source), -c.confidence))
            top=ordered[0]
            same_tier=[c for c in ordered if source_tier(c.source)==source_tier(top.source)]
            status="contested" if len({c.value for c in same_tier})>1 else "resolved-primary"
            reconciled.append({"claim": text, "value": top.value, "status": status,
                               "claim_ids": [c.id for c in claims],
                               "alternatives": sorted(values),
                               "selected_source": top.source})
        return reconciled

    def snapshot(self) -> dict:
        return {
            "evidence": self.evidence.snapshot(),
            "claims": [asdict(c) for c in self.claims],
            "reconciled": self.reconcile(),
        }
