import pandas as pd
import numpy as np
import lightgbm as lgb
import os
import json
import joblib
from datetime import datetime
from typing import Tuple, Dict, Any, List
from quantos.core.logger import logger
from quantos.alpha_engine.models import ModelArtifactMetadata

class ModelTrainer:
    """
    Builds the smallest reliable ML training pipeline for QuantOS V1.
    Uses LightGBM (preferred model per specs) and strict chronological splitting.
    """
    
    def __init__(self, artifact_dir: str = "models"):
        self.artifact_dir = artifact_dir
        os.makedirs(self.artifact_dir, exist_ok=True)
        self.horizon_minutes = 15
        
    def generate_target(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Creates a reproducible prediction target.
        Target: Forward 15-minute return (classification: 1 if return > 0.1%, 0 otherwise).
        This provides a clear horizon and explicit timing without leaking into features.
        """
        if df.empty:
            return df
            
        df = df.copy()
        df = df.sort_values('timestamp')
        
        # Calculate forward return exactly at the horizon
        # The return is calculated from the next candle's open to the close 15m later
        # to simulate a realistic entry price
        df['future_close'] = df['close'].shift(-self.horizon_minutes)
        df['next_open'] = df['open'].shift(-1)
        
        # Target return: (future_close - next_open) / next_open
        df['target_return'] = (df['future_close'] - df['next_open']) / df['next_open']
        
        # Binary classification target: 1 if return > 0.001 (0.1%), else 0
        df['target'] = (df['target_return'] > 0.001).astype(int)
        
        # Drop rows where target cannot be calculated (end of dataset)
        df = df.dropna(subset=['target_return', 'target'])
        
        return df
        
    def split_chronological(self, df: pd.DataFrame, train_ratio: float = 0.7) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Splits data strictly in chronological order to prevent future-data leakage.
        """
        if df.empty:
            return df, df
            
        df = df.sort_values('timestamp')
        split_idx = int(len(df) * train_ratio)
        
        train_df = df.iloc[:split_idx].copy()
        val_df = df.iloc[split_idx:].copy()
        
        # Ensure gap between train and validation to prevent horizon leakage
        # Drop the first `horizon_minutes` rows from validation
        if len(val_df) > self.horizon_minutes:
            val_df = val_df.iloc[self.horizon_minutes:]
            
        return train_df, val_df
        
    def prepare_matrices(self, train_df: pd.DataFrame, val_df: pd.DataFrame, feature_cols: List[str]) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Extracts feature matrices and target vectors.
        Explicitly excludes timestamps, symbols, and target columns from features.
        """
        # Ensure no leakage columns in feature_cols
        leakage_cols = ['timestamp', 'symbol', 'target', 'target_return', 'future_close', 'next_open']
        safe_features = [f for f in feature_cols if f not in leakage_cols]
        
        # Drop any rows with NaN in features
        train_clean = train_df.dropna(subset=safe_features)
        val_clean = val_df.dropna(subset=safe_features)
        
        if len(train_clean) == 0:
            raise ValueError("No training data left after dropping NaNs. Check feature calculations.")
            
        X_train = train_clean[safe_features].values
        y_train = train_clean['target'].values
        
        X_val = val_clean[safe_features].values
        y_val = val_clean['target'].values
        
        return X_train, y_train, X_val, y_val, safe_features
        
    def train_model(self, X_train, y_train, X_val, y_val) -> Tuple[lgb.Booster, Dict[str, float], Dict[str, float]]:
        """
        Trains exactly ONE baseline LightGBM model with minimal tuning.
        """
        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)
        
        # Minimal conservative configuration
        params = {
            'objective': 'binary',
            'metric': 'binary_logloss',
            'boosting_type': 'gbdt',
            'learning_rate': 0.05,
            'num_leaves': 15,          # Keep complexity low to prevent overfitting
            'max_depth': 4,            # Keep depth low
            'feature_fraction': 0.8,
            'seed': 42,                # Deterministic reproducibility
            'verbose': -1
        }
        
        logger.info("Training LightGBM baseline model...")
        
        # Train model
        model = lgb.train(
            params,
            train_data,
            num_boost_round=100,
            valid_sets=[train_data, val_data],
            valid_names=['train', 'valid'],
            callbacks=[lgb.early_stopping(stopping_rounds=10, verbose=False)]
        )
        
        # Calculate basic metrics (LogLoss and basic accuracy approximation)
        train_preds = model.predict(X_train)
        val_preds = model.predict(X_val)
        
        from sklearn.metrics import log_loss, roc_auc_score
        
        train_metrics = {
            'log_loss': float(log_loss(y_train, train_preds)),
            'roc_auc': float(roc_auc_score(y_train, train_preds)) if len(np.unique(y_train)) > 1 else 0.5
        }
        
        val_metrics = {
            'log_loss': float(log_loss(y_val, val_preds)),
            'roc_auc': float(roc_auc_score(y_val, val_preds)) if len(np.unique(y_val)) > 1 else 0.5
        }
        
        return model, train_metrics, val_metrics
        
    def save_artifact(self, model: lgb.Booster, metadata: ModelArtifactMetadata) -> str:
        """
        Saves the trained model and metadata for reproducible future inference.
        """
        version = metadata.model_version
        model_path = os.path.join(self.artifact_dir, f"model_{version}.txt")
        meta_path = os.path.join(self.artifact_dir, f"metadata_{version}.json")
        
        # Save model
        model.save_model(model_path)
        
        # Save metadata
        with open(meta_path, 'w') as f:
            json.dump(metadata.model_dump(mode='json'), f, indent=2)
            
        logger.info(f"Saved model artifact {version} to {self.artifact_dir}")
        return version
