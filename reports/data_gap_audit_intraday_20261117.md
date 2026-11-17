# Laporan Audit Integritas Data & Sinyal: Rekonsiliasi Trade November 2026, Koreksi Syarat Trailing (Peak > Entry), & Pembuatan Arsip Permanen 168.718 Bar Intraday 15M

- **Tanggal Riset & Audit**: Selasa, 17 November 2026 (Sesi 1 & Midday)
- **Status Portofolio**: 100% Kas Cair (*Cash is King*), 593 Trade Tertutup Bersih
- **Hasil Audit Sinyal vs Trade (28 Okt – 17 Nov 2026)**:
  - Total Sinyal Tercatat di Tracker: **104 sinyal**
  - Total Trade Terbuka/Tertutup di DB: **106 trade** (104 sinyal matched 100% + 2 entri manual valid BUMI/PACK 11 Nov)
  - **Kesimpulan**: **TIDAK ADA SINYAL YANG TERLEWAT MAUPUN HILANG** selama sistem sempat mati/restart.
- **Koreksi Logika Auto-Close**:
  - Penegasan aturan baku `GEMINI.md` Seksi 3.1: **Trailing stop HANYA aktif bila $\text{Peak} > \text{Entry}$**.
  - Koreksi pada `Trade #896` (`BRPT` entri 750, high 745): karena harga tidak pernah naik melampaui harga beli, penurunan ke Low 720 ditutup via **Hard Stop Loss -3,5% @ 723,75** (bukan trailing stop).
- **Pengisian Lubang Data (*Data Gap Healing*)**:
  - `stock_prices` (Harian 1D): Ditambal 15 hari ke belakang untuk seluruh 130 saham aktif.
  - `idx_daily_summaries`: Ditambal 15 hari ke belakang (**10.503 baris** data harga EOD, volume, frekuensi, transaksi asing).
  - **Arsip Intraday 15-Menit**: Dibuat tabel database baru `intraday_prices` dan command `stocks:archive-intraday`.
  - Berhasil mengarsipkan **168.718 bar 15-menit** (26 Agustus s/d 17 November 2026) untuk 131 saham + IHSG (^JKSE/COMPOSITE).
  - Terintegrasi otomatis ke scheduler cron pada pukul 12:10 WIB (rehat sesi 1) dan 16:15 WIB (penutupan sesi 2).

---

## 1. Audit Detail Rekonsiliasi Sinyal vs Database Trade

Audit komparasi silang antara SQLite Tracker (`tracker.sqlite3`) dengan database MySQL (`trades`) membuktikan bahwa arsitektur pencatatan berjalan andal:

```
[tracker.sqlite3] (104 Sinyal)  <====== 100% MATCH ======>  [MySQL trades] (104 Sinyal + 2 Manual)
  - 89 Sinyal GABUNGAN                                        - Total 106 Trade
  - 5 Sinyal BOTTOM_REBOUND                                   - 0 Sinyal Terlewat
  - 10 Sinyal BOTTOM_TO_TOP                                   - 0 Sinyal Duplikat Liar
```

Seluruh sinyal dari `BRPT`, `BUMI`, `DEWA`, `ENRG`, `PTRO`, `RAJA`, `SMGR`, `ESSA`, `INET`, `PSAB`, dan `TINS` tercatat rapi di jurnal trading tanpa anomali.

---

## 2. Mengapa Data Harga Menit (15m) Sangat Krusial?

1. **Keterbatasan Yahoo Finance API**:
   - Yahoo Finance membatasi riwayat bar 15 menit hanya sampai **60 hari kalender**.
   - Tanpa penyimpanan permanen ke MySQL, data intraday dari trade-trade sebelumnya akan terhapus (*expired*), sehingga simulasi ekskursi MFE/MAE dan riset *trailing stop* tidak dapat diulang secara deterministik.
2. **Solusi Arsitektur**:
   - Dibuat tabel `intraday_prices` dengan primary unique index `(stock_code, interval, bar_time)`.
   - Command `php artisan stocks:archive-intraday --days=5` berjalan otomatis dua kali sehari via scheduler:
     * **12:10 WIB**: Mengamankan bar 15m Sesi 1.
     * **16:15 WIB**: Mengamankan bar 15m Sesi 2 & penutupan pasar.
   - Jika sistem mati beberapa hari, parameter `--days=5` (atau `--days=60`) otomatis menambal bar yang sempat tertinggal (*self-healing backfill*).

---

## 3. Matriks Hasil Pemeriksaan Lubang Data (Per 17 Nov 2026)

| Komponen Data | Status Sebelum Audit | Status Sesudah Backfill | Keterangan & Tindakan |
| :--- | :---: | :---: | :--- |
| **Harga Harian 1D (`stock_prices`)** | Kosong pada 12, 13, 16 Nov | **LENGKAP (130 Saham/Hari)** | Backfill via `stocks:fetch-history --days=15` |
| **Summary Bursa (`idx_daily_summaries`)** | Bolong pada 10 & 11 Nov | **LENGKAP (10.503 Baris)** | Backfill via `idx:fetch-daily-summary --backfill=15` |
| **Data Harga Menit 15M (`intraday_prices`)** | Belum ada tabel arsip | **168.718 Bar Tersimpan** | Migrasi tabel baru & backfill 60 hari penuh |
| **Portofolio Terbuka (`/trades`)** | BRPT & ENRG masih terbuka | **0 Posisi Open (100% Kas)** | Ditutup disiplin via Lapis 1 & 2 proteksi |

