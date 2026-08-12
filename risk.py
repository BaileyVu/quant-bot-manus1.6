"""Central risk gateway. Every quote must pass this module before it reaches an adapter."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from time import time
from typing import Any

from market_maker.config import BotConfig, Side
from market_maker.models import AccountSnapshot, Order, QuoteIntent, TopOfBook


class RiskRejected(RuntimeError):
    """Raised when a quote violates a non-negotiable operating limit."""


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, **data: Any) -> None:
        def normalize(value: Any) -> Any:
            if is_dataclass(value):
                return asdict(value)
            if isinstance(value, Path):
                return str(value)
            return value

        record = {
            "timestamp": time(),
            "event": event,
            **{key: normalize(value) for key, value in data.items()},
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")


class RiskGateway:
    """Fail-closed controls for stale data, inventory, loss, errors, and external kill switches."""

    def __init__(self, config: BotConfig, audit: AuditLog) -> None:
        self.config = config
        self.audit = audit
        self.starting_equity_usd: float | None = None
        self.consecutive_errors = 0
        self.halted_reason: str | None = None

    @property
    def is_halted(self) -> bool:
        return self.halted_reason is not None

    def halt(self, reason: str) -> None:
        if self.halted_reason is None:
            self.halted_reason = reason
            self.audit.write("risk_halt", reason=reason)

    def observe_account(self, account: AccountSnapshot) -> None:
        if self.starting_equity_usd is None:
            self.starting_equity_usd = account.equity_usd
            self.audit.write("risk_baseline", equity_usd=account.equity_usd)
            return
        drawdown = self.starting_equity_usd - account.equity_usd
        if drawdown >= self.config.risk.max_drawdown_usd:
            self.halt(f"drawdown {drawdown:.2f} exceeds configured maximum")

    def observe_error(self, context: str, error: Exception) -> None:
        self.consecutive_errors += 1
        self.audit.write(
            "error", context=context, detail=repr(error), consecutive_errors=self.consecutive_errors
        )
        if self.consecutive_errors >= self.config.risk.max_consecutive_errors:
            self.halt(f"{self.consecutive_errors} consecutive errors: {context}")

    def observe_success(self) -> None:
        self.consecutive_errors = 0

    def _assert_running(self, book: TopOfBook) -> None:
        if self.config.kill_switch_path.exists():
            self.halt(f"kill switch file detected at {self.config.kill_switch_path}")
        if self.halted_reason:
            raise RiskRejected(self.halted_reason)
        if book.age_seconds > self.config.risk.max_book_age_seconds:
            self.halt(f"market data stale for {book.age_seconds:.3f}s")
            raise RiskRejected(self.halted_reason or "stale market data")
        if not (book.bid > 0 and book.ask > book.bid):
            self.halt("invalid market-data top of book")
            raise RiskRejected(self.halted_reason or "invalid book")

    def approve_quote(
        self, intent: QuoteIntent, book: TopOfBook, account: AccountSnapshot, working_orders: list[Order]
    ) -> None:
        self._assert_running(book)
        if intent.quantity <= 0 or intent.price <= 0:
            raise RiskRejected("non-positive quote")
        if not intent.post_only:
            raise RiskRejected("only post-only orders are permitted")
        if intent.notional_usd > self.config.risk.max_order_notional_usd:
            raise RiskRejected("quote notional exceeds maximum order notional")
        if len(working_orders) >= self.config.risk.max_open_orders:
            raise RiskRejected("maximum open-order count reached")
        working_buys = sum(order.notional_usd for order in working_orders if order.side == Side.BUY)
        working_sells = sum(order.notional_usd for order in working_orders if order.side == Side.SELL)
        candidate_buy = intent.notional_usd if intent.side == Side.BUY else 0.0
        candidate_sell = intent.notional_usd if intent.side == Side.SELL else 0.0
        projected_net = account.net_notional_usd + working_buys - working_sells + candidate_buy - candidate_sell
        if abs(projected_net) > self.config.risk.max_net_notional_usd:
            raise RiskRejected("projected net exposure exceeds limit")
        # On a single market, the worst fill path is all bids or all offers filling, not both.
        worst_long = account.net_notional_usd + working_buys + candidate_buy
        worst_short = account.net_notional_usd - working_sells - candidate_sell
        worst_case_gross = max(abs(worst_long), abs(worst_short))
        if worst_case_gross > self.config.risk.max_gross_notional_usd:
            raise RiskRejected("worst-case gross exposure exceeds limit")
        committed_buy_notional = working_buys
        if intent.side == Side.BUY and account.available_usd < (
            committed_buy_notional + intent.notional_usd + self.config.risk.min_balance_buffer_usd
        ):
            raise RiskRejected("available quote balance is below the configured safety buffer")
