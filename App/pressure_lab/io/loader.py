"""Discovery and parsing of raw measurement files under ``Mediciones/``.

``Mediciones/`` can hold any number of session folders, each with any
number of measurement files -- ``discover_measurements`` walks the whole
tree, so adding a new session or a new run is just dropping a new file in;
nothing here assumes a fixed count or a fixed set of sessions.

The acquisition firmware writes a CSV table with a ``.json`` extension
(historical artifact of an earlier logging format). Each row is one
decimation window (~50 ms / 20 Hz). Not every recording carries the same
columns -- some older sessions also have on-device-computed ``R_ohm,
G_uS, G0_mon, sigma_mon`` (kept for backward compatibility / comparison,
see ``scripts/compare_baselines.py``), while others only have ``adc_raw``.
Either way, ``pressure_lab.calibration.ensure_conductance_uS`` and
``pressure_lab.analysis.prepare_force_proxy`` derive whatever is missing
and recompute their own baseline regardless of what a file already has --
see App/docs/METODOS.md for why post-processing on a real computer does a
better job than trusting whatever a given firmware revision logged.

Nothing here converts to physical force units yet -- see
``pressure_lab.calibration`` for that step, which is still a placeholder
until weight-vs-conductance calibration data exists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from pressure_lab.config import MEDICIONES_DIR

# Matches "Medicion 25 Robots 30 Min.json" -> n_bots=25 ; "Medicion Vacio.json" -> baseline
_N_BOTS_RE = re.compile(r"(\d+)\s*Robots?", re.IGNORECASE)
_BASELINE_RE = re.compile(r"vac[ií]o", re.IGNORECASE)


@dataclass(frozen=True)
class Measurement:
    """Metadata for one measurement file, without loading its data."""

    path: Path
    session: str  # name of the parent date folder, e.g. "24-08-2026"
    label: str  # filename without extension
    n_bots: int | None  # number of active particles/robots, if parseable
    is_baseline: bool  # True for "Vacio" (empty arena) reference runs
    extra_tags: tuple[str, ...] = field(default_factory=tuple)

    def load(self) -> pd.DataFrame:
        return load_measurement(self.path)


def _parse_filename(path: Path) -> tuple[int | None, bool]:
    stem = path.stem
    if _BASELINE_RE.search(stem):
        return None, True
    m = _N_BOTS_RE.search(stem)
    n_bots = int(m.group(1)) if m else None
    return n_bots, False


def discover_measurements(root: Path | str = MEDICIONES_DIR) -> list[Measurement]:
    """Walk ``root`` and catalog every ``.json`` measurement file found.

    Files are grouped by their immediate parent directory name (the
    measurement "session", typically a date like ``24-08-2026``).
    """

    root = Path(root)
    measurements: list[Measurement] = []
    for path in sorted(root.rglob("*.json")):
        n_bots, is_baseline = _parse_filename(path)
        measurements.append(
            Measurement(
                path=path,
                session=path.parent.name,
                label=path.stem,
                n_bots=n_bots,
                is_baseline=is_baseline,
            )
        )
    return measurements


_NUMERIC_COLUMNS = (
    "timestamp(ms)",  # older firmware: mislabeled, actually seconds
    "uptime_s",  # current firmware: same value, correctly named
    "t",
    "n",
    "dt_ms",
    "adc_raw",
    "R_ohm",
    "G_uS",
    "G0_mon",
    "sigma_mon",
    "clipped",  # current firmware only: 1 if the ADC saturated during this window
)


def load_measurement(path: Path | str) -> pd.DataFrame:
    """Parse one raw measurement file into a tidy, numeric DataFrame.

    Adds a convenience ``t_s`` column (seconds from the start of the file,
    monotonic) derived from the millisecond timestamp column ``t``.
    """

    path = Path(path)
    df = pd.read_csv(path, quotechar='"', skipinitialspace=True, index_col=False)
    df.columns = [c.strip() for c in df.columns]

    # The firmware writes a trailing comma on the header row, which pandas
    # turns into a spurious all-NaN "Unnamed: N" column.
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]

    for col in _NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # A serial-logged session commonly has its last line cut off mid-write
    # (power loss, USB disconnect, script interrupted) -- drop any row
    # missing a value in a column that matters, rather than letting a
    # single NaN silently propagate into every downstream computation.
    required = [c for c in ("t", "adc_raw", "G_uS") if c in df.columns]
    df = df.dropna(subset=required).reset_index(drop=True)
    df = df.sort_values("t", kind="mergesort").reset_index(drop=True)
    df["t_s"] = (df["t"] - df["t"].iloc[0]) / 1000.0

    return df
