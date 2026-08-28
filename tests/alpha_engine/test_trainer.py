import pytest
import pandas as pd
import numpy as np
import os
import tempfile
from datetime import datetime, timezone, timedelta
from quantos.alpha_engine.trainer import ModelTrainer
from quantos.alpha_engine.models import ModelArtifactMetadata

@pytest.fixture
def sample_features():
    base_time = datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc)
    data = []
    
    for i in range(100):
        data.append({
            'symbol': 'BTCUSDT',
            'timestamp': base_time + timedelta(minutes=i),
            'open': 100.0 + i,
            'close': 100.5 + i,
            'ret_1m': 0.01,
            'volatility_15m': 0.05
        })
    return pd.DataFrame(data)

def test_generate_target(sample_features):
    trainer = ModelTrainer()
    trainer.horizon_minutes = 5
    
    df = trainer.generate_target(sample_features)
    
    assert 'target' in df.columns
    assert 'target_return' in df.columns
    assert 'future_close' in df.columns
    assert 'next_open' in df.columns
    
    # Check that rows at the end are dropped because target cannot be calculated
    # For a horizon of 5, we shift -5, so the last 5 rows will have NaN future_close
    assert len(df) == len(sample_features) - trainer.horizon_minutes

def test_split_chronological(sample_features):
    trainer = ModelTrainer()
    trainer.horizon_minutes = 5
    
    df = trainer.generate_target(sample_features)
    train_df, val_df = trainer.split_chronological(df, train_ratio=0.7)
    
    # Check chronological order
    assert train_df['timestamp'].max() < val_df['timestamp'].min()
    
    # Check horizon gap (preventing leakage)
    time_diff = val_df['timestamp'].min() - train_df['timestamp'].max()
    assert time_diff > timedelta(minutes=trainer.horizon_minutes)

def test_prepare_matrices_no_leakage(sample_features):
    trainer = ModelTrainer()
    df = trainer.generate_target(sample_features)
    train_df, val_df = trainer.split_chronological(df)
    
    # We explicitly include leakage columns in the requested features
    feature_cols = ['ret_1m', 'volatility_15m', 'target', 'timestamp', 'future_close']
    
    X_train, y_train, X_val, y_val, safe_features = trainer.prepare_matrices(train_df, val_df, feature_cols)
    
    # Ensure leakage columns were removed
    assert 'target' not in safe_features
    assert 'timestamp' not in safe_features
    assert 'future_close' not in safe_features
    
    # Ensure valid features remain
    assert 'ret_1m' in safe_features
    assert 'volatility_15m' in safe_features
    
    # Ensure matrix shape matches safe features
    assert X_train.shape[1] == len(safe_features)

def test_artifact_save_load():
    with tempfile.TemporaryDirectory() as temp_dir:
        trainer = ModelTrainer(artifact_dir=temp_dir)
        
        # Create dummy model and metadata
        import lightgbm as lgb
        train_data = lgb.Dataset(np.array([[1.0], [2.0]]), label=np.array([0, 1]))
        model = lgb.train({'objective': 'binary'}, train_data, 1)
        
        meta = ModelArtifactMetadata(
            model_version="test_1",
            strategy_version="1.0",
            feature_version="1.0",
            target_definition="test",
            prediction_horizon_minutes=15,
            training_start=datetime(2023, 1, 1, tzinfo=timezone.utc),
            training_end=datetime(2023, 1, 2, tzinfo=timezone.utc),
            validation_start=datetime(2023, 1, 3, tzinfo=timezone.utc),
            validation_end=datetime(2023, 1, 4, tzinfo=timezone.utc),
            symbols=["BTCUSDT"],
            features=["f1"],
            training_metrics={"log_loss": 0.1},
            validation_metrics={"log_loss": 0.2}
        )
        
        version = trainer.save_artifact(model, meta)
        
        # Verify files exist
        assert os.path.exists(os.path.join(temp_dir, f"model_{version}.txt"))
        assert os.path.exists(os.path.join(temp_dir, f"metadata_{version}.json"))
