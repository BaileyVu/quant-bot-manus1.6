from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from quantos.alpha_engine.models import AlphaDecision, Signal
from quantos.evaluation_engine.models import Position

class RiskConfig(BaseModel):
    max_position_notional: float = 5000.0
    max_total_exposure_pct: float = 0.9
    max_drawdown_limit: float = 0.2
    min_edge_after_costs: float = 0.0005 # 0.05%
    fee_rate: float = 0.001
    slippage_rate: float = 0.0005

class OrderIntent(BaseModel):
    symbol: str
    direction: str # BUY or SELL
    quantity: float
    notional: float
    reason: str

class RiskResult(BaseModel):
    approved: bool
    order_intent: Optional[OrderIntent] = None
    rejection_reason: Optional[str] = None

class RiskEngine:
    """
    Implements mandatory risk controls for QuantOS V1.
    Risk always precedes execution.
    """
    
    def __init__(self, config: RiskConfig = RiskConfig()):
        self.config = config
        
    def evaluate_decision(self, 
                          decision: AlphaDecision, 
                          current_price: float, 
                          cash: float, 
                          equity: float,
                          active_positions: Dict[str, Position]) -> RiskResult:
        """
        Evaluates an alpha decision against risk limits.
        """
        if decision.signal == Signal.HOLD:
            return RiskResult(approved=False, rejection_reason="HOLD signal")
            
        symbol = decision.symbol
        
        # 1. Position Risk: Prevent duplicate entries
        if decision.signal == Signal.BUY and symbol in active_positions:
            return RiskResult(approved=False, rejection_reason="ALREADY_IN_POSITION")
            
        # 2. Drawdown check
        current_drawdown = (equity - 10000.0) / 10000.0 # Simplified for V1
        if current_drawdown < -self.config.max_drawdown_limit:
            return RiskResult(approved=False, rejection_reason="MAX_DRAWDOWN_BREACHED")
            
        # 3. Capital Constraints & Exposure
        if decision.signal == Signal.BUY:
            # Calculate required capital including fees/slippage
            estimated_entry_price = current_price * (1 + self.config.slippage_rate)
            
            # Use a conservative sizing: min(max_notional, available_cash * limit)
            max_allowed_notional = min(self.config.max_position_notional, cash * 0.95)
            
            if max_allowed_notional < (current_price * 0.0001): # Minimal size check
                return RiskResult(approved=False, rejection_reason="INSUFFICIENT_CAPITAL")
                
            quantity = max_allowed_notional / estimated_entry_price
            
            # 4. Edge After Costs (Simplified for V1 backtest)
            # In production, we'd check decision.model_score against costs
            
            return RiskResult(
                approved=True,
                order_intent=OrderIntent(
                    symbol=symbol,
                    direction="BUY",
                    quantity=quantity,
                    notional=max_allowed_notional,
                    reason="Risk approved entry"
                )
            )
            
        elif decision.signal == Signal.SELL:
            if symbol not in active_positions:
                return RiskResult(approved=False, rejection_reason="NO_POSITION_TO_SELL")
                
            pos = active_positions[symbol]
            return RiskResult(
                approved=True,
                order_intent=OrderIntent(
                    symbol=symbol,
                    direction="SELL",
                    quantity=pos.quantity,
                    notional=pos.quantity * current_price,
                    reason="Risk approved exit"
                )
            )
            
        return RiskResult(approved=False, rejection_reason="UNKNOWN_SIGNAL")
