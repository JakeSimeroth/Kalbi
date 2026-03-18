"""
KALBI-2 Sentiment Analyzer Tool.

CrewAI tool function that uses Anthropic Claude to perform nuanced
sentiment analysis on financial text.  Returns a structured JSON
score with reasoning and key phrase extraction.
"""

import json

import anthropic
import structlog
from crewai.tools import tool

from src.config import Settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_settings: Settings | None = None
_client: anthropic.Anthropic | None = None


def _get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def _get_client() -> anthropic.Anthropic:
    """Lazy-initialise the Anthropic client."""
    global _client
    if _client is None:
        settings = _get_settings()
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


SENTIMENT_SYSTEM_PROMPT = """\
You are a financial sentiment analysis engine. Analyze the provided text
and return ONLY a JSON object with the following fields:

{
  "sentiment_score": <float from -1.0 (extremely bearish) to 1.0 (extremely bullish)>,
  "confidence": <float from 0.0 to 1.0 indicating your confidence in the score>,
  "sentiment_label": "<one of: very_bearish, bearish, slightly_bearish, neutral, slightly_bullish, bullish, very_bullish>",
  "key_phrases": ["<list of 3-5 key phrases from the text that drove the sentiment>"],
  "reasoning": "<1-2 sentence explanation of the sentiment assessment>"
}

Guidelines:
- Focus on market-moving implications, not just tone
- Consider forward-looking statements more heavily
- Distinguish between company-specific vs. macro sentiment
- Score should reflect actionable trading sentiment, not general mood
- Return ONLY valid JSON, no markdown formatting or extra text
"""


# ---------------------------------------------------------------------------
# CrewAI Tools
# ---------------------------------------------------------------------------


@tool
def analyze_sentiment(text: str) -> str:
    """Analyze the financial sentiment of a given text using Claude AI.

    Scores text on a scale from -1.0 (extremely bearish) to 1.0
    (extremely bullish) with confidence rating and key phrase extraction.

    Args:
        text: The text to analyze for financial sentiment. Can be a
              news headline, article excerpt, earnings call snippet,
              social media post, or any financial text.

    Returns:
        JSON string containing sentiment_score (-1 to 1), confidence
        (0 to 1), sentiment_label, key_phrases list, and reasoning.
    """
    try:
        logger.info(
            "sentiment.analyze",
            text_length=len(text),
            text_preview=text[:100],
        )

        if not text.strip():
            return json.dumps(
                {"error": "Empty text provided for sentiment analysis"}
            )

        # Truncate very long text to stay within token limits
        truncated = text[:4000]
        if len(text) > 4000:
            truncated += "\n\n[... text truncated for analysis ...]"

        client = _get_client()
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            system=SENTIMENT_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Analyze the financial sentiment of this text:\n\n{truncated}",
                }
            ],
        )

        # Extract the text response
        raw_response = response.content[0].text.strip()

        # Parse and validate the JSON response
        try:
            result = json.loads(raw_response)
        except json.JSONDecodeError:
            # Try to extract JSON from the response if wrapped in markdown
            import re

            json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = {
                    "error": "Failed to parse sentiment response",
                    "raw_response": raw_response[:500],
                }

        # Validate expected fields
        if "sentiment_score" in result:
            score = result["sentiment_score"]
            if not isinstance(score, (int, float)) or not (-1 <= score <= 1):
                result["warning"] = (
                    f"Score {score} outside expected range [-1, 1]"
                )

        logger.info(
            "sentiment.analyze.done",
            score=result.get("sentiment_score"),
            label=result.get("sentiment_label"),
        )
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error("sentiment.analyze.error", error=str(e))
        return json.dumps({"error": str(e)})
