import json
import pandas as pd
from sqlalchemy import create_engine, text
import config
from module_2_quantitative_engine import QuantitativeEngine
from module_3_strategy_handler import StrategyHandler

def initialize_system():
    """
    Initializes the trading system and validates all components.
    No training required - this just ensures everything is properly configured.
    """
    print("=" * 60)
    print("QUANTAMENTAL TRADER - SYSTEM INITIALIZATION")
    print("=" * 60)
    
    # 1. Test Database Connection
    print("\n[1/4] Testing TimescaleDB connection...")
    try:
        db_engine = create_engine(config.TIMESCALEDB_URI)
        with db_engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print(f"✓ Database connected: {version[:50]}...")
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        print("Make sure TimescaleDB is running (docker-compose up timescaledb)")
        return False
    
    # 2. Initialize Quantitative Engine
    print("\n[2/4] Initializing Quantitative Engine...")
    try:
        quant_engine = QuantitativeEngine()
        print("✓ Quantitative engine initialized with TimescaleDB hypertables")
    except Exception as e:
        print(f"✗ Quantitative engine failed: {e}")
        return False
    
    # 3. Initialize Strategy Handler
    print("\n[3/4] Initializing Strategy Handler...")
    try:
        strategy = StrategyHandler()
        diagnostics = strategy.get_signal_diagnostics()
        print(f"✓ Strategy initialized: {diagnostics['strategy_type']}")
        print(f"  Requires training: {diagnostics['requires_training']}")
        print(f"  Signal weights: {json.dumps(diagnostics['weights'], indent=2)}")
    except Exception as e:
        print(f"✗ Strategy handler failed: {e}")
        return False
    
    # 4. Test Strategy with Sample Data
    print("\n[4/4] Testing strategy with sample data...")
    try:
        # Sample inputs
        sample_fundamental_prob = 0.65
        sample_quant_features = {
            'rsi_14': 45,
            'macd_hist': 0.02,
            'obv': 5000,
            'volume_sma_5': 1000,
            'hours_to_expiration': 48
        }
        
        print(f"Sample fundamental probability: {sample_fundamental_prob}")
        print(f"Sample RSI: {sample_quant_features['rsi_14']}")
        
        # Generate hybrid forecast
        hybrid_prob = strategy.generate_hybrid_forecast(
            sample_fundamental_prob, 
            sample_quant_features
        )
        
        print(f"\n✓ Strategy test successful!")
        print(f"  Output hybrid probability: {hybrid_prob:.3f}")
        
        # Calculate what the edge would be at different market prices
        print("\n  Edge Analysis (Hybrid Prob = {:.1%}):".format(hybrid_prob))
        for market_price in [40, 50, 60, 70, 80]:
            edge = hybrid_prob - (market_price / 100)
            action = "BUY" if edge > config.MIN_EDGE_THRESHOLD else "SKIP"
            print(f"    Market @ {market_price}¢ → Edge: {edge:+.3f} → {action}")
            
    except Exception as e:
        print(f"✗ Strategy test failed: {e}")
        return False
    
    # 5. Create configuration summary
    print("\n" + "=" * 60)
    print("SYSTEM CONFIGURATION")
    print("=" * 60)
    print(f"Trading Mode: {config.TRADING_MODE}")
    print(f"Target Category: {config.TARGET_CATEGORY}")
    print(f"Min Edge Threshold: {config.MIN_EDGE_THRESHOLD:.1%}")
    print(f"Max Position Size: ${config.MAX_POSITION_SIZE}")
    print(f"Min Market Liquidity: {config.MIN_MARKET_LIQUIDITY} contracts")
    
    # Save configuration file for reference
    config_summary = {
        'system': 'Quantamental Trader v1.0',
        'strategy': 'Weighted Ensemble (No Training Required)',
        'initialization_successful': True,
        'configuration': {
            'trading_mode': config.TRADING_MODE,
            'target_category': config.TARGET_CATEGORY,
            'min_edge_threshold': config.MIN_EDGE_THRESHOLD,
            'max_position_size': config.MAX_POSITION_SIZE,
            'min_market_liquidity': config.MIN_MARKET_LIQUIDITY
        },
        'signal_weights': diagnostics['weights']
    }
    
    with open('/app/system_config.json', 'w') as f:
        json.dump(config_summary, f, indent=2)
    
    print("\n✓ Configuration saved to /app/system_config.json")
    
    print("\n" + "=" * 60)
    print("✅ SYSTEM READY TO TRADE")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Ensure your .env file has all required API keys")
    print("2. Run: docker-compose up trader_app")
    print("3. Monitor the logs for trade signals")
    print("4. Create STOP.txt file to safely shut down\n")
    
    return True

if __name__ == "__main__":
    success = initialize_system()
    if not success:
        print("\n⚠️  System initialization failed. Please fix the issues above.")
        exit(1)
