# PTB V6 Trailing Start Compare

Periode: `2026-07-20` sampai `2026-09-01`.
Ticker dipilih: semua ticker picks PTB manual yang punya data Yahoo 5m (`147` ticker).
Trailing stop: `1%`. Fee: `0.3%`.

## Summary 4 Skenario

| Rank | Skenario | Raw Trade | Hari | Total Return Harian | Avg Harian | Median Harian | Win Rate Harian | Avg Trade | Median Trade | Win Rate Trade |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | buy_close_H_minus_1__trail_from_0930 | 434 | 29 | +100.82% | +3.48% | +2.94% | 96.6% | +3.32% | +2.09% | 85.9% |
| 2 | buy_close_H_minus_1__trail_from_entry | 434 | 29 | +64.24% | +2.22% | +1.69% | 96.6% | +2.06% | +0.94% | 77.6% |
| 3 | buy_open_H__trail_from_0930 | 457 | 30 | +64.22% | +2.14% | +2.14% | 93.3% | +2.14% | +1.10% | 73.7% |
| 4 | buy_open_H__trail_from_entry | 457 | 30 | +26.84% | +0.89% | +0.51% | 83.3% | +0.90% | +0.11% | 53.2% |

## Top 20 Trade

```text
      date ticker                              scenario                 open_time  open_price                entry_time  entry_price          trail_start_time                 exit_time  exit_price   exit_reason  return_pct
2026-07-23   MLPT  buy_close_H_minus_1__trail_from_0930 2026-07-23 09:00:00+07:00      1820.0 2026-07-22 16:10:00+07:00       1625.0 2026-07-23 09:30:00+07:00 2026-07-23 09:30:00+07:00     2009.70 trailing_stop       23.37
2026-07-28   MCAS  buy_close_H_minus_1__trail_from_0930 2026-07-28 09:00:00+07:00       282.0 2026-07-27 16:05:00+07:00        266.0 2026-07-28 09:30:00+07:00 2026-07-28 09:30:00+07:00      328.68 trailing_stop       23.26
2026-07-28   MCAS buy_close_H_minus_1__trail_from_entry 2026-07-28 09:00:00+07:00       282.0 2026-07-27 16:05:00+07:00        266.0 2026-07-28 09:00:00+07:00 2026-07-28 09:00:00+07:00      328.68 trailing_stop       23.26
2026-08-21   COIN  buy_close_H_minus_1__trail_from_0930 2026-08-21 09:00:00+07:00      1000.0 2026-08-20 16:10:00+07:00        880.0 2026-08-21 09:30:00+07:00 2026-08-21 09:30:00+07:00     1084.05 trailing_stop       22.89
2026-07-28   BAJA  buy_close_H_minus_1__trail_from_0930 2026-07-28 09:00:00+07:00       242.0 2026-07-27 16:05:00+07:00        222.0 2026-07-28 09:30:00+07:00 2026-07-28 13:50:00+07:00      273.24 trailing_stop       22.78
2026-07-23   MDIA  buy_close_H_minus_1__trail_from_0930 2026-07-23 09:00:00+07:00       106.0 2026-07-22 16:10:00+07:00        104.0 2026-07-23 09:30:00+07:00 2026-07-23 09:30:00+07:00      127.71 trailing_stop       22.50
2026-07-23   MLPT buy_close_H_minus_1__trail_from_entry 2026-07-23 09:00:00+07:00      1820.0 2026-07-22 16:10:00+07:00       1625.0 2026-07-23 09:00:00+07:00 2026-07-23 09:00:00+07:00     1980.00 trailing_stop       21.55
2026-07-23   MDIA           buy_open_H__trail_from_0930 2026-07-23 09:00:00+07:00       106.0 2026-07-23 09:00:00+07:00        106.0 2026-07-23 09:30:00+07:00 2026-07-23 09:30:00+07:00      127.71 trailing_stop       20.18
2026-07-28   BAJA buy_close_H_minus_1__trail_from_entry 2026-07-28 09:00:00+07:00       242.0 2026-07-27 16:05:00+07:00        222.0 2026-07-28 09:00:00+07:00 2026-07-28 09:00:00+07:00      267.30 trailing_stop       20.11
2026-08-26   NZIA  buy_close_H_minus_1__trail_from_0930 2026-08-26 09:00:00+07:00       172.0 2026-08-24 16:10:00+07:00        159.0 2026-08-26 09:30:00+07:00 2026-08-26 09:30:00+07:00      191.07 trailing_stop       19.87
2026-07-22   DOOH  buy_close_H_minus_1__trail_from_0930 2026-07-22 09:00:00+07:00       151.0 2026-07-21 16:10:00+07:00        150.0 2026-07-22 09:30:00+07:00 2026-07-22 09:30:00+07:00      180.18 trailing_stop       19.82
2026-07-23   MDIA buy_close_H_minus_1__trail_from_entry 2026-07-23 09:00:00+07:00       106.0 2026-07-22 16:10:00+07:00        104.0 2026-07-23 09:00:00+07:00 2026-07-23 09:00:00+07:00      124.74 trailing_stop       19.64
2026-07-22   DOOH buy_close_H_minus_1__trail_from_entry 2026-07-22 09:00:00+07:00       151.0 2026-07-21 16:10:00+07:00        150.0 2026-07-22 09:00:00+07:00 2026-07-22 09:00:00+07:00      179.19 trailing_stop       19.16
2026-08-20   COIN buy_close_H_minus_1__trail_from_entry 2026-08-20 09:00:00+07:00       755.0 2026-08-19 16:10:00+07:00        705.0 2026-08-20 09:00:00+07:00 2026-08-20 09:00:00+07:00      841.50 trailing_stop       19.06
2026-08-20   COIN  buy_close_H_minus_1__trail_from_0930 2026-08-20 09:00:00+07:00       755.0 2026-08-19 16:10:00+07:00        705.0 2026-08-20 09:30:00+07:00 2026-08-20 09:30:00+07:00      841.50 trailing_stop       19.06
2026-07-22   DOOH           buy_open_H__trail_from_0930 2026-07-22 09:00:00+07:00       151.0 2026-07-22 09:00:00+07:00        151.0 2026-07-22 09:30:00+07:00 2026-07-22 09:30:00+07:00      180.18 trailing_stop       19.02
2026-08-18   TEBE  buy_close_H_minus_1__trail_from_0930 2026-08-18 09:00:00+07:00      1500.0 2026-08-14 16:10:00+07:00       1375.0 2026-08-18 09:30:00+07:00 2026-08-18 09:30:00+07:00     1638.45 trailing_stop       18.86
2026-08-21   BRRC           buy_open_H__trail_from_0930 2026-08-21 09:00:00+07:00        84.0 2026-08-21 09:00:00+07:00         84.0 2026-08-21 09:30:00+07:00 2026-08-21 09:30:00+07:00       99.99 trailing_stop       18.74
2026-08-21   BRRC  buy_close_H_minus_1__trail_from_0930 2026-08-21 09:00:00+07:00        84.0 2026-08-20 16:10:00+07:00         84.0 2026-08-21 09:30:00+07:00 2026-08-21 09:30:00+07:00       99.99 trailing_stop       18.74
2026-08-18   BYAN buy_close_H_minus_1__trail_from_entry 2026-08-18 09:00:00+07:00     15600.0 2026-08-14 16:10:00+07:00      14400.0 2026-08-18 09:00:00+07:00 2026-08-18 09:00:00+07:00    17102.25 trailing_stop       18.47
```

