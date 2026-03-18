"""
KALBI-2 Data Ingestion Service.

Provides convenience methods for persisting trades, signals, agent
decisions, and portfolio snapshots to TimescaleDB, as well as simple
query helpers used by the risk and meta-review agents.
"""

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.data.models import AgentDecision, PortfolioSnapshot, Signal, Trade


class DataIngestionService:
    """Thin service layer over the KALBI-2 ORM models.

    Every public method expects an already-opened SQLAlchemy ``Session``
    so that callers retain full control of transaction boundaries.
    """

    # ── Writers ──────────────────────────────────────────────────────

    @staticmethod
    def store_trade(session: Session, trade_data: dict) -> Trade:
        """Persist a new trade record.

        Args:
            session: Active SQLAlchemy session.
            trade_data: Dictionary whose keys match ``Trade`` column names.

        Returns:
            The newly created ``Trade`` instance (flushed, with id assigned).
        """
        trade = Trade(**trade_data)
        session.add(trade)
        session.flush()
        return trade

    @staticmethod
    def store_signal(session: Session, signal_data: dict) -> Signal:
        """Persist a new trading signal.

        Args:
            session: Active SQLAlchemy session.
            signal_data: Dictionary whose keys match ``Signal`` column names.

        Returns:
            The newly created ``Signal`` instance.
        """
        signal = Signal(**signal_data)
        session.add(signal)
        session.flush()
        return signal

    @staticmethod
    def store_agent_decision(
        session: Session, decision_data: dict
    ) -> AgentDecision:
        """Persist an agent decision audit record.

        Args:
            session: Active SQLAlchemy session.
            decision_data: Dictionary whose keys match ``AgentDecision`` column names.

        Returns:
            The newly created ``AgentDecision`` instance.
        """
        decision = AgentDecision(**decision_data)
        session.add(decision)
        session.flush()
        return decision

    @staticmethod
    def store_portfolio_snapshot(
        session: Session, snapshot_data: dict
    ) -> PortfolioSnapshot:
        """Persist a point-in-time portfolio snapshot.

        Args:
            session: Active SQLAlchemy session.
            snapshot_data: Dictionary whose keys match ``PortfolioSnapshot``
                column names.

        Returns:
            The newly created ``PortfolioSnapshot`` instance.
        """
        snapshot = PortfolioSnapshot(**snapshot_data)
        session.add(snapshot)
        session.flush()
        return snapshot

    # ── Readers ──────────────────────────────────────────────────────

    @staticmethod
    def get_recent_trades(session: Session, limit: int = 50) -> list[Trade]:
        """Return the most recent trades, newest first.

        Args:
            session: Active SQLAlchemy session.
            limit: Maximum number of records to return (default 50).

        Returns:
            A list of ``Trade`` instances ordered by ``created_at`` descending.
        """
        return (
            session.query(Trade)
            .order_by(Trade.created_at.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_daily_pnl(session: Session) -> float:
        """Calculate the aggregate P&L for today (UTC).

        Sums ``(fill_price - price) * quantity`` for all filled trades
        whose ``created_at`` falls on the current UTC date.  Sell-side
        trades invert the sign so that selling at a higher price than
        bought yields a positive P&L contribution.

        Args:
            session: Active SQLAlchemy session.

        Returns:
            Today's net P&L as a float.  Returns ``0.0`` when there are
            no filled trades for the day.
        """
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        filled_trades: list[Trade] = (
            session.query(Trade)
            .filter(
                Trade.status == "filled",
                Trade.fill_price.isnot(None),
                Trade.created_at >= today_start,
            )
            .all()
        )

        total_pnl: float = 0.0
        for trade in filled_trades:
            diff = trade.fill_price - trade.price
            # Selling reverses the P&L sign (profit when fill > price on sells
            # is already captured because the position was opened at a lower
            # price).  For buys, negative diff means slippage cost.
            if trade.side == "sell":
                total_pnl += diff * trade.quantity
            else:
                total_pnl -= diff * trade.quantity

        return total_pnl
