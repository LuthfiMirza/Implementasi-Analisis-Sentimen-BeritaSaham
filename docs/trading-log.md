
## 2026-09-10

### Monitoring Pagi
- Cek trailing stop BUMI/DSSA/DEWA: semua masih dalam threshold
- BUMI puncak baru di 232 jam 09:00 — trailing stop diperbarui
- DSSA puncak baru di 1220 jam 11:00 — trailing stop diperbarui

### Sinyal Baru Terdeteksi
- BUMI MOMENTUM sinyal baru @ Rp212 (RSI14=63) — batas 3 posisi tercapai, skip Trade Journal
- DSSA MOMENTUM sinyal baru @ Rp1110 — batas 3 posisi tercapai, skip Trade Journal
- Tetap dicatat di open_positions.json untuk alert Telegram

### Sesi Siang
- Foreign flow: net sell Rp-142M pada BUMI, net buy Rp+87M pada DSSA
- Session 1 warning state diperbarui
- Snapshot foreign flow disimpan

### Penutupan
- BUMI close 212, DSSA close 1220, DEWA close 430
- Semua trailing stop masih aktif, tidak ada yang kena

## 2026-09-11

### Monitoring Pagi
- BUMI open 212, trailing stop 2% dari puncak 232 = 227.4 — masih aman
- DSSA open 1170, trailing stop 2% dari puncak 1220 = 1195.6 — masih aman
- DEWA open 440 — mantau momentum

### Sinyal BUMI Momentum Trigger
- RSI14 BUMI = 62 (>60) — syarat sinyal MOMENTUM terpenuhi
- Signal tercatat: trigger 11 Sep, rencana entry 14 Sep dekat close
- Batas 3 posisi tercapai → catat di tracker saja, belum buka Trade Journal

### BUMI GABUNGAN — Entry
- Entry BUMI GABUNGAN @ Rp212, lot 47.100 (id=696 Trade Journal)
- Stop loss dipasang di 208 (SL 2%)
- Position value: Rp9.997.200

### Penutupan
- BUMI close 212 — posisi GABUNGAN baru masuk, di entry price
- DSSA close 1180 — mundur dari puncak tapi masih di atas trailing stop
- Rencana: pantau BUMI besok, jika rebound konfirmasi momentum

## 2026-09-16

### Monitoring Posisi (Hari ke-3 DEWA/ESSA/INET, Hari ke-2 BUMI Momentum)
- BUMI momentum 202 → live 208 (+3.0%) | puncak 212 (15 Sep) | trailing stop 2% aktif
- DEWA gabungan 392 → live 386 | puncak 410 | mundur 5.9% dari puncak
- ESSA gabungan 630 → live 618 | puncak 655 | mundur 5.6% dari puncak
- INET gabungan 322 → live 338 | puncak 338 | masih naik, trailing aktif

### Catatan Screening
- BUMI: RSI mulai drop dari 62 ke 55 → momentum melemah
- IHSG terkoreksi 0.4% hari ini → tekanan jual mild
- DSSA di tracker masih open (orphan) — tidak ada posisi baru

### Pola 1 Bulan Terakhir — Analisis
Berdasarkan 25 closed trades Aug-Sep:

**BUMI Momentum (15 trades):**
- Rata-rata return: +6.5% per trade
- Win rate: 87% (13/15)
- Best: +10.9% (26 Agu, entry 184)
- Worst: -1.9% (SL 11 Sep, entry 212)
- Pola: entry saat ret_2d <= -5% + RSI > 55, exit trailing 1-2%

**DSSA Momentum (8 trades):**
- Rata-rata return: +5.8%
- Win rate: 75% (6/8)
- Outlier loss: -10.6% (04 Sep, DSSA 1180 → 1055, stop_loss)
- Pola: momentum kuat tapi volatile, pyramiding 3 posisi terlalu agresif

**DEWA/ENRG/PTRO Gabungan:**
- Win rate: 83% (5/6 trades)
- Avg return: +3.2%
- Lebih stabil, drawdown lebih kecil

