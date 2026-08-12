"""Shared sys.path bootstrap so a check imports nixverify either way.

A check is both a verify.py plugin and a standalone executable (§4.2). Under
the engine, scripts/ is already importable; run directly it is not. Importing
this module first makes both paths work with no per-check duplication.
"""

import sys
from pathlib import Path

# ARC 026 Stage 2.2 — the runtime observer FAILED `check_capture_plane2` for
# `file-write:.../scripts/nixbus/__pycache__/*.pyc`, against a declaration of
# `RESOURCES = ("journal",)`. The declaration was HONEST and the observation was
# REAL; what was wrong was attribution. Writing a `.pyc` is the interpreter
# caching a module, not the check using a resource — and because the cache is
# shared, the write is attributed to whichever check imports first on a cold
# tree. Three other gates import the same modules and were reported clean purely
# because `check_capture_plane2` was scheduled ahead of them and paid for all
# four. A claim that moves between checks when the PLAN is reordered is an
# artefact of the instrument.
#
# Fixed at the cause rather than by declaring it, which is the precedent ARC 026
# C set when the same gate caught `shutil.rmtree`: declaring
# `file-write:<...>.pyc.124164211425776` would have gone green by exact-string
# match on a path containing a PID-derived temp suffix that never recurs — a
# declaration that can only ever match the run that produced it.
#
# Set HERE, in the one module every check imports before anything else (§4.2's
# both-ways bootstrap), so no check can forget it and no check pays for another's
# import. It suppresses only cache WRITES; imports still work and are unaffected.
sys.dont_write_bytecode = True

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.append(str(_SCRIPTS))
