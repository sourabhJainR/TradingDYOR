from datetime import datetime, timezone

def reassess(decisions, realized_returns):
    scored=[]
    for d in decisions:
        r=realized_returns.get(d["ticker"])
        scored.append({
            "ticker":d["ticker"],
            "action":d["action"],
            "realized_return":r,
            "correct_direction": None if r is None else (
                (d["action"]=="BUY" and r>0) or
                (d["action"]=="SELL" and r<0) or
                (d["action"]=="HOLD" and abs(r)<0.10)
            )
        })
    return {"as_of":datetime.now(timezone.utc).isoformat(),"results":scored}

if __name__=="__main__":
    print("Monthly reassessment requires point-in-time decisions and realized forward returns.")
