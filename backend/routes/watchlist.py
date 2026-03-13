"""
Watchlist API — dynamic add / remove / list / search endpoints.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["watchlist"])

# ── Cached Alpaca asset list for fast search ───────────────────────────

_asset_cache: list[dict] | None = None


def _load_assets() -> list[dict]:
    """Load all tradable US equities from Alpaca (cached in-memory)."""
    global _asset_cache
    if _asset_cache is not None:
        return _asset_cache
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import GetAssetsRequest
        from alpaca.trading.enums import AssetClass, AssetStatus

        client = TradingClient(settings.alpaca_api_key, settings.alpaca_secret_key)
        request = GetAssetsRequest(asset_class=AssetClass.US_EQUITY, status=AssetStatus.ACTIVE)
        assets = client.get_all_assets(request)
        _asset_cache = [
            {"symbol": a.symbol, "name": a.name or ""}
            for a in assets
            if a.tradable and a.symbol.isalpha()  # skip warrants / units with special chars
        ]
        logger.info("Loaded %d tradable assets for ticker search", len(_asset_cache))
        return _asset_cache
    except Exception:
        logger.warning("Failed to load asset list from Alpaca — search will be unavailable")
        _asset_cache = []
        return []


@router.get("/tickers/search")
async def search_tickers(q: str = Query("", min_length=1, max_length=10)):
    """Search for tickers by symbol prefix or company name substring."""
    query = q.strip().upper()
    if not query:
        return []

    assets = _load_assets()

    # Score: exact prefix on symbol → symbol contains → name contains
    prefix_matches = []
    symbol_matches = []
    name_matches = []

    for a in assets:
        sym = a["symbol"].upper()
        name = a["name"].upper()
        if sym.startswith(query):
            prefix_matches.append(a)
        elif query in sym:
            symbol_matches.append(a)
        elif query in name:
            name_matches.append(a)

    # Sort prefix matches by length (shorter = more relevant)
    prefix_matches.sort(key=lambda x: len(x["symbol"]))
    results = (prefix_matches + symbol_matches + name_matches)[:15]
    return results




class _AddTicker(BaseModel):
    ticker: str


@router.get("/watchlist")
async def get_watchlist(request: Request) -> list[str]:
    """Return the current watchlist tickers."""
    return request.app.state.watchlist_store.tickers


@router.post("/watchlist")
async def add_to_watchlist(body: _AddTicker, request: Request):
    """Add a ticker to the watchlist."""
    store = request.app.state.watchlist_store
    ticker = body.ticker.strip().upper()
    if not ticker:
        return JSONResponse(status_code=400, content={"detail": "Ticker is required"})
    if store.add(ticker):
        return {"status": "added", "ticker": ticker, "watchlist": store.tickers}
    return JSONResponse(
        status_code=409,
        content={"detail": f"{ticker} is already on the watchlist"},
    )


@router.delete("/watchlist/{ticker}")
async def remove_from_watchlist(ticker: str, request: Request):
    """Remove a ticker from the watchlist."""
    store = request.app.state.watchlist_store
    t = ticker.strip().upper()
    if store.remove(t):
        return {"status": "removed", "ticker": t, "watchlist": store.tickers}
    return JSONResponse(
        status_code=404,
        content={"detail": f"{t} is not on the watchlist"},
    )
