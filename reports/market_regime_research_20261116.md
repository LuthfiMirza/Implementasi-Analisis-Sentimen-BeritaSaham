# Laporan Riset Kuantitatif & Pasar: Konsolidasi IHSG di Atas MA20 (5.320,98), Audit Eksekusi 4 Trade 13 Nov, & Evaluasi Skenario A vs B Sinyal 16 November 2026

- **Tanggal Riset**: Senin, 16 November 2026 (Penutupan Sesi Perdagangan 16:00 WIB)
- **Status Rezim Pasar**: **KONSOLIDASI NORMAL / DI ATAS MA20 (IHSG 5.320,98 > MA20 5.187,17)**
- **Indeks Acuan**: IHSG (`^JKSE`) Ditutup di **5.320,98 (-0,44% / -23,43 poin)** | Range: Low **5.272,47** — High **5.355,60**
- **Evaluasi Portofolio Sinyal 13 Nov**: **4 Trade Ditutup Disiplin Hari Ini**
  - **2 Posisi Panen Cuan via Lapis 2 Trailing Stop 2,0%**:
    * `PTRO`: Puncak **Rp 2.720 (+7,09%)** &rarr; Kunci Cuan @ **Rp 2.665,60 (+4,94%)**
    * `BUMI`: Puncak **Rp 140 (+2,94%)** &rarr; Kunci Cuan @ **Rp 137,20 (+0,88%)**
  - **2 Posisi Eksekusi Pengaman Lapis 1 Hard Stop Loss -3,5%**:
    * `BRPT`: Low drop pagi ke Rp 775 &rarr; Auto-Close SL @ **Rp 776,82 (-3,50%)**
    * `ENRG`: Low drop pagi ke Rp 640 &rarr; Auto-Close SL @ **Rp 646,55 (-3,50%)**
- **Sinyal Baru Terdeteksi Hari Ini (16 Nov 2026)**:
  - **Drawdown Bounce**: `BRPT` (Grade A+, Skor 90 @ Rp 750), `ENRG` (Grade A, Skor 78 @ Rp 630).
  - **BSJP Momentum Sore**: `AUTO` (Grade A+, Skor 88 @ Rp 3.240), `BKDP` (Grade A @ Rp 159), `FAST` (Grade A @ Rp 334), `COIN` (Grade B Rocket @ Rp 472), `KOTA` (Grade B Rocket @ Rp 69).
  - **Peringatan Dini Skenario B (Day-2 Flush Watch 17 Nov)**: `DEWA` (Ret2D -5,43%), `PTRO` (Ret1D -5,51%), `RAJA` (Ret2D -7,66%).

---

## 1. Analisis Rezim Pasar (Market Regime Check)

Berdasarkan aturan baku pada `GEMINI.md` Seksi 1:
1. **Pemeriksaan Crash Guard**:
   - IHSG turun `-0,44%` hari ini (jauh di bawah batas crash guard `>= -1,0%`).
   - Posisi IHSG (`5.320,98`) tetap bertahan nyaman **di atas MA20 (`5.187,17`)** dengan deviasi `+2,58%`.
   - **Kesimpulan Rezim**: Pasar berada dalam fase **konsolidasi sehat pasca-reli**, BUKAN pasar jatuh bebas (*falling knife*). Sinyal pantulan diskon tetap valid untuk dianalisis dengan seleksi ketat.

---

## 2. Audit Eksekusi 4 Posisi 13 November 2026

Pada sesi perdagangan hari ini (16 Nov 2026), seluruh 4 posisi terbuka dari Jumat (13 Nov) berhasil dieksekusi oleh sistem 3-Lapis Proteksi (`Auto-Close Engine`):

