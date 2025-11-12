import pandas as pd
import numpy as np
from typing import Dict, Optional

import config

class StrategyHandler:
    """
    Module 3: The "Strategy Brain" - Weighted Ensemble System
    
    This version doesn't require training! Instead, it uses a sophisticated
    weighted ensemble approach that combines multiple signals in real-time.
    Each signal is converted to a probability and weighted based on its
    historical reliability in prediction markets.
    """
    
    def __init__(self):
        print("Module 3: Initializing Weighted Ensemble Strategy (No Training Required)")
        
        # These weights are based on academic research on prediction markets
        # and technical analysis effectiveness
        self.signal_weights = {
            'fundamental': 0.40,  # LLM analysis gets highest weight
            'momentum': 0.25,     # Price momentum 
            'mean_reversion': 0.15,  # RSI-based mean reversion
            'volume': 0.10,       # Volume confirmation
            'time_decay': 0.10    # Time-based adjustment
        }
        
        print(f"Strategy weights: {self.signal_weights}")

    def generate_hybrid_forecast(self, fundamental_prob: float, quant_features: dict) -> float:
        """
        Combines all signals into a final probability without ML.
        Uses financial theory and market microstructure principles.
        """
        
        if not quant_features:
            # If we have no technical data, rely solely on fundamental
            return fundamental_prob
            
        try:
            # Container for all our probability signals
            signals = {}
            
            # 1. FUNDAMENTAL SIGNAL (from LLM)
            signals['fundamental'] = fundamental_prob
            
            # 2. MOMENTUM SIGNAL
            # Based on MACD histogram - positive momentum increases probability
            macd_hist = quant_features.get('macd_hist', 0)
            if macd_hist != 0:
                # Normalize MACD to probability space using sigmoid
                momentum_strength = 1 / (1 + np.exp(-macd_hist * 10))
                signals['momentum'] = momentum_strength
            else:
                signals['momentum'] = 0.5  # Neutral
            
            # 3. MEAN REVERSION SIGNAL (RSI)
            # When RSI < 30: Oversold (likely to go up)
            # When RSI > 70: Overbought (likely to go down)
            rsi = quant_features.get('rsi_14', 50)
            if rsi < 30:
                # Oversold - higher probability of upward move
                signals['mean_reversion'] = 0.7 + (30 - rsi) * 0.01
            elif rsi > 70:
                # Overbought - lower probability of continued upward move
                signals['mean_reversion'] = 0.3 - (rsi - 70) * 0.01
            else:
                # Neutral RSI - slight mean reversion tendency
                signals['mean_reversion'] = 0.5 + (50 - rsi) * 0.002
            
            # 4. VOLUME SIGNAL
            # High volume confirms the trend, low volume suggests uncertainty
            current_volume = quant_features.get('volume_sma_5', 1000)
            obv = quant_features.get('obv', 0)
            
            if current_volume > 0 and obv > 0:
                # Positive OBV with good volume = bullish
                volume_ratio = min(obv / current_volume, 10) / 10  # Normalize to 0-1
                signals['volume'] = 0.5 + (volume_ratio - 0.5) * 0.5
            else:
                signals['volume'] = 0.5  # Neutral if no volume data
            
            # 5. TIME DECAY SIGNAL
            # As markets approach expiration, they tend toward extremes
            hours_remaining = quant_features.get('hours_to_expiration', 24)
            
            if hours_remaining < 6:
                # Very close to expiration - amplify the current consensus
                if fundamental_prob > 0.5:
                    signals['time_decay'] = min(fundamental_prob + 0.2, 0.95)
                else:
                    signals['time_decay'] = max(fundamental_prob - 0.2, 0.05)
            elif hours_remaining < 24:
                # Within a day - moderate amplification
                if fundamental_prob > 0.5:
                    signals['time_decay'] = min(fundamental_prob + 0.1, 0.9)
                else:
                    signals['time_decay'] = max(fundamental_prob - 0.1, 0.1)
            else:
                # Plenty of time - no adjustment
                signals['time_decay'] = fundamental_prob
            
            # CALCULATE WEIGHTED ENSEMBLE PROBABILITY
            weighted_sum = 0
            total_weight = 0
            
            print("\n=== Signal Analysis ===")
            for signal_name, signal_value in signals.items():
                weight = self.signal_weights.get(signal_name, 0)
                if signal_value is not None:
                    weighted_sum += signal_value * weight
                    total_weight += weight
                    print(f"{signal_name}: {signal_value:.3f} (weight: {weight})")
            
            # Final probability is the weighted average
            if total_weight > 0:
                hybrid_prob = weighted_sum / total_weight
            else:
                hybrid_prob = fundamental_prob  # Fallback
            
            # Apply Kelly Criterion adjustment for risk management
            # This prevents overconfident predictions
            hybrid_prob = self._apply_kelly_adjustment(hybrid_prob)
            
            print(f"Final Hybrid Probability: {hybrid_prob:.3f}")
            print("=" * 25)
            
            return hybrid_prob
            
        except Exception as e:
            print(f"Error in Module 3 ensemble calculation: {e}")
            return fundamental_prob  # Fallback to fundamental only

    def _apply_kelly_adjustment(self, prob: float, confidence: float = 0.7) -> float:
        """
        Apply Kelly Criterion-inspired adjustment to prevent overconfidence.
        This reduces extreme probabilities based on our confidence level.
        
        :param prob: Raw probability
        :param confidence: How confident we are in our model (0-1)
        :return: Adjusted probability
        """
        # Pull probabilities toward 0.5 based on confidence
        # If confidence = 1.0, no adjustment
        # If confidence = 0.0, return 0.5 (complete uncertainty)
        adjusted = 0.5 + (prob - 0.5) * confidence
        
        # Never go below 5% or above 95% (avoid extreme positions)
        return np.clip(adjusted, 0.05, 0.95)

    def get_signal_diagnostics(self) -> Dict:
        """
        Returns diagnostic information about the strategy.
        Useful for monitoring and debugging.
        """
        return {
            'strategy_type': 'Weighted Ensemble',
            'weights': self.signal_weights,
            'requires_training': False,
            'confidence_level': 0.7
        }
