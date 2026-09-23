from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256

@dataclass(frozen=True)
class EvidenceNode:
    kind:str
    source:str
    url:str
    available_at:str
    observed_at:str|None
    confidence:float
    relevance:float
    content_hash:str

class EvidenceGraph:
    def __init__(self): self.nodes:list[EvidenceNode]=[]
    def add(self,kind,source,url,available_at,content,observed_at=None,confidence=0.5,relevance=0.5):
        digest=sha256(content.strip().encode()).hexdigest()
        if any(n.content_hash==digest for n in self.nodes): return False
        self.nodes.append(EvidenceNode(kind,source,url,available_at,observed_at,max(0,min(1,confidence)),max(0,min(1,relevance)),digest))
        return True
    def coverage(self)->float:
        if not self.nodes: return 0.0
        return sum(n.confidence*n.relevance for n in self.nodes)/len(self.nodes)
    def by_kind(self)->dict[str,int]:
        out={}
        for n in self.nodes: out[n.kind]=out.get(n.kind,0)+1
        return out
    def snapshot(self): return {"count":len(self.nodes),"coverage":self.coverage(),"by_kind":self.by_kind()}
