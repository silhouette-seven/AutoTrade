"""
News Refiner and Documenter node.

Takes all raw news, stock prices, and company profile from state and uses
the Gemini API (Gemma model) to clean, deduplicate, and categorise the data
into three analyst-specific buckets:

    1. **quant_data**       -- financial figures, metrics, analyst targets
                               (for the Quantitative Analyst)
    2. **sentiment_data**   -- market mood, media tone, bullish/bearish cues
                               (for the Sentiment Analyst)
    3. **algo_time_series** -- stock price data organised into a time-series-
                               ready structure (for the Algorithmic Predictor)
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from graph.state import AgentState

load_dotenv()


# ── Prompts ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior financial data analyst. You will receive:
1) A set of raw news articles about a stock.
2) The stock's real-time quote data (open, high, low, close, change).
3) The company's profile (name, industry, market cap, etc.).

Your job is to clean, deduplicate, and organise this information into
EXACTLY three JSON categories. Return a single JSON object with these keys:

{
  "quant_data": {
    "earnings": [...],
    "revenue_figures": [...],
    "analyst_price_targets": [...],
    "financial_metrics": [...],
    "key_statistics": [...],
    "summary": "..."
  },
  "sentiment_data": {
    "overall_sentiment": "bullish | bearish | neutral",
    "confidence": 0.0-1.0,
    "bullish_signals": [...],
    "bearish_signals": [...],
    "media_tone_summary": "...",
    "notable_events": [...]
  }
}

Rules:
- Extract ONLY factual data.  Do NOT invent numbers.
- Deduplicate headlines that cover the same story.
- Each list item should be a short, self-contained string.
- "summary" fields should be 2-3 sentences max.
- Respond with ONLY valid JSON. No markdown fences, no commentary.
"""


# ── Helpers ──────────────────────────────────────────────────────────────────

def _build_user_message(state: AgentState) -> str:
    """
    Assemble the raw data from state into a single text payload
    for the LLM to process.
    """
    symbol = state.get("current_stock", "???")
    profile = state.get("stock_profile", {})
    prices = state.get("stock_prices", {})
    quote = prices.get("quote", {})
    news = state.get("stock_news", [])

    # -- Company profile block
    profile_block = (
        f"Company: {profile.get('name', symbol)}\n"
        f"Symbol:  {symbol}\n"
        f"Industry: {profile.get('industry', 'N/A')}\n"
        f"Exchange: {profile.get('exchange', 'N/A')}\n"
        f"Market Cap: {profile.get('market_cap', 'N/A')}M\n"
        f"Shares Outstanding: {profile.get('shares_outstanding', 'N/A')}\n"
        f"IPO Date: {profile.get('ipo_date', 'N/A')}\n"
    )

    # -- Quote block
    quote_block = (
        f"Current Price: ${quote.get('current_price', 'N/A')}\n"
        f"Open:  ${quote.get('open', 'N/A')}\n"
        f"High:  ${quote.get('high', 'N/A')}\n"
        f"Low:   ${quote.get('low', 'N/A')}\n"
        f"Previous Close: ${quote.get('previous_close', 'N/A')}\n"
        f"Change: {quote.get('change', 'N/A')} "
        f"({quote.get('percent_change', 'N/A')}%)\n"
    )

    # -- News block (cap at 30 articles to stay within token limits)
    news_lines = []
    for i, article in enumerate(news[:30], 1):
        news_lines.append(
            f"{i}. [{article.get('source', '?')}] "
            f"{article.get('headline', '')}\n"
            f"   {article.get('summary', '')[:300]}"
        )
    news_block = "\n\n".join(news_lines) if news_lines else "(no news available)"

    return (
        f"=== COMPANY PROFILE ===\n{profile_block}\n"
        f"=== STOCK QUOTE ===\n{quote_block}\n"
        f"=== NEWS ARTICLES ({len(news)} total, showing up to 30) ===\n"
        f"{news_block}"
    )


