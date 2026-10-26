"""Config loading: reads .env for secrets and returns a simple config dict."""

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_config(env_path=None):
    """Load .env (repo root by default) and return a config dict."""
    env_path = env_path or (REPO_ROOT / ".env")
    load_dotenv(env_path)

    cfg = {
        "device_ip": os.environ.get("DEVICE_IP"),
        "device_id": os.environ.get("DEVICE_ID"),
        "local_key": os.environ.get("LOCAL_KEY"),
        "db_path": os.environ.get("DB_PATH", str(REPO_ROOT / "data" / "power.db")),
        "version": float(os.environ.get("TUYA_VERSION", "3.5")),
        # Seconds of raw 1Hz data to keep before pruning (older lives in
        # rollup_1min). 0 = keep all raw indefinitely.
        "retain_raw_seconds": int(os.environ.get("RETAIN_RAW_SECONDS", "0")),
        # Deadband: only WRITE a raw row when a metric changes by at least this
        # much since the last written value (raw capture still happens in the
        # in-memory buffer, so rollup avg/min/max stay full-resolution).
        "deadband": {
            "current": float(os.environ.get("DEADBAND_CURRENT", "0.05")),    # A
            "power": float(os.environ.get("DEADBAND_POWER", "5.0")),         # W
            "voltage": float(os.environ.get("DEADBAND_VOLTAGE", "2.0")),     # V
            "frequency": float(os.environ.get("DEADBAND_FREQUENCY", "0.1")), # Hz
            "power_factor": float(os.environ.get("DEADBAND_POWER_FACTOR", "0.02")),
            "energy": float(os.environ.get("DEADBAND_ENERGY", "1.0")),       # Wh
            "cpu_temp": float(os.environ.get("DEADBAND_CPU_TEMP", "1.0")),   # C
        },
        # Even if a metric stays inside its deadband, force-write at least this
        # often (heartbeat) so the raw table always has a recent sample.
        "heartbeat_seconds": float(os.environ.get("HEARTBEAT_SECONDS", "60")),
        # Log level for the collector (DEBUG shows every push/write/skip).
        "log_level": os.environ.get("LOG_LEVEL", "INFO").upper(),
    }
    missing = [k for k in ("device_ip", "device_id", "local_key") if not cfg[k]]
    if missing:
        raise SystemExit(
            f"Missing required config in .env: {', '.join(missing)}. "
            f"Copy .env.example to .env and fill it in."
        )
    return cfg
