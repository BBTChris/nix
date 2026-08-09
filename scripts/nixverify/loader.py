"""Import check modules without letting one bad module kill the run (§9.3)."""

from __future__ import annotations

import dataclasses
import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

from nixverify.contract import CheckResult


@dataclasses.dataclass(frozen=True)
class LoadedCheck:
    """A check module after an import attempt that is allowed to have failed."""

    name: str
    run: Callable[..., CheckResult] | None = None
    privilege: str = "user"
    interactive: bool = False
    disruptive: bool = False
    load_error: str = ""


def _import_module(path: Path, name: str) -> ModuleType:
    """Import a file as a module. May raise — the caller isolates it.

    A check's own directory must be on sys.path before exec_module runs, so
    a top-level `import _sibling` inside it resolves the same way it would
    if the check were run standalone — CPython auto-adds a script's own
    directory to sys.path[0] at interpreter startup, but spec_from_file_location
    does not replicate that, so we do it explicitly here.

    Appended, never inserted at the front (docs/debug.md failure mode #8,
    import-shadowing plant): a front insertion would let a future sibling
    named e.g. queue.py, random.py, or token.py silently shadow the real
    stdlib module for every check loaded afterward in the run. Appending
    still makes the directory importable without out-ranking stdlib.

    The entry is never removed. sys.path is process-global and blocks run
    in parallel via ThreadPoolExecutor (engine._run_block); scoping the
    insertion with try/finally around exec_module would let one thread
    remove the entry while another is mid-import of a sibling — trading a
    bounded, deduplicated leak (one entry per distinct checks/ directory)
    for an intermittent, load-dependent import failure. The leak is a
    deliberate trade, not an oversight; tests that care about accumulation
    reset sys.path themselves (see scripts/tests/conftest.py).
    """
    module_dir = str(path.resolve().parent)
    if module_dir not in sys.path:
        sys.path.append(module_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"no import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules[name] = module
    return module


def load_check(checks_dir: Path, name: str) -> LoadedCheck:
    """Load one check. Any failure is captured, never raised.

    This is the fix for the v1 defect where a check importing a missing
    package aborted the entire run — precisely when that check was the thing
    meant to install it.
    """
    path = checks_dir / f"{name}.py"
    if not path.is_file():
        return LoadedCheck(name=name, load_error=f"module not found: {path}")
    try:
        module = _import_module(path, name)
    except Exception as exc:  # noqa: BLE001 pylint: disable=broad-exception-caught
        return LoadedCheck(name=name, load_error=f"import failed: {exc!r}")
    try:
        runner = getattr(module, "run", None)
        if not callable(runner):
            return LoadedCheck(name=name, load_error=f"{name}: no run() callable")
        privilege = str(getattr(module, "PRIVILEGE", "user"))
        interactive = bool(getattr(module, "INTERACTIVE", False))
        disruptive = bool(getattr(module, "DISRUPTIVE", False))
    except Exception as exc:  # noqa: BLE001 pylint: disable=broad-exception-caught
        return LoadedCheck(name=name, load_error=f"attribute read failed: {exc!r}")
    return LoadedCheck(
        name=name,
        run=runner,
        privilege=privilege,
        interactive=interactive,
        disruptive=disruptive,
    )
