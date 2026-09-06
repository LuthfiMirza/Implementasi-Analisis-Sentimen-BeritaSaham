# SELF_RADAR_V1 State

Status: experimental fallback, bukan sinyal resmi.

Rule:
- `RSI14 >= 60`
- `ret_5d >= 5%`
- `dd_20d >= -5%`

Execution plan:
- Scan near close.
- Entry near close on signal date.
- Trailing stop 1% starts next market day at 09:30 WIB.
- Track separately from `GABUNGAN`, `MOMENTUM`, and `BOTTOM_REBOUND`.

## 2026-09-06 Snapshot

BUY SORE INI:
- `SINI` Rp14.500, RSI14 85,17, ret_5d 36,15%, dd_20d -1,36%.
- `CUAN` Rp940, RSI14 69,94, ret_5d 15,34%, dd_20d 0,00%.
- `ESSA` Rp705, RSI14 62,38, ret_5d 8,46%, dd_20d -2,08%.

WAIT:
- `INET` Rp366, RSI14 73,03, ret_5d 4,57%, dd_20d 0,00%.
- `HATM` Rp615, RSI14 61,54, ret_5d 6,03%, dd_20d -5,38%.
- `JKON` Rp88, RSI14 62,70, ret_5d 3,53%, dd_20d 0,00%.
- `IATA` Rp131, RSI14 63,00, ret_5d 3,97%, dd_20d -5,07%.
- `PACK` Rp560, RSI14 91,28, ret_5d 0,00%, dd_20d 0,00%.
- `JARR` Rp3.220, RSI14 71,66, ret_5d 2,22%, dd_20d -3,59%.
- `GULA` Rp780, RSI14 55,36, ret_5d 2,63%, dd_20d -2,50%.

Signal date: 2026-09-06.
Entry: 2026-09-06 near close.
Trailing stop: 1% active 2026-09-07 09:30 WIB.

## Monitoring

Scheduler sends Telegram alert on weekdays at 15:35 WIB using `research:send-self-radar-alert --send`.
Manual fill/exit log command:

```bash
php artisan research:self-radar-log TICKER --date=YYYY-MM-DD --fill=PRICE
php artisan research:self-radar-log TICKER --date=YYYY-MM-DD --exit=PRICE
```
