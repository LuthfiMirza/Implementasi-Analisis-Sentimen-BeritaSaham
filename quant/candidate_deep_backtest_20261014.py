#!/usr/bin/env python3
import pymysql
import pandas as pd
import numpy as np
import json

conn = pymysql.connect(
    host="127.0.0.1",
    port=3306,
    user="root",
    database="sentimena_dashboard",
    cursorclass=pymysql.cursors.DictCursor
)

def get_combined_daily(ticker):
    with conn.cursor() as cur:
        # 1. Historical from stock_prices
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

        # 2. Append latest from idx_daily_summaries if not in stock_prices
        cur.execute("""
            SELECT trade_date as date, open, high, low, close, volume
            FROM idx_daily_summaries
            WHERE stock_code = %s AND trade_date > %s
            ORDER BY trade_date ASC
        """, (ticker, df["date"].max()))
        recent_rows = cur.fetchall()
        if recent_rows:
            rdf = pd.DataFrame(recent_rows)
            rdf["date"] = pd.to_datetime(rdf["date"]).dt.date
            rdf["open"] = rdf["open"].astype(float)
            rdf["high"] = rdf["high"].astype(float)
            rdf["low"] = rdf["low"].astype(float)
            rdf["close"] = rdf["close"].astype(float)
            rdf["volume"] = rdf["volume"].astype(float)
            df = pd.concat([df, rdf], ignore_index=True)

        df = df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
        df["value"] = df["close"] * df["volume"]
        return df

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def evaluate_ticker(ticker):
    df = get_combined_daily(ticker)
    if df.empty or len(df) < 30:
        return None
    
    df["prev_close"] = df["close"].shift(1)
    df["prev_vol"] = df["volume"].shift(1)
    df["ret_1d"] = (df["close"] / df["prev_close"] - 1) * 100
    df["vol_ratio"] = df["volume"] / df["prev_vol"]
    df["rsi14"] = calc_rsi(df["close"], 14)
    df["high_20d"] = df["high"].rolling(20).max()
    df["dd_20d"] = (df["close"] / df["high_20d"] - 1) * 100
    df["ret_5d"] = (df["close"] / df["close"].shift(5) - 1) * 100

    last_row = df.iloc[-1]
    
    # 1. Backtest BSJP Criteria:
    # Close > Open, ret_1d >= 3%, vol_ratio >= 1.5, value >= 100M
    bsjp_cond = (
        (df["close"] > df["open"]) &
        (df["ret_1d"] >= 3.0) &
        (df["vol_ratio"] >= 1.5) &
        (df["value"] >= 100_000_000)
    )
    
    bsjp_trades = []
    # Fee: buy 0.15%, sell 0.25%, friction 0.10%
    for i in range(len(df) - 1):
        if bsjp_cond.iloc[i]:
            entry = df["close"].iloc[i]
            nxt = df.iloc[i+1]
            net_open = ((nxt["open"] * 0.9965) / (entry * 1.0015) - 1) * 100
            max_high = (nxt["high"] / entry - 1) * 100
            
            tp_price = entry * 1.025
            sl_price = entry * 0.970
            if nxt["open"] >= tp_price:
                net_tpsl = ((nxt["open"] * 0.9965) / (entry * 1.0015) - 1) * 100
                hit = "GAP_TP"
            elif nxt["open"] <= sl_price:
                net_tpsl = ((nxt["open"] * 0.9965) / (entry * 1.0015) - 1) * 100
                hit = "GAP_SL"
            elif nxt["high"] >= tp_price and nxt["low"] <= sl_price:
                net_tpsl = ((sl_price * 0.9965) / (entry * 1.0015) - 1) * 100
                hit = "SL_AMBIGUOUS"
            elif nxt["high"] >= tp_price:
                net_tpsl = ((tp_price * 0.9965) / (entry * 1.0015) - 1) * 100
                hit = "TP"
            elif nxt["low"] <= sl_price:
                net_tpsl = ((sl_price * 0.9965) / (entry * 1.0015) - 1) * 100
                hit = "SL"
            else:
                net_tpsl = ((nxt["close"] * 0.9965) / (entry * 1.0015) - 1) * 100
                hit = "HOLD_CLOSE"
                
            bsjp_trades.append({
                "date": df["date"].iloc[i],
                "net_open": net_open,
                "net_tpsl": net_tpsl,
                "max_high": max_high,
                "hit": hit
            })
            
    bdf = pd.DataFrame(bsjp_trades)
    
    # 2. Backtest Swing Momentum (RSI >= 60)
    mom_cond = (df["rsi14"] >= 60.0)
    mom_trades = []
    for i in range(len(df) - 5):
        if mom_cond.iloc[i]:
            entry = df["close"].iloc[i]
            ret_1d = ((df["close"].iloc[i+1] * 0.9965) / (entry * 1.0015) - 1) * 100
            ret_2d = ((df["close"].iloc[i+2] * 0.9965) / (entry * 1.0015) - 1) * 100
            ret_5d = ((df["close"].iloc[i+5] * 0.9965) / (entry * 1.0015) - 1) * 100
            max_5d = (df["high"].iloc[i+1:i+6].max() / entry - 1) * 100
            mom_trades.append({
                "date": df["date"].iloc[i],
                "ret_1d": ret_1d,
                "ret_2d": ret_2d,
                "ret_5d": ret_5d,
                "max_5d": max_5d
            })
    mdf = pd.DataFrame(mom_trades)
    
    return {
        "ticker": ticker,
        "current_date": str(last_row["date"]),
        "current_close": last_row["close"],
        "current_ret_1d": last_row["ret_1d"],
        "current_vol_ratio": last_row["vol_ratio"],
        "current_value_bio": last_row["value"] / 1e9,
        "current_rsi14": last_row["rsi14"],
        "current_ret_5d": last_row["ret_5d"],
        "current_dd_20d": last_row["dd_20d"],
        "history_bars": len(df),
        "bsjp_stats": {
            "n_signals": len(bdf),
            "open_win_rate": round((bdf["net_open"] > 0).mean() * 100, 1) if not bdf.empty else 0,
            "open_mean_net": round(bdf["net_open"].mean(), 2) if not bdf.empty else 0,
            "open_median_net": round(bdf["net_open"].median(), 2) if not bdf.empty else 0,
            "tpsl_win_rate": round((bdf["net_tpsl"] > 0).mean() * 100, 1) if not bdf.empty else 0,
            "tpsl_mean_net": round(bdf["net_tpsl"].mean(), 2) if not bdf.empty else 0,
            "high_ge_25_pct": round((bdf["max_high"] >= 2.5).mean() * 100, 1) if not bdf.empty else 0,
            "avg_max_high": round(bdf["max_high"].mean(), 2) if not bdf.empty else 0,
        },
        "momentum_stats": {
            "n_signals": len(mdf),
            "win_rate_2d": round((mdf["ret_2d"] > 0).mean() * 100, 1) if not mdf.empty else 0,
            "mean_ret_2d": round(mdf["ret_2d"].mean(), 2) if not mdf.empty else 0,
            "win_rate_5d": round((mdf["ret_5d"] > 0).mean() * 100, 1) if not mdf.empty else 0,
            "mean_ret_5d": round(mdf["ret_5d"].mean(), 2) if not mdf.empty else 0,
            "avg_max_upside_5d": round(mdf["max_5d"].mean(), 2) if not mdf.empty else 0,
        }
    }

