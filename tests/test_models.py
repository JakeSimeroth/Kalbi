"""
Tests for the KALBI-2 SQLAlchemy ORM models.

Uses the in-memory SQLite fixtures from conftest.py to verify that all
four core models can be created, persisted, and queried.
"""

from datetime import datetime, timezone

from src.data.models import AgentDecision, PortfolioSnapshot, Signal, Trade


def test_create_trade(db_session):
    """A Trade record should persist and receive an auto-generated ID."""
    trade = Trade(
        trade_type="kalshi",
        ticker_or_market_id="PRES-2024-DEM",
        side="buy",
        quantity=10,
        price=0.55,
        status="pending",
        agent_name="kalshi_specialist",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(trade)
    db_session.commit()
    assert trade.id is not None


def test_create_trade_with_fill(db_session):
    """A Trade with fill_price and slippage should persist correctly."""
    trade = Trade(
        trade_type="equities",
        ticker_or_market_id="AAPL",
        side="buy",
        quantity=50,
        price=185.00,
        fill_price=185.02,
        slippage_bps=1.08,
        status="filled",
        agent_name="executor",
        reasoning="Momentum signal confirmed by all three indicators.",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(trade)
    db_session.commit()
    assert trade.id is not None
    assert trade.fill_price == 185.02
    assert trade.slippage_bps == 1.08


def test_create_signal(db_session):
    """A Signal record should persist and receive an auto-generated ID."""
    signal = Signal(
        source_agent="quant_analyst",
        ticker_or_market_id="AAPL",
        signal_type="long",
        strength=0.8,
        confidence=0.75,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(signal)
    db_session.commit()
    assert signal.id is not None


def test_create_signal_with_metadata(db_session):
    """A Signal with metadata_json should persist the JSON blob."""
    signal = Signal(
        source_agent="news_analyst",
        ticker_or_market_id="TSLA",
        signal_type="short",
        strength=0.6,
        confidence=0.55,
        metadata_json='{"event": "earnings_miss", "sentiment": -0.3}',
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(signal)
    db_session.commit()
    assert signal.id is not None
    assert "earnings_miss" in signal.metadata_json


def test_create_agent_decision(db_session):
    """An AgentDecision record should persist with all fields."""
    decision = AgentDecision(
        agent_name="risk_manager",
        crew_name="equities_crew",
        decision_type="trade_approval",
        input_summary="AAPL long signal, strength=0.8, confidence=0.75",
        output_json='{"approved": true, "position_size": 1500.0}',
        reasoning_chain="Checked daily loss: OK. Position size: OK. Correlation: OK.",
        execution_time_ms=245,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(decision)
    db_session.commit()
    assert decision.id is not None
    assert decision.execution_time_ms == 245


def test_create_portfolio_snapshot(db_session):
    """A PortfolioSnapshot record should persist all metrics."""
    snap = PortfolioSnapshot(
        total_value=10000.0,
        cash_balance=5000.0,
        deployed_value=5000.0,
        deployed_pct=50.0,
        daily_pnl=150.0,
        daily_pnl_pct=1.5,
        max_drawdown_pct=3.2,
        open_positions_count=5,
        portfolio_correlation=0.45,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(snap)
    db_session.commit()
    assert snap.id is not None


def test_query_trades_by_status(db_session):
    """Should be able to query trades filtered by status."""
    for status in ["pending", "filled", "filled", "cancelled"]:
        trade = Trade(
            trade_type="equities",
            ticker_or_market_id="MSFT",
            side="buy",
            quantity=10,
            price=400.0,
            status=status,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(trade)
    db_session.commit()

    filled = db_session.query(Trade).filter(Trade.status == "filled").all()
    assert len(filled) == 2


def test_trade_repr(db_session):
    """Trade __repr__ should include key identifying information."""
    trade = Trade(
        trade_type="kalshi",
        ticker_or_market_id="FOMC-RATE",
        side="buy",
        quantity=5,
        price=0.60,
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(trade)
    db_session.commit()
    repr_str = repr(trade)
    assert "kalshi" in repr_str
    assert "FOMC-RATE" in repr_str
