"""
Risk Manager — hard-coded guardrails that gate every trade.

Rules:
  1. Per-trade notional ≤ max_risk_pct% of portfolio equity.
  2. Cumulative intraday realised loss ≤ max_daily_drawdown_pct% of opening equity.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from config import settings
from models.models import RiskVerdict, TradeThesis

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Stateful risk gate.  Tracks daily P&L in memory and resets
    at the start of each trading day.
    """

    def __init__(self) -> None:
        self._portfolio_equity: float = self._fetch_alpaca_equity()
        self._opening_equity: float = self._portfolio_equity
        self._daily_pnl: float = 0.0
        self._trade_date: date = date.today()

        # P&L history — list of {time, value} snapshots for the intraday chart
        self._pnl_history: list[dict] = [
            {"time": datetime.now().strftime("%H:%M"), "value": 0.0}
        ]

        # Weekly P&L history — daily closing P&L for the week chart
        self._weekly_pnl: list[dict] = [
            {"time": date.today().strftime("%a"), "value": 0.0}
        ]
        self._week_number: int = date.today().isocalendar()[1]

        # User-tunable (exposed via API)
        self.max_risk_pct: float = settings.max_risk_pct
        self.max_daily_drawdown_pct: float = settings.max_daily_drawdown_pct

    # ── Alpaca equity sync ────────────────────────────────────────────

    def _fetch_alpaca_equity(self) -> float:
        # NOTE: Intentionally synchronous — called once during __init__.
        # Acceptable one-time startup delay (1-3s). The rest of the app is async.
        """Fetch live portfolio equity from Alpaca; fall back to config default."""
        try:
            from alpaca.trading.client import TradingClient

            client = TradingClient(settings.alpaca_api_key, settings.alpaca_secret_key)
            account = client.get_account()
            equity = float(account.equity)
            logger.info("Fetched Alpaca equity: $%.2f", equity)
            return equity
        except Exception as exc:
            logger.warning(
                "Could not fetch Alpaca equity (%s) — using config default $%.0f",
                exc, settings.paper_portfolio_equity,
            )
            return settings.paper_portfolio_equity

    # ── Public API ─────────────────────────────────────────────────────

    def evaluate(self, thesis: TradeThesis) -> RiskVerdict:
        """
        Approve or reject a trade thesis.

        Returns a RiskVerdict with the decision and reason.
        """
        self._maybe_reset_day()

        # Rule 1 — per-trade size limit
        max_notional = self._portfolio_equity * (self.max_risk_pct / 100.0)
        if thesis.notional_usd > max_notional:
            return RiskVerdict(
                approved=False,
                reason=(
                    f"Notional ${thesis.notional_usd:.2f} exceeds "
                    f"{self.max_risk_pct}% cap (${max_notional:.2f})"
                ),
            )

        # Rule 2 — daily drawdown limit (only triggers on losses)
        max_loss = self._opening_equity * (self.max_daily_drawdown_pct / 100.0)
        if self._daily_pnl <= -max_loss:
            return RiskVerdict(
                approved=False,
                reason=(
                    f"Daily drawdown ${abs(self._daily_pnl):.2f} has hit "
                    f"{self.max_daily_drawdown_pct}% limit (${max_loss:.2f})"
                ),
            )

        return RiskVerdict(approved=True, reason="Within risk limits")

    def record_pnl(self, pnl: float) -> None:
        """Update intraday P&L after a fill."""
        self._maybe_reset_day()
        self._daily_pnl += pnl
        self._portfolio_equity += pnl

        # Append snapshot to P&L history for the intraday chart
        self._pnl_history.append({
            "time": datetime.now().strftime("%H:%M"),
            "value": round(self._daily_pnl, 2),
        })

        # Update today's entry in the weekly chart
        today_label = date.today().strftime("%a")
        if self._weekly_pnl and self._weekly_pnl[-1]["time"] == today_label:
            self._weekly_pnl[-1]["value"] = round(self._daily_pnl, 2)
        else:
            self._weekly_pnl.append({"time": today_label, "value": round(self._daily_pnl, 2)})

        logger.info(
            "P&L recorded: %+.2f | daily: %+.2f | equity: %.2f",
            pnl, self._daily_pnl, self._portfolio_equity,
        )

    def update_equity(self, equity: float) -> None:
        """Sync equity from Alpaca account snapshot."""
        self._portfolio_equity = equity

    @property
    def portfolio_equity(self) -> float:
        return self._portfolio_equity

    @property
    def daily_pnl(self) -> float:
        return self._daily_pnl

    @property
    def opening_equity(self) -> float:
        return self._opening_equity

    @property
    def pnl_history(self) -> list[dict]:
        """Return timestamped P&L snapshots for the intraday chart."""
        return self._pnl_history

    @property
    def pnl_history_weekly(self) -> list[dict]:
        """Return daily P&L snapshots for the weekly chart."""
        return self._weekly_pnl

    # ── Private Helpers ────────────────────────────────────────────────

    def _maybe_reset_day(self) -> None:
        """Reset daily counters on a new trading day."""
        today = date.today()
        if today != self._trade_date:
            self._trade_date = today
            self._opening_equity = self._portfolio_equity
            self._daily_pnl = 0.0
            self._pnl_history = [
                {"time": datetime.now().strftime("%H:%M"), "value": 0.0}
            ]
            # Reset weekly history on new week (Monday)
            current_week = today.isocalendar()[1]
            if current_week != self._week_number:
                self._week_number = current_week
                self._weekly_pnl = [
                    {"time": today.strftime("%a"), "value": 0.0}
                ]
            else:
                # Add new day entry to existing week
                self._weekly_pnl.append({"time": today.strftime("%a"), "value": 0.0})
            logger.info("New trading day — daily P&L reset")
