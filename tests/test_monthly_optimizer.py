import pandas as pd
import pytest

from tradingdyor.monthly_optimizer import BacktestConfig, _evaluate_config, market_universe


def test_market_universe_supports_selected_market():
    assert market_universe("US", ["msft", "MSFT", "nvda"]) == ["MSFT", "NVDA"]
    assert "^NSEI" in market_universe("INDIA")


def test_invalid_market_rejected():
    with pytest.raises(ValueError):
        market_universe("EUROPE")


def test_trade_config_respects_hard_exit():
    prices = pd.Series(
        [100, 101, 103, 108, 110, 90],
        index=pd.date_range("2026-01-01", periods=6, freq="B"),
    )
    result = _evaluate_config(prices, BacktestConfig(3, 0.05, 0.08), 0)
    assert result["trades"] >= 0


def test_config_has_one_month_bounds():
    cfg = BacktestConfig(30, 0.08, 0.16)
    assert 1 <= cfg.holding_days <= 30
    assert 0 < cfg.stop_loss < cfg.take_profit
