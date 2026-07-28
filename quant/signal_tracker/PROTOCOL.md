# Protokol evaluasi prospektif: sinyal Telegram "Zeta AI"

**Ditetapkan dan di-commit SEBELUM sinyal pertama dicatat.** Aturan di bawah ini tidak boleh
diubah setelah pencatatan dimulai. Kalau ada perubahan yang benar-benar perlu, dokumentasikan
sebagai amandemen bertanggal baru di bawah, jangan edit isi yang sudah ada.

## Kenapa protokol ini ada

Sesi audit menemukan (Fase T dan diskusi lanjutan) bahwa mengevaluasi klaim performa SETELAH
melihat hasilnya membuka banyak cara untuk menipu diri sendiri: memilih sampel yang bagus,
mengubah aturan cut-off, atau membandingkan ke baseline yang menguntungkan. Protokol ini
dirancang supaya evaluasi akhir tidak bisa diarahkan ke kesimpulan yang diinginkan.

## Filter seleksi sinyal (WAJIB dipatuhi apa adanya)

Sinyal dicatat sebagai **tracked** hanya jika keduanya benar:
- `signal_type = BUY`
- `confidence_score = 5` (skor keyakinan tertinggi yang ditampilkan sumber)

Sinyal lain yang terlihat (WATCHLIST, confidence < 5, dst.) **tetap dicatat** ke tabel yang sama
dengan `tracked = 0` dan alasan pengecualian — supaya nanti terlihat berapa banyak sinyal yang
sengaja dilewati, bukan diam-diam hilang.

## Horizon evaluasi

**30 hari kalender** sejak `signal_posted_at`. Berlaku sama untuk semua sinyal, tidak
disesuaikan per saham.

## Harga masuk yang dipakai

**`market_price_at_log`** — harga pasar yang diamati saat sinyal DICATAT, bukan harga entry
yang disebut sumber. Ini harga yang realistis bisa didapat; entry yang mereka sebut mungkin
sudah lewat saat dibaca.

## Aturan penilaian hasil (per sinyal, di hari ke-30)

Ambil harga penutupan H+30 (hari bursa terdekat jika H+30 libur):
1. Jika harga menyentuh TP1 yang disebut kapan pun sebelum H+30 → **TP_HIT**, return dicatat di
   harga TP1.
2. Jika belum, dan harga menyentuh stop loss default (ATR) kapan pun sebelum H+30 →
   **SL_HIT**, return dicatat di harga SL.
3. Jika sampai H+30 tidak menyentuh keduanya → **TIME_EXIT**, return dicatat di harga penutupan
   H+30 apa adanya (untung atau rugi, tidak dibulatkan ke salah satu sisi).

**Ketiga hasil di atas MASUK KE SEMUA PERHITUNGAN RATA-RATA.** Tidak ada sinyal yang dibuang dari
penyebut karena "belum resolved" — itu celah yang membuat Screenshot 2 (82,4% jadi 36,8%)
menyesatkan.

## Biaya transaksi

**0,80% round-trip**, sama seperti asumsi MID yang sudah dipakai riset trading BUMI/DEWA di
proyek ini. Dikurangkan dari return sebelum dilaporkan sebagai "net".

## Pembanding wajib (bukan opsional)

1. **Beli-diamkan** saham yang sama, entry di harga yang sama, dipegang 30 hari kalender penuh.
2. **IHSG** periode yang sama.

Sinyal dianggap punya nilai tambah HANYA jika rata-rata net return-nya mengalahkan KEDUA
pembanding itu, bukan cuma salah satu.

## Yang dilaporkan di akhir (semua, tidak dipilih-pilih)

- Win rate versi jujur (semua tracked signal di penyebut) DAN versi "resolved-only" ala
  Screenshot 2, berdampingan — supaya selisihnya terlihat eksplisit.
- Rata-rata & median return net biaya.
- Sebaran (bukan cuma rata-rata) — histori proyek ini menunjukkan rata-rata bisa ditutupi
  beberapa kemenangan besar.
- Delta terhadap beli-diamkan dan terhadap IHSG.
- Waktu penyelesaian TP_HIT vs SL_HIT vs TIME_EXIT (mengecek dugaan bahwa yang menang selesai
  lebih cepat daripada yang kalah).
- Jumlah sinyal yang terlihat tapi tidak masuk filter (`tracked=0`), by alasan.

## Integritas data

- Tabel `signals` di `tracker.sqlite3` bersifat **append-only** — trigger SQL memblokir
  `UPDATE`/`DELETE` di level database, bukan cuma konvensi.
- Setiap baris menyimpan `logged_at` (kapan dicatat) terpisah dari `signal_posted_at` (kapan
  sumber memposting) — kalau ada jeda signifikan, itu ikut dilaporkan (jeda besar berarti harga
  masuk kemungkinan sudah bergerak jauh dari yang disebut sumber).
- Teks/caption asli disimpan verbatim di `raw_text` sebagai bukti.

## Ambang minimum sebelum kesimpulan ditarik

Jangan simpulkan apa pun sebelum **n ≥ 20 sinyal tracked** DAN horizon 30 hari sudah lewat untuk
semuanya. Di bawah itu, laporkan sebagai "belum cukup data", bukan kesimpulan dini.

---

*Protokol ini dibuat 2026-07-25, sebelum sinyal pertama dicatat.*