| Saham | Entry (13 Nov) | Puncak Intraday (16 Nov) | Realisasi Exit | Return (%) | Tipe Exit | Catatan Kronologis |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **PTRO** | Rp 2.540 | **Rp 2.720 (+7,09%)** | **Rp 2.665,60** | **+4,94%** | **Trailing Stop 2,0%** | Sempat terbang ke 2.720 pukul 09:30 WIB. Pullback 2% memicu trailing stop di 2.665, mengamankan cuan sebelum harga dibanting ke 2.400 sore hari. |
| **BUMI** | Rp 136 | **Rp 140 (+2,94%)** | **Rp 137,20** | **+0,88%** | **Trailing Stop 2,0%** | Sempat menyentuh 140 pukul 09:45 WIB. Trailing stop 2% mengunci profit kecil di 137,20 sebelum harga turun ke 131. |
| **BRPT** | Rp 805 | Rp 810 (+0,62%) | **Rp 776,82** | **-3,50%** | **Hard Stop Loss** | Pagi langsung ditekan guyuran bandar hingga menyentuh Low 775. Hard Cut Loss berhasil memotong kerugian tepat di -3,5% (menghindari floating loss -6,8% saat closing di 750). |
| **ENRG** | Rp 670 | Rp 670 (+0,00%) | **Rp 646,55** | **-3,50%** | **Hard Stop Loss** | Pagi langsung drop ke Low 640. Hard Cut Loss memotong kerugian di -3,5% (menghindari kerugian -6,0% saat closing di 630). |

> **Pelajaran Kunci**:
> 1. Efektivitas Trailing Stop pada `PTRO` (+4,94%) membuktikan keunggulan *Capture Ratio 65,8%* — keuntungan tetap terkunci saat saham berbalik arah drastis.
> 2. Hard Stop Loss -3,5% pada `BRPT` dan `ENRG` menyelamatkan portofolio dari penurunan lebih dalam hingga -6,8% dan -6,0%.

---

## 3. Evaluasi Kualitas Sinyal & Anatomi Lilin Hari Ini (16 Nov 2026)

### A. Bedah Skenario A vs Skenario B pada Saham Tertekan (Hukum `DIP5_WICK`)

Sesuai rumus baku pada `GEMINI.md` Seksi 3.2:
- **Skenario A ($\text{Lower Wick} \ge 1,0\%$)**: Serapan bid sore terbukti aktif &rarr; Win rate pantulan hari berikutnya tinggi.
- **Skenario B ($\text{Lower Wick} < 0,8\%$ / *Dead Low*)**: Rawan kena guyuran lanjutan (*Day-2 Flush*) `-4,0% s/d -4,4%` di pembukaan pagi hari berikutnya &rarr; **DILARANG beli pre-closing; tunggu tangkapan flush pagi Hari ke-2**.

Data empiris per 16 November 2026:
1. `BRPT` (Close 750, Low 750, **Lower Wick 0,00%**, Volume 1,56x MA20):
   - **Kategori: Skenario B (Dead Low / ARB Lock)**.
   - Meskipun secara historis berperingkat Grade A+ karena likuiditas Tier S, ketiadaan ekor bawah menandakan tekanan jual masih belum terserap. Potensi *flush* pagi 17 Nov ke area 720-730 sangat besar.
2. `ENRG` (Close 630, Low 625, **Lower Wick 0,80%**, Volume 0,54x MA20):
   - **Kategori: Skenario B (Volume Kering & Wick Minim)**.
   - Tekanan belum selesai, pantulan berisiko rapuh.
3. `DEWA` (Close 244, Low 244, **Lower Wick 0,00%**, Volume 1,03x MA20):
   - **Kategori: Skenario B Klasik (Dead Low 244)**.
   - Ambang 2-day return -5,43% terpicu (Peringatan Dini). Disiplin tunda entri; tunggu tangkap *flush* pagi 17 Nov saat bandar membuang sisa barang di pembukaan.
4. `RAJA` (Close 494, Low 494, **Lower Wick 0,00%**, Volume 0,68x MA20):
   - **Kategori: Skenario B (Dead Low 494)**.
   - Ret2D -7,66%. Wajib tunggu pantulan Hari ke-2.
5. `PTRO` (Close 2.400, Low 2.370, **Lower Wick 1,27%**, Volume 1,82x MA20):
   - **Kategori: Skenario A (Ada Serapan Bid Sore)**.
   - Ekor bawah terbentuk di atas Low 2.370 dengan volume meledak 1,82x. Kandidat pantulan paling cepat di sektor konstruksi/energi.
