import time
import json
import os
import pandas as pd
import lightgbm as lgb
from datetime import datetime, timezone
from typing import Dict, List, Optional

from quantos.core.config import AppConfig, RuntimeMode
from quantos.core.logger import logger
from quantos.market_data.binance import BinanceClient
from quantos.market_data.storage import MarketDataStorage
from quantos.feature_engine.calculator import FeatureCalculator
from quantos.alpha_engine.models import AlphaDecision, Signal
from quantos.risk_engine.engine import RiskEngine, RiskConfig
from quantos.execution_engine.engine import ExecutionEngine
from quantos.evaluation_engine.simulator import PortfolioSimulator

class PaperTradingRuntime:
    """
    Local paper-trading runtime for QuantOS V1.
    Connects live Binance data to the full MVP decision chain.
    """
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.binance = BinanceClient(config.market_data.binance_base_url)
        self.storage = MarketDataStorage(config.market_data.storage_path)
        self.feature_calc = FeatureCalculator()
        self.risk_engine = RiskEngine(RiskConfig(
            fee_rate=0.001, 
            slippage_rate=0.0005
        ))
        self.execution_engine = ExecutionEngine(mode=RuntimeMode.PAPER)
        
        # Load model
        model_path = "models/model_1.0.0.txt"
        meta_path = "models/metadata_1.0.0.json"
        if not os.path.exists(model_path) or not os.path.exists(meta_path):
            raise FileNotFoundError("Model artifacts missing. Run 'train-model' first.")
            
        self.model = lgb.Booster(model_file=model_path)
        with open(meta_path, 'r') as f:
            self.metadata = json.load(f)
        
        self.feature_cols = self.metadata['features']
        self.horizon = self.metadata['prediction_horizon_minutes']
        
        # Initialize Simulator from persisted state or defaults
        self.simulator = self._load_state()
        
        self.is_running = False
        self.last_candle_time: Dict[str, datetime] = {}
        
    def _load_state(self) -> PortfolioSimulator:
        path = self.config.paper_trading.state_path
        sim = PortfolioSimulator(
            initial_capital=self.config.paper_trading.starting_capital,
            fee_rate=0.001,
            slippage_rate=0.0005
        )
        
        if os.path.exists(path):
            try:
                from quantos.evaluation_engine.models import Position, Trade
                with open(path, 'r') as f:
                    state = json.load(f)
                sim.cash = state['cash']
                sim.total_realized_pnl = state.get('total_realized_pnl', 0.0)
                sim.running_peak = state.get('running_peak', sim.initial_capital)
                
                # Restore positions
                for symbol, pos_data in state.get('positions', {}).items():
                    sim.positions[symbol] = Position(**pos_data)
                
                # Restore trade history
                for trade_data in state.get('trades', []):
                    sim.trades.append(Trade(**trade_data))
                
                # Restore equity curve
                sim.equity_curve = state.get('equity_curve', [])
                
                logger.info(f"Resumed paper trading state from {path}. Cash: {sim.cash}, Positions: {len(sim.positions)}")
            except Exception as e:
                logger.error(f"Failed to load state: {e}. Starting fresh.")
        return sim

    def _save_state(self):
        path = self.config.paper_trading.state_path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        # Serialize positions and trades
        positions_json = {s: p.model_dump(mode='json') for s, p in self.simulator.positions.items()}
        trades_json = [t.model_dump(mode='json') for t in self.simulator.trades]
        
        state = {
            'timestamp': datetime.utcnow().isoformat(),
            'cash': self.simulator.cash,
            'total_realized_pnl': self.simulator.total_realized_pnl,
            'running_peak': self.simulator.running_peak,
            'positions': positions_json,
            'trades': trades_json,
            'equity_curve': self.simulator.equity_curve[-100:] # Keep last 100 snapshots
        }
        with open(path, 'w') as f:
            json.dump(state, f, indent=2)

    def run_iteration(self):
        """
        One cycle of the paper trading loop.
        """
        now = datetime.now(timezone.utc)
        current_prices = {}
        
        for symbol in self.config.market_data.symbols:
            try:
                # 1. Fetch latest completed candles
                candles = self.binance.fetch_klines(symbol, limit=100)
                if not candles:
                    continue
                    
                latest_candle = candles[-1]
                current_prices[symbol] = latest_candle.close
                
                # 2. Stale data check
                time_since_candle = (now - latest_candle.timestamp).total_seconds()
                if time_since_candle > self.config.market_data.stale_threshold_seconds:
                    logger.warning(f"STALE DATA for {symbol}: {time_since_candle}s old. Skipping decision.")
                    continue
                
                # 3. Skip if already processed
                if symbol in self.last_candle_time and latest_candle.timestamp <= self.last_candle_time[symbol]:
                    continue
                
                self.last_candle_time[symbol] = latest_candle.timestamp
                logger.info(f"Processing new candle for {symbol} at {latest_candle.timestamp}")
                
                # 4. Feature Generation
                # Convert candles to DataFrame for the existing calculator
                df = pd.DataFrame([c.model_dump() for c in candles])
                featured_df = self.feature_calc.calculate_features(df)
                row = featured_df.iloc[-1]
                
                # 5. Model Inference
                features = row[self.feature_cols]
                if features.isna().any():
                    logger.debug(f"Insufficient data for features on {symbol}")
                    continue
                    
                pred_score = self.model.predict(features.values.reshape(1, -1))[0]
                
                # 6. Signal Logic
                signal = Signal.HOLD
                if symbol not in self.simulator.positions:
                    if pred_score > 0.6:
                        signal = Signal.BUY
                else:
                    pos = self.simulator.positions[symbol]
                    time_in_trade = (latest_candle.timestamp - pos.entry_time).total_seconds() / 60
                    if time_in_trade >= self.horizon:
                        signal = Signal.SELL
                
                if signal == Signal.HOLD:
                    continue
                    
                # 7. Risk Validation
                decision = AlphaDecision(
                    symbol=symbol, timestamp=latest_candle.timestamp,
                    strategy_version="1.0", model_version=self.metadata['model_version'],
                    feature_version="1.0", signal=signal, model_score=float(pred_score)
                )
                
                risk_res = self.risk_engine.evaluate_decision(
                    decision, latest_candle.close, self.simulator.cash, 
                    self.simulator.cash, self.simulator.positions # Simplified equity
                )
                
                if not risk_res.approved:
                    logger.info(f"RISK REJECTED {signal} {symbol}: {risk_res.rejection_reason}")
                    continue
                
                # 8. Paper Execution
                order = self.execution_engine.construct_order(risk_res.order_intent, latest_candle.timestamp)
                
                if signal == Signal.BUY:
                    self.simulator.open_position(
                        symbol=symbol, timestamp=latest_candle.timestamp,
                        price=latest_candle.close, size_value=risk_res.order_intent.notional
                    )
                else:
                    self.simulator.close_position(symbol, latest_candle.timestamp, latest_candle.close)
                
                logger.info(f"PAPER {signal} executed for {symbol} @ {latest_candle.close}")
                self._save_state()
                
            except Exception as e:
                logger.error(f"Error in runtime loop for {symbol}: {e}", exc_info=True)
        
        # 9. Portfolio Update (Mark-to-Market)
        if current_prices:
            self.simulator.update_equity(now, current_prices)
            self._log_status()

    def _log_status(self):
        if not self.simulator.equity_curve:
            return
        latest = self.simulator.equity_curve[-1]
        logger.info(
            f"STATUS | Mode: {self.config.mode} | Equity: {latest['equity']:.2f} | "
            f"Cash: {latest['cash']:.2f} | Positions: {latest['active_positions']} | "
            f"Trades: {len(self.simulator.trades)}"
        )

    def start(self):
        logger.info(f"Starting QuantOS Paper Trading Runtime (Mode: {self.config.mode})")
        self.is_running = True
        try:
            while self.is_running:
                self.run_iteration()
                time.sleep(10) # Poll every 10 seconds
        except KeyboardInterrupt:
            logger.info("Shutdown requested.")
        finally:
            self.is_running = False
            logger.info("Paper Trading Runtime stopped.")
