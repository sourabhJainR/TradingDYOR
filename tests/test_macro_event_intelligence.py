from datetime import datetime, timezone

from tradingdyor.advance_tax import from_official_observation, tax_calendar, AdvanceTaxMemory
from tradingdyor.event_intelligence import build_forecast
from tradingdyor.regime_intelligence import EventMemory, regime_multiplier


def test_event_forecast_is_time_bound_and_persisted(tmp_path):
    memory = EventMemory(tmp_path / "events.json")
    event = build_forecast(
        "macro", "FOMC", "2026-10-28T18:00:00+00:00",
        1, 0.9, 0.7, -0.4, "official-calendar",
    )
    memory.record_forecast(event)
    observed = memory.record_observation(
        event.event_id, "2026-10-29T18:00:00+00:00", -0.03, 0.8
    )
    assert observed.timing_error_days == 1.0
    assert observed.market_reaction == -0.03
    assert memory.calibration()["observations"] == 1


def test_regime_risk_changes_signal_without_zeroing_it():
    from tradingdyor.regime_intelligence import RegimeState
    crisis = RegimeState("crisis", -0.8, 0.4, -0.3, -0.1, 0.9, 0.9, ())
    assert 0.0 < regime_multiplier(crisis, "BUY") < 1.0


def test_advance_tax_signal_and_calendar(tmp_path):
    signal = from_official_observation("2026-Q2", 100.0, 12.0, 14.0, 8.0)
    assert signal["interpretation"] == "corporate-profit-tax momentum positive"
    assert tax_calendar(2026)[1]["date"] == "2026-09-15"
    memory = AdvanceTaxMemory(str(tmp_path / "tax.json"))
    memory.record(signal)
    assert memory.latest()["corporate_growth"] == 14.0
