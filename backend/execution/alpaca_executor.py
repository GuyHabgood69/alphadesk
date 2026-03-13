"""
Alpaca Executor — places fractional USD market orders via Alpaca's
paper-trading API using the alpaca-py SDK.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from config import settings
from models.models import TradeAction, TradeResult, TradeThesis

logger = logging.getLogger(__name__)


class AlpacaExecutor:
    """
    Thin wrapper around alpaca-py's TradingClient.

    All orders are submitted as *fractional notional* market orders
    so the system trades dollar amounts rather than share quantities.
    """

    def __init__(self) -> None:
        self._client = None
        try:
            self._client = TradingClient(
                api_key=settings.alpaca_api_key,
                secret_key=settings.alpaca_secret_key,
                paper=True,
            )
            logger.info("Alpaca executor connected (paper mode)")
        except Exception:
            logger.warning("Alpaca executor init failed — orders will be disabled")

    async def execute(self, thesis: TradeThesis) -> TradeResult:
        """
        Submit a fractional USD market order for the given thesis.

        Returns a TradeResult with fill details (or error status).
        """
        if self._client is None:
            logger.warning("Alpaca not connected — skipping order for %s", thesis.ticker)
            return TradeResult(
                id="no-connection",
                ticker=thesis.ticker,
                action=thesis.action,
                notional_usd=thesis.notional_usd,
                status="error",
                thesis_summary="Alpaca not connected",
            )

        side = (
            OrderSide.BUY if thesis.action == TradeAction.BUY else OrderSide.SELL
        )

        try:
            order_req = MarketOrderRequest(
                symbol=thesis.ticker,
                notional=round(thesis.notional_usd, 2),
                side=side,
                time_in_force=TimeInForce.DAY,
            )

            loop = asyncio.get_running_loop()
            order = await loop.run_in_executor(
                None, lambda: self._client.submit_order(order_req)
            )

            logger.info(
                "✅  Order submitted: %s %s $%.2f — id=%s",
                side.value, thesis.ticker, thesis.notional_usd, order.id,
            )

            return TradeResult(
                id=str(order.id),
                ticker=thesis.ticker,
                action=thesis.action,
                notional_usd=thesis.notional_usd,
                filled_qty=float(order.filled_qty or 0),
                filled_avg_price=float(order.filled_avg_price or 0),
                status=order.status.value if order.status else "submitted",
            )

        except Exception as exc:
            logger.exception("Order execution failed for %s", thesis.ticker)
            return TradeResult(
                id=str(uuid.uuid4()),
                ticker=thesis.ticker,
                action=thesis.action,
                notional_usd=thesis.notional_usd,
                status="error",
                thesis_summary=str(exc),
            )

    async def close_position(
        self, ticker: str, qty: float, side: TradeAction,
    ) -> None:
        """
        Submit a market order to close a position.

        Args:
            ticker: Symbol to close.
            qty: Number of shares to sell/buy-to-cover.
            side: TradeAction.SELL to close a long, TradeAction.BUY to close a short.
        """
        if self._client is None:
            logger.warning("Alpaca not connected — cannot close %s", ticker)
            raise ConnectionError("Alpaca not connected")

        order_side = OrderSide.BUY if side == TradeAction.BUY else OrderSide.SELL

        loop = asyncio.get_running_loop()
        order = await loop.run_in_executor(None, lambda: self._client.submit_order(
            MarketOrderRequest(
                symbol=ticker,
                qty=round(qty, 6),
                side=order_side,
                time_in_force=TimeInForce.DAY,
            )
        ))

        logger.info(
            "✅  Close order submitted: %s %s qty=%.4f — id=%s",
            order_side.value, ticker, qty, order.id,
        )
