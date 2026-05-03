"""
graph — Autonomous Trading Platform workflow package.

Usage:
    from graph import graph
    result = graph.invoke(initial_state)
"""

from graph.main import graph, build_graph

__all__ = ["graph", "build_graph"]
