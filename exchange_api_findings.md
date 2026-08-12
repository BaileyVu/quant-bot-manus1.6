# Exchange Integration Findings

## Binance Spot

Binance's official API repository documents supported REST, WebSocket, FIX, and market-data streams, including a dedicated Spot Testnet. The testnet accepts API-driven Spot trading and uses `https://testnet.binance.vision/api` for REST, `wss://ws-api.testnet.binance.vision/ws-api/v3` for the WebSocket API, and `wss://stream.testnet.binance.vision` for market-data streams. Live endpoint calls must remain disabled until the user creates appropriately scoped API credentials and completes authenticated testnet validation.

## Hyperliquid

Hyperliquid's official Exchange endpoint exposes authenticated order placement, cancellation, cancel-by-client-ID, and scheduled cancel-all functions. Limit orders can use `Alo` time-in-force to ensure post-only behavior, meaning an order that would immediately match is canceled. Its `scheduleCancel` action is a venue-level dead-man switch: when the deadline fires, all open orders are cancelled. The official Python SDK supports a testnet base URL and recommends an API-wallet private key for programmatic access, while retaining the main wallet address as the account address.

## Design Implication

The implementation will use authenticated order routing only through individual exchange adapters, enforce passive-only order types, and use a local emergency kill switch. For Hyperliquid, it will also maintain a rolling exchange-native cancel-all deadline. The default runtime target is simulated execution; the only environment configurations included for external calls are Binance Spot Testnet and Hyperliquid Testnet.

## Sources

1. Binance official documentation repository: https://github.com/binance/binance-spot-api-docs
2. Binance Spot Test Network: https://testnet.binance.vision/
3. Hyperliquid Exchange endpoint: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint
4. Hyperliquid Python SDK: https://github.com/hyperliquid-dex/hyperliquid-python-sdk
