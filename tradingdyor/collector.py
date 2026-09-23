import json, subprocess
from .sources import SOURCES
from .models import Evidence
from .store import save_evidence

def collect_source(source, node="node", runner="agents/src/runner.js"):
    p=subprocess.run([node,runner,"--url",source.url],capture_output=True,text=True,timeout=60)
    if p.returncode:
        raise RuntimeError(p.stderr[-1000:])
    data=json.loads(p.stdout)
    evidence=Evidence(
      source=source.name,url=source.url,title=data.get("title",""),
      excerpt=data.get("excerpt",""),confidence=0.60,
      extraction_method=data.get("extraction_method","browser")
    )
    save_evidence(evidence)
    return evidence

def collect_all(limit=None):
    results=[]
    for source in SOURCES[:limit]:
        try:
            results.append(collect_source(source))
        except Exception as exc:
            results.append({"source":source.name,"url":source.url,"error":str(exc)})
    return results
