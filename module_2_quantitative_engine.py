import pandas as pd
import talib as ta
from sqlalchemy import create_engine, text
import time

import config
from kalshi_client import KalshiTraderAPI

class QuantitativeEngine:
    """
    Module 2: The "Quantitative Brain".
    Manages historical market data in TimescaleDB and calculates
    technical "graph trend" features using TA-Lib.
    """
    def __init__(self):
        self.db_engine = create_engine(config.TIMESCALEDB_URI)
        self._create_candlestick_table()

    def _create_candlestick_table(self):
        """Ensures the candlestick table (hypertable) exists in Timescaledb."""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS market_candlesticks (
            timestamp TIMESTAMPTZ NOT NULL,
            ticker TEXT NOT NULL,
            open DOUBLE PRECISION,
            high DOUBLE PRECISION,
            low DOUBLE PRECISION,
            close DOUBLE PRECISION,
            volume BIGINT,
            PRIMARY KEY (timestamp, ticker)
        );
        """
        # Convert to Hypertable (TimescaleDB's special sauce)
        create_hypertable_sql = "SELECT create_hypertable('market_candlesticks', 'timestamp', if_not_exists => TRUE);"
        
        try:
            with self.db_engine.connect() as conn:
                conn.execute(text(create_table_sql))
                conn.execute(text(create_hypertable_sql))
                conn.commit()
            print("TimescaleDB 'market_candlesticks' hypertable verified.")
        except Exception as e:
            print(f"Error initializing TimescaleDB: {e}")

    def update_market_data(self, kalshi_api: KalshiTraderAPI, ticker: str):
        """
        Fetches the latest candlestick data from Kalshi and
        saves it to our TimescaleDB.
        """
        print(f"Module 2: Updating market data for {ticker}...")
        try:
            with self.db_engine.connect() as conn:
                # Get the last timestamp we have for this ticker
                last_ts_query = text("SELECT MAX(timestamp) FROM market_candlesticks WHERE ticker = :ticker")
                result = conn.execute(last_ts_query, {'ticker': ticker}).scalar()
                
                start_ts = int(result.timestamp()) if result else int(time.time()) - (86400 * 30) # 30 days ago
                end_ts = int(time.time())

                if start_ts >= end_ts - 60:
                    print("Data is up to date.")
                    return

                # Fetch new data from Kalshi [62]
                df = kalshi_api.get_market_candlesticks(ticker, start_ts, end_ts, period=60)
                
                if df.empty:
                    return

                # Append new data to TimescaleDB
                df_to_sql = df.reset_index()
                df_to_sql['ticker'] = ticker
                df_to_sql.to_sql('market_candlesticks', self.db_engine, if_exists='append', index=False, method='multi')
                print(f"Module 2: Saved {len(df)} new candlesticks for {ticker}.")

        except Exception as e:
            print(f"Error updating market data: {e}")

    def calculate_features(self, ticker: str, market_expiration_ts: int) -> dict:
        """
        Calculates all quantitative features for a market from the database.
        This is the "powerful data analyst algorithm".
        """
        print(f"Module 2: Calculating TA features for {ticker}...")
        try:
            with self.db_engine.connect() as conn:
                query = text("SELECT * FROM market_candlesticks WHERE ticker = :ticker ORDER BY timestamp")
                df = pd.read_sql(query, conn, params={'ticker': ticker}, index_col='timestamp')

            if df.empty:
                return {}

            # 1. TA-Lib "Graph Trend" Indicators [72, 48]
            features = {}
            features['rsi_14'] = ta.RSI(df['close'], timeperiod=14).iloc[-1]
            macd, macdsignal, _ = ta.MACD(df['close'], fastperiod=12, slowperiod=26, signalperiod=9)
            features['macd_hist'] = (macd - macdsignal).iloc[-1]
            
            # 2. Price/Volume Analysis [74, 75, 76]
            features['obv'] = ta.OBV(df['close'], df['volume']).iloc[-1]
            features['volume_sma_5'] = ta.SMA(df['volume'].astype(float), timeperiod=5).iloc[-1]
            
            # 3. Time-to-Expiration (Crucial for event markets) [77, 78]
            hours_remaining = (market_expiration_ts - int(time.time())) / 3600
            features['hours_to_expiration'] = max(0, hours_remaining)

            return features
        except Exception as e:
            print(f"Error calculating TA features: {e}")
            return {}