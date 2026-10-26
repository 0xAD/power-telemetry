# Power Telemetry

Reads live power metrics from an **Atorch S1 Energy Socket (S1BW)** over the local
Tuya protocol and stores them in SQLite for dashboards and analysis.

Licensed under the [MIT License](LICENSE).

**Fully local.** Reads happen over your LAN (port 6668). No Tuya cloud is used
for data collection. The only cloud interaction is a one-time step to obtain the
device's Local Key from the Tuya IoT developer portal.

## How it works

The S1BW runs Tuya protocol 3.5 (AES-GCM). Two facts make it work:

1. **It pushes, it doesn't answer.** Once the real-time reporting toggle
   (DP 140, `real_time_swith_1s_60s`) is armed, the device streams an update
   roughly once per second over an established connection. One-shot `status()`
   queries return `None`. The collector must hold a persistent connection and
   read the push stream (see `collector/device.py`).
2. **It only accepts one local connection at a time.** Keep the Tuya/Smart Life
   app closed on your phone while the collector runs, or reads will drop.

## Metrics

| Metric      | DP  | Scale | Unit    |
|-------------|-----|-------|---------|
| current     | 18  | /1000 | A       |
| power       | 19  | /100  | W       |
| voltage     | 20  | /100  | V       |
| energy      | 123 | ×1    | Wh      |
| frequency   | 133 | /100  | Hz      |
| power_factor| 134 | /100  | —       |
| cpu_temp    | 135 | ×1    | °C      |

Scaling is verified against the device's official DP spec and live measurement.

## Setup

```bash
# 1. Python venv + deps
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# 2. Credentials
cp .env.example .env
#    fill in DEVICE_IP, DEVICE_ID, LOCAL_KEY
#    (LOCAL_KEY from Tuya IoT portal: Query Device Details)

# 3. Quick test (one sample)
./venv/bin/python scripts/once.py
```

## Running the collector

```bash
./venv/bin/python -m collector.run
```

Continuous push-subscriber: keeps ONE persistent connection and reads every
push (≈1 Hz) the device sends. It never sleeps/polls. Three layers keep capture
full-resolution while disk stays small:

1. **In-memory minute buffer** — every 1 Hz sample is buffered, so the 1-min
   rollup (avg/min/max) is computed from ALL samples, never from the
   downsampled raw table. Rollup averages stay unbiased.
2. **Deadband write-through** — a raw `readings` row is written only when a
   metric moves by at least its deadband threshold (default: 5 W, 2 V,
   0.05 A, 0.1 Hz, 1 Wh, ...), or a heartbeat interval (60 s) elapses. Steady
   loads write ~5-10% of the 1 Hz stream; spikes always land.
3. **`rollup_1min` archive** — completed minutes are aggregated from the buffer
   into the compact permanent table, which survives raw pruning.

Tune via `.env`: `RETAIN_RAW_SECONDS` (prune raw after N seconds, 0 = keep
all), `DEADBAND_*` thresholds, `HEARTBEAT_SECONDS`, `LOG_LEVEL`
(DEBUG = every push/write/skip). Logs to stdout (captured by svlogd under
runit).

### Reading the logs

Each completed minute produces one readable rollup line with the actual
measurements, e.g.:

```
INFO power-collector: rolled 16:24:00: voltage=227.1V (226.15-228.6, n16),
     current=1.28A (0.65-1.371, n15), power=277.5W (127.9-300.1, n15),
     cpu_temp=46C (46-46, n16), energy=12715.5Wh (12715-12716, n2),
     frequency=49.96Hz (49.95-49.97, n5), power_factor=0.875 (0.86-0.89, n2)
```

Format per metric: `name=avg (min-max, nSamples)`. `energy` is cumulative, so
its `max` (= the last value in that minute) is the consumption total for the
minute; its `avg` is not meaningful. A missing metric (e.g. `rolled 6 ...`
after a reconnect) means the device pushed no samples for it that minute — not
data loss.

A 5-minute status line reports throughput: `status: 286 pushes, 938 raw
written, 5500 deadband-skipped, ...`. `pushes` = device pushes received,
`raw written` = deadband-passing rows written to `readings`, `deadband-skipped`
= pushes within threshold that were not written.

`power-collector.device` lines report stream health: arm, connection open,
first push, and `no push in 6s; re-arming and reconnecting` (auto-recovery —
expected occasionally, and self-healing).

### As a runit service (Void Linux)

Staged unit lives in `~/services/power-telemetry/` (editable copy; `/etc/sv`
holds the installed copy). Install/enable:

```bash
sudo cp -r ~/services/power-telemetry /etc/sv/
sudo mkdir -p /var/log/power-telemetry && sudo chown aldn /var/log/power-telemetry
sudo ln -s /etc/sv/power-telemetry /var/service/   # enable (starts immediately)
```

Logs: `/var/log/power-telemetry/current`.

## Tools

```bash
./venv/bin/python scripts/scan.py          # discover Tuya devices on LAN
./venv/bin/python scripts/once.py          # one live sample
./venv/bin/python scripts/export_csv.py power --out power.csv
./venv/bin/python -m pytest tests/         # unit tests (DP scaling)
```

## Data layout (SQLite)

**`readings`** — raw 1 Hz rows, one per (timestamp, metric):

```sql
CREATE TABLE readings (
    ts     INTEGER NOT NULL,  -- Unix epoch seconds
    metric TEXT    NOT NULL,
    value  REAL    NOT NULL,
    unit   TEXT,
    PRIMARY KEY (ts, metric)
);
```

**`rollup_1min`** — compact permanent history (avg/min/max/samples per
completed minute per metric). Built automatically by the collector; survives
raw pruning:

```sql
CREATE TABLE rollup_1min (
    ts      INTEGER NOT NULL,  -- bucket start (floor(epoch/60)*60)
    metric  TEXT    NOT NULL,
    unit    TEXT,
    avg     REAL,
    min     REAL,
    max     REAL,
    samples INTEGER,
    PRIMARY KEY (ts, metric)
);
```

`energy` (cumulative Wh) is monotonic, so its rollup `max` is the exact
consumption total for that minute regardless of sample rate.

## Security notes

- The Local Key is a secret. Keep `.env` out of git (it is gitignored).
- The stock device firmware still phones Tuya's cloud on its own. To make it
  fully offline, block the device's IP from the internet **and** DNS at your
  router after the collector is confirmed working (blocking only internet
  without DNS can put the device in a zombie state).
- The Local Key changes if you remove and re-pair the device. Don't re-pair
  after setting this up.
