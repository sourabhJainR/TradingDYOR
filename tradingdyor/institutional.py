from __future__ import annotations
from dataclasses import dataclass, asdict
import re, xml.etree.ElementTree as ET
import requests
from .flows import InstitutionalFlow, normalize_flow_rows
SEC_HEADERS={"User-Agent":"TradingDYOR research/0.6 contact@example.com"}
@dataclass(frozen=True)
class InstitutionalPosition:
    manager_cik:str; manager:str; filing_date:str; period:str; issuer:str; cusip:str
    value_thousands:float; shares:float; share_type:str; put_call:str|None; source_url:str
def _archive(cik,accession,doc): return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-','')}/{doc}"
def recent_13f_filings(manager_cik:str,limit:int=4)->list[dict]:
    cik=str(manager_cik).zfill(10); data=requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",headers=SEC_HEADERS,timeout=20).json()
    r=data.get("filings",{}).get("recent",{}); out=[]
    for i,form in enumerate(r.get("form",[])):
        if form not in {"13F-HR","13F-HR/A"}: continue
        out.append({"filing_date":r["filingDate"][i],"period":r.get("reportDate",[None]*len(r["form"]))[i],"accession":r["accessionNumber"][i],"document":r["primaryDocument"][i]})
        if len(out)>=limit: break
    return out
def parse_13f(manager_cik:str,limit:int=4)->list[InstitutionalPosition]:
    out=[]
    for f in recent_13f_filings(manager_cik,limit):
        base=_archive(manager_cik,f["accession"],"").rsplit("/",1)[0]+"/"
        try:
            index=requests.get(base+f["accession"]+"-index.html",headers=SEC_HEADERS,timeout=20).text
            docs=re.findall(r'href="([^"]+\.xml)"',index,re.I); xml_docs=[d for d in docs if "primary" not in d.lower()] or docs
            if not xml_docs: continue
            xml_url=base+xml_docs[-1]; root=ET.fromstring(requests.get(xml_url,headers=SEC_HEADERS,timeout=20).content)
            for node in root.iter():
                if not node.tag.lower().endswith("infotable"): continue
                def val(name):
                    x=node.find(f".//{{*}}{name}"); return (x.text or "").strip() if x is not None else ""
                out.append(InstitutionalPosition(str(manager_cik),"",f["filing_date"],f["period"] or "",val("nameOfIssuer"),val("cusip"),float(val("value") or 0),float(val("sshPrnamt") or 0),val("sshPrnamtType"),val("putCall") or None,xml_url))
        except (requests.RequestException,ET.ParseError,ValueError): continue
    return out
def ticker_flow_from_positions(ticker,positions):
    return normalize_flow_rows(ticker,[{"filing_date":p.filing_date,"holder":p.manager or p.manager_cik,"shares":p.shares,"value":p.value_thousands*1000} for p in positions])
def summarize_positions(positions):
    return {"observations":len(positions),"total_reported_value":sum(p.value_thousands*1000 for p in positions),"unique_cusips":len({p.cusip for p in positions}),"latest_filing":max((p.filing_date for p in positions),default=None),"positions":[asdict(p) for p in positions[:200]]}
