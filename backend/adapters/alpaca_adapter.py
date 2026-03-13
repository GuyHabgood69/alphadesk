"""
Alpaca Markets adapter — high-frequency price, volume, and quote data.

Uses the alpaca-py SDK to pull real-time snapshots and historical bars
from the Alpaca Data API (paper or live).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest,
    StockLatestBarRequest,
    StockLatestQuoteRequest,
)
from alpaca.data.timeframe import TimeFrame

from config import settings
from adapters.base import DataAdapter

logger = logging.getLogger(__name__)


class AlpacaAdapter(DataAdapter):
    """
    Wraps alpaca-py's StockHistoricalDataClient to satisfy the
    DataAdapter interface.
    """

    def __init__(self) -> None:
        self._client = None
        try:
            self._client = StockHistoricalDataClient(
                api_key=settings.alpaca_api_key,
                secret_key=settings.alpaca_secret_key,
            )
            logger.info("Alpaca data adapter connected")
        except Exception:
            logger.warning("Alpaca data adapter init failed — market data will be unavailable")

    # ── Interface Methods ──────────────────────────────────────────────

    async def fetch_snapshot(self, ticker: str) -> dict[str, Any]:
        """Return latest bar + quote for *ticker*."""
        if self._client is None:
            return {}
        try:
            bar_req = StockLatestBarRequest(symbol_or_symbols=ticker)
            quote_req = StockLatestQuoteRequest(symbol_or_symbols=ticker)

            loop = asyncio.get_running_loop()
            bar = await loop.run_in_executor(
                None, lambda: self._client.get_stock_latest_bar(bar_req)
            )
            quote = await loop.run_in_executor(
                None, lambda: self._client.get_stock_latest_quote(quote_req)
            )

            latest_bar = bar[ticker]
            latest_quote = quote[ticker]

            return {
                "ticker": ticker,
                "price": float(latest_bar.close),
                "open": float(latest_bar.open),
                "high": float(latest_bar.high),
                "low": float(latest_bar.low),
                "volume": int(latest_bar.volume),
                "vwap": float(latest_bar.vwap),
                "bid": float(latest_quote.bid_price),
                "ask": float(latest_quote.ask_price),
                "timestamp": latest_bar.timestamp.isoformat(),
            }
        except Exception:
            logger.exception("Alpaca snapshot failed for %s", ticker)
            return {}

    async def fetch_history(
        self, ticker: str, days: int = 20
    ) -> list[dict[str, Any]]:
        """Return daily bars for *ticker* over the last *days* trading days."""
        if self._client is None:
            return []
        try:
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=int(days * 1.5))  # pad for weekends

            request = StockBarsRequest(
                symbol_or_symbols=ticker,
                timeframe=TimeFrame.Day,
                start=start,
                end=end,
                limit=days,
            )

            loop = asyncio.get_running_loop()
            bars = await loop.run_in_executor(
                None, lambda: self._client.get_stock_bars(request)
            )
            result: list[dict[str, Any]] = []

            for bar in bars[ticker]:
                result.append(
                    {
                        "date": bar.timestamp.isoformat(),
                        "open": float(bar.open),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": int(bar.volume),
                        "vwap": float(bar.vwap),
                    }
                )

            return result
        except Exception:
            logger.exception("Alpaca history failed for %s", ticker)
            return []

    # ── Anomaly Helpers ────────────────────────────────────────────────

    async def compute_volume_z_score(self, ticker: str) -> float:
        """
        Z-score of today's volume vs. the 20-day mean.
        Returns 0.0 on failure.
        """
        history = await self.fetch_history(ticker, days=20)
        if len(history) < 2:
            return 0.0

        volumes = np.array([bar["volume"] for bar in history])
        mean_vol = float(np.mean(volumes[:-1]))  # exclude today
        std_vol = float(np.std(volumes[:-1], ddof=1)) or 1.0
        today_vol = float(volumes[-1])

        return (today_vol - mean_vol) / std_vol

    async def compute_price_change_pct(self, ticker: str) -> float:
        """
        Percentage change from yesterday's close to the latest price.
        Returns 0.0 on failure.
        """
        snapshot = await self.fetch_snapshot(ticker)
        history = await self.fetch_history(ticker, days=2)

        if not snapshot or len(history) < 2:
            return 0.0

        prev_close = history[-2]["close"]
        current = snapshot["price"]

        return ((current - prev_close) / prev_close) * 100.0

    async def compute_atr(self, ticker: str, period: int = 20) -> float:
        """
        Average True Range over *period* daily bars.
        Returns ATR in dollars, or 0.0 on failure.
        """
        history = await self.fetch_history(ticker, days=period + 1)
        if len(history) < 2:
            return 0.0

        true_ranges: list[float] = []
        for i in range(1, len(history)):
            high = history[i]["high"]
            low = history[i]["low"]
            prev_close = history[i - 1]["close"]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)

        return float(np.mean(true_ranges)) if true_ranges else 0.0

    async def compute_atr_threshold_pct(self, ticker: str) -> float | None:
        """
        Dynamic price-move threshold based on ATR × multiplier.
        Returns the threshold as a percentage of current price, or None on failure.
        """
        atr = await self.compute_atr(ticker)
        if atr <= 0:
            return None

        snapshot = await self.fetch_snapshot(ticker)
        price = snapshot.get("price", 0.0)
        if price <= 0:
            return None

        threshold_dollars = atr * settings.atr_multiplier
        threshold_pct = (threshold_dollars / price) * 100.0

        logger.debug(
            "ATR %s: $%.2f × %.1f = $%.2f (%.1f%% of $%.2f)",
            ticker, atr, settings.atr_multiplier, threshold_dollars, threshold_pct, price,
        )
        return threshold_pct

    # ── EMA Crossover ─────────────────────────────────────────────────

    @staticmethod
    def _calc_ema(prices: list[float], period: int) -> list[float]:
        """Compute EMA series for the given period using exponential smoothing."""
        if len(prices) < period:
            return []
        multiplier = 2 / (period + 1)
        ema = [float(np.mean(prices[:period]))]  # seed with SMA
        for price in prices[period:]:
            ema.append(price * multiplier + ema[-1] * (1 - multiplier))
        return ema

    async def compute_ema_signals(self, ticker: str) -> dict:
        """
        Compute 5/15/30-day EMAs and detect crossover events.

        Returns:
            {
                "state": "bullish" | "bearish" | "neutral",
                "crossover": "golden_cross" | "death_cross" | None,
                "values": {"fast": f, "medium": m, "slow": s},
            }
        """
        slow_period = settings.ema_slow_period  # 30
        # Fetch enough bars so we have the full slow-period EMA + 1 day for crossover
        history = await self.fetch_history(ticker, days=slow_period + 10)

        closes = [bar["close"] for bar in history]

        if len(closes) < slow_period + 1:
            return {"state": "neutral", "crossover": None, "values": None}

        fast_ema = self._calc_ema(closes, settings.ema_fast_period)
        med_ema = self._calc_ema(closes, settings.ema_medium_period)
        slow_ema = self._calc_ema(closes, slow_period)

        if not fast_ema or not med_ema or not slow_ema:
            return {"state": "neutral", "crossover": None, "values": None}

        # Current values (latest)
        f, m, s = fast_ema[-1], med_ema[-1], slow_ema[-1]

        # Determine today's trend state
        if f > m > s:
            state = "bullish"
        elif f < m < s:
            state = "bearish"
        else:
            state = "neutral"

        # Determine yesterday's state for crossover detection
        crossover = None
        if len(fast_ema) >= 2 and len(med_ema) >= 2 and len(slow_ema) >= 2:
            fp, mp, sp = fast_ema[-2], med_ema[-2], slow_ema[-2]
            if fp > mp > sp:
                prev_state = "bullish"
            elif fp < mp < sp:
                prev_state = "bearish"
            else:
                prev_state = "neutral"

            if state == "bullish" and prev_state != "bullish":
                crossover = "golden_cross"
            elif state == "bearish" and prev_state != "bearish":
                crossover = "death_cross"

        logger.debug(
            "EMA %s: fast=%.2f med=%.2f slow=%.2f → %s%s",
            ticker, f, m, s, state,
            f" ({crossover})" if crossover else "",
        )

        return {
            "state": state,
            "crossover": crossover,
            "values": {"fast": round(f, 2), "medium": round(m, 2), "slow": round(s, 2)},
        }


