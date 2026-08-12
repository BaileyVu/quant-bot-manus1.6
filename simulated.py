"""Deterministic local exchange for strategy and risk validation without credentials."""

from __future__ import annotations

from time import time
from uuid import uuid4

from market_maker.adapters.base import ExchangeAdapter
from market_maker.config import Side, Venue
from market_maker.models import AccountSnapshot, Order, OrderStatus, Position, QuoteIntent, TopOfBook


class SimulatedExchangeAdapter(ExchangeAdapter):
    """A passive-only fill simulator.

    The adapter deliberately rejects crossing orders. It allows tests and dry runs to exercise the
    same cancel/replace, inventory, and kill-switch paths as external environments.
    """

    def __init__(self, venue: Venue, symbol: str, mid: float = 100_000.0, half_spread: float = 5.0) -> None:
        self.venue = venue
        self.symbol = symbol
        self._book = TopOfBook(venue, symbol, mid - half_spread, mid + half_spread, 2.0, 2.0, time())
        self._orders: dict[str, Order] = {}
        self._position_qty = 0.0
        self._available_usd = 10_000.0

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        await self.cancel_all()

    async def top_of_book(self) -> TopOfBook:
        return self._book

    async def set_book(self, bid: float, ask: float, bid_size: float = 2.0, ask_size: float = 2.0) -> None:
        if bid <= 0 or ask <= bid:
            raise ValueError("book must have 0 < bid < ask")
        self._book = TopOfBook(self.venue, self.symbol, bid, ask, bid_size, ask_size, time())

    async def account(self) -> AccountSnapshot:
        position = Position(self.venue, self.symbol, self._position_qty, self._book.mid)
        return AccountSnapshot(self.venue, self._available_usd, self._available_usd, (position,), time())

    async def open_orders(self) -> list[Order]:
        return [order for order in self._orders.values() if order.status == OrderStatus.OPEN]

    async def place_post_only(self, intent: QuoteIntent) -> Order:
        if intent.symbol != self.symbol or not intent.post_only:
            raise ValueError("simulator only accepts post-only orders on the configured symbol")
        if intent.side == Side.BUY and intent.price >= self._book.ask:
            raise ValueError("post-only buy would cross the simulated book")
        if intent.side == Side.SELL and intent.price <= self._book.bid:
            raise ValueError("post-only sell would cross the simulated book")
        now = time()
        order = Order(
            venue=self.venue,
            symbol=self.symbol,
            side=intent.side,
            price=intent.price,
            quantity=intent.quantity,
            order_id=f"sim-{uuid4().hex}",
            client_order_id=intent.client_order_id,
            status=OrderStatus.OPEN,
            created_at=now,
            updated_at=now,
            raw={"mode": "simulation"},
        )
        self._orders[order.order_id] = order
        return order

    async def cancel(self, order: Order) -> None:
        current = self._orders.get(order.order_id)
        if current and current.status == OrderStatus.OPEN:
            current.status = OrderStatus.CANCELED
            current.updated_at = time()

    async def cancel_all(self) -> None:
        for order in list(await self.open_orders()):
            await self.cancel(order)

    async def simulate_fill(self, order_id: str) -> None:
        """Test helper to fill a working quote at its stated price."""
        order = self._orders[order_id]
        if order.status != OrderStatus.OPEN:
            raise ValueError("only open orders can fill")
        direction = 1.0 if order.side == Side.BUY else -1.0
        self._position_qty += direction * order.quantity
        self._available_usd -= direction * order.notional_usd
        order.status = OrderStatus.FILLED
        order.updated_at = time()
