import os

# --- Trading Mode ---
# 'DEMO' = Use Kalshi Demo Environment (no real money) 
# 'LIVE' = Use Kalshi Production Environment (REAL MONEY)
TRADING_MODE = 'DEMO' 

# --- API Credentials (Loaded from.env file) ---
KALSHI_API_KEY_ID = os.getenv('KALSHI_API_KEY_ID')
KALSHI_PRIVATE_KEY_PATH = os.getenv('KALSHI_PRIVATE_KEY_PATH')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
SERPER_API_KEY = os.getenv('SERPER_API_KEY') 

# --- Database Connection Strings ---
TIMESCALEDB_URI = "postgresql://postgres:your_secure_password@timescaledb:5432/postgres"

# --- Trading & Risk Strategy Parameters ---
TARGET_CATEGORY = 'Politics' # The category to scan [14]
MIN_EDGE_THRESHOLD = 0.08    # The "aggressive edge" to act on (e.g., 8 cents)
MAX_POSITION_SIZE = 100      # Max $ to risk on a single trade
MIN_MARKET_LIQUIDITY = 1000  # Minimum contracts traded to consider a market

# --- Model Paths ---
META_MODEL_PATH = '/app/meta_model.pkl'

# --- Kill Switch ---
# If this file is created in the directory, the bot will shut down safely. [15, 16, 17]
KILL_SWITCH_FILE = '/app/STOP.txt'