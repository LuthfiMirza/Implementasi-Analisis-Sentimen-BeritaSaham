"""
Eksperimen Stop Loss Ketat (2% dsb) dan Solusi Mencegah Minus Dalam pada TINS.
Periode: 1 Des 2025 - 21 Sep 2026, Modal Awal: Rp 10.000.000.

Skenario yang diuji:
1. Baseline (Formula Adaptif sebelumnya: TP Overbought, SL 1.0 ATR)
2. Hard Stop Loss 2% kaku (Instruksi User: ketatin SL 2%)
3. Hard Stop Loss 2.5%, 3%, 4%
4. Solusi 1: Break-Even Stop Loss (begitu untung +3%, SL digeser ke modal 0% risiko)
5. Solusi 2: Filter Rezim Trend EMA50 (Hanya masuk saat harga di atas EMA50 / tren sehat, mencegah trade rugi beruntun di fase downtrend)
6. Solusi 3: Kombinasi Optimal (Filter Trend EMA50 + Stop Loss Ketat Terkontrol + Break-Even)
"""
from __future__ import annotations

import pathlib
import numpy as np
import pandas as pd

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CSV_FILE = REPO_ROOT / "data" / "stocks" / "TINS.csv"

STARTING_CAPITAL = 10_000_000
ROUND_TRIP_COST = 0.008
START_DATE = pd.to_datetime("2025-12-01").date()
END_DATE = pd.to_datetime("2026-09-21").date()

df = pd.read_csv(CSV_FILE)
df["date"] = pd.to_datetime(df["date"]).dt.date
df = df.sort_values("date").reset_index(drop=True)

# Indikator
delta = df["close"].diff()
gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
rs = gain / loss.replace(0, np.nan)
df["rsi14"] = 100 - (100 / (1 + rs))

high_low = df["high"] - df["low"]
high_close = (df["high"] - df["close"].shift(1)).abs()
low_close = (df["low"] - df["close"].shift(1)).abs()
tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
df["atr14"] = tr.rolling(14).mean()

df["bb_mid"] = df["close"].rolling(20).mean()
bb_std = df["close"].rolling(20).std()
df["bb_upper"] = df["bb_mid"] + 2 * bb_std
df["bb_lower"] = df["bb_mid"] - 2 * bb_std
df["bb_pct_b"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])

low14 = df["low"].rolling(14).min()
high14 = df["high"].rolling(14).max()
df["stoch_k"] = 100 * (df["close"] - low14) / (high14 - low14)
df["stoch_d"] = df["stoch_k"].rolling(3).mean()

df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

