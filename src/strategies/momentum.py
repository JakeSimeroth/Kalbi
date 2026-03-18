"""
KALBI-2 Equities Momentum Strategy.

Generates long/short/hold signals for equities based on a confluence of
momentum indicators: MACD crossover direction, RSI confirmation, and
volume confirmation.  All three must agree for a high-strength signal;
partial agreement yields a weaker signal or a hold.
"""

from __future__ import annotations

import numpy as np
import structlog

log = structlog.get_logger(__name__)


class MomentumStrategy:
    """Trend-following momentum strategy for equities.

    Signal logic:
        1. **MACD crossover** -- A bullish crossover (MACD line crossing
           above signal line, indicated by a positive and rising MACD
           histogram) suggests upward momentum; bearish crossover is the
           mirror image.
        2. **RSI confirmation** -- RSI above 50 confirms bullish momentum;
           below 50 confirms bearish.  Extreme readings (>70 or <30)
           add extra conviction.
        3. **Volume confirmation** -- Current volume above its short-term
           moving average confirms the trend has participation.

    When all three agree the signal is strong; when only two agree the
    signal is moderate; when fewer than two agree the strategy holds.

    Args:
        lookback_period: Number of bars used for rolling calculations
            (default ``20``).
        entry_threshold: Minimum signal strength required to emit a
            non-hold signal (default ``0.6``).
    """

    def __init__(
        self,
        lookback_period: int = 20,
        entry_threshold: float = 0.6,
    ) -> None:
        self.lookback_period = lookback_period
        self.entry_threshold = entry_threshold
        log.info(
            "momentum_strategy.initialized",
            lookback_period=self.lookback_period,
            entry_threshold=self.entry_threshold,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_signal(
        self, ohlcv_data: dict, indicators: dict
    ) -> dict:
        """Produce a momentum trading signal for a single equity.

        Args:
            ohlcv_data: Dictionary with at least:
                - ``ticker`` (*str*)
                - ``close`` (*float*) -- most recent closing price
                - ``volume`` (*float*) -- most recent volume
                - ``atr`` (*float*, optional) -- Average True Range for
                  stop/target sizing
            indicators: Pre-computed technical indicator values.  Expected
                keys:
                - ``macd_hist`` (*float*) -- current MACD histogram value
                - ``macd_hist_prev`` (*float*) -- previous bar MACD
                  histogram value
                - ``rsi_14`` (*float*) -- 14-period RSI
                - ``volume_sma`` (*float*) -- short-term volume SMA

        Returns:
            Signal dictionary with keys: ``ticker``, ``direction``
            (``"long"``/``"short"``/``"hold"``), ``strength`` (0-1),
            ``entry_price``, ``stop_loss``, ``take_profit``.
        """
        ticker: str = ohlcv_data.get("ticker", "UNKNOWN")
        close: float = ohlcv_data.get("close", 0.0)
        current_volume: float = ohlcv_data.get("volume", 0.0)
        atr: float = ohlcv_data.get("atr", close * 0.02)  # fallback 2%

        try:
            macd_hist: float = indicators.get("macd_hist", 0.0)
            macd_hist_prev: float = indicators.get("macd_hist_prev", 0.0)
            rsi: float = indicators.get("rsi_14", 50.0)
            volume_sma: float = indicators.get("volume_sma", 1.0)

            # ── Individual sub-signals ────────────────────────────────
            macd_signal = self._macd_signal(macd_hist, macd_hist_prev)
            rsi_signal = self._rsi_signal(rsi)
            vol_confirmed = self._volume_confirmed(current_volume, volume_sma)

            # ── Confluence scoring ────────────────────────────────────
            # Each sub-signal contributes directional weight.
            bullish_votes = 0
            bearish_votes = 0
            total_signals = 3

            if macd_signal > 0:
                bullish_votes += 1
            elif macd_signal < 0:
                bearish_votes += 1

            if rsi_signal > 0:
                bullish_votes += 1
            elif rsi_signal < 0:
                bearish_votes += 1

            if vol_confirmed:
                # Volume confirms whatever the majority direction is.
                if bullish_votes > bearish_votes:
                    bullish_votes += 1
                elif bearish_votes > bullish_votes:
                    bearish_votes += 1
                total_signals += 1  # volume adds a vote

            # Strength is the fraction of confirming votes.
            if bullish_votes >= bearish_votes:
                raw_strength = bullish_votes / max(total_signals, 1)
                direction_candidate = "long"
            else:
                raw_strength = bearish_votes / max(total_signals, 1)
                direction_candidate = "short"

            # Add RSI extremity bonus.
            if rsi > 70 and direction_candidate == "long":
                raw_strength = min(raw_strength + 0.1, 1.0)
            elif rsi < 30 and direction_candidate == "short":
                raw_strength = min(raw_strength + 0.1, 1.0)

            # ── Threshold gate ────────────────────────────────────────
            if raw_strength >= self.entry_threshold:
                direction = direction_candidate
            else:
                direction = "hold"

            # ── Price levels ──────────────────────────────────────────
            stop_loss, take_profit = self._compute_levels(
                close, atr, direction
            )

            signal = {
                "ticker": ticker,
                "direction": direction,
                "strength": round(raw_strength, 4),
                "entry_price": close,
                "stop_loss": round(stop_loss, 4),
                "take_profit": round(take_profit, 4),
            }

            log.info(
                "momentum_strategy.signal",
                ticker=ticker,
                direction=direction,
                strength=round(raw_strength, 4),
            )
            return signal

        except Exception:
            log.exception(
                "momentum_strategy.generate_signal_failed", ticker=ticker
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
    def _macd_signal(macd_hist: float, macd_hist_prev: float) -> int:
        """Return +1 for bullish MACD crossover, -1 for bearish, 0 for flat.

        A bullish crossover is when the histogram turns positive (or becomes
        more positive); bearish is the reverse.
        """
        if macd_hist > 0 and macd_hist > macd_hist_prev:
            return 1
        if macd_hist < 0 and macd_hist < macd_hist_prev:
            return -1
        return 0

    @staticmethod
    def _rsi_signal(rsi: float) -> int:
        """Return +1 for bullish RSI, -1 for bearish, 0 for neutral."""
        if rsi > 55:
            return 1
        if rsi < 45:
            return -1
        return 0

    @staticmethod
    def _volume_confirmed(current_volume: float, volume_sma: float) -> bool:
        """Return True when current volume exceeds its moving average."""
        if volume_sma <= 0:
            return False
        return current_volume > volume_sma

    @staticmethod
    def _compute_levels(
        close: float, atr: float, direction: str
    ) -> tuple[float, float]:
        """Compute stop-loss and take-profit using ATR multiples.

        Stops are placed 1.5x ATR away; targets at 2.5x ATR, giving a
        risk-reward ratio of roughly 1:1.67.
        """
        if atr <= 0:
            atr = close * 0.02  # fallback

        if direction == "long":
            stop_loss = close - 1.5 * atr
            take_profit = close + 2.5 * atr
        elif direction == "short":
            stop_loss = close + 1.5 * atr
            take_profit = close - 2.5 * atr
        else:
            stop_loss = close
            take_profit = close

        return stop_loss, take_profit