## Ticker Yang Dipakai

```text
AADI, AALI, ADMR, ADRO, AKRA, AMMN, AMRT, ANTM, ARCI, ARKO, ASII, ATLA, AUTO, BACH, BAIK, BAJA, BBCA, BBRI, BBTN, BIPI, BKSL, BMRI, BNBR, BNGA, BREN, BRMS, BRPT, BRRC, BSDE, BSSR, BULL, BUMI, BUVA, BWPT, BYAN, CBRE, CDIA, COCO, COIN, CPIN, CTTH, CUAN, CYBR, DEWA, DMAS, DOOH, DSSA, ELSA, EMAS, EMMI, EMTK, ENRG, ERAA, ESSA, FAST, FPNI, FUTR, GDST, GGRM, GJTL, GPSO, GTSI, GULA, HATM, HMSP, HRTA, HRUM, HUMI, IATA, ICBP, IMPC, INCO, INDF, INDY, INET, INKP, IRSX, ISAT, ITMG, JARR, JELI, JGLE, JKON, KBLV, KETR, KIJA, KLBF, KOKA, KOTA, LPKR, LSIP, MAPI, MAXI, MBMA, MCAS, MDIA, MDKA, MEDC, MGLV, MINA, MLPL, MLPT, NCKL, NICL, NSSS, NTBK, NZIA, OASA, OILS, PACK, PADA, PADI, PAMG, PANI, PGAS, PNLF, PRDL, PSAB, PTBA, PTRO, PWON, RAJA, RANS, RATU, REAL, RGAS, RMKE, SGER, SINI, SLIS, SMGR, SMIL, SRTG, SSIA, SWID, TEBE, TINS, TKIM, TLKM, TOBA, TOWR, TPIA, UNVR, VKTR, WIFI, WIRG, WMUU
```

Detail trade CSV: `output/ptb_v6_trailing_start_trades.csv`
