"""
Stock Watcher Daemon.

Runs 24/7 monitoring active portfolio holdings against their
Stop-Loss and Target Price rules defined in the stock_watcher table.
Automatically executes a SELL order if a threshold is breached.
"""
import time
from datetime import date
import yfinance as yf
from database.crud import (
    get_all_stock_watchers,
    get_portfolio_holding,
    insert_executed_trade,
    insert_ledger_entry,
    update_portfolio_record
)

CHECK_INTERVAL_SECONDS = 30  # Adjust as needed (e.g., 60 for 1 minute)

def _get_stock_price(symbol: str) -> float | None:
    """Fetch the latest real-time/close price using yfinance."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="1d")
        if not df.empty:
            return float(df['Close'].iloc[-1])
    except Exception as e:
        print(f"[ERROR] Could not fetch price for {symbol}: {e}")
    return None

def execute_auto_sell(symbol: str, current_price: float, reason: str):
    """Executes a full sell-off of a holding based on a watcher trigger."""
    holding = get_portfolio_holding(symbol)
    if not holding:
        print(f"[WARN] Auto-sell triggered for {symbol} but no holding found.")
        return
        
    qty = holding.get("total_quantity", 0)
    if qty <= 0:
        return
        
    revenue = qty * current_price
    print(f"\n========================================================")
    print(f"🚨 AUTO-SELL EXECUTED: {symbol} at ${current_price:.2f}")
    print(f"   Reason: {reason}")
    print(f"   Shares: {qty} | Revenue: ${revenue:.2f}")
    print(f"========================================================\n")
    
    # 1. Record executed trade
    insert_executed_trade(symbol, date.today(), qty, current_price)
    
    # 2. Update Ledger
    insert_ledger_entry(revenue, "SELL_STOCK", f"Auto-sell ({reason}): {qty} {symbol} at ${current_price:.2f}")
    
    # 3. Update Portfolio (this triggers ON DELETE CASCADE in stock_watcher)
    update_portfolio_record(symbol, -qty, current_price)


def run_watcher():
    print("==========================================================")
    print("   AUTOTRADE STOCK WATCHER DAEMON STARTED")
    print("   Press Ctrl+C to stop.")
    print("==========================================================")
    
    while True:
        try:
            watchers = get_all_stock_watchers()
            
            if not watchers:
                print(f"[{time.strftime('%H:%M:%S')}] No active stock watchers.")
            else:
                for w in watchers:
                    symbol = w["stock"]
                    stop_loss = w["stop_loss"]
                    target = w["target"]
                    
                    price = _get_stock_price(symbol)
                    if price is None:
                        continue
                        
                    status = f"Price: ${price:.2f} | Stop: ${stop_loss:.2f} | Target: ${target:.2f}"
                    
                    if price <= stop_loss:
                        print(f"[{time.strftime('%H:%M:%S')}] {symbol} -> {status}")
                        execute_auto_sell(symbol, price, "STOP-LOSS TRIGGERED")
                    elif price >= target:
                        print(f"[{time.strftime('%H:%M:%S')}] {symbol} -> {status}")
                        execute_auto_sell(symbol, price, "TARGET PRICE HIT")
                    else:
                        print(f"[{time.strftime('%H:%M:%S')}] {symbol} -> {status} (Monitoring...)")
                        
        except Exception as e:
            print(f"[ERROR] Watcher loop encountered an issue: {e}")
            
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        run_watcher()
    except KeyboardInterrupt:
        print("\n[INFO] Stock Watcher stopped by user.")
