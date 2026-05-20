"""Web research service.

Gives Nexus open internet access for research. Three search tiers:
  1. DuckDuckGo Instant Answer API — free, no key, always available
  2. Serper.dev — optional key, Google results, much better quality
  3. Brave Search API — optional key, independent index

Plus a content fetcher that extracts clean text from any URL, and a
financial-specific scraper for SEC filings, earnings, analyst reports.

All results are cleaned, truncated to a safe length, and returned as
structured dicts the LLM tool-calling layer can consume directly.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urljoin, urlparse

import httpx

from app.core.config import settings

# ── Constants ─────────────────────────────────────────────────────────────────

USER_AGENT = (
    "Mozilla/5.0 (compatible; NexusTrader/1.0; +https://nexus-trader.app)"
)
TIMEOUT = 12.0
MAX_CONTENT_CHARS = 8_000   # per page fetch
MAX_SNIPPET_CHARS = 400     # per search result snippet
MAX_RESULTS = 8

# Simple in-process cache: {cache_key: (timestamp, result)}
_CACHE: Dict[str, tuple] = {}
CACHE_TTL = 300  # 5 minutes


def _cache_key(method: str, query: str) -> str:
    return hashlib.md5(f"{method}:{query}".encode()).hexdigest()


def _from_cache(key: str) -> Optional[Any]:
    if key in _CACHE:
        ts, val = _CACHE[key]
        if time.time() - ts < CACHE_TTL:
            return val
        del _CACHE[key]
    return None


def _to_cache(key: str, val: Any) -> None:
    _CACHE[key] = (time.time(), val)


# ── Text cleaning ─────────────────────────────────────────────────────────────

def _clean_html(html: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.I)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"\s{3,}", "\n\n", text)
    return text.strip()


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"… [truncated, {len(text) - max_chars} chars omitted]"


# ── Search providers ──────────────────────────────────────────────────────────

async def _search_duckduckgo(query: str, client: httpx.AsyncClient) -> List[Dict[str, str]]:
    """DuckDuckGo Instant Answer API — free, no key required."""
    try:
        resp = await client.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []

        # Abstract (top answer)
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", query),
                "url": data.get("AbstractURL", ""),
                "snippet": _truncate(data["AbstractText"], MAX_SNIPPET_CHARS),
                "source": "DuckDuckGo Abstract",
            })

        # Related topics
        for topic in data.get("RelatedTopics", [])[:MAX_RESULTS]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("Text", "")[:80],
                    "url": topic.get("FirstURL", ""),
                    "snippet": _truncate(topic.get("Text", ""), MAX_SNIPPET_CHARS),
                    "source": "DuckDuckGo",
                })

        # HTML search fallback for richer results
        if len(results) < 3:
            html_results = await _search_duckduckgo_html(query, client)
            results.extend(html_results)

        return results[:MAX_RESULTS]
    except Exception as e:
        return [{"title": "Search error", "url": "", "snippet": str(e), "source": "DuckDuckGo"}]


async def _search_duckduckgo_html(query: str, client: httpx.AsyncClient) -> List[Dict[str, str]]:
    """Scrape DuckDuckGo HTML results as fallback."""
    try:
        resp = await client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        html = resp.text
        results = []
        # Extract result blocks
        blocks = re.findall(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
            html, re.DOTALL
        )
        for url, title, snippet in blocks[:MAX_RESULTS]:
            results.append({
                "title": _clean_html(title)[:100],
                "url": url,
                "snippet": _truncate(_clean_html(snippet), MAX_SNIPPET_CHARS),
                "source": "DuckDuckGo HTML",
            })
        return results
    except Exception:
        return []


async def _search_serper(query: str, client: httpx.AsyncClient) -> List[Dict[str, str]]:
    """Serper.dev — Google results. Requires SERPER_API_KEY."""
    key = getattr(settings, "serper_api_key", "")
    if not key:
        return []
    try:
        resp = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            json={"q": query, "num": MAX_RESULTS},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("organic", [])[:MAX_RESULTS]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": _truncate(item.get("snippet", ""), MAX_SNIPPET_CHARS),
                "source": "Google (Serper)",
            })
        # Knowledge graph
        kg = data.get("knowledgeGraph", {})
        if kg.get("description"):
            results.insert(0, {
                "title": kg.get("title", query),
                "url": kg.get("website", ""),
                "snippet": _truncate(kg["description"], MAX_SNIPPET_CHARS),
                "source": "Google Knowledge Graph",
            })
        return results
    except Exception:
        return []


async def _search_brave(query: str, client: httpx.AsyncClient) -> List[Dict[str, str]]:
    """Brave Search API. Requires BRAVE_API_KEY."""
    key = getattr(settings, "brave_api_key", "")
    if not key:
        return []
    try:
        resp = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"Accept": "application/json", "X-Subscription-Token": key},
            params={"q": query, "count": MAX_RESULTS},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("web", {}).get("results", [])[:MAX_RESULTS]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": _truncate(item.get("description", ""), MAX_SNIPPET_CHARS),
                "source": "Brave Search",
            })
        return results
    except Exception:
        return []


async def search_web(
    query: str,
    max_results: int = MAX_RESULTS,
    prefer_financial: bool = False,
) -> Dict[str, Any]:
    """
    Search the web using the best available provider.
    Falls through: Serper → Brave → DuckDuckGo.
    Returns structured results with source attribution.
    """
    ck = _cache_key("search", query)
    cached = _from_cache(ck)
    if cached:
        return {**cached, "cached": True}

    if prefer_financial:
        query = f"{query} site:reuters.com OR site:bloomberg.com OR site:wsj.com OR site:sec.gov OR site:seekingalpha.com"

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=TIMEOUT,
    ) as client:
        # Try providers in order of quality
        results = await _search_serper(query, client)
        provider = "serper"
        if not results:
            results = await _search_brave(query, client)
            provider = "brave"
        if not results:
            results = await _search_duckduckgo(query, client)
            provider = "duckduckgo"

    results = results[:max_results]
    out = {
        "query": query,
        "results": results,
        "total": len(results),
        "provider": provider,
        "cached": False,
    }
    _to_cache(ck, out)
    return out


# ── Page fetcher ──────────────────────────────────────────────────────────────

# Domains that are useful for financial research
FINANCIAL_DOMAINS = {
    "reuters.com", "bloomberg.com", "wsj.com", "ft.com",
    "cnbc.com", "marketwatch.com", "seekingalpha.com",
    "sec.gov", "finviz.com", "investopedia.com",
    "federalreserve.gov", "bls.gov", "census.gov",
    "arxiv.org", "ssrn.com", "papers.ssrn.com",
    "github.com", "quantlib.org",
}


async def fetch_page(url: str, max_chars: int = MAX_CONTENT_CHARS) -> Dict[str, Any]:
    """
    Fetch and extract clean text from any URL.
    Returns title, text content, and metadata.
    """
    ck = _cache_key("page", url)
    cached = _from_cache(ck)
    if cached:
        return {**cached, "cached": True}

    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=TIMEOUT,
        ) as client:
            resp = await client.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")

            if "json" in content_type:
                text = json.dumps(resp.json(), indent=2)
            elif "html" in content_type or "text" in content_type:
                text = _clean_html(resp.text)
            else:
                text = f"[Binary content: {content_type}]"

        # Extract title
        title_m = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.I | re.DOTALL)
        title = _clean_html(title_m.group(1)) if title_m else urlparse(url).netloc

        domain = urlparse(url).netloc.replace("www.", "")
        out = {
            "url": url,
            "title": title[:200],
            "domain": domain,
            "content": _truncate(text, max_chars),
            "content_length": len(text),
            "is_financial": any(d in domain for d in FINANCIAL_DOMAINS),
            "cached": False,
        }
        _to_cache(ck, out)
        return out

    except Exception as e:
        return {
            "url": url,
            "title": "",
            "domain": urlparse(url).netloc,
            "content": f"Failed to fetch: {e}",
            "content_length": 0,
            "is_financial": False,
            "cached": False,
            "error": str(e),
        }


# ── Financial-specific research helpers ──────────────────────────────────────

async def research_symbol(symbol: str) -> Dict[str, Any]:
    """
    Deep research on a stock symbol: news, analyst views, SEC filings,
    recent earnings, and any relevant academic/quant research.
    """
    sym = symbol.upper()
    queries = [
        f"{sym} stock analysis latest news",
        f"{sym} earnings revenue analyst price target",
        f"{sym} SEC 10-K 10-Q filing",
        f"{sym} options flow unusual activity",
    ]
    all_results = []
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
        for q in queries[:2]:  # limit to 2 queries to stay fast
            r = await search_web(q, max_results=4)
            all_results.extend(r.get("results", []))

    return {
        "symbol": sym,
        "results": all_results[:10],
        "total": len(all_results),
    }


async def research_strategy(topic: str) -> Dict[str, Any]:
    """
    Research a trading strategy or technical concept.
    Searches academic papers, quant blogs, and documentation.
    """
    queries = [
        f"{topic} trading strategy backtesting results",
        f"{topic} quantitative finance research paper",
        f"site:arxiv.org OR site:ssrn.com {topic} trading",
    ]
    all_results = []
    for q in queries[:2]:
        r = await search_web(q, max_results=4)
        all_results.extend(r.get("results", []))

    return {
        "topic": topic,
        "results": all_results[:10],
        "total": len(all_results),
    }


async def research_market_event(event: str) -> Dict[str, Any]:
    """Research a market event, macro development, or geopolitical situation."""
    r = await search_web(f"{event} market impact analysis", max_results=6, prefer_financial=True)
    return {
        "event": event,
        "results": r.get("results", []),
        "total": r.get("total", 0),
        "provider": r.get("provider"),
    }


web_research_service = type(
    "_Svc", (),
    {
        "search": staticmethod(search_web),
        "fetch": staticmethod(fetch_page),
        "research_symbol": staticmethod(research_symbol),
        "research_strategy": staticmethod(research_strategy),
        "research_event": staticmethod(research_market_event),
    }
)()
