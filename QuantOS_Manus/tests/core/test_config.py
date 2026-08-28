from quantos.core.config import AppConfig

def test_config_load_defaults():
    config = AppConfig.load()
    assert config.environment == "local"
    assert "BTCUSDT" in config.market_data.symbols
    assert "ETHUSDT" in config.market_data.symbols
    assert config.market_data.storage_path == "data/market_data"
