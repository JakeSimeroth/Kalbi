"""
KALBI-2 News Scraper Tools.

CrewAI tool functions for multi-source news aggregation.
Searches NewsAPI, parses financial RSS feeds (Reuters, Bloomberg, CNBC),
and scrapes Reddit posts for market sentiment signals.
"""

import json
from datetime import datetime, timedelta, timezone

import feedparser
import requests
import structlog
from bs4 import BeautifulSoup
from crewai.tools import tool

from src.config import Settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_settings: Settings | None = None


def _get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# Pre-defined financial RSS feeds keyed by topic
RSS_FEEDS = {
    "markets": [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://feeds.reuters.com/reuters/topNews",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",  # Top News
        "https://www.cnbc.com/id/10001147/device/rss/rss.html",   # Market News
    ],
    "economics": [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://www.cnbc.com/id/20910258/device/rss/rss.html",   # Economy
    ],
    "politics": [
        "https://feeds.reuters.com/Reuters/PoliticsNews",
        "https://www.cnbc.com/id/10000113/device/rss/rss.html",   # Politics
    ],
    "technology": [
        "https://feeds.reuters.com/reuters/technologyNews",
        "https://www.cnbc.com/id/19854910/device/rss/rss.html",   # Technology
    ],
}


# ---------------------------------------------------------------------------
# CrewAI Tools
# ---------------------------------------------------------------------------


@tool
def search_news(query: str, max_results: int = 10) -> str:
    """Search for recent news articles using NewsAPI.

    Args:
        query: Search keywords (e.g. 'Federal Reserve interest rates').
        max_results: Maximum number of articles to return (default 10).

    Returns:
        JSON string containing a list of articles with title, source,
        description, published date, and URL.
    """
    try:
        logger.info("news.search_news", query=query, max_results=max_results)
        settings = _get_settings()

        if not settings.newsapi_key:
            return json.dumps(
                {"error": "NEWSAPI_KEY not configured in environment"}
            )

        from_date = (
            datetime.now(timezone.utc) - timedelta(days=7)
        ).strftime("%Y-%m-%d")

        response = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "from": from_date,
                "sortBy": "relevancy",
                "pageSize": max_results,
                "language": "en",
                "apiKey": settings.newsapi_key,
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        articles = []
        for a in data.get("articles", [])[:max_results]:
            articles.append(
                {
                    "title": a.get("title"),
                    "source": a.get("source", {}).get("name"),
                    "description": a.get("description"),
                    "published_at": a.get("publishedAt"),
                    "url": a.get("url"),
                    "content_snippet": (a.get("content") or "")[:500],
                }
            )

        logger.info("news.search_news.done", articles_found=len(articles))
        return json.dumps(articles, indent=2)

    except Exception as e:
        logger.error("news.search_news.error", error=str(e))
        return json.dumps({"error": str(e)})


@tool
def scrape_rss_feeds(topic: str = "markets") -> str:
    """Parse financial RSS feeds for the latest headlines.

    Args:
        topic: Feed topic to scrape. One of 'markets', 'economics',
               'politics', 'technology'. Default 'markets'.

    Returns:
        JSON string with a list of feed items containing title, source,
        summary, published date, and link.
    """
    try:
        logger.info("news.scrape_rss_feeds", topic=topic)
        feed_urls = RSS_FEEDS.get(topic, RSS_FEEDS["markets"])

        all_items = []
        for url in feed_urls:
            try:
                feed = feedparser.parse(url)
                source_name = feed.feed.get("title", url)
                for entry in feed.entries[:15]:
                    # Clean HTML from summary
                    raw_summary = entry.get("summary", "")
                    if raw_summary:
                        soup = BeautifulSoup(raw_summary, "html.parser")
                        clean_summary = soup.get_text(strip=True)[:500]
                    else:
                        clean_summary = ""

                    all_items.append(
                        {
                            "title": entry.get("title", ""),
                            "source": source_name,
                            "summary": clean_summary,
                            "published": entry.get("published", ""),
                            "link": entry.get("link", ""),
                        }
                    )
            except Exception as feed_err:
                logger.warning(
                    "news.scrape_rss_feeds.feed_error",
                    url=url,
                    error=str(feed_err),
                )

        # Sort by published date descending (best effort)
        all_items.sort(key=lambda x: x.get("published", ""), reverse=True)

        logger.info("news.scrape_rss_feeds.done", item_count=len(all_items))
        return json.dumps(all_items[:30], indent=2)

    except Exception as e:
        logger.error("news.scrape_rss_feeds.error", error=str(e))
        return json.dumps({"error": str(e)})


@tool
def search_reddit(
    subreddit: str = "wallstreetbets", query: str = "", limit: int = 10
) -> str:
    """Search Reddit posts for market sentiment and discussion.

    Args:
        subreddit: Subreddit to search (default 'wallstreetbets').
        query: Optional search query within the subreddit.
        limit: Maximum number of posts to return (default 10).

    Returns:
        JSON string with a list of posts containing title, selftext,
        score, comment count, author, created date, and permalink.
    """
    try:
        logger.info(
            "news.search_reddit",
            subreddit=subreddit,
            query=query,
            limit=limit,
        )

        headers = {"User-Agent": "KALBI-2 Trading Bot/1.0"}
        settings = _get_settings()

        # Use OAuth if credentials are available, else public JSON API
        if settings.reddit_client_id and settings.reddit_client_secret:
            auth = requests.auth.HTTPBasicAuth(
                settings.reddit_client_id, settings.reddit_client_secret
            )
            token_resp = requests.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=auth,
                data={"grant_type": "client_credentials"},
                headers=headers,
                timeout=10,
            )
            token_resp.raise_for_status()
            token = token_resp.json().get("access_token")
            headers["Authorization"] = f"Bearer {token}"
            base_url = "https://oauth.reddit.com"
        else:
            base_url = "https://www.reddit.com"

        if query:
            url = f"{base_url}/r/{subreddit}/search.json"
            params = {
                "q": query,
                "restrict_sr": "on",
                "sort": "relevance",
                "t": "week",
                "limit": limit,
            }
        else:
            url = f"{base_url}/r/{subreddit}/hot.json"
            params = {"limit": limit}

        response = requests.get(
            url, headers=headers, params=params, timeout=15
        )
        response.raise_for_status()
        data = response.json()

        posts = []
        for child in data.get("data", {}).get("children", [])[:limit]:
            post = child.get("data", {})
            posts.append(
                {
                    "title": post.get("title"),
                    "selftext": (post.get("selftext") or "")[:500],
                    "score": post.get("score"),
                    "num_comments": post.get("num_comments"),
                    "author": post.get("author"),
                    "created_utc": post.get("created_utc"),
                    "permalink": f"https://reddit.com{post.get('permalink', '')}",
                    "url": post.get("url"),
                    "upvote_ratio": post.get("upvote_ratio"),
                }
            )

        logger.info("news.search_reddit.done", post_count=len(posts))
        return json.dumps(posts, indent=2)

    except Exception as e:
        logger.error("news.search_reddit.error", error=str(e))
        return json.dumps({"error": str(e)})
