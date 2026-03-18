"""
KALBI-2 Kalshi Prediction Market Trading Crew.

Orchestrates the full pipeline for scanning Kalshi prediction markets,
identifying mispriced events, validating risk, and executing trades.
Designed to run every 15 minutes.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import structlog
from crewai import Crew, Process, Task

from src.agents import (
    create_executor,
    create_kalshi_specialist,
    create_news_analyst,
    create_risk_manager,
)

logger = structlog.get_logger(__name__)


class KalshiCrew:
    """Runs every 15 minutes. Scans Kalshi markets for mispriced events.

    The crew follows a strict sequential pipeline:

    1. **News Analyst** -- scans for events relevant to active Kalshi markets.
    2. **Kalshi Specialist** -- evaluates markets for edge using Bayesian
       reasoning and the news context.
    3. **Risk Manager** -- reviews each proposed trade against hard limits.
    4. **Executor** -- places approved orders via Kalshi limit orders.
    """

    def __init__(self, llm: Optional[Any] = None) -> None:
        self._llm = llm

        # -- Agents ----------------------------------------------------------
        self._news_analyst = create_news_analyst(llm=llm)
        self._kalshi_specialist = create_kalshi_specialist(llm=llm)
        self._risk_manager = create_risk_manager(llm=llm)
        self._executor = create_executor(llm=llm)

        # -- Tasks -----------------------------------------------------------
        self._task_scan_news = Task(
            description=(
                "Scan news sources for events that could affect active Kalshi "
                "prediction markets. Focus on politics, economics, and major "
                "events. Return structured JSON with event summaries, sentiment "
                "scores, and affected markets."
            ),
            expected_output=(
                "JSON object with an 'events' list. Each event contains: "
                "'headline', 'source', 'summary', 'sentiment_score' (-1 to 1), "
                "'affected_markets' (list of Kalshi ticker strings), and "
                "'timestamp'."
            ),
            agent=self._news_analyst,
        )

        self._task_evaluate_markets = Task(
            description=(
                "Using the news analysis and current market prices, evaluate "
                "all active Kalshi markets. Estimate true probabilities using "
                "Bayesian reasoning. Identify markets where estimated "
                "probability differs from market price by at least 5%. Return "
                "structured trade recommendations."
            ),
            expected_output=(
                "JSON object with a 'recommendations' list. Each entry "
                "contains: 'market_ticker', 'market_title', 'current_price', "
                "'estimated_probability', 'edge_pct', 'direction' "
                "('yes'/'no'), 'confidence' (0-1), and 'reasoning'."
            ),
            agent=self._kalshi_specialist,
            context=[self._task_scan_news],
        )

        self._task_risk_review = Task(
            description=(
                "Review each proposed Kalshi trade for risk compliance. Check "
                "position sizing, portfolio correlation, daily loss limits, "
                "and deployment caps. Approve or reject each trade with "
                "specific reasoning."
            ),
            expected_output=(
                "JSON object with an 'trades' list. Each entry contains: "
                "'market_ticker', 'status' ('approved'/'rejected'), "
                "'original_size', 'approved_size', 'rejection_reason' "
                "(null if approved), and 'risk_notes'."
            ),
            agent=self._risk_manager,
            context=[self._task_evaluate_markets],
        )

        self._task_execute = Task(
            description=(
                "Execute all approved Kalshi trades using limit orders. Log "
                "every order attempt with full details. Report fill status "
                "for each trade."
            ),
            expected_output=(
                "JSON object with an 'executions' list. Each entry contains: "
                "'market_ticker', 'order_id', 'side', 'price', 'quantity', "
                "'status' ('filled'/'partial'/'pending'/'failed'), and "
                "'error' (null if successful)."
            ),
            agent=self._executor,
            context=[self._task_risk_review],
        )

        # -- Crew ------------------------------------------------------------
        self._crew = Crew(
            agents=[
                self._news_analyst,
                self._kalshi_specialist,
                self._risk_manager,
                self._executor,
            ],
            tasks=[
                self._task_scan_news,
                self._task_evaluate_markets,
                self._task_risk_review,
                self._task_execute,
            ],
            process=Process.sequential,
            verbose=True,
        )

        logger.info(
            "crew_initialized",
            crew="KalshiCrew",
            agent_count=len(self._crew.agents),
            task_count=len(self._crew.tasks),
        )

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    def run(self) -> Dict[str, Any]:
        """Execute the full crew pipeline and return results.

        Returns:
            A dictionary with keys ``status``, ``result``, ``elapsed_seconds``,
            and ``error`` (populated only when the pipeline fails).
        """
        logger.info("crew_run_started", crew="KalshiCrew")
        start = time.monotonic()

        try:
            result = self._crew.kickoff()
            elapsed = round(time.monotonic() - start, 2)

            logger.info(
                "crew_run_completed",
                crew="KalshiCrew",
                elapsed_seconds=elapsed,
            )

            return {
                "status": "success",
                "crew": "KalshiCrew",
                "result": result,
                "elapsed_seconds": elapsed,
                "error": None,
            }

        except Exception as exc:
            elapsed = round(time.monotonic() - start, 2)
            logger.error(
                "crew_run_failed",
                crew="KalshiCrew",
                elapsed_seconds=elapsed,
                error=str(exc),
            )

            return {
                "status": "failure",
                "crew": "KalshiCrew",
                "result": None,
                "elapsed_seconds": elapsed,
                "error": str(exc),
            }
