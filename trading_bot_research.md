# Trading Bot Research: Polymarket, Hyperliquid, Binance

## Polymarket API
- **Gamma API**: `https://gamma-api.polymarket.com` (Public: Markets, events, search)
- **Data API**: `https://data-api.polymarket.com` (Public: Positions, trades, activity)
- **CLOB API**: `https://clob.polymarket.com` (Trading: Orderbook, order management)
- **Authentication**: Required for trading. Uses API keys and potentially L2 signatures (to be confirmed).
- **Rate Limits (CLOB)**:
  - General: 9,000 req / 10s
  - POST /order: 3,500 req / 10s (Burst), 36,000 req / 10 min (Sustained)
  - DELETE /cancel-market-orders: 1,000 req / 10s, 1,500 req / 10 min (Sustained)
- **SDKs**: Official TypeScript, Python, and Rust libraries available.

## Hyperliquid API
- **Base Info**: High-performance decentralized perpetual exchange.
- **REST Rate Limits**: Aggregated weight limit of 1,200 per minute per IP.
- **WebSocket Limits**: 1,000 subscriptions per IP.
- **Python SDK**: `https://github.com/hyperliquid-dex/hyperliquid-python-sdk` (Sync and Async support).
- **Market Making**: Actively encouraged; provides `info` endpoints like `userRateLimit` to monitor usage.
- **Authentication**: API keys (L1) or signing with private keys (L2).

## Binance API
- **General**: Most mature and liquid exchange API.
- **Endpoints**: `https://api.binance.com` (Spot), `https://fapi.binance.com` (Futures).
- **Rate Limits**: Default IP limit is 2,400 per minute. Order limits are tracked separately (e.g., 50 per 10s, 160,000 per 24h).
- **VIP Program**: VIP 1-9 tiers unlock higher limits and lower fees (Maker rebates).
- **Market Maker Program**: Specific programs for Spot and Futures with fee rebates and higher API limits by request.
- **Security**: Supports API Key/Secret and Ed25519/RSA key pairs for signing.

## Key Strategy Considerations
- **Market Making**: Requires low latency, spread management, and inventory risk control.
- **Quant Trading**: Needs robust backtesting, data ingestion, and execution logic.
- **Automation**: Requires high availability (cloud deployment), error handling, and monitoring.

## Strategy and Risk Management
- **Market Making Models**:
  - **Avellaneda-Stoikov**: Standard model for optimal bid-ask spreads based on inventory risk and price volatility.
  - **Inventory Management**: Skewing quotes to attract trades that reduce position imbalance.
  - **Hedging**: Using one platform (e.g., Binance Futures) to hedge inventory risk from another (e.g., Polymarket or Hyperliquid).
- **Market Microstructure**: Analyzing order book depth, tick size, and trade flow to predict short-term price movements.

## Infrastructure and Tech Stack
- **Language Choice**:
  - **MVP (Python)**: High flexibility, fast iteration, extensive libraries (ccxt, pandas, numpy). Latency ~10-50ms.
  - **Production (Rust)**: Low latency, memory safety, high concurrency. Latency <1ms (internal).
- **Deployment**:
  - **Cloud**: AWS (us-east-1 often for low latency to exchanges), GCP, or dedicated trading VPS.
  - **Static IP**: Required for API key whitelisting on most exchanges.
- **Architecture**:
  - **Event-Driven**: WebSocket listeners for real-time market data, async task queues for order execution.
  - **Database**: Time-series database (InfluxDB, TimescaleDB) for trade history and performance tracking.
  - **Monitoring**: Prometheus + Grafana for real-time metrics (latency, PnL, order success rate).
