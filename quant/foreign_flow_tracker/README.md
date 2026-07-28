# Foreign flow snapshot collector

## Kenapa ini ada

User meminta dicari sumber data aliran beli/jual investor asing (net foreign buy/sell), termasuk
kemungkinan live. Sudah dicek berulang di sesi ini bahwa jalur resmi (endpoint broker `idx.co.id`)
dan jalur berbayar (`sectors.app` Bandarmology) tidak bisa diakses gratis.

Satu sumber ditemukan yang benar-benar bisa diambil lewat HTTP biasa tanpa Cloudflare:
`infovesta.com/index/data_info/saham/{topbuy,topsell}` — HTML statis, bukan JS-rendered, berisi
kode saham + volume beli + volume jual + net (lembar) untuk 5 saham dengan net-buy/net-sell
terbesar hari itu.

## Batasan yang WAJIB dipahami sebelum memakai data ini

1. **Live-only, tidak ada riwayat.** Parameter `?date=` di URL diuji dan **diabaikan sepenuhnya**
   — situs selalu mengembalikan snapshot hari ini berapa pun tanggal yang diminta. Tidak ada cara
   mengambil data masa lalu dari sumber ini.
2. **Cuma top-5, bukan semua saham.** Hanya 5 saham dengan net-buy terbesar dan 5 dengan net-sell
   terbesar (dalam satuan lembar, bukan rupiah) yang ditampilkan. Saham blue-chip besar seperti
   BBCA/BBRI/BMRI kemungkinan JARANG muncul di daftar ini — top mover volume lembar biasanya saham
   harga rendah.

### Konsekuensi metodologis

**Data ini TIDAK BISA divalidasi dengan walk-forward** seperti seluruh eksperimen lain di proyek
ini (Fase S/T/W) — karena tidak ada riwayat untuk diuji. Memasukkannya langsung sebagai fitur
model tanpa validasi akan mengulang kesalahan `buying_pressure` lama (diklaim membantu tanpa
pernah diuji out-of-sample, ternyata menurunkan akurasi).

**Yang dibangun di sini bukan fitur model, tapi pengumpul.** `collect_snapshot.py` menyimpan
snapshot hari ini ke `snapshots.jsonl` (append-only) setiap kali dijalankan. Setelah terkumpul
beberapa bulan, baru bisa dicek apakah saham yang muncul di top-5 net-buy punya pola return
berbeda dari yang tidak — itu pun cuma untuk saham-saham yang KEBETULAN muncul di daftar, bukan
untuk 10 saham resmi proyek secara sistematis.

## Cara pakai

```bash
python3 quant/foreign_flow_tracker/collect_snapshot.py
```

Jalankan tiap hari bursa (bisa ditambah ke jadwal manual, TIDAK didaftarkan otomatis ke
`routes/console.php` karena statusnya masih eksploratif, bukan bagian pipeline produksi).

Setelah beberapa bulan data terkumpul, jalankan:

```bash
python3 quant/foreign_flow_tracker/analyze.py
```

untuk cek apakah saham yang masuk top-5 net-buy hari T menunjukkan return berbeda di T+5/T+10
dibanding baseline pasar pada rentang waktu yang sama — dengan catatan sampelnya kemungkinan besar
kecil (cuma tanggal + saham yang kebetulan tertangkap), jadi kesimpulannya wajib dilaporkan
sebagai eksploratif, bukan final.
