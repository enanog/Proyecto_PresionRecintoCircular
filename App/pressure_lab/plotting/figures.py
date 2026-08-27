"""Figure-generating functions mirroring the paper's Fig. 3 and Fig. 4 panels.

Every function takes/returns a matplotlib ``Axes`` (or ``Figure`` for the
multi-panel grids) instead of saving files itself, so panels can be
composed, tweaked, and re-run from a notebook or script without touching
this module -- see ``App/scripts`` for end-to-end examples.
"""

from __future__ import annotations

import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from pressure_lab.analysis.stats import (
    ccdf,
    exponential_tail_fit,
    quantile_quantile,
    skewness_vs_dt,
)
from pressure_lab.plotting.style import TREND_LINE_COLOR, color_by_key


def plot_ccdf_by_group(
    ax: Axes,
    series_by_key: dict,
    xlabel: str = "F (g)",
    ylabel: str = r"$P(F \geq f)$",
    fit_trend: bool = True,
    tail_quantile: float = 0.5,
) -> Axes:
    """Fig. 3(a)-style panel: log-log CCDF, one curve per group key (e.g. N_bots).

    ``series_by_key`` maps a legend key (e.g. an int N_bots, or any sortable
    label) to a 1D array of force samples. Colors follow ``color_by_key``
    (ascending, sequential). If ``fit_trend``, overlays a single dashed
    exp(-F/F0) trend fit to the *pooled* samples' tail, matching the paper's
    black reference line.
    """
    colors = color_by_key(list(series_by_key.keys()))
    pooled = []

    for key in sorted(series_by_key, key=lambda k: (k is None, k)):
        x = np.asarray(series_by_key[key], dtype=float)
        x = x[np.isfinite(x)]
        if x.size == 0:
            continue
        x_sorted, p = ccdf(x)
        label = "vacío" if key is None else str(key)
        ax.plot(x_sorted, p, marker="o", ms=2, ls="none", color=colors[key], label=label)
        pooled.append(x)

    if fit_trend and pooled:
        all_x = np.concatenate(pooled)
        f0, intercept = exponential_tail_fit(all_x, tail_quantile=tail_quantile)
        x_line = np.linspace(all_x.min(), all_x.max(), 200)
        p_line = np.exp(intercept) * np.exp(-x_line / f0)
        ax.plot(x_line, p_line, "-", color=TREND_LINE_COLOR, lw=1.5, label=rf"$e^{{-F/F_0}}$, $F_0$={f0:.3g}")

    ax.set_yscale("log")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.legend(fontsize=8, title="$N_{tot}$")
    return ax


def plot_quantile_quantile(
    ax: Axes,
    x: np.ndarray,
    y: np.ndarray,
    xlabel: str = "$f_b$ quantiles",
    ylabel: str = "$f_c$ quantiles",
    n_quantiles: int = 99,
) -> Axes:
    """Fig. 3(d)-style panel: matched quantiles of two distributions plus y=x."""
    qx, qy = quantile_quantile(x, y, n_quantiles=n_quantiles)
    lo, hi = min(qx.min(), qy.min()), max(qx.max(), qy.max())
    ax.plot([lo, hi], [lo, hi], "--", color="gray", lw=1, label="y = x")
    ax.plot(qx, qy, "o", ms=3, color=TREND_LINE_COLOR)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.legend(fontsize=8)
    return ax


def plot_delta_histogram(
    ax: Axes,
    delta_x: np.ndarray,
    n_bins: int = 60,
    xlabel: str = r"$\delta f$ (kg)",
    ylabel: str = "frequency count",
    title: str | None = None,
    color=None,
) -> Axes:
    """Fig. 4(a)-(d)-style panel: semilog-y histogram of an increment distribution."""
    delta_x = np.asarray(delta_x, dtype=float)
    delta_x = delta_x[np.isfinite(delta_x)]
    ax.hist(delta_x, bins=n_bins, color=color, edgecolor="black", linewidth=0.3)
    ax.set_yscale("log")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title, fontsize=10)
    return ax


def plot_delta_histogram_grid(
    fig: Figure,
    delta_by_key: dict,
    n_bins: int = 60,
    xlabel: str = r"$\delta f$ (kg)",
) -> Figure:
    """Grid of ``plot_delta_histogram`` panels, one subplot per group key."""
    keys = sorted(delta_by_key, key=lambda k: (k is None, k))
    colors = color_by_key(keys)
    n = len(keys)
    ncols = min(n, 2) or 1
    nrows = int(np.ceil(n / ncols)) if n else 1
    axes = fig.subplots(
        nrows, ncols, squeeze=False, gridspec_kw={"hspace": 0.6, "wspace": 0.3}
    ).flatten()

    for ax, key in zip(axes, keys):
        title = "vacío" if key is None else f"$N_{{tot}}$ = {key}"
        plot_delta_histogram(ax, delta_by_key[key], n_bins=n_bins, xlabel=xlabel, title=title, color=colors[key])
    for ax in axes[n:]:
        ax.axis("off")

    return fig


def plot_skewness_vs_dt(
    ax: Axes,
    x: np.ndarray,
    dt_values_s: np.ndarray,
    fs_hz: float,
    label: str | None = None,
    color=None,
) -> Axes:
    """Fig. 4(e)-style panel: skewness of delta_f distribution vs. lag time."""
    used_dt, skew_values = skewness_vs_dt(x, dt_values_s, fs_hz)
    ax.plot(used_dt, skew_values, "-o", ms=3, color=color, label=label)
    ax.axhline(0, color="gray", lw=0.8, ls=":")
    ax.set_xlabel(r"$\delta t$ (s)")
    ax.set_ylabel("skewness")
    if label:
        ax.legend(fontsize=8)
    return ax
