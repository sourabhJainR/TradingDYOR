from tradingdyor.macro import classify_regime
from tradingdyor.sector import SectorState, sector_score
def test_macro_regime_is_bounded():
    r=classify_regime(.1,.15,.03); assert r.name=="risk-on" and -1<=r.score<=1
def test_sector_score():
    assert sector_score(SectorState("Technology",.1,.2,.2,.8,"trend"))>0
