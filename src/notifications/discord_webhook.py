"""
KALBI-2 Discord Webhook Notification Channel.

Posts trade alerts, daily summaries, and error notifications to a Discord
channel via an incoming webhook URL.  Messages are formatted as Discord
embeds with colour-coded sidebars (green for profit, red for loss, orange
for warnings).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import structlog

log = structlog.get_logger(__name__)

_MAX_RETRIES: int = 3
_RETRY_BASE_DELAY: float = 1.0  # seconds

# Discord embed colour constants (decimal representation).
_COLOR_GREEN: int = 0x2ECC71
_COLOR_RED: int = 0xE74C3C
_COLOR_ORANGE: int = 0xF39C12
_COLOR_BLUE: int = 0x3498DB
_COLOR_DARK: int = 0x2C2F33


class DiscordNotifier:
    """Async Discord webhook notification channel for KALBI-2.

    Args:
        webhook_url: Full Discord incoming-webhook URL.
    """

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url
        log.info("discord_notifier.initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send_message(
        self, message: str, embed: Optional[dict] = None
    ) -> bool:
        """Send a message (optionally with a Discord embed) via the webhook.

        Args:
            message: Plain-text content for the message.
            embed: Optional pre-built Discord embed dictionary.  When
                supplied it is sent alongside the plain-text *message*.

        Returns:
            ``True`` if the webhook accepted the payload.
        """
        payload: dict[str, Any] = {"content": message}
        if embed is not None:
            payload["embeds"] = [embed]
        return await self._post_with_retry(payload)

    async def send_trade_alert(self, trade_data: dict) -> bool:
        """Format and send a trade execution alert as a Discord embed.

        Expected keys in *trade_data*:
            - ``market_id`` (*str*)
            - ``side`` (*str*)
            - ``quantity`` (*float*)
            - ``price`` (*float*)
            - ``edge`` (*float*) -- percentage edge
            - ``confidence`` (*float*)

        Args:
            trade_data: Dictionary describing the executed trade.

        Returns:
            ``True`` if the webhook accepted the payload.
        """
        market_id = trade_data.get("market_id", "N/A")
        side = trade_data.get("side", "N/A")
        qty = trade_data.get("quantity", 0)
        price = trade_data.get("price", 0.0)
        edge = trade_data.get("edge", 0.0)
        confidence = trade_data.get("confidence", 0.0)

        color = _COLOR_GREEN if edge >= 0 else _COLOR_RED

        embed: dict[str, Any] = {
            "title": "Trade Executed",
            "color": color,
            "fields": [
                {"name": "Market", "value": str(market_id), "inline": True},
                {"name": "Side", "value": str(side), "inline": True},
                {"name": "Quantity", "value": str(qty), "inline": True},
                {"name": "Price", "value": f"{price:.4f}", "inline": True},
                {"name": "Edge", "value": f"{edge:.2f}%", "inline": True},
                {
                    "name": "Confidence",
                    "value": f"{confidence:.2f}",
                    "inline": True,
                },
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return await self._post_with_retry({"embeds": [embed]})

    async def send_daily_summary(self, summary: dict) -> bool:
        """Send an end-of-day P&L summary as a colour-coded Discord embed.

        Expected keys in *summary*:
            - ``pnl`` (*float*) -- absolute P&L in dollars
            - ``pnl_pct`` (*float*) -- P&L as a percentage
            - ``trade_count`` (*int*)
            - ``win_rate`` (*float*) -- percentage (0-100)
            - ``total_value`` (*float*) -- current portfolio value

        Args:
            summary: Dictionary with daily performance data.

        Returns:
            ``True`` if the webhook accepted the payload.
        """
        pnl = summary.get("pnl", 0.0)
        pnl_pct = summary.get("pnl_pct", 0.0)
        count = summary.get("trade_count", 0)
        win_rate = summary.get("win_rate", 0.0)
        total_value = summary.get("total_value", 0.0)

        color = _COLOR_GREEN if pnl >= 0 else _COLOR_RED

        embed: dict[str, Any] = {
            "title": "Daily Summary",
            "color": color,
            "fields": [
                {
                    "name": "P&L",
                    "value": f"${pnl:,.2f} ({pnl_pct:+.2f}%)",
                    "inline": True,
                },
                {
                    "name": "Trades",
                    "value": str(count),
                    "inline": True,
                },
                {
                    "name": "Win Rate",
                    "value": f"{win_rate:.1f}%",
                    "inline": True,
                },
                {
                    "name": "Portfolio Value",
                    "value": f"${total_value:,.2f}",
                    "inline": False,
                },
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return await self._post_with_retry({"embeds": [embed]})

    async def send_error_alert(self, error: str) -> bool:
        """Send a critical error notification as a Discord embed.

        Args:
            error: Short description of the error.

        Returns:
            ``True`` if the webhook accepted the payload.
        """
        embed: dict[str, Any] = {
            "title": "Error Alert",
            "description": error,
            "color": _COLOR_ORANGE,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return await self._post_with_retry({"embeds": [embed]})

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _post_with_retry(self, payload: dict) -> bool:
        """POST *payload* to the webhook URL with retry logic.

        Uses exponential back-off (1s, 2s, 4s ...) and up to
        ``_MAX_RETRIES`` attempts.

        Args:
            payload: JSON-serialisable webhook body.

        Returns:
            ``True`` on a 2xx response, ``False`` if all attempts fail.
        """
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        self.webhook_url,
                        json=payload,
                        timeout=10.0,
                    )
                if resp.status_code < 300:
                    log.debug(
                        "discord_notifier.webhook_sent",
                        attempt=attempt,
                        status=resp.status_code,
                    )
                    return True

                log.warning(
                    "discord_notifier.webhook_non_2xx",
                    attempt=attempt,
                    status=resp.status_code,
                    body=resp.text[:200],
                )
            except httpx.HTTPError as exc:
                log.warning(
                    "discord_notifier.webhook_error",
                    attempt=attempt,
                    max_retries=_MAX_RETRIES,
                    error=str(exc),
                )

            if attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                await asyncio.sleep(delay)

        log.error("discord_notifier.webhook_exhausted")
        return False
