"""
Backtest Engine: Stockbit Screener Strategy (Volume Spike + Green Candle + Return >= 3%)
Periode: 1 Desember 2025 s/d 21 September 2026
Modal Awal: Rp 10.000.000
Universe: 111 Saham IDX di Database Sentimena
"""
from __future__ import annotations

import pathlib
import numpy as np
import pandas as pd

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CSV_FILE = REPO_ROOT / "data" / "stock_prices_recent.csv"

START_DATE = pd.to_datetime("2025-12-01").date()
END_DATE = pd.to_datetime("2026-09-21").date()
INITIAL_CAPITAL = 10_000_000.0
BUY_FEE = 0.0015
SELL_FEE = 0.0025

df = pd.read_csv(CSV_FILE)
df["date"] = pd.to_datetime(df["date"]).dt.date
df = df.sort_values(["ticker", "date"]).reset_index(drop=True)

# Indikator
df["prev_close"] = df.groupby("ticker")["close"].shift(1)
df["prev_volume"] = df.groupby("ticker")["volume"].shift(1)
df["return_1d"] = (df["close"] - df["prev_close"]) / df["prev_close"]
df["ma5"] = df.groupby("ticker")["close"].transform(lambda x: x.rolling(5).mean())
df["ma10"] = df.groupby("ticker")["close"].transform(lambda x: x.rolling(10).mean())
df["value"] = df["close"] * df["volume"]
df["vol_ratio"] = df["volume"] / df["prev_volume"].replace(0, np.nan)

# Kriteria Screener Stockbit
cond_vol = df["volume"] > df["prev_volume"]
cond_green = df["close"] > df["open"]
cond_ret = df["return_1d"] >= 0.03
cond_val = df["value"] >= 100_000_000
cond_ma5 = df["close"] >= df["ma5"]

df["screener_pass"] = cond_vol & cond_green & cond_ret & cond_val & cond_ma5

# Create daily lookup dictionaries
price_dict = {}
for _, row in df.iterrows():
    price_dict[(row["ticker"], row["date"])] = {
        "open": row["open"],
        "high": row["high"],
        "low": row["low"],
        "close": row["close"],
        "volume": row["volume"],
        "value": row["value"],
        "vol_ratio": row["vol_ratio"],
        "ma5": row["ma5"],
    }

# All trading dates in chronological order
trading_dates = sorted(df["date"].unique())
trading_dates = [d for d in trading_dates if d >= START_DATE]


