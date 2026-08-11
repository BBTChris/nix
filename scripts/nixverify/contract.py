"""Check contract per nix_check_contract.md §4-§5."""

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
    """Six outcomes (§4.1, as amended). CANNOT_MEASURE is never a failure."""

    # nosec B105 - enum member value, not a credential. B105's heuristic keys
    # on the literal "pass"; renaming it to satisfy the scanner would change
    # the wire value every CheckResult and every exit-code mapping is written
    # against. Named site, one line, rule stays live everywhere else.
    PASS = "pass"  # nosec B105
    FAIL_REPAIRABLE = "fail_repairable"
    FAIL_NEEDS_OPERATOR = "fail_needs_operator"
    CANNOT_MEASURE = "cannot_measure"
    SKIPPED = "skipped"
    #: AMENDMENT 1 to the check contract (ARC 024). The subject is real and was
    #: measured; the check carries a known-red marker naming the arc that
    #: discharges it. Neither a PASS (nothing was proven) nor a FAIL (nothing is
    #: broken) — a deferral **with an owner**. Withholds certification, never
    #: durability. See docs/CHECK-CONTRACT-AMENDMENTS.md.
    GUARDED = "guarded"


FAILURES = (Status.FAIL_REPAIRABLE, Status.FAIL_NEEDS_OPERATOR)


@dataclasses.dataclass
class CheckResult:  # pylint: disable=too-many-instance-attributes
    """One check's outcome. `site` and `evidence` are load-bearing — see §5."""

    name: str
    status: Status
    site: str = ""
    evidence: str = ""
    detail: str = ""
    action: str = ""
    upstream_available: str = ""
    #: ARC 024. The arc that discharges a GUARDED verdict. Mechanically required
    #: for GUARDED (see `validate_result`) — a deferral with no owner is
    #: `CHECK-DEBT.md` doctrine B.3's "no owner wearing a name", and would let
    #: GUARDED become the drawer everything awkward is filed in.
    guard_owner: str = ""
    #: ARC 024. Wall-clock seconds the check took, stamped by the engine. Feeds
    #: the Plane-2 verdict event and the progress surface. Never an input to a
    #: verdict — a check whose duration decided its status would be anchored to
    #: a moving value (debug.md §7.4).
    duration_s: float = 0.0


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
    # AMENDMENT 1 (ARC 024). GUARDED is the one status that could rot into a
    # drawer for anything inconvenient, because unlike FAIL it costs nothing to
    # claim. Both of its defining properties are therefore enforced here rather
    # than asked for in prose: it must have MEASURED (evidence), and it must
    # name the arc that discharges it (guard_owner). A GUARDED verdict missing
    # either one is not a deferral, it is an unmeasured claim with a colour, and
    # it degrades to CANNOT_MEASURE like every other unmeasured claim.
    elif result.status is Status.GUARDED and not result.evidence.strip():
        reason = (
            "engine: GUARDED rejected — no evidence recorded; a deferral must "
            "have measured (§5, AMENDMENT 1)"
        )
    elif result.status is Status.GUARDED and not result.guard_owner.strip():
        reason = (
            "engine: GUARDED rejected — no discharging arc named "
            "(CHECK-DEBT.md B.3: an owner that cannot pay is no owner wearing a name)"
        )
    if reason:
        result.status = Status.CANNOT_MEASURE
        # Append, never replace: the downgrade path is exactly where an
        # operator most needs the check's own account of why it is uncertain.
        said = result.detail.strip()
        result.detail = f"{reason}; check said: {said}" if said else reason
    return result


def result_from_defects(
    name: str,
    defects: list[tuple[str, str]],
    evidence: str,
    status: Status = Status.FAIL_NEEDS_OPERATOR,
) -> CheckResult:
    """Turn a `[(site, why)]` list into a CheckResult — PASS when empty.

    Both IB Gateway gates accumulate defects as (site, reason) pairs and then
    render them identically. Factored here rather than duplicated so the two
    can never disagree about how a defect list becomes a verdict (§5.5,
    doctrine C.9) — the same reasoning that makes the service gate import the
    config gate's handshake instead of owning a copy.

    `evidence` is attached to the FAIL as well as the PASS: an operator
    reading a failure needs to know what *was* successfully measured, not
    only what was wrong.
    """
    if not defects:
        return CheckResult(name=name, status=Status.PASS, evidence=evidence)
    return CheckResult(
        name=name,
        status=status,
        site="; ".join(site for site, _ in defects),
        evidence=evidence,
        detail="; ".join(f"{site}: {why}" for site, why in defects),
    )


def exit_code_for(status: Status) -> int:
    """§4.2, as amended. SKIPPED maps to 2: a check that never ran is not a pass.

    AMENDMENT 1 (ARC 024) adds `3 — GUARDED` and is **strictly additive**:
    `0`/`1`/`2` keep the meanings `VERIFY-AND-CHECKS.md` §B.2 gives them, and
    exit 2 in particular is untouched. Part D item 2 of the doctrine — *"keep
    the exit-code contract, including exit 2; it exists because of a measured
    incident"* — is preserved rather than amended, because the incident that
    produced exit 2 was a gate reporting a violation while having measured
    nothing, and GUARDED is a status only available to a gate that DID measure.
    """
    if status is Status.PASS:
        return 0
    if status in FAILURES:
        return 1
    if status is Status.GUARDED:
        return 3
    return 2
