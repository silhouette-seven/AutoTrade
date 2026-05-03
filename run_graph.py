"""
Main Entry Point to execute the Autonomous Trading Workflow.

Run this script to trigger a complete pipeline execution:
1. Stock Picker selects a stock.
2. News Aggregator fetches context.
3. Analysts (Quant, Sentiment, Algo) research the stock.
4. Portfolio Manager synthesises the decision.
5. Execution Agent executes the trade in the database.
"""

from graph.main import graph
from database.models import init_db
from database.crud import get_current_balance

def main():
    print("========================================================")
    print("      AUTOTRADE PIPELINE INITIALIZATION")
    print("========================================================\n")
    
    # 1. Ensure Database is setup
    init_db()

    # 2. Check initial state
    initial_cash = get_current_balance()
    print(f"Starting Cash Balance: ${initial_cash:,.2f}")
    print("\n--- INITIATING LANGGRAPH WORKFLOW ---\n")

    # 3. Run Graph
    # The graph expects a state dict with an optional messages array.
    initial_state = {"messages": []}
    final_state = graph.invoke(initial_state)

    print("\n--- WORKFLOW FINISHED ---\n")
    
    # 4. Display Summary
    final_cash = get_current_balance()
    selected_stock = final_state.get('current_stock', 'Unknown')
    decision = final_state.get('portfolio_decision', {})
    
    action = decision.get('action', 'NONE')
    qty = decision.get('quantity_to_trade', 0)
    
    print("================ SUMMARY ================")
    print(f"Selected Stock: {selected_stock}")
    print(f"Action Taken:   {action} {qty} shares")
    print(f"Final Cash:     ${final_cash:,.2f}")
    print("=========================================\n")

if __name__ == "__main__":
    main()
