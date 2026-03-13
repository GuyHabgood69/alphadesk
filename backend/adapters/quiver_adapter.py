"""
Quiver Quantitative adapter — alternative data (Congressional trades,
retail sentiment, etc.) via Quiver's REST API.

Gracefully degrades to empty responses when QUIVER_API_KEY is not
configured (set to PLACEHOLDER).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from config import settings
from adapters.base import DataAdapter

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.quiverquant.com/beta"
_PLACEHOLDER = "PLACEHOLDER"


class QuiverQuantAdapter(DataAdapter):
    """
    Fetches alternative data from Quiver Quant.

    Endpoints used:
    - /historical/congresstrading/{ticker}
    - /live/wallstreetbets/{ticker}  (retail sentiment)
    """

    def __init__(self) -> None:
        self._api_key = settings.quiver_api_key
        self._enabled = bool(self._api_key and self._api_key != _PLACEHOLDER)
        self._client: httpx.AsyncClient | None = None

        if self._enabled:
            self._client = httpx.AsyncClient(
                base_url=_BASE_URL,
                headers={"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"},
                timeout=15.0, # Keep original timeout
            )
            logger.info("QuiverQuantAdapter ready")
        else:
            logger.warning("QuiverQuant API key not set — adapter disabled")

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        if self._client:
            await self._client.aclose()

    # ── Interface Methods ──────────────────────────────────────────────

    async def fetch_snapshot(self, ticker: str) -> dict[str, Any]:
        """
        Aggregate the latest Congressional trades and retail sentiment
        for *ticker* into a single dict.
        """
        if not self._enabled:
            return {"ticker": ticker, "congressional_trades": [], "retail_sentiment": {}}
        congress = await self._get_congressional_trades(ticker)
        sentiment = await self._get_retail_sentiment(ticker)

        return {
            "ticker": ticker,
            "congressional_trades": congress,
            "retail_sentiment": sentiment,
        }

    async def fetch_history(
        self, ticker: str, days: int = 90
    ) -> list[dict[str, Any]]:
        """
        Return historical Congressional trading for *ticker*.
        Quiver returns dates in the payload so we just forward it.
        """
        if not self._enabled:
            return []
        return await self._get_congressional_trades(ticker)

    # ── Private Helpers ────────────────────────────────────────────────

    async def _get_congressional_trades(
        self, ticker: str
    ) -> list[dict[str, Any]]:
        """Fetch recent Congressional trades for *ticker*."""
        try:
            resp = await self._client.get(f"/historical/congresstrading/{ticker}")
            resp.raise_for_status()
            data = resp.json()

            # Normalise to a consistent shape
            return [
                {
                    "representative": row.get("Representative", ""),
                    "transaction": row.get("Transaction", ""),
                    "amount": row.get("Amount", ""),
                    "date": row.get("TransactionDate", ""),
                    "party": row.get("Party", ""),
                }
                for row in data[-10:]  # latest 10
            ]
        except Exception:
            logger.exception("Quiver congressional trades failed for %s", ticker)
            return []

    async def _get_retail_sentiment(self, ticker: str) -> dict[str, Any]:
        """Fetch WSB / retail-sentiment data for *ticker*."""
        try:
            resp = await self._client.get(f"/live/wallstreetbets/{ticker}")
            resp.raise_for_status()
            data = resp.json()

            if data:
                latest = data[-1]
                return {
                    "mentions": latest.get("Mentions", 0),
                    "rank": latest.get("Rank", 0),
                    "sentiment": latest.get("Sentiment", 0.0),
                    "date": latest.get("Date", ""),
                }
            return {}
        except Exception:
            logger.exception("Quiver retail sentiment failed for %s", ticker)
            return {}
