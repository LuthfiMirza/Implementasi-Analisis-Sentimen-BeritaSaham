#!/usr/bin/env python3
"""Report on tracked signals per PROTOCOL.md. Refuses to draw a conclusion below n=20 evaluated
signals -- prints the honest "not enough data yet" status instead, per the pre-registered
minimum. Everything computed here mirrors PROTOCOL.md's "Yang dilaporkan di akhir" section
exactly, in the same order, so nothing gets silently left out.

    python3 quant/signal_tracker/report.py
"""
from __future__ import annotations

import sqlite3
import statistics
from pathlib import Path

DB_PATH = Path(__file__).parent / "tracker.sqlite3"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
MIN_N = 20


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.row_factory = sqlite3.Row

    tracked = conn.execute("SELECT COUNT(*) FROM signals WHERE tracked = 1").fetchone()[0]
    skipped = conn.execute(
        "SELECT skip_reason, COUNT(*) c FROM signals WHERE tracked = 0 GROUP BY skip_reason"
    ).fetchall()
    evaluated = conn.execute(
        """SELECT s.ticker, o.result, o.days_to_exit, o.net_return, o.buy_hold_return_30d,
                  o.ihsg_return_30d
           FROM outcomes o JOIN signals s ON s.id = o.signal_id"""
    ).fetchall()

    print("=" * 70)
    print("Laporan sinyal 'Zeta AI' -- per PROTOCOL.md")
    print("=" * 70)
    print(f"\nSinyal tracked (BUY, confidence=5): {tracked}")
    print(f"Sinyal terlihat tapi TIDAK dilacak, by alasan:")
    for row in skipped:
        print(f"  {row['skip_reason']}: {row['c']}")
    print(f"\nSudah dievaluasi (lewat 30 hari): {len(evaluated)} / {tracked}")

    if len(evaluated) < MIN_N:
        print(f"\n*** BELUM CUKUP DATA. Protokol menetapkan minimum n={MIN_N} sebelum kesimpulan")
        print(f"    ditarik. Baru ada {len(evaluated)}. Jalankan evaluate.py lagi nanti. ***")
        conn.close()
        return

    results = [r["result"] for r in evaluated]
    n = len(evaluated)
    tp_hit = results.count("TP_HIT")
    sl_hit = results.count("SL_HIT")
    time_exit = results.count("TIME_EXIT")
    unavailable = results.count("DATA_UNAVAILABLE")
    usable = [r for r in evaluated if r["result"] != "DATA_UNAVAILABLE"]

    print(f"\n--- Hasil (n={n}) ---")
    print(f"TP_HIT: {tp_hit}  SL_HIT: {sl_hit}  TIME_EXIT: {time_exit}  DATA_UNAVAILABLE: {unavailable}")

    resolved = tp_hit + sl_hit
    if resolved:
        wr_resolved = tp_hit / resolved
        print(f"\nWin rate versi 'resolved-only' (ala dashboard): {tp_hit}/{resolved} = {wr_resolved:.1%}")
    wr_honest_denom = n - unavailable
    if wr_honest_denom:
        wr_honest = tp_hit / wr_honest_denom
        print(f"Win rate versi JUJUR (semua tracked signal, TIME_EXIT dihitung apa adanya):")
        print(f"  {tp_hit}/{wr_honest_denom} = {wr_honest:.1%}")

    net_returns = [r["net_return"] for r in usable if r["net_return"] is not None]
    if net_returns:
        print(f"\n--- Return net biaya (0.80% round-trip), semua sinyal masuk hitungan ---")
        print(f"Rata-rata : {statistics.mean(net_returns):+.2%}")
        print(f"Median    : {statistics.median(net_returns):+.2%}")
        if len(net_returns) > 1:
            print(f"Std dev   : {statistics.stdev(net_returns):.2%}")
        print(f"Min / Max : {min(net_returns):+.2%} / {max(net_returns):+.2%}")

    bh_returns = [r["buy_hold_return_30d"] for r in usable if r["buy_hold_return_30d"] is not None]
    ihsg_returns = [r["ihsg_return_30d"] for r in usable if r["ihsg_return_30d"] is not None]
    if bh_returns and net_returns:
        print(f"\n--- Pembanding wajib ---")
        print(f"Rata-rata net return sinyal : {statistics.mean(net_returns):+.2%}")
        print(f"Rata-rata beli-diamkan 30hr : {statistics.mean(bh_returns):+.2%}")
        print(f"  -> delta vs beli-diamkan  : {statistics.mean(net_returns) - statistics.mean(bh_returns):+.2%}")
    if ihsg_returns and net_returns:
        print(f"Rata-rata IHSG 30 hari       : {statistics.mean(ihsg_returns):+.2%}")
        print(f"  -> delta vs IHSG          : {statistics.mean(net_returns) - statistics.mean(ihsg_returns):+.2%}")

    for label, subset in [("TP_HIT", [r for r in usable if r["result"] == "TP_HIT"]),
                           ("SL_HIT", [r for r in usable if r["result"] == "SL_HIT"])]:
        days = [r["days_to_exit"] for r in subset if r["days_to_exit"] is not None]
        if days:
            print(f"\nWaktu penyelesaian rata-rata {label}: {statistics.mean(days):.1f} hari (n={len(days)})")

    print(f"\n--- Verdict ---")
    if net_returns and bh_returns and ihsg_returns:
        beats_both = statistics.mean(net_returns) > statistics.mean(bh_returns) and \
                     statistics.mean(net_returns) > statistics.mean(ihsg_returns)
        if beats_both:
            print("Sinyal mengalahkan KEDUA pembanding (beli-diamkan dan IHSG) -- ada indikasi nilai tambah.")
            print("Tetap perlu n lebih besar dan periode lebih panjang sebelum diklaim robust.")
        else:
            print("Sinyal TIDAK mengalahkan salah satu atau kedua pembanding wajib.")
            print("Per protokol, ini berarti sinyal belum terbukti punya nilai tambah dibanding")
            print("strategi pasif (beli-diamkan / ikuti indeks).")

    conn.close()


if __name__ == "__main__":
    main()
