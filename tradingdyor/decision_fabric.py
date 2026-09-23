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
    def __init__(self,policy:RoutingPolicy|None=None,memory:ExperienceMemory|None=None):
        self.policy=policy or RoutingPolicy(); self.memory=memory or ExperienceMemory()
    def plan(self,capabilities:list[str],required_evidence:float=0.7)->FabricPlan:
        chosen=self.policy.evidence_plan(capabilities,minimum=2)
        depth=max(required_evidence, max((self.policy.verification_depth[x] for x in chosen),default=1.0))
        retry=max(0,min(3,round(sum(self.policy.retry_rate[x] for x in chosen))))
        branch=max(1,min(3,round(sum(self.policy.branch_value[x] for x in chosen))))
        return FabricPlan(tuple(chosen),depth,retry,branch)
    def capability_recommendation(self,candidates:list[str])->str:
        return self.memory.recommend(candidates) if self.memory.records else self.policy.choose(candidates)
