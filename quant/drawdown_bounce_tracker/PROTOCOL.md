# Protokol evaluasi prospektif: aturan "IHSG + saham crash bareng" (Fase AB → AC)

**Ditetapkan dan di-commit SEBELUM sinyal live pertama tercatat.** Aturan di bawah tidak boleh
diubah setelah pencatatan dimulai. Perubahan yang benar-benar perlu ditambahkan sebagai amandemen
bertanggal baru di bawah, bukan mengedit isi yang sudah ada.

## Kenapa protokol ini ada

Fase AB menemukan aturan ini positif secara historis untuk BUMI (27 episode independen, konsisten
discovery vs holdout) via backtest. **Backtest historis cuma lolos gerbang pertama** — proyek ini
sudah berkali-kali menemukan pola yang kelihatan bagus secara historis gagal total begitu diuji ke
depan (forward) dengan disiplin yang sama seperti tracker `signal_tracker/` (Zeta AI) sebelumnya.
Tracker ini adalah gerbang kedua: memantau kejadian sinyal BARU secara live, dicatat SEBELUM tahu
hasilnya, supaya tidak ada ruang untuk menipu diri sendiri (pilih sampel, ubah aturan setelah lihat
hasil, dsb).

## Definisi sinyal (dari Fase AB, tidak berubah)

- **Universe**: BUMI dan DEWA, dievaluasi terpisah.
- **Entry trigger**: return kumulatif 2 hari bursa IHSG (`^JKSE`) DAN saham, keduanya `<= -5%`,
  dicek di penutupan tiap hari bursa.
- **Entry eksekusi**: penutupan hari bursa BERIKUTNYA setelah hari trigger (bukan hari trigger
  itu sendiri — sama seperti metodologi backtest Fase AB, hindari lookahead).
- **Exit**: fixed holding period, **10 hari bursa sebagai metrik utama** (titik manis Fase AB
  untuk BUMI: +6,47% discovery / +7,34% holdout). **5 hari bursa dicatat paralel sebagai
  pembanding sekunder** — kedua horizon ditetapkan SEKARANG, sebelum sinyal pertama, supaya tidak
  ada pilihan horizon setelah lihat hasil.
- **Biaya**: 0,80% round-trip, sama seperti semua eksperimen trading proyek ini.

## Status per saham (WAJIB dibaca sebelum menafsirkan laporan)

- **BUMI: tracked penuh.** 27 episode independen di backtest historis, melewati ambang minimum
  n≥20, tidak didominasi satu krisis. Kandidat paling kredibel sejauh ini di proyek ini.
- **DEWA: tracked, tapi berlabel `exploratory` — JANGAN dipakai untuk kesimpulan apa pun sampai
  ada catatan eksplisit yang mencabut label ini.** Backtest Fase AB cuma 18 episode independen,
  26% sinyal historisnya berasal dari satu bulan (Okt 2008, crash Lehman) — sample historisnya
  sendiri sudah tidak cukup meyakinkan, apalagi baru mulai live.

## Realita frekuensi (supaya ekspektasi wajar)

Sinyal ini LANGKA by design (ambang 5% dua hari itu ketat). Di backtest 22 tahun BUMI cuma 27
episode independen ≈ **1,2 kejadian per tahun**. Realistis: mencapai n≥20 sinyal live bisa makan
waktu BERTAHUN-TAHUN, bukan bulan. Laporan di bawah n minimum WAJIB berlabel "belum cukup data",
bukan kesimpulan dini — sama seperti aturan `signal_tracker/` (Zeta AI).

## Deteksi otomatis (beda dari signal_tracker/ yang manual)

Karena aturan ini murni hitungan dari harga OHLCV milik proyek sendiri (bukan sinyal dari sumber
eksternal seperti Telegram), deteksi dilakukan OTOMATIS harian oleh `detect_signal.py`, dijadwalkan
via `research:detect-drawdown-bounce-signal` (lihat `routes/console.php`). Tidak ada input manual
manusia di titik pencatatan sinyal — menghapus kemungkinan bias pemilihan "sinyal mana yang mau
dicatat".

## Aturan penilaian hasil (per sinyal)

1. Entry price = penutupan hari bursa setelah trigger.
2. Exit price (10 hari) & exit price (5 hari) = penutupan pada hari bursa ke-10 dan ke-5 setelah
   entry.
3. `net_return = (exit_price / entry_price - 1) - 0,008`.
4. **Semua sinyal yang trigger MASUK ke perhitungan**, termasuk yang hasilnya rugi — tidak ada
   yang dibuang dari penyebut.

## Pembanding wajib

1. **Beli-diamkan** saham yang sama, entry di harga yang sama, dipegang selama horizon yang sama
   (10 hari / 5 hari).
2. **IHSG** periode yang sama.

Sinyal dianggap punya nilai tambah HANYA jika net return rata-ratanya mengalahkan KEDUA
pembanding itu — bukan cuma salah satu.

## Yang dilaporkan (semua, tidak dipilih-pilih)

- Tabel gaya "equity curve": tanggal, ekuitas hipotetis, P&L per kejadian — format yang sama
  seperti laporan performance broker riil, supaya langsung bisa dibandingkan.
- Win rate, rata-rata & median return net biaya, sebaran (bukan cuma rata-rata).
- Delta terhadap beli-diamkan dan terhadap IHSG.
- Perbandingan horizon 10 hari vs 5 hari, berdampingan.
- BUMI dan DEWA dilaporkan TERPISAH, tidak digabung (status kredibilitasnya beda).

## Integritas data

- `tracker.sqlite3`, tabel `signals` dan `outcomes` bersifat **append-only** — trigger SQL
  memblokir `UPDATE`/`DELETE`, bukan cuma konvensi (pola sama seperti `signal_tracker/`).
- `detected_at` (kapan sistem mendeteksi otomatis) disimpan terpisah dari `trigger_date` (hari
  bursa yang memicu sinyal).

## Ambang minimum sebelum kesimpulan ditarik

Jangan simpulkan apa pun sebelum **n ≥ 20 sinyal tracked** DAN horizon (10 hari / 5 hari) sudah
lewat untuk semuanya. Di bawah itu: laporkan sebagai "belum cukup data", tampilkan progres
(n saat ini / 20), bukan verdict dini.

---

*Protokol ini dibuat 2026-07-31, sebelum sinyal live pertama terdeteksi. Backtest historis Fase AB
(sudah ada sebelum protokol ini, di `quant/run_ihsg_drawdown_entry_experiment.py`) TIDAK dihitung
sebagai bagian dari n live — protokol ini murni untuk kejadian BARU sejak hari ini ke depan.*
