"""
Centralised configuration — reads .env and exposes typed settings.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All tunables and API keys for the AlphaDesk backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Alpaca ──────────────────────────────────────────────────────────
    alpaca_api_key: str = "PLACEHOLDER"
    alpaca_secret_key: str = "PLACEHOLDER"
    alpaca_base_url: str = "https://paper-api.alpaca.markets"

    # ── Quiver Quant ───────────────────────────────────────────────────
    quiver_api_key: str = "PLACEHOLDER"

    # ── Anthropic ──────────────────────────────────────────────────────
    anthropic_api_key: str = "PLACEHOLDER"
    anthropic_model: str = "claude-opus-4-0-20250514"

    # ── Pinecone ───────────────────────────────────────────────────────
    pinecone_api_key: str = "PLACEHOLDER"
    pinecone_index: str = "alphadesk-memory"

    # ── Telegram ───────────────────────────────────────────────────────
    telegram_bot_token: str = "PLACEHOLDER"
    telegram_chat_id: str = "PLACEHOLDER"

    # ── Agent Tunables ─────────────────────────────────────────────────
    watchlist: list[str] = [
        "AAPL", "MSFT", "NVDA", "TSLA", "AMZN",
        "GOOGL", "META", "AMD", "PLTR", "SOFI",
    ]
    scout_interval_seconds: int = 60
    volume_z_threshold: float = 2.5
    price_move_threshold_pct: float = 5.0  # static fallback; ATR-based used when available
    atr_multiplier: float = 1.5            # anomaly = price move > ATR × this multiplier

    # ── EMA Crossover ──────────────────────────────────────────────────
    ema_fast_period: int = 5
    ema_medium_period: int = 15
    ema_slow_period: int = 30

    # ── Signal Filtering ───────────────────────────────────────────────
    scan_blackout_minutes: int = 15     # skip first/last N minutes of market hours
    ticker_cooldown_hours: int = 4      # hours before re-signalling same ticker

    # ── Universe Scan ─────────────────────────────────────────────────
    universe_file: str = "universe.json"    # path to static ticker universe
    universe_batch_size: int = 100          # tickers per Alpaca batch API call

    # ── Risk Defaults ──────────────────────────────────────────────────
    max_risk_pct: float = 1.0      # % of equity per trade
    max_daily_drawdown_pct: float = 10.0  # % of opening equity
    paper_portfolio_equity: float = 100_000.0  # starting equity
    max_notional_usd: float = 500.0  # hard cap per trade from LLM
    # ── Position Manager ────────────────────────────────────────────────
    max_positions: int = 6
    default_stop_loss_pct: float = 3.0        # -3% from entry
    default_take_profit_pct: float = 6.0      # +6% from entry (2:1 R:R)
    max_hold_days: int = 5                    # trading days
    position_check_interval: int = 60         # seconds between barrier checks

    # ── Security ───────────────────────────────────────────────────────
    debug: bool = False  # set True in local .env for dev (disables secure cookies)
    allowed_origins: list[str] = ["http://localhost:3000"]

    # ── Dashboard Auth ─────────────────────────────────────────────────
    dashboard_user: str = "admin"
    dashboard_password: str = "changeme"
    jwt_secret: str = ""  # auto-generated if empty


settings = Settings()
