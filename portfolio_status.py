"""
portfolio_status.py - CLI tool to view real-time portfolio status.

Run this script to see your current cash balance, active holdings,
and total account value.
"""

import sys
import sqlite3
import pandas as pd
from database.models import DB_PATH
from database.crud import get_current_balance, get_full_portfolio, get_latest_price

def print_separator(char="=", length=80):
    print(char * length)

def main():
    print("\n")
    print_separator()
    print("                AUTOTRADE PORTFOLIO STATUS".center(80))
    print_separator()

    # 1. Fetch Cash Balance
    cash_balance = get_current_balance()
    
    # 2. Fetch Holdings
    holdings = get_full_portfolio()
    
    total_stock_value = 0.0
    
    if not holdings:
        print("\n  No active stock holdings found.\n")
    else:
        # Prepare table data
        table_data = []
        for h in holdings:
            stock = h["stock"]
            qty = h["total_quantity"]
            avg_price = h["avg_price"]
            
            # Get latest price to calculate P/L
            latest_price_row = get_latest_price(stock)
            current_price = latest_price_row["price"] if latest_price_row else avg_price
            
            current_val = qty * current_price
            total_stock_value += current_val
            
            pl_dollars = current_val - (qty * avg_price)
            pl_pct = (pl_dollars / (qty * avg_price)) * 100 if (qty * avg_price) > 0 else 0.0
            
            table_data.append({
                "Stock": stock,
                "Qty": qty,
                "Avg Price": f"${avg_price:.2f}",
                "Curr Price": f"${current_price:.2f}",
                "Value": f"${current_val:.2f}",
                "P/L ($)": f"${pl_dollars:+.2f}",
                "P/L (%)": f"{pl_pct:+.2f}%"
            })
            
        df = pd.DataFrame(table_data)
        # Shift index so it's 1-based instead of 0-based
        df.index = df.index + 1
        print("\n" + df.to_string() + "\n")

    # 3. Print Summary
    print_separator("-")
    print(f"  Available Cash:       ${cash_balance:,.2f}")
    print(f"  Total Stock Value:    ${total_stock_value:,.2f}")
    print(f"  TOTAL ACCOUNT VALUE:  ${(cash_balance + total_stock_value):,.2f}")
    print_separator()
    print("\n")

if __name__ == "__main__":
    main()
