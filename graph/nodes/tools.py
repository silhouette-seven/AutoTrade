"""
Placeholder tools and ToolNode instances for the three analyst branches.

Each analyst node (Algorithmic Predictor, Sentiment Analyst, Quantitative
Analyst) has its own dedicated ToolNode so the agent ↔ tool loop stays
isolated per branch.
"""

from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode


# ═══════════════════════════════════════════════════════════════════════════
#  Algorithmic Predictor tools
# ═══════════════════════════════════════════════════════════════════════════

@tool
def run_prediction_model(ticker: str) -> str:
    """Run an algorithmic prediction model for the given ticker symbol."""
    # TODO: implement real prediction logic
    return f"[PLACEHOLDER] Prediction result for {ticker}"


algorithmic_predictor_tools = [run_prediction_model]
algorithmic_predictor_tool_node = ToolNode(algorithmic_predictor_tools)


# ═══════════════════════════════════════════════════════════════════════════
#  Sentiment Analyst tools
# ═══════════════════════════════════════════════════════════════════════════

@tool
def analyse_sentiment(text: str) -> str:
    """Analyse the sentiment of a given text snippet."""
    # TODO: implement real sentiment analysis
    return f"[PLACEHOLDER] Sentiment analysis for: {text[:50]}..."


sentiment_analyst_tools = [analyse_sentiment]
sentiment_analyst_tool_node = ToolNode(sentiment_analyst_tools)


# ═══════════════════════════════════════════════════════════════════════════
#  Quantitative Analyst tools
# ═══════════════════════════════════════════════════════════════════════════

@tool
def compute_statistics(ticker: str) -> str:
    """Compute quantitative statistics for the given ticker symbol."""
    # TODO: implement real quantitative computation
    return f"[PLACEHOLDER] Statistics for {ticker}"


quantitative_analyst_tools = [compute_statistics]
quantitative_analyst_tool_node = ToolNode(quantitative_analyst_tools)
