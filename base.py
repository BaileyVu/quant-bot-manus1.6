"""Abstract venue adapter contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from market_maker.models import AccountSnapshot, Order, QuoteIntent, TopOfBook


class ExchangeAdapter(ABC):
    """Minimal contract for a passive quoting venue.

    Adapters own API authentication and venue-specific conversion. The strategy never receives
    credentials and cannot make arbitrary venue calls.
    """

    @abstractmethod
    async def start(self) -> None:
        """Initialize clients, instruments, and public market-data subscriptions."""

    @abstractmethod
    async def stop(self) -> None:
        """Close clients, subscriptions, and exchange-native safety mechanisms."""

    @abstractmethod
    async def top_of_book(self) -> TopOfBook:
        """Return the latest order-book top."""

    @abstractmethod
    async def account(self) -> AccountSnapshot:
        """Return account state required by the risk gateway."""

    @abstractmethod
    async def open_orders(self) -> list[Order]:
        """Return working orders created on the configured market."""

    @abstractmethod
    async def place_post_only(self, intent: QuoteIntent) -> Order:
        """Place a passive limit order or raise an adapter exception."""

    @abstractmethod
    async def cancel(self, order: Order) -> None:
        """Cancel one specific working order; cancellation should be idempotent."""

    @abstractmethod
    async def cancel_all(self) -> None:
        """Cancel all working orders for the configured market."""

    async def refresh_dead_man_switch(self) -> None:
        """Refresh venue-native cancel-all protection when available."""
        return None
