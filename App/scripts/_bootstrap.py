"""Import-time side effect: put the App/ directory on sys.path.

Scripts in this folder are meant to be run directly (``python
scripts/make_figures.py``) without installing the package first, so each
script does ``import _bootstrap`` before importing anything from
``pressure_lab``. If you *do* install the package (``pip install -e .``
from ``App/``), this becomes a harmless no-op.
"""

from __future__ import annotations

import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parents[1]
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))
