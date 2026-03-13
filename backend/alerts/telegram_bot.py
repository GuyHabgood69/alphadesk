"""
Telegram Bot — sends formatted Markdown trade alerts asynchronously.

Gracefully degrades to a no-op logger when TELEGRAM_BOT_TOKEN is not
configured (set to PLACEHOLDER).
"""

from __future__ import annotations

import logging

from config import settings
from models.models import MemoryMatch, TradeResult, TradeThesis

logger = logging.getLogger(__name__)

_PLACEHOLDER = "PLACEHOLDER"


class TelegramBot:
    """Async wrapper around python-telegram-bot for trade notifications."""

    def __init__(self) -> None:
        self._enabled = (
            settings.telegram_bot_token != _PLACEHOLDER
            and settings.telegram_chat_id != _PLACEHOLDER
        )
        self._bot = None
        self._chat_id = settings.telegram_chat_id

        if self._enabled:
            try:
                from telegram import Bot
                self._bot = Bot(token=settings.telegram_bot_token)
                logger.info("Telegram alerts enabled")
            except Exception:
                logger.warning("Telegram library unavailable — alerts disabled")
                self._enabled = False
        else:
            logger.info("Telegram not configured — alerts will be logged only")

    async def send_alert(
        self,
        result: TradeResult,
        thesis: TradeThesis,
        memory_matches: list[MemoryMatch] | None = None,
    ) -> None:
        """
        Send a richly formatted Markdown message to the configured
        Telegram chat.  Falls back to logging when disabled.
        """
        emoji = "🟢" if thesis.action.value == "BUY" else "🔴"
        summary = (
            f"{emoji} {thesis.action.value} {thesis.ticker} "
            f"${thesis.notional_usd:.2f} — {result.status}"
        )

        if not self._enabled or self._bot is None:
            logger.info("Telegram (disabled): %s", summary)
            return

        from telegram.constants import ParseMode

        status_emoji = "✅" if result.status == "filled" else "⚠️"

        lines = [
            f"{emoji} <b>{thesis.action.value} {thesis.ticker}</b>",
            "",
            f"💰 Notional: <code>${thesis.notional_usd:.2f}</code>",
            f"📊 Conviction: <code>{thesis.conviction:.0%}</code>",
            f"🛑 Stop-loss: <code>{thesis.stop_loss_pct:.1f}%</code>",
            f"{status_emoji} Status: <code>{result.status}</code>",
            "",
            f"📝 <b>Thesis</b>",
            f"<i>{thesis.rationale}</i>",
        ]

        if result.filled_avg_price:
            lines.append(f"\n📈 Fill: <code>{result.filled_qty:.4f}</code> @ <code>${result.filled_avg_price:.2f}</code>")

        if memory_matches:
            lines.append("\n🧠 <b>Similar Past Setups</b>")
            for m in memory_matches[:3]:
                pnl_emoji = "📈" if m.outcome_pnl >= 0 else "📉"
                lines.append(
                    f"  • {m.ticker} ({m.action}) — "
                    f"{pnl_emoji} <code>${m.outcome_pnl:+.2f}</code> "
                    f"[score: {m.score:.2f}]"
                )

        message = "\n".join(lines)

        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode=ParseMode.HTML,
            )
            logger.info("Telegram alert sent for %s", thesis.ticker)
        except Exception:
            logger.exception("Failed to send Telegram alert")

    async def send_html(self, html: str) -> None:
        """
        Send an arbitrary HTML message to the configured chat.
        Used by schedulers and other components that need to post
        messages without constructing a full trade alert.
        """
        if not self._enabled or self._bot is None:
            logger.info("Telegram (disabled): scheduled message skipped")
            return

        from telegram.constants import ParseMode

        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=html,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            logger.exception("Failed to send Telegram HTML message")
