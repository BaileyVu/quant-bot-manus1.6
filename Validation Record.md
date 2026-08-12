# Validation Record

**Validation date:** 12 August 2026.  
**Repository:** `venue-market-maker`.

## Completed Checks

| Check | Result | Evidence |
|---|---:|---|
| Static analysis | Passed | `ruff format .` and `ruff check .` completed with no findings. |
| Automated test suite | Passed | `pytest -q` completed with **6 passed** tests. |
| Simulation quote cycle | Passed | A managed one-cycle simulation created two non-crossing passive quotes and then cancelled them on exit. |
| Binance Spot Testnet public feed | Passed | The adapter established the official Testnet public book-ticker connection and retrieved `BTCUSDT` bid/ask data without credentials. |
| Hyperliquid Testnet public L2 feed | Passed | The adapter established the official Testnet `l2Book` subscription and retrieved `BTC` bid/ask data without credentials. |
| Live-mode gate | Passed by unit test | The configuration model rejects `live` mode without the precise acknowledgement and required venue credentials. |

## Deliberately Not Performed

No account information was queried, no credentials were supplied, no signed exchange request was made, and no testnet or live order was submitted during this validation. Those steps must be completed by the operator using separately created, least-privilege credentials during an observed testnet run.

> The successful public-feed checks demonstrate network and message-schema compatibility only. They do not validate account permissions, balances, order acceptance, fill handling, or financial performance.

## Required Operator Acceptance Tests

| Stage | Required evidence before moving forward |
|---|---|
| Testnet credentials | API/API-wallet key is scoped to trading only; no withdrawals; IP allowlist is enabled where supported. |
| One-cycle authenticated test | Visible post-only order acknowledgement, open-order query, cancellation acknowledgement, and matching JSONL audit records. |
| Soak test | Multiple hours of stable reconnects, no unexplained audit discrepancies, no stale-book halts, and no unhandled error circuit breaks. |
| Live rollout | Explicit live acknowledgement, independently reviewed risk values, funded-capital limit well below account equity, and an active monitoring/incident process. |