def _build_time_series(state: AgentState) -> dict:
    """
    Organise the stock price data into a time-series-ready structure
    for the algorithmic predictor's future prediction model.

    Even without candle history, we create the schema and seed it
    with the current quote so the pipeline always has a consistent
    data structure to work with.
    """
    prices = state.get("stock_prices", {})
    quote = prices.get("quote", {})
    symbol = state.get("current_stock", "")
    profile = state.get("stock_profile", {})
    now_ts = int(datetime.now().timestamp())

    # Seed the first row from the live quote
    if quote and quote.get("current_price") is not None:
        rows = [{
            "timestamp": now_ts,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "close": quote.get("current_price"),
            "previous_close": quote.get("previous_close"),
            "change": quote.get("change"),
            "percent_change": quote.get("percent_change"),
        }]
    else:
        rows = []

    return {
        "symbol": symbol,
        "company_name": profile.get("name", ""),
        "industry": profile.get("industry", ""),
        "market_cap": profile.get("market_cap", 0),
        "data_points": rows,
        "columns": [
            "timestamp", "date", "open", "high", "low", "close",
            "previous_close", "change", "percent_change",
        ],
        "notes": (
            "Seed row from live quote. Append historical rows "
            "as candle data becomes available."
        ),
    }


def _parse_llm_response(raw: str) -> dict:
    """
    Parse the LLM JSON response, handling markdown fences if present.
    """
    cleaned = raw.strip()

    # Strip markdown code fences
    if "```" in cleaned:
        parts = cleaned.split("```")
        # Take the content between the first pair of fences
        if len(parts) >= 3:
            cleaned = parts[1].strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        print(f"[WARN] news_refiner could not parse LLM JSON: {exc}")
        print(f"[WARN] Raw response (first 300 chars): {raw[:300]}")
        return {}


# ── Node function ────────────────────────────────────────────────────────────

def news_refiner_node(state: AgentState) -> dict:
    """
    Refine and categorise aggregated data for the three analyst branches.

    Reads:
        - ``stock_news``, ``stock_prices``, ``stock_profile``

    Writes:
        - ``quant_data``       (for Quantitative Analyst)
        - ``sentiment_data``   (for Sentiment Analyst)
        - ``algo_time_series`` (for Algorithmic Predictor)
    """
    print("=" * 60)
    print("[NODE] news_refiner_node -- entered")
    print("=" * 60)

    symbol = state.get("current_stock", "")
    news = state.get("stock_news", [])

    if not symbol:
        print("[news_refiner] No current_stock -- skipping")
        return {}

    # ── 1) Build the algo time series (deterministic, no LLM needed) ─────
    algo_ts = _build_time_series(state)
    print(f"[news_refiner] Built algo_time_series with "
          f"{len(algo_ts.get('data_points', []))} data point(s)")

    # ── 2) Send news + quote + profile to Gemini for categorisation ──────
    if not news:
        print("[news_refiner] No news articles to refine")
        quant_data = {"summary": "No news data available", "earnings": [],
                      "revenue_figures": [], "analyst_price_targets": [],
                      "financial_metrics": [], "key_statistics": []}
        sentiment_data = {"overall_sentiment": "neutral", "confidence": 0.0,
                          "bullish_signals": [], "bearish_signals": [],
                          "media_tone_summary": "No news data", "notable_events": []}
    else:
        user_message = _build_user_message(state)
        print(f"[news_refiner] Sending {len(news)} articles to Gemini "
              f"for categorisation...")

        llm = ChatGoogleGenerativeAI(
            model="gemma-3-27b-it",
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0,
            convert_system_message_to_human=True,
        )

        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_message),
        ])

        raw = response.content.strip()
        print(f"[news_refiner] LLM response length: {len(raw)} chars")

        parsed = _parse_llm_response(raw)

        quant_data = parsed.get("quant_data", {})
        sentiment_data = parsed.get("sentiment_data", {})

        print(f"[news_refiner] Sentiment: "
              f"{sentiment_data.get('overall_sentiment', '?')} "
              f"(confidence: {sentiment_data.get('confidence', '?')})")
        print(f"[news_refiner] Quant items: "
              f"earnings={len(quant_data.get('earnings', []))}, "
              f"targets={len(quant_data.get('analyst_price_targets', []))}")

    print("[news_refiner] Done.")

    return {
        "quant_data": quant_data,
        "sentiment_data": sentiment_data,
        "algo_time_series": algo_ts,
    }
