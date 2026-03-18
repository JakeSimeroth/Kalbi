# KALBI-2 Architecture

> Autonomous Multi-Agent Trading System for Prediction Markets and Equities

## System Overview

KALBI-2 is a multi-agent trading system that uses CrewAI to orchestrate autonomous
agents across two asset classes: Kalshi prediction markets and US equities (via
Alpaca). The system runs on a fixed schedule driven by APScheduler, with three
independent crews executing analysis-to-execution pipelines at different intervals.

```
┌─────────────────────────────────────────────────────────┐
│                    APScheduler                           │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Kalshi   │  │  Equities    │  │    Meta Crew     │  │
│  │ Crew     │  │  Crew        │  │  (Portfolio Mgr) │  │
│  │ (15 min) │  │  (30 min)    │  │  (2 hr)          │  │
│  └────┬─────┘  └──────┬───────┘  └────────┬─────────┘  │
│       │               │                    │            │
│  ┌────┴───────────────┴────────────────────┴─────────┐  │
│  │              Agent Layer (CrewAI)                  │  │
│  │  News Analyst | Quant | Fundamentals | Kalshi     │  │
│  │  Risk Manager | Executor                          │  │
│  └────┬───────────────┬────────────────────┬─────────┘  │
│       │               │                    │            │
│  ┌────┴───────────────┴────────────────────┴─────────┐  │
│  │              Tool Layer                            │  │
│  │  Kalshi API | Alpaca API | News Scraper | SEC     │  │
│  │  Market Data | Sentiment | Technical Indicators   │  │
│  └────┬───────────────┬────────────────────┬─────────┘  │
│       │               │                    │            │
│  ┌────┴──────┐  ┌─────┴──────┐  ┌─────────┴──────────┐ │
│  │TimescaleDB│  │   Redis    │  │ Risk Engine         │ │
│  │           │  │   Cache    │  │ Position Sizer      │ │
│  │           │  │            │  │ Circuit Breaker     │ │
│  └───────────┘  └────────────┘  └────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Components

### Crews (Orchestration)

Crews are the top-level orchestration unit. Each crew assembles a pipeline of
agents that pass context from one stage to the next, culminating in a trade
decision or portfolio action.

| Crew | Interval | Hours | Pipeline |
|---|---|---|---|
| **KalshiCrew** | 15 min | 24/7 | News Analyst -> Kalshi Specialist -> Risk Manager -> Executor |
| **EquitiesCrew** | 30 min | 9:30 AM - 4:00 PM ET, Mon-Fri | News Analyst -> Fundamentals Analyst -> Quant Analyst -> Risk Manager -> Executor |
| **MetaCrew** | 2 hr | 24/7 | Portfolio-level review: cross-asset correlation, rebalancing, agent performance evaluation |

Additional scheduled jobs:
- **Portfolio Snapshot**: Every 5 minutes -- records portfolio state to TimescaleDB.
- **Daily Summary**: 5:00 PM ET -- compiles end-of-day report and sends via Telegram.

### Agents (Decision Makers)

Each agent is a CrewAI `Agent` instance created by a factory function in `src/agents/`.
Agents are stateless -- all persistent state lives in the database.

| Agent | Role | Responsibilities | Tools |
|---|---|---|---|
| **News Analyst** | Senior News Analyst | Real-time news monitoring, event detection, narrative-driven sentiment analysis. Separates signal from noise across dozens of sources. | `search_news`, `scrape_rss_feeds`, `search_reddit`, `analyze_sentiment` |
| **Quant Analyst** | Quantitative Analyst | Technical and statistical analysis. Generates actionable signals from MACD, RSI, Bollinger Bands, and volume patterns. Skeptical of signals without backtested evidence. | `get_stock_ohlcv`, `get_stock_fundamentals`, `get_market_overview`, `calculate_indicators`, `detect_patterns` |
| **Fundamentals Analyst** | Fundamentals Research Analyst | Evaluates company health, earnings trajectory, cash flow sustainability, and macro positioning. Reviews SEC filings (10-Ks, 10-Qs). | `get_company_filings`, `get_filing_text`, `get_stock_ohlcv`, `get_stock_fundamentals`, `get_market_overview`, `search_news`, `scrape_rss_feeds`, `search_reddit` |
| **Kalshi Specialist** | Prediction Market Specialist | Probability estimation on Kalshi event contracts. Identifies mispricings by comparing estimated probability to market price using Bayesian reasoning. | `get_active_markets`, `get_market_details`, `get_market_candlesticks`, `get_kalshi_positions`, `place_kalshi_order`, `search_news`, `scrape_rss_feeds`, `search_reddit`, `analyze_sentiment`, `get_stock_ohlcv`, `get_stock_fundamentals`, `get_market_overview` |
| **Risk Manager** | Chief Risk Officer | Capital protection. Enforces position-size limits, correlation thresholds, deployment caps, and daily loss limits. Has VETO POWER over any proposed trade. | `get_stock_ohlcv`, `get_stock_fundamentals`, `get_market_overview`, `get_account_info`, `get_stock_positions`, `get_stock_quote`, `place_stock_order`, `get_portfolio_history`, `get_active_markets`, `get_market_details`, `get_market_candlesticks`, `get_kalshi_positions`, `place_kalshi_order` |
| **Executor** | Trade Executor | Order submission to Kalshi and Alpaca. Confirms fills, logs execution details. Uses limit orders by default. Only executes trades approved by Risk Manager. | `get_active_markets`, `get_market_details`, `get_market_candlesticks`, `get_kalshi_positions`, `place_kalshi_order`, `get_account_info`, `get_stock_positions`, `get_stock_quote`, `place_stock_order`, `get_portfolio_history` |

### Tools (API Wrappers)

Tools are thin wrappers around external APIs, exposed as CrewAI-compatible callables.
Each tool handles authentication, error handling, and response normalization.

| Tool Module | Functions | Data Source | Purpose |
|---|---|---|---|
| `kalshi_api` | `get_active_markets`, `get_market_details`, `get_market_candlesticks`, `get_positions`, `place_kalshi_order` | Kalshi REST API | Prediction market data and order execution |
| `alpaca_api` | `get_account_info`, `get_stock_positions`, `get_stock_quote`, `place_stock_order`, `get_portfolio_history` | Alpaca REST API | Equities account, positions, quotes, and order execution |
| `news_scraper` | `search_news`, `scrape_rss_feeds`, `search_reddit` | NewsAPI, RSS, Reddit | Real-time news aggregation from multiple channels |
| `sec_fetcher` | `get_company_filings`, `get_filing_text` | SEC EDGAR | Public company filings (10-K, 10-Q, 8-K) |
| `market_data` | `get_stock_ohlcv`, `get_stock_fundamentals`, `get_market_overview` | Yahoo Finance | OHLCV bars, fundamental metrics, market overview |
| `sentiment_analyzer` | `analyze_sentiment` | NLP pipeline | Text sentiment scoring with confidence |
| `technical_indicators` | `calculate_indicators`, `detect_patterns` | Computed from OHLCV | MACD, RSI, Bollinger Bands, volume analysis, candlestick patterns |

### Strategies

Strategies live in `src/strategies/` and encapsulate the quantitative logic for
generating trading signals. Each strategy exposes a `generate_signal()` or
`evaluate()` method that returns a structured signal dictionary.

#### KalshiEventArb (`kalshi_event_arb.py`)
Event-driven probability estimation strategy for Kalshi markets. Compares an
internally estimated probability (from the fundamental forecaster and ensemble)
against the current market price. Signals `buy_yes` or `buy_no` when the edge
exceeds a configurable threshold (default 8 cents). Requires minimum composite
confidence of 0.6 before acting. Composite confidence blends model certainty
(distance from 0.5) at 60% weight with news sentiment confidence at 40% weight.

#### Momentum (`momentum.py`)
Trend-following strategy for equities using three confluence factors: MACD
crossover direction, RSI confirmation (above/below 50 with extremity bonus),
and volume confirmation (current volume vs. SMA). All three must agree for a
strong signal; partial agreement yields moderate strength. Entry threshold
defaults to 0.6. Stop-loss at 1.5x ATR; take-profit at 2.5x ATR (risk-reward
~1:1.67).

#### MeanReversion (`mean_reversion.py`)
RSI extreme detection combined with Bollinger Band breach. Enters long when
price closes below the lower Bollinger Band AND RSI < 30; enters short when
above the upper band AND RSI > 70. Signal strength is derived from band
penetration depth and RSI extremity. Take-profit target is the middle Bollinger
Band (the mean). Stop-loss at 2x ATR beyond entry.

#### Ensemble (`ensemble.py`)
Weighted combination of all signal sources using configurable weights:
- Fundamental: 40%
- Momentum: 25%
- Mean Reversion: 15%
- Volume: 10%
- Time Decay: 10%

Applies a Kelly-inspired confidence adjustment that pulls extreme predictions
toward 0.5 proportional to ensemble disagreement. Output is clamped to
[0.05, 0.95] -- the system never expresses absolute certainty. Confidence is
computed as a blend of directional agreement (70%) and upstream model confidence
(30%).

### Risk Management

The risk layer sits between the agent decision and order execution. Every
proposed trade must pass through the circuit breaker before reaching the
executor.

#### PositionSizer (`src/risk/position_sizer.py`)
Multi-method position sizing calculator with three algorithms:
- **Kelly Criterion**: Quarter-Kelly by default. Caps at 25% of portfolio regardless of Kelly output. Returns 0 for negative expected value trades.
- **Fixed Fractional**: Allocates a constant percentage (default 2%) of portfolio per trade.
- **Volatility Scaled**: ATR-based sizing where a 1-ATR adverse move equals the dollar risk amount. Naturally sizes smaller in volatile markets.

A `calculate_position_size()` router selects the appropriate method and returns
a standardized result dict with `method`, `position_size`, `raw_fraction`, and
`portfolio_value`.

#### PortfolioMonitor (`src/risk/portfolio_monitor.py`)
Real-time stateful tracker for portfolio health. Maintains positions, cash
balance, start-of-day value, and peak value for drawdown calculation. Computes:
- Daily P&L (absolute and percentage)
- Current and maximum drawdown
- Average pairwise Pearson correlation across positions (using numpy)
- Deployment percentage
- Comprehensive risk summary

The `check_limits()` method flags breaches against configurable thresholds for
daily loss, deployment, and correlation.

#### CircuitBreaker (`src/risk/circuit_breaker.py`)
Pre-trade risk gate enforcing hard limits. Evaluates every proposed trade against:
- **Daily loss limit**: Default 5% of portfolio. Breach rejects all further trades.
- **Position size limit**: Default 2% of portfolio per trade. Suggests reduced size on breach.
- **Deployment cap**: Default 50% of portfolio deployed. Reports remaining capacity.
- **Correlation threshold**: Default 0.7 max pairwise correlation.
- **API health**: 3 consecutive failures triggers unhealthy status.
- **Volatile windows**: No trading in the first or last 15 minutes of the US equities session.

The `evaluate_trade()` method runs all checks and returns `approved` (bool),
`rejection_reasons` (list), and `adjustments` (suggested modifications).

Emergency `trigger_shutdown()` halts all trading until manual restart.

### Data Layer

#### TimescaleDB (PostgreSQL with time-series extensions)
Four core tables defined in `src/data/models.py`, all with indexed `created_at`
columns suitable for TimescaleDB hypertables:

| Table | Purpose | Key Fields |
|---|---|---|
| `trades` | Every executed or attempted trade | `trade_type`, `ticker_or_market_id`, `side`, `quantity`, `price`, `fill_price`, `status`, `slippage_bps`, `agent_name`, `reasoning` |
| `signals` | Trading signals emitted by analysis agents | `source_agent`, `ticker_or_market_id`, `signal_type`, `strength`, `confidence`, `metadata_json` |
| `agent_decisions` | Auditable agent decision records | `agent_name`, `crew_name`, `decision_type`, `input_summary`, `output_json`, `reasoning_chain`, `execution_time_ms` |
| `portfolio_snapshots` | Point-in-time portfolio health snapshots | `total_value`, `cash_balance`, `deployed_value`, `deployed_pct`, `daily_pnl`, `daily_pnl_pct`, `max_drawdown_pct`, `open_positions_count`, `portfolio_correlation` |

The ORM uses SQLAlchemy `declarative_base` with proper indexes on all timestamp
columns. Tables are created automatically on startup via `create_tables()`.

#### Redis Cache
5-minute TTL cache for API responses via `src/data/cache.py` (`CacheService`).
Prevents redundant API calls when multiple agents request the same data within
a short window. Connection string configurable via `REDIS_URL`.

#### SQLAlchemy ORM
All database access goes through SQLAlchemy with:
- Connection pooling (`pool_size=5`, `max_overflow=10`)
- `pool_pre_ping=True` for automatic reconnection
- Proper index definitions on time columns

## Technology Stack

| Component | Technology | Version / Notes |
|---|---|---|
| Agent Framework | CrewAI | Multi-agent orchestration with tool use |
| LLM | Claude (Anthropic API) | Primary reasoning engine for all agents |
| Local LLM (fallback) | Ollama | Optional local inference |
| Prediction Markets | Kalshi API | RSA-signed authentication |
| Equities Broker | Alpaca | Paper trading by default, live-ready |
| Database | TimescaleDB | PostgreSQL 16 with time-series extensions |
| Cache | Redis 7 (Alpine) | 5-minute TTL for API response caching |
| Scheduling | APScheduler | BackgroundScheduler with coalesce and misfire grace |
| Dashboard | Streamlit + Grafana | Streamlit at :8501, Grafana at :3000 |
| Logging | structlog | Structured JSON logging with context vars |
| Configuration | Pydantic Settings | Type-safe env var loading from .env |
| CI/CD | GitHub Actions | Automated testing and deployment |
| Container | Docker Compose 3.9 | TimescaleDB, Redis, Grafana, App |
| Notifications | Telegram + Discord | Trade alerts and daily summaries |
| Language | Python 3.11+ | Type hints throughout |

## Directory Structure

```
kalbi/
├── src/
│   ├── main.py                # Entry point: APScheduler setup, lifecycle
│   ├── config.py              # Pydantic Settings (env var loading)
│   ├── agents/                # CrewAI agent factory functions
│   │   ├── news_analyst.py
│   │   ├── quant_analyst.py
│   │   ├── fundamentals_analyst.py
│   │   ├── kalshi_specialist.py
│   │   ├── risk_manager.py
│   │   └── executor.py
│   ├── crews/                 # CrewAI crew definitions
│   │   ├── kalshi_crew.py
│   │   ├── equities_crew.py
│   │   └── meta_crew.py
│   ├── tools/                 # API wrappers (CrewAI tool functions)
│   │   ├── kalshi_api.py
│   │   ├── alpaca_api.py
│   │   ├── news_scraper.py
│   │   ├── sec_fetcher.py
│   │   ├── market_data.py
│   │   ├── sentiment_analyzer.py
│   │   └── technical_indicators.py
│   ├── strategies/            # Quantitative signal generation
│   │   ├── kalshi_event_arb.py
│   │   ├── momentum.py
│   │   ├── mean_reversion.py
│   │   └── ensemble.py
│   ├── risk/                  # Risk management components
│   │   ├── position_sizer.py
│   │   ├── portfolio_monitor.py
│   │   └── circuit_breaker.py
│   ├── data/                  # Persistence layer
│   │   ├── models.py          # SQLAlchemy ORM models
│   │   ├── cache.py           # Redis cache service
│   │   └── ingestion.py       # Data ingestion pipelines
│   ├── backtesting/           # Backtesting engine and metrics
│   │   ├── engine.py
│   │   ├── data_loader.py
│   │   └── metrics.py
│   ├── dashboard/             # Streamlit app + Grafana provisioning
│   │   └── streamlit_app.py
│   └── notifications/         # Alert channels
│       ├── telegram_bot.py
│       ├── discord_webhook.py
│       └── service.py
├── scripts/                   # Utility scripts
│   ├── setup_db.py
│   ├── seed_historical.py
│   └── github_sync.py
├── tests/                     # Test suite
├── docs/                      # Documentation
├── docker-compose.yml         # Full-stack container orchestration
├── Dockerfile                 # Application container
├── pyproject.toml             # Project metadata and dependencies
├── .env.example               # Template for environment variables
└── .github/                   # CI/CD workflows
```

## Data Flow

1. **APScheduler** fires a crew job at its configured interval.
2. The **Crew** assembles its agent pipeline and kicks off execution.
3. **Analysis agents** (News, Quant, Fundamentals, Kalshi Specialist) use their
   tools to gather data from external APIs, with Redis caching reducing redundant
   calls.
4. Each agent produces a structured signal or analysis that is passed to the next
   agent in the pipeline.
5. The **Risk Manager** receives the proposed trade, runs it through the
   **CircuitBreaker** checks, and applies **PositionSizer** to determine the
   appropriate size.
6. If approved, the **Executor** submits the order to Kalshi or Alpaca and logs
   the trade to TimescaleDB.
7. Every 5 minutes, a **PortfolioSnapshot** job records the current state of the
   portfolio.
8. At end of day, a **DailySummary** job compiles metrics and sends alerts via
   Telegram/Discord.
