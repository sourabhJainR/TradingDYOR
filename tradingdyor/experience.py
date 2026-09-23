from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json


@dataclass(frozen=True)
class Experience:
    capability: str
    success: bool
    duration_ms: float
    evidence_yield: float
    verification_depth: float
    retry_count: int
    branch_value: float = 0.0


class ExperienceMemory:
    def __init__(self, path: str | Path = ".tradingdyor/experience.json"):
        self.path = Path(path)
        self.records: list[Experience] = []
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            self.records = [Experience(**x) for x in json.loads(self.path.read_text())]
        except (OSError, ValueError, TypeError):
            self.records = []

    def record(self, experience: Experience) -> None:
        self.records.append(experience)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([asdict(x) for x in self.records], indent=2))

    def capability_stats(self) -> dict[str, dict[str, float]]:
        grouped: dict[str, list[Experience]] = {}
        for row in self.records:
            grouped.setdefault(row.capability, []).append(row)
        return {
            key: {
                "success_rate": sum(x.success for x in rows) / len(rows),
                "avg_duration_ms": sum(x.duration_ms for x in rows) / len(rows),
                "avg_evidence_yield": sum(x.evidence_yield for x in rows) / len(rows),
                "avg_verification_depth": sum(x.verification_depth for x in rows) / len(rows),
                "avg_retry_count": sum(x.retry_count for x in rows) / len(rows),
                "avg_branch_value": sum(x.branch_value for x in rows) / len(rows),
                "observations": float(len(rows)),
            }
            for key, rows in grouped.items()
        }

    def recommend(self, candidates: list[str]) -> str:
        stats = self.capability_stats()
        if not candidates:
            return ""
        def utility(name: str) -> float:
            s = stats.get(name, {})
            return (
                2.0 * s.get("success_rate", 0.5)
                + 0.5 * s.get("avg_evidence_yield", 0.0)
                + 0.25 * s.get("avg_branch_value", 0.0)
                - 0.0001 * s.get("avg_duration_ms", 0.0)
                - 0.25 * s.get("avg_retry_count", 0.0)
            )
        return max(candidates, key=utility)
