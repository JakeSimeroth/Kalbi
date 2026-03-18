"""
KALBI-2 Agent Registry.

Imports and re-exports every agent factory function so that callers can do::

    from src.agents import create_news_analyst, create_risk_manager
"""

from src.agents.executor import create_executor
from src.agents.fundamentals_analyst import create_fundamentals_analyst
from src.agents.kalshi_specialist import create_kalshi_specialist
from src.agents.news_analyst import create_news_analyst
from src.agents.quant_analyst import create_quant_analyst
from src.agents.risk_manager import create_risk_manager

__all__ = [
    "create_news_analyst",
    "create_quant_analyst",
    "create_fundamentals_analyst",
    "create_kalshi_specialist",
    "create_risk_manager",
    "create_executor",
]
