# QuantOS: V1 Quantitative Trading System MVP

## Overview

**QuantOS** is a deterministic, event-driven quantitative trading system designed as a high-integrity Minimum Viable Product (MVP). The project focuses on bridging the gap between historical backtesting and real-time paper trading through a strictly modular architecture that enforces symbol isolation, capital constraints, and honest execution accounting.

The primary objective of this project is to provide a working, runnable foundation that can process Binance market data, generate deterministic signals using machine learning, and simulate portfolio management with realistic transaction costs.

---

## 📖 Specifications & Documentation

Before interacting with the code, all users are **strongly encouraged** to review the frozen specifications located in the `docs/` directory. These documents define the system's logic, constraints, and mathematical invariants.

| Document | Purpose |
| :--- | :--- |
| [001 Product Requirements](docs/001_PRODUCT_REQUIREMENTS.md) | High-level goals and functional scope. |
| [002 System Architecture](docs/002_SYSTEM_ARCHITECTURE.md) | Module boundaries and event-driven design. |
| [003 Data Architecture](docs/003_DATA_ARCHITECTURE.md) | Canonical candle schemas and storage patterns. |
| [004 Feature Engine](docs/004_FEATURE_ENGINE_SPECIFICATION.md) | Deterministic feature calculation and vector contracts. |
| [005 Alpha Engine](docs/005_ALPHA_ENGINE.md) | Model training, inference, and leakage prevention. |
| [006 Risk & Execution](docs/006_RISK_EXECUTION_SPECIFICATION.md) | Safety boundaries and order construction. |
| [007 Backtesting](docs/007_VALIDATION_BACKTESTING.md) | Evaluation metrics and walk-forward validation. |
| [008 Implementation Guide](docs/008_IMPLEMENTATION_GUIDE.md) | Step-by-step milestone definitions. |

---

## 🚀 Getting Started

### 1. Fork and Clone
To contribute or customize the system, begin by forking the repository to your own GitHub account and cloning it locally:

```bash
git clone https://github.com/BaileyVu/quant-bot-manus1.6.git
cd quant-bot-manus1.6
```

### 2. Installation
QuantOS requires Python 3.10+ and uses `pydantic`, `pandas`, `duckdb`, and `lightgbm`. Install the project in editable mode with development dependencies:

```bash
pip install -e .[dev]
```

### 3. Data Initialization
Fetch initial historical data from Binance to populate the local storage:

```bash
quantos fetch-data
quantos verify-data
```

---

## 🛠️ Running the Project

QuantOS provides a unified CLI to manage the entire quantitative lifecycle.

### Backtesting (Historical Evaluation)
Execute an event-driven backtest using the saved model artifacts. This mode applies realistic fees and slippage to ensure honest performance reporting.

```bash
quantos evaluate-model
```

### Paper Trading (Live Observation)
Start the local paper-trading runtime to process live Binance market data in real-time. This mode is strictly isolated from real order submission for safety.

```bash
quantos paper-trade
```

### Model Training
Re-run the training pipeline to generate new model artifacts based on the current local dataset.

```bash
quantos train-model
```

---

## 🛡️ Safety & Integrity

QuantOS is built with a **Defense-in-Depth** safety philosophy:
*   **Hard Live-Order Block**: The execution layer physically prevents real exchange calls during Milestone 5.
*   **Symbol Isolation**: BTC and ETH positions are tracked in independent, keyed structures to prevent cross-contamination.
*   **Equity Invariants**: The system verifies that `equity = cash + market_value` at every step, failing hard on any accounting discrepancy.

---

## 🧪 Testing
The system includes a comprehensive suite of unit and integration tests. It is recommended to run these after any modification:

```bash
pytest tests/
```

---

## License
This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.
