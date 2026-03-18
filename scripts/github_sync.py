"""Sync daily performance metrics to GitHub.

Queries the database for today's trades and portfolio state, writes a JSON
report to docs/performance/, and commits + pushes to GitHub.

Usage:
    python scripts/github_sync.py
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.config import Settings
from src.data.ingestion import DataIngestionService
from src.data.models import Trade, PortfolioSnapshot


def get_daily_report(session: Session) -> dict:
    """Build a daily performance report from the database."""
    today = datetime.now(timezone.utc).date()

    # Get today's trades
    trades = (
        session.query(Trade)
        .filter(Trade.created_at >= datetime(today.year, today.month, today.day, tzinfo=timezone.utc))
        .all()
    )

    # Get latest portfolio snapshot
    snapshot = (
        session.query(PortfolioSnapshot)
        .order_by(PortfolioSnapshot.created_at.desc())
        .first()
    )

    daily_pnl = DataIngestionService.get_daily_pnl(session)

    return {
        "date": today.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trades": {
            "count": len(trades),
            "details": [
                {
                    "market": t.ticker_or_market_id,
                    "side": t.side,
                    "quantity": t.quantity,
                    "price": float(t.price) if t.price else None,
                    "fill_price": float(t.fill_price) if t.fill_price else None,
                    "status": t.status,
                }
                for t in trades
            ],
        },
        "portfolio": {
            "total_value": float(snapshot.total_value) if snapshot else None,
            "daily_pnl": daily_pnl,
            "deployed_pct": float(snapshot.deployed_pct) if snapshot else None,
            "open_positions": snapshot.open_positions_count if snapshot else 0,
        },
    }


def main():
    settings = Settings()
    engine = create_engine(settings.timescaledb_url)

    with Session(engine) as session:
        report = get_daily_report(session)

    # Write report to docs/performance/
    perf_dir = Path("docs/performance")
    perf_dir.mkdir(parents=True, exist_ok=True)

    report_path = perf_dir / f"{report['date']}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"[+] Report written: {report_path}")

    # Git commit and push
    try:
        subprocess.run(["git", "add", str(report_path)], check=True)
        subprocess.run(
            ["git", "commit", "-m", f"perf: daily report {report['date']}"],
            check=True,
        )
        subprocess.run(["git", "push"], check=True)
        print("[+] Pushed to GitHub.")
    except subprocess.CalledProcessError as e:
        print(f"[-] Git operation failed: {e}")


if __name__ == "__main__":
    main()
