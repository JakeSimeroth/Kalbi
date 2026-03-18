"""
KALBI-2 Equities Mean Reversion Strategy.

Identifies oversold and overbought conditions by combining Bollinger Band
extremes with RSI readings.  When price moves outside the Bollinger Bands
and RSI confirms the extreme, the strategy signals a mean-reversion entry
expecting price to snap back toward the moving average.
"""

from __future__ import annotations

import numpy as np
import structlog

log = structlog.get_logger(__name__)


class MeanReversionStrategy:
    """Bollinger Band + RSI mean-reversion strategy for equities.

    Signal logic:
        1. **Bollinger Band breach** -- Price closes below the lower band
           (oversold) or above the upper band (overbought).
        2. **RSI extreme** -- RSI below 30 confirms oversold; above 70
           confirms overbought.
        3. **Entry** -- When both conditions agree, the strategy enters
           in the opposite direction expecting a reversion to the mean
           (the middle Bollinger Band / SMA).

    Args:
        bollinger_period: Look-back period for the Bollinger Band SMA
            (default ``20``).
        std_dev: Number of standard deviations for the upper/lower bands
            (default ``2.0``).
    """

    def __init__(
        self,
        bollinger_period: int = 20,
        std_dev: float = 2.0,
    ) -> None:
        self.bollinger_period = bollinger_period
        self.std_dev = std_dev
        log.info(
            "mean_reversion_strategy.initialized",
            bollinger_period=self.bollinger_period,
            std_dev=self.std_dev,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_signal(
        self, ohlcv_data: dict, indicators: dict
    ) -> dict:
        """Produce a mean-reversion trading signal for a single equity.

        Args:
            ohlcv_data: Dictionary with at least:
                - ``ticker`` (*str*)
                - ``close`` (*float*) -- most recent closing price
                - ``atr`` (*float*, optional) -- Average True Range
            indicators: Pre-computed indicator values.  Expected keys:
                - ``bb_upper`` (*float*) -- upper Bollinger Band
                - ``bb_middle`` (*float*) -- middle band (SMA)
                - ``bb_lower`` (*float*) -- lower Bollinger Band
                - ``rsi_14`` (*float*) -- 14-period RSI
                - ``bb_bandwidth`` (*float*, optional) -- bandwidth for
                  volatility filtering

        Returns:
            Signal dictionary with keys: ``ticker``, ``direction``
            (``"long"``/``"short"``/``"hold"``), ``strength`` (0-1),
            ``entry_price``, ``stop_loss``, ``take_profit``.
        """
        ticker: str = ohlcv_data.get("ticker", "UNKNOWN")
        close: float = ohlcv_data.get("close", 0.0)
        atr: float = ohlcv_data.get("atr", close * 0.02)

        try:
            bb_upper: float = indicators.get("bb_upper", close)
            bb_middle: float = indicators.get("bb_middle", close)
            bb_lower: float = indicators.get("bb_lower", close)
            rsi: float = indicators.get("rsi_14", 50.0)

            # ── Detect extremes ───────────────────────────────────────
            bb_position = self._bollinger_position(
                close, bb_upper, bb_middle, bb_lower
            )
            rsi_extreme = self._rsi_extreme(rsi)

            # ── Confluence scoring ────────────────────────────────────
            direction = "hold"
            strength = 0.0

            # Oversold: price below lower band AND RSI < 30
            if bb_position == -1 and rsi_extreme == -1:
                direction = "long"  # buy expecting reversion upward
                # Strength based on how far outside the band + RSI depth
                band_penetration = self._band_penetration(
                    close, bb_lower, bb_middle
                )
                rsi_depth = (30.0 - rsi) / 30.0  # deeper = stronger
                strength = min(
                    0.5 * band_penetration + 0.5 * max(rsi_depth, 0.0), 1.0
                )

            # Overbought: price above upper band AND RSI > 70
            elif bb_position == 1 and rsi_extreme == 1:
                direction = "short"  # sell expecting reversion downward
                band_penetration = self._band_penetration(
                    close, bb_upper, bb_middle
                )
                rsi_depth = (rsi - 70.0) / 30.0
                strength = min(
                    0.5 * band_penetration + 0.5 * max(rsi_depth, 0.0), 1.0
                )

            # Partial confirmation: only one condition met
            elif bb_position == -1 or rsi_extreme == -1:
                direction = "long"
                strength = 0.3  # weak signal
            elif bb_position == 1 or rsi_extreme == 1:
                direction = "short"
                strength = 0.3

            # ── Price levels (target = middle band / mean) ────────────
            stop_loss, take_profit = self._compute_levels(
                close, atr, bb_middle, direction
            )

            signal = {
                "ticker": ticker,
                "direction": direction,
                "strength": round(strength, 4),
                "entry_price": close,
                "stop_loss": round(stop_loss, 4),
                "take_profit": round(take_profit, 4),
            }

            log.info(
                "mean_reversion_strategy.signal",
                ticker=ticker,
                direction=direction,
                strength=round(strength, 4),
                bb_position=bb_position,
                rsi=round(rsi, 2),
            )
            return signal

        except Exception:
            log.exception(
                "mean_reversion_strategy.generate_signal_failed",
                ticker=ticker,
            )
            return {
                "ticker": ticker,
                "direction": "hold",
                "strength": 0.0,
                "entry_price": close,
                "stop_loss": close,
                "take_profit": close,
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _bollinger_position(
        close: float,
        bb_upper: float,
        bb_middle: float,
        bb_lower: float,
    ) -> int:
        """Classify price position relative to Bollinger Bands.

        Returns:
            +1 if price is above the upper band (overbought),
            -1 if below the lower band (oversold),
             0 if within the bands.
        """
        if close > bb_upper:
            return 1
        if close < bb_lower:
            return -1
        return 0

    @staticmethod
    def _rsi_extreme(rsi: float) -> int:
        """Classify RSI as overbought (+1), oversold (-1), or neutral (0)."""
        if rsi >= 70.0:
            return 1
        if rsi <= 30.0:
            return -1
        return 0

    @staticmethod
    def _band_penetration(
        close: float, band: float, middle: float
    ) -> float:
        """Measure how far price has penetrated past a Bollinger Band.

        Returns a value between 0 and 1 representing the penetration
        depth relative to the band width.
        """
        band_width = abs(band - middle)
        if band_width <= 0:
            return 0.0
        penetration = abs(close - band)
        return min(penetration / band_width, 1.0)

    @staticmethod
    def _compute_levels(
        close: float,
        atr: float,
        bb_middle: float,
        direction: str,
    ) -> tuple[float, float]:
        """Compute stop-loss and take-profit for a mean-reversion entry.

        The take-profit target is the middle Bollinger Band (the mean).
        The stop-loss is placed at 2x ATR beyond the entry to allow room
        for overshoot before the reversion.
        """
        if atr <= 0:
            atr = close * 0.02

        if direction == "long":
            stop_loss = close - 2.0 * atr
            take_profit = bb_middle  # revert to mean
        elif direction == "short":
            stop_loss = close + 2.0 * atr
            take_profit = bb_middle
        else:
            stop_loss = close
            take_profit = close

        return stop_loss, take_profit
