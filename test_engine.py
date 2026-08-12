from __future__ import annotations

from time import time

import pytest

from market_maker.adapters.simulated import SimulatedExchangeAdapter
from market_maker.config import BotConfig, Environment, Side, Venue
from market_maker.engine import MarketMakerEngine, QuotePricer
from market_maker.models import AccountSnapshot, Position, TopOfBook
from market_maker.risk import AuditLog, RiskGateway, RiskRejected


def config(tmp_path) -> BotConfig:
    return BotConfig(
        environment=Environment.SIMULATION,
        venue=Venue.BINANCE,
        symbol="BTCUSDT",
        audit_log_path=tmp_path / "audit.jsonl",
        kill_switch_path=tmp_path / "KILL_SWITCH",
        strategy={"price_step": 0.1, "quantity_step": 0.0001, "target_order_notional_usd": 20.0},
    )


def book() -> TopOfBook:
    return TopOfBook(Venue.BINANCE, "BTCUSDT", 99_990.0, 100_010.0, 3.0, 3.0, time())


def account(position_quantity: float = 0.0) -> AccountSnapshot:
    return AccountSnapshot(
        Venue.BINANCE,
        available_usd=10_000.0,
        equity_usd=10_000.0,
        positions=(Position(Venue.BINANCE, "BTCUSDT", position_quantity, 100_000.0),),
        observed_at=time(),
    )


def test_pricer_creates_two_non_crossing_post_only_quotes(tmp_path):
    quotes = QuotePricer(config(tmp_path)).make_quotes(book(), account())
    bid, ask = quotes
    assert bid.price < book().ask
    assert ask.price > book().bid
    assert bid.price < ask.price
    assert bid.notional_usd <= 20.0
    assert ask.notional_usd <= 20.0


def test_inventory_skew_lowers_quotes_when_inventory_is_long(tmp_path):
    pricer = QuotePricer(config(tmp_path))
    flat_bid, flat_ask = pricer.make_quotes(book(), account())
    long_bid, long_ask = pricer.make_quotes(book(), account(position_quantity=0.0008))
    assert long_bid.price < flat_bid.price
    assert long_ask.price < flat_ask.price


def test_risk_gateway_rejects_stale_book(tmp_path):
    current_config = config(tmp_path)
    gateway = RiskGateway(current_config, AuditLog(current_config.audit_log_path))
    stale = TopOfBook(Venue.BINANCE, "BTCUSDT", 99_990.0, 100_010.0, 1.0, 1.0, time() - 10)
    quote = QuotePricer(current_config).make_quotes(book(), account())[0]
    with pytest.raises(RiskRejected):
        gateway.approve_quote(quote, stale, account(), [])
    assert gateway.is_halted


@pytest.mark.asyncio
async def test_engine_places_two_simulated_quotes(tmp_path):
    current_config = config(tmp_path)
    adapter = SimulatedExchangeAdapter(Venue.BINANCE, "BTCUSDT")
    engine = MarketMakerEngine(current_config, adapter, AuditLog(current_config.audit_log_path))
    await adapter.start()
    await engine.cycle()
    orders = await adapter.open_orders()
    assert len(orders) == 2
    assert {order.side for order in orders} == {Side.BUY, Side.SELL}
