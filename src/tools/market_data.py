"""
KALBI-2 Market Data Tools (Yahoo Finance).

CrewAI tool functions for fetching stock OHLCV data, fundamentals,
and market overview information via the Yahoo Finance v8 API.
No yfinance package required -- uses direct HTTP requests.
"""

import json
from datetime import datetime, timezone

import requests
import structlog
from crewai.tools import tool

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

YF_BASE = "https://query2.finance.yahoo.com"
YF_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

# Period -> seconds mapping for chart API
PERIOD_MAP = {
    "1d": "1d",
    "5d": "5d",
    "1mo": "1mo",
    "3mo": "3mo",
    "6mo": "6mo",
    "1y": "1y",
    "2y": "2y",
    "5y": "5y",
    "max": "max",
}

# Major indices and benchmark tickers
OVERVIEW_TICKERS = {
    "S&P 500": "^GSPC",
    "Dow Jones": "^DJI",
    "Nasdaq": "^IXIC",
    "Russell 2000": "^RUT",
    "VIX": "^VIX",
    "10Y Treasury Yield": "^TNX",
    "2Y Treasury Yield": "^IRX",
    "Gold": "GC=F",
    "Crude Oil": "CL=F",
    "USD Index": "DX-Y.NYB",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _yf_chart(symbol: str, period: str, interval: str) -> dict:
    """Fetch chart data from Yahoo Finance v8 chart API."""
    url = f"{YF_BASE}/v8/finance/chart/{symbol}"
    params = {
        "range": period,
        "interval": interval,
        "includePrePost": "false",
        "events": "",
    }
    resp = requests.get(url, headers=YF_HEADERS, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _yf_quote(symbols: list[str]) -> dict:
    """Fetch quote summary for one or more symbols."""
    url = f"{YF_BASE}/v7/finance/quote"
    params = {"symbols": ",".join(symbols)}
    resp = requests.get(url, headers=YF_HEADERS, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# CrewAI Tools
# ---------------------------------------------------------------------------


@tool
def get_stock_ohlcv(
    symbol: str, period: str = "1mo", interval: str = "1d"
) -> str:
    """Fetch OHLCV (Open-High-Low-Close-Volume) price data for a stock.

    Args:
        symbol: Ticker symbol (e.g. 'AAPL', 'TSLA', 'SPY').
        period: Date range -- '1d', '5d', '1mo', '3mo', '6mo',
                '1y', '2y', '5y', 'max'. Default '1mo'.
        interval: Candlestick interval -- '1m', '5m', '15m', '1h',
                  '1d', '1wk', '1mo'. Default '1d'.

    Returns:
        JSON string with a list of OHLCV candles, each containing
        date, open, high, low, close, and volume.
    """
    try:
        logger.info(
            "market_data.get_stock_ohlcv",
            symbol=symbol,
            period=period,
            interval=interval,
        )

        data = _yf_chart(symbol, period, interval)
        result_data = data.get("chart", {}).get("result", [])
        if not result_data:
            return json.dumps({"error": f"No data returned for {symbol}"})

        chart = result_data[0]
        timestamps = chart.get("timestamp", [])
        indicators = chart.get("indicators", {})
        quote = indicators.get("quote", [{}])[0]

        candles = []
        for i, ts in enumerate(timestamps):
            candles.append(
                {
                    "date": datetime.fromtimestamp(
                        ts, tz=timezone.utc
                    ).isoformat(),
                    "open": round(quote.get("open", [None])[i] or 0, 4),
                    "high": round(quote.get("high", [None])[i] or 0, 4),
                    "low": round(quote.get("low", [None])[i] or 0, 4),
                    "close": round(quote.get("close", [None])[i] or 0, 4),
                    "volume": quote.get("volume", [None])[i],
                }
            )

        logger.info(
            "market_data.get_stock_ohlcv.done", candle_count=len(candles)
        )
        return json.dumps(
            {"symbol": symbol, "period": period, "interval": interval, "candles": candles},
            indent=2,
        )

    except Exception as e:
        logger.error("market_data.get_stock_ohlcv.error", error=str(e))
        return json.dumps({"error": str(e)})


@tool
def get_stock_fundamentals(symbol: str) -> str:
    """Get key fundamental data for a stock including PE ratio, market cap, and revenue.

    Args:
        symbol: Ticker symbol (e.g. 'AAPL', 'MSFT', 'GOOGL').

    Returns:
        JSON string with fundamental metrics: PE ratio, forward PE,
        market cap, revenue, profit margins, EPS, dividend yield,
        52-week range, beta, and sector.
    """
    try:
        logger.info("market_data.get_stock_fundamentals", symbol=symbol)

        # Use the quoteSummary endpoint for rich fundamental data
        url = (
            f"{YF_BASE}/v10/finance/quoteSummary/{symbol}"
            f"?modules=summaryDetail,defaultKeyStatistics,"
            f"financialData,earningsQuarterlyGrowth"
        )
        resp = requests.get(url, headers=YF_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        quote_summary = data.get("quoteSummary", {}).get("result", [{}])[0]
        summary = quote_summary.get("summaryDetail", {})
        key_stats = quote_summary.get("defaultKeyStatistics", {})
        financial = quote_summary.get("financialData", {})

        def _raw(d: dict, key: str):
            """Extract raw value from Yahoo's nested format."""
            val = d.get(key, {})
            if isinstance(val, dict):
                return val.get("raw") or val.get("fmt")
            return val

        result = {
            "symbol": symbol,
            "market_cap": _raw(summary, "marketCap"),
            "pe_ratio": _raw(summary, "trailingPE"),
            "forward_pe": _raw(summary, "forwardPE"),
            "peg_ratio": _raw(key_stats, "pegRatio"),
            "price_to_book": _raw(key_stats, "priceToBook"),
            "eps_trailing": _raw(key_stats, "trailingEps"),
            "eps_forward": _raw(key_stats, "forwardEps"),
            "revenue": _raw(financial, "totalRevenue"),
            "revenue_growth": _raw(financial, "revenueGrowth"),
            "gross_margins": _raw(financial, "grossMargins"),
            "operating_margins": _raw(financial, "operatingMargins"),
            "profit_margins": _raw(financial, "profitMargins"),
            "return_on_equity": _raw(financial, "returnOnEquity"),
            "debt_to_equity": _raw(financial, "debtToEquity"),
            "current_price": _raw(financial, "currentPrice"),
            "target_mean_price": _raw(financial, "targetMeanPrice"),
            "recommendation": _raw(financial, "recommendationKey"),
            "dividend_yield": _raw(summary, "dividendYield"),
            "beta": _raw(summary, "beta"),
            "fifty_two_week_high": _raw(summary, "fiftyTwoWeekHigh"),
            "fifty_two_week_low": _raw(summary, "fiftyTwoWeekLow"),
            "fifty_day_avg": _raw(summary, "fiftyDayAverage"),
            "two_hundred_day_avg": _raw(summary, "twoHundredDayAverage"),
            "enterprise_value": _raw(key_stats, "enterpriseValue"),
            "ev_to_ebitda": _raw(key_stats, "enterpriseToEbitda"),
        }

        logger.info("market_data.get_stock_fundamentals.done", symbol=symbol)
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(
            "market_data.get_stock_fundamentals.error", error=str(e)
        )
        return json.dumps({"error": str(e)})


@tool
def get_market_overview() -> str:
    """Get a snapshot of major market indices, VIX, treasury yields, and commodities.

    Returns:
        JSON string with current prices, daily change, and percent change
        for S&P 500, Dow Jones, Nasdaq, Russell 2000, VIX, 10Y/2Y
        Treasury yields, Gold, Crude Oil, and USD Index.
    """
    try:
        logger.info("market_data.get_market_overview")
        symbols = list(OVERVIEW_TICKERS.values())
        data = _yf_quote(symbols)

        quotes = data.get("quoteResponse", {}).get("result", [])
        overview = {}
        for q in quotes:
            sym = q.get("symbol", "")
            # Find the friendly name
            name = sym
            for friendly, ticker in OVERVIEW_TICKERS.items():
                if ticker == sym:
                    name = friendly
                    break

            overview[name] = {
                "symbol": sym,
                "price": q.get("regularMarketPrice"),
                "change": q.get("regularMarketChange"),
                "change_pct": q.get("regularMarketChangePercent"),
                "previous_close": q.get("regularMarketPreviousClose"),
                "day_high": q.get("regularMarketDayHigh"),
                "day_low": q.get("regularMarketDayLow"),
                "market_time": q.get("regularMarketTime"),
            }

        logger.info(
            "market_data.get_market_overview.done",
            instruments=len(overview),
        )
        return json.dumps(overview, indent=2)

    except Exception as e:
        logger.error("market_data.get_market_overview.error", error=str(e))
        return json.dumps({"error": str(e)})
