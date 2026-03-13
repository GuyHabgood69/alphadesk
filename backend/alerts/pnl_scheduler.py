"""
Daily P&L Scheduler — sends Telegram summaries at market open & close.

Runs as a background asyncio task. Uses US Eastern Time to align
with NYSE trading hours:
  • 09:30 ET — Morning briefing (previous day recap + opening equity)
  • 16:05 ET — Close-of-day P&L summary
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from config import settings
from activity_feed import feed, FeedSource, FeedEvent

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

# Schedule times (Eastern)
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 5)  # 5 min after close to let final fills settle

_PLACEHOLDER = "PLACEHOLDER"


class PnlScheduler:
    """
    Background task that sends P&L Telegram alerts at market open & close.
    """

    def __init__(self, risk_manager, telegram_bot) -> None:
        self._risk = risk_manager
        self._telegram = telegram_bot
        self._task: asyncio.Task | None = None
        self._running = False

        self._enabled = (
            settings.telegram_bot_token != _PLACEHOLDER
            and settings.telegram_chat_id != _PLACEHOLDER
        )

    # ── Lifecycle ──────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the scheduler loop."""
        if not self._enabled:
            logger.info("P&L scheduler disabled — Telegram not configured")
            return
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("P&L scheduler started — alerts at %s / %s ET",
                     MARKET_OPEN.strftime("%H:%M"), MARKET_CLOSE.strftime("%H:%M"))
        feed.push(FeedSource.SYSTEM, FeedEvent.INFO, "P&L scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("P&L scheduler stopped")

    # ── Core Loop ──────────────────────────────────────────────────────

    async def _loop(self) -> None:
        """Sleep until the next scheduled time, then fire the alert."""
        while self._running:
            try:
                now_et = datetime.now(ET)
                next_fire = self._next_fire_time(now_et)
                delay = (next_fire - now_et).total_seconds()

                logger.info("P&L scheduler: next alert at %s ET (%.0f min)",
                            next_fire.strftime("%H:%M"), delay / 60)

                await asyncio.sleep(delay)

                # Determine which alert type
                fire_time = next_fire.timetz()
                if fire_time.hour == MARKET_OPEN.hour and fire_time.minute == MARKET_OPEN.minute:
                    await self._send_open_briefing()
                else:
                    await self._send_close_summary()

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("P&L scheduler error — retrying in 60s")
                await asyncio.sleep(60)

    # ── Schedule Helpers ───────────────────────────────────────────────

    def _next_fire_time(self, now: datetime) -> datetime:
        """Find the next MARKET_OPEN or MARKET_CLOSE in ET."""
        today = now.date()

        candidates = [
            datetime.combine(today, MARKET_OPEN, tzinfo=ET),
            datetime.combine(today, MARKET_CLOSE, tzinfo=ET),
            datetime.combine(today + timedelta(days=1), MARKET_OPEN, tzinfo=ET),
        ]

        for c in candidates:
            if c > now:
                # Skip weekends (0=Mon, 5=Sat, 6=Sun)
                while c.weekday() >= 5:
                    c += timedelta(days=1)
                return c

        # Fallback: tomorrow open
        tomorrow_open = datetime.combine(today + timedelta(days=1), MARKET_OPEN, tzinfo=ET)
        while tomorrow_open.weekday() >= 5:
            tomorrow_open += timedelta(days=1)
        return tomorrow_open

    # ── Alert Messages ─────────────────────────────────────────────────

    async def _send_open_briefing(self) -> None:
        """Send morning briefing with previous day recap."""
        equity = self._risk.portfolio_equity
        daily_pnl = self._risk.daily_pnl
        now = datetime.now(ET)

        pnl_emoji = "📈" if daily_pnl >= 0 else "📉"
        lines = [
            "☀️ <b>AlphaDesk — Market Open Briefing</b>",
            f"📅 {now.strftime('%A, %B %d %Y')}",
            "",
            f"💼 Portfolio Equity: <code>${equity:,.2f}</code>",
            f"{pnl_emoji} Yesterday's P&L: <code>${daily_pnl:+,.2f}</code>",
            "",
            "🔔 Scout is scanning the watchlist for opportunities.",
        ]

        await self._send(lines)
        feed.push(FeedSource.SYSTEM, FeedEvent.INFO, f"Morning briefing sent — equity ${equity:,.2f}")
        logger.info("Morning briefing sent")

    async def _send_close_summary(self) -> None:
        """Send end-of-day P&L summary."""
        equity = self._risk.portfolio_equity
        daily_pnl = self._risk.daily_pnl
        opening = self._risk.opening_equity
        now = datetime.now(ET)

        pnl_pct = (daily_pnl / opening * 100) if opening else 0.0
        pnl_emoji = "📈" if daily_pnl >= 0 else "📉"

        lines = [
            "🌙 <b>AlphaDesk — Market Close Summary</b>",
            f"📅 {now.strftime('%A, %B %d %Y')}",
            "",
            f"💼 Closing Equity: <code>${equity:,.2f}</code>",
            f"{pnl_emoji} Today's P&L: <code>${daily_pnl:+,.2f}</code> ({pnl_pct:+.2f}%)",
            f"📊 Opening Equity: <code>${opening:,.2f}</code>",
        ]

        # Add weekly context
        weekly = self._risk.pnl_history_weekly
        if weekly:
            weekly_total = sum(d["value"] for d in weekly)
            lines.append(f"\n📆 Week-to-Date P&L: <code>${weekly_total:+,.2f}</code>")

        await self._send(lines)
        feed.push(FeedSource.SYSTEM, FeedEvent.INFO, f"Close summary sent — daily P&L ${daily_pnl:+,.2f}")
        logger.info("Close summary sent — daily P&L $%.2f", daily_pnl)

    async def _send(self, lines: list[str]) -> None:
        """Send an HTML message to Telegram via the public API."""
        message = "\n".join(lines)
        await self._telegram.send_html(message)
