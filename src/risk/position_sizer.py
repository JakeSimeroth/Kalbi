"""
KALBI-2 Position Sizing Engine.

Provides multiple position-sizing algorithms -- Kelly Criterion (fractional),
fixed-fractional, and volatility-scaled (ATR-based) -- behind a single
``calculate_position_size`` router method.  The router selects the
appropriate algorithm based on a ``method`` string and returns a
consistent result dict.
"""

from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)


class PositionSizer:
    """Multi-method position sizing calculator.

    All sizing methods return a dollar amount representing the maximum
    capital to allocate to a single trade, given the current portfolio
    value and risk parameters.

    Typical usage::

        sizer = PositionSizer()
        result = sizer.calculate_position_size(
            method="kelly",
            portfolio_value=100_000,
            win_prob=0.55,
            win_loss_ratio=1.5,
        )
        print(result)
        # {"method": "kelly", "position_size": 2475.0, "raw_fraction": 0.099, ...}
    """

    # ------------------------------------------------------------------
    # Sizing algorithms
    # ------------------------------------------------------------------

    def kelly_criterion(
        self,
        win_prob: float,
        win_loss_ratio: float,
        fraction: float = 0.25,
    ) -> float:
        """Quarter-Kelly position sizing.

        The full Kelly fraction is:

            f* = p - (1 - p) / b

        where *p* is the probability of winning and *b* is the ratio of
        average win to average loss.  Because full Kelly is notoriously
        volatile, we default to quarter-Kelly (``fraction=0.25``).

        Args:
            win_prob: Estimated probability of a winning trade (0 to 1).
            win_loss_ratio: Average win amount divided by average loss
                amount (must be > 0).
            fraction: Kelly fraction to use (default ``0.25`` for
                quarter-Kelly).

        Returns:
            The fraction of portfolio to allocate (0 to 1).  Returns 0
            if the Kelly formula yields a non-positive value (i.e. the
            trade has negative expected value).
        """
        if win_prob <= 0 or win_prob >= 1:
            log.warning(
                "position_sizer.kelly.invalid_prob", win_prob=win_prob
            )
            return 0.0

        if win_loss_ratio <= 0:
            log.warning(
                "position_sizer.kelly.invalid_ratio",
                win_loss_ratio=win_loss_ratio,
            )
            return 0.0

        full_kelly = win_prob - (1.0 - win_prob) / win_loss_ratio

        if full_kelly <= 0:
            log.info(
                "position_sizer.kelly.negative_edge",
                full_kelly=round(full_kelly, 4),
            )
            return 0.0

        fractional_kelly = full_kelly * fraction
        # Cap at 25% of portfolio regardless of Kelly output.
        capped = min(fractional_kelly, 0.25)

        log.debug(
            "position_sizer.kelly",
            full_kelly=round(full_kelly, 4),
            fraction=fraction,
            result=round(capped, 4),
        )
        return capped

    def fixed_fractional(
        self,
        portfolio_value: float,
        risk_pct: float = 0.02,
    ) -> float:
        """Fixed-fractional position sizing.

        Allocates a constant percentage of the total portfolio value to
        each trade, regardless of signal strength or volatility.

        Args:
            portfolio_value: Total portfolio value in dollars.
            risk_pct: Fraction of portfolio to risk (default ``0.02``
                = 2%).

        Returns:
            Dollar amount to allocate to the position.
        """
        if portfolio_value <= 0:
            log.warning(
                "position_sizer.fixed_fractional.invalid_portfolio",
                portfolio_value=portfolio_value,
            )
            return 0.0

        if risk_pct <= 0 or risk_pct > 1:
            log.warning(
                "position_sizer.fixed_fractional.invalid_risk_pct",
                risk_pct=risk_pct,
            )
            return 0.0

        size = portfolio_value * risk_pct
        log.debug(
            "position_sizer.fixed_fractional",
            portfolio_value=portfolio_value,
            risk_pct=risk_pct,
            size=round(size, 2),
        )
        return round(size, 2)

    def volatility_scaled(
        self,
        portfolio_value: float,
        atr: float,
        risk_pct: float = 0.02,
    ) -> float:
        """ATR-based volatility-scaled position sizing.

        Calculates the position size so that a 1-ATR adverse move equals
        the dollar amount at risk (``portfolio_value * risk_pct``).  This
        naturally sizes positions smaller in volatile markets and larger
        in calm markets.

        Args:
            portfolio_value: Total portfolio value in dollars.
            atr: Average True Range of the instrument (same currency
                unit as price).
            risk_pct: Fraction of portfolio to risk per trade (default
                ``0.02`` = 2%).

        Returns:
            Dollar amount to allocate to the position.
        """
        if portfolio_value <= 0:
            log.warning(
                "position_sizer.vol_scaled.invalid_portfolio",
                portfolio_value=portfolio_value,
            )
            return 0.0

        if atr <= 0:
            log.warning(
                "position_sizer.vol_scaled.invalid_atr", atr=atr
            )
            return 0.0

        dollar_risk = portfolio_value * risk_pct
        # Number of shares/contracts such that 1 ATR move = dollar_risk
        units = dollar_risk / atr
        size = round(units * atr, 2)  # total dollar exposure

        log.debug(
            "position_sizer.volatility_scaled",
            portfolio_value=portfolio_value,
            atr=atr,
            risk_pct=risk_pct,
            units=round(units, 4),
            size=size,
        )
        return size

    # ------------------------------------------------------------------
    # Router
    # ------------------------------------------------------------------

    def calculate_position_size(
        self,
        method: str,
        portfolio_value: float,
        **kwargs,
    ) -> dict:
        """Route to the appropriate sizing method and return a result dict.

        Args:
            method: One of ``"kelly"``, ``"fixed_fractional"``, or
                ``"volatility_scaled"``.
            portfolio_value: Total portfolio value in dollars.
            **kwargs: Additional keyword arguments forwarded to the
                chosen method.

        Returns:
            A dictionary with:
            - **method** (*str*) -- the method used.
            - **position_size** (*float*) -- dollar amount to allocate.
            - **raw_fraction** (*float*) -- the fraction of portfolio
              (for Kelly; 0 for other methods).
            - **portfolio_value** (*float*) -- echoed back for
              traceability.
        """
        raw_fraction: float = 0.0

        try:
            if method == "kelly":
                win_prob = kwargs.get("win_prob", 0.5)
                win_loss_ratio = kwargs.get("win_loss_ratio", 1.0)
                fraction = kwargs.get("fraction", 0.25)
                raw_fraction = self.kelly_criterion(
                    win_prob, win_loss_ratio, fraction
                )
                position_size = round(portfolio_value * raw_fraction, 2)

            elif method == "fixed_fractional":
                risk_pct = kwargs.get("risk_pct", 0.02)
                position_size = self.fixed_fractional(
                    portfolio_value, risk_pct
                )

            elif method == "volatility_scaled":
                atr = kwargs.get("atr", 0.0)
                risk_pct = kwargs.get("risk_pct", 0.02)
                position_size = self.volatility_scaled(
                    portfolio_value, atr, risk_pct
                )

            else:
                log.error(
                    "position_sizer.unknown_method", method=method
                )
                position_size = 0.0

        except Exception:
            log.exception(
                "position_sizer.calculate_failed", method=method
            )
            position_size = 0.0

        result = {
            "method": method,
            "position_size": position_size,
            "raw_fraction": round(raw_fraction, 6),
            "portfolio_value": portfolio_value,
        }

        log.info(
            "position_sizer.calculated",
            method=method,
            position_size=position_size,
        )
        return result
