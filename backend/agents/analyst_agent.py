"""
Analyst Agent — receives trade signals from the Scout, queries Pinecone
for similar historical setups, sends context to Claude Opus to generate
a Trade Thesis, then routes the thesis through the risk → execution →
alerting pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import anthropic

from alerts.telegram_bot import TelegramBot
from activity_feed import feed, FeedSource, FeedEvent
from config import settings
from execution.alpaca_executor import AlpacaExecutor
from execution.risk_manager import RiskManager
from memory.pinecone_memory import PineconeMemory
from models.models import (
    AgentState,
    AgentStatus,
    TradeAction,
    TradeResult,
    TradeSignal,
    TradeThesis,
    TrackedPosition,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a senior quantitative analyst. Given real-time market data and
alternative data context, produce a trade thesis in strict JSON with fields:
  action  — "BUY", "SELL", or "HOLD"
  conviction — float 0-1
  notional_usd — dollar amount (max $500 for paper trading)
  stop_loss_pct — stop-loss distance as %
  rationale — 2-3 sentence justification

Respond ONLY with the JSON object. No markdown fences, no commentary.
"""


class AnalystAgent:
    """
    Orchestrates the full analysis → risk → execution → alert pipeline.
    """

    def __init__(self, risk_manager: RiskManager | None = None) -> None:
        self._llm = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._memory = PineconeMemory()
        self._risk = risk_manager or RiskManager()
        self._executor = AlpacaExecutor()
        self._telegram = TelegramBot()
        self._position_manager = None  # injected by main.py
        self.status = AgentStatus(name="AnalystAgent")

        # In-memory trade log (append-only for the dashboard)
        self.trade_log: list[TradeResult] = []

    # ── Public API ─────────────────────────────────────────────────────

    async def analyse(self, signal: TradeSignal) -> None:
        """Full pipeline: LLM thesis → risk check → execute → alert."""
        self.status.state = AgentState.ANALYSING
        self.status.message = f"Analysing {signal.ticker}…"
        feed.push(FeedSource.ANALYST, FeedEvent.THESIS_REQUEST, f"Analysing signal", ticker=signal.ticker)

        try:
            # 1. Query memory for similar past setups
            memory_matches = await self._memory.search(
                context=signal.model_dump_json(), top_k=3
            )

            # 2. Build LLM prompt
            user_prompt = self._build_prompt(signal, memory_matches)

            # 3. Call Claude Opus
            thesis = await self._call_claude(signal.ticker, user_prompt)
            if thesis is None or thesis.action == TradeAction.HOLD:
                logger.info("Analyst: HOLD or parse failure for %s", signal.ticker)
                feed.push(FeedSource.ANALYST, FeedEvent.THESIS_GENERATED, "HOLD — no action", ticker=signal.ticker)
                self.status.state = AgentState.IDLE
                return

            # 4. Risk check
            verdict = self._risk.evaluate(thesis)
            if not verdict.approved:
                logger.warning(
                    "🚫  Risk rejected %s %s: %s",
                    thesis.action, thesis.ticker, verdict.reason,
                )
                feed.push(
                    FeedSource.RISK, FeedEvent.RISK_REJECTED,
                    f"{thesis.action.value} rejected — {verdict.reason}",
                    ticker=thesis.ticker,
                )
                result = TradeResult(
                    ticker=thesis.ticker,
                    action=thesis.action,
                    notional_usd=thesis.notional_usd,
                    status="rejected",
                    risk_verdict=verdict,
                    thesis_summary=thesis.rationale,
                )
                self.trade_log.append(result)
                self.status.state = AgentState.IDLE
                return

            # 5. Execute on Alpaca
            self.status.state = AgentState.EXECUTING
            feed.push(
                FeedSource.RISK, FeedEvent.RISK_APPROVED,
                f"{thesis.action.value} ${thesis.notional_usd:.0f} approved",
                ticker=thesis.ticker,
            )
            result = await self._executor.execute(thesis)
            result.thesis_summary = thesis.rationale
            result.risk_verdict = verdict
            self.trade_log.append(result)
            feed.push(
                FeedSource.EXECUTOR, FeedEvent.ORDER_FILLED,
                f"{result.status} — {result.filled_qty:.4f} @ ${result.filled_avg_price:.2f}",
                ticker=thesis.ticker,
            )

            # 6. Register with Position Manager for barrier monitoring
            if (
                self._position_manager
                and result.status in ("filled", "submitted", "accepted")
                and result.filled_avg_price > 0
                and thesis.action != TradeAction.HOLD
            ):
                is_long = thesis.action == TradeAction.BUY
                entry = result.filled_avg_price
                sl_pct = thesis.stop_loss_pct or settings.default_stop_loss_pct
                tp_pct = settings.default_take_profit_pct

                if is_long:
                    sl_price = entry * (1 - sl_pct / 100)
                    tp_price = entry * (1 + tp_pct / 100)
                else:
                    sl_price = entry * (1 + sl_pct / 100)
                    tp_price = entry * (1 - tp_pct / 100)

                pos = TrackedPosition(
                    ticker=thesis.ticker,
                    side=thesis.action,
                    entry_price=entry,
                    notional_usd=thesis.notional_usd,
                    qty=result.filled_qty,
                    stop_loss_price=round(sl_price, 2),
                    take_profit_price=round(tp_price, 2),
                    max_hold_until=datetime.now(timezone.utc) + timedelta(days=settings.max_hold_days),
                    thesis_summary=thesis.rationale,
                    order_id=result.id,
                )
                self._position_manager.register(pos)

            # 7. Store in memory
            await self._memory.store(thesis, result)

            # 8. Send Telegram alert
            await self._telegram.send_alert(result, thesis, memory_matches)
            feed.push(
                FeedSource.ALERT, FeedEvent.ALERT_SENT,
                f"Telegram alert dispatched for {thesis.action.value} {thesis.ticker}",
                ticker=thesis.ticker,
            )

            self.status.last_run = datetime.now(timezone.utc)
            self.status.state = AgentState.IDLE
            self.status.message = f"Completed {thesis.action.value} {thesis.ticker}"

        except Exception:
            logger.exception("Analyst pipeline error for %s", signal.ticker)
            self.status.state = AgentState.ERROR
            self.status.message = f"Error analysing {signal.ticker}"

    # ── Private Helpers ────────────────────────────────────────────────

    def _build_prompt(self, signal: TradeSignal, memory_matches: list) -> str:
        """Compose the user-message for Claude."""
        parts = [
            "## Live Market Signal",
            f"Ticker: {signal.ticker}",
            f"Price: ${signal.price:.2f}",
            f"Volume: {signal.volume:,}",
            f"Volume Z-Score: {signal.volume_z_score:.2f}",
            f"Price Change: {signal.price_change_pct:+.2f}%",
        ]

        if signal.congressional_trades:
            parts.append("\n## Congressional Trades (recent)")
            for t in signal.congressional_trades[:5]:
                parts.append(
                    f"- {t.get('representative', '?')}: {t.get('transaction', '?')} "
                    f"({t.get('amount', '?')}) on {t.get('date', '?')}"
                )

        if signal.retail_sentiment:
            s = signal.retail_sentiment
            parts.append("\n## Retail Sentiment")
            parts.append(
                f"Mentions: {s.get('mentions', 0)} | "
                f"Rank: {s.get('rank', '?')} | "
                f"Sentiment: {s.get('sentiment', '?')}"
            )

        if signal.ema_state:
            parts.append("\n## EMA Trend Analysis")
            state_label = signal.ema_state.upper()
            parts.append(f"Trend State: {state_label}")
            if signal.ema_crossover:
                parts.append(f"Crossover Event: {signal.ema_crossover.replace('_', ' ').title()}")
            if signal.ema_values:
                v = signal.ema_values
                parts.append(
                    f"EMA Values: Fast({v.get('fast', '?')}) | "
                    f"Medium({v.get('medium', '?')}) | "
                    f"Slow({v.get('slow', '?')})"
                )

        if memory_matches:
            parts.append("\n## Similar Past Setups (from memory)")
            for m in memory_matches:
                parts.append(
                    f"- {m.ticker} ({m.action}) — P&L: ${m.outcome_pnl:+.2f} | "
                    f"Score: {m.score:.2f} | {m.rationale[:80]}…"
                )

        return "\n".join(parts)

    async def _call_claude(self, ticker: str, user_prompt: str) -> TradeThesis | None:
        """Send prompt to Claude Opus and parse the JSON response."""
        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._llm.messages.create(
                    model=settings.anthropic_model,
                    max_tokens=512,
                    system=_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                ),
            )

            raw = response.content[0].text.strip()
            data = json.loads(raw)

            return TradeThesis(
                ticker=ticker,
                action=TradeAction(data["action"]),
                conviction=float(data["conviction"]),
                notional_usd=min(float(data["notional_usd"]), settings.max_notional_usd),
                stop_loss_pct=float(data["stop_loss_pct"]),
                rationale=data["rationale"],
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            logger.exception("Failed to parse Claude response for %s", ticker)
            return None
