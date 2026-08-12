"""Inventory-aware passive market-making engine."""

from __future__ import annotations

import asyncio
import math
from collections import deque
from time import time

from market_maker.adapters.base import ExchangeAdapter
from market_maker.config import BotConfig, Side
from market_maker.models import AccountSnapshot, Order, QuoteIntent, TopOfBook
from market_maker.risk import AuditLog, RiskGateway, RiskRejected
from market_maker.state import HaltedStateStore


class QuotePricer:
    """Creates conservative two-sided quotes from a best bid/offer and current inventory."""

    def __init__(self, config: BotConfig) -> None:
        self.config = config

    @staticmethod
    def _floor(value: float, step: float) -> float:
        return math.floor(value / step) * step

    @staticmethod
    def _ceil(value: float, step: float) -> float:
        return math.ceil(value / step) * step

    def make_quotes(self, book: TopOfBook, account: AccountSnapshot) -> tuple[QuoteIntent, QuoteIntent]:
        strategy = self.config.strategy
        risk = self.config.risk
        normalized_inventory = max(-1.0, min(1.0, account.net_notional_usd / risk.max_net_notional_usd))
        reservation_price = book.mid * (
            1.0 - normalized_inventory * strategy.max_inventory_skew_bps / 10_000.0
        )
        half_spread = max(strategy.min_half_spread_bps / 10_000.0, strategy.price_step / book.mid)

        desired_bid = reservation_price * (1.0 - half_spread)
        desired_ask = reservation_price * (1.0 + half_spread)
        # The following clamps protect post-only behavior even before venue-side ALO/LIMIT_MAKER enforcement.
        bid_price = self._floor(min(desired_bid, book.ask - strategy.price_step), strategy.price_step)
        ask_price = self._ceil(max(desired_ask, book.bid + strategy.price_step), strategy.price_step)
        if bid_price <= 0 or ask_price <= bid_price:
            raise RiskRejected("could not construct a valid two-sided passive quote")

        bid_qty = self._floor(strategy.target_order_notional_usd / bid_price, strategy.quantity_step)
        ask_qty = self._floor(strategy.target_order_notional_usd / ask_price, strategy.quantity_step)
        if bid_qty <= 0 or ask_qty <= 0:
            raise RiskRejected("configured notional is below the venue quantity increment")
        return (
            QuoteIntent.new(self.config.venue, book.symbol, Side.BUY, bid_price, bid_qty),
            QuoteIntent.new(self.config.venue, book.symbol, Side.SELL, ask_price, ask_qty),
        )


class MarketMakerEngine:
    """A single-market engine with deliberate failure containment.

    It is intentionally not a cross-exchange arbitrage engine. Each runtime has one venue and one
    market, making its inventory, order state, and venue-side failure behavior auditable.
    """

    def __init__(self, config: BotConfig, adapter: ExchangeAdapter, audit: AuditLog) -> None:
        self.config = config
        self.adapter = adapter
        self.audit = audit
        self.risk = RiskGateway(config, audit)
        self.pricer = QuotePricer(config)
        self._replacements: deque[float] = deque()
        self._stop_requested = asyncio.Event()
        self.state = HaltedStateStore(config.state_path)

    def request_stop(self) -> None:
        self._stop_requested.set()

    def _can_replace(self) -> bool:
        now = time()
        while self._replacements and now - self._replacements[0] > 60:
            self._replacements.popleft()
        return len(self._replacements) < self.config.risk.max_cancel_replace_per_minute

    @staticmethod
    def _price_distance_bps(order: Order, desired: QuoteIntent) -> float:
        return abs(order.price - desired.price) / desired.price * 10_000.0

    def _is_current(self, order: Order, desired: QuoteIntent) -> bool:
        age = time() - order.created_at
        return (
            order.side == desired.side
            and order.quantity == desired.quantity
            and age <= self.config.strategy.quote_ttl_seconds
            and self._price_distance_bps(order, desired) < self.config.strategy.reprice_threshold_bps
        )

    async def _cancel_obsolete(
        self, existing: list[Order], desired: tuple[QuoteIntent, QuoteIntent]
    ) -> list[Order]:
        remaining: list[Order] = []
        for order in existing:
            target = next((item for item in desired if item.side == order.side), None)
            if target and self._is_current(order, target):
                remaining.append(order)
                continue
            if not self._can_replace():
                self.risk.halt("cancel/replace rate limit reached")
                raise RiskRejected(self.risk.halted_reason or "cancel/replace rate limit")
            await self.adapter.cancel(order)
            self._replacements.append(time())
            self.audit.write("order_canceled", order=order)
        return remaining

    async def cycle(self) -> None:
        book = await self.adapter.top_of_book()
        account = await self.adapter.account()
        self.risk.observe_account(account)
        desired = self.pricer.make_quotes(book, account)
        existing = await self.adapter.open_orders()
        retained = await self._cancel_obsolete(existing, desired)
        active_sides = {order.side for order in retained}
        buy_intent, sell_intent = desired
        ordered_intents = (
            (sell_intent, buy_intent)
            if account.net_notional_usd > 0
            else (buy_intent, sell_intent)
            if account.net_notional_usd < 0
            else desired
        )
        for intent in ordered_intents:
            if intent.side in active_sides:
                continue
            try:
                self.risk.approve_quote(intent, book, account, retained)
            except RiskRejected as error:
                if self.risk.is_halted:
                    raise
                self.audit.write("quote_skipped", side=intent.side, reason=str(error))
                continue
            order = await self.adapter.place_post_only(intent)
            retained.append(order)
            active_sides.add(intent.side)
            self.audit.write("order_placed", order=order, book=book)
        await self.adapter.refresh_dead_man_switch()
        self.risk.observe_success()
        self.audit.write(
            "cycle_complete",
            bid=book.bid,
            ask=book.ask,
            net_notional_usd=account.net_notional_usd,
            gross_notional_usd=account.gross_notional_usd,
            open_orders=len(retained),
        )

    async def run(self) -> None:
        previous_halt = self.state.load_halted_reason()
        if previous_halt:
            raise RuntimeError(
                f"refusing to restart after persisted risk halt: {previous_halt}. "
                "Review the incident, then remove the configured state file to acknowledge it."
            )
        await self.adapter.start()
        self.audit.write(
            "engine_started",
            environment=self.config.environment,
            venue=self.config.venue,
            symbol=self.config.symbol,
        )
        try:
            while not self._stop_requested.is_set() and not self.risk.is_halted:
                try:
                    await self.cycle()
                except RiskRejected as error:
                    self.audit.write("quote_rejected", reason=str(error))
                    self.risk.halt(str(error))
                except Exception as error:
                    self.risk.observe_error("market_maker_cycle", error)
                if self.risk.is_halted:
                    break
                await asyncio.sleep(self.config.strategy.quote_refresh_seconds)
        finally:
            try:
                await self.adapter.cancel_all()
                self.audit.write("orders_cancelled_on_stop")
            except Exception as error:
                self.audit.write("cancel_all_failure", detail=repr(error))
            if self.risk.halted_reason:
                self.state.save_halt(self.risk.halted_reason)
            await self.adapter.stop()
            self.audit.write("engine_stopped", halted_reason=self.risk.halted_reason)
