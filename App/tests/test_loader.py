"""Sanity checks for pressure_lab.io.loader against real files under Mediciones/."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pressure_lab.config import MEDICIONES_DIR
from pressure_lab.io.loader import discover_measurements


@unittest.skipUnless(MEDICIONES_DIR.exists(), "Mediciones/ not present in this checkout")
class TestDiscovery(unittest.TestCase):
    def test_finds_measurements_and_parses_n_bots(self):
        measurements = discover_measurements(MEDICIONES_DIR)
        self.assertGreater(len(measurements), 0)
        labeled = [m for m in measurements if m.n_bots is not None]
        baseline = [m for m in measurements if m.is_baseline]
        self.assertTrue(labeled, "expected at least one 'N Robots' file")
        self.assertTrue(baseline, "expected at least one 'Vacio' baseline file")

    def test_load_first_measurement_has_expected_columns(self):
        m = discover_measurements(MEDICIONES_DIR)[0]
        df = m.load()
        for col in ("adc_raw", "R_ohm", "G_uS", "G0_mon", "sigma_mon", "t_s"):
            self.assertIn(col, df.columns)
        self.assertGreater(len(df), 0)
        # t_s should start at 0 and be monotonically nondecreasing
        self.assertEqual(df["t_s"].iloc[0], 0.0)
        self.assertTrue((df["t_s"].diff().dropna() >= 0).all())


if __name__ == "__main__":
    unittest.main()
