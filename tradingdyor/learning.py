from dataclasses import dataclass, field
from pathlib import Path
import json

@dataclass
class RoutingPolicy:
    capability_weight: dict[str,float] = field(default_factory=lambda: {})
    verification_depth: dict[str,float] = field(default_factory=lambda: {})
    retry_rate: dict[str,float] = field(default_factory=lambda: {})
    branch_value: dict[str,float] = field(default_factory=lambda: {})

    @classmethod
    def load(cls, path: str | Path = ".tradingdyor/policy.json"):
        p=Path(path); policy=cls()
        try:
            data=json.loads(p.read_text())
            for name in ("capability_weight","verification_depth","retry_rate","branch_value"):
                setattr(policy,name,{k:float(v) for k,v in data.get(name,{}).items()})
        except (OSError,ValueError,TypeError):
            pass
        return policy

    def save(self, path: str | Path = ".tradingdyor/policy.json"):
        p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(self.snapshot(),indent=2))

    def _get(self, table, key, default):
        if key not in table: table[key] = default
        return table[key]

    def update(self, capability: str, success: bool, evidence_yield: float, realized_return: float | None = None):
        reward=(1.0 if success else -1.0)+0.5*evidence_yield
        if realized_return is not None: reward+=max(-1.0,min(1.0,realized_return))
        old=self._get(self.capability_weight, capability, 1.0)
        self.capability_weight[capability]=max(0.1,min(3.0,0.9*old+0.1*(1+reward)))
        depth=self._get(self.verification_depth, capability, 1.0)
        self.verification_depth[capability]=max(0.25,min(3.0,0.95*depth+0.05*(1+abs(reward))))
        retry=self._get(self.retry_rate, capability, 0.0)
        self.retry_rate[capability]=min(1.0,retry+0.05) if not success else max(0.0,retry-0.02)

    def learn_outcome(self, outcome, episode):
        signal = outcome.realized_return
        success = outcome.directional_hit is not False
        for capability in episode.capabilities:
            self.update(capability, success, 0.0, signal)
        for strategy, contribution in outcome.attribution.get("strategies", {}).items():
            old=self._get(self.branch_value, f"strategy:{strategy}", 1.0)
            self.branch_value[f"strategy:{strategy}"]=max(0.1,min(3.0,0.9*old+0.1*(1+contribution)))
        for source, contribution in outcome.attribution.get("sources", {}).items():
            old=self._get(self.branch_value, f"source:{source}", 1.0)
            self.branch_value[f"source:{source}"]=max(0.1,min(3.0,0.9*old+0.1*(1+contribution)))
        # Verification depth is recalibrated only from resolved outcomes.
        depth=episode.verification_depth
        outcome_quality=1.0 if outcome.directional_hit else -1.0 if outcome.directional_hit is False else 0.0
        target=max(0.25,min(3.0,depth + 0.25 * (-outcome_quality + outcome.risk_breached)))
        for capability in episode.capabilities:
            current=self._get(self.verification_depth, capability, depth)
            self.verification_depth[capability]=max(0.25,min(3.0,0.8*current+0.2*target))

    def choose(self,candidates:list[str])->str:
        return max(candidates,key=lambda x:self._get(self.capability_weight,x,1.0)) if candidates else ""

    def evidence_plan(self,candidates:list[str],minimum:int=2)->list[str]:
        if not candidates: return []
        ranked=sorted(candidates,key=lambda x:self._get(self.capability_weight,x,1.0)+self._get(self.branch_value,x,1.0),reverse=True)
        return ranked[:max(minimum,min(len(candidates),4))]

    def snapshot(self):
        return {"capability_weight":dict(self.capability_weight),"verification_depth":dict(self.verification_depth),
                "retry_rate":dict(self.retry_rate),"branch_value":dict(self.branch_value)}
