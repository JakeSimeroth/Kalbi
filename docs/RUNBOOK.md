# KALBI-2 Operations Runbook

## Prerequisites

### Software
- **Docker** and **Docker Compose** (v2.x or higher)
- **Python 3.11+** (for local development and running tests)
- **Git** (for version control)

### API Keys Required
You will need active accounts and API credentials for the following services:

| Service | Required | Purpose | Sign Up |
|---|---|---|---|
| Anthropic | Yes | LLM reasoning (Claude) | https://console.anthropic.com |
| Kalshi | Yes | Prediction market trading | https://kalshi.com |
| Alpaca | Yes | Equities trading (paper or live) | https://alpaca.markets |
| NewsAPI | Recommended | News article search | https://newsapi.org |
| Serper | Recommended | Google search API for news | https://serper.dev |
| Polygon | Optional | Premium market data | https://polygon.io |
| Reddit | Optional | Reddit API access | https://www.reddit.com/prefs/apps |
| Telegram | Optional | Trade alert notifications | https://core.telegram.org/bots |
| Discord | Optional | Webhook notifications | https://discord.com/developers |

---

## Quick Start

### 1. Clone the Repository
```bash
git clone <repository-url> kalbi
cd kalbi
```

### 2. Configure Environment Variables
```bash
cp .env.example .env
```
Edit `.env` and fill in your API credentials. At minimum you need:
- `ANTHROPIC_API_KEY`
- `KALSHI_API_KEY_ID` and `KALSHI_PRIVATE_KEY_PATH`
- `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`

Ensure `PAPER_TRADING_MODE=true` for initial setup.

### 3. Start All Services
```bash
docker-compose up -d
```
This starts:
- **TimescaleDB** on port 5432
- **Redis** on port 6379
- **Grafana** on port 3000 (admin/kalbi2)
- **KALBI-2 App** (connects to DB and Redis automatically)

### 4. Verify Services Are Running
```bash
docker-compose ps
```
All services should show "Up" or "healthy" status.

### 5. Check Application Logs
```bash
docker-compose logs -f app
```
You should see:
```
startup.begin  version=0.1.0
config.loaded  paper_mode=True ...
database.initialized ...
cache.initialized ...
scheduler.started  jobs=[...]
startup.complete  mode=PAPER
```

---

## Configuration Reference

All configuration is managed via environment variables loaded by Pydantic Settings
from the `.env` file. The `Settings` class is defined in `src/config.py`.

### LLM Configuration

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | (required) | Anthropic API key for Claude models |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Base URL for local Ollama instance |

### Trading Credentials

| Variable | Default | Description |
|---|---|---|
| `KALSHI_API_KEY_ID` | (required) | Kalshi API key identifier |
| `KALSHI_PRIVATE_KEY_PATH` | (required) | Path to Kalshi RSA private key PEM file |
| `ALPACA_API_KEY` | (required) | Alpaca broker API key |
| `ALPACA_SECRET_KEY` | (required) | Alpaca broker API secret |
| `ALPACA_BASE_URL` | `https://paper-api.alpaca.markets` | Alpaca API base URL. Change to `https://api.alpaca.markets` for live trading. |

### Data API Keys

| Variable | Default | Description |
|---|---|---|
| `NEWSAPI_KEY` | `""` | NewsAPI.org API key |
| `SERPER_API_KEY` | `""` | Serper.dev Google search API key |
| `POLYGON_API_KEY` | `""` | Polygon.io market data API key |
| `REDDIT_CLIENT_ID` | `""` | Reddit application client ID |
| `REDDIT_CLIENT_SECRET` | `""` | Reddit application client secret |

### Infrastructure

| Variable | Default | Description |
|---|---|---|
| `TIMESCALEDB_URL` | `postgresql://kalbi:kalbi@localhost:5432/kalbi` | TimescaleDB connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |

### Notifications

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `""` | Telegram bot token for trade alerts |
| `TELEGRAM_CHAT_ID` | `""` | Telegram chat/channel ID for alerts |
| `DISCORD_WEBHOOK_URL` | `""` | Discord webhook URL for notifications |

### Risk Controls

| Variable | Default | Description |
|---|---|---|
| `MAX_DAILY_LOSS_PCT` | `5.0` | Maximum allowable daily loss as % of portfolio |
| `MAX_POSITION_PCT` | `2.0` | Maximum single-position size as % of portfolio |
| `MAX_PORTFOLIO_DEPLOYED_PCT` | `50.0` | Maximum % of portfolio deployed at once |
| `MAX_CORRELATION` | `0.7` | Maximum allowed pairwise position correlation |
| `PAPER_TRADING_MODE` | `true` | Use paper/sandbox endpoints when true |

