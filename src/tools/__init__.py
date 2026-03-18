"""
KALBI-2 CrewAI Tools.

Central export point for every tool the KALBI-2 agents can use.
Import individual tools or use ``ALL_TOOLS`` for a flat list suitable
for passing directly to a CrewAI agent's ``tools`` parameter.

Category lists (e.g. ``kalshi_api_tools``) are preserved for backward
compatibility with existing agent modules.
"""

# -- Kalshi prediction-market tools ----------------------------------------
from src.tools.kalshi_api import (
    get_active_markets,
    get_market_candlesticks,
    get_market_details,
    get_positions as get_kalshi_positions,
    place_kalshi_order,
)

# -- Alpaca equities tools -------------------------------------------------
from src.tools.alpaca_api import (
    get_account_info,
    get_portfolio_history,
    get_stock_positions,
    get_stock_quote,
    place_stock_order,
)

# -- News / sentiment tools ------------------------------------------------
from src.tools.news_scraper import (
    scrape_rss_feeds,
    search_news,
    search_reddit,
)

# -- SEC EDGAR tools -------------------------------------------------------
from src.tools.sec_fetcher import (
    get_company_filings,
    get_filing_text,
)

# -- Market data (Yahoo Finance) -------------------------------------------
from src.tools.market_data import (
    get_market_overview,
    get_stock_fundamentals,
    get_stock_ohlcv,
)

# -- Sentiment analysis ----------------------------------------------------
from src.tools.sentiment_analyzer import analyze_sentiment

# -- Technical indicators --------------------------------------------------
from src.tools.technical_indicators import (
    calculate_indicators,
    detect_patterns,
)

# ---------------------------------------------------------------------------
# Category lists -- backward-compatible with the original placeholder module
# ---------------------------------------------------------------------------

kalshi_api_tools = [
    get_active_markets,
    get_market_details,
    get_market_candlesticks,
    get_kalshi_positions,
    place_kalshi_order,
]

alpaca_api_tools = [
    get_account_info,
    get_stock_positions,
    get_stock_quote,
    place_stock_order,
    get_portfolio_history,
]

news_scraper_tools = [
    search_news,
    scrape_rss_feeds,
    search_reddit,
]

sec_fetcher_tools = [
    get_company_filings,
    get_filing_text,
]

market_data_tools = [
    get_stock_ohlcv,
    get_stock_fundamentals,
    get_market_overview,
]

sentiment_analyzer_tools = [
    analyze_sentiment,
]

technical_indicators_tools = [
    calculate_indicators,
    detect_patterns,
]

# ---------------------------------------------------------------------------
# Flat collection -- pass this list to a CrewAI Agent's ``tools`` parameter
# ---------------------------------------------------------------------------

ALL_TOOLS = (
    kalshi_api_tools
    + alpaca_api_tools
    + news_scraper_tools
    + sec_fetcher_tools
    + market_data_tools
    + sentiment_analyzer_tools
    + technical_indicators_tools
)

__all__ = [
    # Individual tools
    "get_active_markets",
    "get_market_details",
    "get_market_candlesticks",
    "get_kalshi_positions",
    "place_kalshi_order",
    "get_account_info",
    "get_stock_positions",
    "get_stock_quote",
    "place_stock_order",
    "get_portfolio_history",
    "search_news",
    "scrape_rss_feeds",
    "search_reddit",
    "get_company_filings",
    "get_filing_text",
    "get_stock_ohlcv",
    "get_stock_fundamentals",
    "get_market_overview",
    "analyze_sentiment",
    "calculate_indicators",
    "detect_patterns",
    # Category lists
    "kalshi_api_tools",
    "alpaca_api_tools",
    "news_scraper_tools",
    "sec_fetcher_tools",
    "market_data_tools",
    "sentiment_analyzer_tools",
    "technical_indicators_tools",
    # Flat collection
    "ALL_TOOLS",
]
