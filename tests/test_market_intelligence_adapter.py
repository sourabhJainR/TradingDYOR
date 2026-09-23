from tradingdyor.earnings import EarningsObservation, earnings_signal
from tradingdyor.insiders import normalize_insider_rows, insider_signal


def test_directional_insider_signal():
    rows = normalize_insider_rows("NVDA", [
        {"filing_date": "2026-09-01", "insider": "A", "transaction_code": "P", "shares": 100},
        {"filing_date": "2026-09-02", "insider": "B", "transaction_code": "S", "shares": 40},
    ])
    signal = insider_signal(rows)
    assert signal["net_shares"] == 60
    assert signal["buy_sell_ratio"] == 2.5


def test_earnings_signal():
    rows = [
        EarningsObservation("NVDA", "2026-06-01", 1.2, 1.0, 20),
        EarningsObservation("NVDA", "2026-03-01", 0.9, 1.0, -10),
    ]
    signal = earnings_signal(rows)
    assert signal["avg_surprise_pct"] == 5
    assert signal["positive_rate"] == 0.5
