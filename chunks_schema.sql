-- =============================================================
-- Chunks catalog (slice 2)
--
-- Two tables, schema only — no seed data.  Chunks are populated
-- either by hand (INSERT) or by the miner (slice 3).  Compose.py
-- reads from this catalog at runtime.
-- =============================================================

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS chunk_body;
DROP TABLE IF EXISTS chunks;

CREATE TABLE chunks (
    name        TEXT PRIMARY KEY,
    description TEXT,
    params      TEXT NOT NULL DEFAULT '[]'   -- JSON list of param names: '["addr"]'
);

CREATE TABLE chunk_body (
    chunk_name TEXT    NOT NULL,
    step       INTEGER NOT NULL,            -- 0,1,2,... order within chunk
    mnemonic   TEXT    NOT NULL,
    operand    TEXT,                        -- literal int as string ("14")
                                            -- or param ref ("$addr")
                                            -- or NULL/'' meaning 0
    comment    TEXT,
    PRIMARY KEY (chunk_name, step),
    FOREIGN KEY (chunk_name) REFERENCES chunks(name) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunk_body_name ON chunk_body(chunk_name);
