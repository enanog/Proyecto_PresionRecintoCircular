"""Single entry point that turns a raw loaded measurement into the force-proxy
signal every plot/analysis function actually consumes.

Centralizing this means the rest of the codebase (scripts, notebooks) never
has to know whether a given file came from a firmware revision that logged
its own on-device ``G0_mon`` / ``sigma_mon``, or one that only logs
``adc_raw`` and leaves baseline/noise estimation entirely to Python --
``prepare_force_proxy`` derives whatever is missing and always hands back
the same set of columns, for any number of files from any mix of firmware
revisions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pressure_lab.analysis.offline import (
    activity_envelope,
    centered_baseline,
    centered_baseline_robust,
    centered_sigma,
    seconds_to_samples,
)
from pressure_lab.calibration.convert import ensure_conductance_uS
from pressure_lab.config import DEFAULT_FRONTEND, FrontEndParams


def estimate_fs_hz(t_s: np.ndarray) -> float:
    return 1.0 / np.median(np.diff(np.asarray(t_s, dtype=float)))


def prepare_force_proxy(
    df: pd.DataFrame,
    params: FrontEndParams = DEFAULT_FRONTEND,
    baseline_window_s: float = 60.0,
    envelope_window_s: float = 1.5,
    event_k: float = 4.0,
) -> pd.DataFrame:
    """Return a copy of ``df`` with the columns every plot/analysis function
    consumes: ``G_uS``, ``baseline_offline``, ``sigma_offline``,
    ``dG_offline``, ``envelope_offline``, ``envelope_baseline``,
    ``envelope_sigma``.

    This is the offline, centered/non-causal baseline from
    ``pressure_lab.analysis.offline`` -- the one meant to actually be used
    for analysis. Any ``G0_mon`` / ``sigma_mon`` columns from an
    older-firmware recording are left untouched (still there for
    comparison, e.g. in ``scripts/compare_baselines.py``) but are no longer
    what the rest of the pipeline reads.

    Two different signals for two different jobs:

    - ``dG_offline`` (raw, one value per sample) is what CCDF / histogram /
      skewness statistics should use -- the point-to-point fluctuation
      *is* the thing being measured there.
    - ``envelope_offline`` (``dG_offline`` smoothed over ``envelope_window_s``)
      is what burst/clog *segmentation* should use. A real sustained event
      in this data is itself noisy -- thresholding raw samples against
      sigma fragments one ~10-40s excursion into many isolated sub-second
      flags. Smoothing first turns it into one continuous rise-and-fall
      a duration threshold can actually segment. ``envelope_baseline`` /
      ``envelope_sigma`` are the background level and noise of that
      smoothed envelope (same centered/robust machinery, applied to the
      envelope instead of to G directly).

    ``baseline_window_s`` needs to be comfortably wider than the longest
    real event you expect -- otherwise the centered median baseline starts
    tracking *through* a sustained event instead of around it. See
    App/docs/METODOS.md for the full reasoning and the numbers that led to
    these defaults.
    """
    df = ensure_conductance_uS(df, params)
    fs_hz = estimate_fs_hz(df["t_s"].to_numpy())
    window_samples = seconds_to_samples(baseline_window_s, fs_hz)
    envelope_samples = seconds_to_samples(envelope_window_s, fs_hz)

    g = df["G_uS"].to_numpy()
    baseline, sigma = centered_baseline_robust(g, window_samples, k=event_k)
    dg = g - baseline

    envelope = activity_envelope(dg, envelope_samples)
    envelope_baseline = centered_baseline(envelope, window_samples, robust=True)
    envelope_sigma = centered_sigma(envelope, envelope_baseline, window_samples)

    df = df.copy()
    df["baseline_offline"] = baseline
    df["sigma_offline"] = sigma
    df["dG_offline"] = dg
    df["envelope_offline"] = envelope
    df["envelope_baseline"] = envelope_baseline
    df["envelope_sigma"] = envelope_sigma
    return df
