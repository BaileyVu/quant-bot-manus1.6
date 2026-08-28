import pytest
from datetime import datetime, timezone, timedelta
from quantos.evaluation_engine.simulator import PortfolioSimulator

def test_simulator_basic_trade():
    sim = PortfolioSimulator(initial_capital=10000.0, fee_rate=0.001, slippage_rate=0.0005)
    base_time = datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc)
    
    # 1. Open position
    sim.open_position("BTCUSDT", base_time, 100.0, 5000.0)
    
    assert "BTCUSDT" in sim.positions
    assert sim.cash == 10000.0 - 5000.0 - 5.0
    
    # 2. Update equity
    sim.update_equity(base_time + timedelta(minutes=1), {"BTCUSDT": 110.0})
    assert sim.equity_curve[-1]['equity'] > 10000.0
    
    # 3. Close position
    sim.close_position("BTCUSDT", base_time + timedelta(minutes=15), 110.0)
    
    assert len(sim.positions) == 0
    assert len(sim.trades) == 1
    assert sim.trades[0].net_pnl > 0
    
def test_simulator_metrics():
    sim = PortfolioSimulator(initial_capital=10000.0)
    base_time = datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc)
    
    # Win trade
    sim.open_position("BTCUSDT", base_time, 100.0, 1000.0)
    sim.close_position("BTCUSDT", base_time + timedelta(minutes=15), 110.0)
    
    # Loss trade
    sim.open_position("BTCUSDT", base_time + timedelta(hours=1), 100.0, 1000.0)
    sim.close_position("BTCUSDT", base_time + timedelta(hours=1, minutes=15), 90.0)
    
    metrics = sim.get_metrics()
    assert metrics['trade_count'] == 2
    assert metrics['win_rate'] == 0.5
    assert metrics['total_fees'] > 0
    assert metrics['total_slippage'] > 0
