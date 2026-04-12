## Checklist QA Manual Sentimena (UI/UX)

Lakukan di browser pada resolusi desktop dan mobile (responsive), dengan data real/seed.

### Dashboard
- [ ] Sidebar watchlist muncul, status badge & sparkline tampil atau empty state muncul.
- [ ] Alert watchlist (berita negatif 24 jam) muncul jika ada lonjakan; tidak muncul jika tidak ada data negatif.
- [ ] Chart harga (internal/TradingView) tampil sesuai `STOCK_CHART_MODE`.
- [ ] Ringkasan sentimen (positif/netral/negatif) sesuai data berita; headline positif/negatif tampil atau fallback teks.
- [ ] Link ke `/analytics` dan `/news` berfungsi.

### Analytics
- [ ] Header menampilkan kode, nama, harga terakhir, perubahan %, status decision support, confidence, prediksi.
- [ ] Filter kode saham & periode (7/30/90) bekerja dan reload data.
- [ ] Chart harga-sentimen-volume tampil; bila data kosong muncul pesan “Data harga atau sentimen belum tersedia”.
- [ ] Panel metrik: average/weighted sentiment, news volume, cumulative return, volatility, same-day corr tidak error ketika nilai `N/A`.
- [ ] Panel korelasi/event study menampilkan lag H+1/H+3/H+7; empty state tidak meledak.
- [ ] Panel skenario & prediksi memuat narasi, skenario bullish/netral/bearish, disclaimer prediksi.
- [ ] Headline positif/risk menunjukkan sentiment_badge, skor, method, tanggal; empty state tampil jika kosong.

### News
- [ ] Filter code, sentiment, tanggal, sumber, method, query bekerja dan menjaga nilai terpilih.
- [ ] Badge sentimen + skor + confidence + method tampil; link artikel membuka tab baru.
- [ ] Empty state muncul jika tidak ada hasil filter.

### Watchlist
- [ ] Kartu watchlist menampilkan harga terakhir, % perubahan, status badge, sparkline; empty state jelas.
- [ ] Tombol tambah/hapus berfungsi; form cari bekerja.
- [ ] Link ke analytics per saham berfungsi.

### Prediksi & Sentimen Python
- [ ] Env `SENTIMENT_ENGINE`/`PREDICTION_ENGINE` diset sesuai skenario (rule_based/hybrid/python/baseline).
- [ ] Sentimen: jika `PYTHON_SENTIMENT_ENDPOINT` aktif, pastikan respons label valid dan method `python`; jika endpoint down, method `hybrid_fallback`.
- [ ] Prediksi: jika `PYTHON_PREDICTION_ENDPOINT` aktif, direction berasal dari Python; jika down, method `baseline_fallback`.

### Aksesibilitas & Kopy
- [ ] Teks BI konsisten; disclaimer “bukan rekomendasi investasi” muncul pada panel prediksi/skenario.
- [ ] Kontras teks/warna pada dark mode cukup; link/CTA jelas.
- [ ] Responsif: grid tidak pecah pada <768px.
