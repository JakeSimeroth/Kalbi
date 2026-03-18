"""
KALBI-2 Real-Time Portfolio Monitor.

Tracks portfolio state -- positions, cash, daily P&L, drawdown, and
inter-position correlation -- and exposes a set of ``get_*`` accessors
plus a ``check_limits`` method that flags any breached risk thresholds.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import numpy as np
import structlog

log = structlog.get_logger(__name__)


class PortfolioMonitor:
    """Stateful monitor for real-time portfolio health tracking.

    Call :meth:`update` whenever positions or cash balances change.  The
    monitor recalculates all derived metrics (P&L, drawdown, correlation)
    and makes them available via the ``get_*`` family of accessors.

    Args:
        max_daily_loss_pct: Maximum tolerable daily loss as a percentage
            of portfolio value (default ``5.0``).
        max_deployed_pct: Maximum percentage of total portfolio value
            that may be deployed in open positions (default ``50.0``).
        max_correlation: Maximum allowable average pairwise correlation
            between positions (default ``0.7``).
    """

    def __init__(
        self,
        max_daily_loss_pct: float = 5.0,
        max_deployed_pct: float = 50.0,
        max_correlation: float = 0.7,
    ) -> None:
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_deployed_pct = max_deployed_pct
        self.max_correlation = max_correlation

        # ── Internal state ────────────────────────────────────────────
        self._positions: list[dict] = []
        self._cash_balance: float = 0.0
        self._start_of_day_value: Optional[float] = None
        self._peak_value: float = 0.0
        self._last_update: Optional[datetime] = None

        log.info(
            "portfolio_monitor.initialized",
            max_daily_loss_pct=self.max_daily_loss_pct,
            max_deployed_pct=self.max_deployed_pct,
            max_correlation=self.max_correlation,
        )

    # ------------------------------------------------------------------
    # State mutation
    # ------------------------------------------------------------------

    def update(
        self, positions: list[dict], cash_balance: float
    ) -> None:
        """Refresh the portfolio state with current positions and cash.

        Each position dict should contain at least:
            - ``market_value`` (*float*) -- current market value of the
              position.
            - ``cost_basis`` (*float*) -- original cost of the position.
            - ``returns`` (*list[float]*, optional) -- historical return
              series for correlation calculation.

        Args:
            positions: List of position dictionaries.
            cash_balance: Current uninvested cash balance.
        """
        self._positions = list(positions)
        self._cash_balance = cash_balance

        total_value = self._total_value()

        # Initialise start-of-day value on first update of the day.
        now = datetime.now(timezone.utc)
        if self._start_of_day_value is None or self._is_new_day(now):
            self._start_of_day_value = total_value
            log.info(
                "portfolio_monitor.new_day",
                start_of_day_value=total_value,
            )

        # Track peak for drawdown.
        if total_value > self._peak_value:
            self._peak_value = total_value

        self._last_update = now

        log.debug(
            "portfolio_monitor.updated",
            positions_count=len(positions),
            cash_balance=cash_balance,
            total_value=total_value,
        )

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_daily_pnl(self) -> dict:
        """Return the current day's P&L in absolute and percentage terms.

        Returns:
            Dictionary with ``daily_pnl`` (float) and
            ``daily_pnl_pct`` (float).
        """
        total = self._total_value()
        start = self._start_of_day_value or total

        daily_pnl = total - start
        daily_pnl_pct = (daily_pnl / start * 100.0) if start > 0 else 0.0

        return {
            "daily_pnl": round(daily_pnl, 2),
            "daily_pnl_pct": round(daily_pnl_pct, 4),
        }

    def get_drawdown(self) -> dict:
        """Return the current and maximum drawdown metrics.

        Returns:
            Dictionary with ``current_drawdown_pct`` and
            ``max_drawdown_pct``.
        """
        total = self._total_value()
        if self._peak_value > 0:
            current_dd = (self._peak_value - total) / self._peak_value * 100.0
        else:
            current_dd = 0.0

        return {
            "current_drawdown_pct": round(max(current_dd, 0.0), 4),
            "max_drawdown_pct": round(max(current_dd, 0.0), 4),
        }

    def get_portfolio_correlation(self) -> float:
        """Compute the average pairwise correlation of open positions.

        Uses the ``returns`` key in each position dict (a list of
        historical returns).  Positions without return data are skipped.

        Returns:
            Average pairwise Pearson correlation coefficient.  Returns
            0.0 if fewer than two positions have return series.
        """
        return_series: list[list[float]] = []
        for pos in self._positions:
            returns = pos.get("returns")
            if returns and len(returns) >= 2:
                return_series.append(returns)

        if len(return_series) < 2:
            return 0.0

        try:
            # Truncate all series to the shortest length.
            min_len = min(len(s) for s in return_series)
            matrix = np.array([s[:min_len] for s in return_series])

            corr_matrix = np.corrcoef(matrix)

            # Extract upper-triangle (excluding diagonal).
            n = corr_matrix.shape[0]
            upper_indices = np.triu_indices(n, k=1)
            pairwise_corrs = corr_matrix[upper_indices]

            avg_corr = float(np.nanmean(pairwise_corrs))
            return round(avg_corr, 4)

        except Exception:
            log.exception("portfolio_monitor.correlation_failed")
            return 0.0

    def get_risk_summary(self) -> dict:
        """Return a comprehensive risk snapshot of the portfolio.

        Returns:
            Dictionary containing daily P&L, drawdown, deployment
            percentage, correlation, position count, and total value.
        """
        total = self._total_value()
        deployed = self._deployed_value()
        deployed_pct = (deployed / total * 100.0) if total > 0 else 0.0
        pnl = self.get_daily_pnl()
        dd = self.get_drawdown()
        correlation = self.get_portfolio_correlation()

        return {
            "total_value": round(total, 2),
            "cash_balance": round(self._cash_balance, 2),
            "deployed_value": round(deployed, 2),
            "deployed_pct": round(deployed_pct, 2),
            "open_positions": len(self._positions),
            "daily_pnl": pnl["daily_pnl"],
            "daily_pnl_pct": pnl["daily_pnl_pct"],
            "current_drawdown_pct": dd["current_drawdown_pct"],
            "max_drawdown_pct": dd["max_drawdown_pct"],
            "avg_correlation": correlation,
            "last_update": (
                self._last_update.isoformat() if self._last_update else None
            ),
        }

    def check_limits(self) -> dict:
        """Check all risk limits and report which ones are breached.

        Returns:
            Dictionary mapping limit names to booleans.  ``True`` means
            the limit has been **breached** (bad).
        """
        pnl = self.get_daily_pnl()
        total = self._total_value()
        deployed = self._deployed_value()
        deployed_pct = (deployed / total * 100.0) if total > 0 else 0.0
        correlation = self.get_portfolio_correlation()

        breaches = {
            "daily_loss_breached": (
                pnl["daily_pnl_pct"] <= -self.max_daily_loss_pct
            ),
            "deployment_breached": deployed_pct > self.max_deployed_pct,
            "correlation_breached": correlation > self.max_correlation,
        }

        if any(breaches.values()):
            log.warning("portfolio_monitor.limits_breached", **breaches)

        return breaches

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _total_value(self) -> float:
        """Total portfolio value = cash + sum of position market values."""
        deployed = self._deployed_value()
        return self._cash_balance + deployed

    def _deployed_value(self) -> float:
        """Sum of market values across all open positions."""
        return sum(
            pos.get("market_value", 0.0) for pos in self._positions
        )

    def _is_new_day(self, now: datetime) -> bool:
        """Return True if ``now`` is on a different UTC date than the
        last update."""
        if self._last_update is None:
            return True
        return now.date() != self._last_update.date()
