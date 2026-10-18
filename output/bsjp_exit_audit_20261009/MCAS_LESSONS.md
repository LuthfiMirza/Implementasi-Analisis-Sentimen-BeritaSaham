# MCAS: hipotesis exit 318–320

Riset 9 Oktober 2026, dibuat setelah melihat kejadian MCAS. Ini analisis in-sample, bukan strategi tervalidasi atau bukti fill broker. Semua keterbatasan data pada REPORT.md tetap berlaku, khususnya volume pembukaan nol, tidak ada tick/bid/ask/latency/partial fill, universe terpilih, dan entry berdasarkan close final.

## Rekonstruksi indikatif

Entry pengguna 284, 703 lot. Feed satu menit: 09:00 O312 H316 L294 C304; 09:01 H314; 09:02 O316 H326 L314 C320; 09:03 O322 H326 L314 C316.

| Aturan | Harga model | Waktu | Net setelah fee, sebelum slippage |
|---|---:|---|---:|
| Open | 312 | 09:00 | Rp1.883.618 |
| Trailing 2% sejak open | 304–308 | 09:00 | Rp1.322.624–1.603.121 |
| TP 12%, limit dibulatkan naik | 320 | 09:02 | Rp2.444.612 |
| Break high menit pertama lalu trailing 2% | 318 | 09:02–09:03 | Rp2.304.364 |
| Break high menit pertama lalu trailing 1,5% | 320 | 09:02 | Rp2.444.612 |
| Tunda trailing 2% sampai 09:02 | 318 | 09:02–09:03 | Rp2.304.364 |

Aturan breakout: tunggu candle 09:00 selesai; level aktivasi = high candle pertama + satu fraksi, yaitu 318. Sebelum aktivasi tetap memakai hard stop 3% dari entry. Setelah harga mencapai aktivasi, peak mulai dari harga aktivasi, mengikuti harga selanjutnya; exit ketika menyentuh floor-ke-fraksi(peak x 0,98), atau paling lambat 09:15. Tidak memakai high 326 sebelum terjadi. Peak 326 memberi trigger 318. Dengan trailing 1,5%, trigger 320.

Stockbit trailing standar mulai mengikuti harga sejak pemasangan. Kondisi aktivasi breakout di atas adalah logika riset; implementasi conditional otomatis tidak diverifikasi. Aktivasi manual berpotensi terlambat, dan order FAK tidak menjamin harga maupun full fill. https://help.stockbit.com/id/article/auto-order-trailing-stop-hal-hal-yang-perlu-diketahui-dalam-order-trailing-stop-95qmip/

## Pengujian pembanding

Data publik 1 menit 7 hari diunduh untuk seluruh 21 saham. Dari 100 sinyal sebelumnya, hanya 9 mempunyai seluruh 16 candle 09:00–09:15 dalam jendela tersebut. Ini convenience subset, bukan sampel representatif. Dua di antaranya MCAS; pembanding tanpa MCAS hanya 7 kejadian. Dua skenario intrabar OHLC dan OLHC diuji. Rentang berikut bukan confidence interval atau batas pasti semua jalur tick.

| Model | Mean net 9 sinyal, fee + biaya tambahan 10 bps |
|---|---:|
| Open | +3,438% |
| Trailing 2% langsung | +2,977–3,601% |
| TP8 + SL3 | +5,595% |
| TP12 + SL3 | +6,219% |
| Break menit pertama + trailing 2% | +5,406–6,872% |
| Break menit pertama + trailing 1,5% | +4,860–5,369% |
| Tunggu 09:02 + trailing 2% | +5,258–6,419% |
| Separuh open, separuh breakout trailing 2% | +4,422–5,155% |

Split 50/50 memakai notional sama, bukan pembulatan 703 lot. Tidak menyimulasikan latency saat mengganti atau memasang order. Semua kandidat memiliki hard stop 3% sebelum aktivasi dan deadline 09:15; trailing langsung memakai simulator baseline sebelumnya. Keunggulan angka kecil ini belum dapat digeneralisasi. Parameter 12%, 1 menit, 2 menit dan 1,5% dipelajari dari kasus MCAS, sehingga terdapat risiko overfitting dan multiple comparisons.

Uji ulang target tetap pada 100 sinyal dengan data 5 menit dan biaya sama: OPEN mean +1,339%, win 57%; TP8+SL3 mean +0,390%, win 33%; TP12+SL3 mean +0,513%, win 33%. Kedua jalur candle memberi angka sama untuk target tetap ini. Jadi target 320 yang cocok untuk MCAS justru lebih buruk secara rata-rata pada sampel lebih luas.

## Keputusan

Belum ada strategi paling profit yang tervalidasi. Kandidat menarik untuk uji maju adalah breakout high menit pertama, trailing 2%, hard stop sebelum aktivasi, deadline 09:15. Dilarang menganggap menunggu 09:02 atau memasang TP12 selalu unggul berdasarkan MCAS. Tetapkan aturan sebelum sesi mendatang, catat waktu aktivasi dan real fill, evaluasi pada sampel baru; tidak memilih ulang parameter setelah melihat hasil.

Detail: mcas_hypotheses_case.csv, mcas_hypotheses_trades.csv, mcas_hypotheses_summary.csv (termasuk tanpa MCAS), mcas_hypotheses_missing.csv, mcas_hypotheses_100_tp.csv. Kode: quant/research_bsjp_mcas_exit.py. Snapshot JSON dan manifest tambahan tersimpan di folder ini. Tidak mengubah posisi, dashboard, atau mengirim order.
