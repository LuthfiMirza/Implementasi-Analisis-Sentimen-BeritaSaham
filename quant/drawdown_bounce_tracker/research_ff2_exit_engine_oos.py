#!/usr/bin/env python3
"""Fase FF-2: Walk-Forward OOS Backtest on True 15-Minute Intraday Bars (intraday_prices)
Strictly chronological bar-by-bar simulation (ZERO same-bar lookahead: trailing stop checks
against prior-bar peak first, then updates peak from current bar's High).

Compares:
  1. 15m Close-bar SL (-3.5%) vs Intraday Low-bar SL (-3.5%) vs Wider SL (-4.5% / -5.0%)
  2. Trailing Stop Activation Buffer (0%, 1.5%, 2.0%, 2.5%, 3.0%) + Breakeven Shield
  3. ATR-Adaptive Trailing Stop
  4. Partial Take Profit Scale-Out (50% @ TP1 + 50% runner with wider TS)
Evaluated on BOTH All Trades & Protocol-Compliant Trades (excluding Grade C & Oct 15-19 Crash Guard),
split into Discovery Fold (Aug 26 - Oct 14) vs Holdout Fold (Oct 15 - Nov 25).
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import pymysql

SOCKET_PATH = "/Applications/XAMPP/xamppfiles/var/mysql/mysql.sock"
DB_NAME = "sentimena_dashboard"
BASE_CAPITAL = 10_000_000.0
REPORTS_DIR = Path("/Applications/XAMPP/xamppfiles/htdocs/Implementasi AnalisisSentimenBerita/laravel-app/reports")
CRASH_GUARD_DATES = {"2026-10-15", "2026-10-16", "2026-10-19"}


def get_conn():
    return pymysql.connect(
        user="root",
        unix_socket=SOCKET_PATH,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def load_data():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, ticker, strategy_label, signal_quality,
                       entry_date, exit_date, entry_price, exit_price, pnl_percent, result
                FROM trades
                WHERE status = 'closed'
                  AND entry_date >= '2026-08-26'
                  AND entry_price > 0
                  AND ticker NOT IN ('PSAB', 'TLKM')
                ORDER BY entry_date ASC, id ASC
            """)
            trades = pd.DataFrame(cur.fetchall())

            tks = tuple(sorted(trades["ticker"].str.upper().unique().tolist()))
            placeholders = ",".join(["%s"] * len(tks))
            cur.execute(
                f"""
                SELECT stock_code AS ticker, bar_time, open, high, low, close, volume
                FROM intraday_prices
                WHERE stock_code IN ({placeholders})
                ORDER BY stock_code, bar_time ASC
                """,
                tks,
            )
            bars = pd.DataFrame(cur.fetchall())

            cur.execute(
                f"""
                SELECT s.code AS ticker, sp.price_date, sp.high, sp.low, sp.close
                FROM stock_prices sp
                JOIN stocks s ON s.id = sp.stock_id
                WHERE sp.source <> 'seed' AND s.code IN ({placeholders}) AND sp.price_date >= '2026-07-01'
                ORDER BY s.code, sp.price_date ASC
                """,
                tks,
            )
            daily = pd.DataFrame(cur.fetchall())
    finally:
        conn.close()

    trades["entry_date"] = pd.to_datetime(trades["entry_date"])
    trades["entry_price"] = trades["entry_price"].astype(float)
    trades["ticker"] = trades["ticker"].str.upper()
    trades["grade"] = trades["signal_quality"].fillna("B").str.upper()

    bars["bar_time"] = pd.to_datetime(bars["bar_time"])
    for col in ["open", "high", "low", "close"]:
        bars[col] = bars[col].astype(float)
    bars["bar_date"] = bars["bar_time"].dt.normalize()

    daily["price_date"] = pd.to_datetime(daily["price_date"])
    for col in ["high", "low", "close"]:
        daily[col] = daily[col].astype(float)
    return trades, bars, daily


def compute_daily_atr_pct(daily: pd.DataFrame) -> dict[tuple[str, pd.Timestamp], float]:
    out = {}
    for tk, grp in daily.groupby("ticker"):
        g = grp.sort_values("price_date").copy()
        prev_c = g["close"].shift(1)
        tr = pd.concat([(g["high"] - g["low"]), (g["high"] - prev_c).abs(), (g["low"] - prev_c).abs()], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / 14, min_periods=10, adjust=False).mean()
        atr_pct = (atr / g["close"] * 100.0).fillna(5.0)
        for dt, val in zip(g["price_date"], atr_pct):
            out[(tk, dt)] = float(val)
    return out


