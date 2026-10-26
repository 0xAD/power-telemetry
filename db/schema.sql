-- Power telemetry schema (SQLite).
-- One row per (timestamp, metric). Storing long (metric,value) rows instead of
-- wide (one column per metric) makes the schema flexible and the DB compact.

CREATE TABLE IF NOT EXISTS readings (
    ts       INTEGER NOT NULL,   -- Unix epoch seconds
    metric   TEXT    NOT NULL,   -- current, power, voltage, energy, frequency, power_factor, cpu_temp
    value    REAL    NOT NULL,
    unit     TEXT,
    PRIMARY KEY (ts, metric)
);

-- Helpful for dashboard queries.
CREATE INDEX IF NOT EXISTS idx_readings_metric_ts ON readings (metric, ts);

-- 1-minute rollup for long-term history. Raw 1Hz `readings` can be pruned
-- (e.g. keep recent window); rollup_1min is the compact permanent archive.
CREATE TABLE IF NOT EXISTS rollup_1min (
    ts     INTEGER NOT NULL,   -- bucket start (floor(epoch/60)*60)
    metric TEXT    NOT NULL,
    avg    REAL,
    min    REAL,
    max    REAL,
    samples INTEGER,
    unit   TEXT,
    PRIMARY KEY (ts, metric)
);
CREATE INDEX IF NOT EXISTS idx_rollup_metric_ts ON rollup_1min (metric, ts);
