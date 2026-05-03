"""
Quantitative Analyst node.

Uses **Gemma 4 (gemma-4-31b-it)** with **Grounding with Google Search**
via the native ``google-genai`` SDK. The agent:

    1. Reads the ``quant_data`` produced by the news_refiner.
    2. Formulates a series of research questions focused on financials,
       multiples, estimates, and price targets.
    3. Sends each question to Gemma 4 with ``GoogleSearch`` grounding.
    4. Synthesises all answers into a final **buy_probability** (0-1).
    5. Generates a PDF report.

The output is stored in ``state["quant_report"]``.
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
from services.reporting import generate_analyst_pdf

load_dotenv()


# ── Research Questions Template ──────────────────────────────────────────────

def _build_research_questions(symbol: str, company_name: str,
                              quant_data: dict) -> list[dict]:
    """
    Build a list of quantitative research questions.
    """
    questions = [
        {
            "topic": "earnings_and_revenue",
            "question": (
                f"What were the most recent quarterly earnings (EPS) and "
                f"revenue figures for {company_name} ({symbol})? "
                f"Did they beat or miss analyst expectations?"
            ),
        },
        {
            "topic": "forward_guidance",
            "question": (
                f"What is the forward guidance and future growth outlook "
                f"for {symbol} for the next quarter and fiscal year?"
            ),
        },
        {
            "topic": "valuation_multiples",
            "question": (
                f"What are the current valuation multiples for {symbol} "
                f"(e.g., P/E ratio, Price-to-Sales, EV/EBITDA)? How do "
                f"these compare to its industry peers?"
            ),
        },
        {
            "topic": "analyst_price_targets",
            "question": (
                f"What is the consensus 12-month analyst price target for "
                f"{symbol}? What are the highest and lowest targets currently "
                f"set by major Wall Street firms?"
            ),
        },
        {
            "topic": "balance_sheet_health",
            "question": (
                f"What is the current state of {company_name}'s balance sheet? "
                f"Look for cash reserves, total debt, and free cash flow generation."
            ),
        },
    ]

    # Verify specific earnings signals
    earnings = quant_data.get("earnings", [])
    if earnings:
        signals_str = "; ".join(earnings[:3])
        questions.append({
            "topic": "earnings_signal_verification",
            "question": (
                f"Our analysis found these recent earnings signals for {symbol}: "
                f"{signals_str}. "
                f"Can you verify these numbers are accurate based on the latest reports?"
            ),
        })

    return questions


# ── Synthesis Prompt ─────────────────────────────────────────────────────────

SYNTHESIS_PROMPT = """You are a senior quantitative analyst at a hedge fund.

Based on the grounded research answers below, produce a FINAL VERDICT based STRICTLY on financials, valuation, and quantitative metrics.

Respond with ONLY a valid JSON object (no markdown fences, no commentary):

{{
  "buy_probability": <float 0.0 to 1.0>,
  "verdict": "strong_buy | buy | hold | sell | strong_sell",
  "confidence": <float 0.0 to 1.0>,
  "reasoning": "<2-3 sentence explanation of the quantitative case>",
  "key_factors": ["<factor1>", "<factor2>", ...],
  "risks": ["<risk1>", "<risk2>", ...]
}}

Rules:
- buy_probability: 0.0 = definitely do NOT buy, 1.0 = definitely buy
- Base your decision ONLY on the provided financial metrics and research data
- Be conservative -- when uncertain, lean toward 0.5 (hold)
- List the top 3-5 quantitative factors (e.g. "P/E is 15% below historical average")

=== STOCK ===
{symbol} ({company_name})
Current Price: ${current_price}

=== INITIAL QUANT DATA FROM NEWS ===
{initial_summary}

