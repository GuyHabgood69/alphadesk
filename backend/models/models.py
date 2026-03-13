"""
Shared Pydantic schemas used across every module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────

class TradeAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class AgentState(str, Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    ANALYSING = "analysing"
    EXECUTING = "executing"
    ERROR = "error"


class EmaState(str, Enum):
    BULLISH = "bullish"    # fast > medium > slow
    BEARISH = "bearish"    # fast < medium < slow
    NEUTRAL = "neutral"    # mixed ordering


# ── Data Layer ─────────────────────────────────────────────────────────

class TradeSignal(BaseModel):
    """Raw anomaly detected by the Scout Agent."""
    ticker: str
    price: float
    volume: int
    volume_z_score: float
    price_change_pct: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Optional alternative-data context from Quiver
    congressional_trades: list[dict] = Field(default_factory=list)
    retail_sentiment: dict = Field(default_factory=dict)

    # EMA crossover context
    ema_state: EmaState | None = None
    ema_crossover: str | None = None       # "golden_cross" | "death_cross" | None
    ema_values: dict | None = None         # {"fast": f, "medium": m, "slow": s}


# ── AI Layer ───────────────────────────────────────────────────────────

class TradeThesis(BaseModel):
    """Structured output from the Analyst Agent (Claude Opus)."""
    ticker: str
    action: TradeAction
    conviction: float = Field(ge=0.0, le=1.0, description="0-1 conviction score")
    notional_usd: float = Field(gt=0, description="Dollar amount to trade")
    stop_loss_pct: float = Field(ge=0, le=100, description="Stop-loss as % from entry")
    rationale: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Risk Layer ─────────────────────────────────────────────────────────

class RiskVerdict(BaseModel):
    """Result of the Risk Manager evaluation."""
    approved: bool
    reason: str


class RiskConfig(BaseModel):
    """User-tunable risk parameters."""
    max_risk_pct: float = Field(
        ge=0.1, le=10.0,
        description="Max % of portfolio equity risked per trade",
    )
    max_daily_drawdown_pct: float = Field(
        ge=1.0, le=50.0,
        description="Max daily drawdown as % of opening equity",
    )


# ── Execution Layer ───────────────────────────────────────────────────

class TradeResult(BaseModel):
    """Record of an executed (or rejected) trade."""
    id: str = ""
    ticker: str
    action: TradeAction
    notional_usd: float
    filled_qty: float = 0.0
    filled_avg_price: float = 0.0
    status: str = "pending"  # pending | filled | rejected | error
    risk_verdict: RiskVerdict | None = None
    thesis_summary: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Memory Layer ──────────────────────────────────────────────────────

class MemoryMatch(BaseModel):
    """A similar historical setup returned from Pinecone."""
    score: float
    ticker: str
    action: str
    rationale: str
    outcome_pnl: float
    timestamp: str


# ── Agent Status ──────────────────────────────────────────────────────

class AgentStatus(BaseModel):
    """Live status of an agent."""
    name: str
    state: AgentState = AgentState.IDLE
    last_run: datetime | None = None
    message: str = ""


# ── Position Manager ─────────────────────────────────────────────────

class ExitReason(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    TIME_EXPIRED = "TIME_EXPIRED"
    MANUAL = "MANUAL"


class TrackedPosition(BaseModel):
    """An open position tracked by the Position Manager."""
    ticker: str
    side: TradeAction  # BUY or SELL
    entry_price: float
    entry_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notional_usd: float
    qty: float

    # Barriers
    stop_loss_price: float
    take_profit_price: float
    max_hold_until: datetime

    # Metadata
    thesis_summary: str = ""
    signal_source: str = ""
    order_id: str = ""


class PositionCloseResult(BaseModel):
    """Record of a closed position."""
    ticker: str
    side: TradeAction
    exit_reason: ExitReason
    entry_price: float
    exit_price: float
    qty: float
    pnl_usd: float
    pnl_pct: float
    hold_duration_hours: float
    closed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

