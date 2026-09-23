from tradingdyor.models import SecuritySnapshot
from tradingdyor.decision import decide

def test_low_evidence_is_hold():
    d=decide(SecuritySnapshot(ticker="TEST",evidence_coverage=0.1))
    assert d.action=="HOLD"

def test_good_growth_can_generate_signal():
    s=SecuritySnapshot(ticker="TEST",revenue_growth=.40,earnings_growth=.50,roe=.30,
                       pe=18,debt_to_equity=.2,momentum_12m=.30,volatility_90d=.20,
                       evidence_coverage=.9)
    assert decide(s).action in {"BUY","HOLD"}
