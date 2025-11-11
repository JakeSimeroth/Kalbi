import os
import config

class RiskManager:
    """
    A simple risk management module.
    Checks for the kill switch and calculates position size.
    """
    def check_kill_switch(self) -> bool:
        """
        Checks if the 'STOP.txt' file exists. If so, shut down.
        This is a manual, human-in-the-loop safety brake. [56, 86, 57, 58]
        """
        if os.path.exists(config.KILL_SWITCH_FILE):
            print("!!! KILL SWITCH ENGAGED. SHUTTING DOWN.!!!")
            os.remove(config.KILL_SWITCH_FILE) # Remove file to allow restart
            return True
        return False

    def calculate_position_size(self, edge: float) -> int:
        """
        Calculates the number of contracts to buy.
        This is a simple placeholder. A real system would use a
        Kelly Criterion or similar model.
        
        :param edge: The perceived edge (hybrid_prob - market_price)
        :return: Number of contracts (count)
        """
        # Simple linear sizing: 1 cent edge = $10 bet, maxing out at $100
        size_in_dollars = min(config.MAX_POSITION_SIZE, edge * 1000)
        
        # Convert $ to contract count (assuming 50 cent price)
        # A real model would use the actual price.
        count = int(size_in_dollars / 0.5) 
        return max(1, count) # Bet at least 1 contract