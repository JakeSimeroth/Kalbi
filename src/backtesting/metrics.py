"""
KALBI-2 Backtest Performance Metrics.

Provides static methods for computing standard quantitative finance
metrics from an equity curve and a list of trade records produced by
:class:`BacktestEngine`.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import structlog

log = structlog.get_logger(__name__)

# Assumed number of trading days per year (US equities convention).
_TRADING_DAYS_PER_YEAR: int = 252


class BacktestMetrics:
    """Static utility class for backtest performance analytics."""

    # ------------------------------------------------------------------
    # Comprehensive report
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_all(
        equity_curve: list[dict],
        trades: list[dict],
        risk_free_rate: float = 0.05,
    ) -> dict:
        """Calculate a comprehensive set of backtest metrics.

        Args:
            equity_curve: List of dicts as produced by
                :meth:`BacktestEngine.run`.  Each dict must contain at
                least an ``equity`` key.
            trades: List of trade-record dicts from the engine.
            risk_free_rate: Annualised risk-free rate used for
                Sharpe / Sortino calculations (default 5 %).

        Returns:
            A dictionary with the following keys:

            - ``total_return`` (*float*) -- cumulative return fraction
            - ``annual_return`` (*float*) -- annualised return fraction
            - ``sharpe_ratio`` (*float*)
            - ``sortino_ratio`` (*float*)
            - ``max_drawdown`` (*float*) -- maximum drawdown fraction
            - ``max_drawdown_duration`` (*int*) -- bars in deepest DD
            - ``win_rate`` (*float*) -- fraction (0-1)
            - ``profit_factor`` (*float*)
            - ``avg_win`` (*float*) -- average winning trade P&L
            - ``avg_loss`` (*float*) -- average losing trade P&L
            - ``total_trades`` (*int*)
            - ``avg_trade_duration`` (*float*) -- average bars between
              entry and exit (estimated)
            - ``calmar_ratio`` (*float*)
        """
        equities = [e["equity"] for e in equity_curve] if equity_curve else []
        returns = BacktestMetrics._equity_to_returns(equities)

        total_return = BacktestMetrics._total_return(equities)
        n_bars = len(equities)
        annual_return = BacktestMetrics._annualise_return(
            total_return, n_bars
        )

        dd, dd_dur = BacktestMetrics.max_drawdown(equity_curve)

        sr = BacktestMetrics.sharpe_ratio(returns, risk_free_rate)
        so = BacktestMetrics.sortino_ratio(returns, risk_free_rate)
        wr = BacktestMetrics.win_rate(trades)
        pf = BacktestMetrics.profit_factor(trades)

        avg_w, avg_l = BacktestMetrics._avg_win_loss(trades)
        avg_dur = BacktestMetrics._avg_trade_duration(trades)

        calmar = (
            annual_return / abs(dd) if dd != 0.0 else float("inf")
        )

        metrics = {
            "total_return": round(total_return, 6),
            "annual_return": round(annual_return, 6),
            "sharpe_ratio": round(sr, 4),
            "sortino_ratio": round(so, 4),
            "max_drawdown": round(dd, 6),
            "max_drawdown_duration": dd_dur,
            "win_rate": round(wr, 4),
            "profit_factor": round(pf, 4),
            "avg_win": round(avg_w, 4),
            "avg_loss": round(avg_l, 4),
            "total_trades": len(trades),
            "avg_trade_duration": round(avg_dur, 2),
            "calmar_ratio": round(calmar, 4),
        }

        log.info("backtest_metrics.calculated", **metrics)
        return metrics

    # ------------------------------------------------------------------
    # Individual metrics
    # ------------------------------------------------------------------

    @staticmethod
    def sharpe_ratio(
        returns: list[float],
        risk_free_rate: float = 0.05,
    ) -> float:
        """Compute the annualised Sharpe ratio.

        Args:
            returns: List of per-bar simple returns.
            risk_free_rate: Annualised risk-free rate.

        Returns:
            The Sharpe ratio, or ``0.0`` if there are fewer than two
            returns or standard deviation is zero.
        """
        if len(returns) < 2:
            return 0.0
        arr = np.array(returns, dtype=np.float64)
        daily_rf = risk_free_rate / _TRADING_DAYS_PER_YEAR
        excess = arr - daily_rf
        std = float(np.std(excess, ddof=1))
        if std == 0.0:
            return 0.0
        return float(np.mean(excess)) / std * math.sqrt(
            _TRADING_DAYS_PER_YEAR
        )

    @staticmethod
    def sortino_ratio(
        returns: list[float],
        risk_free_rate: float = 0.05,
    ) -> float:
        """Compute the annualised Sortino ratio.

        Only downside deviation (returns below the daily risk-free rate)
        is used in the denominator.

        Args:
            returns: List of per-bar simple returns.
            risk_free_rate: Annualised risk-free rate.

        Returns:
            The Sortino ratio, or ``0.0`` if there is insufficient data
            or no downside deviation.
        """
        if len(returns) < 2:
            return 0.0
        arr = np.array(returns, dtype=np.float64)
        daily_rf = risk_free_rate / _TRADING_DAYS_PER_YEAR
        excess = arr - daily_rf
        downside = excess[excess < 0.0]
        if len(downside) == 0:
            return float("inf") if float(np.mean(excess)) > 0 else 0.0
        downside_std = float(np.std(downside, ddof=1))
        if downside_std == 0.0:
            return 0.0
        return float(np.mean(excess)) / downside_std * math.sqrt(
            _TRADING_DAYS_PER_YEAR
        )

    @staticmethod
    def max_drawdown(equity_curve: list[dict]) -> tuple[float, int]:
        """Compute the maximum drawdown and its duration in bars.

        Args:
            equity_curve: List of dicts each containing an ``equity``
                key.

        Returns:
            A tuple ``(max_drawdown_pct, max_drawdown_duration_bars)``.
            ``max_drawdown_pct`` is expressed as a negative fraction
            (e.g. ``-0.15`` for a 15 % drawdown).  Duration is the
            number of bars the deepest drawdown persisted.
        """
        if not equity_curve:
            return 0.0, 0

        equities = [e["equity"] for e in equity_curve]
        peak = equities[0]
        max_dd = 0.0
        max_dd_duration = 0
        current_dd_start: Optional[int] = None

        for i, eq in enumerate(equities):
            if eq >= peak:
                peak = eq
                current_dd_start = None
            else:
                dd = (eq - peak) / peak
                if dd < max_dd:
                    max_dd = dd
                    if current_dd_start is None:
                        current_dd_start = i
                    max_dd_duration = i - current_dd_start + 1
                elif current_dd_start is None:
                    current_dd_start = i

        return max_dd, max_dd_duration

    @staticmethod
    def win_rate(trades: list[dict]) -> float:
        """Compute the fraction of winning trades.

        A trade is considered a *win* if the ``action`` is ``"sell"``
        and the trade record indicates positive P&L (inferred from
        sequential cash changes), or more simply if we can pair
        buy/sell trades.  As a pragmatic shortcut, this implementation
        counts sell trades with ``cash_after`` greater than the
        preceding buy's ``cash_after`` as wins.

        Args:
            trades: List of trade-record dicts from the engine.

        Returns:
            Win rate as a float between 0.0 and 1.0, or ``0.0`` if
            there are no completed round-trips.
        """
        round_trips = BacktestMetrics._extract_round_trips(trades)
        if not round_trips:
            return 0.0
        wins = sum(1 for rt in round_trips if rt["pnl"] > 0)
        return wins / len(round_trips)

    @staticmethod
    def profit_factor(trades: list[dict]) -> float:
        """Compute the profit factor (gross wins / gross losses).

        Args:
            trades: List of trade-record dicts from the engine.

        Returns:
            The profit factor.  Returns ``float('inf')`` if there are
            no losing trades and ``0.0`` if there are no trades.
        """
        round_trips = BacktestMetrics._extract_round_trips(trades)
        if not round_trips:
            return 0.0

        gross_wins = sum(rt["pnl"] for rt in round_trips if rt["pnl"] > 0)
        gross_losses = abs(
            sum(rt["pnl"] for rt in round_trips if rt["pnl"] < 0)
        )

        if gross_losses == 0.0:
            return float("inf") if gross_wins > 0 else 0.0
        return gross_wins / gross_losses

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _equity_to_returns(equities: list[float]) -> list[float]:
        """Convert an equity series to simple per-bar returns."""
        if len(equities) < 2:
            return []
        returns = []
        for i in range(1, len(equities)):
            prev = equities[i - 1]
            if prev == 0.0:
                returns.append(0.0)
            else:
                returns.append((equities[i] - prev) / prev)
        return returns

    @staticmethod
    def _total_return(equities: list[float]) -> float:
        """Compute the total cumulative return from an equity series."""
        if len(equities) < 2 or equities[0] == 0.0:
            return 0.0
        return (equities[-1] - equities[0]) / equities[0]

    @staticmethod
    def _annualise_return(
        total_return: float, n_bars: int
    ) -> float:
        """Annualise a total return assuming daily bars."""
        if n_bars <= 1:
            return 0.0
        years = n_bars / _TRADING_DAYS_PER_YEAR
        if years == 0.0:
            return 0.0
        # Handle negative total returns gracefully.
        if total_return <= -1.0:
            return -1.0
        return (1.0 + total_return) ** (1.0 / years) - 1.0

    @staticmethod
    def _extract_round_trips(trades: list[dict]) -> list[dict]:
        """Pair sequential buy/sell trades into round-trip records.

        Each round-trip dict contains:
            - ``entry_price`` (*float*)
            - ``exit_price`` (*float*)
            - ``quantity`` (*float*)
            - ``pnl`` (*float*) -- profit or loss (after commission)
            - ``entry_time`` -- timestamp of the buy
            - ``exit_time`` -- timestamp of the sell

        Args:
            trades: Flat list of trade records from the engine.

        Returns:
            A list of round-trip dictionaries.
        """
        round_trips: list[dict] = []
        pending_buy: Optional[dict] = None

        for trade in trades:
            action = trade.get("action", "")
            if action == "buy":
                pending_buy = trade
            elif action == "sell" and pending_buy is not None:
                qty = min(
                    pending_buy.get("quantity", 0),
                    trade.get("quantity", 0),
                )
                entry_price = pending_buy.get("price", 0.0)
                exit_price = trade.get("price", 0.0)
                entry_commission = pending_buy.get("commission", 0.0)
                exit_commission = trade.get("commission", 0.0)

                pnl = (
                    (exit_price - entry_price) * qty
                    - entry_commission
                    - exit_commission
                )

                round_trips.append(
                    {
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "quantity": qty,
                        "pnl": pnl,
                        "entry_time": pending_buy.get("timestamp"),
                        "exit_time": trade.get("timestamp"),
                    }
                )
                pending_buy = None

        return round_trips

    @staticmethod
    def _avg_win_loss(
        trades: list[dict],
    ) -> tuple[float, float]:
        """Compute the average winning and losing trade P&L.

        Returns:
            A tuple ``(avg_win, avg_loss)``.  Both are ``0.0`` if there
            are no trades in the respective bucket.
        """
        round_trips = BacktestMetrics._extract_round_trips(trades)
        wins = [rt["pnl"] for rt in round_trips if rt["pnl"] > 0]
        losses = [rt["pnl"] for rt in round_trips if rt["pnl"] < 0]

        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = float(np.mean(losses)) if losses else 0.0
        return avg_win, avg_loss

    @staticmethod
    def _avg_trade_duration(trades: list[dict]) -> float:
        """Estimate the average number of bars between entry and exit.

        This is a coarse estimate based on the index position of the
        timestamps in the trade list.  If timestamps are not ordinal
        indices, returns ``0.0``.

        Returns:
            Average duration in bars, or ``0.0`` if not computable.
        """
        round_trips = BacktestMetrics._extract_round_trips(trades)
        if not round_trips:
            return 0.0

        durations: list[float] = []
        for rt in round_trips:
            entry_t = rt.get("entry_time")
            exit_t = rt.get("exit_time")
            if entry_t is not None and exit_t is not None:
                try:
                    delta = exit_t - entry_t
                    durations.append(delta.days if hasattr(delta, "days") else 0)
                except Exception:
                    pass

        return float(np.mean(durations)) if durations else 0.0
