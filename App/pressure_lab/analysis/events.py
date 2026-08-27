"""Event/segment detection on a force-proxy time series.

Two regimes worth telling apart in the force signal: abrupt pressure
*bursts* (a brief, sharp jump that relaxes quickly) and *clogs* (force
stays elevated for a while, e.g. a stable arch forming). Neither label
comes with the measurement -- it has to be derived from the signal. The
approach here is intentionally simple and fully exposed as parameters so
it can be tuned against real data:

1. Flag samples where the signal deviates from its slow baseline by more
   than ``k`` local-noise-sigmas (same rule the firmware already applies
   on-device for ``sigma_mon`` -- see ``detect_spikes``).
2. Group consecutive flagged samples into segments.
3. A segment shorter than ``min_clog_duration_s`` is a *burst*; longer, and
   the elevated force is sustained, so it's called a *clog*.

Treat this as a starting point to iterate on, not a validated algorithm.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def rolling_baseline_sigma(
    x: np.ndarray,
    alpha_base: float = 0.0033,
    alpha_dev: float = 0.0100,
    freeze_k: float = 4.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Re-derive an adaptive baseline + MAD-based sigma from raw samples.

    Reimplements the same exponential-moving-average scheme the firmware
    runs on-device (see ``gBase`` / ``madG`` in fsr_single_read.ino), so it
    can be recomputed post-hoc with different ``alpha`` time constants than
    whatever produced the logged ``G0_mon`` / ``sigma_mon`` columns.
    Baseline and deviation estimators freeze while a sample looks like an
    event, so genuine transients don't leak into the reference.
    """
    x = np.asarray(x, dtype=float)
    n = x.size
    base = np.empty(n)
    mad = np.empty(n)
    sigma = np.empty(n)

    base[0] = x[0]
    mad[0] = 0.0
    sigma[0] = 0.0
    for i in range(1, n):
        d = x[i] - base[i - 1]
        s = 1.2533 * mad[i - 1]
        is_event = s > 0 and abs(d) > freeze_k * s
        if is_event:
            base[i] = base[i - 1]
            mad[i] = mad[i - 1]
        else:
            base[i] = base[i - 1] + alpha_base * d
            mad[i] = mad[i - 1] + alpha_dev * (abs(d) - mad[i - 1])
        sigma[i] = 1.2533 * mad[i]

    return base, sigma


def detect_spikes(dx: np.ndarray, sigma: np.ndarray, k: float = 4.0) -> np.ndarray:
    """Boolean mask of samples where |dx| > k * sigma (sigma > 0 required)."""
    dx = np.asarray(dx, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    return (sigma > 0) & (np.abs(dx) > k * sigma)


@dataclass(frozen=True)
class Segment:
    start_s: float
    end_s: float
    duration_s: float
    peak: float
    kind: str  # "burst" | "clog"


def segment_bursts_and_clogs(
    t_s: np.ndarray,
    x: np.ndarray,
    event_mask: np.ndarray,
    min_clog_duration_s: float = 1.0,
) -> pd.DataFrame:
    """Group contiguous flagged samples into burst/clog segments.

    Returns a DataFrame with columns ``start_s, end_s, duration_s, peak,
    kind``, one row per contiguous run of ``event_mask``. ``peak`` is the
    signed sample of largest magnitude within the segment.
    """
    t_s = np.asarray(t_s, dtype=float)
    x = np.asarray(x, dtype=float)
    mask = np.asarray(event_mask, dtype=bool)

    if not mask.any():
        return pd.DataFrame(columns=["start_s", "end_s", "duration_s", "peak", "kind"])

    edges = np.diff(mask.astype(int))
    starts = np.where(edges == 1)[0] + 1
    ends = np.where(edges == -1)[0] + 1
    if mask[0]:
        starts = np.r_[0, starts]
    if mask[-1]:
        ends = np.r_[ends, mask.size]

    segments: list[Segment] = []
    for s, e in zip(starts, ends):
        chunk = x[s:e]
        peak = chunk[np.argmax(np.abs(chunk))]
        start_s, end_s = t_s[s], t_s[e - 1]
        duration = end_s - start_s
        kind = "clog" if duration >= min_clog_duration_s else "burst"
        segments.append(Segment(start_s, end_s, duration, float(peak), kind))

    return pd.DataFrame(segments)
