"""
KALBI-2 Weighted Ensemble Strategy.

Combines multiple signal sources -- fundamental analysis, momentum,
mean reversion, volume, and time decay -- into a single unified
probability using a configurable weighted average.  This is the
cleaned-up successor to ``module_3_strategy_handler.py`` and serves
as the central decision-fusion layer in the KALBI-2 pipeline.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import structlog

log = structlog.get_logger(__name__)

# Default signal weights derived from academic research on prediction
# markets and technical analysis effectiveness.
_DEFAULT_WEIGHTS: dict[str, float] = {
    "fundamental": 0.40,
    "momentum": 0.25,
    "mean_reversion": 0.15,
    "volume": 0.10,
    "time_decay": 0.10,
}


class EnsembleStrategy:
    """Weighted ensemble that fuses heterogeneous trading signals.

    Each input signal is expected to be a dictionary with at least a
    ``source`` key (identifying which weight to apply) and a ``value``
    key (the signal's probability or normalised strength in [0, 1]).

    Optional per-signal keys:
        - ``confidence`` (*float*, 0-1) -- upstream model's confidence
          in this signal.  Used by :meth:`calculate_confidence` to
          measure agreement.
        - ``weight_override`` (*float*) -- if provided, overrides the
          default weight for this signal.

    Args:
        weights: Mapping of signal source names to their weights.
            Weights do not need to sum to 1 -- they will be normalised
            internally.  If ``None``, the default academic-research-based
            weights are used.
    """

    def __init__(self, weights: Optional[dict[str, float]] = None) -> None:
        self.weights: dict[str, float] = dict(weights or _DEFAULT_WEIGHTS)
        log.info("ensemble_strategy.initialized", weights=self.weights)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def combine_signals(self, signals: list[dict]) -> dict:
        """Produce a single fused signal from multiple sources.

        The combination follows these steps:

        1. Map each signal to its configured weight (or a per-signal
           override).
        2. Compute the weighted average of signal values.
        3. Apply a Kelly-inspired confidence adjustment to temper
           overconfidence.
        4. Clamp the result to [0.05, 0.95] -- never fully certain.

        Args:
            signals: List of signal dictionaries.  Each must contain
                ``source`` (str) and ``value`` (float, 0-1).

        Returns:
            A dictionary with:
            - **combined_value** (*float*) -- the fused probability.
            - **confidence** (*float*) -- agreement-based confidence.
            - **signal_count** (*int*) -- number of signals that
              contributed.
            - **components** (*list[dict]*) -- per-signal breakdown.
        """
        if not signals:
            log.warning("ensemble_strategy.no_signals")
            return {
                "combined_value": 0.5,
                "confidence": 0.0,
                "signal_count": 0,
                "components": [],
            }

        try:
            weighted_sum: float = 0.0
            total_weight: float = 0.0
            components: list[dict] = []

            for sig in signals:
                source: str = sig.get("source", "unknown")
                value: float = sig.get("value", 0.5)
                weight: float = sig.get(
                    "weight_override", self.weights.get(source, 0.0)
                )

                if weight <= 0:
                    log.debug(
                        "ensemble_strategy.skipping_zero_weight",
                        source=source,
                    )
                    continue

                weighted_sum += value * weight
                total_weight += weight
                components.append(
                    {"source": source, "value": value, "weight": weight}
                )

            # Normalise by total weight to produce a proper average.
            if total_weight > 0:
                raw_combined = weighted_sum / total_weight
            else:
                raw_combined = 0.5

            # Kelly-inspired adjustment: pull toward 0.5 proportional
            # to our confidence (reduces extreme predictions).
            confidence = self.calculate_confidence(signals)
            adjusted = self._kelly_adjustment(raw_combined, confidence)

            result = {
                "combined_value": round(adjusted, 4),
                "confidence": round(confidence, 4),
                "signal_count": len(components),
                "components": components,
            }

            log.info(
                "ensemble_strategy.combined",
                combined_value=result["combined_value"],
                confidence=result["confidence"],
                signal_count=result["signal_count"],
            )
            return result

        except Exception:
            log.exception("ensemble_strategy.combine_failed")
            return {
                "combined_value": 0.5,
                "confidence": 0.0,
                "signal_count": 0,
                "components": [],
            }

    def calculate_confidence(self, signals: list[dict]) -> float:
        """Measure agreement across signals to derive a confidence score.

        Confidence is high when all signals point in the same direction
        (all bullish or all bearish) and low when signals disagree.

        The metric is ``1 - normalised_std_dev`` of signal values,
        weighted by each signal's weight.  Perfect agreement yields
        confidence ~1.0; maximum disagreement yields ~0.0.

        A secondary factor is the average per-signal ``confidence`` key,
        if present.  The final score blends directional agreement (70%)
        with upstream model confidence (30%).

        Args:
            signals: List of signal dictionaries with ``source``,
                ``value``, and optionally ``confidence``.

        Returns:
            A float in [0, 1] representing ensemble-level confidence.
        """
        if len(signals) < 2:
            # With fewer than 2 signals there is nothing to compare.
            if signals:
                return signals[0].get("confidence", 0.5)
            return 0.0

        try:
            values: list[float] = []
            weights_list: list[float] = []
            upstream_confidences: list[float] = []

            for sig in signals:
                source = sig.get("source", "unknown")
                value = sig.get("value", 0.5)
                weight = sig.get(
                    "weight_override", self.weights.get(source, 0.0)
                )
                if weight <= 0:
                    continue

                values.append(value)
                weights_list.append(weight)
                upstream_confidences.append(sig.get("confidence", 0.5))

            if not values:
                return 0.0

            arr = np.array(values)
            w = np.array(weights_list)
            w_norm = w / w.sum()

            # Weighted standard deviation of signal values.
            weighted_mean = np.average(arr, weights=w_norm)
            weighted_var = np.average(
                (arr - weighted_mean) ** 2, weights=w_norm
            )
            weighted_std = float(np.sqrt(weighted_var))

            # Max possible std for values in [0,1] is 0.5; normalise.
            agreement = 1.0 - min(weighted_std / 0.5, 1.0)

            # Average upstream confidence.
            avg_upstream = float(np.mean(upstream_confidences))

            # Blend: 70% agreement, 30% upstream confidence.
            return round(0.7 * agreement + 0.3 * avg_upstream, 4)

        except Exception:
            log.exception("ensemble_strategy.confidence_calculation_failed")
            return 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _kelly_adjustment(
        prob: float, confidence: float = 0.7
    ) -> float:
        """Apply a Kelly Criterion-inspired dampening to extreme probabilities.

        Pulls the probability toward 0.5 proportional to ``(1 - confidence)``.
        At ``confidence = 1.0`` the probability is unchanged; at
        ``confidence = 0.0`` it collapses to 0.5 (total uncertainty).

        The result is clamped to [0.05, 0.95] to prevent the system from
        ever expressing absolute certainty.

        Args:
            prob: Raw fused probability (0 to 1).
            confidence: Ensemble confidence (0 to 1).

        Returns:
            Adjusted probability.
        """
        adjusted = 0.5 + (prob - 0.5) * confidence
        return float(np.clip(adjusted, 0.05, 0.95))
