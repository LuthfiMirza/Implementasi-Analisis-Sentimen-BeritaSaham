# Analisis Net-of-Cost Joint TP-SL — BUMI & DEWA

Pertanyaan ekonomi: apakah edge gross ~+0.79% bertahan setelah biaya transaksi realistis?
**Fokus 100% pada expectancy NET dalam persen. Nominal modal tidak dilibatkan.**

---

## 1. Di mana cost dikonsumsi + kondisi pipeline (dilaporkan sebelum percaya angka)

- File: `quant/trading_research/sl_optimizer.py`
- Formula (baris 74–85):
  - `_cost_pct(cost_model) = entry_fee_pct + exit_fee_pct + exit_tax_pct + entry_slippage_pct + exit_slippage_pct`
  - `net_realized_return_pct = gross_realized_return_pct − _cost_pct(cost_model)` → **pengurangan konstan flat per-episode.**
- **Temuan pipeline (penting):**
  1. `build_sl_optimizer_artifact` **meng-hardcode** `cost_model = {semua 0.0}` (baris 207). Warning `"execution costs disabled"` memang dipancarkan.
  2. `joint_metrics` & `standalone_metrics` (baris 104, 120) memanggil `simulate_episode` **tanpa** meneruskan `cost_model` → seluruh `joint_tp_sl_matrix` selalu GROSS, apa pun isinya.
  3. `main()`/CLI (baris 238) **tidak punya argumen** untuk cost. → **Jalur resmi saat ini tidak bisa menyuntik biaya tanpa mengubah file produksi.**
- Konsekuensi metodologis: karena biaya adalah offset konstan, `mean(net_i) = mean(gross_i) − C`, jadi **`net_expectancy = gross_expectancy − C` secara EKSAK**. Saya memakai formula pipeline yang sama, bukan formula alternatif.
- **VALIDASI numerik** (bukan klaim kosong): memanggil `simulate_episode` pipeline dengan `cost_model` MID nonzero vs `gross − C` pada tiap episode pair terbaik → **max abs error = 0.0000000000** (BUMI & DEWA). Bukti derivasi = perilaku produksi.

## Mapping cost yang dipakai (→ key pipeline)

| skenario | entry_fee | exit_fee | exit_tax | entry_slip | exit_slip | **C = round-trip** |
|---|---|---|---|---|---|---|
| LOW  | 0.10 | 0.20 | 0.00 | 0.10 | 0.10 | **0.50%** |
| MID  | 0.15 | 0.25 | 0.00 | 0.20 | 0.20 | **0.80%** |
| HIGH | 0.19 | 0.29 | 0.00 | 0.30 | 0.30 | **1.08%** |

Catatan mapping: pajak jual final IDX (~0.1%) dilipat ke `exit_fee` sesuai brief; `exit_tax_pct=0` supaya tidak dobel. Angka = skenario, belum diverifikasi ke broker spesifik.
Formula net yang dipakai: **`net_exp(pair) = gross_exp(pair) − C`**, `gross_exp` diambil dari `joint_tp_sl_matrix[].expectancy_pct` di artifact `*_sl_optimizer_v1_1.json`.

---

## 2. Tabel net per skenario (dari 96 joint pair)

### BUMI (best/max-expectancy pair: tp=30, SL fixed 7.5%)
| skenario | round-trip % | #pair net-pos | best_net exp % | survive? |
|---|---|---|---|---|
| GROSS | 0.00 | 85/96 | +1.7197 | (baseline) |
| LOW   | 0.50 | 68/96 | +1.2197 | ya |
| MID   | 0.80 | 53/96 | +0.9197 | ya (tapi lihat §3) |
| HIGH  | 1.08 | 38/96 | +0.6397 | ya (tapi lihat §3) |

### DEWA (best/max-expectancy pair: tp=10, SL ATR×1.5)
| skenario | round-trip % | #pair net-pos | best_net exp % | survive? |
|---|---|---|---|---|
| GROSS | 0.00 | 96/96 | +0.7902 | (baseline) |
| LOW   | 0.50 | 25/96 | +0.2902 | ya |
| MID   | 0.80 | **0/96** | **−0.0098** | **TIDAK** |
| HIGH  | 1.08 | 0/96 | −0.2898 | TIDAK |

