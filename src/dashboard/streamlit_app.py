"""
KALBI-2 Trading Dashboard
Run with: streamlit run src/dashboard/streamlit_app.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(page_title="KALBI-2 Dashboard", page_icon="\U0001F4C8", layout="wide")


# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------

def _get_settings_url() -> str:
    """Load the TimescaleDB URL from Settings, falling back to a default."""
    try:
        from src.config import Settings
        settings = Settings()
        return settings.timescaledb_url
    except Exception:
        return "postgresql://kalbi:kalbi@localhost:5432/kalbi"


@st.cache_resource
def get_engine():
    """Create a shared SQLAlchemy engine (cached across reruns)."""
    url = _get_settings_url()
    return create_engine(url, pool_pre_ping=True)


def _db_available() -> bool:
    """Return True if the database is reachable."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Cached queries
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30)
def fetch_latest_snapshot() -> dict | None:
    """Return the most recent portfolio snapshot row as a dict."""
    try:
        with get_engine().connect() as conn:
            row = conn.execute(
                text(
                    "SELECT * FROM portfolio_snapshots "
                    "ORDER BY created_at DESC LIMIT 1"
                )
            ).mappings().first()
        return dict(row) if row else None
    except Exception:
        return None


@st.cache_data(ttl=30)
def fetch_snapshot_history(days: int = 30) -> pd.DataFrame:
    """Return portfolio snapshots for the past *days* days."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        with get_engine().connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT created_at, total_value, daily_pnl, daily_pnl_pct, "
                    "deployed_pct, max_drawdown_pct "
                    "FROM portfolio_snapshots "
                    "WHERE created_at >= :cutoff "
                    "ORDER BY created_at"
                ),
                {"cutoff": cutoff},
            ).mappings().all()
        return pd.DataFrame(rows) if rows else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=15)
def fetch_recent_trades(limit: int = 50) -> pd.DataFrame:
    """Return the most recent trades."""
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, trade_type, ticker_or_market_id, side, quantity, "
                    "price, fill_price, status, slippage_bps, agent_name, "
                    "reasoning, created_at "
                    "FROM trades ORDER BY created_at DESC LIMIT :limit"
                ),
                {"limit": limit},
            ).mappings().all()
        return pd.DataFrame(rows) if rows else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=30)
def fetch_agent_decisions(limit: int = 100) -> pd.DataFrame:
    """Return the most recent agent decisions."""
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, agent_name, crew_name, decision_type, "
                    "input_summary, execution_time_ms, created_at "
                    "FROM agent_decisions ORDER BY created_at DESC LIMIT :limit"
                ),
                {"limit": limit},
            ).mappings().all()
        return pd.DataFrame(rows) if rows else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=30)
def fetch_trade_stats() -> dict:
    """Compute aggregate trade statistics."""
    try:
        with get_engine().connect() as conn:
            row = conn.execute(
                text(
                    "SELECT "
                    "  COUNT(*) AS total_trades, "
                    "  COUNT(*) FILTER (WHERE status = 'filled') AS filled_trades, "
                    "  COUNT(*) FILTER (WHERE fill_price > price AND side = 'buy') AS winning_buys, "
                    "  COUNT(*) FILTER (WHERE status = 'filled') AS filled_count "
                    "FROM trades"
                )
            ).mappings().first()
        if row is None:
            return {"total_trades": 0, "filled_trades": 0, "win_rate": 0.0}
        d = dict(row)
        filled = d.get("filled_trades", 0) or 0
        winning = d.get("winning_buys", 0) or 0
        win_rate = (winning / filled * 100.0) if filled > 0 else 0.0
        return {
            "total_trades": d.get("total_trades", 0),
            "filled_trades": filled,
            "win_rate": round(win_rate, 1),
        }
    except Exception:
        return {"total_trades": 0, "filled_trades": 0, "win_rate": 0.0}


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.sidebar.title("KALBI-2")
st.sidebar.markdown("Autonomous Trading System")
page = st.sidebar.selectbox(
    "Navigate",
    ["Overview", "Trades", "Agents", "Risk", "Backtests"],
)

db_ok = _db_available()
if not db_ok:
    st.sidebar.warning("Database unavailable")
else:
    st.sidebar.success("Database connected")


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

if page == "Overview":
    st.title("Portfolio Overview")

    if not db_ok:
        st.error(
            "Cannot connect to TimescaleDB. Make sure the database is running "
            "and the TIMESCALEDB_URL environment variable is set."
        )
        st.stop()

    snapshot = fetch_latest_snapshot()
    stats = fetch_trade_stats()

    if snapshot:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Portfolio Value", f"${snapshot['total_value']:,.2f}")
        col2.metric(
            "Daily P&L",
            f"${snapshot['daily_pnl']:,.2f}",
            delta=f"{snapshot['daily_pnl_pct']:.2f}%",
        )
        col3.metric("Deployed", f"{snapshot['deployed_pct']:.1f}%")
        col4.metric("Win Rate", f"{stats['win_rate']:.1f}%")
    else:
        st.info("No portfolio snapshots available yet.")

    st.subheader("Equity Curve")
    history = fetch_snapshot_history()
    if not history.empty and "created_at" in history.columns:
        st.line_chart(history.set_index("created_at")["total_value"])
    else:
        st.info("No historical data to display.")

    st.subheader("Open Positions")
    if snapshot:
        st.metric("Open Positions Count", snapshot.get("open_positions_count", 0))
    trades = fetch_recent_trades(limit=20)
    if not trades.empty:
        open_trades = trades[trades["status"].isin(["pending", "partial"])]
        if not open_trades.empty:
            st.dataframe(open_trades, use_container_width=True)
        else:
            st.info("No open positions.")
    else:
        st.info("No trade data available.")


elif page == "Trades":
    st.title("Trade History")

    if not db_ok:
        st.error("Database unavailable.")
        st.stop()

    limit = st.slider("Number of trades", 10, 200, 50)
    trades_df = fetch_recent_trades(limit=limit)

    if not trades_df.empty:
        # Filters
        col1, col2 = st.columns(2)
        with col1:
            trade_types = ["All"] + sorted(trades_df["trade_type"].dropna().unique().tolist())
            selected_type = st.selectbox("Trade Type", trade_types)
        with col2:
            statuses = ["All"] + sorted(trades_df["status"].dropna().unique().tolist())
            selected_status = st.selectbox("Status", statuses)

        filtered = trades_df.copy()
        if selected_type != "All":
            filtered = filtered[filtered["trade_type"] == selected_type]
        if selected_status != "All":
            filtered = filtered[filtered["status"] == selected_status]

        st.dataframe(filtered, use_container_width=True)

        # Trade details expander
        if not filtered.empty:
            st.subheader("Trade Details")
            selected_id = st.selectbox(
                "Select trade ID",
                filtered["id"].tolist(),
            )
            detail = filtered[filtered["id"] == selected_id].iloc[0]
            with st.expander("Reasoning", expanded=True):
                st.text(detail.get("reasoning", "No reasoning recorded."))
    else:
        st.info("No trades recorded yet.")


elif page == "Agents":
    st.title("Agent Activity")

    if not db_ok:
        st.error("Database unavailable.")
        st.stop()

    decisions = fetch_agent_decisions()
    if not decisions.empty:
        st.subheader("Decision Log")
        st.dataframe(decisions, use_container_width=True)

        st.subheader("Decisions by Agent")
        agent_counts = decisions["agent_name"].value_counts()
        st.bar_chart(agent_counts)

        st.subheader("Average Execution Time (ms)")
        if "execution_time_ms" in decisions.columns:
            avg_time = (
                decisions.groupby("agent_name")["execution_time_ms"]
                .mean()
                .sort_values(ascending=False)
            )
            st.bar_chart(avg_time)
    else:
        st.info("No agent decisions recorded yet.")


elif page == "Risk":
    st.title("Risk Dashboard")

    if not db_ok:
        st.error("Database unavailable.")
        st.stop()

    snapshot = fetch_latest_snapshot()
    if snapshot:
        st.subheader("Current Risk Metrics")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Max Drawdown", f"{snapshot.get('max_drawdown_pct', 0):.2f}%")
        col2.metric("Deployed %", f"{snapshot.get('deployed_pct', 0):.1f}%")
        col3.metric(
            "Portfolio Correlation",
            f"{snapshot.get('portfolio_correlation', 0) or 0:.3f}",
        )
        col4.metric("Open Positions", snapshot.get("open_positions_count", 0))

        st.subheader("Circuit Breaker Status")
        try:
            from src.config import Settings
            settings = Settings()
            checks = {
                "Daily Loss Limit": {
                    "current": abs(snapshot.get("daily_pnl_pct", 0)),
                    "limit": settings.max_daily_loss_pct,
                },
                "Deployment Cap": {
                    "current": snapshot.get("deployed_pct", 0),
                    "limit": settings.max_portfolio_deployed_pct,
                },
                "Correlation Threshold": {
                    "current": abs(snapshot.get("portfolio_correlation", 0) or 0),
                    "limit": settings.max_correlation,
                },
            }
            for name, vals in checks.items():
                pct_used = (vals["current"] / vals["limit"] * 100) if vals["limit"] else 0
                status_icon = "\u2705" if pct_used < 80 else ("\u26A0\uFE0F" if pct_used < 100 else "\U0001F6D1")
                st.write(
                    f"{status_icon} **{name}**: {vals['current']:.2f} / {vals['limit']:.2f} "
                    f"({pct_used:.0f}% utilised)"
                )
        except Exception:
            st.warning("Could not load risk settings for circuit breaker display.")

        st.subheader("Risk Metrics Over Time")
        history = fetch_snapshot_history()
        if not history.empty:
            risk_cols = [
                c for c in ["daily_pnl_pct", "deployed_pct", "max_drawdown_pct"]
                if c in history.columns
            ]
            if risk_cols and "created_at" in history.columns:
                st.line_chart(history.set_index("created_at")[risk_cols])
    else:
        st.info("No portfolio snapshot data available.")


elif page == "Backtests":
    st.title("Backtest Results")
    st.info(
        "Backtest integration is coming soon. This page will display "
        "historical strategy performance, comparison charts, and "
        "parameter sensitivity analysis."
    )
