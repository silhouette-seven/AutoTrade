"""
database — Persistent SQLite storage for the trading platform.

Quick start:
    from database import init_db, insert_executed_trade, get_all_executed_trades

    init_db()                                       # create tables (idempotent)
    insert_executed_trade("AAPL", "2026-04-26", 10, 185.50)
    print(get_all_executed_trades())
"""

from database.models import init_db, get_connection, DB_PATH

from database.crud import (
    # Executed Trades
    insert_executed_trade,
    get_all_executed_trades,
    get_executed_trades_by_stock,
    # Analyzed Trades
    insert_analyzed_trade,
    get_all_analyzed_trades,
    get_analyzed_trades_by_stock,
    # Stock Price History
    insert_stock_price,
    get_price_history,
    get_latest_price,
)

__all__ = [
    # setup
    "init_db",
    "get_connection",
    "DB_PATH",
    # executed trades
    "insert_executed_trade",
    "get_all_executed_trades",
    "get_executed_trades_by_stock",
    # analyzed trades
    "insert_analyzed_trade",
    "get_all_analyzed_trades",
    "get_analyzed_trades_by_stock",
    # stock price history
    "insert_stock_price",
    "get_price_history",
    "get_latest_price",
]
