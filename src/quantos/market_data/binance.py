import requests
from datetime import datetime, timezone
from typing import List, Optional
from quantos.core.logger import logger
from quantos.market_data.models import Candle

class BinanceClient:
    def __init__(self, base_url: str = "https://api.binance.com"):
        self.base_url = base_url
        
    def fetch_klines(
        self, 
        symbol: str, 
        interval: str = "1m", 
        start_time: Optional[int] = None, 
        end_time: Optional[int] = None,
        limit: int = 1000
    ) -> List[Candle]:
        endpoint = f"{self.base_url}/api/v3/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
            
        logger.info(f"Fetching {interval} klines for {symbol}")
        response = requests.get(endpoint, params=params)
        response.raise_for_status()
        
        data = response.json()
        candles = []
        
        for row in data:
            # Binance format:
            # [Open time, Open, High, Low, Close, Volume, Close time, ...]
            timestamp = datetime.fromtimestamp(row[0] / 1000.0, tz=timezone.utc)
            # Only consider completed candles. For historical data, we assume they are completed
            # unless the close time is in the future.
            close_time = datetime.fromtimestamp(row[6] / 1000.0, tz=timezone.utc)
            is_completed = close_time < datetime.now(timezone.utc)
            
            if not is_completed:
                logger.debug(f"Skipping incomplete candle at {timestamp}")
                continue
                
            try:
                candle = Candle(
                    symbol=symbol,
                    timestamp=timestamp,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                    is_completed=True
                )
                candles.append(candle)
            except ValueError as e:
                logger.warning(f"Invalid candle data at {timestamp}: {e}")
                
        return candles
