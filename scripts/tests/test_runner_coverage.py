"""§8 runner-coverage guard (I1, final whole-branch review).

check_python_deps is PRIVILEGE=user and DISRUPTIVE=True. The boot unit
(user privilege, disruptive refused per §8) never repairs it, and the
weekly root unit runs only PRIVILEGE=root checks — so pin drift on the
library that places orders (ib_async) was detected at every boot and
repaired never, with the boot unit reporting failure every time.

Rather than hardcoding a second copy of the runner matrix (which would
itself be exactly the kind of duplicated fact CLAUDE.md directive 3 warns
against), this test parses the real `--mode ... --privilege ...` verify.py
invocations straight out of install.sh — the single place all of them are
declared (the boot/weekly-root/weekly-user systemd units are embedded
there as heredocs, and install.sh's own end-of-install call is right there
too). If a future unit is dropped or a check's declared PRIVILEGE/DISRUPTIVE
changes, this test recomputes reachability from the real files with no
separate matrix to fall out of sync.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from nixverify.loader import load_check

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"
REGISTRY = CHECKS / "registry.json"
INSTALL_SH = REPO / "install.sh"

_INVOCATION = re.compile(r"--mode\s+(\S+)\s+--privilege\s+(\S+)([^\n]*)")


def _runners() -> list[tuple[str, bool, bool]]:
    """Every verify.py invocation in install.sh: (privilege, maintenance, allow_interactive)."""
    text = INSTALL_SH.read_text(encoding="utf-8")
    joined = text.replace("\\\n", " ")  # collapse bash line continuations
    runners = [
        (
            privilege,
            "--maintenance" in tail,
            "--allow-interactive" in tail,
        )
        for _mode, privilege, tail in _INVOCATION.findall(joined)
    ]
    assert runners, "no verify.py invocations found in install.sh"
    return runners


def _reachable(
    privilege: str,
    disruptive: bool,
    interactive: bool,
    runners: list[tuple[str, bool, bool]],
) -> bool:
    """True if some runner would both execute this check and, if it is
    DISRUPTIVE, actually be permitted to repair it (not merely inspect it)."""
    for run_privilege, maintenance, allow_interactive in runners:
        if run_privilege not in ("all", privilege):
            continue
        if disruptive and not maintenance:
            continue
        if interactive and not allow_interactive:
            continue
        return True
    return False


def test_every_registry_check_is_reachable_by_a_configured_runner() -> None:
    """Every check named in checks/registry.json must actually run —
    and, if DISRUPTIVE, actually be repaired — under at least one of
    install.sh's configured verify.py invocations. Fails loudly if this
    class of gap (a check with no runner able to fully service it) recurs.
    """
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    names = sorted({name for block in registry["blocks"] for name in block["checks"]})
    runners = _runners()

    unreachable = []
    for name in names:
        loaded = load_check(CHECKS, name)
        assert loaded.run is not None, f"{name}: {loaded.load_error}"
        if not _reachable(
            loaded.privilege, loaded.disruptive, loaded.interactive, runners
        ):
            unreachable.append(name)

    assert not unreachable, (
        f"checks unreachable by any configured runner (never fully serviced): "
        f"{unreachable}"
    )


def test_reachability_helper_catches_a_planted_gap() -> None:
    """Control: a user-privilege disruptive check with only a no-maintenance
    user runner and a maintenance-only root runner (I1's exact original
    shape) must be reported unreachable, proving this test can fail.
    """
    runners = [("user", False, False), ("root", True, False)]
    assert not _reachable("user", True, False, runners)
    # Adding the missing weekly-user (maintenance) runner fixes it.
    runners.append(("user", True, False))
    assert _reachable("user", True, False, runners)
