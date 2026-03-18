"""
KALBI-2 Equities Trading Crew.

Orchestrates the full pipeline for equity market analysis and trading:
news catalyst identification, fundamental filtering, quantitative signal
generation, risk review, and order execution via Alpaca.
Designed to run every 30 minutes during market hours.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import structlog
from crewai import Crew, Process, Task

from src.agents import (
    create_executor,
    create_fundamentals_analyst,
    create_news_analyst,
    create_quant_analyst,
    create_risk_manager,
)

logger = structlog.get_logger(__name__)


class EquitiesCrew:
    """Runs every 30 minutes during market hours.

    The crew follows a strict sequential pipeline:

    1. **News Analyst** -- identifies sector and ticker catalysts.
    2. **Fundamentals Analyst** -- filters to quality names with solid
       financials.
    3. **Quant Analyst** -- generates technical/statistical signals on the
       filtered universe.
    4. **Risk Manager** -- reviews portfolio impact and enforces limits.
    5. **Executor** -- places orders via Alpaca.
    """

    def __init__(self, llm: Optional[Any] = None) -> None:
        self._llm = llm

        # -- Agents ----------------------------------------------------------
        self._news_analyst = create_news_analyst(llm=llm)
        self._fundamentals_analyst = create_fundamentals_analyst(llm=llm)
        self._quant_analyst = create_quant_analyst(llm=llm)
        self._risk_manager = create_risk_manager(llm=llm)
        self._executor = create_executor(llm=llm)

        # -- Tasks -----------------------------------------------------------
        self._task_news_catalysts = Task(
            description=(
                "Identify sector and ticker-level catalysts from current news "
                "flow. Focus on earnings surprises, macro data releases, "
                "sector rotation signals, and breaking corporate events. "
                "Return a structured list of tickers with catalyst summaries "
                "and sentiment scores."
            ),
            expected_output=(
                "JSON object with a 'catalysts' list. Each entry contains: "
                "'ticker', 'sector', 'headline', 'catalyst_type' "
                "('earnings'/'macro'/'corporate'/'sector_rotation'), "
                "'sentiment_score' (-1 to 1), 'urgency' ('high'/'medium'/'low'), "
                "and 'summary'."
            ),
            agent=self._news_analyst,
        )

        self._task_fundamental_filter = Task(
            description=(
                "Filter the catalyst-driven ticker list to quality names only. "
                "Evaluate each company's earnings quality, cash flow "
                "sustainability, balance sheet strength, and macro positioning. "
                "Reject names with deteriorating fundamentals, excessive "
                "leverage, or accounting red flags. Return the filtered "
                "universe with fundamental scores."
            ),
            expected_output=(
                "JSON object with a 'filtered_universe' list. Each entry "
                "contains: 'ticker', 'company_name', 'fundamental_score' "
                "(0-100), 'earnings_quality' ('strong'/'moderate'/'weak'), "
                "'cash_flow_positive' (bool), 'debt_to_equity', "
                "'catalyst_alignment' (how well fundamentals support the "
                "catalyst), and 'reasoning'."
            ),
            agent=self._fundamentals_analyst,
            context=[self._task_news_catalysts],
        )

        self._task_quant_signals = Task(
            description=(
                "Generate quantitative trading signals for the fundamentally "
                "filtered universe. Apply momentum, mean-reversion, and "
                "statistical indicators. Score each ticker for entry timing, "
                "expected move magnitude, and signal confidence. Return "
                "structured trade recommendations with entry/exit levels."
            ),
            expected_output=(
                "JSON object with a 'signals' list. Each entry contains: "
                "'ticker', 'direction' ('long'/'short'), 'entry_price', "
                "'stop_loss', 'take_profit', 'signal_strength' (0-1), "
                "'indicators_used' (list of indicator names), "
                "'expected_holding_period' (hours), and 'reasoning'."
            ),
            agent=self._quant_analyst,
            context=[self._task_fundamental_filter],
        )

        self._task_risk_review = Task(
            description=(
                "Review each proposed equity trade for portfolio-level risk "
                "compliance. Check position sizing against the 2% per-trade "
                "limit, portfolio concentration against the 10% per-ticker "
                "limit, total deployment against the 50% cap, and correlation "
                "against the 0.7 threshold. Evaluate impact on overall "
                "portfolio Greeks and sector exposure. Approve or reject each "
                "trade with specific reasoning and adjusted sizing."
            ),
            expected_output=(
                "JSON object with a 'trades' list. Each entry contains: "
                "'ticker', 'status' ('approved'/'rejected'), 'direction', "
                "'original_quantity', 'approved_quantity', 'position_pct', "
                "'portfolio_impact', 'rejection_reason' (null if approved), "
                "and 'risk_notes'."
            ),
            agent=self._risk_manager,
            context=[self._task_quant_signals],
        )

        self._task_execute = Task(
            description=(
                "Execute all approved equity trades via Alpaca using limit "
                "orders. Use the entry prices from the quant signals as limit "
                "prices. Attach stop-loss and take-profit orders where "
                "applicable. Log every order attempt with full details. "
                "Report fill status for each trade."
            ),
            expected_output=(
                "JSON object with an 'executions' list. Each entry contains: "
                "'ticker', 'order_id', 'side' ('buy'/'sell'), 'order_type', "
                "'limit_price', 'quantity', 'status' "
                "('filled'/'partial'/'pending'/'failed'), 'filled_price', "
                "'stop_loss_order_id', 'take_profit_order_id', and 'error' "
                "(null if successful)."
            ),
            agent=self._executor,
            context=[self._task_risk_review],
        )

        # -- Crew ------------------------------------------------------------
        self._crew = Crew(
            agents=[
                self._news_analyst,
                self._fundamentals_analyst,
                self._quant_analyst,
                self._risk_manager,
                self._executor,
            ],
            tasks=[
                self._task_news_catalysts,
                self._task_fundamental_filter,
                self._task_quant_signals,
                self._task_risk_review,
                self._task_execute,
            ],
            process=Process.sequential,
            verbose=True,
        )

        logger.info(
            "crew_initialized",
            crew="EquitiesCrew",
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
        logger.info("crew_run_started", crew="EquitiesCrew")
        start = time.monotonic()

        try:
            result = self._crew.kickoff()
            elapsed = round(time.monotonic() - start, 2)

            logger.info(
                "crew_run_completed",
                crew="EquitiesCrew",
                elapsed_seconds=elapsed,
            )

            return {
                "status": "success",
                "crew": "EquitiesCrew",
                "result": result,
                "elapsed_seconds": elapsed,
                "error": None,
            }

        except Exception as exc:
            elapsed = round(time.monotonic() - start, 2)
            logger.error(
                "crew_run_failed",
                crew="EquitiesCrew",
                elapsed_seconds=elapsed,
                error=str(exc),
            )

            return {
                "status": "failure",
                "crew": "EquitiesCrew",
                "result": None,
                "elapsed_seconds": elapsed,
                "error": str(exc),
            }
