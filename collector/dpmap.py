"""
DP -> metric mapping for the Atorch S1BW (Tuya protocol 3.5) energy socket.

Datapoint IDs and scales verified against the device's official spec
(Query Device Specification / shadow properties) and live measurement.

Key facts:
  - The device only streams data over an established local connection once the
    "real-time reporting" toggle (dp 140) is armed to True.
  - It PUSHES updates roughly once per second (the toggle is named
    `real_time_swith_1s_60s`). One-shot status() queries return None for these
    DPs; you must read the pushed stream from a persistent connection.
  - All integer DPs carry a `scale` (power of 10 divisor) from the spec.

DP reference (code: dp_id / scale / unit):
  18  cur_current     /1000  A      (scale 3)
  19  cur_power       /100   W      (scale 2)
  20  cur_voltage     /100   V      (scale 2)
  123 ele              x1     Wh    (cumulative energy; /1000 = kWh)
  133 cur_frequency   /100   Hz     (scale 2)
  134 power_factor    /100   -      (scale 2)
  135 cpu_temp         x1     C
  140 real_time_swith_1s_60s  bool  (reporting toggle; arm to True)
"""

# DP -> (name, scale_divisor, unit)
METRICS = {
    18: ("current", 1000, "A"),
    19: ("power", 100, "W"),
    20: ("voltage", 100, "V"),
    123: ("energy", 1, "Wh"),
    133: ("frequency", 100, "Hz"),
    134: ("power_factor", 100, ""),
    135: ("cpu_temp", 1, "C"),
}

# The DP that arms real-time reporting. Must be set to True before streaming.
REALTIME_TOGGLE_DP = 140


def _norm(dp_id: "int | str") -> "int":
    """DP ids may arrive as int (status()) or str (receive() push). Normalize."""
    if isinstance(dp_id, str) and dp_id.isdigit():
        return int(dp_id)
    return int(dp_id)


def scale(dp_id, raw):
    """Convert a raw DP integer to its real-world float value."""
    if raw is None:
        return None
    dp_id = _norm(dp_id)
    if dp_id not in METRICS:
        return raw
    divisor = METRICS[dp_id][1]
    return raw / divisor


def metric_name(dp_id):
    dp_id = _norm(dp_id)
    if dp_id in METRICS:
        return METRICS[dp_id][0]
    return f"dp{dp_id}"


def unit(dp_id):
    dp_id = _norm(dp_id)
    return METRICS[dp_id][2] if dp_id in METRICS else ""
