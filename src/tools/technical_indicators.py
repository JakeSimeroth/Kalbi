"""
KALBI-2 Technical Indicator Tools.

CrewAI tool functions for calculating technical analysis indicators
and detecting chart patterns on OHLCV price data.  Uses pandas-ta
for indicator computation.
"""

import json

import pandas as pd
import pandas_ta as ta
import structlog
from crewai.tools import tool

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_ohlcv(ohlcv_json: str) -> pd.DataFrame:
    """Parse a JSON string of OHLCV data into a pandas DataFrame.

    Expects either a list of dicts with keys: date/timestamp, open,
    high, low, close, volume -- or a dict with a 'candles' key
    containing such a list.
    """
    data = json.loads(ohlcv_json)

    # Handle wrapper format from market_data tools
    if isinstance(data, dict) and "candles" in data:
        data = data["candles"]

    if not isinstance(data, list) or len(data) == 0:
        raise ValueError("OHLCV data must be a non-empty list of candles")

    df = pd.DataFrame(data)

    # Normalise column names to lowercase
    df.columns = [c.lower() for c in df.columns]

    # Ensure required columns exist
    required = {"open", "high", "low", "close"}
    if not required.issubset(set(df.columns)):
        raise ValueError(
            f"Missing required columns. Found: {list(df.columns)}, "
            f"need: {sorted(required)}"
        )

    # Convert numeric columns
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Set date index if available
    date_col = None
    for candidate in ["date", "timestamp", "datetime", "time"]:
        if candidate in df.columns:
            date_col = candidate
            break
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col])
        df.set_index(date_col, inplace=True)

    df.sort_index(inplace=True)
    return df


def _safe_series_to_list(series: pd.Series | None) -> list:
    """Convert a pandas Series to a JSON-safe list, handling NaN."""
    if series is None:
        return []
    return [
        round(v, 6) if pd.notna(v) else None for v in series.tolist()
    ]


# ---------------------------------------------------------------------------
# CrewAI Tools
# ---------------------------------------------------------------------------


@tool
def calculate_indicators(ohlcv_json: str) -> str:
    """Calculate technical analysis indicators on OHLCV price data.

    Computes RSI, MACD (line, signal, histogram), Bollinger Bands
    (upper, middle, lower), OBV, SMA (20, 50), and EMA (12, 26).

    Args:
        ohlcv_json: JSON string of OHLCV data. Must be a list of objects
                    with keys: date, open, high, low, close, volume.
                    Can also be the direct output of get_stock_ohlcv.

    Returns:
        JSON string with computed indicator values. Each indicator is
        an array aligned with the input candles. Includes latest values
        summary for quick reference.
    """
    try:
        logger.info("indicators.calculate", data_length=len(ohlcv_json))
        df = _parse_ohlcv(ohlcv_json)

        if len(df) < 2:
            return json.dumps(
                {"error": "Need at least 2 data points for indicators"}
            )

        # --- RSI (14-period) ---
        rsi = ta.rsi(df["close"], length=14)

        # --- MACD (12, 26, 9) ---
        macd_df = ta.macd(df["close"], fast=12, slow=26, signal=9)
        macd_line = macd_df.iloc[:, 0] if macd_df is not None else None
        macd_signal = macd_df.iloc[:, 1] if macd_df is not None else None
        macd_hist = macd_df.iloc[:, 2] if macd_df is not None else None

        # --- Bollinger Bands (20, 2) ---
        bbands = ta.bbands(df["close"], length=20, std=2)
        bb_lower = bbands.iloc[:, 0] if bbands is not None else None
        bb_middle = bbands.iloc[:, 1] if bbands is not None else None
        bb_upper = bbands.iloc[:, 2] if bbands is not None else None

        # --- OBV ---
        obv = None
        if "volume" in df.columns and df["volume"].notna().any():
            obv = ta.obv(df["close"], df["volume"])

        # --- SMA (20, 50) ---
        sma_20 = ta.sma(df["close"], length=20)
        sma_50 = ta.sma(df["close"], length=50)

        # --- EMA (12, 26) ---
        ema_12 = ta.ema(df["close"], length=12)
        ema_26 = ta.ema(df["close"], length=26)

        # Build result
        indicators = {
            "data_points": len(df),
            "rsi_14": _safe_series_to_list(rsi),
            "macd_line": _safe_series_to_list(macd_line),
            "macd_signal": _safe_series_to_list(macd_signal),
            "macd_histogram": _safe_series_to_list(macd_hist),
            "bollinger_upper": _safe_series_to_list(bb_upper),
            "bollinger_middle": _safe_series_to_list(bb_middle),
            "bollinger_lower": _safe_series_to_list(bb_lower),
            "obv": _safe_series_to_list(obv),
            "sma_20": _safe_series_to_list(sma_20),
            "sma_50": _safe_series_to_list(sma_50),
            "ema_12": _safe_series_to_list(ema_12),
            "ema_26": _safe_series_to_list(ema_26),
        }

        # Latest values summary for quick reference
        def _latest(series):
            if series is not None and len(series) > 0:
                last = series.iloc[-1]
                return round(last, 4) if pd.notna(last) else None
            return None

        indicators["latest"] = {
            "close": round(df["close"].iloc[-1], 4),
            "rsi_14": _latest(rsi),
            "macd_line": _latest(macd_line),
            "macd_signal": _latest(macd_signal),
            "macd_histogram": _latest(macd_hist),
            "bollinger_upper": _latest(bb_upper),
            "bollinger_middle": _latest(bb_middle),
            "bollinger_lower": _latest(bb_lower),
            "sma_20": _latest(sma_20),
            "sma_50": _latest(sma_50),
            "ema_12": _latest(ema_12),
            "ema_26": _latest(ema_26),
        }

        logger.info("indicators.calculate.done", data_points=len(df))
        return json.dumps(indicators, indent=2)

    except Exception as e:
        logger.error("indicators.calculate.error", error=str(e))
        return json.dumps({"error": str(e)})


