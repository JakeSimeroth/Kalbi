"""
KALBI-2 Fundamentals Research Analyst Agent.

Factory function that creates a CrewAI Agent specialising in fundamental
analysis: earnings quality, cash-flow sustainability, macro positioning,
and SEC filing review.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog
from crewai import Agent

from src.tools import market_data_tools, news_scraper_tools, sec_fetcher_tools

logger = structlog.get_logger(__name__)


def create_fundamentals_analyst(llm: Optional[Any] = None) -> Agent:
    """Create and return the Fundamentals Research Analyst agent.

    Args:
        llm: Optional LLM instance to use.  When *None* the CrewAI default
             LLM configuration is used.

    Returns:
        A fully configured :class:`crewai.Agent` ready to be added to a Crew.
    """
    tools = [*sec_fetcher_tools, *market_data_tools, *news_scraper_tools]

    agent = Agent(
        role="Fundamentals Research Analyst",
        goal=(
            "Evaluate company health, earnings trajectory, and macro "
            "positioning."
        ),
        backstory=(
            "CFA charterholder who reads 10-Ks for fun. Focuses on earnings "
            "quality, cash flow sustainability, and catalysts. Understands "
            "that fundamentals set direction but technicals set timing."
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
