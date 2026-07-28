-- Append-only log. UPDATE/DELETE are blocked by triggers below, not just by convention --
-- if a logged row turns out wrong, log a correction row referencing it via notes, never edit.

CREATE TABLE IF NOT EXISTS signals (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    logged_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    signal_posted_at    TEXT NOT NULL,      -- when the source posted it (as stated in the message)
    source              TEXT NOT NULL,      -- e.g. "Zeta AI IDX Stock Signal"
    ticker              TEXT NOT NULL,
    signal_type         TEXT NOT NULL,      -- BUY / WATCHLIST / SELL, as shown
    confidence_score    INTEGER,            -- as shown by the source, NULL if not stated
    stated_entry_price  REAL,               -- entry price the source claims
    market_price_at_log REAL NOT NULL,      -- actual observed market price when YOU logged it
    stated_tp1          REAL,
    stated_sl_default   REAL,               -- default (ATR-based) stop-loss as shown
    indicators_cited    TEXT,               -- free text: "MACD bullish, RSI 58.17, ..."
    raw_text            TEXT,               -- verbatim message/caption, kept as evidence
    tracked             INTEGER NOT NULL,   -- 1 if it matches PROTOCOL.md's filter (BUY + confidence=5), else 0
    skip_reason         TEXT,               -- required if tracked=0, e.g. "confidence=3" or "signal_type=WATCHLIST"
    notes               TEXT
);

-- Outcomes are filled in separately by evaluate.py once the 30-day horizon has elapsed, keyed
-- to a signal_id. This table is also append-only for the same reason.
CREATE TABLE IF NOT EXISTS outcomes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id           INTEGER NOT NULL REFERENCES signals(id),
    evaluated_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    horizon_end_date    TEXT NOT NULL,      -- signal_posted_at + 30 calendar days
    result              TEXT NOT NULL,      -- TP_HIT / SL_HIT / TIME_EXIT / DATA_UNAVAILABLE
    exit_price           REAL,
    exit_date            TEXT,
    days_to_exit          INTEGER,
    gross_return          REAL,             -- (exit_price / market_price_at_log) - 1
    net_return             REAL,            -- gross_return - 0.008 round-trip cost
    buy_hold_return_30d    REAL,            -- same ticker, held the full 30 calendar days
    ihsg_return_30d        REAL,            -- IHSG over the same window
    UNIQUE(signal_id)
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

CREATE TRIGGER IF NOT EXISTS outcomes_no_update
BEFORE UPDATE ON outcomes
BEGIN
    SELECT RAISE(ABORT, 'outcomes is append-only: re-running evaluate.py skips already-evaluated signals');
END;

CREATE TRIGGER IF NOT EXISTS outcomes_no_delete
BEFORE DELETE ON outcomes
BEGIN
    SELECT RAISE(ABORT, 'outcomes is append-only: rows cannot be deleted');
END;
