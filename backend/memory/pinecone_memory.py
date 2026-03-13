"""
Pinecone Memory — stores trade theses and outcomes as vector embeddings
so the Analyst can query similar historical setups before making decisions.

Gracefully degrades to a no-op when PINECONE_API_KEY is not configured.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime

import anthropic
from pinecone import Pinecone

from config import settings
from models.models import MemoryMatch, TradeResult, TradeThesis

logger = logging.getLogger(__name__)


class PineconeMemory:
    """
    Vector memory backed by Pinecone.

    Embeddings are generated via the Anthropic API (voyage-style) or
    a simple hash-based placeholder if embeddings aren't available.
    """

    DIMENSION = 1024  # Anthropic voyage-3 dimension
    _PLACEHOLDER = "PLACEHOLDER"

    def __init__(self) -> None:
        self._enabled = settings.pinecone_api_key != self._PLACEHOLDER
        self._index_name = settings.pinecone_index
        self._index = None
        self._pc = None
        self._anthropic = None

        if self._enabled:
            try:
                self._pc = Pinecone(api_key=settings.pinecone_api_key)
                self._anthropic = anthropic.Anthropic(api_key=settings.anthropic_api_key)
                logger.info("Pinecone memory enabled — index: %s", self._index_name)
            except Exception:
                logger.warning("Pinecone init failed — memory disabled")
                self._enabled = False
        else:
            logger.info("Pinecone not configured — memory will be skipped")

    # ── Lazy Init ──────────────────────────────────────────────────────

    def _get_index(self):
        """Lazily connect to the Pinecone index."""
        if not self._enabled or self._pc is None:
            return None
        if self._index is None:
            try:
                self._index = self._pc.Index(self._index_name)
                logger.info("Connected to Pinecone index: %s", self._index_name)
            except Exception:
                logger.exception("Failed to connect to Pinecone index")
        return self._index

    # ── Public API ─────────────────────────────────────────────────────

    async def store(self, thesis: TradeThesis, result: TradeResult) -> None:
        """
        Embed the thesis rationale and upsert into Pinecone with
        trade metadata.
        """
        idx = self._get_index()
        if idx is None:
            return

        text = self._build_text(thesis, result)
        embedding = await self._embed(text)

        vector_id = hashlib.sha256(
            f"{thesis.ticker}-{thesis.created_at.isoformat()}".encode()
        ).hexdigest()[:32]

        metadata = {
            "ticker": thesis.ticker,
            "action": thesis.action.value,
            "rationale": thesis.rationale[:500],
            "notional_usd": thesis.notional_usd,
            "conviction": thesis.conviction,
            "outcome_pnl": 0.0,  # updated later when position is closed
            "status": result.status,
            "timestamp": thesis.created_at.isoformat(),
        }

        try:
            idx.upsert(vectors=[(vector_id, embedding, metadata)])
            logger.info("Stored thesis in Pinecone: %s", vector_id)
        except Exception:
            logger.exception("Pinecone upsert failed")

    async def search(self, context: str, top_k: int = 3) -> list[MemoryMatch]:
        """
        Find the top-k most similar historical setups to the given context.
        """
        idx = self._get_index()
        if idx is None:
            return []

        embedding = await self._embed(context)

        try:
            results = idx.query(
                vector=embedding,
                top_k=top_k,
                include_metadata=True,
            )

            matches: list[MemoryMatch] = []
            for match in results.get("matches", []):
                meta = match.get("metadata", {})
                matches.append(
                    MemoryMatch(
                        score=float(match.get("score", 0.0)),
                        ticker=meta.get("ticker", "?"),
                        action=meta.get("action", "?"),
                        rationale=meta.get("rationale", ""),
                        outcome_pnl=float(meta.get("outcome_pnl", 0.0)),
                        timestamp=meta.get("timestamp", ""),
                    )
                )

            return matches
        except Exception:
            logger.exception("Pinecone search failed")
            return []

    async def store_outcome(
        self,
        ticker: str,
        action: str,
        rationale: str,
        pnl: float,
    ) -> None:
        """
        Store a trade outcome (closed position) in Pinecone for future LLM context.
        """
        idx = self._get_index()
        if idx is None:
            return

        text = (
            f"Ticker: {ticker}. Action: {action}. "
            f"Outcome P&L: ${pnl:+.2f}. "
            f"Rationale: {rationale}"
        )
        embedding = await self._embed(text)

        vector_id = hashlib.sha256(
            f"outcome-{ticker}-{datetime.now().isoformat()}".encode()
        ).hexdigest()[:32]

        metadata = {
            "ticker": ticker,
            "action": action,
            "rationale": (rationale or "")[:500],
            "outcome_pnl": pnl,
            "status": "closed",
            "timestamp": datetime.now().isoformat(),
        }

        try:
            idx.upsert(vectors=[(vector_id, embedding, metadata)])
            logger.info("Stored outcome in Pinecone: %s %s P&L=$%.2f", ticker, action, pnl)
        except Exception:
            logger.exception("Pinecone outcome upsert failed")

    # ── Private Helpers ────────────────────────────────────────────────

    def _build_text(self, thesis: TradeThesis, result: TradeResult) -> str:
        """Compose a text blob for embedding."""
        return (
            f"Ticker: {thesis.ticker}. Action: {thesis.action.value}. "
            f"Conviction: {thesis.conviction:.2f}. "
            f"Notional: ${thesis.notional_usd:.2f}. "
            f"Stop-loss: {thesis.stop_loss_pct:.1f}%. "
            f"Status: {result.status}. "
            f"Rationale: {thesis.rationale}"
        )

    async def _embed(self, text: str) -> list[float]:
        """
        Generate an embedding vector for *text*.

        Uses Anthropic's voyage-3 model if available; falls back to a
        deterministic hash-based placeholder for local dev.
        """
        try:
            # Anthropic embedding API (voyage-3)
            response = self._anthropic.embeddings.create(
                model="voyage-3",
                input=[text],
            )
            return response.data[0].embedding
        except Exception:
            logger.warning(
                "Embedding API unavailable — using hash placeholder"
            )
            # Deterministic placeholder: hash → fixed-dim float vector
            h = hashlib.sha512(text.encode()).digest()
            vec = [float(b) / 255.0 for b in h]
            # Pad or truncate to DIMENSION
            vec = (vec * ((self.DIMENSION // len(vec)) + 1))[: self.DIMENSION]
            return vec
