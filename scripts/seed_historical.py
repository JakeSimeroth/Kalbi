"""Seed historical market data for backtesting.

Usage:
    python scripts/seed_historical.py --tickers AAPL,MSFT,GOOGL --days 365
    python scripts/seed_historical.py --tickers SPY --days 90 --interval 1h
"""
import argparse
import sys
from datetime import datetime, timedelta

sys.path.insert(0, ".")

import pandas as pd
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.config import Settings


def fetch_yahoo_data(symbol: str, start: str, end: str, interval: str = "1d") -> pd.DataFrame:
    """Fetch OHLCV data from Yahoo Finance v8 API."""
    # Use yfinance-compatible URL
    period_map = {"1d": "1d", "1h": "1h", "5m": "5m", "15m": "15m", "30m": "30m"}
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {
        "period1": int(pd.Timestamp(start).timestamp()),
        "period2": int(pd.Timestamp(end).timestamp()),
        "interval": period_map.get(interval, "1d"),
    }
    headers = {"User-Agent": "Mozilla/5.0"}

    resp = requests.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()["chart"]["result"][0]

    timestamps = data["timestamp"]
    quotes = data["indicators"]["quote"][0]

    df = pd.DataFrame({
        "timestamp": pd.to_datetime(timestamps, unit="s"),
        "open": quotes["open"],
        "high": quotes["high"],
        "low": quotes["low"],
        "close": quotes["close"],
        "volume": quotes["volume"],
    })
    df["symbol"] = symbol
    df = df.dropna(subset=["close"])
    return df


def main():
    parser = argparse.ArgumentParser(description="Seed historical market data")
    parser.add_argument("--tickers", required=True, help="Comma-separated ticker symbols")
    parser.add_argument("--days", type=int, default=365, help="Number of days of history")
    parser.add_argument("--interval", default="1d", help="Data interval (1d, 1h, 5m)")
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",")]
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")

    settings = Settings()
    engine = create_engine(settings.timescaledb_url)

    for ticker in tickers:
        print(f"[*] Fetching {ticker} ({start} to {end}, {args.interval})...")
        try:
            df = fetch_yahoo_data(ticker, start, end, args.interval)
            df.to_sql("historical_ohlcv", engine, if_exists="append", index=False)
            print(f"[+] {ticker}: {len(df)} bars stored.")
        except Exception as e:
            print(f"[-] {ticker}: Failed - {e}")

    engine.dispose()
    print("[+] Seeding complete!")


if __name__ == "__main__":
    main()