### Scheduling

| Variable | Default | Description |
|---|---|---|
| `KALSHI_SCAN_INTERVAL_MIN` | `15` | Minutes between Kalshi market scans |
| `EQUITIES_SCAN_INTERVAL_MIN` | `30` | Minutes between equities analysis cycles |
| `META_REVIEW_INTERVAL_MIN` | `120` | Minutes between meta-review cycles |

---

## Monitoring

### Grafana (Port 3000)
- **URL**: http://localhost:3000
- **Login**: admin / kalbi2
- **Data source**: TimescaleDB is pre-configured via provisioning
- Dashboards are provisioned from `src/dashboard/grafana_provisioning/dashboards/`

Key dashboards to set up:
- Portfolio P&L over time (from `portfolio_snapshots` table)
- Trade history with fill rates (from `trades` table)
- Agent decision audit trail (from `agent_decisions` table)
- Signal strength distribution (from `signals` table)

### Streamlit Dashboard (Port 8501)
- **URL**: http://localhost:8501
- The Streamlit app is defined in `src/dashboard/streamlit_app.py`
- Provides real-time portfolio overview and trade history

### Docker Logs
```bash
# All services
docker-compose logs -f

# Application only
docker-compose logs -f app

# Database only
docker-compose logs -f timescaledb

# Redis only
docker-compose logs -f redis
```

### Structured Logs
The application uses `structlog` for structured logging. Key log events to watch:

| Event | Meaning |
|---|---|
| `startup.complete` | System fully initialized |
| `job.kalshi_crew.start` | Kalshi scan cycle beginning |
| `job.equities_crew.skipped` | Equities scan skipped (market closed) |
| `circuit_breaker.trade_rejected` | Trade failed risk checks |
| `circuit_breaker.SHUTDOWN_TRIGGERED` | Emergency halt activated |
| `position_sizer.calculated` | Position size determined |
| `portfolio_monitor.limits_breached` | Risk limit exceeded |

---

## Troubleshooting

### Database Connection Issues

**Symptom**: `OperationalError: could not connect to server`

1. Verify TimescaleDB is running:
   ```bash
   docker-compose ps timescaledb
   ```
2. Check the health status:
   ```bash
   docker exec kalbi2-timescaledb pg_isready -U kalbi -d kalbi
   ```
3. Verify the connection string in `.env` matches docker-compose:
   - Inside Docker network: `postgresql://kalbi:kalbi@timescaledb:5432/kalbi`
   - From host machine: `postgresql://kalbi:kalbi@localhost:5432/kalbi`
4. Check for port conflicts:
   ```bash
   # Linux/Mac
   lsof -i :5432
   # Windows
   netstat -ano | findstr :5432
   ```

### Redis Connection Issues

**Symptom**: `ConnectionError: Error connecting to Redis`

1. Verify Redis is running:
   ```bash
   docker exec kalbi2-redis redis-cli ping
   ```
   Expected response: `PONG`
2. Check Redis URL format: `redis://localhost:6379/0`

### API Errors

**Symptom**: `401 Unauthorized` or `403 Forbidden` from Kalshi/Alpaca

1. Verify API keys are correctly set in `.env`
2. For Kalshi: ensure the private key PEM file exists at the path specified in
   `KALSHI_PRIVATE_KEY_PATH` and is readable
3. For Alpaca: confirm you are using the correct base URL for your account type
   (paper vs. live)
4. Check API rate limits -- the system caches responses in Redis with a 5-minute
   TTL to minimize API calls

**Symptom**: `429 Too Many Requests`

1. Check Redis is running (cache reduces API call frequency)
2. Consider increasing scan intervals in `.env`
3. Check if multiple instances are running against the same API keys

### Agent Failures

**Symptom**: `job.kalshi_crew.failed` or similar in logs

1. Check the full stack trace in `docker-compose logs -f app`
2. Verify the Anthropic API key is valid and has sufficient credits
3. Check if the LLM is returning errors (look for `anthropic` in logs)
4. If Ollama fallback is configured, verify it is running at the configured URL

### Scheduler Not Running

**Symptom**: No job execution logs appearing

1. Verify the scheduler started:
   ```bash
   docker-compose logs app | grep "scheduler.started"
   ```
2. Check for startup errors before the scheduler initialization
3. Verify all required environment variables are set (Settings validation will
   fail if required fields are missing)

---

