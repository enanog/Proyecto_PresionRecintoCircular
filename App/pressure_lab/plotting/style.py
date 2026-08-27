"""Shared matplotlib styling: paper-like typography plus a sequential palette.

Bot/particle counts (N) are an ordered magnitude, exactly like the paper's
own legend (30/40/45/50) -- so series get colors from a single perceptually
uniform ramp (``viridis``) sampled light-to-dark by ascending N, never a
categorical/rainbow cycle. This is also what the source figure itself uses.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

TREND_LINE_COLOR = "black"


def apply_paper_style() -> None:
    """Call once (e.g. at the top of a script) to set global rcParams."""
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.size": 11,
            "axes.linewidth": 1.0,
            "axes.grid": False,
            "xtick.direction": "in",
            "ytick.direction": "in",
            "xtick.top": True,
            "ytick.right": True,
            "legend.frameon": False,
            "figure.dpi": 120,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
        }
    )


def sequential_palette(n: int, cmap_name: str = "viridis") -> list:
    """n colors from a single perceptually uniform ramp, ordered for an
    ascending magnitude variable (e.g. N_bots). Returns a list of RGBA tuples.
    """
    if n <= 0:
        return []
    if n == 1:
        return [plt.get_cmap(cmap_name)(0.85)]
    cmap = plt.get_cmap(cmap_name)
    return [cmap(x) for x in np.linspace(0.05, 0.90, n)]


def color_by_key(keys: list, cmap_name: str = "viridis") -> dict:
    """Assign a fixed sequential color to each key, keys sorted ascending.

    ``None`` (e.g. an undetermined N_bots) always sorts first and gets a
    neutral gray instead of a ramp color, since it isn't part of the ordered
    sequence.
    """
    sortable = sorted((k for k in keys if k is not None))
    palette = sequential_palette(len(sortable), cmap_name)
    mapping = dict(zip(sortable, palette))
    if any(k is None for k in keys):
        mapping[None] = (0.5, 0.5, 0.5, 1.0)
    return mapping
