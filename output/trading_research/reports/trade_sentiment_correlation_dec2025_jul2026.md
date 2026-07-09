# Sentimen vs Hasil Trade — BUMI & DEWA (Des 2025–Jul 2026)

**Tujuan:** bahan diskusi dengan dosen pembimbing — menempelkan skor sentimen berita
harian ke tiap entri trade journal (`/trades`), untuk melihat apakah entry yang
berbarengan dengan sentimen negatif memang lebih sering berakhir stop-loss.

**Cara menjalankan ulang:** `php artisan trades:analyze-sentiment --user=2 --window=7`
(lihat `app/Console/Commands/AnalyzeTradeSentimentCommand.php`). Window = jumlah hari
ke belakang dari `entry_date` yang diratakan skor sentimennya.

## Metodologi

Untuk tiap trade di journal, dihitung rata-rata `sentiment_score` (skala -1..+1) semua
artikel BUMI/DEWA yang terbit di window N hari sebelum tanggal entry. Dibandingkan
rata-rata itu antara trade yang berakhir menang (TP) vs kalah (SL). Ini **analisis
deskriptif untuk bahan diskusi**, bukan uji hipotesis formal — jumlah trade terlalu
kecil (15) untuk signifikansi statistik.

## Hasil (per 2026-07-09, journal berisi 15 trade)

| Window | Avg sentimen (trade menang) | Avg sentimen (trade kalah) | Selisih (menang−kalah) |
|---|---|---|---|
| 5 hari | 0.006 | 0.325 | **−0.319** |
| 7 hari | 0.136 | 0.244 | **−0.108** |

Trade menang (TP): 8 (5 di antaranya ada data berita di window). Trade kalah (SL): 5
(4 di antaranya ada data berita).

## Interpretasi jujur

**Tidak ditemukan pola yang mendukung hipotesis "sentimen negatif mendahului
kerugian"** — arahnya malah terbalik di kedua window: trade yang berakhir stop-loss
justru rata-rata punya sentimen *lebih positif* sebelum entry dibanding trade yang
menang. Ini konsisten di dua ukuran window (5 & 7 hari), jadi bukan kebetulan pilihan
parameter satu window saja.

**Kemungkinan penyebab (bukan kesimpulan final):**
1. **Coverage berita sangat rendah** — 4-5 dari 15 trade (~30%) tidak punya satu pun
   artikel di window sebelum entry. Rata-rata dari sampel sekecil ini gampang goyah.
2. **Kualitas sentimen ML sudah terbukti lemah** (lihat audit Gap 2 sebelumnya:
   agreement ML vs label manusia cuma 35,6%, di bawah tebak-acak). Kalau skor
   sentimennya sendiri kurang akurat, wajar kalau tidak berkorelasi jelas dengan
   pergerakan harga.
3. **Trade ini masuk berdasar sinyal TP/SL teknikal murni**, bukan sinyal sentimen —
   jadi tidak ada mekanisme yang membuat entry "seharusnya" berkorelasi dengan
   sentimen di tempat pertama. Untuk menguji hipotesis sentimen dengan benar,
   idealnya entry-nya sendiri dipicu oleh sinyal sentimen (bukan ditempel belakangan).

**Ini bukan hasil negatif yang perlu ditutupi** — justru konsisten dan memperkuat
narasi yang sudah dibangun di BAB IV: coverage sentimen BUMI/DEWA rendah dan kualitas
skor ML terbatas, sehingga sentimen belum bisa diandalkan sebagai sinyal tunggal untuk
BUMI/DEWA pada kondisi data saat ini. Layak didiskusikan dengan dosen sebagai arah
lanjutan: apakah perlu redesign supaya entry trade betul-betul dipicu sinyal sentimen
(bukan cuma ditempel post-hoc), dan apakah coverage berita perlu diperluas dulu
sebelum uji ulang.