## Emergency Procedures

### Immediate Shutdown (Kill Switch)
```bash
# Stop all containers immediately
docker-compose down

# Or just the application (DB and Redis keep running)
docker-compose stop app
```

### Circuit Breaker Activation
The system automatically halts all trading when:
- Daily drawdown exceeds 25% (configurable via `MAX_DAILY_LOSS_PCT`)
- The `CircuitBreaker.trigger_shutdown()` method is called

When the circuit breaker is activated:
1. All subsequent trade proposals are rejected
2. The halt persists until the application is restarted
3. Check logs for `circuit_breaker.SHUTDOWN_TRIGGERED` to find the reason

### Manual Recovery After Circuit Breaker
1. Stop the application: `docker-compose stop app`
2. Review the logs to understand what triggered the halt
3. Verify portfolio state via direct database query or Grafana
4. If safe to resume: `docker-compose start app`
5. The circuit breaker resets on restart

### Emergency Position Liquidation
If you need to close all positions immediately:
1. Stop the KALBI-2 application to prevent new trades
2. Log into Alpaca dashboard: https://app.alpaca.markets
3. Log into Kalshi dashboard: https://kalshi.com/portfolio
4. Manually close positions through the respective web interfaces
5. Investigate and resolve the issue before restarting KALBI-2

### Database Recovery
```bash
# Connect to TimescaleDB directly
docker exec -it kalbi2-timescaledb psql -U kalbi -d kalbi

# Check recent trades
SELECT * FROM trades ORDER BY created_at DESC LIMIT 20;

# Check portfolio snapshots
SELECT * FROM portfolio_snapshots ORDER BY created_at DESC LIMIT 10;

# Check for any pending/stuck trades
SELECT * FROM trades WHERE status = 'pending';
```

---

## Maintenance

### Adding a New Agent

1. Create a new factory function in `src/agents/`:
   ```python
   # src/agents/my_new_agent.py
   from crewai import Agent
   from src.tools import my_required_tools

   def create_my_new_agent(llm=None):
       return Agent(
           role="My New Role",
           goal="...",
           backstory="...",
           tools=[...],
           verbose=True,
           allow_delegation=False,
           llm=llm,
       )
   ```
2. Add the agent to the appropriate crew in `src/crews/`.
3. Document the agent's prompts in `docs/AGENT_PROMPTS.md`.
4. Add import tests in `tests/`.

### Adding a New Tool

1. Create the tool module in `src/tools/`:
   ```python
   # src/tools/my_api.py
   from crewai_tools import tool

   @tool("My Tool Name")
   def my_tool(param: str) -> str:
       """Description of what this tool does."""
       ...
   ```
2. Export the tool from `src/tools/__init__.py`.
3. Add it to the appropriate category list in `__init__.py`.
4. Add it to the relevant agent's tool list.

### Updating Strategies

1. Strategy classes live in `src/strategies/`.
2. Each strategy has a `generate_signal()` or `evaluate()` method.
3. After modifying a strategy, run the backtest suite to validate:
   ```bash
   python -m pytest tests/test_backtesting.py -v
   ```
4. Compare metrics (Sharpe, max drawdown, win rate) before and after changes.

### Updating Risk Parameters

Risk parameters can be changed without code modifications by updating `.env`:
```bash
# Tighter risk controls
MAX_DAILY_LOSS_PCT=3.0
MAX_POSITION_PCT=1.5
MAX_PORTFOLIO_DEPLOYED_PCT=40.0
MAX_CORRELATION=0.6
```
Restart the application for changes to take effect:
```bash
docker-compose restart app
```

### Database Migrations

The ORM models use SQLAlchemy's `create_all()` which only creates tables that
do not exist. For schema changes to existing tables:

1. Modify the model in `src/data/models.py`
2. Write a migration script in `scripts/` or use Alembic
3. Test against a local database first
4. Apply to production during a maintenance window

### Switching from Paper to Live Trading

1. **Verify** the system has been running in paper mode with satisfactory
   performance metrics (positive Sharpe, acceptable drawdown).
2. Update `.env`:
   ```bash
   PAPER_TRADING_MODE=false
   ALPACA_BASE_URL=https://api.alpaca.markets
   ```
3. **Reduce risk parameters** for the initial live period:
   ```bash
   MAX_POSITION_PCT=1.0
   MAX_PORTFOLIO_DEPLOYED_PCT=25.0
   ```
4. Restart: `docker-compose restart app`
5. Monitor closely for the first 24-48 hours.
6. Gradually increase risk parameters as confidence builds.
