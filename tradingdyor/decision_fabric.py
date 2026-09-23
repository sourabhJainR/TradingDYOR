from __future__ import annotations
from dataclasses import dataclass
from .experience import ExperienceMemory
from .learning import RoutingPolicy

@dataclass(frozen=True)
class FabricPlan:
    capabilities:tuple[str,...]
    verification_depth:float
    retry_budget:int
    branch_budget:int

class DecisionFabric:
    """Adaptive control plane for capability, verification, retry and branch decisions."""
    def __init__(self,policy:RoutingPolicy|None=None,memory:ExperienceMemory|None=None):
        self.policy=policy or RoutingPolicy(); self.memory=memory or ExperienceMemory()

    def _score(self, name: str) -> float:
        policy_score = self.policy.capability_weight[name] + self.policy.branch_value[name]
        history = self.memory.capability_stats().get(name, {})
        observations = history.get("observations", 0)
        if observations < 2:
            return policy_score
        return (
            0.55 * policy_score
            + 1.20 * history.get("success_rate", 0.5)
            + 0.50 * history.get("avg_evidence_yield", 0.0)
            + 0.25 * history.get("avg_branch_value", 0.0)
            - 0.00005 * history.get("avg_duration_ms", 0.0)
            - 0.25 * history.get("avg_retry_count", 0.0)
        )

    def plan(self,capabilities:list[str],required_evidence:float=0.7)->FabricPlan:
        if not capabilities:
            return FabricPlan((), max(0.7, required_evidence), 0, 1)
        ranked=sorted(dict.fromkeys(capabilities),key=self._score,reverse=True)
        chosen=tuple(ranked[:max(2,min(4,len(ranked)))])
        stats=self.memory.capability_stats()
        risk_depth=[]
        retry_pressure=[]
        branch_value=[]
        for name in chosen:
            s=stats.get(name, {})
            risk_depth.append(s.get("avg_verification_depth", self.policy.verification_depth[name]))
            risk_depth.append(1.0 + (1.0 - s.get("success_rate", 0.5)))
            retry_pressure.append(max(self.policy.retry_rate[name], min(1.0, s.get("avg_retry_count", 0.0) / 3.0)))
            branch_value.append(s.get("avg_branch_value", self.policy.branch_value[name]))
        depth=max(required_evidence, min(3.0, max(risk_depth,default=1.0)))
        retry=max(0,min(3,round(sum(retry_pressure))))
        branch=max(1,min(3,round(sum(branch_value) / max(1,len(branch_value)) * 2)))
        return FabricPlan(chosen,depth,retry,branch)

    def capability_recommendation(self,candidates:list[str])->str:
        historical=self.memory.recommend(candidates)
        return historical or self.policy.choose(candidates)

    def select_branches(self, candidates:list[str], budget:int|None=None) -> list[str]:
        """Use historical branch value when enough observations exist; otherwise preserve exploration."""
        if not candidates:
            return []
        limit=budget or min(3,len(candidates))
        stats=self.memory.capability_stats()
        ranked=sorted(
            dict.fromkeys(candidates),
            key=lambda x:(
                stats.get(x,{}).get("observations",0) >= 2,
                self._score(x),
            ),
            reverse=True,
        )
        return ranked[:max(1,min(limit,len(ranked)))]
