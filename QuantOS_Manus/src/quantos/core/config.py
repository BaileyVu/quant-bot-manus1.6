import os
from pydantic import BaseModel, Field
from enum import Enum

class RuntimeMode(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"

class MarketDataConfig(BaseModel):
    storage_path: str = Field(default="data/market_data")
    symbols: list[str] = Field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    binance_base_url: str = Field(default="https://api.binance.com")
    stale_threshold_seconds: int = 300 # 5 minutes

class PaperTradingConfig(BaseModel):
    starting_capital: float = 10000.0
    state_path: str = Field(default="data/paper_trading_state.json")

class AppConfig(BaseModel):
    market_data: MarketDataConfig = Field(default_factory=MarketDataConfig)
    paper_trading: PaperTradingConfig = Field(default_factory=PaperTradingConfig)
    mode: RuntimeMode = Field(default=RuntimeMode.PAPER)
    environment: str = Field(default="local")
    
    @classmethod
    def load(cls, config_path: str | None = None) -> "AppConfig":
        # In a real implementation, this would load from a YAML or JSON file.
        # For the MVP, we use environment variables or defaults.
        storage_path = os.environ.get("QUANTOS_DATA_DIR", "data/market_data")
        mode_str = os.environ.get("QUANTOS_MODE", "PAPER").upper()
        mode = RuntimeMode.PAPER if mode_str == "PAPER" else RuntimeMode.LIVE
        
        return cls(
            market_data=MarketDataConfig(storage_path=storage_path),
            mode=mode
        )