def sim_trade_15m(
    sub_bars: pd.DataFrame,
    entry_price: float,
    atr_pct: float,
    sl_pct: float = 0.035,
    ts_pct: float = 0.020,
    ts_activation_pct: float = 0.0,
    use_low_for_sl: bool = False,
    use_low_for_ts: bool = False,
    breakeven_trigger: float | None = None,
    atr_k: float | None = None,
    partial_tp_pct: float | None = None,
    runner_ts_pct: float = 0.030,
    max_hold_days: int = 10,
) -> tuple[float, str, float]:
    if sub_bars.empty:
        return 0.0, "no_bars", 0.0

    eff_ts = ts_pct
    if atr_k is not None:
        eff_ts = max(0.018, min(0.035, (atr_pct / 100.0) * atr_k))

    peak = entry_price
    sl_price = entry_price * (1.0 - sl_pct)
    mfe_pct = 0.0
    partial_taken = False
    realized_part = 0.0
    rem_weight = 1.0

    trading_days = sorted(sub_bars["bar_date"].unique())

    for _, bar in sub_bars.iterrows():
        h = bar["high"]
        l = bar["low"]
        c = bar["close"]
        o = bar["open"]

        # 1. Check Hard SL against current bar
        sl_check_px = l if use_low_for_sl else c
        if sl_check_px <= sl_price:
            fill_px = min(o, sl_price) if use_low_for_sl else c
            rem_ret = (fill_px - entry_price) / entry_price * 100.0
            total_ret = realized_part + rem_weight * rem_ret
            etype = "be_stop" if (breakeven_trigger and sl_price >= entry_price) else "stop_loss"
            return total_ret, etype, mfe_pct

        # 2. Check Trailing Stop against PRIOR peak (no same-bar H-then-L illusion!)
        peak_gain = (peak - entry_price) / entry_price
        active_ts_dist = runner_ts_pct if partial_taken else eff_ts
        ts_active = (peak > entry_price) if ts_activation_pct == 0.0 else (peak_gain >= ts_activation_pct)
        if ts_active:
            ts_trigger = peak * (1.0 - active_ts_dist)
            ts_check_px = l if use_low_for_ts else c
            if ts_check_px <= ts_trigger:
                fill_px = min(o, ts_trigger) if use_low_for_ts else c
                rem_ret = (fill_px - entry_price) / entry_price * 100.0
                total_ret = realized_part + rem_weight * rem_ret
                return total_ret, ("partial_ts" if partial_taken else "trailing_stop"), mfe_pct

        # 3. Partial TP Scale-Out (50/50)
        if partial_tp_pct is not None and not partial_taken and h >= entry_price * (1.0 + partial_tp_pct):
            tp_px = entry_price * (1.0 + partial_tp_pct)
            realized_part += 0.5 * ((tp_px - entry_price) / entry_price * 100.0)
            rem_weight = 0.5
            partial_taken = True
            sl_price = max(sl_price, entry_price * 1.002)

        # 4. Update peak & MFE from current bar High (for next bars)
        if h > peak:
            peak = h
            mfe_pct = max(mfe_pct, (peak - entry_price) / entry_price * 100.0)

        # 5. Breakeven shield (for next bars)
        if breakeven_trigger is not None and (peak - entry_price) / entry_price >= breakeven_trigger:
            sl_price = max(sl_price, entry_price * 1.002)

    cutoff_day = trading_days[min(max_hold_days, len(trading_days)) - 1]
    exit_c = float(sub_bars[sub_bars["bar_date"] == cutoff_day]["close"].iloc[-1])
    rem_ret = (exit_c - entry_price) / entry_price * 100.0
    return realized_part + rem_weight * rem_ret, "time_exit", mfe_pct