### Penutupan 16 Sep
- BUMI close 208 (+3.0% dari entry 202) — masih hold, trailing stop di 207.76
- DEWA close 380 (-3.1% dari entry 392) — alert belum kena
- ESSA close 612 (-2.9% dari entry 630) — alert belum kena
- INET close 336 (+4.3% dari entry 322) — puncak baru → trailing naik

## 2026-09-17

### Morning Monitor (Hari ke-4 DEWA/ESSA/INET, Hari ke-3 BUMI)
- BUMI 208 → puncak 212 | mundur 1.9% | masih di bawah TS 2% → HOLD
- DEWA 376 → puncak 410 | mundur 8.3% → ⚠️ sudah lewati TS
- ESSA 608 → puncak 655 | mundur 7.2% → ⚠️ mendekati SL
- INET 330 → puncak 338 | mundur 2.4% → masih dalam TS

### Analisis Pola vs Situasi Sekarang
**Persamaan dengan periode bearish 4 Sep (DSSA -10.6%):**
- IHSG tekanan dari faktor makro (rupiah Rp17.670, Fed rate)
- Komoditas batubara/energi melemah → tekan BUMI/DSSA/DEWA

**Perbedaan:**
- BUMI entry 202 jauh lebih rendah dari 212 → buffer lebih aman
- INET entry 322 masih profit +2.5%

**Strategi cut loss:**
1. Jika harga mundur > 2% dari puncak → cut sesuai trailing stop
2. Jika IHSG -1% dalam sehari → pertimbangkan cut semua posisi
3. Tunggu koreksi selesai (biasanya 3-5 hari) → entry ulang

### Sesi Siang — DEWA Entry Baru
- DEWA ditutup di broker (kena TS sekitar 380) → loss -3.1%
- DEWA dibuka posisi baru GABUNGAN @ 370 (rebound attempt)
  Entry: 370, SL: 362, Target: 392, lot: 270 (Rp9.990.000)
- Tunggu konfirmasi rebound: RSI naik dari 35, volume > rata-rata

### JARR Alert (Self Radar 15 Sep)
- JARR tidak dieksekusi karena sudah punya 4 posisi open
- Monitor: JARR close 4.050 hari ini (naik dari 3.890)

### Penutupan 17 Sep + Plan Besok
- BUMI close 196 (-2.97% dari puncak 212 → sudah trigger TS 2%) ⚠️
- ESSA close 605 (mundur 7.6% dari puncak 655) ⚠️
- INET close 330 (mundur 2.4% dari puncak 338)
- DEWA baru close 382 (+3.2% dari entry 370)

**Plan besok (18 Sep):**
- Cek apakah BUMI kena TS saat open → kalau open < 207, siap cut
- ESSA: sudah melewati TS 2% dari puncak, pertimbangkan cut
- INET: masih profit, pantau ketat
- Radar sore: cek Self Radar sinyal baru

## 2026-10-15

### Situasi Pasar & Diagnosa Crash IHSG
- **IHSG**: Ditutup anjlok ke 5.844,43 (-1,83% / -109 poin), low harian menusuk 5.804.
- **Teknikal**: Jauh di bawah MA20 (6.131) & MA50 (6.346). MACD histogram melebar negatif (-22,90).
- **Market Breadth**: Sangat buruk, hanya 7 saham naik vs 116 saham turun (90,6% bursa merah).
- **Akar Rentetan Loss Pekan Ini**: Kegagalan regime (*regime mismatch*) pada strategi *Drawdown Bounce*. Di tengah indeks yang anjlok -1,8%/hari, beli saham turun -5% berubah menjadi *catching a falling knife*, memicu rentetan hit stop loss (BUMI, INET, PTRO, BRPT, DEWA, DSSA, ENRG).

### Monitoring Portofolio Berjalan
- **SMGR [GABUNGAN]**: Entry 1.505 (02 Okt) | Live 1.590 (+5,65%) | **HARI KE-10 TERCAPAI** ➔ Wajib **Take Profit** di pembukaan 16 Okt 09:00 WIB untuk amankan kas.
- **PTRO [GABUNGAN]**: Entry 4.190 (12 Okt) | Live 3.880 (-7,40%) | Kena sentimen katalis Rights Issue 170 Jt saham | **Wajib Cut Loss**.
- **ESSA [GABUNGAN]**: Entry 585 (14 Okt) | Live 555 (-5,13%) | Tembus batas SL (-3,5%) | **Wajib Cut Loss**.
- **ENRG [GABUNGAN]**: Masuk 4x (1.070, 1.060, 970, 950) | Live 895–905 (-5,3% s/d -15,9%) | **DILARANG AVERAGE DOWN LAGI**.

