import pytest
import os
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from quantos.core.config import AppConfig, RuntimeMode
from quantos.core.runtime import PaperTradingRuntime
from quantos.execution_engine.engine import ExecutionEngine, Order
from quantos.risk_engine.engine import OrderIntent
from quantos.market_data.models import Candle

def test_paper_mode_hard_safety_boundary():
    """
    Test 17: HARD LIVE-ORDER BLOCK
    Verify that ExecutionEngine rejects real order attempts in PAPER mode.
    """
    engine = ExecutionEngine(mode=RuntimeMode.PAPER)
    order = Order(
        order_id="TEST-001",
        symbol="BTCUSDT",
        direction="BUY",
        quantity=1.0,
        timestamp=datetime.now(timezone.utc)
    )
    
    # Paper fill should work
    res = engine.execute_order(order, 50000.0, 0.001, 0.0005)
    assert res.status == "FILLED"
    
    # If we manually switch to LIVE (which is blocked in Milestone 5)
    engine.mode = RuntimeMode.LIVE
    with pytest.raises(RuntimeError, match="LIVE trading is not implemented"):
        engine.execute_order(order, 50000.0, 0.001, 0.0005)

def test_stale_data_detection():
    """
    Test 15: STALE DATA RULE
    Verify that stale candles do not trigger decisions.
    """
    config = AppConfig()
    config.market_data.stale_threshold_seconds = 60 # 1 minute threshold
    
    runtime = PaperTradingRuntime(config)
    runtime.binance = MagicMock()
    
    # Mock a candle that is 2 minutes old
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=2)
    stale_candle = Candle(
        symbol="BTCUSDT", timestamp=stale_time,
        open=50000.0, high=51000.0, low=49000.0, close=50500.0,
        volume=10.0, is_completed=True
    )
    
    runtime.binance.fetch_klines.return_value = [stale_candle]
    
    # Run iteration
    runtime.run_iteration()
    
    # Verify no position was opened
    assert "BTCUSDT" not in runtime.simulator.positions

def test_state_persistence_recovery():
    """
    Test 16: PERSISTENCE
    Verify state saving and loading.
    """
    config = AppConfig()
    config.paper_trading.state_path = "data/test_state.json"
    
    # 1. Save state
    runtime = PaperTradingRuntime(config)
    runtime.simulator.cash = 12345.67
    runtime.simulator.total_realized_pnl = 500.0
    runtime._save_state()
    
    # 2. Load in new instance
    new_runtime = PaperTradingRuntime(config)
    assert new_runtime.simulator.cash == 12345.67
    assert new_runtime.simulator.total_realized_pnl == 500.0
    
    # Cleanup
    if os.path.exists(config.paper_trading.state_path):
        os.remove(config.paper_trading.state_path)

@patch('quantos.core.runtime.BinanceClient')
@patch('quantos.core.runtime.lgb.Booster')
def test_deterministic_acceptance_flow(mock_booster, mock_binance):
    """
    Test 21: DETERMINISTIC LOCAL ACCEPTANCE TEST
    Full chain: market candle -> feature -> model -> signal -> risk -> paper fill -> portfolio
    """
    config = AppConfig()
    # Mock model and metadata
    with open("models/metadata_1.0.0.json", 'w') as f:
        json.dump({
            "model_version": "1.0.0",
            "features": ["ret_1m", "volatility_15m"],
            "prediction_horizon_minutes": 15,
            "symbols": ["BTCUSDT"]
        }, f)
    
    # Mock model prediction (BUY signal)
    mock_booster.return_value.predict.return_value = [0.8]
    
    runtime = PaperTradingRuntime(config)
    
    # Mock market data (100 candles to satisfy calculator)
    base_time = datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc)
    mock_candles = [
        Candle(
            symbol="BTCUSDT", timestamp=base_time + timedelta(minutes=i),
            open=50000.0, high=50100.0, low=49900.0, close=50000.0,
            volume=1.0, is_completed=True
        ) for i in range(100)
    ]
    
    # Inject latest candle as "current" (not stale)
    mock_candles[-1].timestamp = datetime.now(timezone.utc)
    runtime.binance.fetch_klines.return_value = mock_candles
    
    # Run iteration
    runtime.run_iteration()
    
    # Verify the chain completed
    assert "BTCUSDT" in runtime.simulator.positions
    assert len(runtime.simulator.equity_curve) > 0
    assert runtime.simulator.cash < 10000.0 # Capital spent
