"""
AgentState -- shared state definition for the trading workflow.

This TypedDict is the single source of truth for data flowing between nodes.
Expand the fields as you implement real business logic.
"""

from typing import Annotated, Any
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    Shared state for the autonomous trading platform.

    Attributes
    ----------
    messages : list[BaseMessage]
        Conversation / inter-node message history.
        Uses the ``add_messages`` reducer so every node can *append*
        messages instead of overwriting the list.
    data : dict[str, Any]
        Generic scratchpad for intermediate results
        (stock picks, news articles, predictions, etc.).
    current_stock : str
        The stock symbol currently being processed through the pipeline.
        Set by the stock_picker node at the start of each run.
    stock_prices : dict[str, Any]
        Price data for the current stock (real-time quote).
        Populated by the news_aggregator node.
    stock_news : list[dict[str, Any]]
        Raw news articles related to the current stock.
        Populated by the news_aggregator node.
    stock_profile : dict[str, Any]
        Company profile metadata (name, industry, market cap, etc.).
        Populated by the news_aggregator node.

    --- Refined data (populated by news_refiner node) ---

    quant_data : dict[str, Any]
        Quantitative information extracted from news: earnings figures,
        revenue numbers, analyst price targets, financial metrics, etc.
        Consumed by the quantitative_analyst node.
    sentiment_data : dict[str, Any]
        Sentiment-relevant information: market mood, media tone,
        bullish/bearish signals, social buzz summaries, etc.
        Consumed by the sentiment_analyst node.
    algo_time_series : dict[str, Any]
        Stock price data organised into a time-series-ready structure
        (timestamps, OHLC, volume, derived features) for future use
        by the algorithmic_predictor node's prediction model.

    --- Analyst outputs ---

    sentiment_report : dict[str, Any]
        The Sentiment Analyst's final report: buy_probability (0-1),
        research Q&A, reasoning, and grounded sources.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    data: dict[str, Any]
    current_stock: str
    stock_prices: dict[str, Any]
    stock_news: list[dict[str, Any]]
    stock_profile: dict[str, Any]

    # Refined data (set by news_refiner)
    quant_data: dict[str, Any]
    sentiment_data: dict[str, Any]
    algo_time_series: dict[str, Any]

    # Analyst outputs
    sentiment_report: dict[str, Any]
    quant_report: dict[str, Any]
    algo_report: dict[str, Any]
    portfolio_decision: dict[str, Any]
