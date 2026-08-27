"""Generate the paper-style figures from every measurement under Mediciones/,
one plot per file (not bundled into multi-panel composites).

Usage:
    python scripts/make_figures.py [--mediciones PATH] [--out PATH]

Produces, in the output directory:
    ccdf_forces_by_n.png       - CCDF of |dG| by N_bots, with exponential tail fit.
    ccdf_bursts_vs_clogs.png   - CCDF of peak forces, bursts vs. clogs.
    qq_bursts_vs_clogs.png     - quantile-quantile plot of the same two.
    delta_hist_<group>.png     - one histogram of delta-f per N_bots group.
    skewness_vs_dt.png         - skewness of delta-f vs. increment time, all groups.

The underlying signal is uncalibrated (dG_offline = G_uS - baseline_offline,
in microsiemens, from the *offline* centered baseline in
pressure_lab.analysis.pipeline -- not the on-device G0_mon) -- see
pressure_lab/calibration for converting to real force units once a
calibration curve exists, and App/docs/METODOS.md for why the baseline is
recomputed here instead of trusting the logged one, and why burst/clog
segmentation runs on a smoothed activity envelope instead of the raw
per-sample signal.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import _bootstrap  # noqa: F401

import matplotlib.pyplot as plt
import numpy as np

from pressure_lab.analysis.events import detect_spikes, segment_bursts_and_clogs
from pressure_lab.analysis.pipeline import prepare_force_proxy
from pressure_lab.analysis.stats import delta_series
from pressure_lab.config import MEDICIONES_DIR, OUTPUT_DIR
from pressure_lab.io.loader import discover_measurements, load_measurement
from pressure_lab.plotting.figures import (
    plot_ccdf_by_group,
    plot_delta_histogram,
    plot_quantile_quantile,
    plot_skewness_vs_dt,
)
from pressure_lab.plotting.style import apply_paper_style, color_by_key

SPIKE_K = 4.0  # event threshold, in local-noise sigmas, applied to the activity envelope
MIN_CLOG_DURATION_S = 1.0  # segments shorter than this are "bursts"
DELTA_HIST_DT_S = 2.5  # matches the paper's Fig. 4 caption
SKEW_DT_VALUES_S = np.arange(0.25, 15.0, 0.5)


def group_label(key) -> str:
    return "vacío" if key is None else f"$N_{{tot}}$={key}"


def group_filename(key) -> str:
    return "vacio" if key is None else f"N{key}"


def analyze_measurement(path: Path) -> dict:
    """Load one file and derive everything the figures need from it."""
    df = load_measurement(path)
    df = prepare_force_proxy(df)
    dg = df["dG_offline"].to_numpy()
    t_s = df["t_s"].to_numpy()
    fs_hz = 1.0 / np.median(np.diff(t_s))

    # Burst/clog segmentation runs on the smoothed activity envelope, not
    # the raw signal: a real sustained event here is itself noisy, so a
    # per-sample threshold fragments it into sub-second pieces that never
    # reach MIN_CLOG_DURATION_S. See prepare_force_proxy's docstring.
    env = df["envelope_offline"].to_numpy()
    env_base = df["envelope_baseline"].to_numpy()
    env_sigma = df["envelope_sigma"].to_numpy()
    mask = detect_spikes(env - env_base, env_sigma, k=SPIKE_K)
    segments = segment_bursts_and_clogs(t_s, dg, mask, min_clog_duration_s=MIN_CLOG_DURATION_S)

    return {"dg": dg, "t_s": t_s, "fs_hz": fs_hz, "segments": segments}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mediciones", type=Path, default=MEDICIONES_DIR)
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    apply_paper_style()
    args.out.mkdir(parents=True, exist_ok=True)

    measurements = discover_measurements(args.mediciones)
    if not measurements:
        raise SystemExit(f"No measurement files found under {args.mediciones}")

    forces_by_group: dict = {}
    fb_all: list = []
    fc_all: list = []
    delta_by_group: dict = {}
    skew_series_by_group: dict = {}
    fs_by_group: dict = {}

    for m in measurements:
        key = m.n_bots  # None for the "Vacio" baseline run
        print(f"Analyzing {m.label} (n_bots={key}) ...")
        result = analyze_measurement(m.path)

        forces_by_group.setdefault(key, []).append(np.abs(result["dg"]))

        segs = result["segments"]
        if not segs.empty:
            fb_all.append(segs.loc[segs["kind"] == "burst", "peak"].abs().to_numpy())
            fc_all.append(segs.loc[segs["kind"] == "clog", "peak"].abs().to_numpy())
        n_burst = int((segs["kind"] == "burst").sum()) if not segs.empty else 0
        n_clog = int((segs["kind"] == "clog").sum()) if not segs.empty else 0
        print(f"  -> {n_burst} bursts, {n_clog} clogs")

        lag = max(1, int(round(DELTA_HIST_DT_S * result["fs_hz"])))
        delta_by_group.setdefault(key, []).append(delta_series(result["dg"], lag))

        # keep one representative full dG series per group for the skewness panel
        if key not in skew_series_by_group:
            skew_series_by_group[key] = result["dg"]
            fs_by_group[key] = result["fs_hz"]

    forces_by_group = {k: np.concatenate(v) for k, v in forces_by_group.items()}
    delta_by_group = {k: np.concatenate(v) for k, v in delta_by_group.items()}
    fb_all = np.concatenate(fb_all) if fb_all else np.array([])
    fc_all = np.concatenate(fc_all) if fc_all else np.array([])

    def save(fig, name: str) -> None:
        fig.tight_layout()
        path = args.out / name
        fig.savefig(path)
        plt.close(fig)
        print(f"Saved {path}")

    # ---- CCDF of all forces, by N_bots ----
    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    plot_ccdf_by_group(ax, forces_by_group, xlabel=r"$|\delta G|$ (uS)")
    ax.set_title("CCDF of forces, by $N_{tot}$")
    save(fig, "ccdf_forces_by_n.png")

    # ---- CCDF and QQ of burst vs. clog peaks ----
    if fb_all.size and fc_all.size:
        fig, ax = plt.subplots(figsize=(5.5, 4.5))
        plot_ccdf_by_group(ax, {"bursts": fb_all, "clogs": fc_all}, xlabel=r"peak $|\delta G|$ (uS)", fit_trend=False)
        ax.set_title("CCDF: bursts vs. clogs")
        save(fig, "ccdf_bursts_vs_clogs.png")

        fig, ax = plt.subplots(figsize=(5, 5))
        plot_quantile_quantile(ax, fb_all, fc_all, xlabel="$f_b$ quantiles", ylabel="$f_c$ quantiles")
        ax.set_title("QQ: bursts vs. clogs")
        save(fig, "qq_bursts_vs_clogs.png")
    else:
        print("No burst/clog segments detected at all -- skipping ccdf_bursts_vs_clogs.png and qq_bursts_vs_clogs.png (tune SPIKE_K)")

    # ---- delta-f histogram, one file per group ----
    colors = color_by_key(list(delta_by_group.keys()))
    for key, delta in sorted(delta_by_group.items(), key=lambda kv: (kv[0] is None, kv[0])):
        fig, ax = plt.subplots(figsize=(5.5, 4))
        plot_delta_histogram(
            ax,
            delta,
            xlabel=rf"$\delta f$ (uS, $\delta t$={DELTA_HIST_DT_S}s)",
            title=group_label(key),
            color=colors[key],
        )
        save(fig, f"delta_hist_{group_filename(key)}.png")

    # ---- skewness vs. dt, all groups on one plot ----
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    colors = color_by_key(list(skew_series_by_group.keys()))
    for key, series in sorted(skew_series_by_group.items(), key=lambda kv: (kv[0] is None, kv[0])):
        plot_skewness_vs_dt(ax, series, SKEW_DT_VALUES_S, fs_by_group[key], label=group_label(key), color=colors[key])
    ax.set_title("Skewness of $\\delta f$ vs. increment time")
    save(fig, "skewness_vs_dt.png")


if __name__ == "__main__":
    main()
