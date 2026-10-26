#!/usr/bin/env python3
"""
Export readings from the SQLite DB to CSV.

Usage:
    python scripts/export_csv.py [metric] [--start TS] [--end TS] [--out FILE]

Metric defaults to 'power'. Use metric='all' (or omit) for wide format.
Output defaults to stdout; use --out to write a file.
"""
import argparse
import csv
import sys

sys.path.insert(0, ".")
from collector.config import load_config
from collector.dpmap import METRICS, metric_name
from db import store


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("metric", nargs="?", default="power",
                    help="metric name or 'all' (default: power)")
    ap.add_argument("--start", type=int, default=None, help="start epoch ts")
    ap.add_argument("--end", type=int, default=None, help="end epoch ts")
    ap.add_argument("--out", default=None, help="output CSV path")
    args = ap.parse_args()

    cfg = load_config()
    conn = store.connect(cfg["db_path"])

    if args.metric == "all":
        metrics = [metric_name(dp) for dp in METRICS]
    else:
        metrics = [args.metric]

    out = open(args.out, "w", newline="") if args.out else sys.stdout
    writer = csv.writer(out)
    writer.writerow(["ts", "metric", "value", "unit"])
    for m in metrics:
        for ts, val, unit in store.range(conn, m, args.start, args.end):
            writer.writerow([ts, m, val, unit])
    if args.out:
        out.close()
        print(f"Wrote {len(metrics)} metric(s) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
