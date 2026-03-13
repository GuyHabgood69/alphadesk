"""
Agent status & control routes.

GET  /api/agents/status        — Scout & Analyst status + market schedule
POST /api/agents/scout/toggle  — start / stop the Scout loop
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request

from models.models import AgentStatus

router = APIRouter(prefix="/api/agents", tags=["agents"])

_ET = ZoneInfo("America/New_York")


def _market_info() -> dict:
    """Return current market open/close status and next state change."""
    now_et = datetime.now(_ET)
    is_weekend = now_et.weekday() >= 5
    market_open_time = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close_time = now_et.replace(hour=16, minute=0, second=0, microsecond=0)

    if is_weekend:
        is_open = False
        next_event = "Opens Monday 09:30 ET"
    elif now_et < market_open_time:
        is_open = False
        next_event = f"Opens {market_open_time.strftime('%H:%M')} ET"
    elif now_et >= market_close_time:
        is_open = False
        next_event = "Opens tomorrow 09:30 ET"
    else:
        is_open = True
        next_event = f"Closes {market_close_time.strftime('%H:%M')} ET"

    return {
        "market_open": is_open,
        "next_event": next_event,
        "time_et": now_et.strftime("%H:%M ET"),
    }


@router.get("/status")
async def get_agent_statuses(request: Request) -> dict:
    """Return the live status of all agents plus market schedule."""
    scout = request.app.state.scout
    analyst = request.app.state.analyst
    return {
        "agents": [scout.status.model_dump(), analyst.status.model_dump()],
        "market": _market_info(),
    }


@router.post("/scout/toggle")
async def toggle_scout(request: Request) -> dict:
    """Start or stop the Scout Agent scanning loop."""
    scout = request.app.state.scout

    if scout._running:
        await scout.stop()
        return {"action": "stopped", "status": scout.status.model_dump()}
    else:
        await scout.start()
        return {"action": "started", "status": scout.status.model_dump()}
