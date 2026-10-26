"""Unit tests for the collector's rollup buffer and deadband tracker.
Run: python -m unittest tests.test_run -v
or: python tests/test_run.py"""

import sys, os, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collector.run import MinuteBuffer, DeadbandTracker


class TestMinuteBuffer(unittest.TestCase):
    def test_rolls_completed_minute_only(self):
        buf = MinuteBuffer(bucket=60)
        now = int(time.time())
        prev = (now // 60 - 1) * 60
        for i in range(60):
            buf.add(prev + i, "power", 100.0 + i, "W")
        # current in-progress minute must NOT be rolled yet
        cur = (now // 60) * 60
        buf.add(cur + 1, "power", 500.0, "W")

        rows = buf.pop_completed(now)
        self.assertEqual(len(rows), 1)
        ts, metric, avg, mn, mx, n, unit = rows[0]
        self.assertEqual(ts, prev)
        self.assertEqual(metric, "power")
        self.assertAlmostEqual(avg, 129.5)   # unbiased avg of all 60 samples
        self.assertEqual(mn, 100)
        self.assertEqual(mx, 159)
        self.assertEqual(n, 60)
        self.assertEqual(unit, "W")

    def test_avg_unbiased_across_buckets(self):
        buf = MinuteBuffer(bucket=60)
        now = int(time.time())
        prev = (now // 60 - 1) * 60
        for i in range(30):
            buf.add(prev + i, "current", 1.0, "A")       # steady 1.0
            buf.add(prev + i, "current", 2.0, "A")       # spike to 2.0
        rows = buf.pop_completed(now)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0][2], 1.5)          # avg of 30×1.0+30×2.0


class TestDeadbandTracker(unittest.TestCase):
    def setUp(self):
        self.db = DeadbandTracker({"power": 5.0, "voltage": 2.0}, heartbeat=60)

    def test_first_sample_writes(self):
        self.assertTrue(self.db.should_write("power", 100.0, 1000))

    def test_within_deadband_skips(self):
        self.db.should_write("power", 100.0, 1000)
        self.db.note_write("power", 100.0, 1000)
        self.assertFalse(self.db.should_write("power", 102.0, 1001))

    def test_threshold_triggers(self):
        self.db.should_write("power", 100.0, 1000)
        self.db.note_write("power", 100.0, 1000)
        self.assertTrue(self.db.should_write("power", 106.0, 1002))

    def test_heartbeat_force_writes(self):
        self.db.should_write("power", 100.0, 1000)
        self.db.note_write("power", 100.0, 1000)
        self.assertFalse(self.db.should_write("power", 100.5, 1050))
        self.assertTrue(self.db.should_write("power", 100.5, 1060))  # 60s later


if __name__ == "__main__":
    unittest.main()
