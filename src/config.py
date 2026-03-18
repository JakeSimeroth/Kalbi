"""
KALBI-2 Trading System Configuration.

Pydantic settings class that loads environment variables from a .env file.
Covers API credentials, database URLs, notification settings, risk parameters,
and scheduling intervals for the multi-agent trading system.
"""

from pydantic_settings import BaseSettings
from pydantic import Field, computed_field


class Settings(BaseSettings):
    """Central configuration for the KALBI-2 trading system.

    All values are loaded from environment variables or a .env file.
    Sensitive credentials (API keys, secrets) have no defaults and must
    be provided at runtime.
    """

    # ── LLM providers ────────────────────────────────────────────────
    anthropic_api_key: str = Field(
        ..., description="Anthropic API key for Claude models"
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL for the local Ollama instance",
    )

    # ── Kalshi credentials ───────────────────────────────────────────
    kalshi_api_key_id: str = Field(
        ..., description="Kalshi API key identifier"
    )
    kalshi_private_key_path: str = Field(
        ..., description="File-system path to the Kalshi RSA private key"
    )

    # ── Alpaca credentials ───────────────────────────────────────────
    alpaca_api_key: str = Field(
        ..., description="Alpaca broker API key"
    )
    alpaca_api_secret: str = Field(
        ..., description="Alpaca broker API secret"
    )
    alpaca_base_url: str = Field(
        default="https://paper-api.alpaca.markets",
        description="Alpaca REST API base URL (paper or live)",
    )

    # ── News / data API keys ────────────────────────────────────────
    newsapi_key: str = Field(
        default="", description="NewsAPI.org API key"
    )
    serper_api_key: str = Field(
        default="", description="Serper.dev Google-search API key"
    )
    polygon_api_key: str = Field(
        default="", description="Polygon.io API key for market data"
    )
    reddit_client_id: str = Field(
        default="", description="Reddit application client ID"
    )
    reddit_client_secret: str = Field(
        default="", description="Reddit application client secret"
    )

    # ── Database URLs ────────────────────────────────────────────────
    timescaledb_url: str = Field(
        default="postgresql://kalbi:kalbi@localhost:5432/kalbi",
        description="TimescaleDB connection string",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection string",
    )

    # ── Notification channels ────────────────────────────────────────
    telegram_bot_token: str = Field(
        default="", description="Telegram bot token for trade alerts"
    )
    telegram_chat_id: str = Field(
        default="", description="Telegram chat / channel ID for alerts"
    )
    discord_webhook_url: str = Field(
        default="", description="Discord webhook URL for notifications"
    )

    # ── Risk parameters ──────────────────────────────────────────────
    max_daily_loss_pct: float = Field(
        default=5.0,
        description="Maximum allowable daily loss as a percentage of portfolio",
    )
    max_position_pct: float = Field(
        default=2.0,
        description="Maximum single-position size as a percentage of portfolio",
    )
    max_portfolio_deployed_pct: float = Field(
        default=50.0,
        description="Maximum percentage of portfolio that can be deployed at once",
    )
    max_correlation: float = Field(
        default=0.7,
        description="Maximum allowed correlation between open positions",
    )
    paper_trading_mode: bool = Field(
        default=True,
        description="When True the system uses paper/sandbox endpoints",
    )

    # ── Scheduling intervals (minutes) ───────────────────────────────
    kalshi_scan_interval_minutes: int = Field(
        default=15, description="Minutes between Kalshi market scans"
    )
    equities_scan_interval_minutes: int = Field(
        default=30, description="Minutes between equities scans"
    )
    meta_review_interval_minutes: int = Field(
        default=120, description="Minutes between meta-review cycles"
    )

    # ── Computed helpers ─────────────────────────────────────────────
    @computed_field  # type: ignore[misc]
    @property
    def is_paper_trading(self) -> bool:
        """Return True when the system is configured for paper trading."""
        return self.paper_trading_mode

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }
