"""Project-wide paths and default front-end (analog acquisition) parameters.

The physical constants here must mirror whatever is hard-coded in
Codigo/fsr_single_read/fsr_single_read.ino -- the firmware is the ground
truth (it's what actually drove the amplifier during acquisition), this is
just a copy for the Python side. If you change V_EXC / R_FEEDBACK / V_REF
on the Arduino, update them here too, in the same commit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Repo layout: App/pressure_lab/config.py -> repo root is two levels up.
APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parent
MEDICIONES_DIR = REPO_ROOT / "Mediciones"
OUTPUT_DIR = APP_DIR / "output"


@dataclass(frozen=True)
class FrontEndParams:
    """Inverting transimpedance amplifier + ADC parameters.

    Vout = V_EXC * R_FEEDBACK * G_sensor  (G_sensor = 1 / R_sensor)
    G_sensor [uS] = (adc_raw / ADC_FS) * V_REF / (V_EXC * R_FEEDBACK) * 1e6
    """

    v_ref: float = 3.3
    v_exc: float = 0.7534  # matches V_EXC in fsr_single_read.ino
    r_feedback_ohm: float = 12_000.0
    adc_fs: float = 1023.0

    @property
    def k_g_uS(self) -> float:
        """Multiply by average raw ADC counts to get conductance in microsiemens."""
        return (self.v_ref * 1.0e6) / (self.adc_fs * self.v_exc * self.r_feedback_ohm)


DEFAULT_FRONTEND = FrontEndParams()
