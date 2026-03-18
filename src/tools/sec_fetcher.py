"""
KALBI-2 SEC EDGAR Filing Tools.

CrewAI tool functions for fetching public company filings from the
SEC EDGAR API.  No API key required -- only a descriptive User-Agent
header per SEC guidelines.
"""

import json

import requests
import structlog
from crewai.tools import tool

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EDGAR_BASE = "https://efts.sec.gov/LATEST"
EDGAR_FULL_TEXT = "https://efts.sec.gov/LATEST/search-index"
EDGAR_FILINGS = "https://www.sec.gov/cgi-bin/browse-edgar"
EDGAR_SUBMISSIONS = "https://data.sec.gov/submissions"
EDGAR_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"

HEADERS = {
    "User-Agent": "KALBI-2 TradingSystem contact@kalbi-trading.dev",
    "Accept-Encoding": "gzip, deflate",
}

# Common ticker -> CIK mapping is fetched dynamically
_CIK_CACHE: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ticker_to_cik(ticker: str) -> str | None:
    """Resolve a stock ticker to a zero-padded 10-digit CIK via EDGAR."""
    ticker_upper = ticker.upper()
    if ticker_upper in _CIK_CACHE:
        return _CIK_CACHE[ticker_upper]

    try:
        resp = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        for entry in data.values():
            t = entry.get("ticker", "").upper()
            cik = str(entry.get("cik_str", "")).zfill(10)
            _CIK_CACHE[t] = cik
            if t == ticker_upper:
                return cik

    except Exception as e:
        logger.error("sec.ticker_to_cik.error", ticker=ticker, error=str(e))

    return None


# ---------------------------------------------------------------------------
# CrewAI Tools
# ---------------------------------------------------------------------------


@tool
def get_company_filings(
    ticker: str, filing_type: str = "10-K", limit: int = 5
) -> str:
    """Fetch recent SEC EDGAR filings for a company by ticker symbol.

    Args:
        ticker: Stock ticker symbol (e.g. 'AAPL', 'TSLA', 'MSFT').
        filing_type: SEC filing type to filter (e.g. '10-K', '10-Q',
                     '8-K', 'DEF 14A'). Default '10-K'.
        limit: Maximum number of filings to return (default 5).

    Returns:
        JSON string with a list of filings containing accession_number,
        filing_date, form_type, description, and document URL.
    """
    try:
        logger.info(
            "sec.get_company_filings",
            ticker=ticker,
            filing_type=filing_type,
            limit=limit,
        )

        cik = _ticker_to_cik(ticker)
        if not cik:
            return json.dumps(
                {"error": f"Could not resolve ticker '{ticker}' to a CIK"}
            )

        # Fetch submissions JSON from EDGAR
        url = f"{EDGAR_SUBMISSIONS}/CIK{cik}.json"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        company_name = data.get("name", ticker)
        recent = data.get("filings", {}).get("recent", {})

        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        descriptions = recent.get("primaryDocDescription", [])

        filings = []
        for i in range(len(forms)):
            if filing_type and forms[i] != filing_type:
                continue
            accession_clean = accessions[i].replace("-", "")
            doc_url = (
                f"{EDGAR_ARCHIVES}/{cik.lstrip('0')}"
                f"/{accession_clean}/{primary_docs[i]}"
            )
            filings.append(
                {
                    "company": company_name,
                    "ticker": ticker.upper(),
                    "form_type": forms[i],
                    "filing_date": dates[i],
                    "accession_number": accessions[i],
                    "description": descriptions[i] if i < len(descriptions) else "",
                    "document_url": doc_url,
                }
            )
            if len(filings) >= limit:
                break

        logger.info(
            "sec.get_company_filings.done",
            ticker=ticker,
            filings_found=len(filings),
        )
        return json.dumps(filings, indent=2)

    except Exception as e:
        logger.error("sec.get_company_filings.error", error=str(e))
        return json.dumps({"error": str(e)})


@tool
def get_filing_text(accession_number: str) -> str:
    """Get a summary of a specific SEC filing by accession number.

    Fetches the filing index page and retrieves the primary document
    content, truncated to a manageable size for LLM consumption.

    Args:
        accession_number: The SEC accession number (e.g. '0000320193-23-000077').

    Returns:
        JSON string with filing metadata and a content summary
        (first ~5000 characters of the filing text).
    """
    try:
        logger.info(
            "sec.get_filing_text", accession_number=accession_number
        )

        # Fetch the filing index to find the primary document
        accession_clean = accession_number.replace("-", "")
        index_url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{accession_clean}/{accession_number}-index.htm"
        )

        # Use the full-text search endpoint instead for reliability
        search_url = f"{EDGAR_BASE}/search-index"
        search_params = {
            "q": f'accessionNo:"{accession_number}"',
            "dateRange": "custom",
            "startdt": "2000-01-01",
            "enddt": "2099-12-31",
        }

        # Try to fetch the filing directly via the submissions API
        resp = requests.get(
            f"https://efts.sec.gov/LATEST/search-index"
            f"?q=%22{accession_number}%22&from=0&size=1",
            headers=HEADERS,
            timeout=15,
        )

        # Fallback: try the EDGAR full-text search API
        search_resp = requests.get(
            f"{EDGAR_BASE}/efts/search-index",
            params={"q": accession_number, "from": 0, "size": 1},
            headers=HEADERS,
            timeout=15,
        )

        # Fetch the actual filing document
        # Construct URL pattern for common filing paths
        filing_url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{accession_clean}/{accession_number}.txt"
        )
        doc_resp = requests.get(
            filing_url, headers=HEADERS, timeout=30
        )

        if doc_resp.status_code == 200:
            raw_text = doc_resp.text
            # Strip HTML if present
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(raw_text, "html.parser")
            clean_text = soup.get_text(separator="\n", strip=True)

            # Truncate for LLM context
            content_summary = clean_text[:5000]
            if len(clean_text) > 5000:
                content_summary += "\n\n... [TRUNCATED - full document is much longer]"

            result = {
                "accession_number": accession_number,
                "content_length": len(clean_text),
                "content_summary": content_summary,
            }
        else:
            result = {
                "accession_number": accession_number,
                "error": f"Could not fetch filing document (HTTP {doc_resp.status_code})",
                "tried_url": filing_url,
            }

        logger.info("sec.get_filing_text.done")
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error("sec.get_filing_text.error", error=str(e))
        return json.dumps({"error": str(e)})
