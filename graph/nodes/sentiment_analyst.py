"""
Sentiment Analyst node.

Uses **Gemma 4 (gemma-4-31b-it)** with **Grounding with Google Search**
via the native ``google-genai`` SDK. The agent:

    1. Reads the ``sentiment_data`` produced by the news_refiner.
    2. Formulates a series of research questions about the stock.
    3. Sends each question to Gemma 4 with ``GoogleSearch`` grounding
       so the model can fetch live information from the internet.
    4. Synthesises all answers into a final **buy_probability** (0-1)
       and a structured report.

The output is stored in ``state["sentiment_report"]``.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime

from dotenv import load_dotenv
from google import genai
from google.genai.types import GenerateContentConfig, Tool, GoogleSearch

from graph.state import AgentState

load_dotenv()


# ── Research Questions Template ──────────────────────────────────────────────

def _build_research_questions(symbol: str, company_name: str,
                              sentiment_data: dict) -> list[dict]:
    """
    Build a list of research questions derived from the sentiment signals.
    Each item has a ``topic`` (label) and ``question`` (the actual prompt).
    """
    bullish = sentiment_data.get("bullish_signals", [])
    bearish = sentiment_data.get("bearish_signals", [])

    questions = [
        {
            "topic": "current_market_sentiment",
            "question": (
                f"What is the current overall market sentiment for "
                f"{company_name} ({symbol}) stock today? "
                f"Is it bullish or bearish based on latest news and "
                f"analyst opinions?"
            ),
        },
        {
            "topic": "recent_analyst_ratings",
            "question": (
                f"What are the most recent analyst ratings and price targets "
                f"for {symbol}? Have any major firms upgraded or downgraded "
                f"the stock recently?"
            ),
        },
        {
            "topic": "social_media_buzz",
            "question": (
                f"What is the social media and retail investor sentiment "
                f"for {symbol} stock right now? Are retail investors "
                f"bullish or bearish on {company_name}?"
            ),
        },
        {
            "topic": "sector_and_macro",
            "question": (
                f"How is the broader {company_name}'s industry sector "
                f"performing today? Are there macroeconomic factors "
                f"(interest rates, trade policy, etc.) affecting {symbol}?"
            ),
        },
        {
            "topic": "risks_and_headwinds",
            "question": (
                f"What are the key risks and headwinds currently facing "
                f"{company_name} ({symbol})? Are there any regulatory, "
                f"competitive, or supply-chain concerns?"
            ),
        },
    ]

    # Verify specific bullish signals
    if bullish:
        signals_str = "; ".join(bullish[:5])
        questions.append({
            "topic": "bullish_signal_verification",
            "question": (
                f"Our news analysis found these bullish signals for {symbol}: "
                f"{signals_str}. "
                f"Can you verify if these are accurate and still relevant?"
            ),
        })

    # Verify specific bearish signals
    if bearish:
        signals_str = "; ".join(bearish[:5])
        questions.append({
            "topic": "bearish_signal_verification",
            "question": (
                f"Our news analysis found these bearish signals for {symbol}: "
                f"{signals_str}. "
                f"Can you verify if these are accurate and still relevant?"
            ),
        })

    return questions


# ── Synthesis Prompt ─────────────────────────────────────────────────────────

SYNTHESIS_PROMPT = """You are a senior sentiment analyst at a hedge fund.

Based on the research answers below, produce a FINAL VERDICT.

Respond with ONLY a valid JSON object (no markdown fences, no commentary):

{{
  "buy_probability": <float 0.0 to 1.0>,
  "verdict": "strong_buy | buy | hold | sell | strong_sell",
  "confidence": <float 0.0 to 1.0>,
  "reasoning": "<2-3 sentence explanation>",
  "key_factors": ["<factor1>", "<factor2>", ...],
  "risks": ["<risk1>", "<risk2>", ...]
}}

Rules:
- buy_probability: 0.0 = definitely do NOT buy, 1.0 = definitely buy
- Base your decision strictly on the research data provided
- Be conservative -- when uncertain, lean toward 0.5 (hold)
- List the top 3-5 key factors and risks

=== STOCK ===
{symbol} ({company_name})
Current Price: ${current_price}
Change: {change} ({percent_change}%)

=== INITIAL SENTIMENT FROM NEWS ===
Overall: {overall_sentiment}
Media Tone: {media_tone}

