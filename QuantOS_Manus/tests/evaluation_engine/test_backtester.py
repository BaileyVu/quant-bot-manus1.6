import pytest
import pandas as pd
import numpy as np
import os
import json
from datetime import datetime, timezone, timedelta
from quantos.evaluation_engine.backtester import Backtester
from quantos.evaluation_engine.analyzer import EvaluationAnalyzer
from quantos.evaluation_engine.models import Trade

@pytest.fixture
def mock_artifacts(tmp_path):
    import lightgbm as lgb
    
    # Create a dummy model
    X = np.random.rand(100, 10)
    y = np.random.randint(0, 2, 100)
    train_data = lgb.Dataset(X, label=y)
    model = lgb.train({'objective': 'binary', 'verbose': -1}, train_data, 1)
    
    model_path = tmp_path / "model.txt"
    model.save_model(str(model_path))
    
    metadata = {
        "model_version": "1.0.0",
        "features": [
            "ret_1m", "ret_5m", "ret_15m", "volatility_15m", "volatility_60m",
            "sma_ratio_15_60", "rsi_14", "volume_profile_15m", "range_position_60m", "trend_strength_60m"
        ],
        "prediction_horizon_minutes": 15,
        "symbols": ["BTCUSDT"]
    }
    meta_path = tmp_path / "metadata.json"
    with open(meta_path, 'w') as f:
        json.dump(metadata, f)
        
    return str(model_path), str(meta_path)

@pytest.fixture
def sample_ohlcv():
    base_time = datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc)
    data = []
    for i in range(200):
        data.append({
            'symbol': 'BTCUSDT',
            'timestamp': base_time + timedelta(minutes=i),
            'open': 100.0 + i,
            'high': 101.0 + i,
            'low': 99.0 + i,
            'close': 100.5 + i,
            'volume': 1000.0
        })
    return pd.DataFrame(data)

def test_backtester_run(mock_artifacts, sample_ohlcv):
    model_path, meta_path = mock_artifacts
    backtester = Backtester(model_path, meta_path)
    
    report = backtester.run(sample_ohlcv)
    
    assert report.status in ["SUCCESS", "WARNING"]
    assert len(report.equity_curve) > 0
    assert report.model_version == "1.0.0"

def test_analyzer_monte_carlo():
    analyzer = EvaluationAnalyzer(seed=42)
    trades = [
        Trade(symbol="BTC", entry_time=datetime.now(), exit_time=datetime.now(),
              entry_price=100, exit_price=110, quantity=1, entry_notional=100, exit_notional=110,
              entry_fee=0.1, exit_fee=0.1, entry_slippage=0.05, exit_slippage=0.05,
              gross_pnl=10, net_pnl=9.8, pnl_percent=0.098),
        Trade(symbol="BTC", entry_time=datetime.now(), exit_time=datetime.now(),
              entry_price=100, exit_price=90, quantity=1, entry_notional=100, exit_notional=90,
              entry_fee=0.1, exit_fee=0.1, entry_slippage=0.05, exit_slippage=0.05,
              gross_pnl=-10, net_pnl=-10.2, pnl_percent=-0.102)
    ]
    
    results = analyzer.run_monte_carlo(trades, iterations=100)
    assert results['iterations'] == 100
    assert 'probability_of_profit' in results
    assert 'mean_pnl' in results

def test_analyzer_walk_forward(mock_artifacts, sample_ohlcv):
    model_path, meta_path = mock_artifacts
    backtester = Backtester(model_path, meta_path)
    analyzer = EvaluationAnalyzer()
    
    results = analyzer.run_walk_forward(backtester, sample_ohlcv, n_windows=2)
    assert len(results) == 2
    assert results[0]['window'] == 0
    assert results[1]['window'] == 1
