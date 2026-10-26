"""SQLite storage for power readings."""

import os
import sqlite3

SCHEMA = os.path.join(os.path.dirname(__file__), "schema.sql")


def connect(db_path):
    """Open (creating if needed) the SQLite DB and ensure schema exists."""
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(open(SCHEMA).read())
    conn.commit()
    return conn


def insert_readings(conn, ts, metrics):
    """
    Insert a batch of metric values for a single timestamp.

    Args:
        conn: sqlite3 connection from connect().
        ts: Unix epoch seconds.
        metrics: dict {metric_name: (value, unit)}.
    """
    rows = [(ts, name, value, unit) for name, (value, unit) in metrics.items()]
    conn.executemany(
        "INSERT OR IGNORE INTO readings (ts, metric, value, unit) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def insert_raw(conn, ts, metric, value, unit):
    """Insert a single raw reading (one push). Idempotent on (ts, metric)."""
    conn.execute(
        "INSERT OR IGNORE INTO readings (ts, metric, value, unit) VALUES (?, ?, ?, ?)",
        (ts, metric, value, unit),
    )
    conn.commit()


def insert_rollup_rows(conn, rows):
    """Bulk-insert pre-aggregated rollup rows.

    `rows`: iterable of (bucket_ts, metric, avg, min, max, samples, unit).
    Idempotent (INSERT OR REPLACE on (ts, metric)).
    """
    conn.executemany(
        "INSERT OR REPLACE INTO rollup_1min "
        "(ts, metric, avg, min, max, samples, unit) VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def rollup_pending(conn, bucket=60):
    """Aggregate all `readings` buckets not yet rolled up into rollup_1min.

    Rolls up COMPLETED buckets only (a bucket is complete when its end has
    passed), so the current in-progress minute stays in raw only until it ends.
    Idempotent: INSERT OR REPLACE, safe to call repeatedly.
    Returns the number of buckets rolled up.
    """
    last_complete = (int(__import__("time").time()) // bucket) * bucket
    cur = conn.execute(
        "SELECT COALESCE(MAX(ts), 0) FROM rollup_1min"
    )
    watermark = cur.fetchone()[0]

    rows = conn.execute(
        """
        SELECT (ts / ?) * ? AS bucket, metric, unit,
               AVG(value) AS avg, MIN(value) AS min, MAX(value) AS max,
               COUNT(*) AS samples
        FROM readings
        WHERE (ts / ?) * ? > ?
          AND (ts / ?) * ? < ?
        GROUP BY bucket, metric, unit
        """,
        (bucket, bucket, bucket, bucket, watermark, bucket, bucket, last_complete),
    ).fetchall()

    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO rollup_1min (ts, metric, unit, avg, min, max, samples) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    return len(rows)


def prune_raw(conn, keep_seconds):
    """Delete raw `readings` older than `keep_seconds` (rolled-up data survives).
    Returns rows deleted. Use 0/None to keep everything."""
    if not keep_seconds:
        return 0
    cutoff = int(__import__("time").time()) - keep_seconds
    cur = conn.execute("DELETE FROM readings WHERE ts < ?", (cutoff,))
    conn.commit()
    return cur.rowcount


def latest(conn, metric=None, limit=1):
    """Return the most recent reading(s)."""
    if metric:
        cur = conn.execute(
            "SELECT ts, metric, value, unit FROM readings WHERE metric=? "
            "ORDER BY ts DESC LIMIT ?",
            (metric, limit),
        )
    else:
        cur = conn.execute(
            "SELECT ts, metric, value, unit FROM readings ORDER BY ts DESC LIMIT ?",
            (limit,),
        )
    return cur.fetchall()


def range(conn, metric, start_ts=None, end_ts=None, order="ASC"):
    """Readings for a metric, optionally time-bounded. Returns (ts, value, unit)."""
    q = "SELECT ts, value, unit FROM readings WHERE metric=?"
    args = [metric]
    if start_ts is not None:
        q += " AND ts >= ?"
        args.append(start_ts)
    if end_ts is not None:
        q += " AND ts <= ?"
        args.append(end_ts)
    q += " ORDER BY ts " + order
    return conn.execute(q, args).fetchall()
