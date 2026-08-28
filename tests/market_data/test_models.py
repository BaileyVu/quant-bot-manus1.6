import pytest
from datetime import datetime, timezone
from quantos.market_data.models import Candle

def test_candle_valid():
    candle = Candle(
        symbol="BTCUSDT",
        timestamp=datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc),
        open=100.0,
        high=110.0,
        low=90.0,
        close=105.0,
        volume=1000.0
    )
    assert candle.symbol == "BTCUSDT"
    
def test_candle_invalid_timestamp():
    with pytest.raises(ValueError, match="Timestamp must be UTC"):
        Candle(
            symbol="BTCUSDT",
            timestamp=datetime(2023, 1, 1, 12, 0), # No tzinfo
            open=100.0,
            high=110.0,
            low=90.0,
            close=105.0,
            volume=1000.0
        )

def test_candle_invalid_high():
    with pytest.raises(ValueError, match="High must be >= open, close, and low"):
        Candle(
            symbol="BTCUSDT",
            timestamp=datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc),
            open=100.0,
            high=95.0, # High is lower than open
            low=90.0,
            close=105.0,
            volume=1000.0
        )
        
def test_candle_invalid_low():
    with pytest.raises(ValueError, match="Low must be <= open, close, and high"):
        Candle(
            symbol="BTCUSDT",
            timestamp=datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc),
            open=100.0,
            high=110.0,
            low=105.0, # Low is higher than open
            close=95.0,
            volume=1000.0
        )

def test_candle_invalid_volume():
    with pytest.raises(ValueError, match="Volume must be non-negative"):
        Candle(
            symbol="BTCUSDT",
            timestamp=datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc),
            open=100.0,
            high=110.0,
            low=90.0,
            close=105.0,
            volume=-10.0
        )
