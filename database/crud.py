"""
database.crud — Insert and query helpers for every table.

All functions accept an optional ``db_path`` override so tests can point
at an in-memory or temporary database.  When omitted the project-level
``trading.db`` is used.

Functions follow a consistent pattern:
    insert_*   — insert a single row, return the new rowid
    get_*      — retrieve rows (all, by stock, by date range, …)
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from database.models import get_connection, DB_PATH


# ═══════════════════════════════════════════════════════════════════════════
#  Executed Trades
# ═══════════════════════════════════════════════════════════════════════════

def insert_executed_trade(
    stock: str,
    trade_date: date | str,
    quantity: int,
    price: float,
    *,
    db_path: Path | str | None = None,
) -> int:
    """Insert one executed trade and return its ``sno``."""
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO executed_trades (stock, date, quantity, price) "
            "VALUES (?, ?, ?, ?)",
            (stock, str(trade_date), quantity, price),
        )
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]
    finally:
        conn.close()


def get_all_executed_trades(
    *,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Return every row in ``executed_trades`` as a list of dicts."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT * FROM executed_trades ORDER BY sno").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_executed_trades_by_stock(
    stock: str,
    *,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Return executed trades for a specific stock symbol."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM executed_trades WHERE stock = ? ORDER BY date",
            (stock,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════
#  Analyzed Trades
# ═══════════════════════════════════════════════════════════════════════════

def insert_analyzed_trade(
    stock: str,
    analysis_date: date | str,
    *,
    quantitative_analyst_summary: str | None = None,
    algorithmic_predictor_summary: str | None = None,
    sentiment_analyst_summary: str | None = None,
    portfolio_manager_summary: str | None = None,
    execution_agent_decision: str | None = None,
    db_path: Path | str | None = None,
) -> int:
    """Insert one analysis record and return its ``sno``."""
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO analyzed_trades "
            "(stock, date, quantitative_analyst_summary, "
            " algorithmic_predictor_summary, sentiment_analyst_summary, "
            " portfolio_manager_summary, execution_agent_decision) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                stock,
                str(analysis_date),
                quantitative_analyst_summary,
                algorithmic_predictor_summary,
                sentiment_analyst_summary,
                portfolio_manager_summary,
                execution_agent_decision,
            ),
        )
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]
    finally:
        conn.close()


def get_all_analyzed_trades(
    *,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Return every row in ``analyzed_trades`` as a list of dicts."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT * FROM analyzed_trades ORDER BY sno").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_analyzed_trades_by_stock(
    stock: str,
    *,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Return analysis records for a specific stock symbol."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM analyzed_trades WHERE stock = ? ORDER BY date",
            (stock,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════
#  Stock Price History
# ═══════════════════════════════════════════════════════════════════════════

def insert_stock_price(
    stock: str,
    price_date: date | str,
    price: float,
    *,
    db_path: Path | str | None = None,
) -> int:
    """Insert one price record and return its ``serial_no``."""
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO stock_price_history (stock, date, price) "
            "VALUES (?, ?, ?)",
            (stock, str(price_date), price),
        )
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]
    finally:
        conn.close()


def get_price_history(
    stock: str,
    *,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Return full price history for a stock, oldest first."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM stock_price_history WHERE stock = ? ORDER BY date",
            (stock,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_latest_price(
    stock: str,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Return the most recent price record for a stock, or None."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM stock_price_history "
            "WHERE stock = ? ORDER BY date DESC LIMIT 1",
            (stock,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════
#  Balance Ledger
# ═══════════════════════════════════════════════════════════════════════════

def get_current_balance(
    *,
    db_path: Path | str | None = None,
) -> float:
    """Return the most recent total balance from the ledger."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT current_total_balance FROM balance_ledger ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return float(row['current_total_balance']) if row else 0.0
    finally:
        conn.close()


