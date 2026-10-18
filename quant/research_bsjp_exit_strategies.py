import requests
import json
import pymysql
import pandas as pd
import numpy as np
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path

JKT = timezone(timedelta(hours=7))

def tick(price):
    if price < 200:
        return 1
    elif price < 500:
        return 2
    elif price < 2000:
        return 5
    elif price < 5000:
        return 10
    else:
        return 25

def down(price):
    t = tick(price)
    return math.floor((price + 1e-9) / t) * t

def up(price):
    t = tick(price)
    return math.ceil((price - 1e-9) / t) * t

def net_pnl_pct(entry, exit_price, friction_bps=10):
    cost = entry * 1.0015
    proceeds = exit_price * (0.9975 - friction_bps / 10000.0)
    return (proceeds / cost - 1) * 100

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
        df = pd.DataFrame(cur.fetchall())
        df["date"] = pd.to_datetime(df["date"])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        df["value"] = df["close"] * df["volume"]
        return df

def fetch_intraday_bars(ticker, interval="5m", period="60d"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}.JK"
    r = requests.get(url, params={"range": period, "interval": interval}, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    data = r.json()["chart"]["result"][0]
    q = data["indicators"]["quote"][0]
    ts = data.get("timestamp", [])
    rows = []
    for i, t in enumerate(ts):
        vals = {k: q[k][i] for k in ["open", "high", "low", "close", "volume"]}
        if any(vals[k] is None or vals[k] <= 0 for k in ["open", "high", "low", "close"]):
            continue
        dt = datetime.fromtimestamp(t, JKT)
        rows.append({
            "date": str(dt.date()),
            "time": dt.strftime("%H:%M"),
            "timestamp": dt.isoformat(),
            "open": float(vals["open"]),
            "high": float(vals["high"]),
            "low": float(vals["low"]),
            "close": float(vals["close"]),
            "volume": float(vals["volume"])
        })
    return rows

print("Loading data...")
df_swid = get_daily("SWID")
df_baja = get_daily("BAJA")
intra_swid_5m = fetch_intraday_bars("SWID", "5m", "60d")
intra_baja_5m = fetch_intraday_bars("BAJA", "5m", "60d")

print(f"Loaded: SWID {len(df_swid)} daily, {len(intra_swid_5m)} 5m; BAJA {len(df_baja)} daily, {len(intra_baja_5m)} 5m")

# Group intraday bars by date
def group_intraday(bars):
    by_date = {}
    for b in bars:
        d = b["date"]
        if d not in by_date:
            by_date[d] = []
        by_date[d].append(b)
    return by_date

intra_swid_by_date = group_intraday(intra_swid_5m)
intra_baja_by_date = group_intraday(intra_baja_5m)

def backtest_macro_daily_exits(df, ticker):
    """
    Simulates all daily BSJP signals on all available history with various exit models.
    """
    df = df.copy()
    df["prev_close"] = df["close"].shift(1)
    df["prev_vol"] = df["volume"].shift(1)
    df["ret_1d"] = (df["close"] / df["prev_close"] - 1) * 100
    df["vol_ratio"] = df["volume"] / df["prev_vol"]
    
    cond = (
        (df["close"] > df["open"]) &
        (df["ret_1d"] >= 3.0) &
        (df["vol_ratio"] >= 1.5) &
        (df["value"] >= 1e8)
    )
    
    results = []
    for i in range(len(df) - 1):
        if cond.iloc[i]:
            entry_date = df["date"].iloc[i]
            entry = df["close"].iloc[i]
            nxt = df.iloc[i+1]
            nxt_date = nxt["date"]
            O = nxt["open"]
            H = nxt["high"]
            L = nxt["low"]
            C = nxt["close"]
            
            # Model 1: OPEN (Jual lelang 09:00)
            ret_open = net_pnl_pct(entry, O)
            
            # Model 2: TP +2.5% vs SL -3.0%
            tp25 = up(entry * 1.025)
            sl3 = down(entry * 0.970)
            if O >= tp25:
                exit_tp25 = O
                type_tp25 = "gap_tp"
            elif O <= sl3:
                exit_tp25 = O
                type_tp25 = "gap_sl"
            elif H >= tp25 and L <= sl3:
                # Ambiguous: conservative assumption hits SL first
                exit_tp25 = sl3
                type_tp25 = "ambiguous_sl"
            elif H >= tp25:
                exit_tp25 = tp25
                type_tp25 = "hit_tp"
            elif L <= sl3:
                exit_tp25 = sl3
                type_tp25 = "hit_sl"
            else:
                exit_tp25 = C
                type_tp25 = "close_exit"
            ret_tp25 = net_pnl_pct(entry, exit_tp25)
            
            # Model 3: TP +3.5% vs SL -3.0%
            tp35 = up(entry * 1.035)
            if O >= tp35:
                exit_tp35 = O
            elif O <= sl3:
                exit_tp35 = O
            elif H >= tp35 and L <= sl3:
                exit_tp35 = sl3
            elif H >= tp35:
                exit_tp35 = tp35
            elif L <= sl3:
                exit_tp35 = sl3
            else:
                exit_tp35 = C
            ret_tp35 = net_pnl_pct(entry, exit_tp35)

            # Model 4: TP +5.0% vs SL -3.0%
            tp50 = up(entry * 1.050)
            if O >= tp50:
                exit_tp50 = O
            elif O <= sl3:
                exit_tp50 = O
            elif H >= tp50 and L <= sl3:
                exit_tp50 = sl3
            elif H >= tp50:
                exit_tp50 = tp50
            elif L <= sl3:
                exit_tp50 = sl3
            else:
                exit_tp50 = C
            ret_tp50 = net_pnl_pct(entry, exit_tp50)
            
            # Model 5: Split 50/50 (50% di Open, 50% di TP 2.5% / SL 3.0%)
            ret_split_50 = 0.5 * ret_open + 0.5 * ret_tp25
            
            # Model 6: Close H+1
            ret_close = net_pnl_pct(entry, C)
            
            # Metrics
            results.append({
                "ticker": ticker,
                "entry_date": str(entry_date.date()),
                "next_date": str(nxt_date.date()),
                "entry": entry,
                "open": O,
                "high": H,
                "low": L,
                "close": C,
                "ret_open": ret_open,
                "ret_tp25": ret_tp25,
                "ret_tp35": ret_tp35,
                "ret_tp50": ret_tp50,
                "ret_split_50": ret_split_50,
                "ret_close": ret_close,
                "max_high_pct": (H / entry - 1) * 100,
                "hit_tp25": bool(H >= tp25),
                "hit_sl3": bool(L <= sl3)
            })
    return pd.DataFrame(results)

def backtest_intraday_micro_exits(bars_by_date, df, ticker):
    """
    Tests exact 5m intraday path (09:00 - 15:50) for all recent BSJP signals that have intraday bars.
    Evaluates:
    - OPEN (09:00)
    - TRAILING STOP 1.5% and 2.0% (both starting at open and starting at 09:05)
    - BREAKOUT HIGH MENIT PERTAMA (09:00 high + 1 tick) then TRAIL 2%
    - TIME EXIT 09:15 WIB
    - TIME EXIT 11:30 WIB (Sesi 1 Close)
    """
    df = df.copy()
    df["prev_close"] = df["close"].shift(1)
    df["prev_vol"] = df["volume"].shift(1)
    df["ret_1d"] = (df["close"] / df["prev_close"] - 1) * 100
    df["vol_ratio"] = df["volume"] / df["prev_vol"]
    
    cond = (
        (df["close"] > df["open"]) &
        (df["ret_1d"] >= 3.0) &
        (df["vol_ratio"] >= 1.5) &
        (df["value"] >= 1e8)
    )
    
    micro_results = []
    
    for i in range(len(df) - 1):
        if cond.iloc[i]:
            entry = df["close"].iloc[i]
            nxt_date_str = str(df["date"].iloc[i+1].date())
            
            if nxt_date_str not in bars_by_date:
                continue
            
            day_bars = bars_by_date[nxt_date_str]
            if len(day_bars) < 5:
                continue
                
            O = day_bars[0]["open"]
            sl_hard = down(entry * 0.970)
            
            # 1. Exit Open
            ret_open = net_pnl_pct(entry, O)
            
            # 2. Trail 2% directly from open
            # Simulate intrabar: open, high, low, close
            peak = O
            exit_trail2 = None
            for b in day_bars:
                stop = down(peak * 0.98)
                if b["open"] <= stop:
                    exit_trail2 = b["open"]; break
                peak = max(peak, b["high"])
                stop = down(peak * 0.98)
                if b["low"] <= stop:
                    exit_trail2 = stop; break
                if b["time"] >= "15:45":
                    exit_trail2 = b["close"]; break
            if exit_trail2 is None: exit_trail2 = day_bars[-1]["close"]
            ret_trail2 = net_pnl_pct(entry, exit_trail2)

            # 3. Trail 2% START AT 09:15 (tahan gejolak 15 menit pertama)
            peak_915 = O
            exit_trail_delay = None
            for b in day_bars:
                if b["time"] < "09:15":
                    # Hanya hard stop -3%
                    if b["low"] <= sl_hard:
                        exit_trail_delay = sl_hard; break
                    peak_915 = max(peak_915, b["high"])
                else:
                    stop = down(peak_915 * 0.98)
                    if b["open"] <= stop:
                        exit_trail_delay = b["open"]; break
                    peak_915 = max(peak_915, b["high"])
                    stop = down(peak_915 * 0.98)
                    if b["low"] <= stop:
                        exit_trail_delay = stop; break
                    if b["time"] >= "15:45":
                        exit_trail_delay = b["close"]; break
            if exit_trail_delay is None: exit_trail_delay = day_bars[-1]["close"]
            ret_trail_delay = net_pnl_pct(entry, exit_trail_delay)

            # 4. Breakout Menit Pertama (09:00 - 09:05 high + 1 tick) then Trail 2%, else exit 09:15
            first_bar = day_bars[0]
            trigger_level = first_bar["high"] + tick(first_bar["high"])
            activated = False
            exit_breakout = None
            peak_bo = trigger_level
            for b in day_bars[1:]:
                if not activated:
                    if b["low"] <= sl_hard:
                        exit_breakout = sl_hard; break
                    if b["high"] >= trigger_level:
                        activated = True
                        peak_bo = max(trigger_level, b["high"])
                    elif b["time"] >= "09:15":
                        # Kalau sampai 09:15 tidak breakout, exit di market!
                        exit_breakout = b["open"]; break
                else:
                    stop = down(peak_bo * 0.98)
                    if b["open"] <= stop:
                        exit_breakout = b["open"]; break
                    peak_bo = max(peak_bo, b["high"])
                    stop = down(peak_bo * 0.98)
                    if b["low"] <= stop:
                        exit_breakout = stop; break
                    if b["time"] >= "15:45":
                        exit_breakout = b["close"]; break
            if exit_breakout is None: exit_breakout = day_bars[-1]["close"]
            ret_breakout = net_pnl_pct(entry, exit_breakout)

            # 5. Exit Time 09:15
            bar_915 = next((b for b in day_bars if b["time"] >= "09:15"), day_bars[-1])
            ret_915 = net_pnl_pct(entry, bar_915["open"])

            # 6. Exit Sesi 1 Close (11:30)
            bar_1130 = next((b for b in day_bars if b["time"] >= "11:30"), day_bars[-1])
            ret_1130 = net_pnl_pct(entry, bar_1130["close"])
            
            # Find when the High occurred
            highest_bar = max(day_bars, key=lambda x: x["high"])
            
            micro_results.append({
                "ticker": ticker,
                "date": nxt_date_str,
                "entry": entry,
                "ret_open": ret_open,
                "ret_trail2_direct": ret_trail2,
                "ret_trail_delay915": ret_trail_delay,
                "ret_breakout": ret_breakout,
                "ret_915": ret_915,
                "ret_1130": ret_1130,
                "high_time": highest_bar["time"],
                "high_pct": (highest_bar["high"] / entry - 1) * 100
            })
            
    return pd.DataFrame(micro_results)

# Run Macro
res_swid = backtest_macro_daily_exits(df_swid, "SWID")
res_baja = backtest_macro_daily_exits(df_baja, "BAJA")

# Run Micro
micro_swid = backtest_intraday_micro_exits(intra_swid_by_date, df_swid, "SWID")
micro_baja = backtest_intraday_micro_exits(intra_baja_by_date, df_baja, "BAJA")

def summarize_exits(df_res, label):
    models = ["ret_open", "ret_tp25", "ret_tp35", "ret_tp50", "ret_split_50", "ret_close"]
    names = ["1. Jual OPEN (09:00)", "2. TP +2.5% / SL -3%", "3. TP +3.5% / SL -3%", "4. TP +5.0% / SL -3%", "5. Split 50% Open + 50% TP2.5", "6. Close Sore H+1"]
    summary = []
    n = len(df_res)
    for m, name in zip(models, names):
        s = df_res[m]
        win = (s > 0).mean() * 100
        mean = s.mean()
        med = s.median()
        worst = s.min()
        best = s.max()
        profit_factor = (s[s > 0].sum() / abs(s[s < 0].sum())) if (s < 0).sum() != 0 else math.nan
        summary.append({
            "Metode": name,
            "Win Rate": f"{win:.1f}%",
            "Mean Net": f"{mean:+.2f}%",
            "Median Net": f"{med:+.2f}%",
            "Worst Trade": f"{worst:.2f}%",
            "Best Trade": f"{best:.2f}%",
            "Profit Factor": f"{profit_factor:.2f}"
        })
    print(f"\n=== MACRO EXIT AUDIT: {label} (N={n} Sinyal Historis) ===")
    print(pd.DataFrame(summary).to_string(index=False))

summarize_exits(res_swid, "SWID")
summarize_exits(res_baja, "BAJA")

combined_macro = pd.concat([res_swid, res_baja])
summarize_exits(combined_macro, "GABUNGAN SWID & BAJA")

def summarize_micro(df_micro, label):
    if df_micro.empty:
        print(f"\nMicro {label}: Tidak ada data intraday cukup.")
        return
    models = ["ret_open", "ret_trail2_direct", "ret_trail_delay915", "ret_breakout", "ret_915", "ret_1130"]
    names = [
        "1. Open 09:00", 
        "2. Trailing 2% Langsung (Sejak 09:00)", 
        "3. Trailing 2% Mulai 09:15", 
        "4. Breakout Menit-1 + Trail 2%", 
        "5. Time Exit 09:15", 
        "6. Time Exit 11:30 (Sesi 1)"
    ]
    summary = []
    n = len(df_micro)
    for m, name in zip(models, names):
        s = df_micro[m]
        win = (s > 0).mean() * 100
        mean = s.mean()
        med = s.median()
        worst = s.min()
        best = s.max()
        summary.append({
            "Metode Intraday": name,
            "Win Rate": f"{win:.1f}%",
            "Mean Net": f"{mean:+.2f}%",
            "Median Net": f"{med:+.2f}%",
            "Worst Trade": f"{worst:.2f}%",
            "Best Trade": f"{best:.2f}%"
        })
    print(f"\n=== MICRO INTRADAY EXIT AUDIT: {label} (N={n} Sinyal Terakhir) ===")
    print(pd.DataFrame(summary).to_string(index=False))
    print(f"Jam Puncak High H+1 ({label}):")
    print(df_micro["high_time"].value_counts().head(5).to_string())

summarize_micro(micro_swid, "SWID")
summarize_micro(micro_baja, "BAJA")
combined_micro = pd.concat([micro_swid, micro_baja])
summarize_micro(combined_micro, "GABUNGAN SWID & BAJA (INTRADAY)")
