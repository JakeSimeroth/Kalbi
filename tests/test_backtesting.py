"""
Tests for the KALBI-2 backtesting metrics engine.

Validates Sharpe ratio, max drawdown, win rate, and other performance
metrics against known inputs.
"""

import pytest
import numpy as np

from src.backtesting.metrics import BacktestMetrics


# ---------------------------------------------------------------------------
# Sharpe ratio
# ---------------------------------------------------------------------------


def test_sharpe_ratio():
    """Sharpe ratio should return a float for a valid return series."""
    returns = [0.01, -0.005, 0.02, 0.003, -0.01, 0.015]
    result = BacktestMetrics.sharpe_ratio(returns)
    assert isinstance(result, float)


def test_sharpe_ratio_insufficient_data():
    """Sharpe ratio should return 0.0 for fewer than 2 returns."""
    assert BacktestMetrics.sharpe_ratio([]) == 0.0
    assert BacktestMetrics.sharpe_ratio([0.01]) == 0.0


def test_sharpe_ratio_zero_std():
    """Sharpe ratio should return 0.0 when all returns are identical."""
    returns = [0.01, 0.01, 0.01, 0.01]
    result = BacktestMetrics.sharpe_ratio(returns)
    assert result == 0.0


def test_sharpe_ratio_positive_for_good_returns():
    """A consistently positive return series should produce a positive Sharpe."""
    returns = [0.02, 0.015, 0.018, 0.022, 0.019, 0.021]
    result = BacktestMetrics.sharpe_ratio(returns, risk_free_rate=0.02)
    assert result > 0.0


# ---------------------------------------------------------------------------
# Max drawdown
# ---------------------------------------------------------------------------


def test_max_drawdown():
    """Max drawdown should be negative and duration should be positive."""
    equity_curve = [
        {"equity": 100},
        {"equity": 105},
        {"equity": 103},
        {"equity": 98},
        {"equity": 95},
        {"equity": 100},
        {"equity": 102},
    ]
    dd, duration = BacktestMetrics.max_drawdown(equity_curve)
    assert dd < 0  # drawdown is negative
    assert duration > 0


def test_max_drawdown_empty():
    """Max drawdown of an empty equity curve should be (0.0, 0)."""
    dd, duration = BacktestMetrics.max_drawdown([])
    assert dd == 0.0
    assert duration == 0


def test_max_drawdown_monotonic_increase():
    """A monotonically increasing equity curve should have zero drawdown."""
    equity_curve = [{"equity": v} for v in [100, 101, 102, 103, 104]]
    dd, duration = BacktestMetrics.max_drawdown(equity_curve)
    assert dd == 0.0


def test_max_drawdown_magnitude():
    """Verify drawdown calculation for a known peak-to-trough scenario."""
    equity_curve = [
        {"equity": 100},
        {"equity": 110},  # peak
        {"equity": 88},   # trough: (88-110)/110 = -0.2
        {"equity": 95},
    ]
    dd, duration = BacktestMetrics.max_drawdown(equity_curve)
    assert dd == pytest.approx(-0.2, abs=0.001)


# ---------------------------------------------------------------------------
# Win rate
# ---------------------------------------------------------------------------


def test_win_rate_no_trades():
    """Win rate with no trades should return 0.0."""
    result = BacktestMetrics.win_rate([])
    assert result == 0.0


def test_win_rate_all_winners():
    """Win rate should be 1.0 when all round-trip trades are profitable."""
    trades = [
        {"action": "buy", "price": 100, "quantity": 10, "commission": 0},
        {"action": "sell", "price": 110, "quantity": 10, "commission": 0},
        {"action": "buy", "price": 100, "quantity": 10, "commission": 0},
        {"action": "sell", "price": 105, "quantity": 10, "commission": 0},
    ]
    result = BacktestMetrics.win_rate(trades)
    assert result == 1.0


def test_win_rate_mixed():
    """Win rate should reflect the proportion of winning round-trips."""
    trades = [
        {"action": "buy", "price": 100, "quantity": 10, "commission": 0},
        {"action": "sell", "price": 110, "quantity": 10, "commission": 0},  # win
        {"action": "buy", "price": 100, "quantity": 10, "commission": 0},
        {"action": "sell", "price": 90, "quantity": 10, "commission": 0},   # loss
    ]
    result = BacktestMetrics.win_rate(trades)
    assert result == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Profit factor
# ---------------------------------------------------------------------------


def test_profit_factor_no_trades():
    """Profit factor with no trades should return 0.0."""
    result = BacktestMetrics.profit_factor([])
    assert result == 0.0


def test_profit_factor_no_losers():
    """Profit factor with only winners should return inf."""
    trades = [
        {"action": "buy", "price": 100, "quantity": 10, "commission": 0},
        {"action": "sell", "price": 120, "quantity": 10, "commission": 0},
    ]
    result = BacktestMetrics.profit_factor(trades)
    assert result == float("inf")


def test_profit_factor_calculation():
    """Profit factor should equal gross_wins / gross_losses."""
    trades = [
        {"action": "buy", "price": 100, "quantity": 10, "commission": 0},
        {"action": "sell", "price": 120, "quantity": 10, "commission": 0},  # +200
        {"action": "buy", "price": 100, "quantity": 10, "commission": 0},
        {"action": "sell", "price": 90, "quantity": 10, "commission": 0},   # -100
    ]
    result = BacktestMetrics.profit_factor(trades)
    assert result == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Sortino ratio
# ---------------------------------------------------------------------------


def test_sortino_ratio():
    """Sortino ratio should return a float for a valid return series."""
    returns = [0.01, -0.005, 0.02, 0.003, -0.01, 0.015]
    result = BacktestMetrics.sortino_ratio(returns)
    assert isinstance(result, float)


def test_sortino_ratio_insufficient_data():
    """Sortino ratio should return 0.0 for fewer than 2 returns."""
    assert BacktestMetrics.sortino_ratio([]) == 0.0
    assert BacktestMetrics.sortino_ratio([0.01]) == 0.0


# ---------------------------------------------------------------------------
# calculate_all integration
# ---------------------------------------------------------------------------


def test_calculate_all_returns_all_keys():
    """calculate_all should return a dict with all expected metric keys."""
    equity_curve = [{"equity": v} for v in [100, 102, 101, 103, 105, 104, 107]]
    trades = [
        {"action": "buy", "price": 100, "quantity": 10, "commission": 0},
        {"action": "sell", "price": 107, "quantity": 10, "commission": 0},
    ]
    result = BacktestMetrics.calculate_all(equity_curve, trades)

    expected_keys = [
        "total_return",
        "annual_return",
        "sharpe_ratio",
        "sortino_ratio",
        "max_drawdown",
        "max_drawdown_duration",
        "win_rate",
        "profit_factor",
        "avg_win",
        "avg_loss",
        "total_trades",
        "avg_trade_duration",
        "calmar_ratio",
    ]
    for key in expected_keys:
        assert key in result, f"Missing key: {key}"