def evaluate_suite(trades: pd.DataFrame, bars_by_tk: dict, atr_map: dict, configs: list) -> list:
    out = []
    for name, kw in configs:
        recs = []
        for _, t in trades.iterrows():
            tk = t["ticker"]
            if tk not in bars_by_tk:
                continue
            bdf = bars_by_tk[tk]
            sub = bdf[bdf["bar_date"] > t["entry_date"]]
            if sub.empty:
                continue
            days = sorted(sub["bar_date"].unique())[: kw.get("max_hold_days", 10)]
            sub = sub[sub["bar_date"].isin(days)]
            atr_pct = atr_map.get((tk, t["entry_date"]), 5.5)
            pnl_pct, etype, mfe = sim_trade_15m(sub, t["entry_price"], atr_pct, **kw)
            fold = "Disc" if t["entry_date"] < pd.Timestamp("2026-10-15") else "Hold"
            recs.append({"fold": fold, "pnl_pct": pnl_pct, "pnl_rp": BASE_CAPITAL * pnl_pct / 100.0, "etype": etype, "mfe": mfe})

        rdf = pd.DataFrame(recs)

        def summ(dsub):
            if dsub.empty:
                return {"n": 0, "wr": 0, "pf": 0, "avg": 0, "pnl_m": 0, "dd_m": 0, "neg_ts": 0}
            gw = float(dsub[dsub["pnl_rp"] > 0]["pnl_rp"].sum())
            gl = float(-dsub[dsub["pnl_rp"] < 0]["pnl_rp"].sum())
            eq = dsub["pnl_rp"].cumsum()
            dd = float((eq - eq.cummax().clip(lower=0.0)).min())
            neg_ts = int(((dsub["etype"] == "trailing_stop") & (dsub["pnl_pct"] < 0)).sum())
            return {
                "n": len(dsub),
                "wr": round(float((dsub["pnl_pct"] > 0).mean() * 100.0), 1),
                "pf": round(gw / gl, 2) if gl > 0 else 99.0,
                "avg": round(float(dsub["pnl_pct"].mean()), 2),
                "pnl_m": round(float(dsub["pnl_rp"].sum()) / 1e6, 2),
                "dd_m": round(dd / 1e6, 2),
                "neg_ts": neg_ts,
            }

        out.append((name, summ(rdf), summ(rdf[rdf["fold"] == "Disc"]), summ(rdf[rdf["fold"] == "Hold"])))
    return out


