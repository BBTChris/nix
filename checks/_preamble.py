"""Shared sys.path bootstrap so a check imports nixverify either way.

A check is both a verify.py plugin and a standalone executable (§4.2). Under
the engine, scripts/ is already importable; run directly it is not. Importing
this module first makes both paths work with no per-check duplication.
"""

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.append(str(_SCRIPTS))
