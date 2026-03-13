"""
Universe Store — manages the S&P 500 ticker universe with automatic
daily refresh from Wikipedia.

On startup (or when the cache is >24 hours old), fetches the latest
S&P 500 constituents from Wikipedia's "List of S&P 500 companies"
page via ``pandas.read_html()``, writes the tickers to ``universe.json``,
and falls back to the cached file if Wikipedia is unreachable.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import pandas as pd

from config import settings

logger = logging.getLogger(__name__)

_WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
_REFRESH_INTERVAL_SECONDS = 24 * 60 * 60  # 24 hours


def _universe_path() -> Path:
    """Resolve the universe file path (relative to backend root)."""
    p = Path(settings.universe_file)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent / settings.universe_file
    return p


def _fetch_sp500_from_wikipedia() -> list[str]:
    """
    Scrape the current S&P 500 constituents from Wikipedia.

    Returns a sorted list of ticker symbols with dots replaced by hyphens
    (e.g. BRK.B → BRK-B) to match Alpaca's symbol format.
    """
    import io
    from urllib.request import Request, urlopen

    logger.info("Fetching S&P 500 constituents from Wikipedia…")

    # Wikipedia blocks requests without a User-Agent header
    req = Request(_WIKIPEDIA_URL, headers={"User-Agent": "AlphaDesk/1.0"})
    with urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8")

    tables = pd.read_html(io.StringIO(html))

    # The first table on the page is the constituents list
    df = tables[0]

    # The "Symbol" column contains the ticker symbols
    if "Symbol" not in df.columns:
        # Try alternate column names
        symbol_col = None
        for col in df.columns:
            if "symbol" in str(col).lower() or "ticker" in str(col).lower():
                symbol_col = col
                break
        if symbol_col is None:
            raise ValueError(f"Could not find Symbol column. Columns: {list(df.columns)}")
    else:
        symbol_col = "Symbol"

    tickers = (
        df[symbol_col]
        .astype(str)
        .str.strip()
        .str.replace(".", "-", regex=False)  # BRK.B → BRK-B (Alpaca format)
        .tolist()
    )

    # Filter out any empty or invalid entries
    tickers = sorted(set(t for t in tickers if t and t != "nan" and len(t) <= 10))

    logger.info("Fetched %d S&P 500 tickers from Wikipedia", len(tickers))
    return tickers


def _is_cache_stale(path: Path) -> bool:
    """Return True if the cache file is missing, empty, or older than 24h."""
    if not path.exists():
        return True

    try:
        data = json.loads(path.read_text())
        if not isinstance(data, list) or len(data) < 100:
            return True
    except Exception:
        return True

    age = time.time() - os.path.getmtime(path)
    return age > _REFRESH_INTERVAL_SECONDS


def refresh_universe() -> list[str]:
    """
    Refresh the universe ticker list if the cache is stale.

    Called during backend startup. Returns the current ticker list.
    """
    path = _universe_path()

    if not _is_cache_stale(path):
        tickers = json.loads(path.read_text())
        logger.info(
            "Universe cache is fresh (%d tickers) — skipping refresh",
            len(tickers),
        )
        return tickers

    # Try fetching from Wikipedia
    try:
        tickers = _fetch_sp500_from_wikipedia()
        path.write_text(json.dumps(tickers, indent=2))
        logger.info("Universe cache updated: %d tickers → %s", len(tickers), path)
        return tickers
    except Exception:
        logger.exception("Failed to fetch S&P 500 from Wikipedia — using cached file")

        # Fall back to whatever is in the cache
        if path.exists():
            try:
                tickers = json.loads(path.read_text())
                logger.info("Falling back to cached universe: %d tickers", len(tickers))
                return tickers
            except Exception:
                pass

        logger.warning("No universe data available — universe.json is empty")
        return []
