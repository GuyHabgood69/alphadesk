"""
Abstract interface that every data adapter must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DataAdapter(ABC):
    """
    Contract for all market-data / alternative-data adapters.

    Every adapter exposes two async methods so that the Scout Agent
    can treat all data sources uniformly.
    """

    @abstractmethod
    async def fetch_snapshot(self, ticker: str) -> dict[str, Any]:
        """
        Return the latest data point for *ticker*.

        For price adapters this is the most recent quote/bar.
        For alternative-data adapters this is the latest signal.
        """
        ...

    @abstractmethod
    async def fetch_history(
        self, ticker: str, days: int = 20
    ) -> list[dict[str, Any]]:
        """
        Return historical data for *ticker* over the last *days* trading days.
        """
        ...
