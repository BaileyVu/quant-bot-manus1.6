# QuantOS V1 - Milestone 3 Implementation Report

## 1. Repository State Found at Start
- **Foundation and Market Data**: Completed in Milestone 1.
- **Feature Engine**: Completed in Milestone 2.
- **Data Available**: Historical 1-minute OHLCV data for BTCUSDT and ETHUSDT, with calculated features.
- **Frozen Specifications**: Unmodified.

## 2. Model Selected
**LightGBM** was selected as the baseline model.
*Why:* It is explicitly designated as the preferred candidate in `005_ALPHA_ENGINE.md`. It is fast on commodity hardware, handles tabular market features efficiently, supports deterministic training (via seed), and is sufficiently explainable. We used a minimal, conservative configuration (max_depth=4, num_leaves=15, learning_rate=0.05) without any hyperparameter search.

## 3. Target Definition
**Target:** Forward 15-minute return binary classification.
- **What is predicted:** Whether the return from the *next* candle's open to the close 15 minutes later is strictly greater than 0.1% (0.001).
- **Horizon:** 15 minutes.
- **Alignment:** The target is strictly calculated using `shift(-15)` and `shift(-1)`. This ensures that the feature vector at time $t$ predicts the movement from $t+1$ to $t+15$, accurately simulating the delay in entering a trade after a signal is generated.

## 4. Files Created
- `src/quantos/alpha_engine/__init__.py`: Package marker.
- `src/quantos/alpha_engine/models.py`: Defines the `AlphaDecision` and `ModelArtifactMetadata` schemas.
- `src/quantos/alpha_engine/trainer.py`: Implements `ModelTrainer` (target generation, chronological splitting, matrix preparation without leakage, LightGBM training, and artifact saving).
- `tests/alpha_engine/test_trainer.py`: Tests for target generation, chronological splitting, leakage prevention, and artifact saving/loading.

## 5. Files Modified
- `src/quantos/core/cli.py`: Added the `train-model` command to execute the pipeline end-to-end.

## 6. Dataset Split
Data was split **strictly chronologically** (70% train, 30% validation).
A gap equal to the prediction horizon (15 minutes) was enforced between the end of the training set and the start of the validation set to prevent horizon leakage.
- **Training Rows:** 256
- **Validation Rows:** 95

## 7. Feature Count
**Features used:** 10
The model uses the exact 10 features produced by Milestone 2:
`['ret_1m', 'ret_5m', 'ret_15m', 'volatility_15m', 'volatility_60m', 'sma_ratio_15_60', 'rsi_14', 'volume_profile_15m', 'range_position_60m', 'trend_strength_60m']`

## 8. Training Results
- **Log Loss:** 0.6063
- **ROC AUC:** 0.9360

## 9. Validation Results
- **Log Loss:** 0.9452
- **ROC AUC:** 0.3568

## 10. Leakage Checks
- **Data Leakage:** The `prepare_matrices` function explicitly strips `['timestamp', 'symbol', 'target', 'target_return', 'future_close', 'next_open']` from the feature matrix. This is verified by `test_prepare_matrices_no_leakage`.
- **Temporal Leakage:** `test_split_chronological` verifies that the maximum timestamp in the training set is strictly less than the minimum timestamp in the validation set, and that the gap respects the prediction horizon.

## 11. Overfitting Assessment
There is a **large divergence** between training ROC AUC (0.93) and validation ROC AUC (0.35).
The pipeline explicitly detected and logged this divergence (`WARNING - Large divergence between train and validation ROC AUC. Possible overfitting.`).
This is expected given the extremely small dataset (only ~200 candles fetched during development). The model learned the historical noise of this tiny sample. The pipeline correctly identifies this without falsely claiming profitability. The artifact was saved successfully for future evaluation.

**Note:** Milestone 3 is complete. The model is trained and saved. We did not proceed to Milestone 4 (backtesting).
