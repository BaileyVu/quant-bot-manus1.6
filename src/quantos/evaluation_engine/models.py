from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum

class TradeType(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class Trade(BaseModel):
    symbol: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: float
    entry_notional: float
    exit_notional: float
    entry_fee: float
    exit_fee: float
    entry_slippage: float
    exit_slippage: float
    gross_pnl: float
    net_pnl: float
    pnl_percent: float

class Position(BaseModel):
    symbol: str
    quantity: float
    entry_price: float
    entry_time: datetime
    mark_price: float
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    fees: float = 0.0

class PortfolioState(BaseModel):
    timestamp: datetime
    cash: float
    equity: float
    positions: Dict[str, Position] = {}
    total_realized_pnl: float = 0.0

class BacktestMetrics(BaseModel):
    expected_value: float
    net_profit: float
    sharpe_ratio: Optional[float]
    sortino_ratio: Optional[float]
    max_drawdown: float
    profit_factor: Optional[float]
    win_rate: float
    trade_count: int
    average_trade: float
    exposure: float
    total_fees: float
    total_slippage: float

class BacktestReport(BaseModel):
    model_version: str
    symbols: List[str]
    start_time: datetime
    end_time: datetime
    starting_capital: float
    metrics: BacktestMetrics
    equity_curve: List[Dict[str, Any]]
    trades: List[Trade]
    walk_forward_results: Optional[List[Dict[str, Any]]] = None
    monte_carlo_results: Optional[Dict[str, Any]] = None
    data_sufficiency_warning: bool = False
    status: str = "PENDING"