@tool
def detect_patterns(ohlcv_json: str) -> str:
    """Detect chart patterns and key levels in OHLCV price data.

    Identifies support/resistance levels, trend direction, moving average
    crossovers, RSI divergences, and basic candlestick patterns.

    Args:
        ohlcv_json: JSON string of OHLCV data. Must be a list of objects
                    with keys: date, open, high, low, close, volume.
                    Can also be the direct output of get_stock_ohlcv.

    Returns:
        JSON string with detected patterns including trend direction,
        support/resistance levels, crossover signals, and pattern names.
    """
    try:
        logger.info("patterns.detect", data_length=len(ohlcv_json))
        df = _parse_ohlcv(ohlcv_json)

        if len(df) < 20:
            return json.dumps(
                {"error": "Need at least 20 data points for pattern detection"}
            )

        close = df["close"]
        high = df["high"]
        low = df["low"]

        patterns: dict = {
            "data_points": len(df),
            "current_price": round(close.iloc[-1], 4),
            "signals": [],
        }

        # --- Trend Detection ---
        sma_20 = ta.sma(close, length=20)
        sma_50 = ta.sma(close, length=50)

        if sma_20 is not None and sma_50 is not None:
            latest_20 = sma_20.iloc[-1]
            latest_50 = sma_50.iloc[-1]
            if pd.notna(latest_20) and pd.notna(latest_50):
                if latest_20 > latest_50:
                    patterns["trend"] = "bullish"
                    patterns["trend_detail"] = "SMA20 above SMA50"
                else:
                    patterns["trend"] = "bearish"
                    patterns["trend_detail"] = "SMA20 below SMA50"

                # Golden / Death cross detection
                if len(sma_20) >= 2 and len(sma_50) >= 2:
                    prev_20 = sma_20.iloc[-2]
                    prev_50 = sma_50.iloc[-2]
                    if pd.notna(prev_20) and pd.notna(prev_50):
                        if prev_20 <= prev_50 and latest_20 > latest_50:
                            patterns["signals"].append(
                                {
                                    "type": "golden_cross",
                                    "description": "SMA20 crossed above SMA50 (bullish)",
                                    "strength": "strong",
                                }
                            )
                        elif prev_20 >= prev_50 and latest_20 < latest_50:
                            patterns["signals"].append(
                                {
                                    "type": "death_cross",
                                    "description": "SMA20 crossed below SMA50 (bearish)",
                                    "strength": "strong",
                                }
                            )

        # --- Support and Resistance Levels ---
        lookback = min(len(df), 60)
        recent_high = high.tail(lookback)
        recent_low = low.tail(lookback)

        # Resistance: recent swing highs
        resistance_levels = []
        for i in range(2, len(recent_high) - 2):
            h = recent_high.iloc[i]
            if (
                h > recent_high.iloc[i - 1]
                and h > recent_high.iloc[i - 2]
                and h > recent_high.iloc[i + 1]
                and h > recent_high.iloc[i + 2]
            ):
                resistance_levels.append(round(h, 4))

        # Support: recent swing lows
        support_levels = []
        for i in range(2, len(recent_low) - 2):
            lo = recent_low.iloc[i]
            if (
                lo < recent_low.iloc[i - 1]
                and lo < recent_low.iloc[i - 2]
                and lo < recent_low.iloc[i + 1]
                and lo < recent_low.iloc[i + 2]
            ):
                support_levels.append(round(lo, 4))

        # Deduplicate nearby levels (within 1%)
        def _dedup(levels: list[float], threshold: float = 0.01) -> list[float]:
            if not levels:
                return []
            levels_sorted = sorted(set(levels))
            deduped = [levels_sorted[0]]
            for lvl in levels_sorted[1:]:
                if abs(lvl - deduped[-1]) / deduped[-1] > threshold:
                    deduped.append(lvl)
            return deduped

        patterns["resistance_levels"] = _dedup(resistance_levels)
        patterns["support_levels"] = _dedup(support_levels)

        # --- RSI Conditions ---
        rsi = ta.rsi(close, length=14)
        if rsi is not None and len(rsi) > 0:
            latest_rsi = rsi.iloc[-1]
            if pd.notna(latest_rsi):
                patterns["rsi"] = round(latest_rsi, 2)
                if latest_rsi > 70:
                    patterns["signals"].append(
                        {
                            "type": "rsi_overbought",
                            "description": f"RSI at {latest_rsi:.1f} (overbought > 70)",
                            "strength": "moderate",
                        }
                    )
                elif latest_rsi < 30:
                    patterns["signals"].append(
                        {
                            "type": "rsi_oversold",
                            "description": f"RSI at {latest_rsi:.1f} (oversold < 30)",
                            "strength": "moderate",
                        }
                    )

        # --- Bollinger Band Squeeze ---
        bbands = ta.bbands(close, length=20, std=2)
        if bbands is not None and len(bbands) > 0:
            bb_upper = bbands.iloc[-1, 2]  # upper band
            bb_lower = bbands.iloc[-1, 0]  # lower band
            bb_middle = bbands.iloc[-1, 1]  # middle band

            if pd.notna(bb_upper) and pd.notna(bb_lower) and bb_middle > 0:
                bandwidth = (bb_upper - bb_lower) / bb_middle
                patterns["bollinger_bandwidth"] = round(bandwidth, 4)

                if bandwidth < 0.04:
                    patterns["signals"].append(
                        {
                            "type": "bollinger_squeeze",
                            "description": "Tight Bollinger Bands -- potential breakout imminent",
                            "strength": "moderate",
                        }
                    )

                current = close.iloc[-1]
                if current > bb_upper:
                    patterns["signals"].append(
                        {
                            "type": "bollinger_upper_break",
                            "description": "Price above upper Bollinger Band (overbought)",
                            "strength": "moderate",
                        }
                    )
                elif current < bb_lower:
                    patterns["signals"].append(
                        {
                            "type": "bollinger_lower_break",
                            "description": "Price below lower Bollinger Band (oversold)",
                            "strength": "moderate",
                        }
                    )

        # --- MACD Signal ---
        macd_df = ta.macd(close, fast=12, slow=26, signal=9)
        if macd_df is not None and len(macd_df) >= 2:
            macd_curr = macd_df.iloc[-1, 0]
            sig_curr = macd_df.iloc[-1, 1]
            macd_prev = macd_df.iloc[-2, 0]
            sig_prev = macd_df.iloc[-2, 1]

            if all(pd.notna(v) for v in [macd_curr, sig_curr, macd_prev, sig_prev]):
                if macd_prev <= sig_prev and macd_curr > sig_curr:
                    patterns["signals"].append(
                        {
                            "type": "macd_bullish_cross",
                            "description": "MACD crossed above signal line (bullish)",
                            "strength": "moderate",
                        }
                    )
                elif macd_prev >= sig_prev and macd_curr < sig_curr:
                    patterns["signals"].append(
                        {
                            "type": "macd_bearish_cross",
                            "description": "MACD crossed below signal line (bearish)",
                            "strength": "moderate",
                        }
                    )

        # --- Volume Analysis ---
        if "volume" in df.columns and df["volume"].notna().any():
            avg_vol = df["volume"].tail(20).mean()
            latest_vol = df["volume"].iloc[-1]
            if pd.notna(avg_vol) and avg_vol > 0 and pd.notna(latest_vol):
                vol_ratio = latest_vol / avg_vol
                patterns["volume_ratio_vs_20d_avg"] = round(vol_ratio, 2)
                if vol_ratio > 2.0:
                    patterns["signals"].append(
                        {
                            "type": "high_volume",
                            "description": f"Volume {vol_ratio:.1f}x above 20-day average",
                            "strength": "moderate",
                        }
                    )

        patterns["signal_count"] = len(patterns["signals"])

        logger.info(
            "patterns.detect.done",
            signal_count=patterns["signal_count"],
        )
        return json.dumps(patterns, indent=2)

    except Exception as e:
        logger.error("patterns.detect.error", error=str(e))
        return json.dumps({"error": str(e)})