6. `BUMI` (Close 131, Low 129, **Lower Wick 1,55%**, Volume 1,21x MA20):
   - **Kategori: Skenario A (Ekor Bawah Solid)**.
   - Serapan bid di area 129-130 sangat tebal. Berpotensi memantul cepat kembali ke 134-136.

---

## 4. Hasil Pemindaian Radar BSJP (Beli Sore Jual Pagi 17 Nov)

Hasil scanner `trade:scan-bsjp --stage=confirm` mendeteksi 6 kandidat dengan peringkat kualitas:

1. **`AUTO` (Astra Otoparts)** — 🎯 **Sweetspot Likuid (Grade A+ | Skor 88)**:
   - Harga: **Rp 3.240 (+4,18%)** | Nilai Trx: **Rp 8,05 Miliar** | Volume Spike: **1,9x MA20**
   - Target TP Pagi (17 Nov): **Rp 3.320 (+2,5%)** | Hard SL: **Rp 3.140 (-3,0%)**
   - Rekomendasi: **Pilihan #1 Likuiditas & Kualitas Institusi**.
2. **`BKDP` (Bukit Darmo Property)** — 🎯 **Sweetspot Likuid (Grade A | Skor 74)**:
   - Harga: **Rp 159 (+8,90%)** | Nilai Trx: **Rp 4,30 Miliar** | Volume Spike: **7,4x MA20**
   - Target TP Pagi: **Rp 163 (+2,5%)** | Hard SL: **Rp 154 (-3,0%)**
3. **`FAST` (Fast Food Indonesia)** — 🎯 **Sweetspot Likuid (Grade A | Skor 74)**:
   - Harga: **Rp 334 (+7,05%)** | Nilai Trx: **Rp 4,14 Miliar** | Volume Spike: **6,8x MA20**
   - Target TP Pagi: **Rp 342 (+2,5%)** | Hard SL: **Rp 324 (-3,0%)**
4. **`COIN` (Indokripto Koin)** — 🚀 **Super Rocket (Grade B | Skor 60)**:
   - Harga: **Rp 472 (+19,80%)** | Nilai Trx: **Rp 160,06 Miliar** | Volume Spike: **4,1x MA20**
   - Target TP Pagi: **Rp 484 (+2,5%)** | Hard SL: **Rp 458 (-3,0%)**
   - Catatan: Potensi gap-up tinggi, pasang antrean jual di pembukaan 09:00 WIB.
5. **`KOTA` (DMS Propertindo)** — 🚀 **Super Rocket (Grade B | Skor 60)**:
   - Harga: **Rp 69 (+23,21%)** | Nilai Trx: **Rp 167,86 Miliar** | Volume Spike: **3,7x MA20**
   - Target TP Pagi: **Rp 71 (+2,5%)** | Hard SL: **Rp 67 (-3,0%)**

---

## 5. Rencana Aksi & Protokol Trading Selasa, 17 November 2026

1. **Pukul 08:52 WIB (Morning Reminder & Pasang Antrean TP BSJP)**:
   - Pasang order jual di `Rp 3.320` (`AUTO`), `Rp 163` (`BKDP`), atau `Rp 484` (`COIN`) untuk mengeksekusi target cuan pembukaan bursa (+2,5%).
2. **Pukul 09:05 – 09:30 WIB (Skenario B Day-2 Flush Catching)**:
   - Amati `DEWA`, `RAJA`, dan `BRPT`. Jika terjadi *morning panic flush* (-3% s/d -4% dari open), tunggu pembentukan pantulan pertama (*micro-hammer*) untuk entri rebound berprobabilitas tinggi.
3. **Manajemen Posisi Terbuka (`BRPT` @ 750 & `ENRG` @ 630)**:
   - Pasang proteksi ketat: Hard Stop Loss di `Rp 723,75` (`BRPT`) dan `Rp 607,95` (`ENRG`).
   - Aktifkan Trailing Stop 2,0% begitu harga mencetak kenaikan intraday.