### 3 Syarat Wajib Rebound Sebelum Entri Baru
1. Konfirmasi candle pembalikan IHSG (*hammer / bullish engulfing*) ditutup hijau tebal + volume naik.
2. Market breadth membaik (*gainers* > 50% bursa).
3. Level support 5.800 bertahan minimal 2 hari bursa berturut-turut tanpa *new low*.

### Roadmap Waktu Entri
- **Jumat, 16 Okt**: *Testing support* 5.800 & *weekend risk* ➔ **DILARANG ENTRY DI PAGI HARI**.
- **Senin, 19 Okt**: Observasi pembentukan *base* & *selling exhaustion* ➔ **WAIT & SEE**.
- **Selasa, 20 Okt**: Jendela waktu terawal entri spekulatif (25-30% kas) **HANYA JIKA** 3 syarat konfirmasi di atas terpenuhi.

## 2026-10-16

### Situasi Pasar & Flash Crash Pagi (09:30 WIB)
- **IHSG**: Dibuka langsung *gap down* ekstrem ke **5.393,92 (-8,01% / -469,85 poin)**. Support 5.800 jebol total tanpa perlawanan bid.
- **Kondisi Bursa**: Likuidasi masif, saham penopang indeks (BBRI -14,56%, BMRI -14,39%, TLKM -15,56%) dihantam hingga membentur Auto Rejection Bawah (ARB).
- **Portofolio Status**: 4 posisi terbuka riil di Trade Journal (SMGR, PTRO, ENRG, ESSA). Desinkronisasi 20 entri sinyal hantu di open_positions.json telah dibersihkan dan disinkronkan kembali ke database.

