"""
Stock Picker node — entry point of the trading workflow.

Workflow:
    1. Fetch market news from Finnhub.
    2. Feed the headlines to Google Gemma 4 (31B) to get the top-5 tickers.
    3. Filter out stocks that were already analyzed recently (via DB).
    4. Randomly pick one of the remaining tickers.
    5. Set ``current_stock`` in the agent state.
"""

from __future__ import annotations

import json
import os
import random
from datetime import date, timedelta

import finnhub
from dotenv import load_dotenv
import yfinance as yf
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from graph.state import AgentState
from database import init_db, get_all_analyzed_trades
from database.crud import get_current_balance

load_dotenv()

# ── Configuration ────────────────────────────────────────────────────────────

NEWS_CATEGORY = "general"         # finnhub news category
NEWS_MIN_ID = 0                   # pagination cursor (0 = latest)
RECENT_DAYS = 7                   # skip stocks analyzed within this window
TOP_K = 5                         # how many stocks the LLM should suggest
EPSILON = 0.15                    # 15% probability of picking a random exploratory stock

BROAD_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK.B", "UNH", "JNJ",
    "JPM", "V", "PG", "MA", "HD", "CVX", "ABBV", "MRK", "PEP", "KO",
    "PFE", "TMO", "COST", "MCD", "CSCO", "CRM", "NKE", "DIS", "ADBE", "TXN"
]

SYSTEM_PROMPT = f"""You are a stock market analyst. You will receive a collection
of recent financial news headlines from Finnhub.

Your task:
1. Identify the stock tickers (US market, NYSE / NASDAQ) that are being
   discussed the most or present the best trading opportunity.
2. Return EXACTLY {TOP_K} ticker symbols ranked by relevance.

Respond ONLY with a valid JSON array of {TOP_K} uppercase ticker strings.
Example: ["AAPL", "TSLA", "NVDA", "AMD", "PLTR"]

Do NOT include any explanation, commentary, or markdown — just the raw JSON array.
"""


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fetch_finnhub_news() -> list[dict[str, str]]:
    """
    Fetch the latest market news from Finnhub.

    Returns a list of dicts with keys ``headline`` and ``summary``.
    """
    api_key = os.getenv("FINNHUB_API_KEY")
    client = finnhub.Client(api_key=api_key)

    try:
        raw_news = client.general_news(NEWS_CATEGORY, min_id=NEWS_MIN_ID)
        articles = [
            {
                "headline": article.get("headline", ""),
                "summary": (article.get("summary", "") or "")[:300],
            }
            for article in raw_news[:30]  # cap to 30 articles
        ]
        print(f"[stock_picker] Fetched {len(articles)} articles from Finnhub")
        return articles

    except Exception as exc:
        print(f"[WARN] Finnhub API error: {exc}")
        return []


def _ask_llm_for_top_stocks(articles: list[dict[str, str]]) -> list[str]:
    """
    Send the Finnhub headlines to Gemma 4 and parse the top-K ticker list.
    """
    # Build a single text block from all articles
    news_text = "\n\n".join(
        f"Headline: {a['headline']}\nSummary: {a['summary']}"
        for a in articles
    )

    llm = ChatGoogleGenerativeAI(
        model="gemma-3-27b-it",
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0,
        convert_system_message_to_human=True,
    )

    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=news_text),
    ])

    # Parse the JSON array from the response
    raw = response.content.strip()
    print(f"[stock_picker] LLM raw response: {raw}")

    # Try to extract JSON array even if wrapped in markdown fences
    cleaned = raw
    if "```" in cleaned:
        # Strip markdown code fences
        cleaned = cleaned.split("```")[-2] if cleaned.count("```") >= 2 else cleaned
        cleaned = cleaned.strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        tickers = json.loads(cleaned)
        if isinstance(tickers, list):
            tickers = [t.upper().strip() for t in tickers if isinstance(t, str)]
            print(f"[stock_picker] LLM suggested: {tickers}")
            return tickers
    except json.JSONDecodeError:
        print(f"[WARN] Could not parse LLM response as JSON: {raw}")

    return []


