"""
Tests for the KALBI-2 trading strategies.

Covers import checks and behavioral tests for each strategy's signal
generation logic using known inputs.
"""

import pytest


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------


def test_ensemble_import():
    """EnsembleStrategy should be importable from src.strategies."""
    from src.strategies.ensemble import EnsembleStrategy

    assert EnsembleStrategy is not None


def test_momentum_import():
    """MomentumStrategy should be importable from src.strategies."""
    from src.strategies.momentum import MomentumStrategy

    assert MomentumStrategy is not None


def test_mean_reversion_import():
    """MeanReversionStrategy should be importable from src.strategies."""
    from src.strategies.mean_reversion import MeanReversionStrategy

    assert MeanReversionStrategy is not None


def test_kalshi_event_arb_import():
    """KalshiEventArbStrategy should be importable from src.strategies."""
    from src.strategies.kalshi_event_arb import KalshiEventArbStrategy

    assert KalshiEventArbStrategy is not None


# ---------------------------------------------------------------------------
# Ensemble strategy tests
# ---------------------------------------------------------------------------


def test_ensemble_combine_empty_signals():
    """Combining an empty signal list should return neutral values."""
    from src.strategies.ensemble import EnsembleStrategy

    strategy = EnsembleStrategy()
    result = strategy.combine_signals([])
    assert result["combined_value"] == 0.5
    assert result["confidence"] == 0.0
    assert result["signal_count"] == 0


def test_ensemble_combine_single_signal():
    """A single bullish signal should produce a value above 0.5."""
    from src.strategies.ensemble import EnsembleStrategy

    strategy = EnsembleStrategy()
    signals = [{"source": "fundamental", "value": 0.8, "confidence": 0.7}]
    result = strategy.combine_signals(signals)
    assert result["combined_value"] > 0.5
    assert result["signal_count"] == 1


def test_ensemble_combine_agreeing_signals():
    """Multiple agreeing signals should produce high confidence."""
    from src.strategies.ensemble import EnsembleStrategy

    strategy = EnsembleStrategy()
    signals = [
        {"source": "fundamental", "value": 0.8, "confidence": 0.8},
        {"source": "momentum", "value": 0.75, "confidence": 0.7},
        {"source": "mean_reversion", "value": 0.7, "confidence": 0.6},
    ]
    result = strategy.combine_signals(signals)
    assert result["combined_value"] > 0.5
    assert result["confidence"] > 0.5
    assert result["signal_count"] == 3


def test_ensemble_output_clamped():
    """Combined value should never exceed 0.95 or go below 0.05."""
    from src.strategies.ensemble import EnsembleStrategy

    strategy = EnsembleStrategy()
    # All signals at extreme bullish
    signals = [
        {"source": "fundamental", "value": 1.0, "confidence": 1.0},
        {"source": "momentum", "value": 1.0, "confidence": 1.0},
    ]
    result = strategy.combine_signals(signals)
    assert result["combined_value"] <= 0.95


# ---------------------------------------------------------------------------
# Momentum strategy tests
# ---------------------------------------------------------------------------


def test_momentum_bullish_signal():
    """Bullish MACD crossover + RSI > 55 + volume confirmation should signal long."""
    from src.strategies.momentum import MomentumStrategy

    strategy = MomentumStrategy(entry_threshold=0.5)
    ohlcv = {"ticker": "AAPL", "close": 185.0, "volume": 50_000_000, "atr": 3.0}
    indicators = {
        "macd_hist": 0.5,
        "macd_hist_prev": 0.2,
        "rsi_14": 60.0,
        "volume_sma": 40_000_000,
    }
    signal = strategy.generate_signal(ohlcv, indicators)
    assert signal["ticker"] == "AAPL"
    assert signal["direction"] == "long"
    assert signal["strength"] > 0.0


def test_momentum_hold_on_conflicting_signals():
    """Conflicting indicators with high threshold should produce a hold."""
    from src.strategies.momentum import MomentumStrategy

    strategy = MomentumStrategy(entry_threshold=0.9)
    ohlcv = {"ticker": "MSFT", "close": 400.0, "volume": 20_000_000}
    indicators = {
        "macd_hist": 0.1,
        "macd_hist_prev": 0.2,  # MACD declining (not bullish)
        "rsi_14": 50.0,  # neutral
        "volume_sma": 30_000_000,  # below average volume
    }
    signal = strategy.generate_signal(ohlcv, indicators)
    assert signal["direction"] == "hold"


