"""
News and Content Aggregator node.

For a given ``current_stock`` this node:
    1. Fetches the real-time quote from Finnhub (current price, high, low, etc.).
    2. Retrieves the company profile (name, industry, market cap).
    3. Gathers the latest company-specific news articles.
    4. Stores everything into dedicated state fields so downstream nodes
       can consume clean, structured data.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import finnhub
from dotenv import load_dotenv

from graph.state import AgentState

load_dotenv()


# ── Finnhub client (module-level singleton) ──────────────────────────────────

def _get_client() -> finnhub.Client:
    return finnhub.Client(api_key=os.getenv("FINNHUB_API_KEY"))


# ═══════════════════════════════════════════════════════════════════════════
#  Data-fetching helpers
# ═══════════════════════════════════════════════════════════════════════════

def _fetch_quote(client: finnhub.Client, symbol: str) -> dict:
    """
    Get real-time quote for ``symbol``.

    Returns dict with keys: current_price, change, percent_change,
    high, low, open, previous_close.
    """
    try:
        q = client.quote(symbol)
        quote = {
            "current_price": q.get("c"),
            "change": q.get("d"),
            "percent_change": q.get("dp"),
            "high": q.get("h"),
            "low": q.get("l"),
            "open": q.get("o"),
            "previous_close": q.get("pc"),
        }
        print(f"[news_aggregator] Quote for {symbol}: "
              f"${quote['current_price']}  ({quote['percent_change']}%)")
        return quote
    except Exception as exc:
        print(f"[WARN] Could not fetch quote for {symbol}: {exc}")
        return {}


def _fetch_profile(client: finnhub.Client, symbol: str) -> dict:
    """
    Get company profile metadata.

    Returns dict with keys: name, country, exchange, industry, market_cap, etc.
    """
    try:
        p = client.company_profile2(symbol=symbol)
        profile = {
            "name": p.get("name", ""),
            "country": p.get("country", ""),
            "exchange": p.get("exchange", ""),
            "industry": p.get("finnhubIndustry", ""),
            "market_cap": p.get("marketCapitalization", 0),
            "shares_outstanding": p.get("shareOutstanding", 0),
            "logo": p.get("logo", ""),
            "weburl": p.get("weburl", ""),
            "ipo_date": p.get("ipo", ""),
        }
        print(f"[news_aggregator] Profile: {profile['name']} "
              f"({profile['industry']})")
        return profile
    except Exception as exc:
        print(f"[WARN] Could not fetch profile for {symbol}: {exc}")
        return {}


def _fetch_company_news(client: finnhub.Client, symbol: str,
                        days: int = 30) -> list[dict]:
    """
    Fetch company-specific news for the last ``days`` days.

    Returns a list of dicts with keys: headline, summary, source, url,
    datetime, category.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        raw = client.company_news(symbol, _from=from_date, to=today)
        articles = [
            {
                "headline": a.get("headline", ""),
                "summary": (a.get("summary", "") or "")[:500],
                "source": a.get("source", ""),
                "url": a.get("url", ""),
                "datetime": a.get("datetime", 0),
                "category": a.get("category", ""),
            }
            for a in (raw or [])[:50]  # cap at 50 articles
        ]
        print(f"[news_aggregator] Fetched {len(articles)} news articles "
              f"for {symbol}")
        return articles
    except Exception as exc:
        print(f"[WARN] Could not fetch news for {symbol}: {exc}")
        return []


# ── Node function ────────────────────────────────────────────────────────────

def news_aggregator_node(state: AgentState) -> dict:
    """
    Aggregate stock price data, company profile, and news for
    the ``current_stock``.

    Populates state keys:
        - ``stock_prices``  (real-time quote data)
        - ``stock_news``    (list of news articles)
        - ``stock_profile`` (company metadata)
    """
    print("=" * 60)
    print("[NODE] news_aggregator_node -- entered")
    print("=" * 60)

    symbol = state.get("current_stock", "")
    if not symbol:
        print("[news_aggregator] No current_stock set -- skipping")
        return {}

    print(f"[news_aggregator] Aggregating data for: {symbol}")

    client = _get_client()

    # 1) Real-time quote
    quote = _fetch_quote(client, symbol)

    # 2) Company profile
    profile = _fetch_profile(client, symbol)

    # 3) Company news
    news = _fetch_company_news(client, symbol, days=30)

    # Bundle price data
    stock_prices = {
        "symbol": symbol,
        "quote": quote,
    }

    print(f"[news_aggregator] Done. "
          f"quote={'yes' if quote else 'no'}, "
          f"profile={'yes' if profile else 'no'}, "
          f"news={len(news)} articles")

    return {
        "stock_prices": stock_prices,
        "stock_news": news,
        "stock_profile": profile,
    }
