-- Append-only log for the "IHSG + stock crash together" bounce signal (Fase AB -> AC).
-- UPDATE/DELETE blocked by triggers, not just convention -- see PROTOCOL.md.

CREATE TABLE IF NOT EXISTS signals (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    ticker              TEXT NOT NULL,          -- BUMI or DEWA
    label               TEXT NOT NULL,          -- 'tracked' (BUMI) or 'exploratory' (DEWA) per PROTOCOL.md
    trigger_date        TEXT NOT NULL,          -- trading day the 2-day drawdown condition was met
    ihsg_ret_2d         REAL NOT NULL,
    stock_ret_2d        REAL NOT NULL,
    entry_date          TEXT NOT NULL,          -- next trading day after trigger_date
    entry_price         REAL NOT NULL,
    rsi14               REAL,                   -- context only, NOT part of the entry rule -- see
    stoch_k             REAL,                   -- PROTOCOL.md. Live-checked: overbought/oversold
                                                  -- readings matched the entry direction in only
                                                  -- ~3/8 of the user's own hindsight examples, so
                                                  -- these are shown as supporting info, never a
                                                  -- second trigger condition.
    signal_type         TEXT,                   -- Fase BK: 'ret2d' | 'drawdown' | 'ganda' -- which
                                                  -- leg(s) of the combined rule fired (BUMI/DEWA/
                                                  -- BRPT/ESSA/UNVR only; SMGR stays ret2d-only, see
                                                  -- COMBINED_RULE_TICKERS in detect_signal.py).
    notes               TEXT,
    UNIQUE(ticker, trigger_date)
);

-- Fase BL: sinyal MOMENTUM (RSI14 > 60) -- strategi terpisah dari `signals` (drawdown-bounce),
-- tabel sendiri supaya tidak campur dengan mean-reversion. Append-only, pola sama persis.
CREATE TABLE IF NOT EXISTS momentum_signals (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    ticker              TEXT NOT NULL,          -- BUMI, DEWA, atau BRPT (satu-satunya yang lulus
                                                  -- validasi ketat penuh, lihat detect_signal.py)
    trigger_date        TEXT NOT NULL,          -- trading day RSI14 > 60 terpenuhi
    rsi14               REAL NOT NULL,          -- BAGIAN dari aturan entry (beda dari `signals`
                                                  -- table dimana rsi14 cuma info konteks)
    entry_date          TEXT NOT NULL,
    entry_price         REAL NOT NULL,
    notes               TEXT,
    UNIQUE(ticker, trigger_date)
);

-- Fase BN: peringatan dini H-1 sore -- murni informasional, TIDAK mengubah aturan entry resmi
-- (masih closing T+1, lihat `signals`). Tabel terpisah, append-only, pola sama.
CREATE TABLE IF NOT EXISTS heads_up_alerts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    ticker              TEXT NOT NULL,
    trigger_date        TEXT NOT NULL,          -- hari closing yang memicu peringatan (T, bukan T+1)
    ihsg_ret_2d         REAL NOT NULL,
    stock_ret_2d        REAL NOT NULL,
    dd_20d              REAL NOT NULL,
    signal_type         TEXT NOT NULL,
    notes               TEXT,
    UNIQUE(ticker, trigger_date)
);

CREATE TABLE IF NOT EXISTS outcomes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id           INTEGER NOT NULL REFERENCES signals(id),
    horizon_days        INTEGER NOT NULL,       -- 5 or 10 (trading days)
    evaluated_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    exit_date           TEXT NOT NULL,
    exit_price          REAL NOT NULL,
    gross_return        REAL NOT NULL,
    net_return          REAL NOT NULL,          -- gross_return - 0.008 round-trip cost
    buy_hold_return     REAL NOT NULL,           -- same ticker, same window, no signal filter
    ihsg_return         REAL NOT NULL,           -- IHSG over the same window
    UNIQUE(signal_id, horizon_days)
);

CREATE TRIGGER IF NOT EXISTS signals_no_update
BEFORE UPDATE ON signals
BEGIN
    SELECT RAISE(ABORT, 'signals is append-only: log a new row instead of editing');
END;

CREATE TRIGGER IF NOT EXISTS signals_no_delete
BEFORE DELETE ON signals
BEGIN
    SELECT RAISE(ABORT, 'signals is append-only: rows cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS momentum_signals_no_update
BEFORE UPDATE ON momentum_signals
BEGIN
    SELECT RAISE(ABORT, 'momentum_signals is append-only: log a new row instead of editing');
END;

CREATE TRIGGER IF NOT EXISTS momentum_signals_no_delete
BEFORE DELETE ON momentum_signals
BEGIN
    SELECT RAISE(ABORT, 'momentum_signals is append-only: rows cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS heads_up_alerts_no_update
BEFORE UPDATE ON heads_up_alerts
BEGIN
    SELECT RAISE(ABORT, 'heads_up_alerts is append-only: log a new row instead of editing');
END;

CREATE TRIGGER IF NOT EXISTS heads_up_alerts_no_delete
BEFORE DELETE ON heads_up_alerts
BEGIN
    SELECT RAISE(ABORT, 'heads_up_alerts is append-only: rows cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS outcomes_no_update
BEFORE UPDATE ON outcomes
BEGIN
    SELECT RAISE(ABORT, 'outcomes is append-only: re-running evaluate.py skips already-evaluated rows');
END;

CREATE TRIGGER IF NOT EXISTS outcomes_no_delete
BEFORE DELETE ON outcomes
BEGIN
    SELECT RAISE(ABORT, 'outcomes is append-only: rows cannot be deleted');
END;
