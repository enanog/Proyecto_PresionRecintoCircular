"""Minimal end-to-end example: load one measurement, plot the raw signal
and a single CCDF. Run this first to sanity-check the pipeline before
touching scripts/make_figures.py.

Usage:
    python scripts/quickstart.py
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  (must run before pressure_lab imports)

import matplotlib.pyplot as plt

from pressure_lab.analysis.pipeline import prepare_force_proxy
from pressure_lab.analysis.stats import ccdf
from pressure_lab.config import MEDICIONES_DIR, OUTPUT_DIR
from pressure_lab.io.loader import discover_measurements
from pressure_lab.plotting.style import apply_paper_style


def main() -> None:
    apply_paper_style()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    measurements = discover_measurements(MEDICIONES_DIR)
    if not measurements:
        raise SystemExit(f"No measurement files found under {MEDICIONES_DIR}")

    m = measurements[0]
    print(f"Loading {m.label} (session {m.session}, n_bots={m.n_bots})")
    df = m.load()
    df = prepare_force_proxy(df)
    print(df.head())
    print(f"{len(df)} samples, {df['t_s'].iloc[-1]:.1f} s")

    dg = df["dG_offline"]

    fig, (ax_ts, ax_ccdf) = plt.subplots(1, 2, figsize=(9, 3.5))

    ax_ts.plot(df["t_s"], dg, lw=0.5)
    ax_ts.set_xlabel("t (s)")
    ax_ts.set_ylabel(r"$\delta G = G - G_{baseline}$ (uS)")
    ax_ts.set_title(m.label)

    x_sorted, p = ccdf(dg.abs().to_numpy())
    ax_ccdf.plot(x_sorted, p, ".", ms=3)
    ax_ccdf.set_yscale("log")
    ax_ccdf.set_xlabel(r"$|\delta G|$ (uS, uncalibrated force proxy)")
    ax_ccdf.set_ylabel(r"$P(|\delta G| \geq x)$")

    fig.tight_layout()
    out_path = OUTPUT_DIR / "quickstart.png"
    fig.savefig(out_path)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