def insert_ledger_entry(
    balance_change: float,
    change_reason: str,
    additional_remarks: str | None = None,
    *,
    db_path: Path | str | None = None,
) -> int:
    """
    Insert a new ledger entry, automatically calculating the new total balance.
    Returns the new row ID.
    """
    conn = get_connection(db_path)
    try:
        current_balance = get_current_balance(db_path=db_path)
        new_balance = current_balance + balance_change
        
        cur = conn.execute(
            "INSERT INTO balance_ledger (balance_change, current_total_balance, change_reason, additional_remarks) "
            "VALUES (?, ?, ?, ?)",
            (balance_change, new_balance, change_reason, additional_remarks)
        )
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════
#  Portfolio
# ═══════════════════════════════════════════════════════════════════════════

def get_portfolio_holding(
    stock: str,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Return the current holding for a stock."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM portfolio WHERE stock = ?",
            (stock,)
        ).fetchone()
        if row:
            # Re-map keys for backwards compatibility with previous aggregate query
            data = dict(row)
            data["total_quantity"] = data["quantity"]
            data["avg_price"] = data["average_price"]
            return data
        return None
    finally:
        conn.close()


def get_full_portfolio(
    *,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Return all active holdings."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT * FROM portfolio").fetchall()
        result = []
        for r in rows:
            data = dict(r)
            data["total_quantity"] = data["quantity"]
            data["avg_price"] = data["average_price"]
            result.append(data)
        return result
    finally:
        conn.close()


def update_portfolio_record(
    stock: str,
    quantity_change: int,
    current_price: float,
    *,
    db_path: Path | str | None = None,
) -> int | None:
    """
    Update the portfolio state.
    On BUY: calculate new average price and update/insert.
    On SELL: subtract quantity. If quantity <= 0, DELETE row (cascades to watcher).
    Returns the portfolio.id, or None if the holding was deleted.
    """
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT id, quantity, average_price FROM portfolio WHERE stock = ?", (stock,)).fetchone()
        
        if row:
            p_id = row["id"]
            old_qty = row["quantity"]
            old_avg = row["average_price"]
            
            new_qty = old_qty + quantity_change
            
            if new_qty <= 0:
                # Fully sold off, delete the portfolio entry (which triggers ON DELETE CASCADE in stock_watcher)
                conn.execute("DELETE FROM portfolio WHERE id = ?", (p_id,))
                conn.commit()
                return None
                
            if quantity_change > 0:
                # Calculate new weighted average
                new_avg = ((old_qty * old_avg) + (quantity_change * current_price)) / new_qty
            else:
                # Selling doesn't change average buy price
                new_avg = old_avg
                
            conn.execute(
                "UPDATE portfolio SET quantity = ?, average_price = ? WHERE id = ?",
                (new_qty, new_avg, p_id)
            )
            conn.commit()
            return p_id
        else:
            if quantity_change > 0:
                cur = conn.execute(
                    "INSERT INTO portfolio (stock, quantity, average_price) VALUES (?, ?, ?)",
                    (stock, quantity_change, current_price)
                )
                conn.commit()
                return cur.lastrowid
            return None
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════
#  Stock Watcher
# ═══════════════════════════════════════════════════════════════════════════

def upsert_stock_watcher(
    stock: str,
    stop_loss: float,
    target: float,
    portfolio_id: int,
    *,
    db_path: Path | str | None = None,
) -> None:
    """Insert or update the stock watcher thresholds for an active holding."""
    conn = get_connection(db_path)
    try:
        # Check if exists
        row = conn.execute("SELECT id FROM stock_watcher WHERE portfolio_id = ?", (portfolio_id,)).fetchone()
        if row:
            conn.execute(
                "UPDATE stock_watcher SET stop_loss = ?, target = ? WHERE portfolio_id = ?",
                (stop_loss, target, portfolio_id)
            )
        else:
            conn.execute(
                "INSERT INTO stock_watcher (stock, stop_loss, target, portfolio_id) VALUES (?, ?, ?, ?)",
                (stock, stop_loss, target, portfolio_id)
            )
        conn.commit()
    finally:
        conn.close()


def get_all_stock_watchers(
    *,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Fetch all active watcher thresholds."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT * FROM stock_watcher").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


