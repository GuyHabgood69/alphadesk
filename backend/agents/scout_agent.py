"""
Scout Agent — async loop that batch-scans a static universe of tickers for
EMA crossovers and volume/price anomalies using vectorised pandas calculations,
then forwards triggered signals to the Analyst Agent.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from adapters.alpaca_adapter import AlpacaAdapter
from adapters.quiver_adapter import QuiverQuantAdapter
from adapters.universe_scanner import fetch_batch_bars, scan_universe
from agents.analyst_agent import AnalystAgent
from activity_feed import feed, FeedSource, FeedEvent
from config import settings
from models.models import AgentState, AgentStatus, TradeSignal
from watchlist_store import WatchlistStore

logger = logging.getLogger(__name__)


def _load_universe(filepath: str) -> list[str]:
    """Load universe tickers from a JSON file."""
    path = Path(filepath)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / filepath
    if not path.exists():
        logger.warning("Universe file not found: %s — using empty list", path)
        return []
    try:
        data = json.loads(path.read_text())
        if isinstance(data, list):
            return [str(t).upper().strip() for t in data if t]
        logger.warning("Universe file is not a JSON array")
        return []
    except Exception:
        logger.exception("Failed to load universe file: %s", path)
        return []


class ScoutAgent:
    """
    Batch-scans a static universe of ~500 tickers for EMA crossovers and
    volume/price anomalies at a configurable interval.

    Uses vectorised pandas calculations (no per-ticker for-loops) via
    ``universe_scanner.scan_universe()``.

    Triggered tickers are enriched with snapshot + alt-data and handed
    to the Analyst Agent for LLM analysis.
    """

    def __init__(self, analyst: AnalystAgent, watchlist_store: "WatchlistStore | None" = None) -> None:
        self._alpaca = AlpacaAdapter()
        self._quiver = QuiverQuantAdapter()
        self._analyst = analyst
        self._watchlist = watchlist_store
        self._running = False
        self._task: asyncio.Task | None = None
        self.status = AgentStatus(name="ScoutAgent")
        self._last_signalled: dict[str, datetime] = {}  # ticker → UTC timestamp
        self._ET = ZoneInfo("America/New_York")
        self._analyst_semaphore = asyncio.Semaphore(5)  # max 5 concurrent Analyst calls

    # ── Lifecycle ──────────────────────────────────────────────────────

    @property
    def running(self) -> bool:
        """Whether the scanning loop is active."""
        return self._running

    async def start(self) -> None:
        """Kick off the background scanning loop."""
        if self._running:
            logger.warning("Scout Agent already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._loop())
        feed.push(FeedSource.SCOUT, FeedEvent.AGENT_STARTED, "Scout Agent started")
        logger.info("Scout Agent started — interval %ds", settings.scout_interval_seconds)

    async def stop(self) -> None:
        """Gracefully cancel the scanning loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.status.state = AgentState.IDLE
        self.status.message = "Stopped"
        feed.push(FeedSource.SCOUT, FeedEvent.AGENT_STOPPED, "Scout Agent stopped")
        logger.info("Scout Agent stopped")

    # ── Core Loop ──────────────────────────────────────────────────────

    async def _loop(self) -> None:
        """Main scanning loop — only scans during US market hours."""
        while self._running:
            # Gate: skip scanning outside market hours
            if not self._is_market_open():
                now_et = datetime.now(self._ET)
                self.status.state = AgentState.IDLE
                self.status.message = f"Market closed — waiting ({now_et.strftime('%H:%M')} ET)"
                await asyncio.sleep(60)  # re-check every 60s
                continue

            try:
                self.status.state = AgentState.SCANNING
                self.status.message = "Scanning universe…"

                await self._scan_universe()

                self.status.state = AgentState.IDLE
                self.status.last_run = datetime.now(timezone.utc)
                self.status.message = "Scan complete — sleeping"
                feed.push(FeedSource.SCOUT, FeedEvent.SCAN_COMPLETE, "Universe scan complete")

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scout loop error")
                self.status.state = AgentState.ERROR
                self.status.message = "Error during scan — retrying"

            await asyncio.sleep(settings.scout_interval_seconds)

    # ── Filters ────────────────────────────────────────────────────────

    def _is_market_open(self) -> bool:
        """Return True if current ET time is within US market hours (Mon-Fri 9:30-16:00)."""
        now_et = datetime.now(self._ET)
        # Skip weekends (Mon=0, Sun=6)
        if now_et.weekday() >= 5:
            return False
        market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        return market_open <= now_et < market_close

    def _is_on_cooldown(self, ticker: str) -> bool:
        """Return True if this ticker was signalled within the cooldown window."""
        last = self._last_signalled.get(ticker)
        if last is None:
            return False
        return (datetime.now(timezone.utc) - last).total_seconds() < settings.ticker_cooldown_hours * 3600

    def _record_signal(self, ticker: str) -> None:
        """Mark a ticker as just signalled."""
        self._last_signalled[ticker] = datetime.now(timezone.utc)

    # ── Universe Scan ─────────────────────────────────────────────────

    async def _scan_universe(self) -> None:
        """
        Batch-fetch bars for the entire universe, run vectorised EMA
        crossover + anomaly detection, then hand triggered tickers to
        the Analyst Agent.
        """

        # ── 1. Build deduplicated ticker list ──────────────────────────
        universe_tickers = _load_universe(settings.universe_file)
        watchlist_tickers = self._watchlist.tickers if self._watchlist else settings.watchlist

        # Merge watchlist into universe (deduplicate, watchlist first)
        seen: set[str] = set()
        all_tickers: list[str] = []
        for t in list(watchlist_tickers) + universe_tickers:
            if t not in seen:
                seen.add(t)
                all_tickers.append(t)

        if not all_tickers:
            logger.warning("No tickers to scan — universe and watchlist both empty")
            feed.push(
                FeedSource.SCOUT, FeedEvent.SCAN_COMPLETE,
                "No tickers to scan — add tickers to universe.json or watchlist",
            )
            return

        n_batches = (len(all_tickers) + settings.universe_batch_size - 1) // settings.universe_batch_size

        feed.push(
            FeedSource.SCOUT, FeedEvent.SCAN_START,
            f"Scanning {len(all_tickers)} tickers in {n_batches} batches",
            metadata={
                "tickers": all_tickers[:3],
                "total": len(all_tickers),
            },
        )
        logger.info(
            "Universe scan: %d tickers in %d batches of %d",
            len(all_tickers), n_batches, settings.universe_batch_size,
        )

        # ── 2. Batch-fetch historical bars ─────────────────────────────
        alpaca_client = self._alpaca._client  # StockHistoricalDataClient
        df = await fetch_batch_bars(alpaca_client, all_tickers, days=60)

        if df.empty:
            logger.warning("No bar data returned from Alpaca")
            feed.push(
                FeedSource.SCOUT, FeedEvent.SCAN_COMPLETE,
                "No bar data returned — Alpaca may be unavailable",
            )
            return

        # ── 3. Vectorised EMA crossover + anomaly detection ────────────
        triggered = scan_universe(df)

        if not triggered:
            logger.info("Universe scan: no crossovers or anomalies detected")
            return

        logger.info("Universe scan: %d tickers triggered", len(triggered))

        # ── 4. Signal pipeline (per-triggered-ticker) ──────────────────
        async def _process_triggered(hit: dict) -> None:
            ticker = hit["ticker"]

            try:
                # Cooldown check
                if self._is_on_cooldown(ticker):
                    logger.debug("Cooldown active for %s — skipping", ticker)
                    return

                # Fetch live snapshot + alt data
                snapshot = await self._alpaca.fetch_snapshot(ticker)
                alt_data = await self._quiver.fetch_snapshot(ticker)

                reason = hit["reason"]
                ema_crossover = hit["ema_crossover"]

                # Log + feed
                if reason in ("anomaly", "both"):
                    logger.info(
                        "🔔  Anomaly: %s | vol_z=%.2f  price_chg=%.2f%%  ema=%s",
                        ticker, hit["vol_z"], hit["price_chg_pct"], hit["ema_state"],
                    )
                    feed.push(
                        FeedSource.SCOUT, FeedEvent.ANOMALY_FOUND,
                        f"Anomaly detected: vol_z={hit['vol_z']:.2f}, Δprice={hit['price_chg_pct']:+.1f}%, EMA={hit['ema_state']}",
                        ticker=ticker,
                    )

                if reason in ("crossover", "both") and ema_crossover:
                    logger.info(
                        "📊  EMA Crossover: %s | %s (fast=%.2f med=%.2f slow=%.2f)",
                        ticker, ema_crossover,
                        hit["ema_values"]["fast"],
                        hit["ema_values"]["medium"],
                        hit["ema_values"]["slow"],
                    )
                    feed.push(
                        FeedSource.SCOUT, FeedEvent.ANOMALY_FOUND,
                        f"EMA {ema_crossover.replace('_', ' ').title()} detected",
                        ticker=ticker,
                    )

                # Build TradeSignal
                signal = TradeSignal(
                    ticker=ticker,
                    price=snapshot.get("price", hit["price"]),
                    volume=snapshot.get("volume", hit["volume"]),
                    volume_z_score=hit["vol_z"],
                    price_change_pct=hit["price_chg_pct"],
                    congressional_trades=alt_data.get("congressional_trades", []),
                    retail_sentiment=alt_data.get("retail_sentiment", {}),
                    ema_state=hit["ema_state"],
                    ema_crossover=ema_crossover,
                    ema_values=hit["ema_values"],
                )

                await self._analyst.analyse(signal)
                self._record_signal(ticker)

            except Exception:
                logger.exception("Scout error processing triggered ticker %s", ticker)

        # Process all triggered tickers concurrently (limited by semaphore)
        async def _limited(hit: dict) -> None:
            async with self._analyst_semaphore:
                await _process_triggered(hit)

        await asyncio.gather(*[_limited(h) for h in triggered])
