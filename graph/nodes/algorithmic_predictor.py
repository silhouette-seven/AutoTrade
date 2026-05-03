"""
Algorithmic Predictor node.

Runs algorithmic and technical indicator-based predictions using pure math.
Uses ``yfinance`` to fetch historical daily candles and ``pandas`` to compute:
    - SMA (Simple Moving Average)
    - RSI (Relative Strength Index)
    - MACD (Moving Average Convergence Divergence)

The output is stored in ``state["algo_report"]``.
"""

import pandas as pd
import yfinance as yf
from datetime import datetime

from graph.state import AgentState
from services.reporting import generate_analyst_pdf


def calculate_sma(df: pd.DataFrame, window: int) -> pd.Series:
    """Calculate Simple Moving Average."""
    return df['Close'].rolling(window=window).mean()


def calculate_rsi(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Calculate Relative Strength Index."""
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_macd(df: pd.DataFrame, short_window: int = 12, long_window: int = 26, signal_window: int = 9):
    """Calculate MACD and Signal Line."""
    short_ema = df['Close'].ewm(span=short_window, adjust=False).mean()
    long_ema = df['Close'].ewm(span=long_window, adjust=False).mean()
    macd = short_ema - long_ema
    signal = macd.ewm(span=signal_window, adjust=False).mean()
    return macd, signal


def evaluate_indicators(current_price: float, sma_50: float, sma_200: float, 
                        rsi: float, macd: float, signal: float) -> tuple[float, str, str, list]:
    """
    Evaluate technical indicators to generate a verdict and probability.
    """
    score = 0.0
    factors = []
    
    # 1. Trend (SMA)
    if sma_50 > sma_200:
        score += 0.3
        factors.append("Bullish Trend: SMA-50 is above SMA-200 (Golden Cross territory)")
    elif sma_50 < sma_200:
        score -= 0.3
        factors.append("Bearish Trend: SMA-50 is below SMA-200 (Death Cross territory)")
        
    if current_price > sma_50:
        score += 0.2
        factors.append("Short-term Bullish: Current price is above SMA-50")
    else:
        score -= 0.2
        factors.append("Short-term Bearish: Current price is below SMA-50")
        
    # 2. Momentum (RSI)
    if rsi < 30:
        score += 0.3
        factors.append(f"Oversold: RSI is {rsi:.2f} (Potential bounce)")
    elif rsi > 70:
        score -= 0.3
        factors.append(f"Overbought: RSI is {rsi:.2f} (Potential pullback)")
    else:
        factors.append(f"Neutral Momentum: RSI is {rsi:.2f}")

    # 3. MACD
    if macd > signal:
        score += 0.2
        factors.append("Bullish Momentum: MACD is above Signal line")
    else:
        score -= 0.2
        factors.append("Bearish Momentum: MACD is below Signal line")

    # Normalize score from [-1.0, 1.0] to [0.0, 1.0] probability
    # Base probability is 0.5 (Hold)
    prob = max(0.0, min(1.0, 0.5 + (score / 2.0)))
    
    if prob >= 0.8:
        verdict = "strong_buy"
    elif prob >= 0.6:
        verdict = "buy"
    elif prob <= 0.2:
        verdict = "strong_sell"
    elif prob <= 0.4:
        verdict = "sell"
    else:
        verdict = "hold"
        
    reasoning = (
        f"Algorithmic analysis yields a {verdict.replace('_', ' ').upper()} verdict "
        f"with a {prob*100:.0f}% bullish probability score based on the confluence "
        f"of Trend (SMA), Momentum (RSI), and MACD indicators."
    )
    
    return prob, verdict, reasoning, factors


def algorithmic_predictor_node(state: AgentState) -> dict:
    """Generate algorithmic predictions for the selected stocks."""
    print("=" * 60)
    print("[NODE] algorithmic_predictor_node — entered")
    print("=" * 60)

    symbol = state.get("current_stock", "")
    if not symbol:
        print("[algo_predictor] No current_stock -- skipping")
        return {}

    print(f"[algo_predictor] Fetching historical data for {symbol}...")
    
    try:
        # Fetch 6 months of daily data
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="6mo")
        
        if df.empty or len(df) < 50:
            raise ValueError("Not enough historical data fetched from yfinance.")
            
        print(f"[algo_predictor] Fetched {len(df)} daily candles.")
        
        current_price = df['Close'].iloc[-1]
        
        # Calculate Indicators
        df['SMA_50'] = calculate_sma(df, 50)
        df['SMA_200'] = calculate_sma(df, 200)
        df['RSI'] = calculate_rsi(df, 14)
        macd, signal = calculate_macd(df)
        df['MACD'] = macd
        df['Signal'] = signal
        
        # Extract latest values
        latest = df.iloc[-1]
        sma_50 = float(latest['SMA_50']) if pd.notna(latest['SMA_50']) else current_price
        sma_200 = float(latest['SMA_200']) if pd.notna(latest['SMA_200']) else current_price
        rsi = float(latest['RSI']) if pd.notna(latest['RSI']) else 50.0
        macd_val = float(latest['MACD']) if pd.notna(latest['MACD']) else 0.0
        signal_val = float(latest['Signal']) if pd.notna(latest['Signal']) else 0.0
        
        # Evaluate
        prob, verdict, reasoning, factors = evaluate_indicators(
            current_price, sma_50, sma_200, rsi, macd_val, signal_val
        )
        
        algo_report = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "buy_probability": prob,
            "verdict": verdict,
            "confidence": 1.0,  # Algorithms are mathematical, so confidence in the calculation is 1.0
            "reasoning": reasoning,
            "key_factors": factors,
            "risks": ["Algorithmic trading carries systemic market risks", "Past performance does not guarantee future results"],
            "indicators": {
                "Current Price": f"${current_price:.2f}",
                "SMA (50-day)": f"${sma_50:.2f}",
                "SMA (200-day)": f"${sma_200:.2f}",
                "RSI (14-day)": f"{rsi:.2f}",
                "MACD": f"{macd_val:.2f}",
                "MACD Signal": f"{signal_val:.2f}"
            }
        }
        
    except Exception as e:
        print(f"[WARN] Algorithmic prediction failed: {e}")
        algo_report = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "buy_probability": 0.5,
            "verdict": "hold",
            "confidence": 0.0,
            "reasoning": f"Algorithmic analysis failed due to error: {e}",
            "key_factors": [],
            "risks": ["Data unavailable"],
            "indicators": {}
        }
        
    print(f"[algo_predictor] >> VERDICT: {algo_report['verdict']} (buy_prob={algo_report['buy_probability']:.2f})")
    
    # Generate PDF
    try:
        raw_data_summary = {
            "Data Source": "Yahoo Finance (yfinance)",
            "Period": "Last 6 Months",
            "Interval": "1 Day",
            "Notes": "Using adjusted close prices for indicator calculation."
        }
        generate_analyst_pdf("Algorithmic Predictor", symbol, raw_data_summary, algo_report)
    except Exception as e:
        print(f"[WARN] Failed to generate PDF for Algorithmic Predictor: {e}")

    print("[algo_predictor] Done.")
    return {"algo_report": algo_report}
