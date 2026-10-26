"""Unit tests for DP scaling. Run: python -m unittest tests.test_dpmap -v
or: python tests/test_dpmap.py"""

import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collector import dpmap


class TestScaling(unittest.TestCase):
    def test_scaling_power(self):
        self.assertEqual(dpmap.scale(19, 44367), 443.67)  # /100

    def test_scaling_voltage(self):
        self.assertEqual(dpmap.scale(20, 22776), 227.76)  # /100

    def test_scaling_current(self):
        self.assertEqual(dpmap.scale(18, 1987), 1.987)  # /1000

    def test_scaling_frequency(self):
        self.assertEqual(dpmap.scale(133, 5000), 50.00)  # /100

    def test_scaling_power_factor(self):
        self.assertEqual(dpmap.scale(134, 98), 0.98)  # /100

    def test_energy_is_wh(self):
        self.assertEqual(dpmap.scale(123, 10886), 10886)  # x1 Wh

    def test_none_passthrough(self):
        self.assertIsNone(dpmap.scale(19, None))

    def test_unknown_dp_passthrough(self):
        self.assertEqual(dpmap.scale(999, 42), 42)

    def test_metric_names(self):
        self.assertEqual(dpmap.metric_name(19), "power")
        self.assertEqual(dpmap.metric_name(123), "energy")
        self.assertEqual(dpmap.metric_name(999), "dp999")

    def test_units(self):
        self.assertEqual(dpmap.unit(19), "W")
        self.assertEqual(dpmap.unit(18), "A")
        self.assertEqual(dpmap.unit(20), "V")
        self.assertEqual(dpmap.unit(123), "Wh")
        self.assertEqual(dpmap.unit(999), "")

    def test_string_keys_normalized(self):
        # receive() push path yields str keys; scale/name/unit must handle them
        self.assertEqual(dpmap.scale("19", 44367), 443.67)
        self.assertEqual(dpmap.metric_name("19"), "power")
        self.assertEqual(dpmap.unit("123"), "Wh")


if __name__ == "__main__":
    unittest.main(verbosity=2)
