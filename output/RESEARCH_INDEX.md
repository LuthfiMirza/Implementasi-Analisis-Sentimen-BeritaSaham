# Indeks Artefak Riset (`output/`)

Folder ini berisi 700+ file dari proses riset kuantitatif skripsi (eksperimen, audit, backtest, keputusan go/no-go). **Mayoritas adalah jejak audit granular otomatis** (tiap gate keputusan menulis file JSON+TXT-nya sendiri) — jangan coba baca semua, mulai dari sini.

## Kalau cuma boleh baca 1 file: `project_current_state_summary.txt`

Ringkasan status resmi terkini seluruh proyek riset kuantitatif (baseline aktif, status Phase A/B, kandidat mana yang boleh/tidak boleh dipromosikan).

## Peta Temuan Final (per topik)

| Topik | Baca file ini | Kesimpulan singkat |
|---|---|---|
| Status proyek keseluruhan | `project_current_state_summary.txt` | Framework 10-ticker resmi *frozen*, next action = perluasan data dulu |
| Kenapa Phase B ditutup tanpa promosi | `phase_b_postmortem.txt` | Semua item (5-8) no_go — sinyal usability, bukan bug |
| Model prediksi 10 ticker resmi (V6A/V6B) | `prediction_research/model_comparison.txt` | V6A dir_acc ~40.5%, V6B (+sentimen) naik tipis 1-2% |
| Model BUMI/DEWA khusus | `prediction_research/model_comparison_volatile_special_summary.txt` | BUMI RF ~42%, DEWA GB ~50.5% (sudah dipromosikan ke produksi) |
| Strategi TP/SL BUMI/DEWA | `trading_research/reports/BUMI_DEWA_net_cost_verdict.md` | **[DEAD]** — net-of-cost tidak profitable, cuma fat-tail artifact |
| Eksperimen trading lanjutan (regime/hold-lama) | `trading_research/reports/BUMI_DEWA_v3_regime_longer_hold_experiment.md` | 1 kandidat experimental (belum boleh dipromosikan), sisanya kalah vs naive buy-hold |
| Eksperimen fitur/model BUMI v3 (2026-07-07) | `prediction_research/bumi_v3_fair_subset_verification.txt` | Tidak ada improvement robust; sentimen coverage cuma ~2% |
| Coverage sentimen & rencana perbaikan (2026-07-07) | *(lihat memory Claude, bukan file — `project-gap-remediation-plan.md`)* | Coverage 0.22%, tie-break sentimen ML→rule-based sudah diperbaiki, 801 artikel divalidasi manual |

## Peta Direktori

| Folder | Isi | Jumlah file |
|---|---|---|
| `output/` (root) | Jejak audit granular per-fase (baseline_v2..v9, phase_a, phase_b item1-8, governance gates, holdout checks) — **arsip eksperimen, sebagian besar superseded**, JANGAN dianggap kesimpulan final tanpa cek `project_current_state_summary.txt` dulu | ~608 |
| `prediction_research/` | Dataset training (`dataset.csv`, `dataset_bumi_special.csv`, dst), model comparison reports (V6A/V6B/BUMI/DEWA) | 78 |
| `trading_research/` | Laporan backtest TP/SL, net-of-cost verdict, eksperimen regime/hold-lama | 11 |
| `single_variable_experiment_runs{,_v2,_v3}/` | Eksperimen isolasi 1 variabel (confirmation days, threshold, EMA slope) — semua exploratory, hasil final di rangkum di root-level closeout | 20 |
| `walk_forward_with_costs_run/` | Validasi walk-forward dengan biaya transaksi disertakan | 2 |
| `paper_trading/` | Log paper trading harian | 2 |
| `quant/` | Script riset eksperimen BUMI/DEWA sentimen tersimpan sebagai referensi | 1 |

## Cara menelusuri arsip root-level (kalau butuh detail spesifik)

File-file di root diberi nama per-fase, contoh: `phase_b_item5_*`, `baseline_v4_quality_gate_*`, `holdout_profitability_borderline_*`. Kalau butuh histori keputusan spesifik:

```bash
ls output/phase_b_item5_*        # semua artefak item 5 Phase B
ls output/baseline_v4_*          # semua artefak redesign baseline v4
```

Pola umum tiap fase: `*_report.txt` (naratif), `*_summary.json` (angka), `*_go_no_go.json` (keputusan lolos/tidak).

---
*File ini dibuat 2026-07-07 sebagai bagian dari Gap 6 (dokumentasi & infra) — lihat memory Claude `project-gap-remediation-plan.md` untuk konteks lengkap kenapa dibutuhkan.*
