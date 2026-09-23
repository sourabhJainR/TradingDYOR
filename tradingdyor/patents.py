from __future__ import annotations
import os, requests

BASE="https://search.patentsview.org/api/v1/patent/"
FIELDS=["patent_id","patent_title","patent_date","assignees.assignee_organization","inventors.inventor_name_first","inventors.inventor_name_last"]

def search_patents(organization:str,limit:int=25,api_key:str|None=None)->dict:
    key=api_key or os.getenv("PATENTSVIEW_API_KEY")
    if not key: return {"status":"not_configured","organization":organization,"patents":[]}
    query={"_text_phrase":{"assignees.assignee_organization":organization}}
    params={"q":__import__("json").dumps(query),"f":__import__("json").dumps(FIELDS),
            "o":__import__("json").dumps({"size":max(1,min(limit,100))})}
    r=requests.get(BASE,params=params,headers={"X-Api-Key":key},timeout=20)
    r.raise_for_status()
    data=r.json()
    return {"status":"ok","organization":organization,"total_hits":data.get("total_hits",0),"patents":data.get("patents",[])}
