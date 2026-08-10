"""Check contract per VERIFY-AND-CHECKS.md §4-§5."""

from __future__ import annotations

import dataclasses
from enum import StrEnum
from pathlib import Path


class Mode(StrEnum):
    """install superset-of correct superset-of verify (§4)."""

    VERIFY = "verify"
    CORRECT = "correct"
    INSTALL = "install"

    @property
    def rank(self) -> int:
        """Ordering so a check can ask 'am I allowed to repair?' cheaply."""
        return {Mode.VERIFY: 0, Mode.CORRECT: 1, Mode.INSTALL: 2}[self]


class Status(StrEnum):
    """Five outcomes (§4.1). CANNOT_MEASURE is never a failure."""

    PASS = "pass"
    FAIL_REPAIRABLE = "fail_repairable"
    FAIL_NEEDS_OPERATOR = "fail_needs_operator"
    CANNOT_MEASURE = "cannot_measure"
    SKIPPED = "skipped"


FAILURES = (Status.FAIL_REPAIRABLE, Status.FAIL_NEEDS_OPERATOR)


@dataclasses.dataclass
class CheckResult:
    """One check's outcome. `site` and `evidence` are load-bearing — see §5."""

    name: str
    status: Status
    site: str = ""
    evidence: str = ""
    detail: str = ""
    action: str = ""
    upstream_available: str = ""


@dataclasses.dataclass(frozen=True)
class Context:
    """Everything a check may need about the run it is part of.

    `privilege` accepts the sentinel "all" so install.sh can run user and
    root checks in one pass (§8's three-runner table); the systemd units
    pass "user"/"root" and get only their own subset.

    `allow_interactive` is what lets install.sh run INTERACTIVE checks while
    every headless runner skips them.
    """

    nix_home: Path
    mode: Mode
    privilege: str = "user"
    maintenance: bool = False
    allow_interactive: bool = False


def validate_result(result: CheckResult) -> CheckResult:
    """Enforce §5 mechanically rather than trusting the check author.

    A PASS with no evidence measured nothing; a FAIL with no site cannot say
    what is wrong. Both are downgraded to CANNOT_MEASURE — the honest answer
    is 'unknown', never a false assurance.
    """
    reason = ""
    if result.status is Status.PASS and not result.evidence.strip():
        reason = "engine: PASS rejected — no evidence recorded (§5)"
    elif result.status in FAILURES and not result.site.strip():
        reason = "engine: FAIL rejected — no site named (§5)"
    if reason:
        result.status = Status.CANNOT_MEASURE
        # Append, never replace: the downgrade path is exactly where an
        # operator most needs the check's own account of why it is uncertain.
        said = result.detail.strip()
        result.detail = f"{reason}; check said: {said}" if said else reason
    return result


def exit_code_for(status: Status) -> int:
    """§4.2. SKIPPED maps to 2: a check that never ran is not a pass."""
    if status is Status.PASS:
        return 0
    if status in FAILURES:
        return 1
    return 2
