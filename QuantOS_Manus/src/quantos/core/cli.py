import argparse
import sys
from quantos.core.logger import logger
from quantos.core.config import AppConfig

def main():
    parser = argparse.ArgumentParser(description="QuantOS V1 MVP")
    parser.add_argument("--config", help="Path to config file", default=None)
    parser.add_argument("command", choices=["fetch-data", "verify-data", "generate-features", "train-model", "evaluate-model", "paper-trade"], help="Command to run")
    
    args = parser.parse_args()
    
    logger.info(f"Starting QuantOS with command: {args.command}")
    config = AppConfig.load(args.config)
    
    from quantos.market_data.binance import BinanceClient
    from quantos.market_data.storage import MarketDataStorage
    
    storage = MarketDataStorage(config.market_data.storage_path)
    
    if args.command == "fetch-data":
        logger.info("Fetching market data...")
        client = BinanceClient(config.market_data.binance_base_url)
        for symbol in config.market_data.symbols:
            try:
                candles = client.fetch_klines(symbol, limit=100)
                storage.save_candles(symbol, candles)
            except Exception as e:
                logger.error(f"Failed to fetch data for {symbol}: {e}")
                
    elif args.command == "verify-data":
        logger.info("Verifying market data...")
        for symbol in config.market_data.symbols:
            try:
                query = "SELECT COUNT(*) as count, MIN(timestamp) as start, MAX(timestamp) as end FROM market_data"
                result = storage.query_data(symbol, query)
                logger.info(f"Verification for {symbol}:\n{result.to_string()}")
            except Exception as e:
                logger.error(f"Failed to verify data for {symbol}: {e}")
                
    elif args.command == "generate-features":
        logger.info("Generating features from stored market data...")
        import pandas as pd
        from quantos.feature_engine.calculator import FeatureCalculator
        
        calculator = FeatureCalculator()
        
        for symbol in config.market_data.symbols:
            try:
                # Fetch recent data to calculate features
                query = "SELECT * FROM market_data ORDER BY timestamp DESC LIMIT 200"
                df = storage.query_data(symbol, query)
                
                # DuckDB returns DESC due to query, we need ASC for feature calculation
                df = df.sort_values('timestamp').reset_index(drop=True)
                
                logger.info(f"Loaded {len(df)} candles for {symbol}")
                
                # Calculate features
                featured_df = calculator.calculate_features(df)
                
                # Extract latest
                latest_vector = calculator.extract_latest_vector(featured_df, symbol)
                
                if latest_vector:
                    missing = latest_vector.has_missing_values()
                    logger.info(f"Latest Feature Vector for {symbol} at {latest_vector.timestamp}:")
                    logger.info(f"Has missing values: {missing}")
                    for name, value in latest_vector.features.items():
                        logger.info(f"  {name}: {value:.6f}" if not pd.isna(value) else f"  {name}: NaN")
                else:
                    logger.warning(f"Could not generate feature vector for {symbol}")
                    
            except Exception as e:
                logger.error(f"Failed to generate features for {symbol}: {e}")
                
    elif args.command == "train-model":
        logger.info("Training baseline model (Milestone 3)...")
        import pandas as pd
        from quantos.feature_engine.calculator import FeatureCalculator
        from quantos.alpha_engine.trainer import ModelTrainer
        from quantos.alpha_engine.models import ModelArtifactMetadata
        
        feature_calc = FeatureCalculator()
        trainer = ModelTrainer()
        
        all_data = []
        for symbol in config.market_data.symbols:
            try:
                # Fetch larger dataset for training
                # For Milestone 3, we need more data to calculate 60m features and have training data left
                query = "SELECT * FROM market_data ORDER BY timestamp ASC"
                df = storage.query_data(symbol, query)
                
                # Calculate features
                featured_df = feature_calc.calculate_features(df)
                
                # Generate target
                targeted_df = trainer.generate_target(featured_df)
                all_data.append(targeted_df)
                logger.info(f"Prepared {len(targeted_df)} labeled samples for {symbol}")
            except Exception as e:
                logger.error(f"Failed to prepare data for {symbol}: {e}")
                
        if all_data:
            combined_df = pd.concat(all_data).sort_values('timestamp')
            
            # Split chronologically
            train_df, val_df = trainer.split_chronological(combined_df)
            
            logger.info(f"Chronological split: Train {len(train_df)} rows, Val {len(val_df)} rows")
            
            # Prepare matrices
            X_train, y_train, X_val, y_val, safe_features = trainer.prepare_matrices(
                train_df, val_df, feature_calc.expected_features
            )
            
            # Train model
            model, train_metrics, val_metrics = trainer.train_model(X_train, y_train, X_val, y_val)
            
            logger.info(f"Training metrics: {train_metrics}")
            logger.info(f"Validation metrics: {val_metrics}")
            
            # Check for overfitting
            if train_metrics['roc_auc'] - val_metrics['roc_auc'] > 0.15:
                logger.warning("Large divergence between train and validation ROC AUC. Possible overfitting.")
                
            # Save artifacts
            metadata = ModelArtifactMetadata(
                model_version="1.0.0",
                strategy_version="1.0",
                feature_version=feature_calc.version,
                target_definition="Forward 15m return > 0.1%",
                prediction_horizon_minutes=trainer.horizon_minutes,
                training_start=train_df['timestamp'].min().to_pydatetime(),
                training_end=train_df['timestamp'].max().to_pydatetime(),
                validation_start=val_df['timestamp'].min().to_pydatetime(),
                validation_end=val_df['timestamp'].max().to_pydatetime(),
                symbols=config.market_data.symbols,
                features=safe_features,
                training_metrics=train_metrics,
                validation_metrics=val_metrics
            )
            
            trainer.save_artifact(model, metadata)
            
    elif args.command == "evaluate-model":
        logger.info("Evaluating baseline model (Milestone 4)...")
        import os
        import json
        import pandas as pd
        from quantos.evaluation_engine.backtester import Backtester
        from quantos.evaluation_engine.analyzer import EvaluationAnalyzer
        
        model_path = "models/model_1.0.0.txt"
        meta_path = "models/metadata_1.0.0.json"
        
        if not os.path.exists(model_path) or not os.path.exists(meta_path):
            logger.error("Model artifacts not found. Run 'train-model' first.")
            return
            
        backtester = Backtester(model_path, meta_path)
        analyzer = EvaluationAnalyzer()
        
        # Load all available data for backtesting
        all_data = []
        for symbol in config.market_data.symbols:
            try:
                query = "SELECT * FROM market_data ORDER BY timestamp ASC"
                df = storage.query_data(symbol, query)
                all_data.append(df)
            except Exception as e:
                logger.error(f"Failed to load data for {symbol}: {e}")
                
        if all_data:
            combined_df = pd.concat(all_data).sort_values('timestamp')
            
            # Run main backtest
            report = backtester.run(combined_df)
            
            # Run Monte Carlo
            mc_results = analyzer.run_monte_carlo(report.trades)
            report.monte_carlo_results = mc_results
            
            # Run Walk-Forward
            wf_results = analyzer.run_walk_forward(backtester, combined_df)
            report.walk_forward_results = wf_results
            
            # Print summary
            m = report.metrics
            logger.info("=== Backtest Report ===")
            logger.info(f"Period: {report.start_time} to {report.end_time}")
            logger.info(f"Trades: {m.trade_count}")
            logger.info(f"Net Profit: {m.net_profit:.2f}")
            logger.info(f"Win Rate: {m.win_rate:.2%}")
            logger.info(f"Max Drawdown: {m.max_drawdown:.2%}")
            logger.info(f"Sharpe: {m.sharpe_ratio if m.sharpe_ratio else 'N/A'}")
            logger.info(f"Status: {report.status}")
            
            if report.data_sufficiency_warning:
                logger.warning("DATA SUFFICIENCY WARNING: Dataset is too small for statistical confidence.")
                
            # Save report
            with open("backtest_report.json", "w") as f:
                json.dump(report.model_dump(mode='json'), f, indent=2)
            logger.info("Full report saved to backtest_report.json")
            
    elif args.command == "paper-trade":
        from quantos.core.runtime import PaperTradingRuntime
        runtime = PaperTradingRuntime(config)
        runtime.start()
        
    logger.info("Command completed successfully")

if __name__ == "__main__":
    main()
