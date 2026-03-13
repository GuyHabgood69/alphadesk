"""
Position Manager — monitors open positions and enforces triple-barrier
exits (stop-loss, take-profit, time-expiry) for event-driven swing trading.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from config import settings
from models.models import (
    ExitReason,
    PositionCloseResult,
    TradeAction,
    TrackedPosition,
)

logger = logging.getLogger(__name__)


class PositionManager:
    """
    Tracks open positions and closes them when a barrier is breached.

    Barriers checked every `position_check_interval` seconds:
      • Stop-loss:   price falls below (long) or rises above (short) threshold
      • Take-profit: price rises above (long) or falls below (short) threshold
      • Time-expiry: position has been held longer than `max_hold_days`
    """

    def __init__(
        self,
        alpaca_adapter: Any,
        alpaca_executor: Any,
        risk_manager: Any,
        telegram_bot: Any | None = None,
        memory: Any | None = None,
    ) -> None:
        self._adapter = alpaca_adapter
        self._executor = alpaca_executor
        self._risk = risk_manager
        self._telegram = telegram_bot
        self._memory = memory

        self._positions: list[TrackedPosition] = []
        self._closed_history: list[PositionCloseResult] = []
        self._task: asyncio.Task | None = None
        self._running = False

        logger.info(
            "PositionManager initialised — max %d positions, "
            "barriers: -%s%% / +%s%% / %dd",
            settings.max_positions,
            settings.default_stop_loss_pct,
            settings.default_take_profit_pct,
            settings.max_hold_days,
        )

    # ── Public Interface ──────────────────────────────────────────────

    @property
    def open_positions(self) -> list[TrackedPosition]:
        """Return a copy of currently tracked positions."""
        return list(self._positions)

    @property
    def closed_history(self) -> list[PositionCloseResult]:
        """Return closed position history."""
        return list(self._closed_history)

    @property
    def has_capacity(self) -> bool:
        """True if we can accept another position."""
        return len(self._positions) < settings.max_positions

    def is_holding(self, ticker: str) -> bool:
        """True if we already hold a position in this ticker."""
        return any(p.ticker == ticker for p in self._positions)

    def register(self, position: TrackedPosition) -> bool:
        """
        Register a new position for tracking.

        Returns False if at capacity or ticker is already held.
        """
        if not self.has_capacity:
            logger.warning(
                "Position rejected: at max capacity (%d/%d)",
                len(self._positions), settings.max_positions,
            )
            return False

        if self.is_holding(position.ticker):
            logger.warning(
                "Position rejected: already holding %s", position.ticker,
            )
            return False

        self._positions.append(position)
        logger.info(
            "📌 Position registered: %s %s @ $%.2f | "
            "SL=$%.2f TP=$%.2f | Expires %s",
            position.side.value,
            position.ticker,
            position.entry_price,
            position.stop_loss_price,
            position.take_profit_price,
            position.max_hold_until.strftime("%Y-%m-%d"),
        )
        return True

    async def manual_close(self, ticker: str) -> bool:
        """
        Manually close a position by ticker.

        Returns True on success, False if ticker not found.
        """
        pos = next((p for p in self._positions if p.ticker == ticker), None)
        if pos is None:
            logger.warning("Manual close requested for %s but no open position", ticker)
            return False

        snapshot = await self._adapter.fetch_snapshot(ticker)
        current_price = snapshot.get("price", pos.entry_price)
        await self._close_position(pos, ExitReason.MANUAL, current_price)
        return True

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background barrier-checking loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._check_loop())
        logger.info("PositionManager started (checking every %ds)", settings.position_check_interval)

    async def stop(self) -> None:
        """Stop the background loop gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("PositionManager stopped")

    # ── Background Loop ───────────────────────────────────────────────

    async def _check_loop(self) -> None:
        """Periodically evaluate all open positions against their barriers."""
        while self._running:
            try:
                if self._positions:
                    await self._evaluate_all()
            except Exception:
                logger.exception("Error in position check loop")

            await asyncio.sleep(settings.position_check_interval)

    async def _evaluate_all(self) -> None:
        """Check each open position and close if a barrier is breached."""
        positions_to_close: list[tuple[TrackedPosition, ExitReason, float]] = []

        for pos in self._positions:
            try:
                snapshot = await self._adapter.fetch_snapshot(pos.ticker)
                if not snapshot or "price" not in snapshot:
                    logger.warning("No price data for %s — skipping check", pos.ticker)
                    continue

                current_price = snapshot["price"]
                now = datetime.now(timezone.utc)

                reason = self._check_barriers(pos, current_price, now)
                if reason:
                    positions_to_close.append((pos, reason, current_price))

            except Exception:
                logger.exception("Error evaluating position %s", pos.ticker)

        # Close outside the iteration loop to avoid modifying the list mid-loop
        for pos, reason, price in positions_to_close:
            await self._close_position(pos, reason, price)

    def _check_barriers(
        self,
        pos: TrackedPosition,
        current_price: float,
        now: datetime,
    ) -> ExitReason | None:
        """Return the exit reason if any barrier is breached, else None."""
        is_long = pos.side == TradeAction.BUY

        # Stop-loss
        if is_long and current_price <= pos.stop_loss_price:
            return ExitReason.STOP_LOSS
        if not is_long and current_price >= pos.stop_loss_price:
            return ExitReason.STOP_LOSS

        # Take-profit
        if is_long and current_price >= pos.take_profit_price:
            return ExitReason.TAKE_PROFIT
        if not is_long and current_price <= pos.take_profit_price:
            return ExitReason.TAKE_PROFIT

        # Time expiry
        if now >= pos.max_hold_until:
            return ExitReason.TIME_EXPIRED

        return None

    # ── Position Closing ──────────────────────────────────────────────

    async def _close_position(
        self,
        pos: TrackedPosition,
        reason: ExitReason,
        current_price: float,
    ) -> None:
        """Close a position via Alpaca and record the result."""
        is_long = pos.side == TradeAction.BUY

        # Calculate P&L
        if is_long:
            pnl_usd = (current_price - pos.entry_price) * pos.qty
        else:
            pnl_usd = (pos.entry_price - current_price) * pos.qty

        pnl_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100
        if not is_long:
            pnl_pct = -pnl_pct

        hold_hours = (datetime.now(timezone.utc) - pos.entry_time).total_seconds() / 3600

        # Submit closing order (opposite side)
        close_side = TradeAction.SELL if is_long else TradeAction.BUY
        try:
            await self._executor.close_position(pos.ticker, pos.qty, close_side)
        except Exception:
            logger.exception("Failed to close position %s — will retry next cycle", pos.ticker)
            return

        # Record result
        result = PositionCloseResult(
            ticker=pos.ticker,
            side=pos.side,
            exit_reason=reason,
            entry_price=pos.entry_price,
            exit_price=current_price,
            qty=pos.qty,
            pnl_usd=round(pnl_usd, 2),
            pnl_pct=round(pnl_pct, 2),
            hold_duration_hours=round(hold_hours, 1),
        )
        self._closed_history.append(result)

        # Remove from tracked list
        self._positions = [p for p in self._positions if p.ticker != pos.ticker]

        # Update RiskManager P&L
        self._risk.record_pnl(pnl_usd)

        emoji = "🟢" if pnl_usd >= 0 else "🔴"
        logger.info(
            "%s Position closed: %s %s | %s | P&L: $%.2f (%.1f%%) | Held %.1fh",
            emoji, pos.side.value, pos.ticker, reason.value,
            pnl_usd, pnl_pct, hold_hours,
        )

        # Send Telegram alert
        if self._telegram:
            msg = (
                f"{emoji} <b>Position Closed — {reason.value}</b>\n"
                f"<b>{pos.side.value} {pos.ticker}</b>\n"
                f"Entry: ${pos.entry_price:.2f} → Exit: ${current_price:.2f}\n"
                f"P&L: <b>${pnl_usd:+.2f}</b> ({pnl_pct:+.1f}%)\n"
                f"Hold: {hold_hours:.1f}h | Reason: {reason.value}"
            )
            await self._telegram.send_html(msg)

        # Store outcome in memory for future LLM context
        if self._memory:
            try:
                await self._memory.store_outcome(
                    ticker=pos.ticker,
                    action=pos.side.value,
                    rationale=pos.thesis_summary,
                    pnl=pnl_usd,
                )
            except Exception:
                logger.warning("Failed to store close outcome in memory for %s", pos.ticker)
