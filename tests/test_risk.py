"""
Tests for the KALBI-2 risk management components.

Covers PositionSizer, CircuitBreaker, and PortfolioMonitor with import
checks and behavioral tests against known inputs.
"""

import pytest


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------


def test_position_sizer_import():
    """PositionSizer should be importable from src.risk."""
    from src.risk.position_sizer import PositionSizer

    assert PositionSizer is not None


def test_circuit_breaker_import():
    """CircuitBreaker should be importable from src.risk."""
    from src.risk.circuit_breaker import CircuitBreaker

    assert CircuitBreaker is not None


def test_portfolio_monitor_import():
    """PortfolioMonitor should be importable from src.risk."""
    from src.risk.portfolio_monitor import PortfolioMonitor

    assert PortfolioMonitor is not None


# ---------------------------------------------------------------------------
# PositionSizer tests
# ---------------------------------------------------------------------------


def test_kelly_criterion_positive_edge():
    """Kelly should return a positive fraction for a trade with positive EV."""
    from src.risk.position_sizer import PositionSizer

    sizer = PositionSizer()
    result = sizer.kelly_criterion(win_prob=0.6, win_loss_ratio=1.5)
    assert result > 0.0
    assert result <= 0.25  # capped at 25%


def test_kelly_criterion_negative_edge():
    """Kelly should return 0 for a trade with negative expected value."""
    from src.risk.position_sizer import PositionSizer

    sizer = PositionSizer()
    result = sizer.kelly_criterion(win_prob=0.3, win_loss_ratio=0.5)
    assert result == 0.0


def test_kelly_criterion_invalid_prob():
    """Kelly should return 0 for invalid probability values."""
    from src.risk.position_sizer import PositionSizer

    sizer = PositionSizer()
    assert sizer.kelly_criterion(win_prob=0.0, win_loss_ratio=1.5) == 0.0
    assert sizer.kelly_criterion(win_prob=1.0, win_loss_ratio=1.5) == 0.0


def test_fixed_fractional_sizing():
    """Fixed fractional should return portfolio_value * risk_pct."""
    from src.risk.position_sizer import PositionSizer

    sizer = PositionSizer()
    result = sizer.fixed_fractional(portfolio_value=100_000, risk_pct=0.02)
    assert result == 2000.0


def test_fixed_fractional_zero_portfolio():
    """Fixed fractional should return 0 for a zero-value portfolio."""
    from src.risk.position_sizer import PositionSizer

    sizer = PositionSizer()
    result = sizer.fixed_fractional(portfolio_value=0, risk_pct=0.02)
    assert result == 0.0


def test_volatility_scaled_sizing():
    """Volatility-scaled sizing should return a positive value for valid inputs."""
    from src.risk.position_sizer import PositionSizer

    sizer = PositionSizer()
    result = sizer.volatility_scaled(
        portfolio_value=100_000, atr=2.5, risk_pct=0.02
    )
    assert result > 0.0


def test_calculate_position_size_router():
    """The router method should delegate to the correct algorithm."""
    from src.risk.position_sizer import PositionSizer

    sizer = PositionSizer()

    result = sizer.calculate_position_size(
        method="kelly",
        portfolio_value=100_000,
        win_prob=0.6,
        win_loss_ratio=1.5,
    )
    assert result["method"] == "kelly"
    assert result["position_size"] > 0
    assert result["portfolio_value"] == 100_000

    result = sizer.calculate_position_size(
        method="fixed_fractional",
        portfolio_value=100_000,
    )
    assert result["method"] == "fixed_fractional"
    assert result["position_size"] == 2000.0


def test_calculate_position_size_unknown_method():
    """Unknown method should return position_size of 0."""
    from src.risk.position_sizer import PositionSizer

    sizer = PositionSizer()
    result = sizer.calculate_position_size(
        method="nonexistent", portfolio_value=100_000
    )
    assert result["position_size"] == 0.0


# ---------------------------------------------------------------------------
# CircuitBreaker tests
# ---------------------------------------------------------------------------


def test_circuit_breaker_initialization():
    """CircuitBreaker should initialize with config values."""
    from src.risk.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker({"max_daily_loss_pct": 10.0, "max_position_pct": 3.0})
    assert cb.max_daily_loss_pct == 10.0
    assert cb.max_position_pct == 3.0
    assert not cb.is_halted


