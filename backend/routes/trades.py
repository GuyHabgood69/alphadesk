"""
Trade, Risk & Activity Feed API routes.

GET  /api/trades         — trade log
GET  /api/risk-config    — current risk settings
POST /api/risk-config    — update risk settings
GET  /api/portfolio      — portfolio equity + daily P&L
GET  /api/pnl-history    — timestamped P&L snapshots
GET  /api/activity-feed  — agent activity log
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from activity_feed import feed
from config import settings
from models.models import RiskConfig, TradeResult

router = APIRouter(prefix="/api", tags=["trades"])


@router.get("/trades", response_model=list[TradeResult])
async def get_trade_log(request: Request) -> list[TradeResult]:
    """Return the in-memory trade log (most recent first)."""
    analyst = request.app.state.analyst
    return list(reversed(analyst.trade_log))


@router.get("/risk-config", response_model=RiskConfig)
async def get_risk_config(request: Request) -> RiskConfig:
    """Return the current risk parameters."""
    risk = request.app.state.risk
    return RiskConfig(
        max_risk_pct=risk.max_risk_pct,
        max_daily_drawdown_pct=risk.max_daily_drawdown_pct,
    )


@router.post("/risk-config", response_model=RiskConfig)
async def update_risk_config(
    body: RiskConfig, request: Request
) -> RiskConfig:
    """Update the live risk parameters."""
    risk = request.app.state.risk
    risk.max_risk_pct = body.max_risk_pct
    risk.max_daily_drawdown_pct = body.max_daily_drawdown_pct
    return body


@router.get("/portfolio")
async def get_portfolio(request: Request) -> dict:
    """Return portfolio equity, daily P&L, and position limits."""
    risk = request.app.state.risk
    return {
        "equity": risk.portfolio_equity,
        "daily_pnl": risk.daily_pnl,
        "max_positions": settings.max_positions,
    }


@router.get("/pnl-history")
async def get_pnl_history(request: Request) -> list[dict]:
    """Return timestamped intraday P&L snapshots for the chart."""
    risk = request.app.state.risk
    return risk.pnl_history


@router.get("/activity-feed")
async def get_activity_feed() -> list[dict]:
    """Return the most recent agent activity entries."""
    return feed.get_entries(limit=50)


@router.get("/activity-feed/log")
async def get_activity_feed_log() -> list[dict]:
    """Return detailed 24h activity log for the LOG page."""
    from datetime import datetime, timedelta
    since = (datetime.now() - timedelta(hours=24)).isoformat()
    entries = feed.get_entries_since(since)
    # Return newest first
    return list(reversed(entries))


@router.get("/pnl-history-weekly")
async def get_pnl_history_weekly(request: Request) -> list[dict]:
    """Return daily P&L snapshots for the current week."""
    risk = request.app.state.risk
    return risk.pnl_history_weekly


@router.get("/positions")
async def get_positions(request: Request) -> list[dict]:
    """Return currently tracked open positions."""
    pm = request.app.state.position_manager
    return [pos.model_dump(mode="json") for pos in pm.open_positions]


@router.get("/positions/history")
async def get_position_history(request: Request) -> list[dict]:
    """Return closed position history."""
    pm = request.app.state.position_manager
    return [r.model_dump(mode="json") for r in pm.closed_history]


@router.post("/positions/{ticker}/close")
async def close_position_manually(ticker: str, request: Request):
    """Manually close an open position by ticker."""
    pm = request.app.state.position_manager
    success = await pm.manual_close(ticker.upper())
    if not success:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=404,
            content={"detail": f"No open position for {ticker.upper()}"},
        )
    return {"status": "closed", "ticker": ticker.upper()}