def main():
    trades, bars, daily = load_data()
    atr_map = compute_daily_atr_pct(daily)
    bars_by_tk = {tk: grp.reset_index(drop=True) for tk, grp in bars.groupby("ticker")}

    # Subset 2: Protocol-Compliant (skip Grade C & Oct 15-19 Crash Guard days)
    compliant = trades[
        (trades["grade"] != "C")
        & (~trades["entry_date"].dt.strftime("%Y-%m-%d").isin(CRASH_GUARD_DATES))
    ].copy()

    configs = [
        ("0_Baseline_15mClose_SL3.5_TS2.0_Buf0%", dict(sl_pct=0.035, ts_pct=0.020, ts_activation_pct=0.0, use_low_for_sl=False, use_low_for_ts=False)),
        ("1_15mClose_SL3.5_TS2.0_Buf1.5%", dict(sl_pct=0.035, ts_pct=0.020, ts_activation_pct=0.015, use_low_for_sl=False, use_low_for_ts=False)),
        ("2_15mClose_SL3.5_TS2.0_Buf2.0%", dict(sl_pct=0.035, ts_pct=0.020, ts_activation_pct=0.020, use_low_for_sl=False, use_low_for_ts=False)),
        ("3_15mClose_SL3.5_TS2.0_Buf2.5%", dict(sl_pct=0.035, ts_pct=0.020, ts_activation_pct=0.025, use_low_for_sl=False, use_low_for_ts=False)),
        ("4_15mClose_SL3.5_TS2.0_Buf2.0%_BE2.5%", dict(sl_pct=0.035, ts_pct=0.020, ts_activation_pct=0.020, breakeven_trigger=0.025, use_low_for_sl=False, use_low_for_ts=False)),
        ("5_15mClose_SL3.5_TS2.5_Buf2.5%", dict(sl_pct=0.035, ts_pct=0.025, ts_activation_pct=0.025, use_low_for_sl=False, use_low_for_ts=False)),
        ("6_15mClose_ATR_k0.35_Buf2.0%", dict(sl_pct=0.035, atr_k=0.35, ts_activation_pct=0.020, use_low_for_sl=False, use_low_for_ts=False)),
        ("7_15mClose_PartialTP50@+5%_RunTS3.0%", dict(sl_pct=0.035, ts_pct=0.020, ts_activation_pct=0.020, partial_tp_pct=0.05, runner_ts_pct=0.030, use_low_for_sl=False, use_low_for_ts=False)),
        ("8_15mClose_PartialTP50@+4%_RunTS3.0%", dict(sl_pct=0.035, ts_pct=0.020, ts_activation_pct=0.020, partial_tp_pct=0.04, runner_ts_pct=0.030, use_low_for_sl=False, use_low_for_ts=False)),
        ("9_BrokerLowSL3.5_TS2.0_Buf0%", dict(sl_pct=0.035, ts_pct=0.020, ts_activation_pct=0.0, use_low_for_sl=True, use_low_for_ts=False)),
        ("10_BrokerLowSL3.5_TS2.0_Buf2.0%", dict(sl_pct=0.035, ts_pct=0.020, ts_activation_pct=0.020, use_low_for_sl=True, use_low_for_ts=False)),
        ("11_BrokerLowSL4.5_TS2.0_Buf2.0%", dict(sl_pct=0.045, ts_pct=0.020, ts_activation_pct=0.020, use_low_for_sl=True, use_low_for_ts=False)),
        ("12_BrokerLowSL5.0_PartialTP50@+5%_Run3%", dict(sl_pct=0.050, ts_pct=0.020, ts_activation_pct=0.020, partial_tp_pct=0.05, runner_ts_pct=0.030, use_low_for_sl=True, use_low_for_ts=False)),
    ]

    res_all = evaluate_suite(trades, bars_by_tk, atr_map, configs)
    res_comp = evaluate_suite(compliant, bars_by_tk, atr_map, configs)

    def print_tbl(title, rows):
        print(f"\n=== {title} ===")
        hdr = f"{'Config':40s} | {'N':>3s} | {'WR%':>5s} | {'PF':>5s} | {'PnL(Jt)':>7s} | {'MaxDD':>7s} | {'NegTS':>5s} | {'DiscPF':>6s} | {'HoldPF':>6s} | {'HoldPnL':>7s}"
        print(hdr)
        print("-" * len(hdr))
        for name, a, d, h in rows:
            print(f"{name:40s} | {a['n']:3d} | {a['wr']:5.1f} | {a['pf']:5.2f} | {a['pnl_m']:+7.2f} | {a['dd_m']:7.2f} | {a['neg_ts']:5d} | {d['pf']:6.2f} | {h['pf']:6.2f} | {h['pnl_m']:+7.2f}")

    print_tbl(f"ALL TRADES (n={len(trades)})", res_all)
    print_tbl(f"PROTOCOL-COMPLIANT (No Grade C, No Oct15-19 Crash, n={len(compliant)})", res_comp)

    lines = [
        "# Laporan Riset Kuantitatif Fase FF-2: Simulasi 15-Menit Kronologis — Activation Buffer, Partial TP (50/50), & Audit Hard SL Intraday",
        "",
        f"> **Tanggal Riset**: 26 November 2026  ",
        f"> **Dataset**: `{len(bars):,}` bar 15-menit (`intraday_prices`) pada `{len(trades)}` trade (`2026-08-26` s/d `2026-11-24`), tanpa *same-bar lookahead*.  ",
        "> **Split Walk-Forward**: Discovery (`26 Agu – 14 Okt`) vs Holdout Krisis+Rebound (`15 Okt – 25 Nov`).",
        "",
        f"## 1. Hasil Pada Trade Patuh Protokol (Tanpa Grade C & Crash Guard 15–19 Okt, `n={len(compliant)}`)",
        "",
        "| Konfigurasi Exit | N | WR | PF | Total PnL (Jt) | MaxDD (Jt) | Neg TS | Disc PF | **Holdout PF** | **Holdout PnL (Jt)** |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for name, a, d, h in res_comp:
        lines.append(f"| `{name}` | {a['n']} | {a['wr']:.1f}% | **{a['pf']:.2f}** | {a['pnl_m']:+.2f} | {a['dd_m']:.2f} | {a['neg_ts']} | {d['pf']:.2f} | **{h['pf']:.2f}** | **{h['pnl_m']:+.2f}** |")

    lines.extend([
        "",
        f"## 2. Hasil Pada Seluruh Trade Mentah (`n={len(trades)}`)",
        "",
        "| Konfigurasi Exit | N | WR | PF | Total PnL (Jt) | MaxDD (Jt) | Neg TS | Disc PF | Holdout PF | Holdout PnL (Jt) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])
    for name, a, d, h in res_all:
        lines.append(f"| `{name}` | {a['n']} | {a['wr']:.1f}% | {a['pf']:.2f} | {a['pnl_m']:+.2f} | {a['dd_m']:.2f} | {a['neg_ts']} | {d['pf']:.2f} | {h['pf']:.2f} | {h['pnl_m']:+.2f} |")

    out_path = REPORTS_DIR / "research_ff2_exit_engine_oos_20261126.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nUpdated report: {out_path}")


if __name__ == "__main__":
    main()
