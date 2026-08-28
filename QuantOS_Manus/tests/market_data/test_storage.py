import pytest
import os
import tempfile
from datetime import datetime, timezone, timedelta
from quantos.market_data.models import Candle
from quantos.market_data.storage import MarketDataStorage

@pytest.fixture
def temp_storage():
    with tempfile.TemporaryDirectory() as temp_dir:
        yield MarketDataStorage(temp_dir)

def test_storage_save_and_query(temp_storage):
    base_time = datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc)
    candles = [
        Candle(
            symbol="BTCUSDT",
            timestamp=base_time,
            open=100.0, high=110.0, low=90.0, close=105.0, volume=1000.0
        ),
        Candle(
            symbol="BTCUSDT",
            timestamp=base_time + timedelta(minutes=1),
            open=105.0, high=115.0, low=95.0, close=110.0, volume=1200.0
        )
    ]
    
    temp_storage.save_candles("BTCUSDT", candles)
    
    result = temp_storage.query_data("BTCUSDT", "SELECT COUNT(*) as count FROM market_data")
    assert result.iloc[0]['count'] == 2

def test_storage_duplicate_detection(temp_storage):
    base_time = datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc)
    candle1 = Candle(
        symbol="BTCUSDT",
        timestamp=base_time,
        open=100.0, high=110.0, low=90.0, close=105.0, volume=1000.0
    )
    
    # Save same candle twice
    temp_storage.save_candles("BTCUSDT", [candle1])
    temp_storage.save_candles("BTCUSDT", [candle1])
    
    result = temp_storage.query_data("BTCUSDT", "SELECT COUNT(*) as count FROM market_data")
    # Should only have 1 row due to duplicate detection
    assert result.iloc[0]['count'] == 1