candidates = ["BAIK", "BRPT", "HATM", "PANI", "MAPI", "BKDP", "BUMI", "ESSA"]
results = []
for c in candidates:
    res = evaluate_ticker(c)
    if res:
        results.append(res)

print("="*85)
print("HASIL BACKTEST RISET MENDALAM KANDIDAT BSJP & MOMENTUM (14 OKTOBER 2026)")
print("="*85)
for r in results:
    bs = r["bsjp_stats"]
    ms = r["momentum_stats"]
    print(f"\n📌 #{r['ticker']} (Harga: Rp{r['current_close']:,.0f} | 1D: {r['current_ret_1d']:+.2f}% | Vol Spike: {r['current_vol_ratio']:.2f}x | Trx: Rp{r['current_value_bio']:.2f} M | RSI: {r['current_rsi14']:.1f})")
    print(f"   📊 HISTORICAL BSJP (N={bs['n_signals']} sinyal teruji):")
    print(f"      • Win Rate Jual Open (09:00 WIB) : {bs['open_win_rate']}% (Mean Net: {bs['open_mean_net']:+.2f}%)")
    print(f"      • Probabilitas High >= +2.5%     : {bs['high_ge_25_pct']}% (Rerata High H+1: +{bs['avg_max_high']}%)")
    print(f"      • TP 2.5% vs SL 3.0% Win Rate    : {bs['tpsl_win_rate']}% (Mean Net: {bs['tpsl_mean_net']:+.2f}%)")
    print(f"   🚀 SWING MOMENTUM (N={ms['n_signals']} sinyal RSI>=60):")
    print(f"      • 2-Day Hold Win Rate: {ms['win_rate_2d']}% (Mean: {ms['mean_ret_2d']:+.2f}%)")
    print(f"      • 5-Day Hold Win Rate: {ms['win_rate_5d']}% (Mean: {ms['mean_ret_5d']:+.2f}%) | Max Upside 5D: +{ms['avg_max_upside_5d']}%")

# Save detailed JSON for audit
with open("quant/candidate_deep_backtest_20261014.json", "w") as f:
    json.dump(results, f, indent=2)

print("\n" + "="*85)
print("Audit tersimpan di quant/candidate_deep_backtest_20261014.json")
