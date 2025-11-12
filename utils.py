import os
import config
import numpy as np

class RiskManager:
    """
    Advanced risk management using Kelly Criterion and portfolio limits.
    """
    
    def __init__(self):
        self.kelly_fraction = 0.25  # Use 1/4 Kelly for safety
        self.max_portfolio_risk = 0.10  # Max 10% of capital per trade
        
    def check_kill_switch(self) -> bool:
        """
        Checks if the 'STOP.txt' file exists. If so, shut down.
        This is a manual, human-in-the-loop safety brake.
        """
        if os.path.exists(config.KILL_SWITCH_FILE):
            print("!!! KILL SWITCH ENGAGED. SHUTTING DOWN !!!")
            os.remove(config.KILL_SWITCH_FILE)  # Remove file to allow restart
            return True
        return False

    def calculate_position_size(self, edge: float, market_price: float = 50) -> int:
        """
        Calculates optimal position size using the Kelly Criterion.
        
        Kelly formula: f = (p*b - q) / b
        where:
        - f = fraction of capital to bet
        - p = probability of winning
        - q = probability of losing (1-p)
        - b = odds (amount won per dollar bet)
        
        :param edge: The perceived edge (hybrid_prob - market_price_as_probability)
        :param market_price: Current market price in cents (for calculating odds)
        :return: Number of contracts to buy
        """
        
        if edge <= 0:
            return 0  # No edge, no bet
            
        # Convert market price to probability
        market_prob = market_price / 100.0
        
        # Our estimated probability (market + edge)
        our_prob = market_prob + edge
        
        # Ensure probability is valid
        our_prob = np.clip(our_prob, 0.01, 0.99)
        
        # Calculate Kelly fraction
        # For binary bets that pay 1:1
        win_prob = our_prob
        lose_prob = 1 - our_prob
        
        # Kelly fraction
        kelly_full = win_prob - lose_prob  # Simplified for 1:1 odds
        
        # Apply fractional Kelly (more conservative)
        kelly_adjusted = kelly_full * self.kelly_fraction
        
        # Convert to dollar amount
        # Never risk more than MAX_POSITION_SIZE
        position_dollars = min(
            config.MAX_POSITION_SIZE,
            kelly_adjusted * config.MAX_POSITION_SIZE / self.max_portfolio_risk
        )
        
        # Ensure minimum bet if we have edge
        if position_dollars < 1 and edge > config.MIN_EDGE_THRESHOLD:
            position_dollars = 1
        
        # Convert dollars to contracts
        # Assume we're buying at market_price cents
        contract_price_dollars = market_price / 100.0
        num_contracts = int(position_dollars / contract_price_dollars)
        
        # Ensure at least 1 contract if we have significant edge
        if num_contracts == 0 and edge > config.MIN_EDGE_THRESHOLD * 1.5:
            num_contracts = 1
            
        print(f"  Position Sizing: Edge={edge:.3f}, Kelly={kelly_full:.3f}, "
              f"Adjusted Kelly={kelly_adjusted:.3f}, Contracts={num_contracts}")
        
        return num_contracts

    def validate_order(self, ticker: str, side: str, count: int, price: int) -> bool:
        """
        Final validation before placing an order.
        Checks for common issues and safety concerns.
        """
        
        # Check contract count
        if count <= 0:
            print(f"⚠️  Invalid order: Zero or negative contracts")
            return False
            
        if count > 1000:
            print(f"⚠️  Safety check: Order size ({count}) exceeds maximum (1000)")
            return False
        
        # Check price sanity (1-99 cents for Kalshi)
        if price < 1 or price > 99:
            print(f"⚠️  Invalid price: {price} cents (must be 1-99)")
            return False
        
        # Calculate total risk
        total_risk = count * (price / 100.0)
        if total_risk > config.MAX_POSITION_SIZE:
            print(f"⚠️  Order exceeds max position size: ${total_risk:.2f} > ${config.MAX_POSITION_SIZE}")
            return False
        
        print(f"✓ Order validated: {side.upper()} {count} contracts @ {price}¢ (Risk: ${total_risk:.2f})")
        return True

    def log_trade(self, ticker: str, side: str, count: int, price: int, edge: float):
        """
        Logs trade details for record keeping and analysis.
        """
        import datetime
        
        timestamp = datetime.datetime.now().isoformat()
        trade_log = f"{timestamp} | {ticker} | {side.upper()} | {count} @ {price}¢ | Edge: {edge:.3f}\n"
        
        # Append to log file
        with open('/app/trades.log', 'a') as f:
            f.write(trade_log)
        
        print(f"📝 Trade logged: {trade_log.strip()}")
