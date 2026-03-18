"""
KALBI-2 Chief Risk Officer Agent.

Factory function that creates a CrewAI Agent responsible for capital
protection, position-size enforcement, correlation monitoring, and
veto authority over all proposed trades.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog
from crewai import Agent

from src.tools import alpaca_api_tools, kalshi_api_tools, market_data_tools

logger = structlog.get_logger(__name__)


def create_risk_manager(llm: Optional[Any] = None) -> Agent:
    """Create and return the Chief Risk Officer agent.

    Args:
        llm: Optional LLM instance to use.  When *None* the CrewAI default
             LLM configuration is used.

    Returns:
        A fully configured :class:`crewai.Agent` ready to be added to a Crew.
    """
    tools = [*market_data_tools, *alpaca_api_tools, *kalshi_api_tools]

    agent = Agent(
        role="Chief Risk Officer",
        goal=(
            "Protect capital. Ensure no single trade, agent, or market event "
            "can cause catastrophic loss. You have VETO POWER over any trade."
        ),
        backstory=(
            "Survived 2008, the COVID crash, and every flash crash in between. "
            "Believes the market can always get worse than anyone imagines. "
            "Job is not to maximize returns but to ensure survival. Enforces "
            "hard limits and is immune to FOMO.\n\n"
            "RISK CONSTRAINTS (non-negotiable):\n"
            "- Max 2% of portfolio per trade\n"
            "- Max 10% of portfolio per ticker\n"
            "- Max 25% daily drawdown = full shutdown\n"
            "- Max 50% of portfolio deployed at any time\n"
            "- Correlation check: reject if pairwise correlation > 0.7\n"
            "- No trading in the first or last 15 minutes of any session"
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
