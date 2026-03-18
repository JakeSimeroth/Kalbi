"""
KALBI-2 Kalshi Prediction Market Tools.

CrewAI tool functions for interacting with the Kalshi exchange API.
Uses httpx for HTTP calls with RSA key signing, mirroring the auth
pattern from the existing kalshi_client.py.
"""

import base64
import hashlib
import json
import time
from datetime import datetime, timezone

import httpx
import structlog
from crewai.tools import tool
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, utils

from src.config import Settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_settings: Settings | None = None


def _get_settings() -> Settings:
    """Lazy-load settings so import-time env errors are avoided."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def _kalshi_base_url() -> str:
    """Return the correct Kalshi API base URL based on trading mode."""
    settings = _get_settings()
    if settings.paper_trading_mode:
        return "https://demo-api.kalshi.com/trade-api/v2"
    return "https://api.elections.kalshi.com/trade-api/v2"


def _load_private_key():
    """Load the RSA private key from the configured path."""
    settings = _get_settings()
    with open(settings.kalshi_private_key_path, "r") as f:
        pem_data = f.read()
    return serialization.load_pem_private_key(pem_data.encode(), password=None)


def _sign_request(method: str, path: str, timestamp_ms: int) -> str:
    """
    Create the RSA-PSS signature required by Kalshi API v2.

    The message to sign is: timestamp_ms + method + path
    """
    private_key = _load_private_key()
    message = f"{timestamp_ms}{method}{path}".encode()
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode()


def _kalshi_request(
    method: str,
    path: str,
    params: dict | None = None,
    body: dict | None = None,
) -> dict:
    """Execute an authenticated request against the Kalshi API."""
    settings = _get_settings()
    base_url = _kalshi_base_url()
    url = f"{base_url}{path}"
    timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    signature = _sign_request(method.upper(), path, timestamp_ms)

    headers = {
        "Content-Type": "application/json",
        "KALSHI-ACCESS-KEY": settings.kalshi_api_key_id,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": str(timestamp_ms),
    }

    with httpx.Client(timeout=30.0) as client:
        response = client.request(
            method=method.upper(),
            url=url,
            headers=headers,
            params=params,
            json=body,
        )
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# CrewAI Tools
# ---------------------------------------------------------------------------


@tool
def get_active_markets(category: str = "") -> str:
    """Fetch open Kalshi prediction markets, optionally filtered by category.

    Args:
        category: Category slug to filter by (e.g. 'politics', 'economics').
                  Leave empty to return all open markets.

    Returns:
        JSON string containing a list of open markets with their tickers,
        titles, prices, and volumes.
    """
    try:
        logger.info("kalshi.get_active_markets", category=category)
        params: dict = {"status": "open", "limit": 100}
        if category:
            params["category"] = category

        data = _kalshi_request("GET", "/markets", params=params)
        markets = data.get("markets", [])

        results = []
        for m in markets:
            results.append(
                {
                    "ticker": m.get("ticker"),
                    "title": m.get("title"),
                    "yes_ask": m.get("yes_ask"),
                    "yes_bid": m.get("yes_bid"),
                    "no_ask": m.get("no_ask"),
                    "no_bid": m.get("no_bid"),
                    "volume": m.get("volume"),
                    "open_interest": m.get("open_interest"),
                    "category": m.get("category"),
                    "close_time": m.get("close_time"),
                }
            )

        logger.info("kalshi.get_active_markets.done", count=len(results))
        return json.dumps(results, indent=2)

    except Exception as e:
        logger.error("kalshi.get_active_markets.error", error=str(e))
        return json.dumps({"error": str(e)})


@tool
def get_market_details(market_id: str) -> str:
    """Get detailed information for a specific Kalshi market including orderbook depth.

    Args:
        market_id: The Kalshi market ticker (e.g. 'PRES-2024-DEM').

    Returns:
        JSON string with market details: title, description, prices,
        volume, orderbook bids/asks, and resolution details.
    """
    try:
        logger.info("kalshi.get_market_details", market_id=market_id)

        # Fetch market info
        market_data = _kalshi_request("GET", f"/markets/{market_id}")

        # Fetch orderbook
        orderbook_data = _kalshi_request(
            "GET", f"/markets/{market_id}/orderbook", params={"depth": 10}
        )

        market = market_data.get("market", {})
        result = {
            "ticker": market.get("ticker"),
            "title": market.get("title"),
            "subtitle": market.get("subtitle"),
            "status": market.get("status"),
            "yes_ask": market.get("yes_ask"),
            "yes_bid": market.get("yes_bid"),
            "no_ask": market.get("no_ask"),
            "no_bid": market.get("no_bid"),
            "last_price": market.get("last_price"),
            "volume": market.get("volume"),
            "open_interest": market.get("open_interest"),
            "close_time": market.get("close_time"),
            "expiration_time": market.get("expiration_time"),
            "category": market.get("category"),
            "orderbook": orderbook_data.get("orderbook", {}),
        }

        logger.info("kalshi.get_market_details.done", market_id=market_id)
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error("kalshi.get_market_details.error", error=str(e))
        return json.dumps({"error": str(e)})


@tool
def get_market_candlesticks(market_id: str, period_interval: int = 60) -> str:
    """Fetch OHLCV candlestick data for a Kalshi market.

    Args:
        market_id: The Kalshi market ticker.
        period_interval: Candlestick period in minutes (default 60).

    Returns:
        JSON string with a list of candlesticks, each containing
        timestamp, open, high, low, close, and volume.
    """
    try:
        logger.info(
            "kalshi.get_market_candlesticks",
            market_id=market_id,
            period_interval=period_interval,
        )
        now_ts = int(datetime.now(timezone.utc).timestamp())
        start_ts = now_ts - (7 * 24 * 3600)  # Last 7 days

        params = {
            "start_ts": start_ts,
            "end_ts": now_ts,
            "period_interval": period_interval,
        }
        data = _kalshi_request(
            "GET", f"/markets/{market_id}/candlesticks", params=params
        )

        candles = []
        for c in data.get("candlesticks", []):
            candles.append(
                {
                    "timestamp": c.get("end_period_ts"),
                    "open": c.get("price", {}).get("open"),
                    "high": c.get("price", {}).get("high"),
                    "low": c.get("price", {}).get("low"),
                    "close": c.get("price", {}).get("close"),
                    "volume": c.get("volume"),
                }
            )

        logger.info(
            "kalshi.get_market_candlesticks.done", candle_count=len(candles)
        )
        return json.dumps(candles, indent=2)

    except Exception as e:
        logger.error("kalshi.get_market_candlesticks.error", error=str(e))
        return json.dumps({"error": str(e)})


@tool
def get_positions() -> str:
    """Get all current open positions on Kalshi.

    Returns:
        JSON string listing each open position with market ticker,
        side, quantity, average price, and market value.
    """
    try:
        logger.info("kalshi.get_positions")
        data = _kalshi_request("GET", "/portfolio/positions")

        positions = []
        for p in data.get("market_positions", []):
            positions.append(
                {
                    "ticker": p.get("ticker"),
                    "yes_count": p.get("yes_count"),
                    "no_count": p.get("no_count"),
                    "avg_yes_price": p.get("avg_yes_price"),
                    "avg_no_price": p.get("avg_no_price"),
                    "market_value": p.get("market_value"),
                }
            )

        logger.info("kalshi.get_positions.done", count=len(positions))
        return json.dumps(positions, indent=2)

    except Exception as e:
        logger.error("kalshi.get_positions.error", error=str(e))
        return json.dumps({"error": str(e)})


@tool
def place_kalshi_order(
    market_id: str, side: str, quantity: int, price: int
) -> str:
    """Place a limit order on Kalshi prediction market.

    Args:
        market_id: The Kalshi market ticker to trade.
        side: 'yes' or 'no' -- the side of the contract to buy.
        quantity: Number of contracts to buy.
        price: Limit price in cents (1-99).

    Returns:
        JSON string with the order confirmation or error details.
    """
    try:
        logger.info(
            "kalshi.place_order",
            market_id=market_id,
            side=side,
            quantity=quantity,
            price=price,
        )

        if side not in ("yes", "no"):
            return json.dumps({"error": "side must be 'yes' or 'no'"})
        if not (1 <= price <= 99):
            return json.dumps({"error": "price must be between 1 and 99 cents"})
        if quantity < 1:
            return json.dumps({"error": "quantity must be at least 1"})

        order_body = {
            "ticker": market_id,
            "action": "buy",
            "side": side,
            "count": quantity,
            "type": "limit",
            "yes_price": price if side == "yes" else None,
            "no_price": price if side == "no" else None,
        }
        # Remove None values
        order_body = {k: v for k, v in order_body.items() if v is not None}

        data = _kalshi_request("POST", "/portfolio/orders", body=order_body)

        order = data.get("order", {})
        result = {
            "order_id": order.get("order_id"),
            "ticker": order.get("ticker"),
            "side": order.get("side"),
            "count": order.get("count"),
            "price": order.get("yes_price") or order.get("no_price"),
            "status": order.get("status"),
            "created_time": order.get("created_time"),
        }

        logger.info(
            "kalshi.place_order.done", order_id=result.get("order_id")
        )
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error("kalshi.place_order.error", error=str(e))
        return json.dumps({"error": str(e)})
