"""
KALBI-2 Circuit Breaker -- Hard-Stop Safety System.

The circuit breaker is the last line of defence before a trade reaches the
broker.  It evaluates every proposed trade against a battery of risk
checks -- daily loss limits, position-size limits, portfolio deployment
caps, correlation thresholds, API health, and market-hours volatility
windows.  If any check fails the trade is rejected (or adjusted) and,
in extreme cases, the entire system can be halted.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog

log = structlog.get_logger(__name__)


class CircuitBreaker:
    """Pre-trade risk gate that enforces hard limits.

    The constructor accepts a ``config`` dictionary whose keys mirror the
    risk parameters in ``src.config.Settings``.  Any missing key falls
    back to a conservative default.

    Expected ``config`` keys:
        - ``max_daily_loss_pct`` (*float*) -- default ``5.0``
        - ``max_position_pct`` (*float*) -- default ``2.0``
        - ``max_portfolio_deployed_pct`` (*float*) -- default ``50.0``
        - ``max_correlation`` (*float*) -- default ``0.7``
        - ``max_consecutive_api_failures`` (*int*) -- default ``3``
        - ``volatile_window_minutes`` (*int*) -- default ``15``

    Args:
        config: Risk-parameter dictionary.
    """

    def __init__(self, config: dict) -> None:
        self.max_daily_loss_pct: float = config.get(
            "max_daily_loss_pct", 5.0
        )
        self.max_position_pct: float = config.get(
            "max_position_pct", 2.0
        )
        self.max_deployed_pct: float = config.get(
            "max_portfolio_deployed_pct", 50.0
        )
        self.max_correlation: float = config.get("max_correlation", 0.7)
        self.max_consecutive_api_failures: int = config.get(
            "max_consecutive_api_failures", 3
        )
        self.volatile_window_minutes: int = config.get(
            "volatile_window_minutes", 15
        )

        self._halted: bool = False
        self._halt_reason: Optional[str] = None

        log.info(
            "circuit_breaker.initialized",
            max_daily_loss_pct=self.max_daily_loss_pct,
            max_position_pct=self.max_position_pct,
            max_deployed_pct=self.max_deployed_pct,
            max_correlation=self.max_correlation,
        )

    # ------------------------------------------------------------------
    # Individual checks -- each returns True when the limit is BREACHED
    # ------------------------------------------------------------------

    def check_daily_loss(self, daily_pnl_pct: float) -> bool:
        """Return ``True`` if the daily loss limit has been breached.

        Args:
            daily_pnl_pct: Today's P&L expressed as a signed percentage
                of portfolio value (negative means loss).
        """
        breached = daily_pnl_pct <= -self.max_daily_loss_pct
        if breached:
            log.warning(
                "circuit_breaker.daily_loss_breached",
                daily_pnl_pct=daily_pnl_pct,
                limit=-self.max_daily_loss_pct,
            )
        return breached

    def check_position_size(self, trade_risk_pct: float) -> bool:
        """Return ``True`` if the proposed position is too large.

        Args:
            trade_risk_pct: The proposed trade's risk as a percentage of
                portfolio value.
        """
        breached = trade_risk_pct > self.max_position_pct
        if breached:
            log.warning(
                "circuit_breaker.position_size_breached",
                trade_risk_pct=trade_risk_pct,
                limit=self.max_position_pct,
            )
        return breached

    def check_deployment(self, deployed_pct: float) -> bool:
        """Return ``True`` if the portfolio is over-deployed.

        Args:
            deployed_pct: Percentage of total portfolio currently
                deployed in open positions.
        """
        breached = deployed_pct > self.max_deployed_pct
        if breached:
            log.warning(
                "circuit_breaker.deployment_breached",
                deployed_pct=deployed_pct,
                limit=self.max_deployed_pct,
            )
        return breached

    def check_correlation(self, new_trade_correlation: float) -> bool:
        """Return ``True`` if adding this trade would create excessive
        portfolio correlation.

        Args:
            new_trade_correlation: Estimated average pairwise correlation
                of the portfolio *after* adding the proposed trade.
        """
        breached = new_trade_correlation > self.max_correlation
        if breached:
            log.warning(
                "circuit_breaker.correlation_breached",
                new_trade_correlation=new_trade_correlation,
                limit=self.max_correlation,
            )
        return breached

    def check_api_health(self, consecutive_failures: int) -> bool:
        """Return ``True`` if the API is considered unhealthy.

        The API is deemed unhealthy when there have been 3 or more
        consecutive failures (configurable via
        ``max_consecutive_api_failures``).

        Args:
            consecutive_failures: Number of consecutive API call failures.
        """
        breached = consecutive_failures >= self.max_consecutive_api_failures
        if breached:
            log.warning(
                "circuit_breaker.api_unhealthy",
                consecutive_failures=consecutive_failures,
                limit=self.max_consecutive_api_failures,
            )
        return breached

    def check_market_hours(self) -> bool:
        """Return ``True`` if the current time is within the first or last
        15 minutes of the US equities regular session (09:30-16:00 ET).

        These windows are characterised by elevated volatility and wider
        spreads, making them riskier for systematic entries.

        Note:
            The check uses a simplified UTC offset for US Eastern Time
            (UTC-4 for EDT, UTC-5 for EST).  For production use, consider
            using ``zoneinfo`` or ``pytz`` for accurate DST handling.
        """
        now_utc = datetime.now(timezone.utc)
        # Approximate ET as UTC-4 (EDT).  A production system should use
        # proper timezone handling.
        et_hour = (now_utc.hour - 4) % 24
        et_minute = now_utc.minute

        market_open_min = 9 * 60 + 30   # 09:30 ET in minutes
        market_close_min = 16 * 60       # 16:00 ET in minutes
        current_min = et_hour * 60 + et_minute

        window = self.volatile_window_minutes

        in_open_window = (
            market_open_min <= current_min < market_open_min + window
        )
        in_close_window = (
            market_close_min - window <= current_min < market_close_min
        )

        is_volatile = in_open_window or in_close_window
        if is_volatile:
            log.info(
                "circuit_breaker.volatile_window",
                et_hour=et_hour,
                et_minute=et_minute,
                in_open_window=in_open_window,
                in_close_window=in_close_window,
            )
        return is_volatile

    # ------------------------------------------------------------------
    # Master evaluation
    # ------------------------------------------------------------------

    def evaluate_trade(
        self,
        trade_proposal: dict,
        portfolio_state: dict,
    ) -> dict:
        """Run all circuit-breaker checks against a proposed trade.

        Args:
            trade_proposal: Dictionary describing the proposed trade.
                Expected keys:
                - ``trade_risk_pct`` (*float*) -- risk as % of portfolio.
                - ``estimated_correlation`` (*float*) -- estimated post-
                  trade portfolio correlation.
            portfolio_state: Current portfolio snapshot.  Expected keys:
                - ``daily_pnl_pct`` (*float*) -- today's P&L percentage.
                - ``deployed_pct`` (*float*) -- current deployment %.
                - ``consecutive_api_failures`` (*int*) -- API failure
                  count.

        Returns:
            A dictionary with:
            - **approved** (*bool*) -- ``True`` if the trade passes all
              checks.
            - **rejection_reasons** (*list[str]*) -- human-readable
              reasons for rejection (empty if approved).
            - **adjustments** (*dict*) -- suggested modifications (e.g.
              reduced position size) that *would* make the trade pass.
        """
        if self._halted:
            log.error(
                "circuit_breaker.system_halted",
                halt_reason=self._halt_reason,
            )
            return {
                "approved": False,
                "rejection_reasons": [
                    f"System halted: {self._halt_reason}"
                ],
                "adjustments": {},
            }

        rejection_reasons: list[str] = []
        adjustments: dict = {}

        # ── Extract fields ────────────────────────────────────────────
        trade_risk_pct: float = trade_proposal.get("trade_risk_pct", 0.0)
        estimated_corr: float = trade_proposal.get(
            "estimated_correlation", 0.0
        )
        daily_pnl_pct: float = portfolio_state.get("daily_pnl_pct", 0.0)
        deployed_pct: float = portfolio_state.get("deployed_pct", 0.0)
        api_failures: int = portfolio_state.get(
            "consecutive_api_failures", 0
        )

        # ── Run checks ────────────────────────────────────────────────
        if self.check_daily_loss(daily_pnl_pct):
            rejection_reasons.append(
                f"Daily loss limit breached: {daily_pnl_pct:.2f}% "
                f"(limit: -{self.max_daily_loss_pct:.2f}%)"
            )

        if self.check_position_size(trade_risk_pct):
            rejection_reasons.append(
                f"Position too large: {trade_risk_pct:.2f}% "
                f"(limit: {self.max_position_pct:.2f}%)"
            )
            # Suggest a reduced size.
            adjustments["suggested_risk_pct"] = self.max_position_pct * 0.9

        if self.check_deployment(deployed_pct + trade_risk_pct):
            rejection_reasons.append(
                f"Would exceed deployment cap: "
                f"{deployed_pct + trade_risk_pct:.2f}% "
                f"(limit: {self.max_deployed_pct:.2f}%)"
            )
            remaining = max(self.max_deployed_pct - deployed_pct, 0.0)
            adjustments["max_additional_deployment_pct"] = round(
                remaining, 2
            )

        if self.check_correlation(estimated_corr):
            rejection_reasons.append(
                f"Portfolio correlation too high: {estimated_corr:.2f} "
                f"(limit: {self.max_correlation:.2f})"
            )

        if self.check_api_health(api_failures):
            rejection_reasons.append(
                f"API unhealthy: {api_failures} consecutive failures "
                f"(limit: {self.max_consecutive_api_failures})"
            )

        if self.check_market_hours():
            rejection_reasons.append(
                "Trade proposed during volatile market open/close window"
            )
            adjustments["delay_minutes"] = self.volatile_window_minutes

        approved = len(rejection_reasons) == 0

        result = {
            "approved": approved,
            "rejection_reasons": rejection_reasons,
            "adjustments": adjustments,
        }

        if approved:
            log.info(
                "circuit_breaker.trade_approved",
                trade_risk_pct=trade_risk_pct,
            )
        else:
            log.warning(
                "circuit_breaker.trade_rejected",
                reasons=rejection_reasons,
                adjustments=adjustments,
            )

        return result

    # ------------------------------------------------------------------
    # Emergency halt
    # ------------------------------------------------------------------

    def trigger_shutdown(self, reason: str) -> None:
        """Halt all trading activity.

        Once triggered the circuit breaker will reject *every* subsequent
        trade proposal until the system is manually restarted.

        Args:
            reason: Human-readable explanation of why the shutdown was
                triggered (persisted in logs).
        """
        self._halted = True
        self._halt_reason = reason
        log.critical(
            "circuit_breaker.SHUTDOWN_TRIGGERED",
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def is_halted(self) -> bool:
        """Return ``True`` if the system has been halted."""
        return self._halted

    @property
    def halt_reason(self) -> Optional[str]:
        """Return the reason for the current halt, or ``None``."""
        return self._halt_reason
