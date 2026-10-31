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


def test_india_regime_uses_india_index_and_volatility_index(monkeypatch):
    import pandas as pd
    from tradingdyor.regime_intelligence import classify_market_regime
    calls = []
    prices = pd.Series([100.0 + i * 0.1 for i in range(260)])
    volatility = pd.Series([20.0 for _ in range(260)])

    def fake_series(ticker, period):
        calls.append(ticker)
        return volatility if ticker == "^INDIAVIX" else prices

    monkeypatch.setattr("tradingdyor.regime_intelligence._series", fake_series)
    result = classify_market_regime("INDIA")
    assert result.name in {"normal", "expansion", "slowdown", "high-stress", "crisis"}
    assert calls == ["^NSEI", "^INDIAVIX"]


def test_company_event_pressure_is_ticker_scoped(tmp_path):
    from datetime import datetime, timedelta, timezone
    from tradingdyor.event_intelligence import event_pressure

    memory = EventMemory(tmp_path / "events.json")
    expected = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    memory.record_forecast(build_forecast("company", "NVDA", expected, 2, 1.0, 1.0, 0.5, "official"))
    memory.record_forecast(build_forecast("company", "MU", expected, 2, 1.0, 1.0, 0.5, "official"))
    assert event_pressure(memory, "NVDA") == 1.0
    assert event_pressure(memory, "MU") == 1.0
    assert event_pressure(memory, "AMD") == 0.0


def test_macro_market_validation_rejects_unknown_market():
    from tradingdyor.macro_intelligence import macro_state
    import pytest
    with pytest.raises(ValueError):
        macro_state("EUROPE")


def test_event_forecast_rejects_naive_time_and_malformed_metric_links():
    import pytest
    with pytest.raises(ValueError, match="explicit timezone"):
        build_forecast("company", "ABC", "2026-11-01T12:00:00", 1, 0.5, 0.5, 0.0, "issuer")
    with pytest.raises(ValueError, match="must be a list"):
        build_forecast("company", "ABC", "2026-11-01T12:00:00+00:00", 1, 0.5, 0.5, 0.0, "issuer", "revenue_growth")


def test_corrupt_event_memory_is_unavailable_and_not_overwritten(tmp_path):
    import pytest
    path = tmp_path / "corrupt-events.json"
    original = b"{not-json"
    path.write_bytes(original)
    memory = EventMemory(path)
    assert memory.load_status == "unavailable"
    with pytest.raises(RuntimeError):
        memory.record_forecast(build_forecast(
            "company", "ABC", "2026-11-01T12:00:00+00:00", 1, 0.5, 0.5, 0.0, "issuer",
        ))
    assert path.read_bytes() == original
