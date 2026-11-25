# Laporan Riset Kuantitatif Fase FG-3: Strategi `RS_DEFENSIVE` (*Defensive Relative Strength Rotation*, 2023–2026 OOS)

> **Tanggal Riset**: 26 November 2026  
> **Universe**: 18 saham BigCap & Defensif LQ45 (`ADRO, AMRT, ASII, BBCA, BBNI, BBRI, BMRI, CPIN, ICBP, INDF, INTP, ITMG, KLBF, MEDC, PTBA, SMGR, TLKM, UNVR`)  
> **Biaya Transaksi**: `0,40%` *round-trip* (0,15% beli + 0,25% jual). Evaluasi Walk-Forward per tahun (`2023`, `2024`, `2025`, `2026`) + khusus rezim bearish (`IHSG < MA50`).

## 1. Hasil Komparasi 4 Tahun (Termasuk Rezim Bearish `IHSG < MA50`)

| Konfigurasi `RS_DEFENSIVE` | N | WR (%) | PF | Avg Net (%) | Sum Net (%) | MaxDD (%) | PF 2023 | PF 2024 | PF 2025 | PF 2026 | **PF Rezim Bearish** |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `A_RS>=2.5%_Vol>=1.5x_IHSGRed_TS2.5/Buf2%` | 103 | 37.9% | **0.57** | -0.99% | -102.1% | -102.1% | 0.55 | 0.98 | 0.44 | 0.46 | **0.58** |
| `B_RS>=2.0%_Vol>=1.3x_IHSGRed_TS2.5/Buf2%` | 145 | 37.2% | **0.59** | -0.93% | -134.7% | -149.4% | 1.01 | 0.94 | 0.39 | 0.38 | **0.67** |
| `C_RS>=3.0%_Vol>=1.5x_IHSGRed_TS2.5/Buf2%` | 89 | 34.8% | **0.49** | -1.16% | -103.2% | -106.3% | 0.80 | 0.77 | 0.29 | 0.42 | **0.58** |
| `D_RS>=2.5%_Vol>=1.5x_WeakOr<MA50_Hold5d` | 160 | 35.0% | **0.57** | -0.92% | -147.9% | -157.5% | 0.63 | 0.82 | 0.36 | 0.54 | **0.53** |
| `E_RS>=2.5%_Vol>=1.3x_WeakOr<MA50_Hold10d` | 187 | 32.6% | **0.46** | -1.33% | -248.6% | -267.8% | 0.60 | 0.62 | 0.30 | 0.43 | **0.42** |

## 2. Keputusan Gate Walk-Forward OOS
- **Kandidat Terbaik**: `B_RS>=2.0%_Vol>=1.3x_IHSGRed_TS2.5/Buf2%` (WR `37.2%`, PF `0.59`, Avg Net `-0.93%`, PF Bearish `0.67`).
- **Verdict**: **❌ GAGAL GATE OOS (WR < 55% atau PF < 1.5) — DOKUMENTASIKAN SEBAGAI TEMUAN NEGATIF, JANGAN DEPLOY**