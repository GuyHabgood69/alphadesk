"""
Activity Feed — in-memory log of agent actions for the dashboard.

Each entry has a timestamp, source agent, event type, and message.
The feed is capped at MAX_ENTRIES to prevent unbounded growth.
"""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

MAX_ENTRIES = 2000


class FeedSource(str, Enum):
    SCOUT = "scout"
    ANALYST = "analyst"
    RISK = "risk"
    EXECUTOR = "executor"
    ALERT = "alert"
    SYSTEM = "system"


class FeedEvent(str, Enum):
    SCAN_START = "scan_start"
    ANOMALY_FOUND = "anomaly_found"
    SCAN_COMPLETE = "scan_complete"
    THESIS_REQUEST = "thesis_request"
    THESIS_GENERATED = "thesis_generated"
    RISK_APPROVED = "risk_approved"
    RISK_REJECTED = "risk_rejected"
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    ALERT_SENT = "alert_sent"
    AGENT_STARTED = "agent_started"
    AGENT_STOPPED = "agent_stopped"
    ERROR = "error"
    INFO = "info"


class ActivityFeed:
    """In-memory activity log (single-threaded asyncio only)."""

    def __init__(self) -> None:
        self._entries: list[dict] = []
        self._id_counter: int = 0

    def push(
        self,
        source: FeedSource,
        event: FeedEvent,
        message: str,
        ticker: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Append an event to the feed."""
        entry = {
            "id": self._id_counter,
            "time": datetime.now().strftime("%H:%M:%S"),
            "timestamp": datetime.now().isoformat(),
            "source": source.value,
            "event": event.value,
            "message": message,
            "ticker": ticker,
            "metadata": metadata or {},
        }
        self._entries.append(entry)
        self._id_counter += 1

        # Cap size
        if len(self._entries) > MAX_ENTRIES:
            self._entries = self._entries[-MAX_ENTRIES:]

        logger.debug("Feed [%s/%s]: %s", source.value, event.value, message)

    def get_entries(self, limit: int = 50) -> list[dict]:
        """Return most recent entries, newest first."""
        return list(reversed(self._entries[-limit:]))

    def clear(self) -> None:
        """Clear all entries."""
        self._entries.clear()

    def get_entries_since(self, since_iso: str) -> list[dict]:
        """Return all entries with timestamp >= since_iso."""
        return [
            e for e in self._entries
            if e.get("timestamp", "") >= since_iso
        ]


# Singleton
feed = ActivityFeed()
