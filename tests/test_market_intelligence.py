from tradingdyor.insiders import normalize_insider_rows, insider_signal
from tradingdyor.earnings import EarningsObservation, earnings_signal
from tradingdyor.corporate_actions import normalize_actions
from tradingdyor.sector import SectorState, sector_score

def test_insider_and_earnings_signals():
    rows=normalize_insider_rows("NVDA",[{"filing_date":"2026-01-01","insider":"A","shares":100,"price":10,"transaction_code":"P"},{"filing_date":"2026-01-02","insider":"B","shares":40,"price":11,"transaction_code":"S"}])
    assert insider_signal(rows)["net_shares"]==60
    e=[EarningsObservation("NVDA","Q1",10,9,11),EarningsObservation("NVDA","Q2",10,10,-2)]
    assert earnings_signal(e)["positive_rate"]==0.5

def test_actions_and_sector_score():
    a=normalize_actions([{"ticker":"NVDA","event_date":"2026-01-01","kind":"split","ratio":10}])
    assert a[0].ratio==10
    assert sector_score(SectorState("AI",.1,.2,.1,.8,"risk-on"))>.0
