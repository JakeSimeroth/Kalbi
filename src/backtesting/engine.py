"""
KALBI-2 Event-Driven Backtest Engine.

Simulates strategy execution over historical OHLCV data with realistic
commission modelling and a simple slippage model.  The engine iterates
bar-by-bar, asks the strategy for a signal, executes simulated trades,
and records the resulting equity curve.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Protocol

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# Strategy protocol -- any object with a ``generate_signal`` method
# ------------------------------------------------------------------

class StrategyProtocol(Protocol):
    """Minimal interface that a strategy must satisfy to work with the
    :class:`BacktestEngine`.

    The ``generate_signal`` method receives the current OHLCV bar and the
    full history up to (and including) that bar, and returns a signal
    dictionary.
    """

    def generate_signal(
        self, current_bar: pd.Series, history: pd.DataFrame
    ) -> dict:
        """Return a signal dict.

        Expected keys in the returned dictionary:
            - ``action`` (*str*): One of ``"buy"``, ``"sell"``, or
              ``"hold"``.
            - ``quantity`` (*float*, optional): Number of units.
              Defaults to ``1.0`` if omitted.
            - ``price`` (*float*, optional): Limit price.  If omitted the
              engine uses the bar's close price.
        """
        ...  # pragma: no cover


class BacktestEngine:
    """Event-driven backtest engine for KALBI-2.

    Args:
        initial_capital: Starting cash balance in dollars.
        commission_pct: Round-trip commission as a fraction of trade
            notional (e.g. ``0.001`` = 0.1 %).
        slippage_pct: Simulated slippage as a fraction of the execution
            price (e.g. ``0.0005`` = 0.05 %).
    """

    def __init__(
        self,
        initial_capital: float = 10_000.0,
        commission_pct: float = 0.001,
        slippage_pct: float = 0.0005,
    ) -> None:
        self.initial_capital = initial_capital
        self.commission_pct = commission_pct
        self.slippage_pct = slippage_pct

        # State that is reset between runs.
        self.cash: float = initial_capital
        self.position: float = 0.0
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []

        log.info(
            "backtest_engine.initialized",
            initial_capital=initial_capital,
            commission_pct=commission_pct,
            slippage_pct=slippage_pct,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, strategy: Any, data: pd.DataFrame) -> dict:
        """Run a backtest over *data* using *strategy*.

        The engine iterates through each row of *data* (assumed to be
        sorted by time in ascending order).  For every bar it:

        1. Updates the portfolio equity with the current price.
        2. Asks the strategy for a signal via ``generate_signal``.
        3. Executes a simulated trade if the signal is actionable.
        4. Records the equity snapshot.

        Args:
            strategy: An object satisfying :class:`StrategyProtocol`.
            data: A ``pandas.DataFrame`` with at least ``close`` and an
                index that can serve as a timestamp (``DatetimeIndex`` or
                a ``timestamp`` / ``date`` column).

        Returns:
            A dictionary containing ``trades``, ``equity_curve``,
            ``initial_capital``, and ``final_equity``.
        """
        self._reset()
        data = data.copy()

        if "close" not in data.columns:
            raise ValueError(
                "Data must contain a 'close' column."
            )

        log.info(
            "backtest_engine.run_started",
            bars=len(data),
            start=str(data.index[0]),
            end=str(data.index[-1]),
        )

        for i in range(len(data)):
            current_bar = data.iloc[i]
            history = data.iloc[: i + 1]
            current_price = float(current_bar["close"])
            timestamp = data.index[i]

            # 1. Update equity curve
            self._update_equity(current_price, timestamp)

            # 2. Generate signal
            try:
                signal = strategy.generate_signal(current_bar, history)
            except Exception:
                log.exception(
                    "backtest_engine.strategy_error",
                    bar_index=i,
                )
                continue

            # 3. Execute trade if actionable
            action = signal.get("action", "hold")
            if action in ("buy", "sell"):
                trade = self._execute_trade(signal, current_price, timestamp)
                if trade is not None:
                    self.trades.append(trade)

        # Final equity snapshot
        if len(data) > 0:
            final_price = float(data.iloc[-1]["close"])
            self._update_equity(final_price, data.index[-1])

        results = self.get_results()
        log.info(
            "backtest_engine.run_completed",
            total_trades=len(self.trades),
            final_equity=results["final_equity"],
        )
        return results

    def get_results(self) -> dict:
        """Return the full backtest results as a dictionary.

        Returns:
            Dictionary with keys:
            - ``initial_capital`` (*float*)
            - ``final_equity`` (*float*)
            - ``trades`` (*list[dict]*)
            - ``equity_curve`` (*list[dict]*)
        """
        final_equity = self.initial_capital
        if self.equity_curve:
            final_equity = self.equity_curve[-1]["equity"]

        return {
            "initial_capital": self.initial_capital,
            "final_equity": final_equity,
            "trades": list(self.trades),
            "equity_curve": list(self.equity_curve),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _reset(self) -> None:
        """Reset engine state for a fresh run."""
        self.cash = self.initial_capital
        self.position = 0.0
        self.trades = []
        self.equity_curve = []

    def _execute_trade(
        self,
        signal: dict,
        current_price: float,
        timestamp: Any,
    ) -> Optional[dict]:
        """Simulate a trade execution with slippage and commission.

        Args:
            signal: Signal dictionary with ``action``, optional
                ``quantity``, and optional ``price``.
            current_price: The bar's close price (used when signal does
                not specify a price).
            timestamp: Timestamp of the current bar.

        Returns:
            A trade record dictionary, or ``None`` if the trade could not
            be executed (e.g. insufficient cash for a buy).
        """
        action = signal["action"]
        quantity = float(signal.get("quantity", 1.0))
        base_price = float(signal.get("price", current_price))

        # Apply slippage
        if action == "buy":
            exec_price = base_price * (1.0 + self.slippage_pct)
        else:  # sell
            exec_price = base_price * (1.0 - self.slippage_pct)

        notional = exec_price * quantity
        commission = notional * self.commission_pct

        if action == "buy":
            total_cost = notional + commission
            if total_cost > self.cash:
                log.debug(
                    "backtest_engine.insufficient_cash",
                    required=total_cost,
                    available=self.cash,
                )
                return None
            self.cash -= total_cost
            self.position += quantity
        else:  # sell
            if quantity > self.position:
                quantity = self.position  # can only sell what we hold
                if quantity <= 0:
                    return None
                notional = exec_price * quantity
                commission = notional * self.commission_pct
            self.cash += notional - commission
            self.position -= quantity

        trade_record = {
            "timestamp": timestamp,
            "action": action,
            "quantity": quantity,
            "price": exec_price,
            "commission": commission,
            "notional": notional,
            "cash_after": self.cash,
            "position_after": self.position,
        }

        log.debug(
            "backtest_engine.trade_executed",
            action=action,
            qty=quantity,
            price=exec_price,
            commission=commission,
        )
        return trade_record

    def _update_equity(self, current_price: float, timestamp: Any) -> None:
        """Compute and record the current portfolio equity.

        Equity = cash + (position * current_price).

        Args:
            current_price: The latest market price.
            timestamp: Timestamp label for the equity snapshot.
        """
        equity = self.cash + self.position * current_price
        self.equity_curve.append(
            {
                "timestamp": timestamp,
                "equity": equity,
                "cash": self.cash,
                "position": self.position,
                "price": current_price,
            }
        )
