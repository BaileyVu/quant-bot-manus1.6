from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from quantos.risk_engine.engine import OrderIntent
from quantos.core.config import RuntimeMode
from quantos.core.logger import logger

class Order(BaseModel):
    order_id: str
    symbol: str
    direction: str
    quantity: float
    order_type: str = "MARKET"
    status: str = "PENDING"
    timestamp: datetime

class ExecutionResult(BaseModel):
    order_id: str
    symbol: str
    filled_quantity: float
    avg_price: float
    fees: float
    status: str # FILLED, REJECTED
    timestamp: datetime

class ExecutionEngine:
    """
    Handles order construction and exchange interaction for QuantOS V1.
    Implements a hard safety boundary to prevent real orders in PAPER mode.
    """
    
    def __init__(self, mode: RuntimeMode = RuntimeMode.PAPER):
        self.mode = mode
        self.order_counter = 0
        
    def construct_order(self, intent: OrderIntent, timestamp: datetime) -> Order:
        """
        Converts approved risk intent into a formal order.
        """
        self.order_counter += 1
        return Order(
            order_id=f"ORD-{self.order_counter:05d}",
            symbol=intent.symbol,
            direction=intent.direction,
            quantity=intent.quantity,
            timestamp=timestamp
        )
        
    def execute_order(self, order: Order, current_price: float, fee_rate: float, slippage_rate: float) -> ExecutionResult:
        """
        Main entry point for order execution.
        Enforces the hard live-order block for Milestone 5.
        """
        if self.mode == RuntimeMode.PAPER:
            return self._process_paper_fill(order, current_price, fee_rate, slippage_rate)
        
        # HARD SAFETY BOUNDARY: Milestone 5 must never submit real orders
        logger.critical(f"CRITICAL SAFETY VIOLATION: Attempted real order execution in {self.mode} mode!")
        raise RuntimeError("LIVE trading is not implemented or authorized in Milestone 5.")

    def _process_paper_fill(self, order: Order, price: float, fee_rate: float, slippage_rate: float) -> ExecutionResult:
        """
        Simulates a fill for the paper trading environment using Milestone 4 accounting.
        """
        # Calculate execution price with slippage
        if order.direction == "BUY":
            fill_price = price * (1 + slippage_rate)
        else:
            fill_price = price * (1 - slippage_rate)
            
        notional = order.quantity * fill_price
        fees = notional * fee_rate
        
        logger.info(f"PAPER FILL: {order.direction} {order.quantity} {order.symbol} @ {fill_price:.4f} (Fee: {fees:.4f})")
        
        return ExecutionResult(
            order_id=order.order_id,
            symbol=order.symbol,
            filled_quantity=order.quantity,
            avg_price=fill_price,
            fees=fees,
            status="FILLED",
            timestamp=datetime.utcnow()
        )
