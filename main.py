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
        print("=" * 60)
        print("INITIALIZING QUANTAMENTAL TRADER")
        print("=" * 60)
        
        self.kalshi_api = KalshiTraderAPI()
        self.forecaster = FundamentalForecaster()  # Module 1
        self.quant_engine = QuantitativeEngine()   # Module 2
        self.strategy_handler = StrategyHandler()  # Module 3
        self.risk_manager = RiskManager()
        
        self.processed_markets = set()  # To avoid re-analyzing static markets
        self.trade_count = 0
        self.loop_count = 0
        
        print("✅ All modules initialized successfully")
        print("=" * 60)

    def run_bot(self):
        """The main event loop."""
        print(f"\n🤖 BOT IS LIVE IN {config.TRADING_MODE} MODE")
        print("Starting continuous market scanning...\n")
        
        while True:
            self.loop_count += 1
            print(f"\n{'='*60}")
            print(f"SCAN CYCLE #{self.loop_count} - {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*60}")
            
            # 1. RISK CHECK: Check for manual kill switch
            if self.risk_manager.check_kill_switch():
                print("\n👋 Shutdown initiated by kill switch. Goodbye!")
                break
                
            try:
                # 2. DISCOVER: Find all open politics markets
                markets = self.kalshi_api.get_politics_markets()
                
                if not markets:
                    print("⚠️  No open politics markets found. Will retry in 5 minutes...")
                    time.sleep(300)
                    continue
                
                print(f"📊 Found {len(markets)} open politics markets")
                
                opportunities_found = 0
                
                for i, market in enumerate(markets, 1):
                    # Skip if already analyzed this loop
                    if market.ticker in self.processed_markets:
                        continue
                    
                    print(f"\n--- [{i}/{len(markets)}] Analyzing: {market.ticker} ---")
                    print(f"    Title: {market.title[:80]}...")
                    
                    # 3. LIQUIDITY CHECK: Ignore illiquid markets
                    if market.volume < config.MIN_MARKET_LIQUIDITY:
                        print(f"    ⏭️  Skipping: Low volume ({market.volume} < {config.MIN_MARKET_LIQUIDITY})")
                        self.processed_markets.add(market.ticker)
                        continue

                    # 4. MODULE 2: Update "Graph Trends" data
                    print(f"    📈 Fetching technical data...")
                    self.quant_engine.update_market_data(self.kalshi_api, market.ticker)
                    
                    # 5. MODULE 2: Calculate Quantitative Features
                    quant_features = self.quant_engine.calculate_features(
                        market.ticker, 
                        int(market.expiration_timestamp)
                    )
                    
                    if not quant_features:
                        print(f"    ⏭️  Skipping: Insufficient technical data")
                        self.processed_markets.add(market.ticker)
                        continue
                        
                    # 6. MODULE 1: Calculate Fundamental Probability
                    print(f"    🧠 Running LLM fundamental analysis...")
                    fundamental_prob = self.forecaster.get_fundamental_probability(market)
                    
                    # 7. MODULE 3: Generate Hybrid Forecast
                    print(f"    🔀 Generating hybrid forecast...")
                    hybrid_prob = self.strategy_handler.generate_hybrid_forecast(
                        fundamental_prob, 
                        quant_features
                    )
                    
                    # 8. FIND THE "AGGRESSIVE EDGE"
                    current_price_cents = market.yes_ask  # Price to buy 'Yes'
                    edge = hybrid_prob - (current_price_cents / 100.0)
                    
                    print(f"\n    💡 EDGE ANALYSIS:")
                    print(f"       Hybrid Probability: {hybrid_prob:.1%}")
                    print(f"       Market Ask Price:   {current_price_cents}¢")
                    print(f"       Edge:              {edge:+.1%}")
                    
                    # 9. EXECUTE TRADE IF EDGE EXISTS
                    if edge > config.MIN_EDGE_THRESHOLD:
                        print(f"    🎯 OPPORTUNITY FOUND! Edge exceeds threshold ({edge:.1%} > {config.MIN_EDGE_THRESHOLD:.1%})")
                        
                        position_size = self.risk_manager.calculate_position_size(edge, current_price_cents)
                        
                        if position_size > 0:
                            # Validate order before execution
                            if self.risk_manager.validate_order(
                                market.ticker, 'yes', position_size, current_price_cents
                            ):
                                # Place the order
                                self.kalshi_api.place_order(
                                    ticker=market.ticker,
                                    side='yes',
                                    count=position_size,
                                    price=current_price_cents
                                )
                                
                                # Log the trade
                                self.risk_manager.log_trade(
                                    market.ticker, 'yes', position_size, 
                                    current_price_cents, edge
                                )
                                
                                self.trade_count += 1
                                opportunities_found += 1
                                print(f"    ✅ Trade #{self.trade_count} executed successfully!")
                        else:
                            print(f"    ⚠️  Position size too small, skipping trade")
                    else:
                        print(f"    ❌ No edge: {edge:+.1%} < {config.MIN_EDGE_THRESHOLD:.1%} threshold")
                    
                    self.processed_markets.add(market.ticker)
                    
                    # Brief pause between markets to avoid API rate limits
                    time.sleep(2)
                
                # Summary of this scan
                print(f"\n📊 SCAN SUMMARY:")
                print(f"   Markets analyzed: {len(self.processed_markets)}")
                print(f"   Opportunities found: {opportunities_found}")
                print(f"   Total trades executed: {self.trade_count}")
                
                # Clear the cache for next loop
                self.processed_markets.clear()
                
                # Wait before next scan
                wait_time = 300  # 5 minutes
                print(f"\n⏰ Next scan in {wait_time} seconds...")
                print(f"   (Create '{config.KILL_SWITCH_FILE}' to stop safely)")
                
                # Sleep with periodic checks for kill switch
                for _ in range(wait_time // 10):
                    time.sleep(10)
                    if self.risk_manager.check_kill_switch():
                        print("\n👋 Shutdown initiated by kill switch. Goodbye!")
                        return

            except KeyboardInterrupt:
                print("\n\n⚠️  Keyboard interrupt received. Shutting down gracefully...")
                break
                
            except Exception as e:
                print(f"\n🚨 ERROR IN MAIN LOOP: {e}")
                print("Will retry in 60 seconds...")
                time.sleep(60)

        print(f"\n{'='*60}")
        print(f"TRADING SESSION COMPLETE")
        print(f"Total trades executed: {self.trade_count}")
        print(f"Total scan cycles: {self.loop_count}")
        print(f"{'='*60}\n")

# ============================================================
# HOW TO RUN THIS BOT
# ============================================================
#
# 1. Make sure Docker is running
#
# 2. Fill in your .env file with API keys:
#    KALSHI_API_KEY_ID=your_key_here
#    KALSHI_PRIVATE_KEY_PATH=/app/kalshi_private_key.pem
#    GEMINI_API_KEY=your_key_here
#    SERPER_API_KEY=your_key_here
#
# 3. Place your Kalshi private key file in the project directory
#
# 4. Initialize the system (one time only):
#    docker-compose run --rm trader_app python train_model.py
#
# 5. Run the main bot:
#    docker-compose up trader_app
#
# 6. To stop safely, create a file named 'STOP.txt' in the directory
#
# ============================================================

if __name__ == "__main__":
    bot = QuantamentalTrader()
    bot.run_bot()
