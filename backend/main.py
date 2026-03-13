"""
AlphaDesk — FastAPI entrypoint.

Lifecycle:
  • startup  → instantiate agents, attach to app.state
  • shutdown → gracefully stop the Scout loop
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from agents.analyst_agent import AnalystAgent
from agents.scout_agent import ScoutAgent
from alerts.pnl_scheduler import PnlScheduler
from alerts.telegram_bot import TelegramBot
from config import settings
from execution.position_manager import PositionManager
from execution.risk_manager import RiskManager
from routes import agents as agents_routes
from routes import auth as auth_routes
from routes import trades as trades_routes
from routes import watchlist as watchlist_routes
from watchlist_store import WatchlistStore
from universe_store import refresh_universe

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-28s | %(levelname)-5s | %(message)s",
)
logger = logging.getLogger(__name__)


# ── JWT Auth Middleware (imported from auth_middleware.py) ─────────
from auth_middleware import JwtAuthMiddleware  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    # ── Startup ────────────────────────────────────────────────────────
    logger.info("🚀  AlphaDesk starting…")

    risk = RiskManager()
    analyst = AnalystAgent(risk_manager=risk)  # I7: inject shared RiskManager

    # Refresh S&P 500 universe (daily, from Wikipedia)
    universe_tickers = refresh_universe()
    logger.info("Universe: %d tickers loaded", len(universe_tickers))

    # Dynamic watchlist — loads from watchlist.json (seeds from config on first run)
    wl_store = WatchlistStore()
    scout = ScoutAgent(analyst=analyst, watchlist_store=wl_store)

    # Daily P&L Telegram scheduler
    telegram = TelegramBot()
    pnl_scheduler = PnlScheduler(risk_manager=risk, telegram_bot=telegram)

    # Position Manager — triple-barrier exit monitoring
    position_mgr = PositionManager(
        alpaca_adapter=scout._alpaca,   # reuse the same Alpaca data client
        alpaca_executor=analyst._executor,
        risk_manager=risk,
        telegram_bot=telegram,
        memory=analyst._memory,
    )
    analyst._position_manager = position_mgr  # inject for post-fill registration

    # Share instances via app.state so routes can access them
    app.state.risk = risk
    app.state.analyst = analyst
    app.state.scout = scout
    app.state.pnl_scheduler = pnl_scheduler
    app.state.position_manager = position_mgr
    app.state.watchlist_store = wl_store

    # Start background tasks
    pnl_scheduler.start()
    position_mgr.start()
    await scout.start()  # auto-start — loop gates to US market hours (9:30–16:00 ET)

    logger.info("✅  Agents initialised — Scout auto-started (market-hours gated)")

    yield  # ← app is serving

    # ── Shutdown ───────────────────────────────────────────────────────
    await position_mgr.stop()
    await pnl_scheduler.stop()
    await scout.stop()
    logger.info("👋  AlphaDesk shut down cleanly")


# ── App Factory ────────────────────────────────────────────────────────

app = FastAPI(
    title="AlphaDesk",
    version="0.1.0",
    description="Autonomous paper-trading system with AI-driven analysis.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# JWT auth middleware (protects all endpoints except /api/auth/login)
app.add_middleware(JwtAuthMiddleware)

app.include_router(auth_routes.router)
app.include_router(trades_routes.router)
app.include_router(agents_routes.router)
app.include_router(watchlist_routes.router)


@app.get("/", tags=["health"])
async def health() -> dict:
    return {"status": "ok", "service": "alphadesk"}
