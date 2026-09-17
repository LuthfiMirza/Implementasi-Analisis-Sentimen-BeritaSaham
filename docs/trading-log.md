
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
