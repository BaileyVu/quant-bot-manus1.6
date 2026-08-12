"""Binance Spot adapter using official REST and public WebSocket interfaces."""

from __future__ import annotations

import asyncio
import hashlib
from contextlib import suppress
import hmac
import json
from decimal import ROUND_DOWN, Decimal
from time import time
from typing import Any
from urllib.parse import urlencode

import aiohttp

from market_maker.adapters.base import ExchangeAdapter
from market_maker.config import BotConfig, Environment, Side, Venue
from market_maker.models import AccountSnapshot, Order, OrderStatus, Position, QuoteIntent, TopOfBook


class BinanceAdapter(ExchangeAdapter):
    _LIVE_REST = "https://api.binance.com"
    _TESTNET_REST = "https://testnet.binance.vision"
    _LIVE_WS = "wss://stream.binance.com:9443/ws"
    _TESTNET_WS = "wss://stream.testnet.binance.vision/ws"

    def __init__(self, config: BotConfig) -> None:
        if config.venue != Venue.BINANCE:
            raise ValueError("BinanceAdapter requires venue=binance")
        self.config = config
        self.symbol = config.symbol
        self.base_url = self._LIVE_REST if config.environment == Environment.LIVE else self._TESTNET_REST
        self.ws_url = self._LIVE_WS if config.environment == Environment.LIVE else self._TESTNET_WS
        self._session: aiohttp.ClientSession | None = None
        self._stream_task: asyncio.Task[None] | None = None
        self._book: TopOfBook | None = None
        self._book_ready = asyncio.Event()
        self._price_step = config.strategy.price_step
        self._quantity_step = config.strategy.quantity_step
        self._min_notional = config.strategy.min_notional_usd
        self._base_asset = ""
        self._quote_asset = "USDT"

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        await self._load_symbol_filters()
        self._stream_task = asyncio.create_task(self._run_book_stream(), name="binance-book-ticker")
        try:
            await asyncio.wait_for(self._book_ready.wait(), timeout=8)
        except TimeoutError:
            await self._refresh_book_http()

    async def stop(self) -> None:
        if self._stream_task:
            self._stream_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._stream_task
        if self._session:
            await self._session.close()
            self._session = None

    async def _load_symbol_filters(self) -> None:
        payload = await self._request("GET", "/api/v3/exchangeInfo", {"symbol": self.symbol})
        try:
            details = payload["symbols"][0]
            filters = {item["filterType"]: item for item in details["filters"]}
            self._price_step = float(filters["PRICE_FILTER"]["tickSize"])
            self._quantity_step = float(filters["LOT_SIZE"]["stepSize"])
            notional_filter = filters.get("NOTIONAL", filters.get("MIN_NOTIONAL", {}))
            self._min_notional = float(notional_filter.get("minNotional", 0))
            self._base_asset = details["baseAsset"]
            self._quote_asset = details["quoteAsset"]
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise RuntimeError(f"unable to load exchange filters for {self.symbol}: {payload}") from error

    async def _run_book_stream(self) -> None:
        assert self._session
        url = f"{self.ws_url}/{self.symbol.lower()}@bookTicker"
        reconnect_delay = 1.0
        while True:
            try:
                async with self._session.ws_connect(url, heartbeat=15, receive_timeout=30) as socket:
                    reconnect_delay = 1.0
                    async for message in socket:
                        if message.type != aiohttp.WSMsgType.TEXT:
                            continue
                        payload = json.loads(message.data)
                        self._book = TopOfBook(
                            venue=Venue.BINANCE,
                            symbol=self.symbol,
                            bid=float(payload["b"]),
                            ask=float(payload["a"]),
                            bid_size=float(payload["B"]),
                            ask_size=float(payload["A"]),
                            received_at=time(),
                        )
                        self._book_ready.set()
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 15)

    async def _refresh_book_http(self) -> None:
        payload = await self._request("GET", "/api/v3/ticker/bookTicker", {"symbol": self.symbol})
        self._book = TopOfBook(
            venue=Venue.BINANCE,
            symbol=self.symbol,
            bid=float(payload["bidPrice"]),
            ask=float(payload["askPrice"]),
            bid_size=float(payload["bidQty"]),
            ask_size=float(payload["askQty"]),
            received_at=time(),
        )
        self._book_ready.set()

    async def top_of_book(self) -> TopOfBook:
        if self._book is None:
            await self._refresh_book_http()
        assert self._book
        return self._book

    def _credentials(self) -> tuple[str, str]:
        key = self.config.credentials.binance_api_key
        secret = self.config.credentials.binance_api_secret
        if key is None or secret is None:
            raise RuntimeError(
                "Binance authenticated operation requires BINANCE_API_KEY and BINANCE_API_SECRET"
            )
        return key.get_secret_value(), secret.get_secret_value()

    def _signed_params(self, parameters: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
        api_key, api_secret = self._credentials()
        data = {**parameters, "timestamp": int(time() * 1000), "recvWindow": 5_000}
        query = urlencode(data, doseq=True)
        data["signature"] = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        return data, {"X-MBX-APIKEY": api_key}

    async def _request(
        self, method: str, path: str, parameters: dict[str, Any] | None = None, signed: bool = False
    ) -> Any:
        if not self._session:
            raise RuntimeError("adapter has not been started")
        parameters = parameters or {}
        headers: dict[str, str] = {}
        if signed:
            parameters, headers = self._signed_params(parameters)
        async with self._session.request(
            method, f"{self.base_url}{path}", params=parameters, headers=headers
        ) as response:
            payload = await response.json(content_type=None)
            if response.status >= 400:
                raise RuntimeError(f"Binance {method} {path} failed ({response.status}): {payload}")
            return payload

    @staticmethod
    def _status(raw: str) -> OrderStatus:
        return {
            "NEW": OrderStatus.OPEN,
            "PARTIALLY_FILLED": OrderStatus.OPEN,
            "FILLED": OrderStatus.FILLED,
            "CANCELED": OrderStatus.CANCELED,
            "REJECTED": OrderStatus.REJECTED,
            "EXPIRED": OrderStatus.CANCELED,
        }.get(raw, OrderStatus.UNKNOWN)

    def _to_order(self, payload: dict[str, Any]) -> Order:
        now = time()
        return Order(
            venue=Venue.BINANCE,
            symbol=payload["symbol"],
            side=Side(payload["side"]),
            price=float(payload["price"]),
            quantity=float(payload["origQty"]),
            order_id=str(payload["orderId"]),
            client_order_id=payload.get("clientOrderId", ""),
            status=self._status(payload.get("status", "NEW")),
            created_at=float(payload.get("time", int(now * 1000))) / 1000,
            updated_at=float(payload.get("updateTime", int(now * 1000))) / 1000,
            raw=payload,
        )

    async def account(self) -> AccountSnapshot:
        book = await self.top_of_book()
        payload = await self._request("GET", "/api/v3/account", signed=True)
        balances = {row["asset"]: row for row in payload.get("balances", [])}
        base_quantity = float(balances.get(self._base_asset, {}).get("free", 0)) + float(
            balances.get(self._base_asset, {}).get("locked", 0)
        )
        quote_available = float(balances.get(self._quote_asset, {}).get("free", 0))
        quote_total = quote_available + float(balances.get(self._quote_asset, {}).get("locked", 0))
        position = Position(Venue.BINANCE, self.symbol, base_quantity, book.mid)
        return AccountSnapshot(
            venue=Venue.BINANCE,
            available_usd=quote_available,
            equity_usd=quote_total + position.gross_notional_usd,
            positions=(position,),
            observed_at=time(),
        )

    async def open_orders(self) -> list[Order]:
        payload = await self._request("GET", "/api/v3/openOrders", {"symbol": self.symbol}, signed=True)
        return [self._to_order(item) for item in payload]

    @staticmethod
    def _floor(value: float, step: float) -> float:
        units = (Decimal(str(value)) / Decimal(str(step))).quantize(Decimal("1"), ROUND_DOWN)
        return float(units * Decimal(str(step)))

    async def place_post_only(self, intent: QuoteIntent) -> Order:
        if intent.symbol != self.symbol or not intent.post_only:
            raise ValueError("Binance adapter accepts only post-only intents on its configured symbol")
        quantity = self._floor(intent.quantity, self._quantity_step)
        price = self._floor(intent.price, self._price_step)
        if quantity <= 0 or price <= 0 or quantity * price < self._min_notional:
            raise ValueError("quote does not meet Binance symbol quantity, price, or notional rules")
        payload = await self._request(
            "POST",
            "/api/v3/order",
            {
                "symbol": self.symbol,
                "side": intent.side.value,
                "type": "LIMIT_MAKER",
                "quantity": f"{quantity:.16f}",
                "price": f"{price:.16f}",
                "newClientOrderId": intent.client_order_id,
                "newOrderRespType": "RESULT",
            },
            signed=True,
        )
        return self._to_order(payload)

    async def cancel(self, order: Order) -> None:
        await self._request(
            "DELETE", "/api/v3/order", {"symbol": self.symbol, "orderId": order.order_id}, signed=True
        )

    async def cancel_all(self) -> None:
        await self._request("DELETE", "/api/v3/openOrders", {"symbol": self.symbol}, signed=True)