def run_fixed_hold_backtest(hold_days: int, rank_by: str = "value", max_slots: int = 1):
    """Backtest dengan fixed holding period (misal H+1, H+3, H+5)."""
    cash = INITIAL_CAPITAL
    slots = [None] * max_slots  # Each slot holds: {"ticker", "buy_price", "buy_date", "shares", "days_held"}
    trade_log = []

    for idx, d in enumerate(trading_dates):
        # 1. Update existing positions & check exit
        for i in range(max_slots):
            pos = slots[i]
            if pos is not None:
                pos["days_held"] += 1
                if pos["days_held"] >= hold_days:
                    # Exit at today's close
                    p_info = price_dict.get((pos["ticker"], d))
                    sell_price = p_info["close"] if p_info else pos["buy_price"]
                    gross_proceeds = pos["shares"] * sell_price
                    net_proceeds = gross_proceeds * (1 - SELL_FEE)
                    cost = pos["cost"]
                    pnl = net_proceeds - cost
                    pnl_pct = pnl / cost

                    cash += net_proceeds
                    trade_log.append({
                        "ticker": pos["ticker"],
                        "entry_date": pos["buy_date"],
                        "exit_date": d,
                        "days_held": pos["days_held"],
                        "entry_price": pos["buy_price"],
                        "exit_price": sell_price,
                        "pnl_pct": pnl_pct,
                        "pnl_rp": pnl,
                        "exit_reason": f"HOLD_{hold_days}D",
                    })
                    slots[i] = None

        # 2. Check for new candidates today
        available_slots = [i for i in range(max_slots) if slots[i] is None]
        if available_slots:
            today_candidates = df[(df["date"] == d) & (df["screener_pass"])].copy()
            # Don't buy same stock if already holding
            held_tickers = {s["ticker"] for s in slots if s is not None}
            today_candidates = today_candidates[~today_candidates["ticker"].isin(held_tickers)]

            if not today_candidates.empty:
                if rank_by == "value":
                    today_candidates = today_candidates.sort_values("value", ascending=False)
                elif rank_by == "vol_ratio":
                    today_candidates = today_candidates.sort_values("vol_ratio", ascending=False)
                elif rank_by == "return":
                    today_candidates = today_candidates.sort_values("return_1d", ascending=False)

                picks = today_candidates.head(len(available_slots))
                for slot_idx, (_, pick) in zip(available_slots, picks.iterrows()):
                    # Allocate portion of cash
                    alloc_cash = cash / (len(available_slots) - available_slots.index(slot_idx))
                    buy_price = pick["close"]
                    cost_per_share = buy_price * (1 + BUY_FEE)
                    shares = int(alloc_cash // cost_per_share)
                    if shares > 0:
                        total_cost = shares * cost_per_share
                        cash -= total_cost
                        slots[slot_idx] = {
                            "ticker": pick["ticker"],
                            "buy_price": buy_price,
                            "buy_date": d,
                            "shares": shares,
                            "cost": total_cost,
                            "days_held": 0,
                            "peak_price": buy_price,
                        }

    # Close any remaining open positions at the last available close
    last_date = trading_dates[-1]
    for i in range(max_slots):
        pos = slots[i]
        if pos is not None:
            p_info = price_dict.get((pos["ticker"], last_date))
            sell_price = p_info["close"] if p_info else pos["buy_price"]
            net_proceeds = pos["shares"] * sell_price * (1 - SELL_FEE)
            pnl = net_proceeds - pos["cost"]
            cash += net_proceeds
            trade_log.append({
                "ticker": pos["ticker"],
                "entry_date": pos["buy_date"],
                "exit_date": last_date,
                "days_held": pos["days_held"] + 1,
                "entry_price": pos["buy_price"],
                "exit_price": sell_price,
                "pnl_pct": pnl / pos["cost"],
                "pnl_rp": pnl,
                "exit_reason": "FINAL_CLOSE",
            })
            slots[i] = None

    return cash, pd.DataFrame(trade_log)


def run_dynamic_trailing_backtest(sl_pct: float = 0.03, trailing_pct: float = 0.025, max_slots: int = 1, rank_by: str = "value"):
    """Backtest dengan Stop Loss 3% & Trailing Stop 2.5% dari Puncak."""
    cash = INITIAL_CAPITAL
    slots = [None] * max_slots
    trade_log = []

    for idx, d in enumerate(trading_dates):
        # 1. Update existing positions & check SL / Trailing Stop
        for i in range(max_slots):
            pos = slots[i]
            if pos is not None:
                p_info = price_dict.get((pos["ticker"], d))
                if p_info:
                    today_high = p_info["high"]
                    today_low = p_info["low"]
                    today_close = p_info["close"]
                    pos["days_held"] += 1

                    # Update peak price
                    if today_high > pos["peak_price"]:
                        pos["peak_price"] = today_high

                    # Check Hard Stop Loss: Low touched entry * (1 - sl_pct)
                    sl_level = pos["buy_price"] * (1 - sl_pct)
                    trailing_level = pos["peak_price"] * (1 - trailing_pct)

                    exit_triggered = False
                    exit_price = None
                    exit_reason = ""

                    if today_low <= sl_level:
                        exit_triggered = True
                        exit_price = sl_level
                        exit_reason = f"SL_{sl_pct*100:.1f}%"
                    elif pos["peak_price"] >= pos["buy_price"] * 1.03 and today_low <= trailing_level:
                        exit_triggered = True
                        exit_price = trailing_level
                        exit_reason = f"TRAILING_{trailing_pct*100:.1f}%"
                    elif pos["days_held"] >= 10:  # Max 10 days time stop
                        exit_triggered = True
                        exit_price = today_close
                        exit_reason = "MAX_10D"

                    if exit_triggered:
                        gross_proceeds = pos["shares"] * exit_price
                        net_proceeds = gross_proceeds * (1 - SELL_FEE)
                        pnl = net_proceeds - pos["cost"]
                        cash += net_proceeds
                        trade_log.append({
                            "ticker": pos["ticker"],
                            "entry_date": pos["buy_date"],
                            "exit_date": d,
                            "days_held": pos["days_held"],
                            "entry_price": pos["buy_price"],
                            "exit_price": exit_price,
                            "pnl_pct": pnl / pos["cost"],
                            "pnl_rp": pnl,
                            "exit_reason": exit_reason,
                        })
                        slots[i] = None

        # 2. Check for new candidates today
        available_slots = [i for i in range(max_slots) if slots[i] is None]
        if available_slots:
            today_candidates = df[(df["date"] == d) & (df["screener_pass"])].copy()
            held_tickers = {s["ticker"] for s in slots if s is not None}
            today_candidates = today_candidates[~today_candidates["ticker"].isin(held_tickers)]

            if not today_candidates.empty:
                if rank_by == "value":
                    today_candidates = today_candidates.sort_values("value", ascending=False)
                elif rank_by == "vol_ratio":
                    today_candidates = today_candidates.sort_values("vol_ratio", ascending=False)

                picks = today_candidates.head(len(available_slots))
                for slot_idx, (_, pick) in zip(available_slots, picks.iterrows()):
                    alloc_cash = cash / (len(available_slots) - available_slots.index(slot_idx))
                    buy_price = pick["close"]
                    cost_per_share = buy_price * (1 + BUY_FEE)
                    shares = int(alloc_cash // cost_per_share)
                    if shares > 0:
                        total_cost = shares * cost_per_share
                        cash -= total_cost
                        slots[slot_idx] = {
                            "ticker": pick["ticker"],
                            "buy_price": buy_price,
                            "buy_date": d,
                            "shares": shares,
                            "cost": total_cost,
                            "days_held": 0,
                            "peak_price": buy_price,
                        }

    # Final close
    last_date = trading_dates[-1]
    for i in range(max_slots):
        pos = slots[i]
        if pos is not None:
            p_info = price_dict.get((pos["ticker"], last_date))
            sell_price = p_info["close"] if p_info else pos["buy_price"]
            net_proceeds = pos["shares"] * sell_price * (1 - SELL_FEE)
            pnl = net_proceeds - pos["cost"]
            cash += net_proceeds
            trade_log.append({
                "ticker": pos["ticker"],
                "entry_date": pos["buy_date"],
                "exit_date": last_date,
                "days_held": pos["days_held"] + 1,
                "entry_price": pos["buy_price"],
                "exit_price": sell_price,
                "pnl_pct": pnl / pos["cost"],
                "pnl_rp": pnl,
                "exit_reason": "FINAL_CLOSE",
            })
            slots[i] = None

    return cash, pd.DataFrame(trade_log)


def print_stats(name: str, final_cash: float, trades: pd.DataFrame):
    if trades.empty:
        print(f"=== {name} ===: No trades generated.")
        return

    n_trades = len(trades)
    wins = trades[trades["pnl_rp"] > 0]
    losses = trades[trades["pnl_rp"] <= 0]
    wr = len(wins) / n_trades * 100
    total_profit = wins["pnl_rp"].sum()
    total_loss = abs(losses["pnl_rp"].sum())
    pf = total_profit / total_loss if total_loss > 0 else np.nan
    ret_total = (final_cash - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    avg_pnl = trades["pnl_pct"].mean() * 100

    print(f"=== {name} ===")
    print(f"Modal Awal   : Rp {INITIAL_CAPITAL:,.0f}")
    print(f"Modal Akhir  : Rp {final_cash:,.0f} ({ret_total:+.2f}%)")
    print(f"Total Trade  : {n_trades} (Win: {len(wins)}, Loss: {len(losses)})")
    print(f"Win Rate     : {wr:.1f}%")
    print(f"Profit Factor: {pf:.2f}")
    print(f"Avg Trade PnL: {avg_pnl:+.2f}%")
    print(f"Best Trade   : {trades.loc[trades['pnl_pct'].idxmax()]['ticker']} ({trades['pnl_pct'].max()*100:+.1f}%)")
    print(f"Worst Trade  : {trades.loc[trades['pnl_pct'].idxmin()]['ticker']} ({trades['pnl_pct'].min()*100:+.1f}%)")
    print()


print("=== RUNNING MULTI-MODEL BACKTEST (1 DES 2025 - 21 SEP 2026) ===")
# 1. Model Hold 1 Hari (Scalp / OSO) - Rank by Value
c1, t1 = run_fixed_hold_backtest(hold_days=1, rank_by="value", max_slots=1)
print_stats("Model 1: Scalp OSO (Hold 1 Hari, Top Value)", c1, t1)

# 2. Model Hold 1 Hari - Rank by Volume Spike Ratio
c2, t2 = run_fixed_hold_backtest(hold_days=1, rank_by="vol_ratio", max_slots=1)
print_stats("Model 2: Scalp OSO (Hold 1 Hari, Top Volume Spike)", c2, t2)

# 3. Model Swing 3 Hari (Hold 3 Hari, Top Value)
c3, t3 = run_fixed_hold_backtest(hold_days=3, rank_by="value", max_slots=1)
print_stats("Model 3: Swing Pendek (Hold 3 Hari, Top Value)", c3, t3)

# 4. Model Swing 5 Hari (Hold 5 Hari, Top Value)
c4, t4 = run_fixed_hold_backtest(hold_days=5, rank_by="value", max_slots=1)
print_stats("Model 4: Swing Menengah (Hold 5 Hari, Top Value)", c4, t4)

# 5. Model Trailing Stop Dinamis (SL 3%, Trailing 2.5%, Top Value)
c5, t5 = run_dynamic_trailing_backtest(sl_pct=0.03, trailing_pct=0.025, max_slots=1, rank_by="value")
print_stats("Model 5: Risk Managed (SL 3% + Trailing Lock 2.5%, Top Value)", c5, t5)

# 6. Model Multi-Slot Portfolio (3 Slots, SL 3% + Trailing 2.5%, Top Value)
c6, t6 = run_dynamic_trailing_backtest(sl_pct=0.03, trailing_pct=0.025, max_slots=3, rank_by="value")
print_stats("Model 6: Diversified Portfolio (3 Slots, SL 3% + Trailing 2.5%)", c6, t6)
