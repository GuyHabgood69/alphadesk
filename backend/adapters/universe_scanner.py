"""
Universe Scanner — batch-fetches historical bars from Alpaca and runs
vectorised EMA crossover + volume/price anomaly detection across the
entire ticker universe using pandas.

No per-ticker for-loops; all indicator math is groupby + vectorized.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from config import settings

logger = logging.getLogger(__name__)


# ── Batch Bar Fetching ────────────────────────────────────────────────


async def fetch_batch_bars(
    client: StockHistoricalDataClient,
    tickers: list[str],
    days: int = 60,
) -> pd.DataFrame:
    """
    Fetch daily bars for *tickers* over the last *days* calendar days.

    Uses Alpaca's multi-symbol ``StockBarsRequest`` so one API call
    covers up to ``settings.universe_batch_size`` symbols.

    Returns a DataFrame with columns:
        symbol, timestamp, open, high, low, close, volume, vwap
    """
    if client is None or not tickers:
        return pd.DataFrame()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=int(days * 1.5))  # pad for weekends/holidays

    batch_size = settings.universe_batch_size
    frames: list[pd.DataFrame] = []

    for i in range(0, len(tickers), batch_size):
        chunk = tickers[i : i + batch_size]
        try:
            request = StockBarsRequest(
                symbol_or_symbols=chunk,
                timeframe=TimeFrame.Day,
                start=start,
                end=end,
            )

            loop = asyncio.get_running_loop()
            bars = await loop.run_in_executor(
                None, lambda req=request: client.get_stock_bars(req)
            )

            rows: list[dict[str, Any]] = []
            for symbol, bar_list in bars.data.items():
                for bar in bar_list:
                    rows.append(
                        {
                            "symbol": symbol,
                            "timestamp": bar.timestamp,
                            "open": float(bar.open),
                            "high": float(bar.high),
                            "low": float(bar.low),
                            "close": float(bar.close),
                            "volume": int(bar.volume),
                            "vwap": float(bar.vwap),
                        }
                    )

            if rows:
                frames.append(pd.DataFrame(rows))

            logger.debug(
                "Batch %d-%d: fetched bars for %d/%d symbols",
                i, i + len(chunk), len(set(r["symbol"] for r in rows)), len(chunk),
            )

        except Exception:
            logger.exception(
                "Batch bar fetch failed for chunk %d-%d", i, i + len(chunk),
            )

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df.sort_values(["symbol", "timestamp"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


# ── Vectorised Universe Scan ──────────────────────────────────────────


def scan_universe(
    df: pd.DataFrame,
    ema_fast: int | None = None,
    ema_medium: int | None = None,
    ema_slow: int | None = None,
    vol_z_threshold: float | None = None,
    atr_multiplier: float | None = None,
    price_move_threshold_pct: float | None = None,
) -> list[dict[str, Any]]:
    """
    Run EMA crossover + anomaly detection across all symbols in *df*.

    Parameters default to the values in ``settings`` when not supplied.

    Returns a list of dicts for every symbol that triggered:
        {
            "ticker": str,
            "reason": "anomaly" | "crossover" | "both",
            "vol_z": float,
            "price_chg_pct": float,
            "ema_state": "bullish" | "bearish" | "neutral",
            "ema_crossover": "golden_cross" | "death_cross" | None,
            "ema_values": {"fast": f, "medium": m, "slow": s},
            "price": float,
            "volume": int,
        }
    """
    if df.empty:
        return []

    # Resolve defaults
    ema_fast = ema_fast or settings.ema_fast_period
    ema_medium = ema_medium or settings.ema_medium_period
    ema_slow = ema_slow or settings.ema_slow_period
    vol_z_threshold = vol_z_threshold or settings.volume_z_threshold
    atr_multiplier = atr_multiplier or settings.atr_multiplier
    price_move_threshold_pct = price_move_threshold_pct or settings.price_move_threshold_pct

    # ── EMA / SMA computation (vectorised per group) ──────────────────

    grouped_close = df.groupby("symbol")["close"]

    df["ema_fast"] = grouped_close.transform(
        lambda x: x.ewm(span=ema_fast, adjust=False).mean()
    )
    df["ema_medium"] = grouped_close.transform(
        lambda x: x.ewm(span=ema_medium, adjust=False).mean()
    )
    df["ema_slow"] = grouped_close.transform(
        lambda x: x.ewm(span=ema_slow, adjust=False).mean()
    )

    # ── EMA state + crossover detection ───────────────────────────────

    df["bullish"] = (df["ema_fast"] > df["ema_medium"]) & (
        df["ema_medium"] > df["ema_slow"]
    )
    df["bearish"] = (df["ema_fast"] < df["ema_medium"]) & (
        df["ema_medium"] < df["ema_slow"]
    )

    # Previous day state for crossover detection
    df["prev_bullish"] = df.groupby("symbol")["bullish"].shift(1).fillna(False)
    df["prev_bearish"] = df.groupby("symbol")["bearish"].shift(1).fillna(False)

    df["golden_cross"] = df["bullish"] & df["prev_bullish"].eq(False)
    df["death_cross"] = df["bearish"] & df["prev_bearish"].eq(False)

    # ── Volume z-score (vectorised per group) ─────────────────────────

    grouped_vol = df.groupby("symbol")["volume"]
    vol_mean = grouped_vol.transform(lambda x: x.rolling(20, min_periods=5).mean())
    vol_std = grouped_vol.transform(
        lambda x: x.rolling(20, min_periods=5).std().replace(0, np.nan)
    )
    df["vol_z"] = ((df["volume"] - vol_mean) / vol_std).fillna(0.0)

    # ── Price change % (day-over-day close) ───────────────────────────

    df["prev_close"] = grouped_close.shift(1)
    df["price_chg_pct"] = (
        (df["close"] - df["prev_close"]) / df["prev_close"] * 100.0
    ).fillna(0.0)

    # ── ATR-based dynamic threshold ───────────────────────────────────

    df["high_low"] = df["high"] - df["low"]
    df["high_prev"] = (df["high"] - df["prev_close"]).abs()
    df["low_prev"] = (df["low"] - df["prev_close"]).abs()
    df["true_range"] = df[["high_low", "high_prev", "low_prev"]].max(axis=1)
    df["atr"] = df.groupby("symbol")["true_range"].transform(
        lambda x: x.rolling(20, min_periods=5).mean()
    )
    df["atr_threshold_pct"] = (df["atr"] * atr_multiplier / df["close"] * 100.0).fillna(
        price_move_threshold_pct
    )

    # ── Filter to latest bar per symbol ───────────────────────────────

    latest = df.groupby("symbol").tail(1).copy()

    # Anomaly flag: volume z-score OR price move exceeds dynamic threshold
    latest["is_anomaly"] = (latest["vol_z"].abs() >= vol_z_threshold) | (
        latest["price_chg_pct"].abs() >= latest["atr_threshold_pct"]
    )

    # Crossover flag
    latest["has_crossover"] = latest["golden_cross"] | latest["death_cross"]

    # Only keep rows that triggered something
    triggered = latest[latest["is_anomaly"] | latest["has_crossover"]]

    # ── Build result dicts ────────────────────────────────────────────

    results: list[dict[str, Any]] = []
    for _, row in triggered.iterrows():
        is_anomaly = bool(row["is_anomaly"])
        has_cross = bool(row["has_crossover"])

        if is_anomaly and has_cross:
            reason = "both"
        elif is_anomaly:
            reason = "anomaly"
        else:
            reason = "crossover"

        # Determine EMA state string
        if row["bullish"]:
            ema_state = "bullish"
        elif row["bearish"]:
            ema_state = "bearish"
        else:
            ema_state = "neutral"

        # Determine crossover type
        crossover = None
        if row["golden_cross"]:
            crossover = "golden_cross"
        elif row["death_cross"]:
            crossover = "death_cross"

        results.append(
            {
                "ticker": row["symbol"],
                "reason": reason,
                "vol_z": round(float(row["vol_z"]), 2),
                "price_chg_pct": round(float(row["price_chg_pct"]), 2),
                "ema_state": ema_state,
                "ema_crossover": crossover,
                "ema_values": {
                    "fast": round(float(row["ema_fast"]), 2),
                    "medium": round(float(row["ema_medium"]), 2),
                    "slow": round(float(row["ema_slow"]), 2),
                },
                "price": round(float(row["close"]), 2),
                "volume": int(row["volume"]),
            }
        )

    logger.info(
        "Universe scan: %d/%d symbols triggered (%d anomalies, %d crossovers)",
        len(results),
        len(latest),
        sum(1 for r in results if r["reason"] in ("anomaly", "both")),
        sum(1 for r in results if r["reason"] in ("crossover", "both")),
    )

    return results
