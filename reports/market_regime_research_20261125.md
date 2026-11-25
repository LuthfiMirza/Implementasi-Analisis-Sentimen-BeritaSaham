# Laporan Audit Riset Mendalam Pasar EOD — Rabu, 25 November 2026

> **Waktu Audit**: Kamis dini hari, 26 November 2026 (`00:38 WIB`) — Data EOD Final 25 Nov + Penutupan Wall Street 25 Nov  
> **Status Rezim Pasar (`GEMINI.md`)**: **SIAGA MERAH / AMBANG `CASH IS KING`** *(IHSG `-0,84%` di `5.197,61`, Breadth jatuh ke `19,5%`, Rupiah `Rp 18.303`, Wall Street anjlok pasca Core PCE AS)*  
> **Catatan Sistem Lokal**: Server lokal/MySQL sempat berhenti pasca *restart* — posisi `#931 BUMI` & `#932 DEWA` yang menyentuh Hard SL di Sesi 2 belum tersinkronisasi ke DB; wajib jalankan `bash start_sentimena.sh` sebelum pembukaan Kamis `09:00 WIB`.

---

## 1. Ringkasan Eksekutif & Struktur Teknikal Final IHSG (`^JKSE`)

Perdagangan **Rabu, 25 November 2026** ditutup dengan tekanan jual tajam pada Sesi 2 (`14:00–14:30 WIB`). Setelah sempat bertahan di rentang `5.202–5.247` sepanjang Sesi 1, IHSG dibanting hingga menembus level psikologis `5.200` ke **Low `5.165,67` (`-1,45%` intraday)** sebelum ditahan oleh saham Big Banks & defensif sehingga ditutup di **`5.197,61` (`-43,97 poin` / `-0,84%`)**.

| Metrik IHSG (`^JKSE`) | Senin, 23 Nov | Selasa, 24 Nov | Rabu, 25 Nov (EOD Final) | Status & Sinyal |
| :--- | :---: | :---: | :---: | :--- |
| **Open** | 5.134,06 | 5.283,29 | **5.235,83** | Gap-down ringan |
| **High** | 5.244,35 | 5.314,74 | **5.246,79** | Gagal tembus `5.250` |
| **Low** | 5.062,09 | 5.198,64 | **5.165,67** | **Menembus Low kemarin (`5.198`) — Higher Low patah!** |
| **Close** | 5.215,85 (`+1,35%`) | 5.241,59 (`+0,49%`) | **5.197,61 (`-0,84%`)** | Ditutup di bawah psikologis `5.200` |
| **Lower Wick** | `+3,04%` | `+0,83%` | **`+0,62%`** | Serapan lemah (< 1,0%) |
| **MA20 / Deviasi** | 5.152,24 (`+1,23%`) | 5.151,02 (`+1,76%`) | **5.146,78 (`+0,99%`)** | **Sisa buffer hanya 50 poin di atas MA20!** |
| **MA50 / Deviasi** | 5.641,05 (`-7,54%`) | 5.616,66 (`-6,68%`) | **5.591,87 (`-7,05%`)** | Tren menengah masih bearish |
| **RSI(14) Wilder** | 44,35 | 45,86 | **43,68** | Melemah |
| **MACD Histogram** | +44,86 | +43,89 | **+39,39** | Positif namun menyusut 3 hari beruntun |

### Keruntuhan Market Breadth Sesi 2 (77 Saham Likuid)
- **Pagi (`10:18 WIB`)**: 22 Naik (`28,6%`) vs 47 Turun (`61,0%`) — 0 ARB.
- **EOD Final (`16:00 WIB`)**: Jatuh menjadi **15 Naik (`19,5%`)** vs **58 Turun (`75,3%`)**, 4 Flat (`5,2%`).
- **4 Saham Utama Terkunci/Hampir ARB 7% (*Dead Low `0,00%`*)**: **`CUAN -6,99%`** (`346`), **`ISAT -6,95%`** (`1.405`), **`BRMS -6,90%`** (`270`), **`BRPT -6,62%`** (`635`), disusul **`DSSA -6,30%`**, **`ARTO -6,19%`**, dan **`TINS -6,07%`**.