def _get_recently_analyzed_stocks(days: int = RECENT_DAYS) -> set[str]:
    """
    Query the database for stocks analyzed within the last ``days`` days.
    """
    init_db()  # ensure tables exist
    cutoff = str(date.today() - timedelta(days=days))
    all_trades = get_all_analyzed_trades()
    return {
        t["stock"]
        for t in all_trades
        if t.get("date", "") >= cutoff
    }


def _get_stock_price(symbol: str) -> float | None:
    """Fetch the latest real-time/close price using yfinance."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="1d")
        if not df.empty:
            return float(df['Close'].iloc[-1])
    except Exception:
        pass
    return None

# ── Node function ────────────────────────────────────────────────────────────

def stock_picker_node(state: AgentState) -> dict:
    """
    Pick a stock for the pipeline to analyse.

    Steps:
        1. Fetch market news from Finnhub.
        2. Ask Gemma 4 for the top-5 tickers.
        3. Exclude recently analyzed tickers.
        4. Simulated Annealing: 15% chance to explore random stock.
        5. Verify price < cash_balance.
    """
    print("=" * 60)
    print("[NODE] stock_picker_node — entered")
    print("=" * 60)

    # Check if manually overridden
    existing_stock = state.get("current_stock")
    if existing_stock:
        print(f"[stock_picker] Bypassing AI selection. Using preset stock: {existing_stock}")
        return {}

    cash_balance = get_current_balance()
    print(f"[stock_picker] Current Cash Balance: ${cash_balance:.2f}")

    # Simulated Annealing -> Random Explore
    if random.random() < EPSILON:
        print("[stock_picker] Simulated Annealing: Taking an exploratory random pick.")
        candidates = list(BROAD_TICKERS)
        random.shuffle(candidates)
    else:
        # Step 1 — fetch Finnhub news
        articles = _fetch_finnhub_news()

        if not articles:
            print("[stock_picker] No articles found — falling back to broad list")
            candidates = list(BROAD_TICKERS)
        else:
            # Step 2 — LLM picks top-K
            candidates = _ask_llm_for_top_stocks(articles)

        if not candidates:
            candidates = list(BROAD_TICKERS)

    # Step 3 — filter out recently analyzed
    recently_analyzed = _get_recently_analyzed_stocks()
    fresh = [t for t in candidates if t not in recently_analyzed]
    
    if not fresh:
        print("[stock_picker] All candidates recently analyzed — reusing full list")
        fresh = list(candidates)

    # Step 4 — Find affordable stock
    chosen = None
    for symbol in fresh:
        price = _get_stock_price(symbol)
        if price is not None:
            if price <= cash_balance:
                print(f"[stock_picker] Verified {symbol} price (${price:.2f}) is affordable.")
                chosen = symbol
                break
            else:
                print(f"[stock_picker] Skipping {symbol} (price ${price:.2f} > balance ${cash_balance:.2f})")
        else:
            print(f"[stock_picker] Could not fetch price for {symbol}, skipping.")

    # Fallback to random if no LLM pick was affordable
    if not chosen:
        print("[stock_picker] No initial candidates affordable. Falling back to broad search.")
        random.shuffle(BROAD_TICKERS)
        for symbol in BROAD_TICKERS:
            price = _get_stock_price(symbol)
            if price is not None and price <= cash_balance:
                chosen = symbol
                print(f"[stock_picker] Fallback chose affordable stock {symbol} (${price:.2f})")
                break

    if not chosen:
        print("[WARN] Could not find any affordable stock! Defaulting to F.")
        chosen = "F" # Ford is usually < $15

    print(f"[stock_picker] >> Final Selected stock: {chosen}")

    # Step 5 — update state
    return {"current_stock": chosen}
