"""
KALBI-2 Prediction Market Specialist Agent.

Factory function that creates a CrewAI Agent specialising in Kalshi
prediction markets: probability estimation, mispricing detection,
and Bayesian updating on breaking news.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog
from crewai import Agent

from src.tools import (
    kalshi_api_tools,
    market_data_tools,
    news_scraper_tools,
    sentiment_analyzer_tools,
)

logger = structlog.get_logger(__name__)


def create_kalshi_specialist(llm: Optional[Any] = None) -> Agent:
    """Create and return the Prediction Market Specialist agent.

    Args:
        llm: Optional LLM instance to use.  When *None* the CrewAI default
             LLM configuration is used.

    Returns:
        A fully configured :class:`crewai.Agent` ready to be added to a Crew.
    """
    tools = [
        *kalshi_api_tools,
        *news_scraper_tools,
        *sentiment_analyzer_tools,
        *market_data_tools,
    ]

    agent = Agent(
        role="Prediction Market Specialist",
        goal=(
            "Find mispriced event contracts on Kalshi by synthesizing news, "
            "data, and base rates to estimate true probabilities."
        ),
        backstory=(
            "Former Superforecaster from the Good Judgment Project. Thinks "
            "in calibrated probabilities, updates on new evidence using "
            "Bayesian reasoning. Obsessed with finding edge between market "
            "price and true probability. Understands Kalshi markets are thin "
            "and can be slow to update on breaking news."
        ),
        tools=tools,
        verbose=True,
        allow_delegation=False,
        llm=llm,
    )

    logger.info(
        "agent_created",
        agent_role=agent.role,
        tool_count=len(tools),
    )
    return agent