def test_momentum_stop_and_target_levels():
    """Long signal should have stop below entry and target above."""
    from src.strategies.momentum import MomentumStrategy

    strategy = MomentumStrategy(entry_threshold=0.5)
    ohlcv = {"ticker": "AAPL", "close": 185.0, "volume": 50_000_000, "atr": 3.0}
    indicators = {
        "macd_hist": 0.5,
        "macd_hist_prev": 0.2,
        "rsi_14": 65.0,
        "volume_sma": 40_000_000,
    }
    signal = strategy.generate_signal(ohlcv, indicators)
    if signal["direction"] == "long":
        assert signal["stop_loss"] < signal["entry_price"]
        assert signal["take_profit"] > signal["entry_price"]


# ---------------------------------------------------------------------------
# Mean reversion strategy tests
# ---------------------------------------------------------------------------


def test_mean_reversion_oversold_signal():
    """Price below lower BB + RSI < 30 should produce a long (buy) signal."""
    from src.strategies.mean_reversion import MeanReversionStrategy

    strategy = MeanReversionStrategy()
    ohlcv = {"ticker": "AAPL", "close": 170.0, "atr": 3.0}
    indicators = {
        "bb_upper": 195.0,
        "bb_middle": 185.0,
        "bb_lower": 175.0,
        "rsi_14": 25.0,
    }
    signal = strategy.generate_signal(ohlcv, indicators)
    assert signal["direction"] == "long"
    assert signal["strength"] > 0.0


def test_mean_reversion_overbought_signal():
    """Price above upper BB + RSI > 70 should produce a short (sell) signal."""
    from src.strategies.mean_reversion import MeanReversionStrategy

    strategy = MeanReversionStrategy()
    ohlcv = {"ticker": "AAPL", "close": 200.0, "atr": 3.0}
    indicators = {
        "bb_upper": 195.0,
        "bb_middle": 185.0,
        "bb_lower": 175.0,
        "rsi_14": 75.0,
    }
    signal = strategy.generate_signal(ohlcv, indicators)
    assert signal["direction"] == "short"
    assert signal["strength"] > 0.0


def test_mean_reversion_neutral_signal():
    """Price within Bollinger Bands + neutral RSI should produce hold."""
    from src.strategies.mean_reversion import MeanReversionStrategy

    strategy = MeanReversionStrategy()
    ohlcv = {"ticker": "AAPL", "close": 185.0, "atr": 3.0}
    indicators = {
        "bb_upper": 195.0,
        "bb_middle": 185.0,
        "bb_lower": 175.0,
        "rsi_14": 50.0,
    }
    signal = strategy.generate_signal(ohlcv, indicators)
    assert signal["direction"] == "hold"
    assert signal["strength"] == 0.0


# ---------------------------------------------------------------------------
# Kalshi event arb strategy tests
# ---------------------------------------------------------------------------


def test_kalshi_event_arb_buy_yes():
    """High estimated prob vs low market price should signal buy_yes."""
    from src.strategies.kalshi_event_arb import KalshiEventArbStrategy

    strategy = KalshiEventArbStrategy(min_edge=0.08, min_confidence=0.5)
    signal = strategy.evaluate(
        market_data={"market_id": "TEST-MARKET", "yes_price": 0.40},
        news_sentiment={"sentiment_score": 0.5, "confidence": 0.7},
        estimated_probability=0.60,
    )
    assert signal["action"] == "buy_yes"
    assert signal["edge"] > 0.0


def test_kalshi_event_arb_buy_no():
    """Low estimated prob vs high market price should signal buy_no."""
    from src.strategies.kalshi_event_arb import KalshiEventArbStrategy

    strategy = KalshiEventArbStrategy(min_edge=0.08, min_confidence=0.5)
    signal = strategy.evaluate(
        market_data={"market_id": "TEST-MARKET", "yes_price": 0.70},
        news_sentiment={"sentiment_score": -0.3, "confidence": 0.7},
        estimated_probability=0.50,
    )
    assert signal["action"] == "buy_no"
    assert signal["edge"] < 0.0


def test_kalshi_event_arb_pass_no_edge():
    """When edge is within the dead zone, action should be pass."""
    from src.strategies.kalshi_event_arb import KalshiEventArbStrategy

    strategy = KalshiEventArbStrategy(min_edge=0.08)
    signal = strategy.evaluate(
        market_data={"market_id": "TEST-MARKET", "yes_price": 0.50},
        news_sentiment={"sentiment_score": 0.0, "confidence": 0.8},
        estimated_probability=0.53,
    )
    assert signal["action"] == "pass"


def test_kalshi_event_arb_edge_calculation():
    """calculate_edge should return estimated_prob - market_price."""
    from src.strategies.kalshi_event_arb import KalshiEventArbStrategy

    strategy = KalshiEventArbStrategy()
    assert strategy.calculate_edge(0.7, 0.5) == pytest.approx(0.2)
    assert strategy.calculate_edge(0.3, 0.5) == pytest.approx(-0.2)
    assert strategy.calculate_edge(0.5, 0.5) == pytest.approx(0.0)