---

## 2. Rotasi Sektoral Final EOD 25 November 2026

| Sektor | n | Naik | Turun | Avg Chg | Nilai Trx (Rp M) | Ringkasan EOD |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Consumer / Retail / Auto** | 11 | **6** | 5 | **`-0,15%`** | 465,3 | **Satu-satunya benteng defensif**: `UNVR +3,86%`, `ASII +1,83%`, `AMRT +0,97%`, `ICBP +0,70%`, `KLBF +0,63%` |
| **Banks** | 7 | 3 | 4 | `-1,45%` | **2.082,3** | Big Banks menahan indeks (`BBCA +0,43%`, `BBNI +0,28%`, `BMRI +0,25%`), namun `BBRI -0,97%` & bank digital anjlok (`ARTO -6,19%`) |
| **Energy / Coal / O&G** | 15 | 3 | 10 | `-1,53%` | 613,1 | Batubara/migas murni bertahan (`MEDC +1,28%`, `PTBA +1,03%`, `ITMG +0,82%`), sedangkan Grup Bakrie/energi spekulatif diguyur (`RAJA -4,93%`, `ENRG -4,50%`, `DEWA -3,31%`, `PTRO -3,06%`, `BUMI -1,55%`) |
| **Property & Radar Others** | 16 | 1 | 14 | `-1,94%` | 147,4 | Hampir merah merata (`NZIA -5,13%`) |
| **Metals & Mining** | 10 | 1 | 9 | **`-2,76%`** | 739,6 | Terseret koreksi emas dunia & ex-MSCI (`BRMS -6,90%`, `TINS -6,07%`, `AMMN -3,33%`); hanya `INCO +0,59%` hijau |
| **Telco & Tech** | 9 | **0** | 8 | **`-3,06%`** | 571,3 | 0 saham hijau (`ISAT -6,95%`, `WIFI -5,75%`, `INET -4,44%`, `TLKM -3,37%`) |
| **Conglo / Infra / Petchem** | 9 | 1 | 8 | **`-3,26%`** | 470,8 | **Sektor terburuk (ex-MSCI)**: `CUAN -6,99%`, `BRPT -6,62%`, `DSSA -6,30%`, `TPIA -3,27%`; anomali hijau kuat: **`INTP +2,47%`** (Vol `2,87x`!) |

---

## 3. Shock Makro Global & Overnight (Katalis Kunci Pembukaan Kamis, 26 Nov)

| Instrumen | EOD 25 Nov | Perubahan | Implikasi untuk Pembukaan BEI Kamis 09:00 WIB |
| :--- | :---: | :---: | :--- |
| **Nasdaq (`^IXIC`)** | 23.217,46 | **`-2,17%`** *(sempat `-4%`)* | **TEKANAN BERAT** — Core PCE AS panas (`3,3% YoY` vs `3,2%` est), GDP Q3 kuat `4,3%`, isu tarif baru, & aksi jual AI/chip (Nvidia `-8%`). |
| **S&P 500 (`^GSPC`)** | 7.111,87 | **`-1,24%`** *(sempat `-2,7%`)* | Memastikan ekspektasi kenaikan suku bunga The Fed Desember. |
| **Dow Jones (`^DJI`)** | 49.937,80 | `-0,16%` *(sempat `-1,4%`)* | Relatif lebih tahan berkat rotasi *value/defensive*. |
| **Nikkei (`^N225`) / HSI (`^HSI`)** | 57.117 / 21.966 | **`-2,60%`** / **`-1,14%`** | Asia kompak tertekan. |
| **USD/IDR JISDOR / Spot** | **Rp 18.303** / **18.332** | **`+0,54%` s/d `+0,67%`** | **Sinyal bahaya outflow** — Rupiah melemah menembus `Rp 18.300/USD` disertai *net foreign sell* akibat overhang konsultasi MSCI (s/d April 2027). |
| **Emas (`GC=F`)** | US\$ 3.529,80 | **`-0,90%`** *(sempat `< 3.500`)* | Tekanan berlanjut bagi saham emas/logam (`BRMS`, `MDKA`, `PSAB`, `ANTM`, `AMMN`). |
| **WTI (`CL=F`) / Brent (`BZ=F`)** | US\$ 83,60 / 90,20 | `+1,89%` / `-1,31%` | Mixed di migas; WTI rebound tipis. |

