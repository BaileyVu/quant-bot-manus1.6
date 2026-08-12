"""Service entry point. Live execution requires both configuration and environment-level acknowledgement."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
from contextlib import suppress
from pathlib import Path

from market_maker.adapters.base import ExchangeAdapter
from market_maker.adapters.binance import BinanceAdapter
from market_maker.adapters.hyperliquid import HyperliquidAdapter
from market_maker.adapters.simulated import SimulatedExchangeAdapter
from market_maker.config import BotConfig, Environment, Venue
from market_maker.engine import MarketMakerEngine
from market_maker.risk import AuditLog


def load_config(path: Path) -> BotConfig:
    """Load non-secret JSON configuration and inject secrets only from the process environment."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    supplied_credentials = raw.pop("credentials", {})
    if supplied_credentials:
        raise ValueError("credentials must not be stored in configuration files; use environment variables")
    raw["credentials"] = {
        "binance_api_key": os.environ.get("BINANCE_API_KEY"),
        "binance_api_secret": os.environ.get("BINANCE_API_SECRET"),
        "hyperliquid_account_address": os.environ.get("HYPERLIQUID_ACCOUNT_ADDRESS"),
        "hyperliquid_api_wallet_private_key": os.environ.get("HYPERLIQUID_API_WALLET_PRIVATE_KEY"),
    }
    raw["operator_live_acknowledgement"] = os.environ.get("OPERATOR_LIVE_ACKNOWLEDGEMENT")
    config = BotConfig.model_validate(raw)
    config.state_path.parent.mkdir(parents=True, exist_ok=True)
    config.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    return config


def build_adapter(config: BotConfig) -> ExchangeAdapter:
    if config.environment == Environment.SIMULATION:
        symbol = config.symbol if config.venue == Venue.BINANCE else config.hyperliquid_coin
        return SimulatedExchangeAdapter(config.venue, symbol)
    if config.venue == Venue.BINANCE:
        return BinanceAdapter(config)
    if config.venue == Venue.HYPERLIQUID:
        return HyperliquidAdapter(config)
    raise ValueError(f"unsupported venue {config.venue}")


async def run(config: BotConfig, once: bool, check_market_data: bool) -> None:
    audit = AuditLog(config.audit_log_path)
    engine = MarketMakerEngine(config, build_adapter(config), audit)
    if check_market_data:
        await engine.adapter.start()
        try:
            book = await engine.adapter.top_of_book()
            print(
                f"market_data_ok venue={book.venue} symbol={book.symbol} "
                f"bid={book.bid} ask={book.ask} age_seconds={book.age_seconds:.3f}"
            )
        finally:
            await engine.adapter.stop()
        return
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(signum, engine.request_stop)
    if once:
        await engine.adapter.start()
        try:
            await engine.cycle()
        finally:
            await engine.adapter.cancel_all()
            await engine.adapter.stop()
        return
    await engine.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Safety-controlled passive market maker")
    parser.add_argument("--config", type=Path, required=True, help="Non-secret JSON configuration file")
    parser.add_argument("--once", action="store_true", help="Run exactly one managed quote cycle and exit")
    parser.add_argument(
        "--check-market-data",
        action="store_true",
        help="Verify public market-data connectivity without using credentials or placing orders",
    )
    arguments = parser.parse_args()
    if arguments.once and arguments.check_market_data:
        parser.error("--once and --check-market-data cannot be used together")
    config = load_config(arguments.config)
    asyncio.run(run(config, arguments.once, arguments.check_market_data))


if __name__ == "__main__":
    main()
