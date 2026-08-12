# Venue Market Maker

> **Status:** This repository is a production-oriented *execution service*, not evidence that any strategy will be profitable. It defaults to simulation and provides Binance Spot Testnet and Hyperliquid Testnet profiles. It contains no credentials and cannot submit live orders unless an operator deliberately enables the live-mode gate.

## What the Service Does

The service runs one passive, two-sided quoting strategy on one configured market at a time. It ingests a best bid and offer, derives inventory-skewed quotes, cancels quotes that no longer meet the pricing rules, and submits only venue-enforced post-only limit orders. Binance orders use `LIMIT_MAKER`; Hyperliquid orders use `Alo`, which cancels an order that would immediately match. Hyperliquid also receives a rolling venue-side `scheduleCancel` deadline, so a process failure is designed to lead to order cancellation rather than unmanaged resting liquidity.[1] [2]

| Included control | Implementation |
|---|---|
| Execution environments | `simulation`, Binance Spot `testnet`, Hyperliquid `testnet`, plus intentionally gated `live` mode |
| Passive-order enforcement | Local non-crossing quote checks plus Binance `LIMIT_MAKER` and Hyperliquid `Alo` order types |
| Exposure protection | Maximum single-order, projected net, projected gross, order-count, and quote-balance limits |
| Data-quality protection | Stops quoting when the best bid/offer is stale or invalid |
| Operational safety | External kill-switch file, error circuit breaker, persisted risk halt, audit JSONL log, signal-aware shutdown |
| Hyperliquid failure containment | Rolling 30-second exchange-native cancel-all deadline |
| Credential handling | Credentials are read only from process environment variables; configuration files containing credentials are rejected |

## Scope and Non-Goals

This is a **single-venue, single-instrument passive market-maker**. It does not transfer funds, change leverage, open market orders, execute arbitrage between venues, or provide a profitability forecast. It does not turn a low-latency market-making operation into a high-frequency trading system; Python and public internet connectivity are not suitable for competing with colocated specialists. The correct use is conservative strategy validation and low-frequency liquidity provision following venue-specific compliance review.

## Setup

Create an isolated Python 3.11 environment, install the package with development dependencies, and use the simulation profile first. The commands below are intended for a machine you control; do not put secrets in the repository.

```bash
cd venue-market-maker
python3.11 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -e '.[dev]'
pytest -q
market-maker --config config/simulation.json --once
```

A successful simulation run should create two non-crossing resting orders in `runtime/simulation-audit.jsonl` and then cancel them because `--once` terminates the managed cycle.

## Testnet Validation

| Venue | Profile | Credential requirements | External behavior |
|---|---|---|---|
| Binance Spot | `config/binance-testnet.json` | `BINANCE_API_KEY`, `BINANCE_API_SECRET` from the Spot Test Network | Gets symbol filters and book updates, then submits/cancels small `LIMIT_MAKER` test orders. |
| Hyperliquid Perpetuals | `config/hyperliquid-testnet.json` | `HYPERLIQUID_ACCOUNT_ADDRESS`, `HYPERLIQUID_API_WALLET_PRIVATE_KEY` | Gets L2 data, then submits/cancels small `Alo` orders and refreshes the venue dead-man switch. |

Binance documents a dedicated API-only Spot Test Network and testnet endpoints, while Hyperliquid's maintained Python SDK exposes its `TESTNET_API_URL` and recommends a separate API-wallet private key with the funded account's main address retained as `account_address`.[1] [3]

After creating an API key or API-wallet key with the **minimum required permissions**, export only testnet credentials into the process environment.

```bash
cp .env.example .env
# Edit .env locally. Do not commit it.
set -a && . ./.env && set +a
market-maker --config config/binance-testnet.json --once
# or
market-maker --config config/hyperliquid-testnet.json --once
```

Before adding credentials, verify the public feed with the credential-free health check. The command opens the market-data connection only; it does not call account or trading endpoints.

```bash
market-maker --config config/binance-testnet.json --check-market-data
market-maker --config config/hyperliquid-testnet.json --check-market-data
```

The first authenticated run should be an operator-observed `--once` cycle. Inspect the venue order history, audit log, and cancellation result. Run a multi-hour testnet soak test before changing an environment from `testnet` to `live`.

## Live Mode: Deliberate Two-Key Gate

Live mode is intentionally absent from the supplied profiles. To create a live profile, an operator must set `environment` to `live`, provide live credentials **outside the repository**, and set the exact acknowledgement below. Missing either validation fails before any order-routing object is built.

```bash
export OPERATOR_LIVE_ACKNOWLEDGEMENT=I_UNDERSTAND_LIVE_TRADING_RISK
```

Before live operation, restrict the Binance key to Spot trading and read-only account access, disable withdrawal permission, and allowlist the deployment server's egress IP. For Hyperliquid, use an API-wallet key rather than the primary wallet private key. Keep the `max_order_notional_usd`, `max_net_notional_usd`, and `max_drawdown_usd` values materially lower than the total capital available during initial rollout.

> Live enablement is an operational decision with real financial consequences. This code can enforce stated limits, but no software eliminates exchange failures, asset volatility, adverse selection, network partitions, liquidation, or configuration error.

## Emergency Procedures

The service is fail-closed. Creating the configured kill-switch file causes the next cycle to halt and cancel its known market orders.

```bash
mkdir -p runtime
touch runtime/KILL_SWITCH
```

A risk halt is persisted to the configured `state_path`. The service will refuse to restart while that file contains a halt reason. Review the audit log and venue order state first; only then remove the precise configured state file to acknowledge the incident.

```bash
rm runtime/binance-testnet-state.json
```

When a Hyperliquid process becomes unavailable, its rolling `scheduleCancel` deadline is intended to cancel open orders. It should be treated as defense in depth—not a substitute for independent monitoring or checking actual exchange order state.[2]

## Deployment Options

| Approach | Trade-offs | Cost | Setup complexity |
|---|---|---:|---|
| A dedicated Linux VM with Docker or `systemd` | Supports a fixed egress IP, long-lived WebSockets, host-level firewall rules, and separate non-root credentials; requires operational ownership. | Hosting-provider dependent. | Higher; recommended for a persistent live service. |
| A continuously running managed service | Less server administration and easy deployment; may not provide a fixed egress IP or the network controls needed for restrictive API key allowlists. | Usage-based. | Lower; suitable for simulation and testnet only unless its networking/security controls meet the venue requirements. |

The supplied `Dockerfile`, `compose.yaml`, and `deploy/market-maker.service` support the first option. Do not deploy more than one instance with the same credentials and instrument unless an external leader-election or order-ownership system is added; two active instances can quote against one another or fight over order state.

## Observability and Operations

Audit records use JSON Lines so they can be sent to a centralized log system. Alert on `risk_halt`, `cancel_all_failure`, three consecutive errors, stale market-data conditions, and any discrepancy between the venue's open orders and the service's audit trail. Retain raw audit records and exchange trade/order reports for operational reconciliation.

The initial risk baseline is the equity observed when the process starts. If you deposit or withdraw funds while it runs, restart only after closing/canceling the bot's orders and reviewing the logs; otherwise the drawdown circuit breaker may no longer represent the intended baseline.

## References

[1] [Binance Spot API documentation and Testnet](https://github.com/binance/binance-spot-api-docs)

[2] [Hyperliquid Exchange endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint)

[3] [Hyperliquid Python SDK](https://github.com/hyperliquid-dex/hyperliquid-python-sdk)

[4] [Hyperliquid WebSocket subscriptions](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions)
