"""
services.realtime — Finnhub WebSocket client for real-time trade data.

Runs in a background thread and keeps a thread-safe dict of the latest
price for each subscribed symbol.

Usage:
    from services.realtime import RealtimeTracker

    tracker = RealtimeTracker()
    tracker.subscribe("AAPL")
    tracker.start()

    # Later …
    price = tracker.get_latest_price("AAPL")
    tracker.stop()
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any

import websocket                       # websocket-client
from dotenv import load_dotenv

load_dotenv()


class RealtimeTracker:
    """
    Maintains a live WebSocket connection to Finnhub and
    caches the most recent trade price per symbol.
    """

    WS_URL = "wss://ws.finnhub.io"

    def __init__(self) -> None:
        self._api_key: str = os.getenv("FINNHUB_API_KEY", "")
        self._subscriptions: set[str] = set()
        self._latest: dict[str, dict[str, Any]] = {}   # symbol -> {price, volume, timestamp}
        self._lock = threading.Lock()
        self._ws: websocket.WebSocketApp | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    # ── Public API ───────────────────────────────────────────────────────

    def subscribe(self, symbol: str) -> None:
        """Add a symbol to the subscription list."""
        self._subscriptions.add(symbol.upper())
        # If already connected, send a live subscribe message
        if self._ws and self._running:
            self._ws.send(json.dumps({
                "type": "subscribe",
                "symbol": symbol.upper(),
            }))
            print(f"[realtime] Subscribed to {symbol.upper()} (live)")

    def unsubscribe(self, symbol: str) -> None:
        """Remove a symbol from the subscription list."""
        sym = symbol.upper()
        self._subscriptions.discard(sym)
        if self._ws and self._running:
            self._ws.send(json.dumps({
                "type": "unsubscribe",
                "symbol": sym,
            }))

    def get_latest_price(self, symbol: str) -> dict[str, Any] | None:
        """
        Return the latest trade data for ``symbol``, or ``None``
        if no data has arrived yet.

        Returns dict: {"price": float, "volume": float, "timestamp": int}
        """
        with self._lock:
            return self._latest.get(symbol.upper())

    def start(self) -> None:
        """Open the WebSocket in a daemon thread."""
        if self._running:
            return

        url = f"{self.WS_URL}?token={self._api_key}"
        self._ws = websocket.WebSocketApp(
            url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._running = True
        self._thread = threading.Thread(
            target=self._ws.run_forever,
            daemon=True,
            name="finnhub-ws",
        )
        self._thread.start()
        print("[realtime] WebSocket thread started")

    def stop(self) -> None:
        """Gracefully close the WebSocket."""
        self._running = False
        if self._ws:
            self._ws.close()
        print("[realtime] WebSocket stopped")

    # ── WebSocket callbacks ──────────────────────────────────────────────

    def _on_open(self, ws: Any) -> None:
        print(f"[realtime] Connected — subscribing to {len(self._subscriptions)} symbols")
        for sym in self._subscriptions:
            ws.send(json.dumps({"type": "subscribe", "symbol": sym}))

    def _on_message(self, ws: Any, message: str) -> None:
        try:
            payload = json.loads(message)
            if payload.get("type") == "trade":
                for trade in payload.get("data", []):
                    sym = trade.get("s", "")
                    with self._lock:
                        self._latest[sym] = {
                            "price": trade.get("p"),
                            "volume": trade.get("v"),
                            "timestamp": trade.get("t"),
                        }
        except (json.JSONDecodeError, KeyError):
            pass  # silently skip malformed frames

    def _on_error(self, ws: Any, error: Any) -> None:
        print(f"[realtime] WebSocket error: {error}")

    def _on_close(self, ws: Any, close_status: Any = None,
                  close_msg: Any = None) -> None:
        print("[realtime] WebSocket closed")
        self._running = False


# ── Module-level singleton for convenient import ─────────────────────────────

_tracker: RealtimeTracker | None = None


def get_realtime_tracker() -> RealtimeTracker:
    """Return (and lazily create) the global RealtimeTracker singleton."""
    global _tracker
    if _tracker is None:
        _tracker = RealtimeTracker()
    return _tracker
