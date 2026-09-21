"""
Cek kelayakan historis saham kandidat baru.
Ambil data dari Yahoo Finance dan evaluasi:
  - Jumlah hari bursa tersedia
  - Apakah memenuhi syarat minimum 1250 hari bursa
  - Likuiditas (rata-rata volume × harga ≈ turnover IDR)
  - Ringkasan fundamental (dari DB jika ada)
  - Skor kelayakan backtest

Usage:
    python quant/check_history_candidates.py
"""
from __future__ import annotations

import datetime
import json
import sys
import warnings

warnings.filterwarnings("ignore")

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance tidak tersedia. Aktifkan venv dulu.")
    sys.exit(1)

CANDIDATES = ["ARCI", "PSAB", "TINS", "ADMR", "KIJA", "BULL"]
MIN_TRADING_DAYS   = 1250   # syarat minimum proyek ini
GOOD_TRADING_DAYS  = 2500   # ideal (≈10 tahun bursa)
MIN_TURNOVER_IDR   = 50_000_000_000  # Rp 50 miliar/hari (likuiditas layak)
FETCH_PERIOD       = "max"          # ambil semua riwayat yang ada

SECTOR_NOTES = {
    "ARCI": "Infrastruktur / Konstruksi",
    "PSAB": "Pertambangan Emas",
    "TINS": "Pertambangan Timah (BUMN)",
    "ADMR": "Energi / Migas (Adaro Minerals)",
    "KIJA": "Properti Industri (Kawasan Jababeka)",
    "BULL": "Transportasi Laut / Tanker",
}

ANSI_RESET  = "\033[0m"
ANSI_GREEN  = "\033[92m"
ANSI_YELLOW = "\033[93m"
ANSI_RED    = "\033[91m"
ANSI_BOLD   = "\033[1m"
ANSI_CYAN   = "\033[96m"
ANSI_DIM    = "\033[2m"

IDR_PER_LOT = 100   # 1 lot = 100 saham

def fmt_num(n: float, decimals: int = 0) -> str:
    return f"{n:,.{decimals}f}"

def fmt_idr(n: float) -> str:
    if n >= 1_000_000_000_000:
        return f"Rp {n/1_000_000_000_000:.2f} T"
    if n >= 1_000_000_000:
        return f"Rp {n/1_000_000_000:.1f} M"
    if n >= 1_000_000:
        return f"Rp {n/1_000_000:.1f} jt"
    return f"Rp {n:,.0f}"

def color(text: str, code: str) -> str:
    return f"{code}{text}{ANSI_RESET}"

def verdict_color(ok: bool) -> str:
    return ANSI_GREEN if ok else ANSI_RED

results = []

print()
print(color("=" * 60, ANSI_BOLD))
print(color("  LAPORAN KELAYAKAN SAHAM KANDIDAT BARU", ANSI_BOLD + ANSI_CYAN))
print(color(f"  Digenerate: {datetime.datetime.now().strftime('%d %b %Y %H:%M WIB')}", ANSI_DIM))
print(color("=" * 60, ANSI_BOLD))
print(f"\n  Syarat minimum: {color(f'{MIN_TRADING_DAYS:,} hari bursa', ANSI_BOLD)}")
print(f"  Syarat ideal  : {color(f'{GOOD_TRADING_DAYS:,} hari bursa (≥10 tahun)', ANSI_BOLD)}")
print(f"  Syarat likuid : {fmt_idr(MIN_TURNOVER_IDR)} turnover/hari rata-rata\n")