`best_net` = expectancy tertinggi lintas 96 pair (ranking tak berubah oleh offset konstan, jadi best_net_pair = best_gross_pair). Semua angka = gross_exp − C.

---

## 3. Uji ketahanan extreme-winner PADA net (buang top-5% winner, lalu recompute mean)

Re-simulasi per-episode ke-96 pair (pipeline `simulate_episode`), net = gross − C, di skenario MID:

| ticker | #pair net-pos @ MID | #pair net-pos **DAN** robust (excl top-5% > 0) |
|---|---|---|
| BUMI | 53/96 | **0/96** |
| DEWA | 0/96 | **0/96** |

- **BUMI:** tiap pair yang net-positif di MID menjadi **NEGATIF** begitu top-5% winner dibuang. Contoh best pair (tp=30/SL7.5): net_full +0.92 → excl-top5% **−0.88**. Pair TP moderat (tp=12.5) pun: net_full +0.36 → excl-top5% −0.32. **Seluruh net-positif = artefak fat-tail.**
- **DEWA:** tidak ada pair net-positif di MID sejak awal; best pair net −0.01 (full) → −0.73 (excl top-5%). Konsisten dengan warning `extreme_winner_dependency` yang sudah ada di artifact gross.

---

## 4. Break-even round-trip cost

- **BUMI:** 1.7197% (best/max-expectancy pair). Break-even pair "terpilih-by-score" (gross +0.792) = 0.792%.
- **DEWA:** 0.7902% (best pair).

Bandingkan skenario: MID (0.80%) sudah **melampaui** break-even DEWA (0.79%) → DEWA nol/negatif di MID. BUMI max-expectancy pair break-even 1.72% (di atas HIGH), tapi itu pair lottery tp=30 (hit-rate 0.166) yang survival-nya semu (lihat §3).

---

## VONIS AKHIR (fakta)

- **BUMI → [DEAD].** Net-positif memang ada sampai HIGH pada level expectancy (best +0.92 @ MID, 53/96 pair positif), TAPI **0/96 pair bertahan positif tanpa top-5% winner** di MID. Sesuai definisi brief: "yang positif hanya bertahan lewat extreme-winner → tidak ada edge tradeable." Edge = artefak fat-tail, bukan edge yang bisa ditradingkan berulang.

- **DEWA → [DEAD].** **0/96 pair net-positif di MID** (best net −0.0098). Break-even 0.79% < biaya MID 0.80%. Excl-top5% makin dalam negatif. Tidak ada edge tradeable.

### Ringkas
| | GROSS best | MID best_net | #net-pos @ MID | #robust @ MID | break-even | vonis |
|---|---|---|---|---|---|---|
| BUMI | +1.72 | +0.92 | 53/96 | **0/96** | 1.72% | **[DEAD]** (fat-tail) |
| DEWA | +0.79 | −0.01 | **0/96** | 0/96 | 0.79% | **[DEAD]** |

Edge gross +0.79% **tidak bertahan** sebagai edge tradeable pada biaya realistis: DEWA lenyap secara expectancy di MID; BUMI hanya "positif" karena 5% trade ekstrem.

---

## Validasi
- `git status --short storage/` = **bersih** (tidak ada artifact produksi berubah/ditimpa; baseline gross utuh).
- Artifact baru hanya di `output/trading_research/reports/` (untracked): `net_cost_analysis.py`, `net_robustness_scan.py`, `BUMI_DEWA_net_cost_verdict.md`.
- Usability gate TIDAK dilonggarkan; `selected` tetap null di artifact asli (tidak disentuh). Analisis ini mengukur, tidak memaksa lolos.
- `python3 -m pytest quant -q` = **312 passed**.
- `php artisan test` = (lihat hasil di chat).
- Linearitas net=gross−C tervalidasi ke perilaku pipeline (max abs err 0.0).
