"""
main.py — Autonomous trading workflow graph definition.

Assembles all nodes and edges into a single LangGraph StateGraph that can
be compiled and executed.  The topology mirrors the workflow diagram:

    START
      │
      ▼
    stock_picker
      │
      ▼
    news_aggregator
      │
      ▼
    news_refiner ──────────────────────────────────┐
      │                 │                           │
      ▼                 ▼                           ▼
  algo_predictor   sentiment_analyst        quant_analyst
      ↕                 ↕                           ↕
  algo_tools       sentiment_tools          quant_tools
      │                 │                           │
      └────────► portfolio_manager ◄────────────────┘
                        │
                        ▼
                  execution_agent
                        │
                        ▼
                       END
"""

from langgraph.graph import StateGraph, START, END

from graph.state import AgentState

# ── Node functions ───────────────────────────────────────────────────────────
from graph.nodes import (
    stock_picker_node,
    news_aggregator_node,
    news_refiner_node,
    algorithmic_predictor_node,
    sentiment_analyst_node,
    quantitative_analyst_node,
    portfolio_manager_node,
    execution_agent_node,
    # ToolNode instances
    algorithmic_predictor_tool_node,
    sentiment_analyst_tool_node,
    quantitative_analyst_tool_node,
)


# ── Routing helpers ──────────────────────────────────────────────────────────

def _route_after_analyst(state: AgentState) -> str:
    """
    Shared routing logic for all three analyst nodes.

    If the last message in state contains tool_calls, route to the
    corresponding ToolNode; otherwise proceed to portfolio_manager.

    This function is wrapped per-analyst to return the correct ToolNode name.
    """
    messages = state.get("messages", [])
    if messages and hasattr(messages[-1], "tool_calls") and messages[-1].tool_calls:
        return "use_tools"
    return "portfolio_manager"


# ═══════════════════════════════════════════════════════════════════════════
#  Build the graph
# ═══════════════════════════════════════════════════════════════════════════

def build_graph() -> StateGraph:
    """Construct and return the (uncompiled) StateGraph."""

    workflow = StateGraph(AgentState)

    # ── Register nodes ───────────────────────────────────────────────────
    workflow.add_node("stock_picker",       stock_picker_node)
    workflow.add_node("news_aggregator",    news_aggregator_node)
    workflow.add_node("news_refiner",       news_refiner_node)

    # Analyst nodes
    workflow.add_node("algo_predictor",     algorithmic_predictor_node)
    workflow.add_node("sentiment_analyst",  sentiment_analyst_node)
    workflow.add_node("quant_analyst",      quantitative_analyst_node)

    # ToolNodes (one per analyst)
    workflow.add_node("algo_tools",         algorithmic_predictor_tool_node)
    workflow.add_node("sentiment_tools",    sentiment_analyst_tool_node)
    workflow.add_node("quant_tools",        quantitative_analyst_tool_node)

    # Downstream nodes
    workflow.add_node("portfolio_manager",  portfolio_manager_node)
    workflow.add_node("execution_agent",    execution_agent_node)

    # ── Linear edges (top of the graph) ──────────────────────────────────
    workflow.add_edge(START,                "stock_picker")
    workflow.add_edge("stock_picker",       "news_aggregator")
    workflow.add_edge("news_aggregator",    "news_refiner")

    # ── Fan-out: news_refiner → 3 analyst branches ──────────────────────
    workflow.add_conditional_edges(
        "news_refiner",
        # Always fan-out to all three branches in parallel
        lambda _state: ["algo_predictor", "sentiment_analyst", "quant_analyst"],
        ["algo_predictor", "sentiment_analyst", "quant_analyst"],
    )

    # ── Algorithmic Predictor ↔ ToolNode loop ────────────────────────────
    workflow.add_conditional_edges(
        "algo_predictor",
        _route_after_analyst,
        {
            "use_tools":         "algo_tools",
            "portfolio_manager": "portfolio_manager",
        },
    )
    workflow.add_edge("algo_tools", "algo_predictor")

    # ── Sentiment Analyst ↔ ToolNode loop ────────────────────────────────
    workflow.add_conditional_edges(
        "sentiment_analyst",
        _route_after_analyst,
        {
            "use_tools":         "sentiment_tools",
            "portfolio_manager": "portfolio_manager",
        },
    )
    workflow.add_edge("sentiment_tools", "sentiment_analyst")

    # ── Quantitative Analyst ↔ ToolNode loop ─────────────────────────────
    workflow.add_conditional_edges(
        "quant_analyst",
        _route_after_analyst,
        {
            "use_tools":         "quant_tools",
            "portfolio_manager": "portfolio_manager",
        },
    )
    workflow.add_edge("quant_tools", "quant_analyst")

    # ── Linear edges (bottom of the graph) ───────────────────────────────
    workflow.add_edge("portfolio_manager", "execution_agent")
    workflow.add_edge("execution_agent",   END)

    return workflow


# ── Compile ──────────────────────────────────────────────────────────────────

graph = build_graph().compile()


# ── Quick sanity check when run directly ─────────────────────────────────────

if __name__ == "__main__":
    print("✓ Graph compiled successfully!\n")
    print(graph.get_graph().draw_ascii())
