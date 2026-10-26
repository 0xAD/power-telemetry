"""
Main collector: continuous push-subscriber for the S1BW energy socket.

Design
------
The device pushes a full datapoint set at ~1 Hz over a persistent local
connection (Tuya protocol 3.5) once the real-time toggle is armed. We keep ONE
connection open for the life of the process and read every push.

Three layers keep capture full-resolution while disk stays small:

1. In-memory minute buffer  — every 1 Hz sample for the current minute is
   buffered, so the 1-minute rollup (avg/min/max) is computed from ALL samples,
   never from the downsampled raw table. This keeps rollup averages unbiased.

2. Deadband write-through    — a raw `readings` row is only written when a
   metric moves by at least its deadband threshold, OR a heartbeat interval has
   elapsed since its last write. Raw capture is therefore sparse for steady
   loads but never stale, and transient spikes always land.

3. rollup_1min archive       — completed minutes are aggregated from the buffer
   into the compact permanent table (avg/min/max/samples), which survives raw
   pruning.

Run from the repo root:
    python -m collector.run
"""

import datetime
import logging
import time

from .config import load_config
from .device import S1EnergySocket
from .dpmap import METRICS, metric_name, scale, unit
from db import store

log = logging.getLogger("power-collector")

BUCKET = 60           # rollup bucket size, seconds
PRUNE_EVERY = 3600    # seconds between raw-retention passes
STATUS_EVERY = 300    # seconds between periodic status summaries


class MinuteBuffer:
    """Accumulate every 1 Hz sample, bucketed by minute, in memory.

    Aggregating from here (instead of from the deadbanded raw table) keeps
    rollup avg/min/max exact.
    """

    def __init__(self, bucket=BUCKET):
        self.bucket = bucket
        self.buckets = {}  # bucket_start -> {metric: list[(ts, value, unit)]}

    def add(self, ts, metric, value, unit):
        b = (ts // self.bucket) * self.bucket
        self.buckets.setdefault(b, {}).setdefault(metric, []).append(
            (ts, value, unit)
        )

    def pop_completed(self, now):
        """Aggregate and return every COMPLETED bucket (its end has passed).
        Returns list of (bucket_ts, metric, avg, min, max, samples, unit)."""
        current = (now // self.bucket) * self.bucket
        rows = []
        for b in list(self.buckets):
            if b < current:
                for metric, samples in self.buckets.pop(b).items():
                    vals = [v for _t, v, _u in samples]
                    if not vals:
                        continue
                    rows.append((
                        b, metric,
                        sum(vals) / len(vals), min(vals), max(vals),
                        len(vals), samples[0][2],
                    ))
        return rows

    def __len__(self):
        return len(self.buckets)


class DeadbandTracker:
    """Decides whether a raw row is worth writing, per metric."""

    def __init__(self, thresholds, heartbeat):
        self.thresholds = thresholds
        self.heartbeat = heartbeat
        self.last_value = {}  # metric -> last written value
        self.last_ts = {}     # metric -> ts of last write
        self.written = 0
        self.skipped = 0

    def should_write(self, metric, value, ts):
        if metric not in self.last_value:
            return True  # first sample always lands
        delta = abs(value - self.last_value[metric])
        thresh = self.thresholds.get(metric, 0.0)
        if delta >= thresh:
            return True  # moved beyond deadband
        if self.heartbeat and (ts - self.last_ts.get(metric, 0)) >= self.heartbeat:
            return True  # heartbeat fallback keeps steady values fresh
        return False

    def note_write(self, metric, value, ts):
        self.last_value[metric] = value
        self.last_ts[metric] = ts
        self.written += 1


def main():
    logging.basicConfig(
        level=logging.getLevelName(__import__("os").environ.get("LOG_LEVEL", "INFO")),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = load_config()

    conn = store.connect(cfg["db_path"])
    socket = S1EnergySocket(
        cfg["device_id"], cfg["device_ip"], cfg["local_key"], version=cfg["version"]
    )

    keep_raw = int(cfg.get("retain_raw_seconds", 0) or 0)
    buffer = MinuteBuffer()
    tracker = DeadbandTracker(cfg.get("deadband", {}), cfg.get("heartbeat_seconds", 60))

    log.info(
        "collector started: device=%s @ %s -> %s | raw retention: %s | "
        "deadband: %s | heartbeat: %ss",
        cfg["device_id"], cfg["device_ip"], cfg["db_path"],
        f"{keep_raw}s" if keep_raw else "keep-all",
        cfg.get("deadband"), cfg.get("heartbeat_seconds"),
    )

    next_prune = time.time() + PRUNE_EVERY
    next_status = time.time() + STATUS_EVERY
    pushes = 0

    # Continuous subscriber: stream() arms the toggle, keeps one connection
    # open, reconnects on failure, and yields each pushed datapoint forever.
    for ts, dps in socket.stream():
        ts = int(ts)
        pushes += 1
        for dp_id, raw in dps.items():
            if dp_id not in METRICS or raw is None:
                continue  # skip the toggle DP and unknown DPs
            name = metric_name(dp_id)
            value = scale(dp_id, raw)
            u = unit(dp_id)

            # Always buffer the full-resolution sample (rollup source of truth).
            buffer.add(ts, name, value, u)

            # Deadband write-through to raw.
            if tracker.should_write(name, value, ts):
                store.insert_raw(conn, ts, name, value, u)
                tracker.note_write(name, value, ts)
                log.debug("wrote %s=%s%s @ %s", name, round(value, 3), u, ts)
            else:
                tracker.skipped += 1
                log.debug("skipped %s=%s%s @ %s (within deadband)",
                          name, round(value, 3), u, ts)

        # Roll completed minute buckets (from the buffer).
        now = time.time()
        rows = buffer.pop_completed(now)
        if rows:
            store.insert_rollup_rows(conn, rows)
            # One line per metric with its actual avg value (min-max, samples).
            detail = ", ".join(
                f"{r[1]}={r[2]:g}{r[6]} ({r[3]:g}-{r[4]:g}, n{r[5]})" for r in rows
            )
            log.info("rolled %s: %s",
                     datetime.datetime.fromtimestamp(rows[0][0])
                     .strftime("%H:%M:%S"), detail)

        # Periodic status + raw pruning.
        if now >= next_status:
            log.info(
                "status: %d pushes, %d raw written, %d deadband-skipped, "
                "buffered buckets=%d, last raw ts=%s",
                pushes, tracker.written, tracker.skipped, len(buffer),
                conn.execute("SELECT MAX(ts) FROM readings").fetchone()[0],
            )
            pushes = 0
            next_status = now + STATUS_EVERY

        if keep_raw and now >= next_prune:
            deleted = store.prune_raw(conn, keep_raw)
            if deleted:
                log.info("pruned %d raw row(s) older than %ss", deleted, keep_raw)
            next_prune = now + PRUNE_EVERY


if __name__ == "__main__":
    main()
