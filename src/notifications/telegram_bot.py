"""
KALBI-2 Telegram Notification Channel.

Sends trade alerts, daily summaries, error notifications, and shutdown
alerts to a configured Telegram chat via the python-telegram-bot library.
All methods are async and include retry logic (up to 3 attempts with
exponential back-off).
"""

from __future__ import annotations

import asyncio
from typing import Optional

import structlog
from telegram import Bot
from telegram.error import TelegramError

log = structlog.get_logger(__name__)

_MAX_RETRIES: int = 3
_RETRY_BASE_DELAY: float = 1.0  # seconds


class TelegramNotifier:
    """Async Telegram notification channel for KALBI-2.

    Args:
        bot_token: Telegram Bot API token obtained from @BotFather.
        chat_id: Target chat or channel ID for messages.
    """

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id
        log.info(
            "telegram_notifier.initialized",
            chat_id=self.chat_id,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send_message(self, message: str) -> bool:
        """Send a plain-text message to the configured chat.

        Args:
            message: The text to send (Telegram MarkdownV2 is *not*
                applied -- the message is sent as-is).

        Returns:
            ``True`` if the message was delivered successfully.
        """
        return await self._send_with_retry(message)

    async def send_trade_alert(self, trade_data: dict) -> bool:
        """Format and send a trade execution alert.

        Expected keys in *trade_data*:
            - ``market_id`` (*str*)
            - ``side`` (*str*) -- e.g. ``"buy_yes"``, ``"sell"``
            - ``quantity`` (*float*)
            - ``price`` (*float*)
            - ``edge`` (*float*) -- percentage edge
            - ``confidence`` (*float*) -- model confidence (0-1)

        Args:
            trade_data: Dictionary describing the executed trade.

        Returns:
            ``True`` if the alert was delivered successfully.
        """
        market_id = trade_data.get("market_id", "N/A")
        side = trade_data.get("side", "N/A")
        qty = trade_data.get("quantity", 0)
        price = trade_data.get("price", 0.0)
        edge = trade_data.get("edge", 0.0)
        confidence = trade_data.get("confidence", 0.0)

        message = (
            "\U0001f514 TRADE EXECUTED\n"
            f"Market: {market_id}\n"
            f"Side: {side} | Qty: {qty} | Price: {price:.4f}\n"
            f"Edge: {edge:.2f}% | Confidence: {confidence:.2f}"
        )
        return await self._send_with_retry(message)

    async def send_daily_summary(self, summary: dict) -> bool:
        """Send an end-of-day P&L summary.

        Expected keys in *summary*:
            - ``pnl`` (*float*) -- absolute P&L in dollars
            - ``pnl_pct`` (*float*) -- P&L as a percentage
            - ``trade_count`` (*int*)
            - ``win_rate`` (*float*) -- percentage (0-100)
            - ``total_value`` (*float*) -- current portfolio value

        Args:
            summary: Dictionary with daily performance data.

        Returns:
            ``True`` if the summary was delivered successfully.
        """
        pnl = summary.get("pnl", 0.0)
        pnl_pct = summary.get("pnl_pct", 0.0)
        count = summary.get("trade_count", 0)
        win_rate = summary.get("win_rate", 0.0)
        total_value = summary.get("total_value", 0.0)

        message = (
            "\U0001f4ca DAILY SUMMARY\n"
            f"P&L: ${pnl:,.2f} ({pnl_pct:+.2f}%)\n"
            f"Trades: {count} | Win Rate: {win_rate:.1f}%\n"
            f"Portfolio: ${total_value:,.2f}"
        )
        return await self._send_with_retry(message)

    async def send_error_alert(self, error: str, context: str = "") -> bool:
        """Send a critical error notification.

        Args:
            error: Short description of the error.
            context: Optional additional context (e.g. stack trace excerpt,
                module name).

        Returns:
            ``True`` if the alert was delivered successfully.
        """
        ctx_line = f"\nContext: {context}" if context else ""
        message = f"\u26a0\ufe0f ERROR\n{error}{ctx_line}"
        return await self._send_with_retry(message)

    async def send_shutdown_alert(self, reason: str) -> bool:
        """Send a system shutdown notification.

        Args:
            reason: Human-readable explanation for the shutdown.

        Returns:
            ``True`` if the alert was delivered successfully.
        """
        message = f"\U0001f6d1 SYSTEM SHUTDOWN\nReason: {reason}"
        return await self._send_with_retry(message)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _send_with_retry(self, text: str) -> bool:
        """Attempt to send *text* up to ``_MAX_RETRIES`` times.

        Uses exponential back-off (1s, 2s, 4s ...) between attempts.

        Args:
            text: The message body.

        Returns:
            ``True`` on success, ``False`` if all attempts failed.
        """
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                )
                log.debug(
                    "telegram_notifier.message_sent",
                    attempt=attempt,
                    chat_id=self.chat_id,
                )
                return True
            except TelegramError as exc:
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                log.warning(
                    "telegram_notifier.send_failed",
                    attempt=attempt,
                    max_retries=_MAX_RETRIES,
                    error=str(exc),
                    retry_delay=delay,
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(delay)

        log.error(
            "telegram_notifier.send_exhausted",
            chat_id=self.chat_id,
            text_preview=text[:80],
        )
        return False
