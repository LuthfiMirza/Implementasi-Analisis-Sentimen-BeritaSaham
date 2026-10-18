import pymysql
import pandas as pd
import numpy as np
import json
from datetime import datetime

conn = pymysql.connect(host="127.0.0.1", port=3306, user="root", database="sentimena_dashboard", cursorclass=pymysql.cursors.DictCursor)

def get_daily(ticker):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT p.price_date as date, p.open, p.high, p.low, p.close, p.volume
            FROM stock_prices p
            JOIN stocks s ON p.stock_id = s.id
            WHERE s.code = %s
            ORDER BY p.price_date ASC
        """, (ticker,))
        rows = cur.fetchall()
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)
        df["value"] = df["close"] * df["volume"]
        return df

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def backtest_bsjp(df, ticker):
    """
    BSJP Criteria:
    - Close > Open
    - Return >= 3.0% (vs yesterday close)
    - Volume >= 1.5x yesterday volume
    - Value >= 100_000_000
    Exit:
    - Next-day Open (Open Scalp)
    - Next-day TP 2.5% vs SL 3.0%
    - Next-day High (max upside)
    """
    df = df.copy()
    df["prev_close"] = df["close"].shift(1)
    df["prev_vol"] = df["volume"].shift(1)
    df["ret_1d"] = (df["close"] / df["prev_close"] - 1) * 100
    df["vol_ratio"] = df["volume"] / df["prev_vol"]
    
    # BSJP condition
    cond = (
        (df["close"] > df["open"]) &
        (df["ret_1d"] >= 3.0) &
        (df["vol_ratio"] >= 1.5) &
        (df["value"] >= 100_000_000)
    )
    
    trades = []
    # Fees: buy 0.15%, sell 0.25%, friction 0.10%
    # net proceeds = exit * (1 - 0.0025 - 0.0010) = exit * 0.9965
    # total cost = entry * (1 + 0.0015) = entry * 1.0015
    for i in range(len(df) - 1):
        if cond.iloc[i]:
            sig_date = df["date"].iloc[i]
            entry_price = df["close"].iloc[i]
            
            # Next day
            nxt = df.iloc[i+1]
            nxt_date = nxt["date"]
            nxt_open = nxt["open"]
            nxt_high = nxt["high"]
            nxt_low = nxt["low"]
            nxt_close = nxt["close"]
            
            # Exit 1: Open
            net_ret_open = ((nxt_open * 0.9965) / (entry_price * 1.0015) - 1) * 100
            gross_ret_open = (nxt_open / entry_price - 1) * 100
            
            # Exit 2: Next day High
            max_upside = (nxt_high / entry_price - 1) * 100
            
            # Exit 3: TP 2.5% vs SL -3.0% simulation
            tp_price = entry_price * 1.025
            sl_price = entry_price * 0.970
            
            if nxt_open >= tp_price:
                exit_sim = nxt_open
                outcome = "gap_tp"
            elif nxt_open <= sl_price:
                exit_sim = nxt_open
                outcome = "gap_sl"
            elif nxt_high >= tp_price and nxt_low <= sl_price:
                # Ambiguous intraday: conservative assumption hit SL first or 50/50
                exit_sim = sl_price
                outcome = "sl_ambiguous"
            elif nxt_high >= tp_price:
                exit_sim = tp_price
                outcome = "tp"
            elif nxt_low <= sl_price:
                exit_sim = sl_price
                outcome = "sl"
            else:
                exit_sim = nxt_close
                outcome = "close_hold"
                
            net_ret_sim = ((exit_sim * 0.9965) / (entry_price * 1.0015) - 1) * 100
            
            trades.append({
                "ticker": ticker,
                "signal_date": str(sig_date),
                "next_date": str(nxt_date),
                "entry": entry_price,
                "open": nxt_open,
                "high": nxt_high,
                "low": nxt_low,
                "close": nxt_close,
                "gross_open_pct": gross_ret_open,
                "net_open_pct": net_ret_open,
                "max_upside_pct": max_upside,
                "outcome_tp_sl": outcome,
                "net_tp_sl_pct": net_ret_sim
            })
            
    tdf = pd.DataFrame(trades)
    return tdf

def backtest_self_radar(df, ticker):
    """
    SELF_RADAR_V1 Criteria:
    - RSI14 >= 60.0
    - ret_5d >= 5.0%
    - dd_20d >= -5.0% (within 5% of 20-day high)
    Exit:
    - Next-day Open
    - Next-day Close
    - 2-day Close
    - 5-day Close
    """
    df = df.copy()
    df["rsi14"] = calc_rsi(df["close"], 14)
    df["ret_5d"] = (df["close"] / df["close"].shift(5) - 1) * 100
    df["high_20d"] = df["high"].rolling(20).max()
    df["dd_20d"] = (df["close"] / df["high_20d"] - 1) * 100
    
    cond = (
        (df["rsi14"] >= 60.0) &
        (df["ret_5d"] >= 5.0) &
        (df["dd_20d"] >= -5.0)
    )
    
    trades = []
    for i in range(len(df) - 1):
        if cond.iloc[i]:
            sig_date = df["date"].iloc[i]
            entry_price = df["close"].iloc[i]
            
            nxt = df.iloc[i+1]
            net_open = ((nxt["open"] * 0.9965) / (entry_price * 1.0015) - 1) * 100
            net_close = ((nxt["close"] * 0.9965) / (entry_price * 1.0015) - 1) * 100
            max_high = (nxt["high"] / entry_price - 1) * 100
            
            # 2-day and 5-day if available
            ret_2d = ((df["close"].iloc[i+2] * 0.9965) / (entry_price * 1.0015) - 1) * 100 if i+2 < len(df) else None
            ret_5d = ((df["close"].iloc[i+5] * 0.9965) / (entry_price * 1.0015) - 1) * 100 if i+5 < len(df) else None
            
            trades.append({
                "ticker": ticker,
                "signal_date": str(sig_date),
                "entry": entry_price,
                "rsi14": df["rsi14"].iloc[i],
                "ret_5d_sig": df["ret_5d"].iloc[i],
                "dd_20d_sig": df["dd_20d"].iloc[i],
                "net_open_pct": net_open,
                "net_close_pct": net_close,
                "max_high_pct": max_high,
                "net_2d_pct": ret_2d,
                "net_5d_pct": ret_5d
            })
            
    return pd.DataFrame(trades)

def get_current_indicators(df, ticker):
    df = df.copy()
    df["rsi14"] = calc_rsi(df["close"], 14)
    df["ret_1d"] = (df["close"] / df["close"].shift(1) - 1) * 100
    df["ret_2d"] = (df["close"] / df["close"].shift(2) - 1) * 100
    df["ret_5d"] = (df["close"] / df["close"].shift(5) - 1) * 100
    df["high_20d"] = df["high"].rolling(20).max()
    df["dd_20d"] = (df["close"] / df["high_20d"] - 1) * 100
    df["vol_ratio"] = df["volume"] / df["volume"].shift(1)
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    return {
        "ticker": ticker,
        "date": str(last["date"]),
        "open": last["open"],
        "high": last["high"],
        "low": last["low"],
        "close": last["close"],
        "volume": last["volume"],
        "value_m": last["value"] / 1e9,
        "ret_1d_pct": last["ret_1d"],
        "ret_2d_pct": last["ret_2d"],
        "ret_5d_pct": last["ret_5d"],
        "vol_ratio": last["vol_ratio"],
        "rsi14": last["rsi14"],
        "high_20d": last["high_20d"],
        "dd_20d_pct": last["dd_20d"],
        "bsjp_valid": bool(last["close"] > last["open"] and last["ret_1d"] >= 3.0 and last["vol_ratio"] >= 1.5 and last["value"] >= 1e8),
        "self_radar_valid": bool(last["rsi14"] >= 60.0 and last["ret_5d"] >= 5.0 and last["dd_20d"] >= -5.0),
        "gabungan_dd_valid": bool(last["dd_20d"] <= -20.0 or last["ret_2d"] <= -5.0),
        "momentum_valid": bool(last["rsi14"] >= 60.0)
    }

print("=== CURRENT STATUS AS OF 2026-10-13 ===")
for t in ["SWID", "BAJA", "HATM", "BUMI", "ESSA", "BRPT"]:
    df = get_daily(t)
    curr = get_current_indicators(df, t)
    print(json.dumps(curr, indent=2))

print("\n=== BSJP BACKTEST: SWID vs BAJA ===")
for t in ["SWID", "BAJA", "HATM", "BUMI", "ESSA", "BRPT"]:
    df = get_daily(t)
    tdf = backtest_bsjp(df, t)
    if not tdf.empty:
        n = len(tdf)
        win_open = (tdf["net_open_pct"] > 0).mean() * 100
        mean_open = tdf["net_open_pct"].mean()
        median_open = tdf["net_open_pct"].median()
        worst_open = tdf["net_open_pct"].min()
        best_open = tdf["net_open_pct"].max()
        
        win_tp_sl = (tdf["net_tp_sl_pct"] > 0).mean() * 100
        mean_tp_sl = tdf["net_tp_sl_pct"].mean()
        median_tp_sl = tdf["net_tp_sl_pct"].median()
        
        avg_max_upside = tdf["max_upside_pct"].mean()
        high_ge_25 = (tdf["max_upside_pct"] >= 2.5).mean() * 100
        
        # Recent 2026
        tdf_2026 = tdf[tdf["signal_date"] >= "2026-01-01"]
        n_2026 = len(tdf_2026)
        win_open_2026 = (tdf_2026["net_open_pct"] > 0).mean() * 100 if n_2026 else 0
        mean_open_2026 = tdf_2026["net_open_pct"].mean() if n_2026 else 0
        
        print(f"[{t}] N={n} | Open Win={win_open:.1f}% | Open Mean={mean_open:+.2f}% | Open Med={median_open:+.2f}% | Worst={worst_open:.2f}% | Best={best_open:.2f}%")
        print(f"      High >= +2.5% rate: {high_ge_25:.1f}% | Avg High: +{avg_max_upside:.2f}%")
        print(f"      TP2.5/SL3 Win={win_tp_sl:.1f}% | Mean={mean_tp_sl:+.2f}% | Med={median_tp_sl:+.2f}%")
        print(f"      2026 Only: N={n_2026} | Win={win_open_2026:.1f}% | Mean={mean_open_2026:+.2f}%\n")

print("\n=== SELF_RADAR_V1 BACKTEST: HATM vs OTHERS ===")
for t in ["HATM", "SWID", "BAJA"]:
    df = get_daily(t)
    sr_df = backtest_self_radar(df, t)
    if not sr_df.empty:
        n = len(sr_df)
        win_open = (sr_df["net_open_pct"] > 0).mean() * 100
        mean_open = sr_df["net_open_pct"].mean()
        win_close = (sr_df["net_close_pct"] > 0).mean() * 100
        mean_close = sr_df["net_close_pct"].mean()
        avg_high = sr_df["max_high_pct"].mean()
        print(f"[{t} SELF_RADAR] N={n} | Open Win={win_open:.1f}% | Open Mean={mean_open:+.2f}% | Close Win={win_close:.1f}% | Close Mean={mean_close:+.2f}% | Avg Next High={avg_high:+.2f}%")
