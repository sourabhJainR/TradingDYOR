from __future__ import annotations
from dataclasses import dataclass
from copy import deepcopy
from .decision import decide
from .models import SecuritySnapshot

@dataclass(frozen=True)
class Branch:
    name: str
    action: str
    score: float
    confidence: float
    changed: dict[str, float]

def evaluate_branches(snapshot: SecuritySnapshot, changes: dict[str, dict[str, float]]) -> list[Branch]:
    base = decide(snapshot)
    out = [Branch("base", base.action, base.score, base.confidence, {})]
    for name, patch in changes.items():
        data = deepcopy(snapshot.__dict__); data.update(patch)
        d = decide(SecuritySnapshot(**data))
        out.append(Branch(name, d.action, d.score, d.confidence, patch))
    return out
