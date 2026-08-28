import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from quantos.feature_engine.calculator import FeatureCalculator
from quantos.feature_engine.models import FeatureVector

@pytest.fixture
def sample_data():
    base_time = datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc)
    
    # Create 100 candles of dummy data
    data = []
    price = 100.0
    for i in range(100):
        data.append({
            'symbol': 'BTCUSDT',
            'timestamp': base_time + timedelta(minutes=i),
            'open': price,
            'high': price + 1.0,
            'low': price - 1.0,
            'close': price + (0.1 * (i % 5 - 2)), # Slight oscillation
            'volume': 1000.0 + (10 * i)
        })
        price = data[-1]['close']
        
    return pd.DataFrame(data)

def test_feature_calculator_determinism(sample_data):
    calc = FeatureCalculator()
    
    # Calculate twice on same data
    result1 = calc.calculate_features(sample_data.copy())
    result2 = calc.calculate_features(sample_data.copy())
    
    # Results should be identical
    pd.testing.assert_frame_equal(result1, result2)
    
def test_feature_calculator_missing_data(sample_data):
    calc = FeatureCalculator()
    
    # Calculate on insufficient data (e.g., 10 rows when we need 60 for some features)
    short_data = sample_data.iloc[:10].copy()
    result = calc.calculate_features(short_data)
    
    # Extract latest
    vector = calc.extract_latest_vector(result, 'BTCUSDT')
    
    # Should have missing values because window=60 needs 60 rows
    assert vector.has_missing_values() is True
    assert np.isnan(vector.features['volatility_60m'])
    
def test_feature_calculator_sufficient_data(sample_data):
    calc = FeatureCalculator()
    
    # Calculate on sufficient data (100 rows > 60)
    result = calc.calculate_features(sample_data)
    
    # Extract latest
    vector = calc.extract_latest_vector(result, 'BTCUSDT')
    
    # Should not have missing values
    assert vector.has_missing_values() is False
    assert not np.isnan(vector.features['volatility_60m'])
    
def test_feature_vector_model():
    vector = FeatureVector(
        symbol="BTCUSDT",
        timestamp=datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc),
        features={"ret_1m": 0.01, "volatility_15m": 0.005}
    )
    assert vector.has_missing_values() is False
    
    vector_with_nan = FeatureVector(
        symbol="BTCUSDT",
        timestamp=datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc),
        features={"ret_1m": 0.01, "volatility_15m": np.nan}
    )
    assert vector_with_nan.has_missing_values() is True
