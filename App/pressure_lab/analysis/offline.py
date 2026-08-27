"""Non-causal ("look ahead and behind") baseline + noise estimation.

This is the offline replacement for the firmware's on-device baseline
(``G0_mon`` / ``sigma_mon``), which is a *causal* exponential moving average:
it can only look at past samples, has a fixed memory budget (2KB RAM on an
Arduino UNO), and has to decide in real time. None of those constraints
apply once a recording is sitting on disk -- so here the baseline at each
point is estimated using a window *centered* on that point, using samples
from both before and after it.

Practical consequence: a centered window has no lag. The causal EMA always
trails a real, sustained change in the signal by roughly its time constant
(tau ~ 15s in the firmware); a centered window of the same width sees the
change coming and going symmetrically, so it settles on the new level about
twice as fast, with no systematic delay. See App/docs/METODOS.md for the
worked-out comparison and the bibliography behind this.

Both functions default to *robust* statistics (median / MAD-style mean
absolute deviation) rather than mean / standard deviation, for the same
reason the firmware avoids a plain standard deviation: one huge spike
shouldn't be able to distort the very estimate used to decide what counts
as a spike.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MAD_TO_SIGMA = 1.2533  # same Gaussian-equivalence factor the firmware uses


def seconds_to_samples(window_s: float, fs_hz: float) -> int:
    """Convert a window length in seconds to an odd number of samples
    (odd so a centered window has a well-defined middle sample)."""
    n = max(1, int(round(window_s * fs_hz)))
    return n if n % 2 == 1 else n + 1


def centered_baseline(x: np.ndarray, window_samples: int, robust: bool = True) -> np.ndarray:
    """Two-sided moving baseline over ``x``.

    ``robust=True`` (default) uses the rolling median, which -- like the
    firmware's event-freezing rule -- keeps a handful of large excursions
    inside the window from dragging the baseline toward them. ``robust=False``
    uses a plain rolling mean instead (faster, but sensitive to outliers).
    """
    s = pd.Series(np.asarray(x, dtype=float))
    if robust:
        b = s.rolling(window_samples, center=True, min_periods=1).median()
    else:
        b = s.rolling(window_samples, center=True, min_periods=1).mean()
    return b.to_numpy()


def centered_sigma(x: np.ndarray, baseline: np.ndarray, window_samples: int) -> np.ndarray:
    """Centered MAD-based noise sigma around a given baseline.

    Scaled by the same 1.2533 factor the firmware applies to its own
    ``sigma_mon``, so values from both methods are directly comparable.
    """
    resid = pd.Series(np.abs(np.asarray(x, dtype=float) - np.asarray(baseline, dtype=float)))
    mad = resid.rolling(window_samples, center=True, min_periods=1).mean()
    return (MAD_TO_SIGMA * mad).to_numpy()


def centered_baseline_robust(
    x: np.ndarray, window_samples: int, k: float = 4.0
) -> tuple[np.ndarray, np.ndarray]:
    """Centered baseline/sigma, refined to not absorb sustained events.

    ``centered_baseline`` alone is robust to a *few* extreme samples inside
    the window (the median ignores their magnitude), but not to an event
    that lasts long enough to occupy a large fraction of the window itself
    -- a real sustained "clog" wider than a few seconds can end up
    dragging even the median baseline toward it, which shrinks the
    residual (``x - baseline``) right where the event is and can hide it
    from event detection entirely. That's the offline equivalent of the
    firmware's problem it was trying to avoid in the first place (see
    App/docs/METODOS.md), just triggered by event *duration* instead of
    causal lag.

    Fix: two passes. The first pass gives a rough baseline/sigma good
    enough to flag which samples look anomalous. The second pass
    recomputes the rolling median with those flagged samples masked out
    (excluded from the window entirely, not just outvoted) -- so a
    sustained event no longer competes for a share of its own baseline,
    regardless of how long it lasts relative to the window.
    """
    x = np.asarray(x, dtype=float)
    baseline = centered_baseline(x, window_samples, robust=True)
    sigma = centered_sigma(x, baseline, window_samples)

    dx = x - baseline
    event_mask = (sigma > 0) & (np.abs(dx) > k * sigma)

    # Second pass: recompute both baseline AND sigma with event-flagged
    # samples excluded from every rolling window. Masking the baseline
    # alone isn't enough -- sigma is a rolling average of |residual|, and
    # an event's own (now large) residual sitting inside its own sigma
    # window inflates the very threshold meant to catch it.
    masked_x = pd.Series(np.where(event_mask, np.nan, x))
    refined = masked_x.rolling(window_samples, center=True, min_periods=1).median()
    refined = refined.ffill().bfill()  # only triggers if an entire window is masked out
    refined_arr = refined.to_numpy()

    refined_dx = x - refined_arr
    masked_abs_resid = pd.Series(np.where(event_mask, np.nan, np.abs(refined_dx)))
    mad = masked_abs_resid.rolling(window_samples, center=True, min_periods=1).mean()
    mad = mad.ffill().bfill()
    refined_sigma = (MAD_TO_SIGMA * mad).to_numpy()

    return refined_arr, refined_sigma


def activity_envelope(dx: np.ndarray, window_samples: int) -> np.ndarray:
    """Smoothed |dx| -- kills sample-to-sample noise while preserving the
    shape of a real multi-second excursion.

    Why this exists: a real sustained "clog" in this data isn't a clean
    flat plateau, it's itself noisy (the sensor keeps jittering a few uS
    up and down *while* the overall level is elevated). Thresholding each
    raw sample individually against sigma catches only the noisiest
    instants of the excursion and fragments a single ~10-40s event into
    many isolated sub-second flags, none of which reach a "clog" duration.
    Smoothing first (short window relative to the excursion, long relative
    to sample noise) turns the excursion into one continuous rise-and-fall
    that a threshold can actually segment as one event. Use this, not the
    raw signal, as the input to event detection for burst/clog
    segmentation; keep using the raw signal for CCDF/histogram statistics,
    where the point-to-point fluctuation itself is the thing being
    measured.
    """
    return (
        pd.Series(np.abs(np.asarray(dx, dtype=float)))
        .rolling(window_samples, center=True, min_periods=1)
        .mean()
        .to_numpy()
    )
