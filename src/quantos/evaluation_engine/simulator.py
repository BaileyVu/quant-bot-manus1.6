import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Any, Optional
from quantos.evaluation_engine.models import Trade, Position, PortfolioState

class PortfolioSimulator:
    """
    Deterministic multi-symbol simulated portfolio for QuantOS V1.
    Tracks cash, positions, and equity curve with strict symbol isolation and honest accounting.
    """
    
    def __init__(self, initial_capital: float = 10000.0, fee_rate: float = 0.001, slippage_rate: float = 0.0005):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate
        
        # Symbol-aware structures
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.equity_curve: List[Dict[str, Any]] = []
        self.total_realized_pnl = 0.0
        self.running_peak = initial_capital
        
    def update_equity(self, timestamp: datetime, current_prices: Dict[str, float]):
        """
        Updates the equity curve based on current market prices for all symbols.
        Implements the Equity Invariant: equity = cash + sum(quantity * mark_price)
        """
        market_value_of_positions = 0.0
        
        # Update mark prices and calculate unrealized PnL
        for symbol, position in self.positions.items():
            if symbol in current_prices:
                position.mark_price = current_prices[symbol]
                position.unrealized_pnl = position.quantity * (position.mark_price - position.entry_price)
                market_value_of_positions += position.quantity * position.mark_price
            else:
                # If no price update, use last known mark price
                market_value_of_positions += position.quantity * position.mark_price
                
        equity = self.cash + market_value_of_positions
        
        # Equity Invariant Checks
        if not np.isfinite(equity) or equity < 0:
            raise ValueError(f"CRITICAL ACCOUNTING FAILURE: Invalid equity state at {timestamp}: {equity}")
            
        self.running_peak = max(self.running_peak, equity)
        drawdown = (equity - self.running_peak) / self.running_peak
        
        self.equity_curve.append({
            'timestamp': timestamp,
            'equity': float(equity),
            'cash': float(self.cash),
            'market_value': float(market_value_of_positions),
            'drawdown': float(drawdown),
            'active_positions': len(self.positions)
        })
        
    def open_position(self, symbol: str, timestamp: datetime, price: float, size_value: float):
        """
        Simulates opening a LONG position with strict capital constraints.
        Accounting: cash = cash - notional - fees - slippage_cost
        """
        if symbol in self.positions:
            return # Already in a position for this symbol
            
        # Realistic entry price including slippage
        entry_slippage_cost = price * self.slippage_rate
        entry_price = price + entry_slippage_cost
        
        # Calculate quantity and fees
        quantity = size_value / entry_price
        entry_fee = size_value * self.fee_rate
        total_cost = size_value + entry_fee
        
        # Capital Constraint Check
        if self.cash < total_cost:
            # Insufficient funds - in production this would be REJECTED by Risk Engine
            return
            
        # Execute accounting
        self.cash -= total_cost
        
        self.positions[symbol] = Position(
            symbol=symbol,
            quantity=quantity,
            entry_price=entry_price,
            entry_time=timestamp,
            mark_price=price,
            fees=entry_fee
        )
        
    def close_position(self, symbol: str, timestamp: datetime, price: float):
        """
        Simulates closing a position.
        Accounting: cash = cash + exit_notional - fees - slippage_cost
        """
        if symbol not in self.positions:
            return
            
        position = self.positions[symbol]
        
        # Realistic exit price including slippage
        exit_slippage_cost = price * self.slippage_rate
        exit_price = price - exit_slippage_cost
        
        exit_notional = position.quantity * exit_price
        exit_fee = exit_notional * self.fee_rate
        
        net_proceeds = exit_notional - exit_fee
        
        # PnL Reconciliation
        entry_notional = position.quantity * position.entry_price
        total_entry_cost = entry_notional + position.fees
        
        gross_pnl = exit_notional - entry_notional
        net_pnl = net_proceeds - total_entry_cost
        pnl_percent = net_pnl / total_entry_cost
        
        # Record trade to ledger
        trade = Trade(
            symbol=symbol,
            entry_time=position.entry_time,
            exit_time=timestamp,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            entry_notional=entry_notional,
            exit_notional=exit_notional,
            entry_fee=position.fees,
            exit_fee=exit_fee,
            entry_slippage=position.quantity * (position.entry_price - (position.entry_price / (1 + self.slippage_rate))),
            exit_slippage=position.quantity * (price - exit_price),
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            pnl_percent=pnl_percent
        )
        self.trades.append(trade)
        
        # Update global state
        self.cash += net_proceeds
        self.total_realized_pnl += net_pnl
        del self.positions[symbol]
        
    def get_metrics(self) -> Dict[str, Any]:
        """
        Calculates required performance metrics using standard conventions.
        """
        if not self.trades:
            return {
                'expected_value': 0.0, 'net_profit': 0.0, 'sharpe_ratio': None,
                'sortino_ratio': None, 'max_drawdown': 0.0, 'profit_factor': None,
                'win_rate': 0.0, 'trade_count': 0, 'average_trade': 0.0,
                'exposure': 0.0, 'total_fees': 0.0, 'total_slippage': 0.0
            }
            
        pnls = [t.net_pnl for t in self.trades]
        pnl_percents = [t.pnl_percent for t in self.trades]
        
        net_profit = sum(pnls)
        win_rate = len([p for p in pnls if p > 0]) / len(pnls)
        
        # Sharpe Ratio (Simplified for 1m timeframe)
        sharpe = np.mean(pnl_percents) / np.std(pnl_percents) * np.sqrt(252 * 24 * 60) if len(pnls) > 1 and np.std(pnl_percents) > 0 else None
        
        # Sortino Ratio
        downside_returns = [p for p in pnl_percents if p < 0]
        sortino = np.mean(pnl_percents) / np.std(downside_returns) * np.sqrt(252 * 24 * 60) if len(downside_returns) > 1 and np.std(downside_returns) > 0 else None
        
        # Max Drawdown
        drawdowns = [e['drawdown'] for e in self.equity_curve]
        max_dd = abs(min(drawdowns)) if drawdowns else 0.0
        
        # Profit Factor
        gross_profit = sum([p for p in pnls if p > 0])
        gross_loss = abs(sum([p for p in pnls if p < 0]))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
        
        # Exposure (Time in market)
        total_steps = len(self.equity_curve)
        market_steps = len([e for e in self.equity_curve if e['active_positions'] > 0])
        exposure = market_steps / total_steps if total_steps > 0 else 0.0
        
        return {
            'expected_value': float(np.mean(pnls)),
            'net_profit': float(net_profit),
            'sharpe_ratio': float(sharpe) if sharpe is not None else None,
            'sortino_ratio': float(sortino) if sortino is not None else None,
            'max_drawdown': float(max_dd),
            'profit_factor': float(profit_factor) if profit_factor is not None else None,
            'win_rate': float(win_rate),
            'trade_count': int(len(pnls)),
            'average_trade': float(np.mean(pnls)),
            'exposure': float(exposure),
            'total_fees': float(sum([t.entry_fee + t.exit_fee for t in self.trades])),
            'total_slippage': float(sum([t.entry_slippage + t.exit_slippage for t in self.trades]))
        }