=== RESEARCH FINDINGS ===
{research_findings}
"""


from services.utils import retry_on_error

# ── Helpers ──────────────────────────────────────────────────────────────────

@retry_on_error(max_retries=3, delay=2, backoff=2)
def _grounded_query(client: genai.Client, question: str) -> str:
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
    response = client.models.generate_content(
        model="gemma-4-31b-it",
        contents=prompt,
        config=GenerateContentConfig(temperature=0),
    )
    return response.text or ""


def _parse_json(raw: str) -> dict:
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
        return {}


# ── Node function ────────────────────────────────────────────────────────────

def quantitative_analyst_node(state: AgentState) -> dict:
    """
    Research stock financials using Gemma 4 + Google Search grounding,
    produce a buy_probability score, and generate a PDF report.
    """
    print("=" * 60)
    print("[NODE] quantitative_analyst_node -- entered")
    print("=" * 60)

    symbol = state.get("current_stock", "")
    profile = state.get("stock_profile", {})
    prices = state.get("stock_prices", {})
    quote = prices.get("quote", {})
    quant_data = state.get("quant_data", {})
    company_name = profile.get("name", symbol)

    if not symbol:
        print("[quant_analyst] No current_stock -- skipping")
        return {}

    print(f"[quant_analyst] Analysing financials for: "
          f"{company_name} ({symbol})")

    # ── 1) Build research questions ──────────────────────────────────────
    questions = _build_research_questions(symbol, company_name, quant_data)
    print(f"[quant_analyst] Prepared {len(questions)} research questions")

    # ── 2) Ask each question with Google Search grounding ────────────────
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    research_qa: list[dict] = []
    DELAY_BETWEEN_CALLS = 4

    for i, q in enumerate(questions, 1):
        print(f"[quant_analyst]   Q{i}/{len(questions)}: {q['topic']}...")
        try:
            answer = _grounded_query(client, q["question"])
            research_qa.append({
                "topic": q["topic"],
                "question": q["question"],
                "answer": answer[:1500],
            })
            print(f"[quant_analyst]   A{i}: {answer[:120]}...")
        except Exception as exc:
            print(f"[WARN] Research question {i} failed: {exc}")
            research_qa.append({
                "topic": q["topic"],
                "question": q["question"],
                "answer": f"(research failed: {exc})",
            })
        
        if i < len(questions):
            time.sleep(DELAY_BETWEEN_CALLS)

    # ── 3) Synthesise into final verdict ─────────────────────────────────
    research_text = "\n\n".join(
        f"--- {qa['topic'].upper()} ---\nQ: {qa['question']}\nA: {qa['answer']}"
        for qa in research_qa
    )

    synthesis_input = SYNTHESIS_PROMPT.format(
        symbol=symbol,
        company_name=company_name,
        current_price=quote.get("current_price", "N/A"),
        initial_summary=quant_data.get("summary", "N/A"),
        research_findings=research_text,
    )

    try:
        print("[quant_analyst] Synthesising final verdict...")
        time.sleep(DELAY_BETWEEN_CALLS)
        raw = _plain_query(client, synthesis_input)
        verdict = _parse_json(raw)
    except Exception as exc:
        print(f"[WARN] Verdict synthesis failed: {exc}")
        verdict = {}

    if not verdict or "buy_probability" not in verdict:
        verdict = {
            "buy_probability": 0.5,
            "verdict": "hold",
            "confidence": 0.0,
            "reasoning": "Unable to synthesise verdict; defaulting to hold.",
            "key_factors": [],
            "risks": ["Synthesis parsing failed"],
        }

    # ── 4) Build the full report ─────────────────────────────────────────
    quant_report = {
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

    prob = quant_report["buy_probability"]
    verd = quant_report["verdict"]
    print(f"[quant_analyst] >> VERDICT: {verd} (buy_prob={prob:.2f})")
    
    # ── 5) Generate PDF ──────────────────────────────────────────────────
    try:
        generate_analyst_pdf("Quantitative Analyst", symbol, quant_data, quant_report)
    except Exception as e:
        print(f"[WARN] Failed to generate PDF for Quantitative Analyst: {e}")

    print("[quant_analyst] Done.")
    return {"quant_report": quant_report}
