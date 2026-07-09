# Simulasi Backtest Trade Journal BUMI & DEWA (Des 2025 – Jul 2026)

**Tujuan:** bahan evaluasi bersama dosen pembimbing — mempelajari volatilitas harga
BUMI & DEWA periode Desember 2025–Juli 2026 dan (tahap berikutnya) mengaitkannya
dengan sinyal sentimen. Semua entri di halaman `/trades` untuk user demo adalah
**SIMULASI BACKTEST, bukan transaksi riil** (dilabeli eksplisit di kolom notes).

## Metodologi (reproducible)

- Skrip: `quant/trading_research/backtest_journal_sim_dec2025_jul2026.py`
- Sumber harga: kolom OHLC asli tabel `stock_prices` (baris `source='seed'` DIBUANG — lihat catatan data di bawah).
- Modal awal: Rp 33.000.000, dibagi dua Rp 16.500.000 per saham.
- Strategi (parameter dari kandidat tervalidasi OOS, lihat `BUMI_DEWA_candidate_oos_walkforward_validation.md`):
  - Take-profit 30% (fixed pct), stop-loss 3% (fixed pct), hold maksimum 40 hari bursa.
  - Re-entry hari bursa berikutnya setelah keluar (continuous exposure) sampai data habis.
  - Biaya ~0,25% round-trip (net-of-cost).
  - Sizing lot penuh (100 lembar) dengan reinvestasi ekuitas berjalan.

## Hasil

| | Buy & Hold | Strategi AI TP/SL |
|---|---|---|
| Total (modal 33jt) | **Rp 20,18 jt (−38,83%)** | **Rp 34,39 jt (+4,20%)** |
| DEWA | −33,77% | +33,49% (win rate 15,8%, 6/38) |
| BUMI | −43,90% | −25,10% (win rate 10,8%, 4/37) |

**Interpretasi jujur:** periode ini pasar untuk kedua saham jatuh dalam. Buy-and-hold
rugi ~39%. Strategi AI **tidak menghasilkan untung besar** — hanya bertahan (+4,2%),
karena stop-loss 3% memotong kerugian cepat. Mayoritas trade kalah tipis −3,25% (kena SL),
tapi beberapa kali menangkap rebound +29,8% yang menutup puluhan kerugian kecil.
DEWA selamat bahkan untung; BUMI tetap rugi karena tren turunnya terlalu deras.
Ini konsisten dengan temuan OOS bahwa strategi TP/SL ini **tidak mengalahkan buy-and-hold
secara statistik** — di sini ia menang bukan karena "profitable", tapi karena buy-and-hold
kebetulan sangat buruk (crash), sehingga sekadar bertahan sudah relatif unggul.

## ⚠️ Catatan kualitas data (penting untuk integritas skripsi)

Percobaan pertama menghasilkan +2027% yang mustahil. Penyebabnya: tabel `stock_prices`
punya **30 baris `source='seed'` (data sintetis/demo)** tercampur dengan data asli untuk
BUMI & DEWA sejak Des 2025; **27 tanggal punya dua harga sekaligus** (mis. DEWA asli ~440
vs seed ~57 di tanggal yang sama). Backtest yang benar HARUS memfilter baris seed dulu.
Kontaminasi ini sebaiknya dibersihkan dari database sebelum dipakai analisis apa pun
pada BUMI/DEWA. Backup 4 entri journal contoh lama (paper-profit) disimpan di
`storage/app/trades_backup_before_sim_*.json`.
