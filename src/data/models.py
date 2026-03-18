"""
KALBI-2 SQLAlchemy ORM models for TimescaleDB.

Defines the core persistence layer: trades, signals, agent decisions,
and portfolio snapshots.  All timestamp columns are indexed for
efficient time-range queries (TimescaleDB hypertable friendly).
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Trade(Base):
    """A single executed (or attempted) trade on Kalshi or Alpaca."""

    __tablename__ = "trades"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    trade_type: str = Column(
        String(16), nullable=False, doc="'kalshi' or 'equities'"
    )
    ticker_or_market_id: str = Column(
        String(128), nullable=False, doc="Ticker symbol or Kalshi market ID"
    )
    side: str = Column(
        String(8), nullable=False, doc="'buy' or 'sell'"
    )
    quantity: float = Column(Float, nullable=False)
    price: float = Column(
        Float, nullable=False, doc="Requested / limit price"
    )
    fill_price: float = Column(
        Float, nullable=True, doc="Actual fill price (None if unfilled)"
    )
    status: str = Column(
        String(32),
        nullable=False,
        default="pending",
        doc="e.g. pending, filled, partial, cancelled, rejected",
    )
    slippage_bps: float = Column(
        Float, nullable=True, doc="Slippage in basis points vs. requested price"
    )
    agent_name: str = Column(
        String(64), nullable=True, doc="Name of the agent that placed the trade"
    )
    reasoning: str = Column(
        Text, nullable=True, doc="Free-text reasoning summary"
    )
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_trades_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Trade(id={self.id}, type={self.trade_type}, "
            f"ticker={self.ticker_or_market_id}, side={self.side}, "
            f"qty={self.quantity}, status={self.status})>"
        )


class Signal(Base):
    """A trading signal emitted by an analysis agent."""

    __tablename__ = "signals"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    source_agent: str = Column(
        String(64), nullable=False, doc="Agent that produced the signal"
    )
    ticker_or_market_id: str = Column(
        String(128), nullable=False, doc="Ticker symbol or Kalshi market ID"
    )
    signal_type: str = Column(
        String(16),
        nullable=False,
        doc="'long', 'short', 'hold', 'buy_yes', 'buy_no', or 'pass'",
    )
    strength: float = Column(
        Float, nullable=False, doc="Relative signal strength (0-1)"
    )
    confidence: float = Column(
        Float, nullable=False, doc="Model confidence (0-1)"
    )
    metadata_json: str = Column(
        Text, nullable=True, doc="Arbitrary JSON metadata blob"
    )
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_signals_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Signal(id={self.id}, agent={self.source_agent}, "
            f"ticker={self.ticker_or_market_id}, type={self.signal_type}, "
            f"confidence={self.confidence})>"
        )


class AgentDecision(Base):
    """An auditable record of an agent's decision-making step."""

    __tablename__ = "agent_decisions"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    agent_name: str = Column(
        String(64), nullable=False, doc="Name of the deciding agent"
    )
    crew_name: str = Column(
        String(64), nullable=True, doc="CrewAI crew this agent belongs to"
    )
    decision_type: str = Column(
        String(64), nullable=False, doc="Category of decision (e.g. 'trade', 'risk_check')"
    )
    input_summary: str = Column(
        Text, nullable=True, doc="Summary of the inputs considered"
    )
    output_json: str = Column(
        Text, nullable=True, doc="Structured JSON output of the decision"
    )
    reasoning_chain: str = Column(
        Text, nullable=True, doc="Step-by-step reasoning trace"
    )
    execution_time_ms: int = Column(
        Integer, nullable=True, doc="Wall-clock execution time in milliseconds"
    )
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_agent_decisions_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<AgentDecision(id={self.id}, agent={self.agent_name}, "
            f"type={self.decision_type})>"
        )


class PortfolioSnapshot(Base):
    """Point-in-time snapshot of portfolio health metrics."""

    __tablename__ = "portfolio_snapshots"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    total_value: float = Column(
        Float, nullable=False, doc="Total portfolio value (cash + positions)"
    )
    cash_balance: float = Column(
        Float, nullable=False, doc="Uninvested cash balance"
    )
    deployed_value: float = Column(
        Float, nullable=False, doc="Value currently deployed in positions"
    )
    deployed_pct: float = Column(
        Float, nullable=False, doc="Percentage of portfolio deployed"
    )
    daily_pnl: float = Column(
        Float, nullable=False, doc="Absolute daily P&L"
    )
    daily_pnl_pct: float = Column(
        Float, nullable=False, doc="Daily P&L as a percentage of portfolio"
    )
    max_drawdown_pct: float = Column(
        Float, nullable=False, doc="Running max drawdown percentage"
    )
    open_positions_count: int = Column(
        Integer, nullable=False, doc="Number of currently open positions"
    )
    portfolio_correlation: float = Column(
        Float, nullable=True, doc="Average pairwise correlation of positions"
    )
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_portfolio_snapshots_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<PortfolioSnapshot(id={self.id}, value={self.total_value}, "
            f"pnl={self.daily_pnl}, deployed={self.deployed_pct}%)>"
        )


def create_tables(engine: Engine) -> None:
    """Create all ORM-mapped tables if they do not already exist.

    Args:
        engine: A SQLAlchemy ``Engine`` connected to the target database.
    """
    Base.metadata.create_all(bind=engine)
