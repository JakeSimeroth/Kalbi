import pandas as pd
import joblib

import config

class StrategyHandler:
    """
    Module 3: The "Strategy Brain" or "Meta-Model".
    Fuses the 'fundamental_prob' (from Module 1) and 'quant_features'
    (from Module 2) to find the "aggressive edge".
    """
    def __init__(self):
        try:
            self.model = joblib.load(config.META_MODEL_PATH)
            self.scaler = joblib.load('/app/scaler.pkl')
            print("Module 3: Meta-model loaded successfully.")
        except FileNotFoundError:
            print("ERROR: 'meta_model.pkl' not found. Run 'train_model.py' first.")
            self.model = None
            self.scaler = None

    def generate_hybrid_forecast(self, fundamental_prob: float, quant_features: dict) -> float:
        """
        Combines signals and predicts the 'true' hybrid probability.
        """
        if not self.model:
            print("Module 3: No model loaded, returning neutral probability.")
            return 0.5

        try:
            # 1. Create the feature vector (must match train_model.py)
            feature_data = quant_features.copy()
            feature_data['fundamental_prob'] = fundamental_prob
            
            # Ensure order is identical to training [83, 84, 85]
            feature_df = pd.DataFrame([feature_data])
            feature_order = self.model.get_booster().feature_names
            feature_df = feature_df[feature_order]

            # 2. Scale the features
            features_scaled = self.scaler.transform(feature_df)
            
            # 3. Predict the probability of 'Yes' (class 1)
            hybrid_prob = self.model.predict_proba(features_scaled)[11]
            
            print(f"Module 3: Hybrid forecast generated. Prob: {hybrid_prob:.2f}")
            return hybrid_prob
        except Exception as e:
            print(f"Error in Module 3 (Strategy Handler): {e}")
            return 0.5 # Neutral prob on failure