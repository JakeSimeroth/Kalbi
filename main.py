import time
from kalshi_client import KalshiTraderAPI
from module_1_fundamental_forecaster import FundamentalForecaster
from module_2_quantitative_engine import QuantitativeEngine
from module_3_strategy_handler import StrategyHandler
from utils import RiskManager
import config

class QuantamentalTrader:
    """
    The main "all-in-one" program.
    Orchestrates all modules in a continuous event loop.
    """
    def __init__(self):
        print("Initializing Quantamental Trader...")
        self.kalshi_api = KalshiTraderAPI()
        self.forecaster = FundamentalForecaster() # Module 1
        self.quant_engine = QuantitativeEngine()  # Module 2
        self.strategy_handler = StrategyHandler() # Module 3
        self.risk_manager = RiskManager()
        self.processed_markets = set() # To avoid re-analyzing static markets

    def run_bot(self):
        """The main event loop."""
        print("Bot is LIVE. Starting event loop...")
        while True:
            # 1. RISK CHECK: Check for manual kill switch [56, 57, 58]
            if self.risk_manager.check_kill_switch():
                break
                
            try:
                # 2. DISCOVER: Find all open politics markets [60, 61]
                markets = self.kalshi_api.get_politics_markets()
                
                for market in markets:
                    if market.ticker in self.processed_markets:
                        continue # Skip if already analyzed this loop

                    print(f"\n--- Analyzing Market: {market.ticker} ---")
                    
                    # 3. LIQUIDITY CHECK: Ignore illiquid markets
                    if market.volume < config.MIN_MARKET_LIQUIDITY:
                        print(f"Skipping {market.ticker}: Insufficient volume ({market.volume}).")
                        continue

                    # 4. MODULE 2: Update "Graph Trends" data [62]
                    self.quant_engine.update_market_data(self.kalshi_api, market.ticker)
                    
                    # 5. MODULE 2: Calculate Quantitative Features
                    quant_features = self.quant_engine.calculate_features(
                        market.ticker, 
                        int(market.expiration_ts)
                    )
                    if not quant_features:
                        print(f"Skipping {market.ticker}: No quantitative features found.")
                        continue
                        
                    # 6. MODULE 1: Calculate Fundamental Probability
                    fundamental_prob = self.forecaster.get_fundamental_probability(market)
                    
                    # 7. MODULE 3: Generate Hybrid Forecast
                    hybrid_prob = self.strategy_handler.generate_hybrid_forecast(
                        fundamental_prob, 
                        quant_features
                    )
                    
                    # 8. FIND THE "AGGRESSIVE EDGE"
                    current_price_cents = market.yes_ask # Price to buy 'Yes'
                    edge = hybrid_prob - (current_price_cents / 100.0)
                    
                    print(f"EDGE ANALYSIS: HybridProb={hybrid_prob:.2f}, MarketAsk={current_price_cents}c, Edge={edge:.2f}")

                    # 9. EXECUTE TRADE
                    if edge > config.MIN_EDGE_THRESHOLD:
                        position_size = self.risk_manager.calculate_position_size(edge)
                        self.kalshi_api.place_order(
                            ticker=market.ticker,
                            side='yes',
                            count=position_size,
                            price=current_price_cents
                        )
                    
                    self.processed_markets.add(market.ticker)
                
                self.processed_markets.clear() # Clear cache for next loop
                print("\nLoop complete. Waiting 5 minutes...")
                time.sleep(300) # Wait 5 minutes before re-scanning all markets

            except Exception as e:
                print(f"!!! FATAL ERROR IN MAIN LOOP: {e}!!!")
                time.sleep(60) # Wait 1 min before retrying

### --- How to Run ---

# 1. Make sure Docker is running.
# 2. Fill in your.env file with API keys.
# 3. Build the Docker container:
#    docker-compose build
#
# 4. Run the one-time model training script:
#    docker-compose run --rm trader_app python train_model.py
#
# 5. Run the main bot:
#    docker-compose up trader_app

if __name__ == "__main__":
    bot = QuantamentalTrader()
    bot.run_bot()