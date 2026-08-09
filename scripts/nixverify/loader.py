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
    """Import a file as a module. May raise — the caller isolates it."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"no import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
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
    runner = getattr(module, "run", None)
    if not callable(runner):
        return LoadedCheck(name=name, load_error=f"{name}: no run() callable")
    return LoadedCheck(
        name=name,
        run=runner,
        privilege=str(getattr(module, "PRIVILEGE", "user")),
        interactive=bool(getattr(module, "INTERACTIVE", False)),
        disruptive=bool(getattr(module, "DISRUPTIVE", False)),
    )