for ticker in CANDIDATES:
    yahoo_sym = f"{ticker}.JK"
    print(color(f"  ⟳ Mengambil data {ticker} ({yahoo_sym})...", ANSI_DIM), end="\r")

    try:
        tk  = yf.Ticker(yahoo_sym)
        df  = tk.history(period=FETCH_PERIOD, auto_adjust=True)

        if df is None or df.empty:
            results.append({
                "ticker": ticker,
                "status": "NO_DATA",
                "days": 0,
                "ok_history": False,
                "ok_liquidity": False,
            })
            print(f"  [{color('GAGAL', ANSI_RED)}] {ticker:6s}: tidak ada data di Yahoo Finance")
            continue

        # drop baris weekend / holiday jika ada
        df = df[df.index.dayofweek < 5]
        n_days      = len(df)
        date_start  = df.index[0].strftime("%d %b %Y")
        date_end    = df.index[-1].strftime("%d %b %Y")

        # Turnover harian (Volume × Close price dalam IDR)
        # Close dari yfinance sudah dalam IDR asli
        df["turnover"] = df["Volume"] * df["Close"]
        avg_turnover    = df["turnover"].median()
        last_price      = float(df["Close"].iloc[-1])
        last_volume     = int(df["Volume"].iloc[-1])

        ok_history   = n_days >= MIN_TRADING_DAYS
        ok_liquidity = avg_turnover >= MIN_TURNOVER_IDR

        # Cek apakah data CSV lokal juga sudah ada
        import pathlib
        csv_path = pathlib.Path(__file__).parent / "data" / "stocks" / f"{ticker}.csv"
        has_csv  = csv_path.exists()

        # Gap cek: apakah data terbaru (dalam 7 hari ke belakang)
        last_date_dt = df.index[-1].date()
        today = datetime.date.today()
        days_gap = (today - last_date_dt).days
        data_fresh = days_gap <= 7

        res = {
            "ticker"       : ticker,
            "sector"       : SECTOR_NOTES.get(ticker, "-"),
            "status"       : "OK" if (ok_history and ok_liquidity) else "PARTIAL" if ok_history else "INSUFFICIENT",
            "days"         : n_days,
            "date_start"   : date_start,
            "date_end"     : date_end,
            "days_gap"     : days_gap,
            "avg_turnover" : avg_turnover,
            "last_price"   : last_price,
            "last_volume"  : last_volume,
            "ok_history"   : ok_history,
            "ok_liquidity" : ok_liquidity,
            "has_local_csv": has_csv,
            "data_fresh"   : data_fresh,
        }
        results.append(res)

        # --- Print hasil per saham ---
        verdict = "✅ LAYAK" if (ok_history and ok_liquidity) else ("⚠️  KURANG LIKUID" if ok_history else "❌ TIDAK CUKUP")
        vcolor  = ANSI_GREEN if (ok_history and ok_liquidity) else (ANSI_YELLOW if ok_history else ANSI_RED)

        hist_mark = color("✔", ANSI_GREEN) if ok_history else color("✘", ANSI_RED)
        liq_mark  = color("✔", ANSI_GREEN) if ok_liquidity else color("✘", ANSI_RED)

        print(f"\n  {color(ticker, ANSI_BOLD + ANSI_CYAN)} — {SECTOR_NOTES.get(ticker, '')}")
        print(f"    {color(verdict, vcolor + ANSI_BOLD)}")
        print(f"    Periode   : {date_start}  →  {date_end}")
        print(f"    Hari bursa: {hist_mark} {color(str(n_days), verdict_color(ok_history))} hari "
              f"({'≥' if ok_history else '<'} {MIN_TRADING_DAYS} min, "
              f"{'≥' if n_days >= GOOD_TRADING_DAYS else '<'} {GOOD_TRADING_DAYS} ideal)")
        print(f"    Likuiditas: {liq_mark} Median turnover {fmt_idr(avg_turnover)}/hari")
        print(f"    Harga term.: Rp {fmt_num(last_price)} | Vol: {fmt_num(last_volume)} lot")
        print(f"    Data lokal : {'Ada (CSV)' if has_csv else color('Belum ada CSV lokal', ANSI_YELLOW)} | "
              f"Freshness: {'🟢 Baru' if data_fresh else color(f'🔴 Gap {days_gap} hari', ANSI_RED)}")

    except Exception as exc:
        results.append({
            "ticker": ticker,
            "status": "ERROR",
            "error": str(exc),
            "ok_history": False,
            "ok_liquidity": False,
        })
        print(f"  [{color('ERROR', ANSI_RED)}] {ticker}: {exc}")

# ──────────────────────────────────────────────────────────────────
# RINGKASAN TABEL
# ──────────────────────────────────────────────────────────────────
print()
print(color("=" * 60, ANSI_BOLD))
print(color("  RINGKASAN KEPUTUSAN", ANSI_BOLD + ANSI_CYAN))
print(color("=" * 60, ANSI_BOLD))
print()
print(f"  {'TICKER':<8} {'HARI':>6} {'TURNOVER/HARI':<18} {'HIST':>5} {'LIQ':>5}  STATUS")
print(f"  {'------':<8} {'----':>6} {'-------------':<18} {'----':>5} {'---':>5}  ------")

layak    = []
kurang   = []
ditolak  = []

for r in results:
    h = color("✔", ANSI_GREEN) if r.get("ok_history") else color("✘", ANSI_RED)
    l = color("✔", ANSI_GREEN) if r.get("ok_liquidity") else color("✘", ANSI_RED)
    t = fmt_idr(r.get("avg_turnover", 0)) if r.get("avg_turnover") else "N/A"
    d = str(r.get("days", 0))

    if r.get("ok_history") and r.get("ok_liquidity"):
        status = color("✅ LAYAK BACKTEST", ANSI_GREEN)
        layak.append(r["ticker"])
    elif r.get("ok_history"):
        status = color("⚠️  Hari cukup, likuiditas kurang", ANSI_YELLOW)
        kurang.append(r["ticker"])
    else:
        status = color("❌ Belum cukup data historis", ANSI_RED)
        ditolak.append(r["ticker"])

    print(f"  {r['ticker']:<8} {d:>6} {t:<18} {h:>12} {l:>12}  {status}")

print()
print(color("── REKOMENDASI ──────────────────────────────────────────", ANSI_BOLD))
if layak:
    print(f"\n  {color('LANGSUNG BISA DIBACKTEST:', ANSI_GREEN + ANSI_BOLD)}")
    for t in layak:
        print(f"    → {t}")
if kurang:
    print(f"\n  {color('PERLU PERTIMBANGAN (hari cukup tapi likuiditas rendah):', ANSI_YELLOW + ANSI_BOLD)}")
    for t in kurang:
        print(f"    → {t}")
if ditolak:
    print(f"\n  {color('BELUM BISA DIBACKTEST (data historis kurang dari 1250 hari):', ANSI_RED + ANSI_BOLD)}")
    for t in ditolak:
        print(f"    → {t}")

print()
print(color("── LANGKAH SELANJUTNYA ──────────────────────────────────", ANSI_BOLD))
if layak:
    syms = " ".join(layak)
    print(f"\n  1. Tambahkan ke aktif dan fetch historis:")
    print(f"     {color(f'php artisan stocks:fetch-history --tickers={syms}', ANSI_CYAN)}")
    print(f"\n  2. Fetch berita untuk kandiat layak:")
    print(f"     {color(f'php artisan news:fetch --stocks={syms}', ANSI_CYAN)}")
if layak or kurang:
    print(f"\n  3. Jalankan backtest drawdown-bounce:")
    print(f"     {color('python quant/drawdown_bounce_tracker/backtest_ptb_picks.py', ANSI_CYAN)}")

print()
