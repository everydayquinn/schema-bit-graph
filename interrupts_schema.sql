-- =============================================================
-- Interrupt dispatcher schema (the missing third role).
--
-- interrupt_vectors  : event_type -> handler_chunk lookup
-- event_log          : append-only history of every fired event + outcome
--
-- Apply on top of an existing cpu.db that already has chunks_schema.
-- =============================================================

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS event_log;
DROP TABLE IF EXISTS interrupt_vectors;

CREATE TABLE interrupt_vectors (
    event_type    TEXT PRIMARY KEY,
    handler_chunk TEXT NOT NULL,           -- references chunks.name
    description   TEXT,
    registered_on TEXT NOT NULL DEFAULT (date('now'))
);

CREATE TABLE event_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type    TEXT NOT NULL,
    payload_json  TEXT,                    -- JSON of the event payload
    fired_at      TEXT NOT NULL DEFAULT (datetime('now')),
    handler_chunk TEXT,                    -- NULL if no handler registered
    cycles_used   INTEGER,
    halted_clean  INTEGER NOT NULL DEFAULT 0,  -- 1 if HLT fired, 0 if max_cycles hit
    output_a      INTEGER,
    output_b      INTEGER,
    output_out    INTEGER,
    error         TEXT                     -- non-NULL if dispatch failed
);

CREATE INDEX IF NOT EXISTS idx_event_log_type ON event_log(event_type);
CREATE INDEX IF NOT EXISTS idx_event_log_fired ON event_log(fired_at);

-- View: latest outcome per event type
DROP VIEW IF EXISTS v_event_log_recent;
CREATE VIEW v_event_log_recent AS
SELECT id, event_type, fired_at, handler_chunk, halted_clean,
       cycles_used, output_a, output_out
FROM   event_log
ORDER  BY id DESC;
