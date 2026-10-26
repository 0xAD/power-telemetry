#!/usr/bin/env python3
"""
One-shot read: arm the socket and print one sample of all metrics.

Usage:
    python scripts/once.py

Requires .env with DEVICE_IP, DEVICE_ID, LOCAL_KEY.
"""
import sys

sys.path.insert(0, ".")
from collector.config import load_config
from collector.device import S1EnergySocket
from collector.dpmap import METRICS, metric_name, scale, unit


def main():
    cfg = load_config()
    sock = S1EnergySocket(cfg["device_id"], cfg["device_ip"], cfg["local_key"],
                          version=cfg["version"])
    print("Reading (arming real-time toggle, ~15s)...")
    merged = {}
    for _ts, dps in sock.stream(duration=15):
        for dp_id, raw in dps.items():
            if dp_id in METRICS and raw is not None:
                merged[dp_id] = raw

    if not merged:
        print("No data received. Is the device reachable? Is the Tuya app closed?")
        return 1

    print("\nLatest readings:")
    for dp_id in sorted(merged):
        name = metric_name(dp_id)
        val = scale(dp_id, merged[dp_id])
        u = unit(dp_id) if dp_id in METRICS else ""
        print(f"  {name:<13} {val:>10.3f} {u}".rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
