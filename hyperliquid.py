"""Hyperliquid perpetuals adapter using its official Python SDK and L2-book WebSocket feed."""

from __future__ import annotations

import asyncio
import json
import math
from contextlib import suppress
from time import time
from typing import Any

import websockets
from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
from hyperliquid.utils.types import Cloid

from market_maker.adapters.base import ExchangeAdapter
from market_maker.config import BotConfig, Environment, Side, Venue
from market_maker.models import AccountSnapshot, Order, OrderStatus, Position, QuoteIntent, TopOfBook


class HyperliquidAdapter(ExchangeAdapter):
    _LIVE_WS = "wss://api.hyperliquid.xyz/ws"
    _TESTNET_WS = "wss://api.hyperliquid-testnet.xyz/ws"

    def __init__(self, config: BotConfig) -> None:
        if config.venue != Venue.HYPERLIQUID:
            raise ValueError("HyperliquidAdapter requires venue=hyperliquid")
        self.config = config
        self.coin = config.hyperliquid_coin.upper()
        self.base_url = (
            constants.MAINNET_API_URL if config.environment == Environment.LIVE else constants.TESTNET_API_URL
        )
        self.ws_url = self._LIVE_WS if config.environment == Environment.LIVE else self._TESTNET_WS
        self._info: Info | None = None
        self._exchange: Exchange | None = None
        self._book: TopOfBook | None = None
        self._book_ready = asyncio.Event()
        self._stream_task: asyncio.Task[None] | None = None
        self._metadata: dict[str, Any] | None = None
        self._size_decimals = 4

    def _require_credentials(self) -> tuple[str, str]:
        address = self.config.credentials.hyperliquid_account_address
        private_key = self.config.credentials.hyperliquid_api_wallet_private_key
        if not address or not private_key:
            raise RuntimeError(
                "Hyperliquid authenticated operation requires HYPERLIQUID_ACCOUNT_ADDRESS and "
                "HYPERLIQUID_API_WALLET_PRIVATE_KEY"
            )
        return address.lower(), private_key.get_secret_value()

    async def start(self) -> None:
        # Market-data only operation works without credentials. Authentication is deferred to order calls.
        # Perpetuals do not need spot asset metadata. Supplying an empty spot universe avoids
        # an SDK Testnet parsing defect when the remote spot metadata is temporarily inconsistent.
        self._info = await asyncio.to_thread(
            Info, self.base_url, True, None, {"universe": [], "tokens": []}
        )
        await self._load_metadata()
        self._stream_task = asyncio.create_task(self._run_book_stream(), name="hyperliquid-l2-book")
        try:
            await asyncio.wait_for(self._book_ready.wait(), timeout=8)
        except TimeoutError:
            await self._refresh_book_http()

    async def stop(self) -> None:
        if self._stream_task:
            self._stream_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._stream_task
        # Do not clear a scheduled venue kill switch on shutdown; it is intentionally fail-closed.

    async def _load_metadata(self) -> None:
        assert self._info
        metadata = await asyncio.to_thread(self._info.meta)
        self._metadata = metadata
        universe = metadata.get("universe", [])
        matching = next((item for item in universe if item.get("name") == self.coin), None)
        if not matching:
            raise ValueError(
                f"Hyperliquid perpetual coin {self.coin} is not present in the selected environment"
            )
        self._size_decimals = int(matching["szDecimals"])

    async def _run_book_stream(self) -> None:
        reconnect_delay = 1.0
        subscription = {
            "method": "subscribe",
            "subscription": {"type": "l2Book", "coin": self.coin, "fast": True},
        }
        while True:
            try:
                async with websockets.connect(
                    self.ws_url, ping_interval=15, ping_timeout=15, close_timeout=5
                ) as socket:
                    await socket.send(json.dumps(subscription))
                    reconnect_delay = 1.0
                    async for raw in socket:
                        payload = json.loads(raw)
                        if payload.get("channel") != "l2Book":
                            continue
                        data = payload["data"]
                        bids, asks = data["levels"]
                        if not bids or not asks:
                            continue
                        self._book = TopOfBook(
                            venue=Venue.HYPERLIQUID,
                            symbol=self.coin,
                            bid=float(bids[0]["px"]),
                            ask=float(asks[0]["px"]),
                            bid_size=float(bids[0]["sz"]),
                            ask_size=float(asks[0]["sz"]),
                            received_at=time(),
                        )
                        self._book_ready.set()
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 15)

    async def _refresh_book_http(self) -> None:
        assert self._info
        snapshot = await asyncio.to_thread(self._info.l2_snapshot, self.coin)
        bids, asks = snapshot["levels"]
        self._book = TopOfBook(
            venue=Venue.HYPERLIQUID,
            symbol=self.coin,
            bid=float(bids[0]["px"]),
            ask=float(asks[0]["px"]),
            bid_size=float(bids[0]["sz"]),
            ask_size=float(asks[0]["sz"]),
            received_at=time(),
        )
        self._book_ready.set()

    async def top_of_book(self) -> TopOfBook:
        if self._book is None:
            await self._refresh_book_http()
        assert self._book
        return self._book

    async def _ensure_exchange(self) -> tuple[str, Info, Exchange]:
        address, secret = self._require_credentials()
        if self._info is None:
            raise RuntimeError("adapter has not been started")
        if self._exchange is None:
            wallet = Account.from_key(secret)
            if self._metadata is None:
                raise RuntimeError("Hyperliquid metadata was not initialized")
            self._exchange = Exchange(
                wallet,
                self.base_url,
                meta=self._metadata,
                account_address=address,
                spot_meta={"universe": [], "tokens": []},
            )
        return address, self._info, self._exchange

    @staticmethod
    def _status(raw: str) -> OrderStatus:
        return {
            "open": OrderStatus.OPEN,
            "filled": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELED,
            "rejected": OrderStatus.REJECTED,
            "marginCanceled": OrderStatus.CANCELED,
        }.get(raw, OrderStatus.UNKNOWN)

    @staticmethod
    def _hyperliquid_cloid(client_order_id: str) -> Cloid:
        # Hyperliquid requires an exact 16-byte hexadecimal value; preserve the random UUID entropy.
        hex_id = "".join(character for character in client_order_id if character in "0123456789abcdef")[-32:]
        return Cloid.from_str(f"0x{hex_id.zfill(32)}")

    def _to_order(self, payload: dict[str, Any]) -> Order:
        now = time()
        return Order(
            venue=Venue.HYPERLIQUID,
            symbol=payload["coin"],
            side=Side.BUY if payload["side"].upper() in {"B", "BUY"} else Side.SELL,
            price=float(payload["limitPx"]),
            quantity=float(payload.get("origSz", payload["sz"])),
            order_id=str(payload["oid"]),
            client_order_id=payload.get("cloid") or "",
            status=OrderStatus.OPEN,
            created_at=float(payload.get("timestamp", int(now * 1000))) / 1000,
            updated_at=now,
            raw=payload,
        )

    async def account(self) -> AccountSnapshot:
        address, info, _ = await self._ensure_exchange()
        state = await asyncio.to_thread(info.user_state, address)
        positions: list[Position] = []
        for row in state.get("assetPositions", []):
            position = row["position"]
            if position["coin"] != self.coin:
                continue
            positions.append(
                Position(
                    venue=Venue.HYPERLIQUID,
                    symbol=self.coin,
                    signed_quantity=float(position["szi"]),
                    mark_price=float(position["positionValue"]) / max(abs(float(position["szi"])), 1e-12),
                    unrealized_pnl_usd=float(position.get("unrealizedPnl", 0)),
                )
            )
        summary = state["marginSummary"]
        return AccountSnapshot(
            venue=Venue.HYPERLIQUID,
            available_usd=float(state["withdrawable"]),
            equity_usd=float(summary["accountValue"]),
            positions=tuple(positions),
            observed_at=time(),
        )

    async def open_orders(self) -> list[Order]:
        address, info, _ = await self._ensure_exchange()
        payload = await asyncio.to_thread(info.open_orders, address)
        return [self._to_order(row) for row in payload if row["coin"] == self.coin]

    def _quantize_size(self, quantity: float) -> float:
        multiplier = 10**self._size_decimals
        return math.floor(quantity * multiplier) / multiplier

    async def place_post_only(self, intent: QuoteIntent) -> Order:
        if intent.symbol != self.coin or not intent.post_only:
            raise ValueError("Hyperliquid adapter accepts only post-only intents on its configured coin")
        _, _, exchange = await self._ensure_exchange()
        quantity = self._quantize_size(intent.quantity)
        if quantity <= 0 or quantity * intent.price < self.config.strategy.min_notional_usd:
            raise ValueError("quote does not meet Hyperliquid configured quantity or minimum-notional rules")
        response = await asyncio.to_thread(
            exchange.order,
            self.coin,
            intent.side == Side.BUY,
            quantity,
            intent.price,
            {"limit": {"tif": "Alo"}},
            False,
            self._hyperliquid_cloid(intent.client_order_id),
        )
        status = response.get("response", {}).get("data", {}).get("statuses", [{}])[0]
        if "error" in status:
            raise RuntimeError(f"Hyperliquid rejected post-only order: {status['error']}")
        if "resting" not in status:
            raise RuntimeError(f"Hyperliquid post-only order did not rest: {response}")
        now = time()
        return Order(
            venue=Venue.HYPERLIQUID,
            symbol=self.coin,
            side=intent.side,
            price=intent.price,
            quantity=quantity,
            order_id=str(status["resting"]["oid"]),
            client_order_id=str(self._hyperliquid_cloid(intent.client_order_id)),
            status=OrderStatus.OPEN,
            created_at=now,
            updated_at=now,
            raw=response,
        )

    async def cancel(self, order: Order) -> None:
        _, _, exchange = await self._ensure_exchange()
        response = await asyncio.to_thread(exchange.cancel, self.coin, int(order.order_id))
        statuses = response.get("response", {}).get("data", {}).get("statuses", [])
        if not statuses or statuses[0] != "success":
            raise RuntimeError(f"Hyperliquid cancel failed: {response}")

    async def cancel_all(self) -> None:
        orders = await self.open_orders()
        if not orders:
            return
        _, _, exchange = await self._ensure_exchange()
        response = await asyncio.to_thread(
            exchange.bulk_cancel, [{"coin": self.coin, "oid": int(order.order_id)} for order in orders]
        )
        statuses = response.get("response", {}).get("data", {}).get("statuses", [])
        if len(statuses) != len(orders) or any(status != "success" for status in statuses):
            raise RuntimeError(f"Hyperliquid cancel-all reported partial failure: {response}")

    async def refresh_dead_man_switch(self) -> None:
        # Schedule a venue-side cancel-all 30 seconds in the future. The engine refreshes it every cycle.
        _, _, exchange = await self._ensure_exchange()
        deadline_ms = int((time() + 30) * 1000)
        response = await asyncio.to_thread(exchange.schedule_cancel, deadline_ms)
        if response.get("status") != "ok":
            raise RuntimeError(f"Hyperliquid dead-man switch refresh failed: {response}")