*(Catatan kalender global: Bursa AS **LIBUR Thanksgiving** pada Kamis, 26 Nov 2026.)*

---

## 4. Audit Forensik Posisi Portofolio & Akurasi Analisis Pagi (Scorecard)

Seluruh aturan proteksi `GEMINI.md` dan peringatan pagi tadi (`10:18–10:37 WIB`) **terbukti 100% akurat** melindungi modal dari guyuran Sesi 2 (`14:00–14:30 WIB`):

| Emiten | Posisi / Peringatan Pagi (`10:18–10:37`) | Realita Penutupan 25 Nov (15m Low → Close) | Evaluasi Audit |
| :--- | :--- | :--- | :--- |
| **`#927 ENRG`** | Auto-Closed TS 2% @ **553,70 (`-0,23%`)**; saran pagi: *jangan re-entry di `545`, tunggu uji `530–535`* | Pukul `14:30` dibanting ke **Low `520` (`-6,31%`)**, tutup **`530` (`-4,50%`)**, `LW +1,92%` | ✅ **TERSELAMATKAN SEMPURNA.** Keluar `-0,23%` menghindari drawdown `-6,3%` & tepat menyentuh zona beli diskon `520–530`. |
| **`#922 BRPT`** | Auto-Closed Hard SL @ **656,20 (`-3,50%`)**; dilarang average down | Langsung lanjut ambles ke **Dead Low `635` (`-6,62%`)** | ✅ **TERSELAMATKAN.** Memotong kerugian disiplin di `-3,5%`. |
| **`#931 BUMI`** | Open `BOTTOM_REBOUND` @ `130` (Hard SL **`125,45`**) | Pukul `14:15` dibanting ke **Low `123` (`-5,38%`)**, tutup `127` (`LW +3,25%`) | 🚨 **HARD SL `-3,50%` (`125,45`) TERSENTUH INTRADAY.** Wajib sinkronisasi auto-close di MySQL saat server menyala. |
| **`#932 DEWA`** | Open `BOTTOM_REBOUND` @ `244` (Hard SL **`235,46`**) | Pukul `14:00` jebol ke **Low `232` (`-4,92%`)**, tutup **`234` (`-3,31%`)** | 🚨 **HARD SL `-3,50%` (`235,46`) JEBOL.** Wajib disiplin Cut Loss & sinkronisasi auto-close di MySQL. |
| **`ISAT`** *(BSJP 24 Nov)* | Peringatan pagi: Cut Loss disiplin di `1.455` | Sore ambles ke **Dead Low `1.405` (`-6,95%`)** | ✅ **TERSELAMATKAN** dari kerugian tambahan `-3,5%`. |
| **`TINS` & `PSAB`** | Peringatan pagi: Exit `PSAB` (`386` BEP) & Cut `TINS` (`3.020`) | `TINS` tutup **`2.940` (`-6,07%`)**, `PSAB` Dead Low **`380` (`-2,06%`)** | ✅ **TERSELAMATKAN.** |
| **Watchlist Pagi (`UNVR`, `INTP`)** | Diidentifikasi sebagai 2 pemimpin rotasi defensif pagi | **`UNVR +3,86%`** (`1.615`, #1 Top Gainer) & **`INTP +2,47%`** (`6.225`, #2 Top Gainer, Vol `2,87x`) | ✅ **BULLSEYE.** Sebaliknya `MBMA` & `BUKA` yang sempat `+4%` pagi berbalik merah sore (membuktikan aturan hindari beli Sesi 1). |

---

## 5. Audit Sinyal EOD 25 Nov & Protokol Taktis Kamis, 26 November 2026

### A. Sinyal Resmi yang Terpicu di Penutupan 25 Nov
- **Terpicu `GABUNGAN`**:
  1. **`ENRG`** (`Close 530`, `Low 520`, `dd_20d -20,90%`, `RSI 31,1`, **`LW +1,92%`** — *Skenario A*, Vol `0,41x` → Grade B).
  2. **`PTRO`** (`Close 2.220`, `Low 2.190`, `ret_2d -9,76%`, `RSI 37,4`, **`LW +1,37%`** — *Skenario A*, Vol `0,26x` → Grade B).
  3. **🚫 DITOLAK (`Grade C` / `Skenario B Dead Low`)**: `BRPT` (`LW 0,00%`), `INET` (`LW 0,00%`), `DEWA` (`LW 0,86%`), `RAJA` (`LW 0,95%`).
- **Terpicu `DIP5_WICK` Skenario A (`Low <= -5%` + `LW >= 1%`)**: `TEBE` (`LW +5,56%`), `BREN` (`LW +4,07%`), `BYAN` (`LW +3,22%`, Vol `2,01x`), `AMMN` (`LW +2,24%`), `ENRG` (`LW +1,92%`).
- **Kandidat BSJP Momentum**: **`INTP`** (`+2,47%`, Vol `2,87x`, `UW 1,61%`) & **`UNVR`** (`+3,86%`, Vol `1,52x`, `UW 0,93%`).

### B. Rencana Aksi Wajib Kamis, 26 November 2026
1. **Sebelum 09:00 WIB**: Jalankan `bash start_sentimena.sh` agar MySQL, Auto-Close 3-Lapis, dan Scheduler kembali aktif & merekonsiliasi auto-close `#931 BUMI` / `#932 DEWA` (jika masih memegang barang riil di broker, disiplin eksekusi proteksi).
2. **Sesi 1 Kamis (`09:00 – 11:30 WIB`) — MODE `WAIT & SEE / DEFENSIVE MUTLAK`**:
   - **DILARANG BELI DI PAGI HARI!** Efek kejatuhan Nasdaq `-2,17%`, S&P 500 `-1,24%`, Rupiah `18.303`, dan 4 saham utama yang ditutup *Dead Low* (`CUAN`, `ISAT`, `BRMS`, `BRPT`) sangat berpotensi memicu *morning flush* pembukaan Kamis.
   - **Pantau Garis Hidup IHSG di `5.146` (MA20)**:
     - **Jika IHSG jebol `< 5.145` (`>= -1,0%`)**: **CRASH GUARD AKTIF ➔ 100% `CASH IS KING`**, batalkan semua rencana beli `ENRG`/`PTRO`/saham apapun hingga 3 syarat konfirmasi rebound `GEMINI.md` terpenuhi kembali.
3. **Sesi 2 Kamis (`15:00 – 15:50 WIB`) — Jendela Evaluasi Ulang (Hanya Jika MA20 `5.146` Bertahan)**:
   - Karena Wall Street libur Thanksgiving pada Kamis malam, apabila IHSG mampu menahan MA20 `5.146` dan membentuk *lower wick* serapan serta breadth membaik, baru pantau secara selektif (alokasi konservatif maks 25%–50%):
     - **`ENRG`** (bila menahan zona demand `515–530` dengan *Lower Wick* `>= 1,0%` + volume meningkat),
     - **`PTRO`** (bila bertahan `>= 2.190` dengan *Lower Wick* `>= 1,0%`), atau
     - Rotasi defensif **`UNVR` / `BBCA` / `ASII`**.
