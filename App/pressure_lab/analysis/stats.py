"""Distribution-level statistics used for the force-proxy figures.

Deliberately dependency-light (numpy only, no scipy) since these are all
one-liners once you commit to a definition:

- ``ccdf``                  -> P(X >= x) on log-log axes, per group.
- ``exponential_tail_fit``  -> the dashed/solid exp(-F/F0) trend overlaid on the CCDF.
- ``quantile_quantile``     -> QQ plot comparing two distributions.
- ``delta_series`` / ``skewness_vs_dt`` -> increment distributions and
  their skewness as a function of the increment timescale.
"""

from __future__ import annotations

import numpy as np


def ccdf(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Empirical complementary CDF (survival function): P(X >= x).

    Returns ``(sorted_x, p)`` ready to plot directly (typically on log-log
    axes). Convention: for n sorted ascending samples, the i-th smallest
    (1-indexed) gets p = (n - i + 1) / n, so the largest sample has p = 1/n
    and nothing is ever exactly 0 (which log-log axes can't show anyway).
    """
    x_sorted = np.sort(np.asarray(x, dtype=float))
    n = x_sorted.size
    p = np.arange(n, 0, -1) / n
    return x_sorted, p


def exponential_tail_fit(
    x: np.ndarray, tail_quantile: float = 0.0
) -> tuple[float, float]:
    """Fit the CCDF tail to P(X >= x) ~= exp(intercept) * exp(-x / F0).

    ``tail_quantile`` (in [0, 1)) restricts the fit to the upper tail, e.g.
    0.5 fits only the top half of the distribution by value. Returns
    ``(F0, intercept)``; overlay with
    ``p_fit = np.exp(intercept) * np.exp(-x_sorted / F0)``.
    """
    x_sorted, p = ccdf(x)
    if tail_quantile > 0:
        cutoff = np.quantile(x_sorted, tail_quantile)
        mask = x_sorted >= cutoff
        x_sorted, p = x_sorted[mask], p[mask]

    slope, intercept = np.polyfit(x_sorted, np.log(p), 1)
    f0 = -1.0 / slope
    return f0, intercept


def quantile_quantile(
    x: np.ndarray, y: np.ndarray, n_quantiles: int = 99
) -> tuple[np.ndarray, np.ndarray]:
    """Matched-quantile pairs (qx, qy) for a QQ plot comparing two samples."""
    q = np.linspace(1.0 / (n_quantiles + 1), n_quantiles / (n_quantiles + 1), n_quantiles)
    qx = np.quantile(np.asarray(x, dtype=float), q)
    qy = np.quantile(np.asarray(y, dtype=float), q)
    return qx, qy


def delta_series(x: np.ndarray, lag: int) -> np.ndarray:
    """delta_x(t) = x(t + lag) - x(t), for a fixed sample lag."""
    x = np.asarray(x, dtype=float)
    if lag < 1:
        raise ValueError("lag must be >= 1 sample")
    return x[lag:] - x[:-lag]


def skewness(x: np.ndarray) -> float:
    """Fisher-Pearson (population) moment skewness: m3 / m2^1.5."""
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    mean = x.mean()
    m2 = np.mean((x - mean) ** 2)
    m3 = np.mean((x - mean) ** 3)
    if m2 == 0:
        return 0.0
    return m3 / m2**1.5


def skewness_vs_dt(
    x: np.ndarray, dt_values_s: np.ndarray, fs_hz: float
) -> tuple[np.ndarray, np.ndarray]:
    """Skewness of the increment distribution as a function of lag time.

    For each time increment in ``dt_values_s``, build delta_x over that lag
    (converted to samples via ``fs_hz``) and compute its skewness. Returns
    the actually-used dt values (snapped to the sampling grid) alongside
    the skewness values.
    """
    dt_values_s = np.asarray(dt_values_s, dtype=float)
    used_dt = np.empty_like(dt_values_s)
    skew_values = np.empty_like(dt_values_s)
    for i, dt in enumerate(dt_values_s):
        lag = max(1, int(round(dt * fs_hz)))
        used_dt[i] = lag / fs_hz
        skew_values[i] = skewness(delta_series(x, lag))
    return used_dt, skew_values
