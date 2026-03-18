"""
KALBI-2 Meta Overseer Crew.

High-level crew that monitors overall system performance, adjusts capital
allocation between sub-crews (Kalshi and Equities), reviews portfolio-wide
risk metrics, triggers rebalancing, and generates summary reports.
Designed to run every 2 hours.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import structlog
from crewai import Agent, Crew, Process, Task

from src.tools import alpaca_api_tools, kalshi_api_tools, market_data_tools

logger = structlog.get_logger(__name__)


class MetaCrew:
    """Runs every 2 hours. Oversees capital allocation and overall performance.

    Uses a single **Meta Strategist** agent that reviews all sub-crew
    results and makes portfolio-wide decisions.

    Pipeline:

    1. Review recent P&L of each sub-crew.
    2. Adjust capital allocation between Kalshi and Equities.
    3. Review overall portfolio risk metrics.
    4. Trigger rebalancing if needed.
    5. Generate summary report.
    """

    def __init__(self, llm: Optional[Any] = None) -> None:
        self._llm = llm

        # -- Meta Strategist agent (created inline) --------------------------
        meta_tools = [
            *market_data_tools,
            *alpaca_api_tools,
            *kalshi_api_tools,
        ]

        self._meta_strategist = Agent(
            role="Meta Strategist",
            goal=(
                "Oversee the entire KALBI-2 trading system. Optimise capital "
                "allocation across sub-strategies, monitor aggregate risk, "
                "and ensure the system remains profitable and within all "
                "risk constraints."
            ),
            backstory=(
                "Former multi-strategy hedge fund portfolio manager. Thinks "
                "in terms of Sharpe ratios, drawdown curves, and capital "
                "efficiency. Understands that the best trade is sometimes no "
                "trade. Responsible for the system's survival above all else. "
                "Reviews each sub-crew's performance with cold objectivity "
                "and reallocates capital based on risk-adjusted returns."
            ),
            tools=meta_tools,
            verbose=True,
            allow_delegation=False,
            llm=llm,
        )

        logger.info(
            "agent_created",
            agent_role=self._meta_strategist.role,
            tool_count=len(meta_tools),
        )

        # -- Tasks -----------------------------------------------------------
        self._task_review_pnl = Task(
            description=(
                "Review the recent P&L of each sub-crew (Kalshi and Equities). "
                "Pull current positions, recent fills, and realized/unrealized "
                "P&L from both Kalshi and Alpaca. Calculate per-crew Sharpe "
                "ratio, win rate, average win/loss, and maximum drawdown over "
                "the last 24 hours and 7 days. Return a structured performance "
                "summary."
            ),
            expected_output=(
                "JSON object with 'kalshi_performance' and "
                "'equities_performance' keys. Each contains: 'realized_pnl', "
                "'unrealized_pnl', 'total_pnl', 'win_rate', 'avg_win', "
                "'avg_loss', 'sharpe_24h', 'sharpe_7d', 'max_drawdown', "
                "'open_positions_count', and 'capital_deployed'."
            ),
            agent=self._meta_strategist,
        )

        self._task_adjust_allocation = Task(
            description=(
                "Based on the P&L review, adjust the capital allocation "
                "between Kalshi and Equities sub-crews. Increase allocation "
                "to better-performing strategies (higher risk-adjusted returns) "
                "and decrease allocation to underperformers. Ensure no single "
                "strategy exceeds 70% of total capital. Consider current "
                "market regime (trending vs. mean-reverting) in the decision. "
                "Return the new allocation targets."
            ),
            expected_output=(
                "JSON object with: 'kalshi_allocation_pct', "
                "'equities_allocation_pct', 'cash_reserve_pct', "
                "'reasoning', 'previous_allocation' (dict), and "
                "'allocation_change' (dict showing delta)."
            ),
            agent=self._meta_strategist,
            context=[self._task_review_pnl],
        )

        self._task_risk_metrics = Task(
            description=(
                "Review overall portfolio risk metrics across all strategies. "
                "Check aggregate exposure, sector concentration, correlation "
                "between Kalshi and equity positions, daily drawdown status, "
                "and proximity to circuit-breaker thresholds. Flag any "
                "emerging risks that individual crews may not see."
            ),
            expected_output=(
                "JSON object with: 'total_portfolio_value', "
                "'total_deployed_pct', 'daily_pnl_pct', "
                "'distance_to_circuit_breaker_pct', 'sector_exposures' "
                "(dict), 'cross_strategy_correlation', "
                "'risk_flags' (list of warning strings), and "
                "'overall_risk_level' ('low'/'moderate'/'elevated'/'critical')."
            ),
            agent=self._meta_strategist,
            context=[self._task_review_pnl, self._task_adjust_allocation],
        )

        self._task_rebalance = Task(
            description=(
                "If the risk review or allocation adjustment requires it, "
                "generate specific rebalancing instructions. Identify "
                "positions to trim, close, or scale into. If the portfolio "
                "is within acceptable bounds, confirm no rebalancing is "
                "needed. All rebalancing must respect risk constraints."
            ),
            expected_output=(
                "JSON object with: 'rebalance_needed' (bool), "
                "'actions' (list of dicts, each with 'platform' "
                "('kalshi'/'alpaca'), 'ticker', 'action' "
                "('reduce'/'close'/'increase'), 'target_quantity', "
                "and 'reasoning'), and 'estimated_turnover_pct'."
            ),
            agent=self._meta_strategist,
            context=[self._task_risk_metrics],
        )

        self._task_summary_report = Task(
            description=(
                "Generate a concise executive summary report of the current "
                "system state. Include overall P&L, capital allocation, risk "
                "posture, any rebalancing actions taken, and a forward-looking "
                "view for the next cycle. This report should be suitable for "
                "logging and for human review via Telegram/Discord alerts."
            ),
            expected_output=(
                "JSON object with: 'report_timestamp', 'headline' (one-line "
                "summary), 'total_pnl_24h', 'total_pnl_7d', "
                "'current_allocation' (dict), 'risk_level', "
                "'rebalancing_summary', 'key_positions' (top 5 by size), "
                "'outlook' (brief forward view), and 'alerts' (list of "
                "actionable items for human review)."
            ),
            agent=self._meta_strategist,
            context=[
                self._task_review_pnl,
                self._task_adjust_allocation,
                self._task_risk_metrics,
                self._task_rebalance,
            ],
        )

        # -- Crew ------------------------------------------------------------
        self._crew = Crew(
            agents=[self._meta_strategist],
            tasks=[
                self._task_review_pnl,
                self._task_adjust_allocation,
                self._task_risk_metrics,
                self._task_rebalance,
                self._task_summary_report,
            ],
            process=Process.sequential,
            verbose=True,
        )

        logger.info(
            "crew_initialized",
            crew="MetaCrew",
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
        logger.info("crew_run_started", crew="MetaCrew")
        start = time.monotonic()

        try:
            result = self._crew.kickoff()
            elapsed = round(time.monotonic() - start, 2)

            logger.info(
                "crew_run_completed",
                crew="MetaCrew",
                elapsed_seconds=elapsed,
            )

            return {
                "status": "success",
                "crew": "MetaCrew",
                "result": result,
                "elapsed_seconds": elapsed,
                "error": None,
            }

        except Exception as exc:
            elapsed = round(time.monotonic() - start, 2)
            logger.error(
                "crew_run_failed",
                crew="MetaCrew",
                elapsed_seconds=elapsed,
                error=str(exc),
            )

            return {
                "status": "failure",
                "crew": "MetaCrew",
                "result": None,
                "elapsed_seconds": elapsed,
                "error": str(exc),
            }
