"""
KALBI-2 Backtest Data Loader.

Provides static methods for loading OHLCV data from CSV files, Yahoo
Finance (via yfinance), and TimescaleDB (historical Kalshi market data).
All loaders return a ``pandas.DataFrame`` with a ``DatetimeIndex``.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd
import structlog

log = structlog.get_logger(__name__)


class DataLoader:
    """Utility class for loading historical market data.

    All methods are static and return a :class:`pandas.DataFrame` with
    a ``DatetimeIndex`` and at least the columns ``open``, ``high``,
    ``low``, ``close``, ``volume`` (where applicable).
    """

    # ------------------------------------------------------------------
    # CSV
    # ------------------------------------------------------------------

    @staticmethod
    def load_csv(filepath: str) -> pd.DataFrame:
        """Load OHLCV data from a CSV file.

        The CSV is expected to have a date / timestamp column that pandas
        can parse automatically, plus columns mappable to ``open``,
        ``high``, ``low``, ``close``, ``volume``.  Column names are
        normalised to lowercase.

        Args:
            filepath: Path to the CSV file.

        Returns:
            A ``DataFrame`` indexed by datetime with OHLCV columns.

        Raises:
            FileNotFoundError: If *filepath* does not exist.
            ValueError: If the required ``close`` column is missing.
        """
        log.info("data_loader.load_csv", filepath=filepath)

        df = pd.read_csv(filepath, parse_dates=True)
        df.columns = [c.strip().lower() for c in df.columns]

        # Attempt to find and set a datetime index.
        date_col: Optional[str] = None
        for candidate in ("date", "datetime", "timestamp", "time"):
            if candidate in df.columns:
                date_col = candidate
                break

        if date_col is not None:
            df[date_col] = pd.to_datetime(df[date_col])
            df.set_index(date_col, inplace=True)
        elif not isinstance(df.index, pd.DatetimeIndex):
            # Try to coerce the existing index to datetime.
            try:
                df.index = pd.to_datetime(df.index)
            except Exception:
                log.warning(
                    "data_loader.csv_no_datetime_index",
                    filepath=filepath,
                )

        if "close" not in df.columns:
            raise ValueError(
                f"CSV at {filepath} must contain a 'close' column. "
                f"Found columns: {list(df.columns)}"
            )

        df.sort_index(inplace=True)
        log.info(
            "data_loader.csv_loaded",
            rows=len(df),
            columns=list(df.columns),
        )
        return df

    # ------------------------------------------------------------------
    # Yahoo Finance
    # ------------------------------------------------------------------

    @staticmethod
    def fetch_yahoo(
        symbol: str,
        start: str,
        end: str,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data from Yahoo Finance via *yfinance*.

        Args:
            symbol: Ticker symbol (e.g. ``"AAPL"``).
            start: Start date string (e.g. ``"2023-01-01"``).
            end: End date string (e.g. ``"2024-01-01"``).
            interval: Bar interval -- one of ``"1m"``, ``"5m"``,
                ``"15m"``, ``"1h"``, ``"1d"``, ``"1wk"``, ``"1mo"``.

        Returns:
            A ``DataFrame`` indexed by datetime with OHLCV columns
            (lowercase).

        Raises:
            ImportError: If *yfinance* is not installed.
            ValueError: If Yahoo Finance returns no data for the
                requested range.
        """
        try:
            import yfinance as yf
        except ImportError as exc:
            raise ImportError(
                "yfinance is required to fetch Yahoo Finance data. "
                "Install it with: pip install yfinance"
            ) from exc

        log.info(
            "data_loader.fetch_yahoo",
            symbol=symbol,
            start=start,
            end=end,
            interval=interval,
        )

        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, end=end, interval=interval)

        if df.empty:
            raise ValueError(
                f"No data returned from Yahoo Finance for {symbol} "
                f"({start} to {end}, interval={interval})."
            )

        # Normalise column names to lowercase.
        df.columns = [c.strip().lower() for c in df.columns]

        # Keep only the core OHLCV columns if present.
        keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
        df = df[keep]

        df.sort_index(inplace=True)
        log.info(
            "data_loader.yahoo_loaded",
            symbol=symbol,
            rows=len(df),
        )
        return df

    # ------------------------------------------------------------------
    # TimescaleDB (Kalshi history)
    # ------------------------------------------------------------------

    @staticmethod
    def load_kalshi_history(
        market_id: str,
        db_session: Any,
    ) -> pd.DataFrame:
        """Load historical Kalshi market data from TimescaleDB.

        Queries the ``signals`` table for rows matching *market_id* and
        pivots them into a time-series ``DataFrame`` suitable for
        backtesting.  The returned frame has columns ``close``
        (representing the latest signal strength or price snapshot) and
        ``volume`` (set to 1 per row as a placeholder).

        Args:
            market_id: The Kalshi market identifier (e.g.
                ``"KXBTC-24MAR14"``).
            db_session: A SQLAlchemy ``Session`` connected to the
                TimescaleDB instance.

        Returns:
            A ``DataFrame`` indexed by datetime with at least a
            ``close`` column.

        Raises:
            ValueError: If no rows are found for *market_id*.
        """
        from sqlalchemy import text

        log.info(
            "data_loader.load_kalshi_history",
            market_id=market_id,
        )

        query = text(
            "SELECT created_at, strength AS close "
            "FROM signals "
            "WHERE ticker_or_market_id = :market_id "
            "ORDER BY created_at ASC"
        )

        result = db_session.execute(
            query, {"market_id": market_id}
        )
        rows = result.fetchall()

        if not rows:
            raise ValueError(
                f"No historical data found for Kalshi market {market_id}."
            )

        df = pd.DataFrame(rows, columns=["timestamp", "close"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
        df["volume"] = 1  # placeholder

        log.info(
            "data_loader.kalshi_loaded",
            market_id=market_id,
            rows=len(df),
        )
        return df
