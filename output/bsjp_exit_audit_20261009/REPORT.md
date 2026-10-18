# Audit BSJP: pilihan exit dan trailing Stockbit 2%

Tanggal audit: 9 Oktober 2026. Status: riset eksploratif, belum layak menetapkan metode paling profit atau mengubah strategi produksi.

## Kesimpulan

Trailing 2% bisa menggantikan fungsi stop tetap sejak aktif, tetapi bukan jaminan rugi maksimal 2%, harga jual tertentu, atau semua lot terjual. Pada seluruh 100 sinyal, open mempunyai mean return tertinggi di skenario yang diuji. Pada satu pilihan volume spike tertinggi per hari, peringkat open versus trailing berubah menurut asumsi urutan intrabar. Karena itu trailing-only belum terbukti lebih unggul.

## Data dan rancangan

- Sumber: raw OHLCV Yahoo Finance chart, diunduh melalui quant/fetch_bsjp_exit_audit.py; respons asli dan download_manifest.json disimpan di folder ini.
- Universe: 20 saham dari dataset screener lama ditambah MCAS. Ini universe retrospektif terpilih, bukan seluruh BEI dan bukan sampel bebas selection/survivorship bias.
- Entry 2026-07-16 sampai 2026-10-08: 100 sinyal dengan data pagi lengkap; 13 sinyal dikeluarkan karena candle pembukaan tidak lengkap. Subset satu saham per hari: 43 transaksi valid. Peringkat dipilih SEBELUM mengecek ketersediaan candle exit; kandidat tanpa data tidak digantikan runner-up.
- Filter mengikuti radar: close > open, return harian >=3%, volume >=1.5 kali hari sebelumnya, estimasi nilai close x volume >=Rp100 juta. Estimasi nilai bukan nilai transaksi resmi. Tidak memakai syarat MA tambahan dari script screener lama.
- Entry = daily close, dengan asumsi bisa memperoleh close. Data close dan volume akhir belum final pada 15:50; ini perbandingan exit bersyarat, belum backtest sistem entry pre-closing yang dapat dieksekusi.
- Semua exit memakai sinyal yang sama, fee beli 0.15%, jual 0.25%, lot bulat dengan alokasi Rp20 juta per transaksi. Tidak menggandakan modal melalui compounding sinyal simultan.
- Semua metode selain OPEN wajib keluar di open candle 09:15 bila belum terpicu. TP tetap diuji bersama SL 3%; SL saja juga diuji. Trailing tidak memakai fixed SL tambahan.
- TRAIL2_ENTRY: peak awal harga entry (proxy order aktif setelah entry/close). TRAIL2_OPEN: baru aktif dari open pagi. Pergerakan sejak pemasangan sore hingga close tidak tersedia pada proxy ENTRY.
- Dua skenario per candle 5 menit: open-high-low-close dan open-low-high-close. Ini sensitivitas jalur sintetis di dalam OHLC asli, bukan tick asli, bukan batas matematis seluruh kemungkinan jalur.
- Stop dibulatkan turun, TP dibulatkan naik ke fraksi BEI. Gap melewati stop dieksekusikan pada open yang tersedia. Limit TP yang sudah marketable saat open memakai open dengan asumsi full fill; antrean tidak diketahui.
- Sensitivitas biaya eksekusi tambahan: 0, 10, 30 bps atas nilai jual. Bukan rekonstruksi actual bid/ask, bukan asumsi literal limit terisi di bawah limit.
- Pemisahan waktu deskriptif: early sebelum 2026-09-10, late sesudahnya. Bukan holdout prospektif karena universe dipilih retrospektif.

## Hasil utama: seluruh sinyal

Tabel memakai fee broker + biaya tambahan 10 bps. Rentang berasal dari dua skenario jalur OHLC; bukan confidence interval. Return adalah mean per transaksi pada modal terpakai, bukan return portofolio.

| Metode | N | Mean net % | Win rate % |
|---|---:|---:|---:|
| OPEN | 100 | 1.34 | 57.00 |
| TP2.5_SL3 | 100 | 0.46–0.64 | 40.00–43.00 |
| TP3.5_SL3 | 100 | 0.54–0.76 | 39.00–42.00 |
| TRAIL2_ENTRY | 100 | 0.60–0.96 | 28.00–37.00 |
| TRAIL2_OPEN | 100 | 0.52–0.87 | 28.00–37.00 |
| SL3 | 100 | 0.46 | 32.00 |
| TIME0915 | 100 | 0.51 | 36.00 |

## Satu saham per hari: hasil tidak konklusif

| Metode | N | OHLC mean % | OLHC mean % |
|---|---:|---:|---:|
| OPEN | 43 | 1.429 | 1.429 |
| TRAIL2_ENTRY | 43 | 1.611 | 1.063 |
| TRAIL2_OPEN | 43 | 1.521 | 0.906 |

Paired bootstrap 5.000 resampling tanggal pada 43 pasangan (TRAIL2_ENTRY minus OPEN, percentage points); interval deskriptif 95% tidak mengatasi selection bias:

