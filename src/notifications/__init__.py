"""
KALBI-2 Notification sub-package.

Provides Telegram and Discord notification channels, plus a unified
:class:`NotificationService` that dispatches to whichever channels are
configured.
"""

from src.notifications.service import NotificationService
from src.notifications.telegram_bot import TelegramNotifier
from src.notifications.discord_webhook import DiscordNotifier

__all__ = [
    "NotificationService",
    "TelegramNotifier",
    "DiscordNotifier",
]
