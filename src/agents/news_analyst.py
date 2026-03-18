"""
KALBI-2 News Analyst Agent.

Factory function that creates a CrewAI Agent specialising in real-time
news monitoring, event detection, and narrative-driven sentiment analysis.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog
from crewai import Agent

from src.tools import news_scraper_tools, sentiment_analyzer_tools

logger = structlog.get_logger(__name__)


def create_news_analyst(llm: Optional[Any] = None) -> Agent:
    """Create and return the Senior News Analyst agent.

    Args:
        llm: Optional LLM instance to use.  When *None* the CrewAI default
             LLM configuration is used.

    Returns:
        A fully configured :class:`crewai.Agent` ready to be added to a Crew.
    """
    tools = [*news_scraper_tools, *sentiment_analyzer_tools]

    agent = Agent(
        role="Senior News Analyst",
        goal=(
            "Identify market-moving events and sentiment shifts before "
            "they are priced in."
        ),
        backstory=(
            "Former Bloomberg terminal power user who synthesizes information "
            "from dozens of sources in real-time. Has a nose for separating "
            "signal from noise and understands how narrative drives price action."
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
