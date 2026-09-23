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
    """Small gated memory: cold-start observations do not override the policy by themselves."""
    def __init__(self, path: str | Path = ".tradingdyor/experience.json", max_records: int = 5000):
        self.path = Path(path)
        self.max_records = max(100, max_records)
        self.records: list[Experience] = []
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            self.records = [Experience(**x) for x in json.loads(self.path.read_text())][-self.max_records:]
        except (OSError, ValueError, TypeError):
            self.records = []

    def record(self, experience: Experience) -> None:
        if not experience.capability or experience.duration_ms < 0:
            return
        row = Experience(
            capability=experience.capability,
            success=bool(experience.success),
            duration_ms=float(max(0.0, experience.duration_ms)),
            evidence_yield=float(max(0.0, min(1.0, experience.evidence_yield))),
            verification_depth=float(max(0.25, min(3.0, experience.verification_depth))),
            retry_count=max(0, int(experience.retry_count)),
            branch_value=float(max(0.0, min(3.0, experience.branch_value))),
        )
        self.records.append(row)
        self.records = self.records[-self.max_records:]
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

    def utility(self, name: str) -> float:
        s = self.capability_stats().get(name, {})
        if s.get("observations", 0) < 2:
            return 0.0
        return (
            2.0 * s.get("success_rate", 0.5)
            + 0.5 * s.get("avg_evidence_yield", 0.0)
            + 0.25 * s.get("avg_branch_value", 0.0)
            - 0.0001 * s.get("avg_duration_ms", 0.0)
            - 0.25 * s.get("avg_retry_count", 0.0)
        )

    def recommend(self, candidates: list[str]) -> str:
        if not candidates:
            return ""
        stats = self.capability_stats()
        experienced = [x for x in candidates if stats.get(x, {}).get("observations", 0) >= 2]
        if not experienced:
            return ""
        return max(experienced, key=self.utility)
