"""
services.realtime — Finnhub WebSocket client for real-time trade data.

Re-exported from services package for convenience:
    from services.realtime import RealtimeTracker, get_realtime_tracker
"""

from services import RealtimeTracker, get_realtime_tracker

__all__ = ["RealtimeTracker", "get_realtime_tracker"]
