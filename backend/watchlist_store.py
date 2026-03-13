"""
WatchlistStore — JSON-persisted dynamic watchlist.

Loads from ``watchlist.json`` on init (falls back to config defaults).
Every add / remove writes the file back to disk so state survives restarts.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)

_DEFAULT_FILE = Path(__file__).resolve().parent / "watchlist.json"


class WatchlistStore:
    """
    Manages a persistent JSON-backed watchlist of tickers.
    """

    def __init__(self, path: Path = _DEFAULT_FILE) -> None:
        self._path = path
        self._tickers: list[str] = []  # ordered list, no duplicates
        self._load()

    # ── Public API ────────────────────────────────────────────────────

    @property
    def tickers(self) -> list[str]:
        """Return the current watchlist (copy)."""
        return list(self._tickers)

    def add(self, ticker: str) -> bool:
        """Add a ticker (uppercased). Returns False if already present."""
        t = ticker.strip().upper()
        if not t:
            return False
        if t in self._tickers:
            return False
        self._tickers.append(t)
        self._save()
        logger.info("Watchlist + %s  (%d total)", t, len(self._tickers))
        return True

    def remove(self, ticker: str) -> bool:
        """Remove a ticker. Returns False if not found."""
        t = ticker.strip().upper()
        if t not in self._tickers:
            return False
        self._tickers.remove(t)
        self._save()
        logger.info("Watchlist − %s  (%d total)", t, len(self._tickers))
        return True

    # ── Persistence ───────────────────────────────────────────────────

    def _load(self) -> None:
        """Load from JSON file, falling back to config defaults."""
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._tickers = list(dict.fromkeys(data))  # dedupe, preserve order
                logger.info(
                    "Watchlist loaded from %s (%d tickers)", self._path.name, len(self._tickers),
                )
                return
            except Exception:
                logger.warning("Failed to read %s — using config defaults", self._path.name)

        # First run or bad file → seed from config
        self._tickers = list(settings.watchlist)
        self._save()
        logger.info("Watchlist seeded from config (%d tickers)", len(self._tickers))

    def _save(self) -> None:
        """Persist current list to disk."""
        try:
            self._path.write_text(json.dumps(self._tickers, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("Failed to write watchlist to %s", self._path.name)