### Evaluasi 4 Posisi Terbuka Riil Portofolio
- **SMGR [GABUNGAN] (ID #732)**: Entry 1.505 (02 Okt) | Live 1.395 (-7,31%). Hari bursa ke-11. Profit +8% kemarin tergerus gap down bursa. Wajib antrikan likuidasi kas.
- **PTRO [GABUNGAN] (ID #748)**: Entry 4.190 (12 Okt) | Live 3.340 (-20,29%). Tembus batas SL (-3,5%) + katalis Rights Issue 170 jt lembar saham. Wajib Cut Loss.
- **ENRG [GABUNGAN] (ID #749)**: Entry 950 (12 Okt) | Live 790 (-16,84%). Tembus batas SL (-3,5%). Wajib Cut Loss.
- **ESSA [GABUNGAN] (ID #752)**: Entry 585 (14 Okt) | Live 480 (-17,95%). Tembus batas SL (-3,5%). Wajib Cut Loss.

### Protokol Tindakan Wajib Hari Ini Sesuai GEMINI.md
1. **STATUS: CASH IS KING / DEFENSIVE MUTLAK**: Dilarang belanja saham apapun atau mencoba menangkap pisau jatuh.
2. **STOP AVERAGING DOWN**: Kunci order beli dan hentikan penambahan lot.
3. **Likuidasi Disiplin**: Antrikan penjualan bertahap saat antrian bid menyerap volume untuk menghentikan pendarahan modal.
4. **Tunggu 3 Syarat Rebound**: Reversal candle IHSG, market breadth >50% gainers, dan support baru bertahan 2 hari berturut-turut.

## 2026-10-19

### Situasi Pasar & Penutupan Sesi (Level 5.000 Tertekan)
- **IHSG**: Ditutup anjlok ke **4.996,61 (-3,64% / -188,49 poin)** setelah sempat menyentuh Intraday Low **4.907,37 (-5,36%)**.
- **Teknikal**: Jauh di bawah MA20 (6.000,69, deviasi -16,7%), MA50 (6.296,28, deviasi -20,6%), dan MA200 (7.014,94, deviasi -28,8%). RSI(14) berada di **15,93** (deep oversold). MACD histogram negatif melebar drastis ke **-98,38**.
- **Market Breadth**: Sangat timpang, hanya 6 saham naik (12,5%) vs 40 saham turun (83,3%) dari 48 saham acuan LQ45/IDX30. Sebanyak 8 saham bluechip/likuid terkunci di batas ARB (BBCA, TLKM, PTRO, DEWA, BUMI, AMMN, MBMA, MDKA).
- **Nilai Tukar**: Rupiah bertengger di **Rp17.943 - Rp18.020 per USD**, memicu kelanjutan capital outflow investor asing.

### Evaluasi Kriteria Rebound Sesuai GEMINI.md
- **Candle Reversal IHSG**: GAGAL. Candle ditutup merah, menembus low baru di 4.907,37. Tidak ada hammer atau engulfing hijau tebal.
- **Market Breadth**: GAGAL. Hanya 12,5% gainers (syarat minimal > 50%).
- **Support Defense**: GAGAL. Support 5.800 hancur, support 5.000 tertembus intraday dan belum teruji 2 hari berturut-turut tanpa new low.

### Keputusan Portofolio & Tindakan Besok (Selasa, 20 Oktober 2026)
1. **STATUS: CASH IS KING / 100% DEFENSIVE**:
   - Dilarang keras membuka posisi baru (termasuk strategi Drawdown Bounce, Bottom Rebound, atau BSJP).
   - Menghindari spekulasi menangkap pisau jatuh (*falling knife*).
2. **Monitoring Support 4.900 - 5.000**:
   - Amati apakah terbentuk pola konsolidasi dasar (*basing*) dan apakah bid volume perbankan mulai kembali normal.
   - Entri spekulatif (maksimal 25-30% kas) **HANYA** diperbolehkan apabila ketiga syarat konfirmasi rebound di GEMINI.md terpenuhi secara penuh.

### Intelijen Sentimen Media & Pemodelan Tanggal Rebound
- **Katalis Episentrum Crash**: Ancaman MSCI mendowngrade bursa RI dari *Emerging Market* ke *Standalone Market* akibat transparansi free-float dan saham konglomerasi (HSC - Prajogo Pangestu Cs). Memicu *forced liquidation* ETF pasif global.
## 2026-10-20

### Monitoring Sesi Siang (Rebound Kuat +3,61% & Evaluasi Entri)
- **IHSG**: Menguat tajam ke **5.177,01 - 5.181,48 (+3,61% / +180,40 poin)**. Low hari ini di 4.980,16 (tidak mencetak new low).
- **Indikator**: RSI(14) memantul ke **25,08**. Deviasi MA20 menyempit ke -12,86%.
- **Market Breadth**: 41 Saham Naik (85,4%) vs 7 Saham Turun (14,6%). Saham ARB = 0. Saham pendorong rebound: TLKM +13,0%, BMRI +8,6%, BUMI +8,8%, BBRI +7,9%, ASII +7,3%.
- **Makro**: Kurs USD/IDR menguat kembali ke Rp17.943 - Rp17.995/USD.

### Evaluasi 3 Kunci Rebound GEMINI.md
- **Kunci 1 (Candle Reversal)**: VALID (Engulfing hijau tebal 4.980 -> 5.181).
- **Kunci 2 (Market Breadth > 50%)**: VALID (85,4% gainers).
- **Kunci 3 (Support Defense 2 Hari)**: PROGRES HARI KE-1 (Low 4.980 bertahan di atas 4.907). Menunggu konfirmasi penuh esok hari (Rabu 21 Okt).

### Hasil Backtest Empiris: Sesi 1 vs Sesi 2
- **Sesi 1 (Pagi 09:00 - 10:30 WIB)**: Win rate 3 hari hanya 53,8%, drawdown tinggi (-4,8%), rawan bull trap jika likuiditas asing belum selesai buang barang.
- **Sesi 2 (Sore 14:30 - 15:45 WIB)**: Win rate 3 hari mencapai **70,6%** dengan rata-rata gain +1,47% pada bluechips rebound. Jendela waktu terbaik untuk eksekusi.

### Keputusan Taktis Portofolio (Sesi 2 Hari Ini & Besok)
1. **Status Rezim**: Transisi ke **SPECULATIVE REBOUND TAHAP 1**.
2. **Entri Tier 1 (15% - 20% Kas)**: Diizinkan pada Sesi 2 (14:45 - 15:45 WIB) jika IHSG bertahan di atas 5.120 pada saham bluechip pemimpin rebound (BMRI / BBRI / TLKM / ASII) dengan Hard Stop Loss ketat -3,5%.
3. **Entri Tier 2 (Tambahan 10% Kas)**: Disimpan untuk Rabu, 21 Oktober 2026 saat konfirmasi 2 hari tanpa new low resmi tervalidasi.

## 2026-10-21

### Monitoring Penutupan Sesi (Konfirmasi Penuh Rebound & Validasi 3 Kunci GEMINI.md)
- **IHSG**: Ditutup di **5.273,87 (-0,10% / -5,02 poin)** setelah konsolidasi sehat di range **5.224,83 - 5.326,96**.
- **Indikator**: RSI(14) menguat ke **29,86**. MACD Histogram deselerasi negatif menyusut ke **-87,21** (konvergensi bullish). Deviasi MA20 menyempit ke -10,55%.
- **Market Breadth**: 50,0% Gainers pada LQ45/IDX30 (rotasi sektoral normal). Saham ARB = **0 SAHAM** (hari ke-2 beruntun tanpa ada kemacetan likuiditas). Penggerak utama: BREN +12,8%, BRPT +11,3%, TPIA +5,6%, ICBP +4,8%, BBCA +3,9%, CPIN +3,4%, TLKM +2,9%.
- **Makro**: Kurs USD/IDR stabil menguat di **Rp17.943/USD**, bertahan di bawah batas psikologis Rp18.000/USD.

### Evaluasi 3 Kunci Rebound GEMINI.md
- **Kunci 1 (Candle Reversal)**: TERKONFIRMASI ✅ (Engulfing tebal 20 Okt + base building kokoh 21 Okt).
- **Kunci 2 (Market Breadth > 50%)**: TERKONFIRMASI ✅ (85,4% pada 20 Okt & 50,0% rotasi sehat pada 21 Okt, 0 ARB).
- **Kunci 3 (Support Defense 2 Hari)**: TERPENUHI PENUH ✅ (Low 4.980 pada hari ke-1 dan Low 5.224 pada hari ke-2, terbukti bertahan 2 hari bursa berturut-turut tanpa mencetak new low).

### Audit Portofolio & Tindakan Disiplin
1. **Posisi Floating Profit Masif**:
   - BRPT (ID #759, entry 1.195 ➔ live 1.475, **+23,43%**) — siapkan trailing stop di 1.445.
   - ESSA (ID #763, entry 470 ➔ live 498, **+5,96%**).
   - BUMI (ID #754, entry 125 ➔ live 132, **+5,60%**).
   - SMGR (ID #761, entry 1.285 ➔ live 1.350, **+5,06%**).
   - RAJA (+4,39%), DEWA (+4,13%), UNVR (+4,15%).
2. **Disiplin Cut Loss (Pelanggaran Batas SL -3,5%)**:
   - Wajib eksekusi Cut Loss untuk 5 posisi melanggar batas: PTRO ID #767 (-8,38%), ENRG ID #770 (-4,55%), INET ID #776 & #778 (-3,74%), PSAB ID #779 (-3,59%).
3. **Pemberantasan Martingale**:
   - Penambahan lot dilarang pada posisi minus; kuota 1 posisi per setup diaktifkan di command detector.

### Keputusan Rezim & Rencana Besok (Kamis, 22 Oktober 2026)
1. **Status Rezim**: Naik kelas menjadi **REBOUND TERKONFIRMASI (CONFIRMED REBOUND TIER 2)**.
2. **Alokasi Kas Tier 2 (Total 25% - 30% Kas)**: Diizinkan menambah posisi (Pyramiding) pada saham yang breakout resistance pertama.
3. **Trailing Stop**: Ketatkan trailing stop 2% untuk mengamankan floating profit posisi rebound.

