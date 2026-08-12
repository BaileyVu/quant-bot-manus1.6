"""Configuration and explicit execution-environment gates."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator


class Environment(StrEnum):
    SIMULATION = "simulation"
    TESTNET = "testnet"
    LIVE = "live"


class Venue(StrEnum):
    BINANCE = "binance"
    HYPERLIQUID = "hyperliquid"


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class RiskLimits(BaseModel):
    """Limits are enforced before *every* order submission."""

    max_order_notional_usd: float = Field(gt=0, default=25.0)
    max_net_notional_usd: float = Field(gt=0, default=100.0)
    max_gross_notional_usd: float = Field(gt=0, default=200.0)
    max_open_orders: int = Field(ge=2, default=4)
    max_drawdown_usd: float = Field(gt=0, default=50.0)
    max_book_age_seconds: float = Field(gt=0, default=3.0)
    max_consecutive_errors: int = Field(ge=1, default=3)
    max_cancel_replace_per_minute: int = Field(ge=1, default=30)
    min_balance_buffer_usd: float = Field(ge=0, default=10.0)


class StrategyConfig(BaseModel):
    """Conservative passive quoting parameters for one market."""

    target_order_notional_usd: float = Field(gt=0, default=20.0)
    min_half_spread_bps: float = Field(gt=0, default=12.0)
    reprice_threshold_bps: float = Field(gt=0, default=4.0)
    max_inventory_skew_bps: float = Field(ge=0, default=30.0)
    quote_refresh_seconds: float = Field(gt=0, default=1.5)
    quote_ttl_seconds: float = Field(gt=1, default=12.0)
    price_step: float = Field(gt=0, default=0.01)
    quantity_step: float = Field(gt=0, default=0.0001)
    min_notional_usd: float = Field(ge=0, default=10.0)


class CredentialConfig(BaseModel):
    """Credentials are injected through environment variables, never configuration files."""

    binance_api_key: SecretStr | None = None
    binance_api_secret: SecretStr | None = None
    hyperliquid_account_address: str | None = None
    hyperliquid_api_wallet_private_key: SecretStr | None = None


class BotConfig(BaseModel):
    environment: Environment = Environment.SIMULATION
    venue: Venue = Venue.BINANCE
    symbol: str = "BTCUSDT"
    hyperliquid_coin: str = "BTC"
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    risk: RiskLimits = Field(default_factory=RiskLimits)
    credentials: CredentialConfig = Field(default_factory=CredentialConfig)
    state_path: Path = Path("./runtime/state.json")
    audit_log_path: Path = Path("./runtime/audit.jsonl")
    kill_switch_path: Path = Path("./runtime/KILL_SWITCH")
    operator_live_acknowledgement: str | None = None

    @field_validator("symbol")
    @classmethod
    def uppercase_symbol(cls, value: str) -> str:
        value = value.strip().upper()
        if not value.isalnum():
            raise ValueError("symbol must be alphanumeric, for example BTCUSDT")
        return value

    @model_validator(mode="after")
    def validate_execution_gate(self) -> "BotConfig":
        if self.environment != Environment.LIVE:
            return self
        if self.operator_live_acknowledgement != "I_UNDERSTAND_LIVE_TRADING_RISK":
            raise ValueError(
                "live mode requires OPERATOR_LIVE_ACKNOWLEDGEMENT=I_UNDERSTAND_LIVE_TRADING_RISK"
            )
        if self.venue == Venue.BINANCE and not (
            self.credentials.binance_api_key and self.credentials.binance_api_secret
        ):
            raise ValueError("live Binance mode requires BINANCE_API_KEY and BINANCE_API_SECRET")
        if self.venue == Venue.HYPERLIQUID and not (
            self.credentials.hyperliquid_account_address
            and self.credentials.hyperliquid_api_wallet_private_key
        ):
            raise ValueError(
                "live Hyperliquid mode requires HYPERLIQUID_ACCOUNT_ADDRESS and "
                "HYPERLIQUID_API_WALLET_PRIVATE_KEY"
            )
        return self
