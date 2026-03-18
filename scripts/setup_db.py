"""Initialize TimescaleDB schema for KALBI-2.

Usage:
    python scripts/setup_db.py
"""
import sys
sys.path.insert(0, ".")

from sqlalchemy import create_engine, text
from src.config import Settings
from src.data.models import create_tables


def setup_database():
    settings = Settings()
    engine = create_engine(settings.timescaledb_url)

    # Create all ORM tables
    create_tables(engine)
    print("[+] Tables created.")

    # Enable TimescaleDB extension and convert to hypertables
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
        conn.commit()
        print("[+] TimescaleDB extension enabled.")

        hypertables = ["trades", "signals", "agent_decisions", "portfolio_snapshots"]
        for table in hypertables:
            try:
                conn.execute(text(
                    f"SELECT create_hypertable('{table}', 'created_at', "
                    f"if_not_exists => TRUE, migrate_data => TRUE)"
                ))
                conn.commit()
                print(f"[+] Hypertable: {table}")
            except Exception as e:
                print(f"[~] Hypertable {table}: {e}")

        # Create continuous aggregates for portfolio snapshots (hourly)
        try:
            conn.execute(text("""
                CREATE MATERIALIZED VIEW IF NOT EXISTS portfolio_hourly
                WITH (timescaledb.continuous) AS
                SELECT
                    time_bucket('1 hour', created_at) AS bucket,
                    AVG(total_value) AS avg_value,
                    MAX(total_value) AS max_value,
                    MIN(total_value) AS min_value,
                    LAST(daily_pnl, created_at) AS last_pnl
                FROM portfolio_snapshots
                GROUP BY bucket
            """))
            conn.commit()
            print("[+] Continuous aggregate: portfolio_hourly")
        except Exception as e:
            print(f"[~] Continuous aggregate: {e}")

    engine.dispose()
    print("[+] Database setup complete!")


if __name__ == "__main__":
    setup_database()
