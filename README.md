# KALBI-2

**Autonomous Multi-Agent Trading System** -- Prediction Markets & Equities

KALBI-2 is an AI-powered trading system that uses specialized [CrewAI](https://crewai.com) agents to autonomously trade on [Kalshi](https://kalshi.com) prediction markets and [Alpaca](https://alpaca.markets) equities. Agents collaborate in crews, each with distinct expertise: news analysis, quantitative signals, fundamental research, risk management, and trade execution.

---

## Architecture

```
                        ┌─────────────────────┐
                        │    APScheduler       │
                        └──────┬──────────────┘
               ┌───────────────┼───────────────┐
               v               v               v
        ┌──────────┐   ┌──────────────┐   ┌──────────┐
        │  Kalshi  │   │  Equities    │   │   Meta   │
        │  Crew    │   │  Crew        │   │   Crew   │
        │ (15 min) │   │ (30 min)     │   │  (2 hr)  │
        └────┬─────┘   └──────┬───────┘   └────┬─────┘
             │                │                 │
     ┌───────┴────────────────┴─────────────────┴──────┐
     │              CrewAI Agent Layer                  │
     │  News Analyst · Quant · Fundamentals · Kalshi   │
     │  Risk Manager · Executor                        │
     └───────┬────────────────┬─────────────────┬──────┘
             │                │                 │
     ┌───────┴──┐    ┌───────┴──┐    ┌─────────┴──────┐
     │TimescaleDB│    │  Redis   │    │ Risk Engine    │
     │ (Postgres)│    │  Cache   │    │ Circuit Breaker│
     └──────────┘    └──────────┘    └────────────────┘
```

## Features

- **Multi-Agent Crews**: Specialized AI agents collaborate via CrewAI (News Analyst, Quant, Fundamentals, Kalshi Specialist, Risk Manager, Executor)
- **Dual Market**: Trades both Kalshi prediction markets and Alpaca equities
- **Risk-First**: Hard circuit breakers -- 2% per trade, 25% daily drawdown shutdown, 50% max deployment, correlation limits
- **Full Observability**: Grafana dashboards, Streamlit UI, Telegram/Discord alerts, structured logging
- **Backtesting**: Event-driven backtester with Sharpe, Sortino, drawdown, and win-rate metrics
- **CI/CD**: GitHub Actions for linting, testing, nightly backtests, and auto-deploy

## Quick Start

```bash
# 1. Clone
git clone https://github.com/JakeStephen/Kalbi.git
cd Kalbi

# 2. Configure
cp .env.example .env
# Edit .env with your API keys (Anthropic, Kalshi, Alpaca, etc.)

# 3. Start infrastructure
docker-compose up -d

# 4. Initialize database
pip install -e ".[dev]"
python scripts/setup_db.py

# 5. Run (paper trading mode by default)
python -m src.main
```

## Project Structure

```
src/
├── agents/          # CrewAI agent definitions (6 agents)
├── crews/           # Crew orchestration (Kalshi, Equities, Meta)
├── tools/           # API wrappers as CrewAI tools (7 tools)
├── strategies/      # Trading strategies (momentum, mean reversion, ensemble, event arb)
├── risk/            # Position sizing, portfolio monitoring, circuit breakers
├── data/            # SQLAlchemy models, data ingestion, Redis cache
├── notifications/   # Telegram & Discord alerting
├── backtesting/     # Event-driven backtester with metrics
├── dashboard/       # Streamlit app + Grafana provisioning
├── config.py        # Pydantic settings (loads .env)
└── main.py          # APScheduler entry point
```

## Agents

| Agent | Role | Runs In |
|-------|------|---------|
| News Analyst | Scrapes & scores news sentiment | Kalshi + Equities Crew |
| Quant Analyst | Technical signals (RSI, MACD, Bollinger) | Equities Crew |
| Fundamentals Analyst | SEC filings, earnings, macro | Equities Crew |
| Kalshi Specialist | Bayesian probability estimation | Kalshi Crew |
| Risk Manager | Veto power, position limits, circuit breakers | All Crews |
| Executor | Limit order execution, fill confirmation | All Crews |

## Safety Controls

| Control | Limit |
|---------|-------|
| Per-trade risk | Max 2% of portfolio |
| Per-ticker exposure | Max 10% of portfolio |
| Daily drawdown kill | 25% triggers full shutdown |
| Max deployment | 50% (rest in cash) |
| Correlation guard | Reject if portfolio correlation > 0.7 |
| Market hours | No equities trading in first/last 15 min |
| Paper trading | Required for first 30 days |

## Monitoring

- **Grafana**: `http://localhost:3000` (admin / kalbi2)
- **Streamlit**: `python -m src.dashboard.streamlit_app` at `:8501`
- **Logs**: Structured JSON via `structlog`
- **Alerts**: Telegram trade alerts, daily P&L summaries, error notifications

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Lint
ruff check src/ tests/

# Type check
mypy src/

# Test
pytest tests/ -v --cov=src

# Backtest
python -m src.backtesting.engine
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Agent Framework | CrewAI |
| LLM | Claude (Anthropic API) |
| Prediction Markets | Kalshi API |
| Equities Broker | Alpaca |
| Database | TimescaleDB |
| Cache | Redis |
| Scheduler | APScheduler |
| Dashboard | Streamlit + Grafana |
| CI/CD | GitHub Actions |
| Container | Docker Compose |

## Documentation

- [Architecture](docs/ARCHITECTURE.md) -- System design and data flow
- [Agent Prompts](docs/AGENT_PROMPTS.md) -- All agent specifications (versioned)
- [Runbook](docs/RUNBOOK.md) -- Deploy, monitor, troubleshoot

## License

MIT
