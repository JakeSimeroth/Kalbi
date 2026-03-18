"""
KALBI-2 Unified Notification Service.

Wraps TelegramNotifier and DiscordNotifier behind a single interface.
At construction time, each channel is enabled only when the required
credentials / URLs are supplied.  All ``send_*`` methods dispatch to
every enabled channel in parallel and return ``True`` if *at least one*
channel succeeded.
"""

from __future__ import annotations

import asyncio
from typing import Optional

import structlog

from src.notifications.telegram_bot import TelegramNotifier
from src.notifications.discord_webhook import DiscordNotifier

log = structlog.get_logger(__name__)


class NotificationService:
    """Unified notification dispatcher for KALBI-2.

    Only channels whose credentials are provided (non-empty strings) are
    activated.  If no channel is configured every ``send_*`` call logs a
    warning and returns ``False``.

    Args:
        telegram_bot_token: Telegram Bot API token (empty to disable).
        telegram_chat_id: Telegram target chat ID (empty to disable).
        discord_webhook_url: Discord incoming-webhook URL (empty to
            disable).
    """

    def __init__(
        self,
        telegram_bot_token: str = "",
        telegram_chat_id: str = "",
        discord_webhook_url: str = "",
    ) -> None:
        self._telegram: Optional[TelegramNotifier] = None
        self._discord: Optional[DiscordNotifier] = None

        if telegram_bot_token and telegram_chat_id:
            self._telegram = TelegramNotifier(
                bot_token=telegram_bot_token,
                chat_id=telegram_chat_id,
            )
            log.info("notification_service.telegram_enabled")

        if discord_webhook_url:
            self._discord = DiscordNotifier(
                webhook_url=discord_webhook_url,
            )
            log.info("notification_service.discord_enabled")

        if self._telegram is None and self._discord is None:
            log.warning("notification_service.no_channels_configured")

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def has_channels(self) -> bool:
        """Return ``True`` if at least one notification channel is active."""
        return self._telegram is not None or self._discord is not None

    # ------------------------------------------------------------------
    # Dispatch methods
    # ------------------------------------------------------------------

    async def send_message(self, message: str) -> bool:
        """Broadcast a plain-text message to all active channels.

        Args:
            message: The text to send.

        Returns:
            ``True`` if at least one channel delivered the message.
        """
        return await self._dispatch("send_message", message=message)

    async def send_trade_alert(self, trade_data: dict) -> bool:
        """Broadcast a trade execution alert to all active channels.

        Args:
            trade_data: Dictionary describing the executed trade.

        Returns:
            ``True`` if at least one channel delivered the alert.
        """
        return await self._dispatch("send_trade_alert", trade_data=trade_data)

    async def send_daily_summary(self, summary: dict) -> bool:
        """Broadcast an end-of-day P&L summary to all active channels.

        Args:
            summary: Dictionary with daily performance data.

        Returns:
            ``True`` if at least one channel delivered the summary.
        """
        return await self._dispatch("send_daily_summary", summary=summary)

    async def send_error_alert(self, error: str, context: str = "") -> bool:
        """Broadcast a critical error notification to all active channels.

        The Telegram channel receives the optional *context* parameter;
        Discord receives only the error string.

        Args:
            error: Short description of the error.
            context: Optional extra context (forwarded to Telegram only).

        Returns:
            ``True`` if at least one channel delivered the alert.
        """
        tasks = []
        if self._telegram is not None:
            tasks.append(self._telegram.send_error_alert(error, context))
        if self._discord is not None:
            tasks.append(self._discord.send_error_alert(error))

        if not tasks:
            log.warning(
                "notification_service.no_channels",
                method="send_error_alert",
            )
            return False

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return self._evaluate_results(results, "send_error_alert")

    async def send_shutdown_alert(self, reason: str) -> bool:
        """Broadcast a system shutdown notification.

        The shutdown alert is sent to Telegram.  Discord receives a
        plain-text message since it does not have a dedicated shutdown
        method.

        Args:
            reason: Human-readable explanation for the shutdown.

        Returns:
            ``True`` if at least one channel delivered the alert.
        """
        tasks = []
        if self._telegram is not None:
            tasks.append(self._telegram.send_shutdown_alert(reason))
        if self._discord is not None:
            tasks.append(
                self._discord.send_message(
                    f"\U0001f6d1 SYSTEM SHUTDOWN\nReason: {reason}"
                )
            )

        if not tasks:
            log.warning(
                "notification_service.no_channels",
                method="send_shutdown_alert",
            )
            return False

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return self._evaluate_results(results, "send_shutdown_alert")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _dispatch(self, method_name: str, **kwargs) -> bool:
        """Invoke *method_name* on every active channel in parallel.

        Args:
            method_name: The name of the method to call on each notifier.
            **kwargs: Keyword arguments forwarded to each notifier method.

        Returns:
            ``True`` if at least one channel succeeded.
        """
        tasks = []
        if self._telegram is not None:
            tasks.append(getattr(self._telegram, method_name)(**kwargs))
        if self._discord is not None:
            tasks.append(getattr(self._discord, method_name)(**kwargs))

        if not tasks:
            log.warning(
                "notification_service.no_channels",
                method=method_name,
            )
            return False

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return self._evaluate_results(results, method_name)

    @staticmethod
    def _evaluate_results(results: list, method_name: str) -> bool:
        """Check gathered results and return ``True`` if any succeeded.

        Exceptions captured by ``asyncio.gather`` are logged and counted
        as failures.

        Args:
            results: List of booleans / exceptions from ``gather``.
            method_name: Name of the originating method (for logging).

        Returns:
            ``True`` if at least one result is ``True``.
        """
        success = False
        for result in results:
            if isinstance(result, BaseException):
                log.error(
                    "notification_service.channel_exception",
                    method=method_name,
                    error=str(result),
                )
            elif result is True:
                success = True

        if not success:
            log.error(
                "notification_service.all_channels_failed",
                method=method_name,
            )
        return success