=== RESEARCH FINDINGS ===
{research_findings}
"""


from services.utils import retry_on_error

# ── Helpers ──────────────────────────────────────────────────────────────────

@retry_on_error(max_retries=3, delay=2, backoff=2)
def _grounded_query(client: genai.Client, question: str) -> str:
    """
    Send a single question to Gemma 4 with Google Search grounding enabled.
    Returns the model's text response.
    """
    response = client.models.generate_content(
        model="gemma-4-31b-it",
        contents=question,
        config=GenerateContentConfig(
            tools=[Tool(google_search=GoogleSearch())],
            temperature=0.2,
        ),
    )
    return response.text or ""


@retry_on_error(max_retries=3, delay=2, backoff=2)
def _plain_query(client: genai.Client, prompt: str) -> str:
    """
    Send a prompt to Gemma 4 WITHOUT grounding (for final synthesis).
    """
    response = client.models.generate_content(
        model="gemma-4-31b-it",
        contents=prompt,
        config=GenerateContentConfig(temperature=0),
    )
    return response.text or ""


def _parse_json(raw: str) -> dict:
    """Parse a JSON response, stripping markdown fences if present."""
    cleaned = raw.strip()
    if "```" in cleaned:
        parts = cleaned.split("```")
        if len(parts) >= 3:
            cleaned = parts[1].strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        print(f"[WARN] Could not parse JSON: {exc}")
        print(f"[WARN] Raw (first 300 chars): {raw[:300]}")
        return {}


# ── Node function ────────────────────────────────────────────────────────────

def sentiment_analyst_node(state: AgentState) -> dict:
    """
    Research stock sentiment using Gemma 4 + Google Search grounding,
    then produce a buy_probability score.

    Reads:
        - ``current_stock``, ``stock_profile``, ``stock_prices``
        - ``sentiment_data`` (from news_refiner)

    Writes:
        - ``sentiment_report``
    """
    print("=" * 60)
    print("[NODE] sentiment_analyst_node -- entered")
    print("=" * 60)

    symbol = state.get("current_stock", "")
    profile = state.get("stock_profile", {})
    prices = state.get("stock_prices", {})
    quote = prices.get("quote", {})
    sentiment_data = state.get("sentiment_data", {})
    company_name = profile.get("name", symbol)

    if not symbol:
        print("[sentiment_analyst] No current_stock -- skipping")
        return {}

    print(f"[sentiment_analyst] Analysing sentiment for: "
          f"{company_name} ({symbol})")

    # ── 1) Build research questions ──────────────────────────────────────
    questions = _build_research_questions(symbol, company_name, sentiment_data)
    print(f"[sentiment_analyst] Prepared {len(questions)} research questions")

    # ── 2) Create google-genai client ────────────────────────────────────
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

    # ── 3) Ask each question with Google Search grounding ────────────────
    research_qa: list[dict] = []
    DELAY_BETWEEN_CALLS = 4  # seconds, to respect free-tier rate limits

    for i, q in enumerate(questions, 1):
        print(f"[sentiment_analyst]   Q{i}/{len(questions)}: "
              f"{q['topic']}...")
        try:
            answer = _grounded_query(client, q["question"])
            research_qa.append({
                "topic": q["topic"],
                "question": q["question"],
                "answer": answer[:1500],
            })
            print(f"[sentiment_analyst]   A{i}: "
                  f"{answer[:120]}...")
        except Exception as exc:
            print(f"[WARN] Research question {i} failed: {exc}")
            research_qa.append({
                "topic": q["topic"],
                "question": q["question"],
                "answer": f"(research failed: {exc})",
            })

        # Rate-limit delay between calls
        if i < len(questions):
            time.sleep(DELAY_BETWEEN_CALLS)

    print(f"[sentiment_analyst] Completed {len(research_qa)} "
          f"research queries")

    # ── 4) Synthesise into final verdict ─────────────────────────────────
    research_text = "\n\n".join(
        f"--- {qa['topic'].upper()} ---\n"
        f"Q: {qa['question']}\n"
        f"A: {qa['answer']}"
        for qa in research_qa
    )

    synthesis_input = SYNTHESIS_PROMPT.format(
        symbol=symbol,
        company_name=company_name,
        current_price=quote.get("current_price", "N/A"),
        change=quote.get("change", "N/A"),
        percent_change=quote.get("percent_change", "N/A"),
        overall_sentiment=sentiment_data.get("overall_sentiment", "unknown"),
        media_tone=sentiment_data.get("media_tone_summary", "N/A"),
        research_findings=research_text,
    )

    try:
        print("[sentiment_analyst] Synthesising final verdict...")
        time.sleep(DELAY_BETWEEN_CALLS)
        raw = _plain_query(client, synthesis_input)
        verdict = _parse_json(raw)
    except Exception as exc:
        print(f"[WARN] Verdict synthesis failed: {exc}")
        verdict = {}

    # Fallback defaults
    if not verdict or "buy_probability" not in verdict:
        verdict = {
            "buy_probability": 0.5,
            "verdict": "hold",
            "confidence": 0.0,
            "reasoning": "Unable to synthesise verdict; defaulting to hold.",
            "key_factors": [],
            "risks": ["Synthesis parsing failed"],
        }

    # ── 5) Build the full report ─────────────────────────────────────────
    sentiment_report = {
        "symbol": symbol,
        "company_name": company_name,
        "timestamp": datetime.now().isoformat(),
        "buy_probability": verdict.get("buy_probability", 0.5),
        "verdict": verdict.get("verdict", "hold"),
        "confidence": verdict.get("confidence", 0.0),
        "reasoning": verdict.get("reasoning", ""),
        "key_factors": verdict.get("key_factors", []),
        "risks": verdict.get("risks", []),
        "research_qa": research_qa,
    }

    prob = sentiment_report["buy_probability"]
    verd = sentiment_report["verdict"]
    conf = sentiment_report["confidence"]
    print(f"[sentiment_analyst] >> VERDICT: {verd} "
          f"(buy_prob={prob:.2f}, confidence={conf:.2f})")
    print(f"[sentiment_analyst] >> Reasoning: "
          f"{sentiment_report['reasoning'][:200]}")
          
    # ── 6) Generate PDF ──────────────────────────────────────────────────
    try:
        from services.reporting import generate_analyst_pdf
        generate_analyst_pdf("Sentiment Analyst", symbol, sentiment_data, sentiment_report)
    except Exception as e:
        print(f"[WARN] Failed to generate PDF for Sentiment Analyst: {e}")

    print("[sentiment_analyst] Done.")

    return {"sentiment_report": sentiment_report}
