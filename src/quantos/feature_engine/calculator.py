import pandas as pd
import numpy as np
from typing import List, Optional
from quantos.core.logger import logger
from quantos.feature_engine.models import FeatureVector

class FeatureCalculator:
    """
    Calculates the 10-15 approved production features from canonical market data.
    Ensures deterministic output without look-ahead bias.
    """
    
    def __init__(self, version: str = "1.0"):
        self.version = version
        # Define the exact features we expect to produce
        self.expected_features = [
            "ret_1m", "ret_5m", "ret_15m",          # Short/medium term returns
            "volatility_15m", "volatility_60m",     # Volatility
            "sma_ratio_15_60",                      # Moving average relationship
            "rsi_14",                               # Momentum
            "volume_profile_15m",                   # Volume behavior
            "range_position_60m",                   # Relative position within recent range
            "trend_strength_60m"                    # Trend strength
        ]
        
    def calculate_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate all features on a dataframe of candles.
        Input df must be sorted by timestamp and contain standard OHLCV columns.
        """
        if df.empty:
            return df
            
        df = df.copy()
        df = df.sort_values('timestamp')
        
        # 1-3. Returns
        df['ret_1m'] = df['close'].pct_change(1)
        df['ret_5m'] = df['close'].pct_change(5)
        df['ret_15m'] = df['close'].pct_change(15)
        
        # 4-5. Volatility (Standard deviation of 1m returns)
        df['volatility_15m'] = df['ret_1m'].rolling(window=15).std()
        df['volatility_60m'] = df['ret_1m'].rolling(window=60).std()
        
        # 6. Moving average relationship
        sma_15 = df['close'].rolling(window=15).mean()
        sma_60 = df['close'].rolling(window=60).mean()
        df['sma_ratio_15_60'] = sma_15 / sma_60 - 1.0
        
        # 7. RSI (14 periods)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi_14'] = 100 - (100 / (1 + rs))
        
        # 8. Volume profile (ratio of current volume to 15m average)
        vol_sma_15 = df['volume'].rolling(window=15).mean()
        df['volume_profile_15m'] = df['volume'] / vol_sma_15
        
        # 9. Range position (0 to 1, where current close is within 60m high/low range)
        high_60 = df['high'].rolling(window=60).max()
        low_60 = df['low'].rolling(window=60).min()
        range_60 = high_60 - low_60
        # Avoid division by zero
        range_60 = range_60.replace(0, np.nan)
        df['range_position_60m'] = (df['close'] - low_60) / range_60
        
        # 10. Trend strength (ADX approximation or simple directional movement)
        # We'll use a simple linear regression slope approximation over 60m normalized by price
        # For simplicity and determinism in pandas without statsmodels:
        # (Close - Close 60m ago) / (60 * Volatility)
        df['trend_strength_60m'] = (df['close'] - df['close'].shift(60)) / (df['close'] * df['volatility_60m'] * 60)
        
        return df
        
    def extract_latest_vector(self, df: pd.DataFrame, symbol: str) -> Optional[FeatureVector]:
        """
        Extract the most recent feature vector from a calculated dataframe.
        """
        if df.empty:
            return None
            
        latest = df.iloc[-1]
        
        features = {}
        for feat in self.expected_features:
            if feat in latest:
                val = float(latest[feat])
                features[feat] = val if not pd.isna(val) else np.nan
                
        return FeatureVector(
            symbol=symbol,
            timestamp=latest['timestamp'].to_pydatetime(),
            version=self.version,
            features=features
        )