def run_experiment(
    name: str,
    hard_sl_pct: float | None = None,
    use_breakeven: bool = False,
    be_trigger_pct: float = 0.035,
    filter_trend_ema50: bool = False,
    use_atr_ts: bool = True,
    ts_atr_mult: float = 1.0,
):
    trades = []
    in_position = False
    entry_price = 0.0
    entry_date = None
    peak_price = 0.0
    entry_atr = 0.0
    be_active = False

    for i in range(50, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        curr_date = row["date"]

        if curr_date < START_DATE:
            continue
        if curr_date > END_DATE:
            break

        if not in_position:
            # Syarat Entry:
            cond_oversold = (prev["stoch_k"] < 25 or row["stoch_k"] < 25)
            cond_band = (prev["bb_pct_b"] < 0.30 or prev["rsi14"] < 48)
            cond_reversal = (row["close"] > row["open"] and row["close"] > prev["close"])
            
            # Optional Trend Filter (hanya buy saat harga di atas EMA50 atau EMA50 naik)
            cond_trend = True
            if filter_trend_ema50:
                cond_trend = (row["close"] >= row["ema50"] or row["ema50"] > prev["ema50"])

            if cond_oversold and cond_band and cond_reversal and cond_trend:
                in_position = True
                entry_price = row["close"]
                entry_date = curr_date
                peak_price = entry_price
                entry_atr = row["atr14"]
                be_active = False
        else:
            if row["high"] > peak_price:
                peak_price = row["high"]

            # Cek Break-Even Activation
            gain_from_entry = (row["high"] - entry_price) / entry_price
            if use_breakeven and gain_from_entry >= be_trigger_pct:
                be_active = True

            # Cek Kondisi Exit:
            # 1. Take Profit Overbought
            cond_tp = (row["rsi14"] > 68 or row["stoch_k"] > 80 or row["bb_pct_b"] > 0.95)
            
            # 2. Hard Stop Loss dari entry
            cond_hard_sl = False
            if hard_sl_pct is not None:
                loss_pct = (row["close"] - entry_price) / entry_price
                if loss_pct <= -hard_sl_pct:
                    cond_hard_sl = True

            # 3. Break-Even Stop Loss (jika sudah aktif dan harga turun menyentuh entry)
            cond_be_hit = False
            if be_active and row["close"] <= entry_price:
                cond_be_hit = True

            # 4. Trailing Stop
            cond_ts = False
            if use_atr_ts:
                ts_dist = max(0.04, (entry_atr / entry_price) * ts_atr_mult)
                pullback = (row["close"] - peak_price) / peak_price
                if pullback <= -ts_dist:
                    cond_ts = True

            # Eksekusi Exit jika salah satu kena
            if cond_tp or cond_hard_sl or cond_be_hit or cond_ts or i == len(df) - 1:
                exit_price = row["close"]
                exit_date = curr_date

                if cond_tp:
                    reason = "TP (Overbought)"
                elif cond_be_hit:
                    reason = "Break-Even SL (0%)"
                elif cond_hard_sl:
                    reason = f"Hard SL (-{hard_sl_pct*100:.1f}%)"
                elif cond_ts:
                    reason = "Trailing Stop"
                else:
                    reason = "EOD Exit"

                net_ret = (exit_price / entry_price) - 1.0 - ROUND_TRIP_COST
                trades.append({
                    "entry_date": entry_date,
                    "exit_date": exit_date,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "net_ret": net_ret,
                    "reason": reason,
                })
                in_position = False

    cap = STARTING_CAPITAL
    for t in trades:
        cap *= (1 + t["net_ret"])

    n_trades = len(trades)
    if n_trades == 0:
        return {"name": name, "trades": [], "n": 0, "win_rate": 0, "avg_ret": 0, "final_cap": cap, "max_loss": 0}

    rets = [t["net_ret"] for t in trades]
    win_rate = np.mean([r > 0 for r in rets]) * 100
    avg_ret = np.mean(rets) * 100
    losses = [r * 100 for r in rets if r < 0]
    max_loss = min(losses) if losses else 0.0
    avg_loss = np.mean(losses) if losses else 0.0

    return {
        "name": name,
        "trades": trades,
        "n": n_trades,
        "win_rate": win_rate,
        "avg_ret": avg_ret,
        "final_cap": cap,
        "pnl_pct": (cap / STARTING_CAPITAL - 1) * 100,
        "max_loss": max_loss,
        "avg_loss": avg_loss,
    }

# Run all scenarios
scenarios = [
    # 1. Baseline Adaptif
    ("1. Baseline Adaptif (SL 1.0 ATR ~6%)", None, False, 0.035, False, True, 1.0),
    # 2. Hard SL 2% Kaku
    ("2. Hard SL 2% Kaku (Instruksi User)", 0.02, False, 0.035, False, True, 1.0),
    # 3. Hard SL 3%
    ("3. Hard SL 3% Kaku", 0.03, False, 0.035, False, True, 1.0),
    # 4. Hard SL 4%
    ("4. Hard SL 4% Kaku", 0.04, False, 0.035, False, True, 1.0),
    # 5. Baseline + Break-Even (Begitu profit +3.5%, kunci SL di modal)
    ("5. Break-Even Stop Loss (Kunci Modal)", None, True, 0.035, False, True, 1.0),
    # 6. Filter Trend EMA50 (Hindari pisau jatuh di fase downtrend)
    ("6. Filter Trend EMA50 Saham Sehat", None, False, 0.035, True, True, 1.0),
    # 7. Solusi Juara: Filter Trend EMA50 + Break-Even + SL Terkontrol 3.5%
    ("7. KOMBINASI JUARA (Trend + Break-Even + SL 3.5%)", 0.035, True, 0.035, True, True, 1.0),
]

print("=" * 95)
print("  PERBANDINGAN EFEK STOP LOSS KETAT VS SOLUSI ANTI-MINUS DALAM PADA TINS")
print(f"  Periode: {START_DATE} s/d {END_DATE} | Modal Awal: Rp 10.000.000")
print("=" * 95)
print(f"  {'Nama Skenario':<46} {'Trade':>5} {'Win Rate':>9} {'Max Minus':>10} {'Rata Minus':>11} {'Saldo Akhir':>14}")
print(f"  {'-'*46} {'-'*5} {'-'*9} {'-'*10} {'-'*11} {'-'*14}")

results = []
for sc in scenarios:
    res = run_experiment(
        name=sc[0],
        hard_sl_pct=sc[1],
        use_breakeven=sc[2],
        be_trigger_pct=sc[3],
        filter_trend_ema50=sc[4],
        use_atr_ts=sc[5],
        ts_atr_mult=sc[6],
    )
    results.append(res)
    print(f"  {res['name']:<46} {res['n']:>5} {res['win_rate']:>8.1f}% {res['max_loss']:>9.2f}% {res['avg_loss']:>10.2f}% Rp {res['final_cap']:>11,.0f}")

# Detail Trade untuk Skenario 2 (SL 2% Kaku) dan Skenario 7 (Kombinasi Juara)
def print_trade_details(res):
    print("\n" + "=" * 95)
    print(f"  DETAIL TRADE: {res['name']}")
    print("=" * 95)
    print(f"  {'#':<3} {'Entry':<12} {'Exit':<12} {'Alasan Exit':<22} {'Beli':>8} {'Jual':>8} {'Net PnL%':>10} {'Saldo':>15}")
    print(f"  {'-'*3} {'-'*12} {'-'*12} {'-'*22} {'-'*8} {'-'*8} {'-'*10} {'-'*15}")
    c = STARTING_CAPITAL
    for i, t in enumerate(res["trades"], start=1):
        c *= (1 + t["net_ret"])
        print(f"  {i:<3} {str(t['entry_date']):<12} {str(t['exit_date']):<12} {t['reason']:<22} {t['entry_price']:>8,.0f} {t['exit_price']:>8,.0f} {t['net_ret']*100:>+9.2f}% Rp {c:>12,.0f}")

print_trade_details(results[1]) # Hard SL 2%
print_trade_details(results[6]) # Kombinasi Juara
