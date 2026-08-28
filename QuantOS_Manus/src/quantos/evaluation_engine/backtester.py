import pandas as pd
import numpy as np
import lightgbm as lgb
import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from quantos.core.logger import logger
from quantos.feature_engine.calculator import FeatureCalculator
from quantos.alpha_engine.models import AlphaDecision, Signal
from quantos.evaluation_engine.simulator import PortfolioSimulator
from quantos.evaluation_engine.models import BacktestReport, BacktestMetrics
from quantos.risk_engine.engine import RiskEngine, RiskConfig
from quantos.execution_engine.engine import ExecutionEngine

class Backtester:
    """
    Event-driven historical evaluation engine for QuantOS V1.
    Repaired version with strict symbol isolation, risk controls, and robust accounting.
    """
    
    def __init__(self, model_path: str, metadata_path: str):
        self.model = lgb.Booster(model_file=model_path)
        with open(metadata_path, 'r') as f:
            self.metadata = json.load(f)
            
        self.feature_calc = FeatureCalculator()
        self.feature_cols = self.metadata['features']
        self.horizon = self.metadata['prediction_horizon_minutes']
        
        # Core engines
        self.risk_engine = RiskEngine()
        self.execution_engine = ExecutionEngine()
        
    def run(self, df: pd.DataFrame, initial_capital: float = 10000.0) -> BacktestReport:
        """
        Runs a sequential multi-symbol backtest with repaired accounting flow.
        """
        if df.empty:
            raise ValueError("Empty dataframe provided for backtest")
            
        # Ensure data is sorted by timestamp and symbol
        df = df.sort_values(['timestamp', 'symbol']).reset_index(drop=True)
        
        # Calculate features per symbol to ensure isolation
        all_featured = []
        for symbol in df['symbol'].unique():
            symbol_df = df[df['symbol'] == symbol].copy()
            featured_symbol_df = self.feature_calc.calculate_features(symbol_df)
            all_featured.append(featured_symbol_df)
            
        featured_df = pd.concat(all_featured).sort_values(['timestamp', 'symbol']).reset_index(drop=True)
        
        simulator = PortfolioSimulator(initial_capital=initial_capital)
        
        unique_timestamps = sorted(featured_df['timestamp'].unique())
        logger.info(f"Starting REPAIRED backtest across {len(unique_timestamps)} unique timestamps")
        
        # Event-driven loop by timestamp
        for ts in unique_timestamps:
            ts_events = featured_df[featured_df['timestamp'] == ts]
            
            # 1. Update equity first (Mark-to-Market)
            current_prices = dict(zip(ts_events['symbol'], ts_events['close']))
            simulator.update_equity(ts, current_prices)
            
            # 2. Process symbols
            for _, row in ts_events.iterrows():
                symbol = row['symbol']
                price = row['close']
                
                # A. Check for exit signal (Time-based exit)
                if symbol in simulator.positions:
                    pos = simulator.positions[symbol]
                    time_in_trade = (ts - pos.entry_time).total_seconds() / 60
                    if time_in_trade >= self.horizon:
                        # Risk Check for Exit
                        decision = AlphaDecision(
                            symbol=symbol, timestamp=ts, strategy_version="1.0",
                            model_version=self.metadata['model_version'], feature_version="1.0",
                            signal=Signal.SELL
                        )
                        risk_res = self.risk_engine.evaluate_decision(
                            decision, price, simulator.cash, 0.0, simulator.positions
                        )
                        if risk_res.approved:
                            simulator.close_position(symbol, ts, price)
                
                # B. Check for entry signal
                features = row[self.feature_cols]
                if features.isna().any():
                    continue
                    
                pred_score = self.model.predict(features.values.reshape(1, -1))[0]
                
                if symbol not in simulator.positions and pred_score > 0.6:
                    decision = AlphaDecision(
                        symbol=symbol, timestamp=ts, strategy_version="1.0",
                        model_version=self.metadata['model_version'], feature_version="1.0",
                        signal=Signal.BUY, model_score=float(pred_score)
                    )
                    
                    # Risk Engine Approval
                    risk_res = self.risk_engine.evaluate_decision(
                        decision, price, simulator.cash, 10000.0, simulator.positions # Simplified equity check
                    )
                    
                    if risk_res.approved and risk_res.order_intent:
                        # Execution Engine: Order Construction
                        order = self.execution_engine.construct_order(risk_res.order_intent, ts)
                        
                        # Portfolio Simulator: Fill and Accounting
                        simulator.open_position(
                            symbol=symbol,
                            timestamp=ts,
                            price=price,
                            size_value=risk_res.order_intent.notional
                        )
                        
        # Final metrics
        metrics_dict = simulator.get_metrics()
        metrics = BacktestMetrics(**metrics_dict)
        
        report = BacktestReport(
            model_version=self.metadata['model_version'],
            symbols=self.metadata['symbols'],
            start_time=pd.to_datetime(unique_timestamps[0]).to_pydatetime(),
            end_time=pd.to_datetime(unique_timestamps[-1]).to_pydatetime(),
            starting_capital=initial_capital,
            metrics=metrics,
            equity_curve=simulator.equity_curve,
            trades=simulator.trades,
            data_sufficiency_warning=len(featured_df) < 1000,
            status="SUCCESS" if len(simulator.trades) >= 5 else "WARNING"
        )
        
        return report