def test_circuit_breaker_defaults():
    """CircuitBreaker should use conservative defaults for missing config keys."""
    from src.risk.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker({})
    assert cb.max_daily_loss_pct == 5.0
    assert cb.max_position_pct == 2.0
    assert cb.max_deployed_pct == 50.0
    assert cb.max_correlation == 0.7


def test_circuit_breaker_approves_safe_trade():
    """A trade within all limits should be approved."""
    from src.risk.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker({})
    result = cb.evaluate_trade(
        trade_proposal={"trade_risk_pct": 1.0, "estimated_correlation": 0.3},
        portfolio_state={
            "daily_pnl_pct": -1.0,
            "deployed_pct": 20.0,
            "consecutive_api_failures": 0,
        },
    )
    assert result["approved"] is True
    assert len(result["rejection_reasons"]) == 0


def test_circuit_breaker_rejects_oversized_trade():
    """A trade exceeding position size limit should be rejected."""
    from src.risk.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker({"max_position_pct": 2.0})
    result = cb.evaluate_trade(
        trade_proposal={"trade_risk_pct": 5.0, "estimated_correlation": 0.3},
        portfolio_state={
            "daily_pnl_pct": 0.0,
            "deployed_pct": 10.0,
            "consecutive_api_failures": 0,
        },
    )
    assert result["approved"] is False
    assert any("Position too large" in r for r in result["rejection_reasons"])


def test_circuit_breaker_rejects_daily_loss_breach():
    """A trade should be rejected when daily loss limit is breached."""
    from src.risk.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker({"max_daily_loss_pct": 5.0})
    result = cb.evaluate_trade(
        trade_proposal={"trade_risk_pct": 1.0, "estimated_correlation": 0.3},
        portfolio_state={
            "daily_pnl_pct": -6.0,
            "deployed_pct": 10.0,
            "consecutive_api_failures": 0,
        },
    )
    assert result["approved"] is False
    assert any("Daily loss" in r for r in result["rejection_reasons"])


def test_circuit_breaker_shutdown():
    """After trigger_shutdown(), all trades should be rejected."""
    from src.risk.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker({})
    cb.trigger_shutdown("Test emergency")
    assert cb.is_halted is True
    assert cb.halt_reason == "Test emergency"

    result = cb.evaluate_trade(
        trade_proposal={"trade_risk_pct": 0.5, "estimated_correlation": 0.1},
        portfolio_state={
            "daily_pnl_pct": 0.0,
            "deployed_pct": 5.0,
            "consecutive_api_failures": 0,
        },
    )
    assert result["approved"] is False
    assert any("halted" in r.lower() for r in result["rejection_reasons"])


# ---------------------------------------------------------------------------
# PortfolioMonitor tests
# ---------------------------------------------------------------------------


def test_portfolio_monitor_initialization():
    """PortfolioMonitor should initialize with default parameters."""
    from src.risk.portfolio_monitor import PortfolioMonitor

    monitor = PortfolioMonitor()
    assert monitor.max_daily_loss_pct == 5.0
    assert monitor.max_deployed_pct == 50.0
    assert monitor.max_correlation == 0.7


def test_portfolio_monitor_update_and_summary():
    """After update(), get_risk_summary() should reflect the new state."""
    from src.risk.portfolio_monitor import PortfolioMonitor

    monitor = PortfolioMonitor()
    positions = [
        {"market_value": 3000.0, "cost_basis": 2800.0},
        {"market_value": 2000.0, "cost_basis": 2100.0},
    ]
    monitor.update(positions=positions, cash_balance=5000.0)

    summary = monitor.get_risk_summary()
    assert summary["total_value"] == 10000.0
    assert summary["cash_balance"] == 5000.0
    assert summary["deployed_value"] == 5000.0
    assert summary["open_positions"] == 2


def test_portfolio_monitor_check_limits_clean():
    """check_limits() should show no breaches for a healthy portfolio."""
    from src.risk.portfolio_monitor import PortfolioMonitor

    monitor = PortfolioMonitor()
    positions = [{"market_value": 2000.0, "cost_basis": 2000.0}]
    monitor.update(positions=positions, cash_balance=8000.0)

    breaches = monitor.check_limits()
    assert breaches["daily_loss_breached"] is False
    assert breaches["deployment_breached"] is False
    assert breaches["correlation_breached"] is False
