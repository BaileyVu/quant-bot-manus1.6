import time
from datetime import datetime, timezone
from quantos.market_data.binance import BinanceClient
from quantos.core.logger import logger

def verify_binance_readonly():
    """
    Test 22: READ-ONLY BINANCE TEST
    Connects to market data and verifies valid updates without trading permissions.
    """
    logger.info("Starting READ-ONLY Binance connectivity test...")
    client = BinanceClient()
    symbols = ["BTCUSDT", "ETHUSDT"]
    
    success = True
    for symbol in symbols:
        try:
            logger.info(f"Testing connectivity for {symbol}...")
            candles = client.fetch_klines(symbol, limit=5)
            
            if not candles:
                logger.error(f"FAIL: No candles received for {symbol}")
                success = False
                continue
                
            latest = candles[-1]
            logger.info(f"SUCCESS: Received candle for {symbol}")
            logger.info(f"  Timestamp: {latest.timestamp}")
            logger.info(f"  Close: {latest.close}")
            
            # Basic validation
            if latest.timestamp > datetime.now(timezone.utc):
                logger.error(f"FAIL: Future timestamp received for {symbol}")
                success = False
            
            if latest.close <= 0:
                logger.error(f"FAIL: Invalid price received for {symbol}")
                success = False
                
        except Exception as e:
            logger.error(f"FAIL: Connection error for {symbol}: {e}")
            success = False
            
    if success:
        logger.info("OVERALL STATUS: PASS (Read-only connectivity verified)")
    else:
        logger.info("OVERALL STATUS: FAIL (Connectivity issues detected)")
    return success

if __name__ == "__main__":
    verify_binance_readonly()
