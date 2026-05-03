"""
Execution Agent node — final node before END.

Takes the portfolio decisions and executes the trades
in the database (updating executed_trades, balance_ledger, portfolio,
and analyzed_trades).
"""

from datetime import date
from graph.state import AgentState
from database.crud import (
    get_current_balance,
    get_portfolio_holding,
    insert_executed_trade,
    insert_ledger_entry,
    update_portfolio_record,
    upsert_stock_watcher,
    insert_analyzed_trade
)

def execution_agent_node(state: AgentState) -> dict:
    """Execute trades based on portfolio decisions."""
    print("=" * 60)
    print("[NODE] execution_agent_node — entered")
    print("=" * 60)

    symbol = state.get("current_stock", "")
    decision = state.get("portfolio_decision", {})
    
    if not symbol or not decision:
        print("[WARN] Missing symbol or decision. Aborting execution.")
        return {}

    action = decision.get("action", "HOLD").upper()
    qty = decision.get("quantity_to_trade", 0)
    
    # We need the current price used by the portfolio manager.
    # Fallback to the real-time quote in state.
    prices = state.get("stock_prices", {})
    current_price = prices.get("quote", {}).get("current_price", 0.0)

    print(f"[execution_agent] Processing {action} for {qty} shares of {symbol} at ${current_price:.2f}")

    trade_id = None
    executed = False

    try:
        if action == "BUY" and qty > 0:
            cash = get_current_balance()
            cost = qty * current_price
            
            if cost > cash:
                print(f"[WARN] Insufficient funds: Cost ${cost:.2f} > Cash ${cash:.2f}. Adjusting qty.")
                qty = int(cash // current_price)
                cost = qty * current_price
            
            if qty > 0:
                print(f"[execution_agent] Executing BUY of {qty} {symbol} for ${cost:.2f}")
                # 1. Record executed trade
                trade_id = insert_executed_trade(symbol, date.today(), qty, current_price)
                # 2. Update Ledger
                insert_ledger_entry(-cost, "BUY_STOCK", f"Bought {qty} shares of {symbol} at ${current_price:.2f}")
                # 3. Update Portfolio
                portfolio_id = update_portfolio_record(symbol, qty, current_price)
                
                # 4. Upsert Stock Watcher Rules
                if portfolio_id:
                    target_price = decision.get("target_price", current_price * 1.05)
                    stop_loss = decision.get("stop_loss", current_price * 0.95)
                    upsert_stock_watcher(symbol, stop_loss, target_price, portfolio_id)
                    print(f"[execution_agent] Set Stock Watcher for {symbol}: Target ${target_price:.2f}, Stop Loss ${stop_loss:.2f}")
                
                executed = True
            else:
                print(f"[WARN] Cannot afford even 1 share of {symbol}.")

        elif action == "SELL" and qty > 0:
            holding = get_portfolio_holding(symbol)
            if not holding:
                print(f"[WARN] Cannot SELL {symbol}: No active holdings found.")
            else:
                held_qty = holding.get("total_quantity", 0)
                if qty > held_qty:
                    print(f"[WARN] Requested to sell {qty} but only hold {held_qty}. Adjusting.")
                    qty = held_qty
                
                if qty > 0:
                    revenue = qty * current_price
                    print(f"[execution_agent] Executing SELL of {qty} {symbol} for ${revenue:.2f}")
                    # 1. Record executed trade
                    trade_id = insert_executed_trade(symbol, date.today(), qty, current_price)
                    # 2. Update Ledger
                    insert_ledger_entry(revenue, "SELL_STOCK", f"Sold {qty} shares of {symbol} at ${current_price:.2f}")
                    # 3. Update Portfolio (Negative quantity to reduce holding)
                    update_portfolio_record(symbol, -qty, current_price)
                    executed = True

        elif action == "HOLD":
            print(f"[execution_agent] Action is HOLD. No trades executed.")
            
    except Exception as e:
        print(f"[ERROR] Trade execution failed: {e}")

    # Record the Analysis Summary
    print("[execution_agent] Logging full analysis to database...")
    try:
        quant_rep = state.get("quant_report", {}).get("reasoning", "")
        algo_rep = state.get("algo_report", {}).get("reasoning", "")
        sent_rep = state.get("sentiment_report", {}).get("reasoning", "")
        port_rep = decision.get("reasoning", "")
        
        insert_analyzed_trade(
            stock=symbol,
            analysis_date=date.today(),
            quantitative_analyst_summary=quant_rep,
            algorithmic_predictor_summary=algo_rep,
            sentiment_analyst_summary=sent_rep,
            portfolio_manager_summary=port_rep,
            execution_agent_decision="Yes" if executed else "No"
        )
    except Exception as e:
        print(f"[ERROR] Failed to log analyzed trade: {e}")

    print("[execution_agent] Done.")
    return {}
