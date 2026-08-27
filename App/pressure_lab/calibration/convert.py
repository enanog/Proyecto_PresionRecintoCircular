"""Front-end electrical conversions, and the (currently unknown) force calibration.

Two layers, kept separate on purpose:

1. Electrical conversion (ADC counts -> resistance/conductance): fully
   determined by the amplifier circuit, implemented below.
2. Force calibration (conductance -> grams/newtons): requires an actual
   weight-vs-conductance calibration curve for the FSR ring, which doesn't
   exist yet in this repo (the project plan is to obtain it from paired
   camera + load measurements). Until then, ``Calibration`` defaults to an
   identity map so every plot/analysis function can already be written in
   terms of "force" and will start reporting real units the moment a curve
   is supplied, with no changes needed elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from pressure_lab.config import DEFAULT_FRONTEND, FrontEndParams


def adc_to_conductance_uS(adc_raw: np.ndarray, params: FrontEndParams = DEFAULT_FRONTEND) -> np.ndarray:
    """Average raw ADC counts -> sensor conductance [uS] (Vout = V_EXC*Rf*G)."""
    return np.asarray(adc_raw, dtype=float) * params.k_g_uS


def ensure_conductance_uS(df: pd.DataFrame, params: FrontEndParams = DEFAULT_FRONTEND) -> pd.DataFrame:
    """Return a copy of ``df`` guaranteed to have a ``G_uS`` column.

    Some recordings already have ``G_uS`` computed on-device; others only
    log ``adc_raw`` and expect this electrical conversion to happen here
    instead. Either way, the result is the same column, computed with the
    *same* front-end parameters -- so analysis code never has to care which
    firmware revision produced a given file.
    """
    if "G_uS" in df.columns:
        return df
    if "adc_raw" not in df.columns:
        raise ValueError("df has neither 'G_uS' nor 'adc_raw' -- can't derive conductance")
    df = df.copy()
    df["G_uS"] = adc_to_conductance_uS(df["adc_raw"].to_numpy(), params)
    return df


def resistance_to_conductance(r_ohm: np.ndarray) -> np.ndarray:
    """Ohms -> microsiemens."""
    return 1.0e6 / np.asarray(r_ohm, dtype=float)


def conductance_to_resistance(g_uS: np.ndarray) -> np.ndarray:
    """Microsiemens -> ohms."""
    return 1.0e6 / np.asarray(g_uS, dtype=float)


@dataclass(frozen=True)
class Calibration:
    """Maps a conductance excursion (dG, in uS) to a force-like quantity.

    ``scale`` / ``offset`` implement ``force = scale * dG + offset`` for the
    common case of a linear (or already-fitted-and-baked-in) calibration.
    Pass a ``fit_fn`` instead for anything non-linear (e.g. a power law
    fitted from calibration weights); when given, it takes priority over
    scale/offset.

    ``unit`` is carried along purely for axis labels -- update it once a
    real calibration is in place (e.g. "g", "N").
    """

    scale: float = 1.0
    offset: float = 0.0
    unit: str = "uS (uncalibrated)"
    fit_fn: Callable[[np.ndarray], np.ndarray] | None = None

    def __call__(self, dg_uS: np.ndarray) -> np.ndarray:
        dg_uS = np.asarray(dg_uS, dtype=float)
        if self.fit_fn is not None:
            return self.fit_fn(dg_uS)
        return self.scale * dg_uS + self.offset

    @property
    def is_identity(self) -> bool:
        return self.fit_fn is None and self.scale == 1.0 and self.offset == 0.0


IDENTITY_CALIBRATION = Calibration()


def delta_conductance_to_force(
    dg_uS: np.ndarray, calibration: Calibration = IDENTITY_CALIBRATION
) -> np.ndarray:
    """Convenience wrapper: apply a Calibration to a dG array."""
    return calibration(dg_uS)
