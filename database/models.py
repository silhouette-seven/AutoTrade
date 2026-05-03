"""
database.models — SQLite schema definitions and table creation.

Three tables:
    1. executed_trades    — records of trades that were actually placed
    2. analyzed_trades    — per-stock analysis summaries from every agent
    3. stock_price_history — historical price data used by the pipeline

Run ``init_db()`` once at startup to ensure all tables exist.
"""

import sqlite3
from pathlib import Path

# ── Default database path (project root) ─────────────────────────────────────
DB_PATH: Path = Path(__file__).resolve().parent.parent / "trading.db"


# ── SQL statements ───────────────────────────────────────────────────────────

CREATE_EXECUTED_TRADES = """
CREATE TABLE IF NOT EXISTS executed_trades (
    sno                 INTEGER PRIMARY KEY AUTOINCREMENT,
    stock               TEXT    NOT NULL,
    date                DATE    NOT NULL,
    quantity            INTEGER NOT NULL,
    price               REAL    NOT NULL
);
"""

CREATE_ANALYZED_TRADES = """
CREATE TABLE IF NOT EXISTS analyzed_trades (
    sno                             INTEGER PRIMARY KEY AUTOINCREMENT,
    stock                           TEXT    NOT NULL,
    date                            DATE    NOT NULL,
    quantitative_analyst_summary    TEXT,
    algorithmic_predictor_summary   TEXT,
    sentiment_analyst_summary       TEXT,
    portfolio_manager_summary       TEXT,
    execution_agent_decision        TEXT    CHECK(execution_agent_decision IN ('Yes', 'No'))
);
"""

CREATE_STOCK_PRICE_HISTORY = """
CREATE TABLE IF NOT EXISTS stock_price_history (
    serial_no   INTEGER PRIMARY KEY AUTOINCREMENT,
    stock       TEXT    NOT NULL,
    date        DATE    NOT NULL,
    price       REAL    NOT NULL
);
"""

CREATE_BALANCE_LEDGER = """
CREATE TABLE IF NOT EXISTS balance_ledger (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    date                    DATETIME DEFAULT CURRENT_TIMESTAMP,
    balance_change          REAL    NOT NULL,
    current_total_balance   REAL    NOT NULL,
    change_reason           TEXT    NOT NULL CHECK(change_reason IN ('DEPOSIT', 'WITHDRAWAL', 'BUY_STOCK', 'SELL_STOCK')),
    additional_remarks      TEXT
);
"""

CREATE_PORTFOLIO = """
CREATE TABLE IF NOT EXISTS portfolio (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    stock               TEXT    UNIQUE NOT NULL,
    quantity            INTEGER NOT NULL,
    average_price       REAL    NOT NULL
);
"""

CREATE_STOCK_WATCHER = """
CREATE TABLE IF NOT EXISTS stock_watcher (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    stock           TEXT    NOT NULL,
    stop_loss       REAL    NOT NULL,
    target          REAL    NOT NULL,
    portfolio_id    INTEGER NOT NULL,
    FOREIGN KEY(portfolio_id) REFERENCES portfolio(id) ON DELETE CASCADE
);
"""

# ── Initialization ───────────────────────────────────────────────────────────

def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """
    Open (or create) the SQLite database and return a connection.

    Parameters
    ----------
    db_path : Path | str | None
        Override the default database file location.
    """
    path = str(db_path or DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row          # access columns by name
    conn.execute("PRAGMA journal_mode=WAL")  # better concurrent read perf
    conn.execute("PRAGMA foreign_keys = ON;") # enable cascade deletes
    return conn


def init_db(db_path: Path | str | None = None) -> None:
    """Create all tables if they don't already exist."""
    conn = get_connection(db_path)
    try:
        conn.execute(CREATE_EXECUTED_TRADES)
        conn.execute(CREATE_ANALYZED_TRADES)
        conn.execute(CREATE_STOCK_PRICE_HISTORY)
        conn.execute(CREATE_BALANCE_LEDGER)
        conn.execute(CREATE_PORTFOLIO)
        conn.execute(CREATE_STOCK_WATCHER)
        
        # Insert initial $1000 balance if table is empty
        cursor = conn.execute("SELECT COUNT(*) FROM balance_ledger")
        count = cursor.fetchone()[0]
        if count == 0:
            conn.execute(
                "INSERT INTO balance_ledger (balance_change, current_total_balance, change_reason, additional_remarks) "
                "VALUES (?, ?, ?, ?)",
                (1000.0, 1000.0, 'DEPOSIT', 'Initial deposit for trading account')
            )
            print("[DB] Inserted initial $1000.00 balance into ledger.")
            
        conn.commit()
        print("[DB] All tables initialised successfully.")
    finally:
        conn.close()
