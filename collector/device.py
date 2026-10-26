"""
Low-level reader for the Atorch S1BW over Tuya protocol 3.5.

The device does NOT answer one-shot status() queries with live values.
Instead, once the real-time reporting toggle (dp 140) is armed True, it PUSHES
an update roughly once per second on an established persistent connection.

This module encapsulates that: arm the toggle, open a persistent socket, and
yield each pushed datapoint dict {dp_id: raw_value}.
"""

import logging
import time
import tinytuya

from .dpmap import REALTIME_TOGGLE_DP

log = logging.getLogger("power-collector.device")

DEFAULT_VER = 3.5

# If no push arrives within this long after arming, the arm likely didn't take.
# The device intermittently needs the toggle re-sent or a reconnect.
ARM_RETRY_WINDOW = 6.0


class S1EnergySocket:
    """Reads live metrics from an Atorch S1BW over the local Tuya protocol."""

    def __init__(self, device_id, device_ip, local_key, version=DEFAULT_VER):
        self.device_id = device_id
        self.device_ip = device_ip
        self.local_key = local_key
        self.version = version

    def _arm_realtime(self):
        """Set the real-time reporting toggle on. Uses the standard Device
        class (which can write); the stream is read via XenonDevice."""
        arm = tinytuya.Device(
            self.device_id, self.device_ip, self.local_key, version=self.version
        )
        arm.set_socketTimeout(5)
        log.info("arming real-time toggle (dp %s = True)", REALTIME_TOGGLE_DP)
        arm.set_value(REALTIME_TOGGLE_DP, True)
        time.sleep(2)
        try:
            arm.close()
        except Exception as exc:
            log.debug("arm close: %s", exc)

    def _open_stream(self):
        """Open a persistent XenonDevice connection and register interest."""
        rd = tinytuya.XenonDevice(
            self.device_id, self.device_ip, self.local_key, version=self.version
        )
        rd.set_socketTimeout(3)
        rd.set_socketPersistent(True)
        try:
            rd.status()
        except Exception:
            pass
        return rd

    def stream(self, duration=None, interval=0.4):
        """
        Arm real-time reporting and yield (timestamp, dps_dict) for each pushed
        update. Retries the arm + reconnect if no push arrives within a short
        window (the device intermittently needs the toggle re-sent).

        Args:
            duration: stop after this many seconds (None = run forever).
            interval: poll interval for the socket receive in seconds.
        """
        self._arm_realtime()
        rd = self._open_stream()
        log.info("stream open on %s:%s", self.device_ip, 6668)

        t0 = time.time()
        last_push = time.time()
        got_any = False
        while True:
            if duration is not None and (time.time() - t0) > duration:
                break
            try:
                data = rd.receive()
                if data and "dps" in data and data.get("dps"):
                    if not got_any:
                        log.info("first push received; streaming")
                    got_any = True
                    last_push = time.time()
                    # Normalize DP keys to int so consumers can rely on them.
                    dps = {int(k): v for k, v in data["dps"].items()}
                    yield time.time(), dps
            except Exception as exc:
                log.warning("receive error: %s: %s", type(exc).__name__, exc)

            # If we armed but got nothing for a while, re-arm and reconnect.
            if (time.time() - last_push) > ARM_RETRY_WINDOW:
                log.warning("no push in %.0fs; re-arming and reconnecting",
                            ARM_RETRY_WINDOW)
                try:
                    rd.close()
                except Exception as exc:
                    log.debug("close on retry: %s", exc)
                self._arm_realtime()
                rd = self._open_stream()
                last_push = time.time()

            time.sleep(interval)

        try:
            rd.close()
        except Exception:
            pass


def poll_once(device_id, device_ip, local_key, window=15.0):
    """
    Convenience: arm, stream for `window` seconds, and return a dict of the
    latest value per metric (merged from all pushes in the window).
    Returns None if no data was received.
    """
    sock = S1EnergySocket(device_id, device_ip, local_key)
    merged = {}
    for _ts, dps in sock.stream(duration=window):
        merged.update(dps)
    return merged or None
