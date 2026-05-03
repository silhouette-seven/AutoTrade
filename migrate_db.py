"""
Migration script to convert the portfolio table and seed the XOM stock watcher.
"""
import sqlite3
from database.models import init_db, get_connection
from database.crud import update_portfolio_record, upsert_stock_watcher

def migrate():
    print("Migrating database...")
    
    conn = get_connection()
    
    # 1. Fetch existing portfolio data for XOM
    # In the current DB schema, it was append-only ledger. We sum it up.
    print("Fetching existing portfolio data...")
    row = conn.execute(
        "SELECT stock, SUM(quantity) as qty, "
        "SUM(quantity * average_price) / SUM(quantity) as avg_price "
        "FROM portfolio WHERE stock = 'XOM' GROUP BY stock"
    ).fetchone()
    
    xom_qty = 0
    xom_avg = 0.0
    if row and row['qty'] > 0:
        xom_qty = row['qty']
        xom_avg = row['avg_price']
        print(f"Found XOM holding: {xom_qty} shares at ${xom_avg:.2f}")
    else:
        print("No active XOM holding found. (Maybe DB is already clean?)")
        
    # 2. Drop the old portfolio table (this will destroy the ledger history, but that's fine for the state migration)
    print("Dropping old portfolio table...")
    conn.execute("DROP TABLE IF EXISTS stock_watcher")
    conn.execute("DROP TABLE IF EXISTS portfolio")
    conn.commit()
    conn.close()
    
    # 3. Run init_db to create the new tables
    print("Initializing new tables...")
    init_db()
    
    # 4. Insert XOM back into the new stateful portfolio table
    if xom_qty > 0:
        print("Restoring XOM holding to new portfolio table...")
        p_id = update_portfolio_record('XOM', xom_qty, xom_avg)
        
        # 5. Insert Stock Watcher entry (+5% target, -4% stop-loss)
        target = xom_avg * 1.05
        stop_loss = xom_avg * 0.96
        print(f"Setting XOM stock watcher: Target ${target:.2f}, Stop Loss ${stop_loss:.2f}")
        upsert_stock_watcher('XOM', stop_loss, target, p_id)
        
    print("Migration complete!")

if __name__ == "__main__":
    migrate()
