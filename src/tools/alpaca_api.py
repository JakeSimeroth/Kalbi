"""
KALBI-2 Alpaca Equities Trading Tools.

CrewAI tool functions for interacting with the Alpaca brokerage API.
Uses the alpaca-py SDK for account management, positions, quotes,
order placement, and portfolio history.
"""

import json

import structlog
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import (
    GetPortfolioHistoryRequest,
    LimitOrderRequest,
    MarketOrderRequest,
)
from crewai.tools import tool

from src.config import Settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_settings: Settings | None = None
_trading_client: TradingClient | None = None
_data_client: StockHistoricalDataClient | None = None


def _get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def _get_trading_client() -> TradingClient:
    """Lazy-initialise the Alpaca TradingClient."""
    global _trading_client
    if _trading_client is None:
        settings = _get_settings()
        _trading_client = TradingClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_api_secret,
            paper=settings.paper_trading_mode,
        )
    return _trading_client


def _get_data_client() -> StockHistoricalDataClient:
    """Lazy-initialise the Alpaca StockHistoricalDataClient."""
    global _data_client
    if _data_client is None:
        settings = _get_settings()
        _data_client = StockHistoricalDataClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_api_secret,
        )
    return _data_client


# ---------------------------------------------------------------------------
# CrewAI Tools
# ---------------------------------------------------------------------------


@tool
def get_account_info() -> str:
    """Get Alpaca brokerage account information including balance and buying power.

    Returns:
        JSON string with account_id, cash balance, buying_power,
        portfolio_value, equity, and account status.
    """
    try:
        logger.info("alpaca.get_account_info")
        client = _get_trading_client()
        account = client.get_account()

        result = {
            "account_id": str(account.id),
            "status": str(account.status),
            "cash": str(account.cash),
            "buying_power": str(account.buying_power),
            "portfolio_value": str(account.portfolio_value),
            "equity": str(account.equity),
            "long_market_value": str(account.long_market_value),
            "short_market_value": str(account.short_market_value),
            "initial_margin": str(account.initial_margin),
            "maintenance_margin": str(account.maintenance_margin),
            "daytrade_count": account.daytrade_count,
            "pattern_day_trader": account.pattern_day_trader,
        }

        logger.info("alpaca.get_account_info.done")
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error("alpaca.get_account_info.error", error=str(e))
        return json.dumps({"error": str(e)})


@tool
def get_stock_positions() -> str:
    """Get all current open stock positions from Alpaca.

    Returns:
        JSON string listing each position with symbol, quantity,
        average entry price, current price, market value, and P&L.
    """
    try:
        logger.info("alpaca.get_positions")
        client = _get_trading_client()
        positions = client.get_all_positions()

        results = []
        for p in positions:
            results.append(
                {
                    "symbol": p.symbol,
                    "qty": str(p.qty),
                    "side": str(p.side),
                    "avg_entry_price": str(p.avg_entry_price),
                    "current_price": str(p.current_price),
                    "market_value": str(p.market_value),
                    "unrealized_pl": str(p.unrealized_pl),
                    "unrealized_plpc": str(p.unrealized_plpc),
                    "change_today": str(p.change_today),
                }
            )

        logger.info("alpaca.get_positions.done", count=len(results))
        return json.dumps(results, indent=2)

    except Exception as e:
        logger.error("alpaca.get_positions.error", error=str(e))
        return json.dumps({"error": str(e)})


@tool
def get_stock_quote(symbol: str) -> str:
    """Get the latest real-time quote for a stock ticker.

    Args:
        symbol: The stock ticker symbol (e.g. 'AAPL', 'TSLA').

    Returns:
        JSON string with the latest bid, ask, bid_size, ask_size,
        and timestamp for the given symbol.
    """
    try:
        logger.info("alpaca.get_stock_quote", symbol=symbol)
        client = _get_data_client()
        request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        quotes = client.get_stock_latest_quote(request)

        quote = quotes.get(symbol)
        if quote is None:
            return json.dumps({"error": f"No quote found for {symbol}"})

        result = {
            "symbol": symbol,
            "bid_price": float(quote.bid_price),
            "ask_price": float(quote.ask_price),
            "bid_size": quote.bid_size,
            "ask_size": quote.ask_size,
            "timestamp": str(quote.timestamp),
        }

        logger.info("alpaca.get_stock_quote.done", symbol=symbol)
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error("alpaca.get_stock_quote.error", error=str(e))
        return json.dumps({"error": str(e)})


@tool
def place_stock_order(
    symbol: str,
    qty: float,
    side: str,
    order_type: str = "limit",
    limit_price: float = None,
) -> str:
    """Place a stock order on Alpaca (market or limit).

    Args:
        symbol: The stock ticker symbol to trade (e.g. 'AAPL').
        qty: Number of shares to buy or sell (supports fractional).
        side: 'buy' or 'sell'.
        order_type: 'market' or 'limit' (default 'limit').
        limit_price: Required for limit orders. Price per share in dollars.

    Returns:
        JSON string with order confirmation including order_id, status,
        filled_qty, and submitted timestamp.
    """
    try:
        logger.info(
            "alpaca.place_order",
            symbol=symbol,
            qty=qty,
            side=side,
            order_type=order_type,
            limit_price=limit_price,
        )

        if side not in ("buy", "sell"):
            return json.dumps({"error": "side must be 'buy' or 'sell'"})

        order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
        client = _get_trading_client()

        if order_type == "market":
            request = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=TimeInForce.DAY,
            )
        elif order_type == "limit":
            if limit_price is None:
                return json.dumps(
                    {"error": "limit_price is required for limit orders"}
                )
            request = LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=TimeInForce.DAY,
                limit_price=limit_price,
            )
        else:
            return json.dumps(
                {"error": f"Unsupported order_type: {order_type}"}
            )

        order = client.submit_order(request)

        result = {
            "order_id": str(order.id),
            "symbol": order.symbol,
            "side": str(order.side),
            "qty": str(order.qty),
            "order_type": str(order.order_type),
            "limit_price": str(order.limit_price) if order.limit_price else None,
            "status": str(order.status),
            "filled_qty": str(order.filled_qty),
            "submitted_at": str(order.submitted_at),
        }

        logger.info("alpaca.place_order.done", order_id=result["order_id"])
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error("alpaca.place_order.error", error=str(e))
        return json.dumps({"error": str(e)})


@tool
def get_portfolio_history(period: str = "1D") -> str:
    """Get Alpaca portfolio P&L history over a given period.

    Args:
        period: Time period -- '1D' (1 day), '1W' (1 week), '1M' (1 month),
                '3M' (3 months), '1A' (1 year). Default '1D'.

    Returns:
        JSON string with arrays of timestamps, equity values, and
        profit_loss values over the requested period.
    """
    try:
        logger.info("alpaca.get_portfolio_history", period=period)
        client = _get_trading_client()

        request = GetPortfolioHistoryRequest(period=period)
        history = client.get_portfolio_history(request)

        result = {
            "timestamps": [str(t) for t in (history.timestamp or [])],
            "equity": [float(e) for e in (history.equity or [])],
            "profit_loss": [float(p) for p in (history.profit_loss or [])],
            "profit_loss_pct": [
                float(p) for p in (history.profit_loss_pct or [])
            ],
            "base_value": float(history.base_value) if history.base_value else None,
            "timeframe": str(history.timeframe) if history.timeframe else None,
        }

        logger.info(
            "alpaca.get_portfolio_history.done",
            data_points=len(result["timestamps"]),
        )
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error("alpaca.get_portfolio_history.error", error=str(e))
        return json.dumps({"error": str(e)})
