from dataclasses import dataclass, field
from collections import defaultdict

@dataclass
class RoutingPolicy:
    capability_weight: dict[str,float] = field(default_factory=lambda: defaultdict(lambda: 1.0))
    verification_depth: dict[str,float] = field(default_factory=lambda: defaultdict(lambda: 1.0))
    retry_rate: dict[str,float] = field(default_factory=lambda: defaultdict(lambda: 0.0))
    branch_value: dict[str,float] = field(default_factory=lambda: defaultdict(lambda: 1.0))

    def update(self, capability: str, success: bool, evidence_yield: float, realized_return: float | None = None):
        reward=(1.0 if success else -1.0)+0.5*evidence_yield
        if realized_return is not None: reward+=max(-1.0,min(1.0,realized_return))
        old=self.capability_weight[capability]
        self.capability_weight[capability]=max(0.1,min(3.0,0.9*old+0.1*(1+reward)))
        self.verification_depth[capability]=max(0.25,min(3.0,0.95*self.verification_depth[capability]+0.05*(1+abs(reward))))
        self.retry_rate[capability]=min(1.0,self.retry_rate[capability]+0.05) if not success else max(0.0,self.retry_rate[capability]-0.02)

    def choose(self,candidates:list[str])->str:
        return max(candidates,key=lambda x:self.capability_weight[x]) if candidates else ""

    def evidence_plan(self,candidates:list[str],minimum:int=2)->list[str]:
        if not candidates: return []
        ranked=sorted(candidates,key=lambda x:self.capability_weight[x]+self.branch_value[x],reverse=True)
        return ranked[:max(minimum,min(len(candidates),4))]

    def snapshot(self):
        return {"capability_weight":dict(self.capability_weight),"verification_depth":dict(self.verification_depth),
                "retry_rate":dict(self.retry_rate),"branch_value":dict(self.branch_value)}
