"""
KALBI-2 Kalshi Event-Driven Arbitrage Strategy.

Identifies mispriced event contracts on Kalshi by comparing an internally
estimated probability (from the fundamental forecaster and ensemble) against
the current market price.  When the estimated probability diverges from the
market price by more than a configurable edge threshold, the strategy emits
a buy_yes or buy_no signal.
"""

from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)


class KalshiEventArbStrategy:
    """Event-driven strategy that exploits probability mispricings on Kalshi.

    The core logic is straightforward: if our estimated probability for an
    event is significantly higher than the market-implied probability (the
    Yes price), we buy Yes contracts.  If our estimate is significantly
    *lower*, we buy No contracts (equivalently, sell Yes).  The minimum
    edge and confidence thresholds prevent the strategy from acting on
    noise.

    Args:
        min_edge: Minimum absolute probability edge required to act
            (default ``0.08``, i.e. 8 cents on a $1 contract).
        min_confidence: Minimum confidence score from the upstream model
            required before the strategy will emit a non-pass signal
            (default ``0.6``).
    """

    def __init__(
        self,
        min_edge: float = 0.08,
        min_confidence: float = 0.6,
    ) -> None:
        self.min_edge = min_edge
        self.min_confidence = min_confidence
        log.info(
            "kalshi_event_arb_strategy.initialized",
            min_edge=self.min_edge,
            min_confidence=self.min_confidence,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        market_data: dict,
        news_sentiment: dict,
        estimated_probability: float,
    ) -> dict:
        """Evaluate a Kalshi market and return a trading signal.

        Args:
            market_data: Dictionary containing at least ``market_id`` and
                ``yes_price`` (the current market-implied probability for
                the Yes outcome, expressed as a float between 0 and 1).
            news_sentiment: Dictionary with sentiment information from the
                news analysis pipeline.  Expected keys include
                ``sentiment_score`` (float, -1 to 1) and ``confidence``
                (float, 0 to 1).
            estimated_probability: The fundamental forecaster's estimated
                probability that the event resolves Yes (0 to 1).

        Returns:
            A signal dictionary with the following keys:

            - **market_id** (*str*): The Kalshi market identifier.
            - **action** (*str*): One of ``"buy_yes"``, ``"buy_no"``, or
              ``"pass"``.
            - **edge** (*float*): The absolute probability edge detected.
            - **confidence** (*float*): Composite confidence in the signal.
            - **reasoning** (*str*): Human-readable explanation of the
              decision.
        """
        market_id: str = market_data.get("market_id", "unknown")
        yes_price: float = market_data.get("yes_price", 0.5)

        try:
            edge = self.calculate_edge(estimated_probability, yes_price)
            sentiment_score: float = news_sentiment.get("sentiment_score", 0.0)
            sentiment_confidence: float = news_sentiment.get("confidence", 0.5)

            # Composite confidence blends the upstream model confidence with
            # the news sentiment confidence.
            composite_confidence = self._composite_confidence(
                estimated_probability, sentiment_confidence
            )

            # ----------------------------------------------------------
            # Decision logic
            # ----------------------------------------------------------
            if composite_confidence < self.min_confidence:
                action = "pass"
                reasoning = (
                    f"Confidence {composite_confidence:.2f} below threshold "
                    f"{self.min_confidence:.2f}; passing."
                )
            elif edge >= self.min_edge:
                # Our estimate is *higher* than the market -- buy Yes.
                action = "buy_yes"
                reasoning = (
                    f"Estimated prob {estimated_probability:.2f} vs market "
                    f"{yes_price:.2f} => +{edge:.2f} edge. "
                    f"Sentiment score {sentiment_score:+.2f} supports long Yes."
                )
            elif edge <= -self.min_edge:
                # Our estimate is *lower* than the market -- buy No.
                action = "buy_no"
                reasoning = (
                    f"Estimated prob {estimated_probability:.2f} vs market "
                    f"{yes_price:.2f} => {edge:.2f} edge. "
                    f"Sentiment score {sentiment_score:+.2f} supports long No."
                )
            else:
                action = "pass"
                reasoning = (
                    f"Edge {edge:+.2f} within dead-zone "
                    f"(+/-{self.min_edge:.2f}); no actionable signal."
                )

            signal = {
                "market_id": market_id,
                "action": action,
                "edge": edge,
                "confidence": composite_confidence,
                "reasoning": reasoning,
            }

            log.info(
                "kalshi_event_arb_strategy.signal",
                market_id=market_id,
                action=action,
                edge=round(edge, 4),
                confidence=round(composite_confidence, 4),
            )
            return signal

        except Exception:
            log.exception(
                "kalshi_event_arb_strategy.evaluate_failed",
                market_id=market_id,
            )
            return {
                "market_id": market_id,
                "action": "pass",
                "edge": 0.0,
                "confidence": 0.0,
                "reasoning": "Evaluation failed due to an internal error.",
            }

    def calculate_edge(
        self, estimated_prob: float, market_price: float
    ) -> float:
        """Calculate the probability edge.

        Positive edge means our estimate is higher than the market price
        (bullish on Yes); negative edge means lower (bullish on No).

        Args:
            estimated_prob: Our model's estimated probability (0 to 1).
            market_price: The current Kalshi Yes price (0 to 1).

        Returns:
            The signed edge as a float.
        """
        return estimated_prob - market_price

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _composite_confidence(
        estimated_prob: float,
        sentiment_confidence: float,
    ) -> float:
        """Blend model probability certainty with sentiment confidence.

        Certainty is measured as the absolute distance of the probability
        from 0.5 (maximum uncertainty).  A probability of 0.9 yields
        certainty 0.8; a probability of 0.55 yields certainty 0.1.

        The composite confidence is a weighted average of this certainty
        metric and the sentiment confidence.

        Args:
            estimated_prob: Model probability (0 to 1).
            sentiment_confidence: News sentiment confidence (0 to 1).

        Returns:
            Composite confidence score (0 to 1).
        """
        certainty = abs(estimated_prob - 0.5) * 2.0  # scale to 0-1
        return 0.6 * certainty + 0.4 * sentiment_confidence
