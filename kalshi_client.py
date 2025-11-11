import pandas as pd
from kalshi_python import Configuration, KalshiClient
from kalshi_python.models import Market, Order # Import necessary models

import config

class KalshiTraderAPI:
    """
    A dedicated wrapper for all Kalshi API interactions.
    Handles authentication and switches between Demo and Live environments.
    """
    def __init__(self):
        self.client = self._create_client()
        print(f"Kalshi client initialized in '{config.TRADING_MODE}' mode.")

    def _create_client(self):
        """Initializes the KalshiClient based on the TRADING_MODE."""
        if config.TRADING_MODE == 'DEMO':
            host = "https://demo-api.kalshi.com/trade-api/v2"
        else:
            host = "https://api.elections.kalshi.com/trade-api/v2" [59]
        
        cfg = Configuration(host=host)
        
        # Load private key for authenticated requests 
        try:
            with open(config.KALSHI_PRIVATE_KEY_PATH, "r") as f:
                private_key = f.read()
            cfg.api_key_id = config.KALSHI_API_KEY_ID
            cfg.private_key_pem = private_key
        except Exception as e:
            print(f"Warning: Could not load private key. Authenticated endpoints will fail. {e}")
            
        return KalshiClient(cfg)

    def get_politics_markets(self) -> list[Market]:
        """
        Fetches all 'open' markets in the target 'Politics' category.
        This directly implements the user's first requirement.
        """
        print(f"Fetching open markets for category: '{config.TARGET_CATEGORY}'...")
        try:
            # First, get all series (templates) for the Politics category [60, 59]
            series_response = self.client.get_series_list(
                category=config.TARGET_CATEGORY
            )
            
            politics_series_tickers = [s.ticker for s in series_response.series]
            
            if not politics_series_tickers:
                print(f"No series found for category '{config.TARGET_CATEGORY}'.")
                return

            # Now, get all 'open' markets for those series tickers [59, 61]
            markets =
            for ticker in politics_series_tickers:
                market_response = self.client.get_markets(
                    series_ticker=ticker,
                    status='open' # Only get currently tradable markets
                )
                markets.extend(market_response.markets)
            
            print(f"Found {len(markets)} open politics markets.")
            return markets
        except Exception as e:
            print(f"Error fetching politics markets: {e}")
            return

    def get_market_candlesticks(self, ticker: str, start_ts: int, end_ts: int, period: int = 60) -> pd.DataFrame:
        """
        Fetches the "graph trends" (OHLCV candlestick data) for a market. [62]
        """
        try:
            response = self.client.get_market_candlesticks(
                ticker=ticker,
                start_ts=start_ts,
                end_ts=end_ts,
                period_interval=period # 60 minutes
            )
            
            # Convert list of candlestick objects to a DataFrame
            data =
            for candle in response.candlesticks:
                data.append({
                    'timestamp': pd.to_datetime(candle.end_period_ts, unit='s'),
                    'open': candle.price.open,
                    'high': candle.price.high,
                    'low': candle.price.low,
                    'close': candle.price.close,
                    'volume': candle.volume
                })
            
            if not data:
                return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            df = pd.DataFrame(data).set_index('timestamp')
            return df
        except Exception as e:
            print(f"Error fetching candlesticks for {ticker}: {e}")
            return pd.DataFrame()

    def place_order(self, ticker: str, side: str, count: int, price: int):
        """Places a limit order on the exchange."""
        if config.TRADING_MODE == 'DEMO':
            print(f" Placing order: {side} {count} contracts of {ticker} @ {price} cents.")
            # In a real 'LIVE' scenario, you would remove the check.
            # This is a safety guard.
            return
            
        print(f"[LIVE] Placing order: {side} {count} contracts of {ticker} @ {price} cents.")
        try:
            order = Order(
                ticker=ticker,
                side=side,
                count=count,
                type='limit',
                yes_price=price if side == 'yes' else None,
                no_price=price if side == 'no' else None
            )
            response = self.client.create_order(order=order)
            print(f"Order placed successfully. Order ID: {response.order.order_id}")
        except Exception as e:
            print(f"Error placing order: {e}")