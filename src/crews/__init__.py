"""
KALBI-2 Crew Registry.

Imports and re-exports every crew class so that callers can do::

    from src.crews import KalshiCrew, EquitiesCrew, MetaCrew
"""

from src.crews.equities_crew import EquitiesCrew
from src.crews.kalshi_crew import KalshiCrew
from src.crews.meta_crew import MetaCrew

__all__ = [
    "KalshiCrew",
    "EquitiesCrew",
    "MetaCrew",
]
