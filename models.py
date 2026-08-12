"""Venue-neutral models used by the strategy, risk gateway, and adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from time import time
from typing import Any
from uuid import uuid4

from market_maker.config import Side, Venue


class OrderStatus(StrEnum):
    NEW = "new"
    OPEN = "open"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TopOfBook:
    venue: Venue
    symbol: str
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    received_at: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread_bps(self) -> float:
        return (self.ask - self.bid) / self.mid * 10_000.0

    @property
    def age_seconds(self) -> float:
        return max(0.0, time() - self.received_at)


@dataclass(frozen=True, slots=True)
class QuoteIntent:
    venue: Venue
    symbol: str
    side: Side
    price: float
    quantity: float
    post_only: bool = True
    client_order_id: str = ""

    @property
    def notional_usd(self) -> float:
        return self.price * self.quantity

    @classmethod
    def new(
        cls, venue: Venue, symbol: str, side: Side, price: float, quantity: float, post_only: bool = True
    ) -> "QuoteIntent":
        return cls(
            venue=venue,
            symbol=symbol,
            side=side,
            price=price,
            quantity=quantity,
            post_only=post_only,
            client_order_id=f"mm-{uuid4().hex[:24]}",
        )


@dataclass(slots=True)
class Order:
    venue: Venue
    symbol: str
    side: Side
    price: float
    quantity: float
    order_id: str
    client_order_id: str
    status: OrderStatus
    created_at: float
    updated_at: float
    raw: dict[str, Any]

    @property
    def notional_usd(self) -> float:
        return self.price * self.quantity

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Position:
    venue: Venue
    symbol: str
    signed_quantity: float
    mark_price: float
    unrealized_pnl_usd: float = 0.0

    @property
    def net_notional_usd(self) -> float:
        return self.signed_quantity * self.mark_price

    @property
    def gross_notional_usd(self) -> float:
        return abs(self.net_notional_usd)


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    venue: Venue
    available_usd: float
    equity_usd: float
    positions: tuple[Position, ...]
    observed_at: float

    @property
    def gross_notional_usd(self) -> float:
        return sum(position.gross_notional_usd for position in self.positions)

    @property
    def net_notional_usd(self) -> float:
        return sum(position.net_notional_usd for position in self.positions)