- OHLC: selisih mean +0.182 pp; interval [-0.927, +1.595] pp.
- OLHC: selisih mean -0.366 pp; interval [-1.531, +1.158] pp.

## MCAS 8–9 Oktober: entry Rp284, 703 lot

Data 1 menit tanggal 9 Oktober mencatat: 09:00 O312/H316/L294/C304; 09:02 H326; 09:12 L260; 09:15 O288. Candle 09:00 mempunyai volume nol di feed meskipun OHLC bergerak, sehingga memerlukan verifikasi Chartbit/tape broker sebelum dianggap rekonstruksi eksekusi.

| Skenario | Harga simulasi | Net sesudah fee, sebelum slippage |
|---|---:|---:|
| Open | 312 | Rp1.883.618 (+9,42%) |
| Trailing aktif sejak awal, OHLC | 308 | Rp1.603.121 (+8,02%) |
| Trailing aktif sejak awal, OLHC | 304 | Rp1.322.624 (+6,61%) |
| Hanya SL3 hingga deadline | 274 | -Rp781.103 (-3,91%) |
| Exit 09:15 | 288 | Rp200.636 (+1,00%) |

Stop trailing dari peak 326 adalah 318, tetapi order aktif sejak open pada dua skenario ini sudah terpicu pada candle pertama. Memilih 326 lalu menghitung trailing secara retrospektif akan melebihkan hasil. Harga simulasi stop bukan bukti fill broker. TP limit 292/294 yang sudah marketable saat pembukaan dapat memperoleh harga pembukaan dalam model, bukan otomatis dibatasi profit persis 2,5%/3,5%.

## Koreksi backtest lama

Reproduksi dari CSV lama mendapatkan 331 sinyal, 82,779% memiliki high H+1 di atas entry, mean high +6,384%, dan gross close win rate 34,441%. Itu data harian; tidak membuktikan waktu high di 15 menit pertama. Sebanyak 94/331 sinyal menyentuh TP2,5 dan SL2,5 pada hari yang sama, sehingga mendahulukan TP secara otomatis bersifat optimistis. Filter lama volume >1x, berbeda dari radar >=1,5x.

## Batas data dan keputusan

95 dari 100 candle pembukaan memiliki volume nol di feed. Tidak ada historical bid/ask, kedalaman antrean, latency, partial fill, atau status papan/FCA point-in-time. Karena itu hasil tidak membuktikan 703 lot atau order Rp20 juta dapat diisi pada harga model. Risiko likuiditas, suspensi dan corporate action belum dimodelkan lengkap. Sample universe terpilih dan periode pendek tidak mendukung klaim generalisasi pasar.

Keputusan: belum menghapus fixed SL atau mengganti default menjadi trailing-only berdasarkan audit ini. OPEN layak menjadi pembanding utama pada uji maju; trailing 2% tetap kandidat untuk diuji. Validasi selanjutnya memerlukan order activation timestamp, Initial Stop Price Stockbit, tape/Chartbit 1 menit atau tick yang valid, dan catatan fill/partial fill. Paper/shadow tracking pada sinyal mendatang diperlukan sebelum promosi strategi. Tidak ada transaksi nyata atau order broker yang dikirim.

## Stockbit dan sumber aturan

- [Stockbit: perhitungan dan market FAK](https://help.stockbit.com/id/article/auto-order-trailing-stop-hal-hal-yang-perlu-diketahui-dalam-order-trailing-stop-95qmip/): initial stop dari harga saat pasang, dibulatkan turun; stop naik bersama peak.
- [Stockbit: status dan partial match](https://help.stockbit.com/id/article/auto-order-trailing-stop-apa-itu-trailing-stop-dan-bagaimana-cara-aksesnya-1jha3uq/): sisa lot partial match ditarik; trigger bukan jaminan full match.
- [BEI: jam, auction dan fraksi](https://www.idx.id/id/produk-layanan/jam-dan-mekanisme-perdagangan/): harga 200–<500 memakai fraksi 2; target entry 284 x 1,025 menjadi limit 292 bila dibulatkan naik. Prapenutupan bukan jaminan harga sudah terkunci sejak 15:50.

## Reproduksi dan berkas

Jalankan dari root workspace:

```sh
python3 laravel-app/quant/fetch_bsjp_exit_audit.py
python3 laravel-app/quant/audit_bsjp_exit.py
python3 -m unittest discover -s laravel-app/quant -p test_audit_bsjp_exit.py
```

Fetch mengakses periode relatif penyedia; gunakan JSON cache dan hash audit_metadata.json untuk mereproduksi snapshot tanggal ini. exit_summary.csv memuat semua sensitivitas biaya dan pembagian periode; exit_trades.csv memuat detail transaksi. Lima tes edge case lulus (gap, urutan candle, larangan memakai high masa depan, deadline, fraksi/fee). Laporan ini tidak mengubah keputusan formal Phase B yang mengevaluasi kandidat lain.
