import numpy as np
import pandas as pd
from typing import List, Dict, Any
from quantos.evaluation_engine.models import Trade, BacktestReport

class EvaluationAnalyzer:
    """
    Performs Walk-Forward validation and Monte Carlo robustness checks for QuantOS V1.
    """
    
    def __init__(self, seed: int = 42):
        self.seed = seed
        np.random.seed(seed)
        
    def run_monte_carlo(self, trades: List[Trade], iterations: int = 1000) -> Dict[str, Any]:
        """
        Focused Monte Carlo analysis of trade results.
        Tests robustness via trade sequence randomization.
        """
        if not trades:
            return {"status": "INSUFFICIENT_DATA"}
            
        pnls = [t.net_pnl for t in trades]
        n_trades = len(pnls)
        
        simulated_final_pnls = []
        simulated_max_drawdowns = []
        
        for _ in range(iterations):
            # Shuffle trade sequence
            shuffled_pnls = np.random.choice(pnls, size=n_trades, replace=True)
            
            # Calculate equity curve
            equity = 10000.0 + np.cumsum(shuffled_pnls)
            simulated_final_pnls.append(equity[-1] - 10000.0)
            
            # Max Drawdown
            peak = np.maximum.accumulate(equity)
            drawdown = (peak - equity) / peak
            simulated_max_drawdowns.append(np.max(drawdown))
            
        return {
            "iterations": iterations,
            "mean_pnl": float(np.mean(simulated_final_pnls)),
            "pnl_std": float(np.std(simulated_final_pnls)),
            "p5_pnl": float(np.percentile(simulated_final_pnls, 5)),
            "p95_pnl": float(np.percentile(simulated_final_pnls, 95)),
            "mean_max_drawdown": float(np.mean(simulated_max_drawdowns)),
            "p95_max_drawdown": float(np.percentile(simulated_max_drawdowns, 95)),
            "probability_of_profit": float(len([p for p in simulated_final_pnls if p > 0]) / iterations)
        }
        
    def run_walk_forward(self, backtester, df: pd.DataFrame, n_windows: int = 3) -> List[Dict[str, Any]]:
        """
        Minimal walk-forward evaluation framework.
        Splits data into N sequential windows and runs backtests.
        """
        if df.empty or len(df) < 100:
            return [{"window": 0, "status": "INSUFFICIENT_DATA"}]
            
        df = df.sort_values('timestamp').reset_index(drop=True)
        window_size = len(df) // n_windows
        
        results = []
        for i in range(n_windows):
            start_idx = i * window_size
            end_idx = (i + 1) * window_size if i < n_windows - 1 else len(df)
            
            window_df = df.iloc[start_idx:end_idx].copy()
            
            try:
                report = backtester.run(window_df)
                results.append({
                    "window": i,
                    "start": window_df['timestamp'].min().isoformat(),
                    "end": window_df['timestamp'].max().isoformat(),
                    "net_profit": report.metrics.net_profit,
                    "trade_count": report.metrics.trade_count,
                    "win_rate": report.metrics.win_rate
                })
            except Exception as e:
                results.append({
                    "window": i,
                    "status": "ERROR",
                    "error": str(e)
                })
                
        return results
