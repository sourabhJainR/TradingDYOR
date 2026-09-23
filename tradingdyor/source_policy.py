from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceRule:
    name: str
    tier: int
    weight: float
    kinds: tuple[str, ...]


SOURCE_RULES = (
    SourceRule("SEC", 1, 1.00, ("filing", "insider", "institutional")),
    SourceRule("Company IR", 1, 1.00, ("earnings", "guidance", "corporate_action")),
    SourceRule("FRED", 1, 1.00, ("macro",)),
    SourceRule("ECB", 1, 1.00, ("macro",)),
    SourceRule("USPTO/PatentsView", 1, 0.95, ("patent",)),
    SourceRule("Institutional", 2, 0.80, ("institutional",)),
    SourceRule("Market data", 2, 0.80, ("market", "sector")),
    SourceRule("Aggregator", 3, 0.55, ("market", "secondary")),
)


def source_weight(source: str, kind: str = "") -> float:
    source_l = source.lower()
    matches = [
        r.weight for r in SOURCE_RULES
        if (r.name.lower() in source_l or source_l in r.name.lower())
        and (not kind or kind in r.kinds)
    ]
    return max(matches, default=0.5)


def source_tier(source: str) -> int:
    source_l = source.lower()
    for rule in SOURCE_RULES:
        if rule.name.lower() in source_l or source_l in rule.name.lower():
            return rule.tier
    return 3


def rank_evidence(items: list[dict]) -> list[dict]:
    return sorted(
        items,
        key=lambda x: (source_tier(str(x.get("source", ""))), -float(x.get("confidence", 0))),
    )
