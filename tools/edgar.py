"""SEC EDGAR client — free, no API key required."""

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

BASE_URL = "https://data.sec.gov"
HEADERS = {"User-Agent": "stock-intelligence-agent contact@example.com"}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_cik(ticker: str) -> str | None:
    """Resolve ticker → CIK number."""
    url = "https://efts.sec.gov/LATEST/search-index?q=%22{}%22&dateRange=custom&startdt=2020-01-01&forms=10-K".format(ticker)
    resp = requests.get(
        "https://www.sec.gov/cgi-bin/browse-edgar",
        params={"action": "getcompany", "company": "", "CIK": ticker,
                "type": "10-K", "dateb": "", "owner": "include", "count": "1",
                "search_text": "", "output": "atom"},
        headers=HEADERS,
        timeout=15,
    )
    # CIK appears in the feed URL — parse from response
    if "CIK=" in resp.text:
        start = resp.text.find("CIK=") + 4
        end = resp.text.find("&", start)
        return resp.text[start:end].zfill(10)
    return None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_recent_filings(cik: str, form_type: str = "10-Q") -> list[dict]:
    """Latest filings metadata for a CIK."""
    cik_padded = cik.zfill(10)
    url = f"{BASE_URL}/submissions/CIK{cik_padded}.json"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    dates = filings.get("filingDate", [])
    accessions = filings.get("accessionNumber", [])
    docs = filings.get("primaryDocument", [])

    results = []
    for form, dt, acc, doc in zip(forms, dates, accessions, docs):
        if form == form_type:
            results.append({"form": form, "date": dt, "accession": acc, "doc": doc})
        if len(results) >= 4:   # latest 4 filings only
            break
    return results


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_company_facts(cik: str) -> dict:
    """Structured financial facts (revenue, EPS, etc.) in XBRL format."""
    cik_padded = cik.zfill(10)
    url = f"{BASE_URL}/api/xbrl/companyfacts/CIK{cik_padded}.json"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()
