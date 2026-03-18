"""
KALBI-2 Quantitative Analyst Agent.

Factory function that creates a CrewAI Agent specialising in technical
analysis, statistical signal generation, and systematic trading strategies.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog
from crewai import Agent

from src.tools import market_data_tools, technical_indicators_tools

logger = structlog.get_logger(__name__)


def create_quant_analyst(llm: Optional[Any] = None) -> Agent:
    """Create and return the Quantitative Analyst agent.

    Args:
        llm: Optional LLM instance to use.  When *None* the CrewAI default
             LLM configuration is used.

    Returns:
        A fully configured :class:`crewai.Agent` ready to be added to a Crew.
    """
    tools = [*market_data_tools, *technical_indicators_tools]

    agent = Agent(
        role="Quantitative Analyst",
        goal=(
            "Generate actionable trading signals from technical and "
            "statistical analysis."
        ),
        backstory=(
            "A quant who believes in systematic, data-driven decision making. "
            "Combines classical technical indicators with statistical edge "
            "detection. Skeptical of signals without backtested evidence."
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
