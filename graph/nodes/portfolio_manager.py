"""
Portfolio Manager node.

Receives outputs from all three analyst branches, queries the current
cash balance and portfolio holdings, and uses Gemma 4 to synthesise
an actionable portfolio decision (BUY, SELL, HOLD) along with a target
price and a stop loss.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from dotenv import load_dotenv
from google import genai
from google.genai.types import GenerateContentConfig

from graph.state import AgentState
from database.crud import get_current_balance, get_portfolio_holding, get_full_portfolio
from services.utils import retry_on_error

load_dotenv()

SYNTHESIS_PROMPT = """You are the Lead Portfolio Manager for an autonomous trading platform.
Your job is to review the analysis from three specialised agents (Sentiment, Quantitative, and Algorithmic), check the current cash balance, examine the FULL PORTFOLIO to ensure diversification, and make a final trading decision.

Respond with ONLY a valid JSON object. Do not include markdown formatting or commentary.

{{
  "action": "BUY" | "SELL" | "HOLD",
  "quantity_to_trade": <integer>,
  "target_price": <float>,
  "stop_loss": <float>,
  "reasoning": "<brief paragraph explaining the synthesis, target price logic, and diversification considerations>"
}}

Rules:
1. "action" must be one of: BUY, SELL, HOLD.
2. Calculate "target_price" as a realistic 1-month goal based on the analysts' data.
3. Calculate "stop_loss" as a strict risk management threshold based on current price.
4. "quantity_to_trade" should be based on available cash (if buying) or current holdings (if selling). If HOLD, set to 0. Do NOT risk more than 20% of cash on a single trade.
5. Base your final decision on the consensus of the three analyst buy probabilities (0.0 to 1.0).
6. DIVERSIFICATION: Review the FULL PORTFOLIO. Avoid over-concentrating in a single stock or sector. If the portfolio is already heavily invested in this stock or similar stocks, lean towards HOLD or SELL.

=== STOCK & PORTFOLIO ===
Stock: {symbol} ({company_name})
Current Price: ${current_price}
Available Cash: ${cash_balance}
Current Holding of this stock: {holding_str}

=== FULL PORTFOLIO ===
{full_portfolio_str}

=== 1. SENTIMENT ANALYST ===
Verdict: {sent_verdict} (Prob: {sent_prob})
Reasoning: {sent_reason}

=== 2. QUANTITATIVE ANALYST ===
Verdict: {quant_verdict} (Prob: {quant_prob})
Reasoning: {quant_reason}

=== 3. ALGORITHMIC PREDICTOR ===
Verdict: {algo_verdict} (Prob: {algo_prob})
Reasoning: {algo_reason}
"""

@retry_on_error(max_retries=3, delay=2, backoff=2)
def _query_manager(client: genai.Client, prompt: str) -> str:
    """Send prompt to Gemma 4."""
    response = client.models.generate_content(
        model="gemma-4-31b-it",
        contents=prompt,
        config=GenerateContentConfig(temperature=0.1),
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
        print(f"[WARN] Could not parse Manager JSON: {exc}")
        return {}

def portfolio_manager_node(state: AgentState) -> dict:
    """Synthesise analyst outputs into portfolio decisions."""
    print("=" * 60)
    print("[NODE] portfolio_manager_node — entered")
    print("=" * 60)

    symbol = state.get("current_stock", "")
    if not symbol:
        print("[portfolio_manager] No current_stock -- skipping")
        return {}

    # 1. Gather Data
    profile = state.get("stock_profile", {})
    company_name = profile.get("name", symbol)
    prices = state.get("stock_prices", {})
    current_price = prices.get("quote", {}).get("current_price", 0.0)
    
    sent_rep = state.get("sentiment_report", {})
    quant_rep = state.get("quant_report", {})
    algo_rep = state.get("algo_report", {})
    
    # 2. Get Ledger & Portfolio Data
    cash_balance = get_current_balance()
    holding = get_portfolio_holding(symbol)
    
    if holding:
        h_qty = holding.get("total_quantity", 0)
        h_avg = holding.get("avg_price", 0.0)
        holding_str = f"{h_qty} shares at ${h_avg:.2f} avg"
    else:
        holding_str = "0 shares"
        
    full_portfolio = get_full_portfolio()
    if full_portfolio:
        full_portfolio_lines = []
        for p in full_portfolio:
            full_portfolio_lines.append(f"- {p['stock']}: {p['total_quantity']} shares at ${p['avg_price']:.2f} avg")
        full_portfolio_str = "\n".join(full_portfolio_lines)
    else:
        full_portfolio_str = "No active holdings in the portfolio."

    print(f"[portfolio_manager] Synthesising for {symbol} at ${current_price}")
    print(f"[portfolio_manager] Cash: ${cash_balance:.2f} | Holdings: {holding_str}")

    # 3. Format Prompt
    prompt = SYNTHESIS_PROMPT.format(
        symbol=symbol,
        company_name=company_name,
        current_price=current_price,
        cash_balance=f"{cash_balance:.2f}",
        holding_str=holding_str,
        full_portfolio_str=full_portfolio_str,
        sent_verdict=sent_rep.get("verdict", "N/A"),
        sent_prob=sent_rep.get("buy_probability", 0.5),
        sent_reason=sent_rep.get("reasoning", "N/A"),
        quant_verdict=quant_rep.get("verdict", "N/A"),
        quant_prob=quant_rep.get("buy_probability", 0.5),
        quant_reason=quant_rep.get("reasoning", "N/A"),
        algo_verdict=algo_rep.get("verdict", "N/A"),
        algo_prob=algo_rep.get("buy_probability", 0.5),
        algo_reason=algo_rep.get("reasoning", "N/A"),
    )

    # 4. Call LLM
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    try:
        raw_resp = _query_manager(client, prompt)
        decision = _parse_json(raw_resp)
    except Exception as e:
        print(f"[WARN] Portfolio manager failed: {e}")
        decision = {}

    # 5. Fallback defaults
    if not decision or "action" not in decision:
        decision = {
            "action": "HOLD",
            "quantity_to_trade": 0,
            "target_price": current_price * 1.05,
            "stop_loss": current_price * 0.95,
            "reasoning": "Fallback to HOLD due to LLM synthesis failure.",
        }

    # Add timestamp
    decision["timestamp"] = datetime.now().isoformat()
    
    act = decision.get("action")
    qty = decision.get("quantity_to_trade")
    tp = decision.get("target_price")
    sl = decision.get("stop_loss")
    
    print(f"[portfolio_manager] >> DECISION: {act} {qty} shares")
    print(f"[portfolio_manager] >> Target: ${tp:.2f} | Stop Loss: ${sl:.2f}")
    print(f"[portfolio_manager] >> Reasoning: {decision.get('reasoning')}")
    print("[portfolio_manager] Done.")

    return {"portfolio_decision": decision}
