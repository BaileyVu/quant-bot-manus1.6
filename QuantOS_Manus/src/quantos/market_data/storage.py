import os
import pandas as pd
import duckdb
from typing import List
from quantos.market_data.models import Candle
from quantos.core.logger import logger

class MarketDataStorage:
    def __init__(self, base_path: str):
        self.base_path = base_path
        os.makedirs(self.base_path, exist_ok=True)
        
    def _get_file_path(self, symbol: str) -> str:
        return os.path.join(self.base_path, f"{symbol}_1m.parquet")
        
    def save_candles(self, symbol: str, candles: List[Candle]):
        if not candles:
            return
            
        df = pd.DataFrame([c.model_dump() for c in candles])
        # Ensure timestamp is datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        file_path = self._get_file_path(symbol)
        
        if os.path.exists(file_path):
            existing_df = pd.read_parquet(file_path)
            combined_df = pd.concat([existing_df, df])
            # Drop duplicates based on timestamp
            combined_df = combined_df.drop_duplicates(subset=['timestamp'], keep='last')
            combined_df = combined_df.sort_values('timestamp')
        else:
            combined_df = df.sort_values('timestamp')
            
        # Check for missing candles (1 minute interval)
        if len(combined_df) > 1:
            time_diffs = combined_df['timestamp'].diff().dropna()
            expected_diff = pd.Timedelta(minutes=1)
            missing = time_diffs[time_diffs > expected_diff]
            if not missing.empty:
                logger.warning(f"Found {len(missing)} missing candle gaps for {symbol}")
                
        combined_df.to_parquet(file_path, index=False)
        logger.info(f"Saved {len(candles)} new candles for {symbol}. Total: {len(combined_df)}")
        
    def get_duckdb_connection(self) -> duckdb.DuckDBPyConnection:
        conn = duckdb.connect(database=':memory:')
        return conn
        
    def query_data(self, symbol: str, query: str) -> pd.DataFrame:
        file_path = self._get_file_path(symbol)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"No data found for {symbol}")
            
        conn = self.get_duckdb_connection()
        # Register the parquet file as a view
        conn.execute(f"CREATE VIEW market_data AS SELECT * FROM read_parquet('{file_path}')")
        result = conn.execute(query).df()
        return result
