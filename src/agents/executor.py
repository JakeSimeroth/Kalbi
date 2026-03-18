"""
KALBI-2 Trade Executor Agent.

Factory function that creates a CrewAI Agent responsible for submitting
approved trades to Kalshi and Alpaca, confirming fills, and logging
execution details.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog
from crewai import Agent

from src.tools import alpaca_api_tools, kalshi_api_tools

logger = structlog.get_logger(__name__)


def create_executor(llm: Optional[Any] = None) -> Agent:
    """Create and return the Trade Executor agent.

    Args:
        llm: Optional LLM instance to use.  When *None* the CrewAI default
             LLM configuration is used.

    Returns:
        A fully configured :class:`crewai.Agent` ready to be added to a Crew.
    """
    tools = [*kalshi_api_tools, *alpaca_api_tools]

    agent = Agent(
        role="Trade Executor",
        goal="Execute approved trades with best available pricing and confirm fills.",
        backstory=(
            "Meticulous execution trader. Never fat-fingers an order. "
            "Double-checks every parameter before submission. Logs everything. "
            "ONLY executes trades approved by Risk Manager. Uses limit orders "
            "by default."
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
