"""Record every verdict the REAL check code produces while the suite runs.

ARC 027 / 0.2 and §0f. The §2.4 binding table has been built by reading for
three arcs, and ARC 026 proved what that costs: `check_verify_logging` sat in
the table as a green gate whose green had never been shown able to turn red,
and nothing said so, because nobody had claimed anything about it. §0f's answer
is *"built from measured evidence each arc"* — and evidence you can read is not
evidence you measured.

## What this measures, exactly

`checks/check_*.py` all expose `run(mode, ctx) -> CheckResult`. Every path into
a check goes through it: `verify.py` calls it, `actuation.standalone_main` calls
it, and every can-fail control in `scripts/tests/` reaches it either directly or
by spawning the check's CLI. So one observation point sees them all:

    **the return value of `run` in a file named `check_<name>.py`.**

The tracer records `(check, status, module path, owning test, pid)` for every
such return. A check is BOUND when some committed test drove the real code to a
NON-PASS status. Nothing here reads a docstring, a table, or a filename.

## §7.12 — what would have to be true for this to report a binding while
## measuring nothing?

1. **The tracer could be installed and never fire**, and an empty record file
   reads exactly like "no check ever went red". *Closed in `binding_census.py`:*
   a run producing zero PASS observations is CANNOT-MEASURE, not a clean sheet —
   the instrument must be seen working before its silence means anything.

2. **A check could go red in a COPY of itself.** Several controls copy a gate
   into `tmp_path` and drive it there, and the copy's verdict is not obviously
   the shipped gate's. *Not closed — REPORTED:* `canonical` is recorded per
   observation, and the census prints real-module and copied-module bindings in
   separate columns rather than merging them. D3.16 is exactly this distinction
   and it is not the tracer's place to collapse it.

3. **Subprocess controls could be invisible.** The strongest can-fails spawn
   `checks/check_x.py` as a program; a tracer living only in the pytest process
   would miss every one and call them unbound. *Closed:* the driver puts a
   generated `sitecustomize.py` on `PYTHONPATH`, so any child interpreter
   installs the same tracer. A child that inherits neither (a control passing a
   hand-built `env=`) is invisible, and that is stated rather than assumed.

4. **Attribution could be guesswork.** *Closed:* `pytest_runtest_setup` stamps
   the nodeid into the environment, so the owning test comes from the runner,
   not from a heuristic over the call stack — and it survives into children,
   which a stack walk cannot.

5. **The observation point could be wrong.** If a check ever measured something
   outside `run`, this would see the wrong verdict. *Closed by the contract:*
   `run` IS the check's interface — `engine.run_blocks` and
   `actuation.standalone_main` have no other entry.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import sysconfig
import threading
from pathlib import Path

#: Where observations are appended, one JSON object per line. Absent = off, so
#: importing this module in an ordinary session does nothing at all.
OUT_VAR = "NIX_BINDING_CENSUS_OUT"
#: The nodeid of the test currently running, stamped by the pytest hook below
#: and inherited by every child process the test spawns.
TEST_VAR = "NIX_BINDING_CENSUS_TEST"
#: The canonical `checks/` directory, so a copied module can be told apart from
#: the shipped one (§7.12/2).
CHECKS_VAR = "NIX_BINDING_CENSUS_CHECKS"

_LOCK = threading.Lock()
_INSTALLED = False
#: The append-only descriptor, opened ONCE at install. See `_open_sink`.
_FD = -1


def _open_sink() -> int:
    """Open the record file at install time, and never again.

    **THIS IS THE INSTRUMENT'S OWN §0a DEFECT, MEASURED.** The first version
    called `open()` per observation, and five controls went red — not because
    anything was broken, but because `nixverify.observe` hooks the `open` AUDIT
    EVENT, so the tracer's own bookkeeping appeared inside the observation
    window as `file-write:.../observations.jsonl` and was charged to whichever
    check was being observed. The instrument became the artefact, which is
    exactly the class ARC 026's `.pyc` finding named and D1 generalises.

    Two properties close it, and both matter:

    * The descriptor is opened HERE, during `sitecustomize` import — which is
      before `observe.py` arms its hook, and `observe.py` documents that the
      window opens after import for precisely this reason.
    * Writes then go through `os.write`, which raises **no audit event at all**,
      so nothing the tracer does afterwards is visible to an observer.

    `O_APPEND` makes each short write atomic across the processes that inherit
    this file, which is how a spawned check's verdict lands in the same file as
    its parent's without a lock spanning process boundaries.
    """
    path = os.environ.get(OUT_VAR)
    if not path:
        return -1
    try:
        return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    except OSError:  # pragma: no cover - an unwritable sink disables the tracer
        return -1


_SHA: dict[str, str] = {}


def _digest(path: str) -> str:
    """sha256 of the module that produced a verdict, memoised per process.

    **Location is not identity.** Several controls copy a gate into `tmp_path`
    and plant against it there; the first cut of this census called every one of
    those a weaker "copy" binding, which would have demoted three gates that are
    in fact running the shipped bytes. The digest is what separates *the shipped
    gate, executed from a different directory* from *a modified gate*, and only
    the second is a weaker claim. Read with `os.open`/`os.read` for the same
    reason `_open_sink` exists: `open()` raises an audit event and this runs
    inside the observation window.
    """
    cached = _SHA.get(path)
    if cached is not None:
        return cached
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            hasher = hashlib.sha256()
            while chunk := os.read(fd, 65536):
                hasher.update(chunk)
            digest = hasher.hexdigest()
        finally:
            os.close(fd)
    except OSError:  # pragma: no cover - a module that vanished mid-run
        digest = ""
    _SHA[path] = digest
    return digest


def _record(check: str, status: str, module: str) -> None:
    """Append one observation. Never raises into the program being measured."""
    if _FD < 0:
        return
    canonical_dir = os.environ.get(CHECKS_VAR, "")
    row = {
        "check": check,
        "status": status,
        "module": module,
        "canonical": bool(canonical_dir)
        and os.path.dirname(module) == canonical_dir.rstrip("/"),
        "sha": _digest(module),
        "test": os.environ.get(TEST_VAR, ""),
        "pid": os.getpid(),
    }
    try:
        with _LOCK:
            os.write(_FD, (json.dumps(row) + "\n").encode("utf-8"))
    except OSError:  # pragma: no cover - a full disk must not fail the suite
        pass


def _check_name(filename: str) -> str | None:
    """`check_<x>` for a file that is one, else None."""
    stem = Path(filename).stem
    return stem if stem.startswith("check_") else None


def _status_name(value: object) -> str:
    """`CheckResult.status` reduced to a name, whatever enum shape it has."""
    status = getattr(value, "status", None)
    if status is None:
        return ""
    return str(getattr(status, "name", status))


def install() -> bool:
    """Arm the `PY_RETURN` monitor. Idempotent; False when there is nothing to do.

    `sys.monitoring` rather than `sys.settrace` because the callback can return
    `DISABLE` for a code object it does not care about, and the interpreter then
    stops calling it there **permanently**. A `settrace` hook is called for every
    call event in the process and would have multiplied the suite's three
    minutes by an order of magnitude — an instrument whose cost changes what the
    operator is willing to run is an instrument that will not be run.
    """
    # E1101: astroid has no model of `sys.monitoring` (PEP 669, 3.12+), so every
    # member below reads as missing. The interpreter running this IS 3.14 and the
    # committed suite exercises the callback; the alternative — a `getattr` dance
    # to placate a static model that is simply out of date — would make the one
    # instrument that watches every gate harder to read.
    # pylint: disable=global-statement,no-member
    global _INSTALLED, _FD
    if _INSTALLED or not os.environ.get(OUT_VAR):
        return False
    _FD = _open_sink()
    if _FD < 0:
        return False
    monitoring = sys.monitoring
    tool = monitoring.PROFILER_ID
    try:
        monitoring.use_tool_id(tool, "nix-binding-census")
    except ValueError:  # pragma: no cover - another profiler owns the slot
        return False
    stdlib = sysconfig.get_paths()["stdlib"]

    def _on_return(code: object, _offset: int, retval: object) -> object:
        filename = getattr(code, "co_filename", "")
        if getattr(code, "co_name", "") != "run" or filename.startswith(stdlib):
            return monitoring.DISABLE
        name = _check_name(filename)
        if name is None:
            return monitoring.DISABLE
        status = _status_name(retval)
        if status:
            _record(name, status, filename)
        return None

    monitoring.register_callback(tool, monitoring.events.PY_RETURN, _on_return)
    monitoring.set_events(tool, monitoring.events.PY_RETURN)
    _INSTALLED = True
    return True


# --------------------------------------------------------------------------
# pytest plugin surface — attribution, from the runner rather than a heuristic
# --------------------------------------------------------------------------


def pytest_runtest_setup(item: object) -> None:
    """Stamp the running nodeid where the tracer — and children — can read it."""
    os.environ[TEST_VAR] = str(getattr(item, "nodeid", ""))


def pytest_configure(config: object) -> None:
    """Arm inside the pytest process too, not only in spawned children."""
    del config  # pytest injects fixtures by PARAMETER NAME; it cannot be renamed
    install()


install()
