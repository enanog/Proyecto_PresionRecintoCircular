"""Sanity checks for pressure_lab.analysis.stats. No pytest dependency:

    python -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from pressure_lab.analysis.stats import (
    ccdf,
    delta_series,
    quantile_quantile,
    skewness,
    skewness_vs_dt,
)


class TestCcdf(unittest.TestCase):
    def test_monotonic_nonincreasing(self):
        x = np.random.default_rng(0).exponential(size=500)
        _, p = ccdf(x)
        self.assertTrue(np.all(np.diff(p) <= 0))

    def test_bounds(self):
        x = np.arange(1, 11)
        x_sorted, p = ccdf(x)
        self.assertAlmostEqual(p[0], 1.0)
        self.assertAlmostEqual(p[-1], 1.0 / len(x))
        np.testing.assert_array_equal(x_sorted, x)


class TestSkewness(unittest.TestCase):
    def test_symmetric_distribution_near_zero(self):
        x = np.random.default_rng(1).normal(size=20000)
        self.assertAlmostEqual(skewness(x), 0.0, delta=0.05)

    def test_right_skewed_positive(self):
        x = np.random.default_rng(2).exponential(size=20000)
        self.assertGreater(skewness(x), 0.5)

    def test_constant_series_is_zero(self):
        self.assertEqual(skewness(np.ones(10)), 0.0)


class TestDeltaSeries(unittest.TestCase):
    def test_shape_and_values(self):
        x = np.array([0.0, 1.0, 3.0, 6.0])
        d = delta_series(x, lag=1)
        np.testing.assert_array_equal(d, [1.0, 2.0, 3.0])

    def test_rejects_bad_lag(self):
        with self.assertRaises(ValueError):
            delta_series(np.arange(5), lag=0)


class TestSkewnessVsDt(unittest.TestCase):
    def test_output_lengths_match_input(self):
        x = np.random.default_rng(3).normal(size=1000)
        dt_values = np.array([0.5, 1.0, 2.0])
        used_dt, skew_values = skewness_vs_dt(x, dt_values, fs_hz=20.0)
        self.assertEqual(len(used_dt), 3)
        self.assertEqual(len(skew_values), 3)


class TestQuantileQuantile(unittest.TestCase):
    def test_identical_distributions_fall_on_y_equals_x(self):
        rng = np.random.default_rng(4)
        x = rng.normal(size=5000)
        qx, qy = quantile_quantile(x, x, n_quantiles=50)
        np.testing.assert_array_almost_equal(qx, qy)


if __name__ == "__main__":
    unittest.main()
