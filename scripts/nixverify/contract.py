"""Check contract per nix_check_contract.md §4-§5."""

from __future__ import annotations

import dataclasses
import re
from enum import StrEnum
from pathlib import Path

#: A `guard_owner` names EXACTLY ONE arc. ARC 025.
#:
#: §4.1 defines GUARDED as a marker naming **the specific** discharging arc, and
#: doctrine B.3 says *an owner that cannot pay is no owner wearing a name*. The
#: non-empty test that shipped in ARC 024 catches `""` and nothing else, and the
#: only `guard_owner` on the tree read `"the bulk check retrofit arc (ARC 025+),
#: sized in ARC 024 Stage 6.4"` — which passes a non-empty test while naming a
#: RANGE and two different arcs. A range cannot be held to account: every arc in
#: it can point at the next one, which is precisely how a marker becomes
#: furniture.
#:
#: **The grammar is deliberately the smallest thing that can be one arc.** No
#: stage suffix, no parenthetical, no prose. Every additional production is a
#: place a range can hide, and a stage suffix buys no binding power the arc
#: number does not already carry — the ledger's owner column, `bank.sh`, and this
#: engine all reason at arc granularity. Justification for the reader who wants
#: to widen it: widen the ledger prose instead, which is free-text by design.
GUARD_OWNER_PATTERN = r"ARC \d{3}"
_GUARD_OWNER = re.compile(rf"^{GUARD_OWNER_PATTERN}$")
#: Spellings that turn one arc into an open-ended commitment.
_RANGE_MARKERS = re.compile(
    r"(\d\s*\+)|(\bonwards?\b)|(\bor later\b)|(\bor after\b)|(\d{3}\s*[-–]\s*\d{3})",
    re.IGNORECASE,
)


#: WHERE "WHICH ARCS HAVE COMPLETED" COMES FROM, and it is DERIVED, never listed.
#:
#: `CLAUDE.md`: *"Every arc, on completion, MUST (1) append its summary to the end
#: of `~/nix/sessions/SESSION.md`"*. That sentence makes the session log the
#: DEFINITION of arc completion on this box, not a proxy for it — so this predicate
#: reads it rather than restating what it says (directive 3).
#:
#: **Three candidates were weighed and two rejected on the facts:**
#:
#: * **A hardcoded list.** Rejected outright. It is a moving anchor (`debug.md` §8
#:   failure mode #4) that goes stale at the close of every arc, which is exactly
#:   the cadence at which this predicate has to be right.
#: * **Git history.** The tempting one, because `check_artifact_gate_coverage`'s
#:   ratchet uses it for precisely the *"the hand being judged cannot reach it"*
#:   property. **It is wrong here, and measurably so:** commits naming an arc are
#:   made THROUGHOUT that arc, so `ARC 026` is already all over the history while
#:   ARC 026 is in flight. A rule reading it would reject a guard naming the arc
#:   that is currently running — the one arc that certainly CAN discharge it —
#:   and every arc would be born unable to own a marker.
#: * **`docs/CHECK-DEBT.md`'s series table.** A real per-arc record, but a softer
#:   convention than the session log (ARC 023 appears twice in it) and it carries
#:   a count rather than a completion. Kept as a CROSS-CHECK, below.
#:
#: The session log's weakness is that it is an ordinary working-tree file, and a
#: PARTIAL parse of it is the dangerous failure: fewer arcs read as fewer closed
#: arcs, and a guard pointing at history would pass. That is answered by
#: cross-derivation against `docs/CHECK-DEBT.md`'s series table — a second,
#: independently-maintained per-arc record.
#:
#: **THE TWO RECORDS HAVE DIFFERENT TENSES, AND THE FIRST SPELLING OF THIS RULE
#: GOT IT WRONG.** The obvious cross-check — *the session log's highest arc must
#: not be below the series table's* — was written, and this arc's own suite
#: reddened on it immediately: the series row for an arc is written DURING that
#: arc (it carries the running figure), while the session summary is appended AT
#: CLOSE. So the series table legitimately runs one arc ahead, always, and the
#: simple floor called every in-flight arc a broken session log.
#:
#: The tense-correct rule: **every arc with a series row must be closed in the
#: session log, EXCEPT the newest series row, which may be the arc in flight.**
#: It still catches the failure that matters — a partial session parse leaves
#: many series arcs unmatched, not one — and it cannot fire on the normal state
#: of an arc that is running. Arcs before the ledger opened have no series rows
#: and are simply not cross-checked, which is honest: the ledger cannot vouch for
#: a period it did not cover.
_SESSION_LOG = "sessions/SESSION.md"
_DEBT_LEDGER = "docs/CHECK-DEBT.md"
_ARC_IN_HEADING = re.compile(r"\bARC (\d{3})\b")
_SERIES_ROW = re.compile(r"^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*ARC (\d+)\s*\|", re.MULTILINE)


def completed_arcs(home: Path) -> tuple[frozenset[int], str]:
    """Arcs whose CLOSE-OUT SUMMARY is on the record. Returns (arcs, error).

    A non-empty `error` means the question could not be answered, and every
    caller must treat that as CANNOT_MEASURE rather than as "nothing has
    completed" — the fail-open reading would turn this whole predicate off
    silently the first time the log moved, which is the defect it exists to stop.

    Only HEADING lines are read. Arc summaries are `##`-level headings; the prose
    beneath them cites other arcs constantly, and counting a citation as a
    completion would mark an arc complete because somebody mentioned it.
    """
    log = home / _SESSION_LOG
    try:
        text = log.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return frozenset(), f"cannot read {_SESSION_LOG}: {exc!r}"
    arcs = frozenset(
        int(match.group(1))
        for line in text.splitlines()
        if line.startswith("#")
        for match in _ARC_IN_HEADING.finditer(line)
    )
    if not arcs:
        return frozenset(), (
            f"{_SESSION_LOG} names no arc in any heading — the completion record "
            "cannot be read, so no guard owner can be checked against it"
        )
    ledger = home / _DEBT_LEDGER
    try:
        rows = _SERIES_ROW.findall(ledger.read_text(encoding="utf-8"))
    except OSError, UnicodeDecodeError:
        rows = []
    if rows:
        series = {int(value) for value in rows}
        # The newest series row may belong to the arc in flight; every older one
        # must name an arc the session log records as closed.
        unmatched = sorted(series - arcs - {max(series)})
        if unmatched:
            return frozenset(), (
                f"{_DEBT_LEDGER}'s series table records ARC(s) "
                f"{', '.join(f'{n:03d}' for n in unmatched)} that "
                f"{_SESSION_LOG} does not close, and they are not the newest "
                "series row — the completion record is UNDER-REPORTING (a "
                "partial parse or a truncated log), so it cannot be used to "
                "judge whether a guard owner can still pay"
            )
    return arcs, ""


def guard_owner_defect(value: str, completed: frozenset[int] | None = None) -> str:
    """Why `value` is not a dischargeable single-arc identifier, or `''`.

    One implementation, two consumers (doctrine C.9): `validate_result` enforces
    it on every GUARDED verdict, and `check_artifact_gate_coverage` uses the same
    function for the arcs that admit a baseline addition. Two spellings of "what
    counts as an arc" would disagree the first time one was edited.

    ## `completed` — the third iteration of one flaw (ARC 026, B2)

    ARC 024 required a non-empty owner. `"the bulk check retrofit arc (ARC 025+)"`
    passed it while naming a range. ARC 025 constrained the SHAPE to exactly one
    arc — and set the only live guard to `ARC 025`, **an arc that has since
    completed with the guard still standing.** Shape was never the property;
    doctrine B.3 asks for *"the arc that can actually discharge it"*, and an arc
    that is over can discharge nothing. A marker pointing at history is a
    known-red with no owner wearing a name — the exact furniture B.3 describes,
    reached by a third route.

    Pass `completed` (from `completed_arcs`) to enforce dischargeability.

    **IT IS OPT-IN, AND THAT IS A DISTINCTION RATHER THAN A CONVENIENCE.** A
    `guard_owner` is a FORWARD-LOOKING OBLIGATION: it names who will pay, so a
    completed arc is disqualifying. `check_artifact_gate_coverage`'s `admitted`
    map is a BACKWARD-LOOKING RECORD: it names the arc that admitted a baseline
    addition, an event that has already happened, so a completed arc is the
    *normal and correct* value there and will be the value for every entry the
    moment its arc closes. Applying dischargeability to `admitted` would redden
    a true record at the next arc boundary. Same grammar, two tenses; the caller
    states which one it is holding.
    """
    owner = value.strip()
    if not owner:
        return (
            "no discharging arc named (CHECK-DEBT.md B.3: an owner that cannot "
            "pay is no owner wearing a name)"
        )
    if _GUARD_OWNER.fullmatch(owner):
        if completed is not None and int(owner.split()[1]) in completed:
            return (
                f"{owner!r} has ALREADY COMPLETED — its close-out summary is in "
                f"{_SESSION_LOG}. A guard may only name an arc that can still "
                "discharge it (doctrine B.3: an owner that cannot pay is no "
                "owner wearing a name). Re-point the marker at a live arc or "
                "take the red"
            )
        return ""
    if _RANGE_MARKERS.search(owner):
        return (
            f"{owner!r} names a RANGE of arcs, not one arc — GUARDED requires the "
            "SPECIFIC discharging arc (§4.1), and a range lets every arc in it "
            "point at the next one. Expected exactly 'ARC NNN'"
        )
    named = re.findall(GUARD_OWNER_PATTERN, owner)
    if len(named) > 1:
        return (
            f"{owner!r} names {len(named)} arcs {named} — GUARDED requires exactly "
            "one discharging arc (§4.1). Expected exactly 'ARC NNN'"
        )
    return (
        f"{owner!r} is not a single arc identifier — expected exactly 'ARC NNN' "
        "(the literal 'ARC', one space, three digits), with the prose about WHY "
        "kept in the ledger rather than in the owner field"
    )


#: OPERATOR RULING (ARC 027, discharging CHECK-DEBT D2.31). **A guard may be
#: RE-OWNED at most twice.** Two re-ownings means the debt has been carried by
#: three arcs; the THIRD re-owning is a FAIL, not a fourth deferral.
#:
#: This is the fourth iteration of one flaw and it closes the last route. ARC 024
#: required a non-empty owner and `"ARC 025+"` passed it. ARC 025 required exactly
#: one arc and `"ARC 025"` passed it, then ARC 025 closed with the guard standing.
#: ARC 026 required the named arc to be OPEN — and left the one move that rule
#: cannot see: re-point the marker at the next arc at every arc boundary, forever.
#: Every individual move is honest, visible, and single-arc. The SEQUENCE is the
#: unpaid debt, and no rule that judges one value can see a sequence.
GUARD_REOWN_CEILING = 2


def reowning_defect(
    lineage: tuple[str, ...], ceiling: int = GUARD_REOWN_CEILING
) -> str:
    """Why this guard's owner LINEAGE has exhausted the deferral ceiling, or `''`.

    `lineage` is the ordered sequence of owner values as **committed**, oldest
    first, with consecutive duplicates already collapsed by the caller — one entry
    per *change of owner*. `len(lineage) - 1` is therefore the number of
    RE-OWNINGS, which is the quantity the ruling bounds.

    ## Why transitions and not the size of the distinct SET

    `A -> B -> A` is two deferrals, not one. A set-based count would let a guard
    be walked around a short cycle of arc numbers indefinitely at a constant
    apparent cost, which is the same defect wearing a different shape.

    ## debug.md §7.12 — what would have to be true for this to pass while counting nothing

    1. **The lineage could be read from the WORKING TREE**, where it is always one
       value, so the count would be 0 forever. *Closed at the caller:* the lineage
       is derived from the declaring file's git history — the one record the hand
       making the re-owning cannot edit in the same motion (the property
       `check_artifact_gate_coverage._high_water_mark` already established, and
       the reason this is an extension of that walk rather than a second one).
    2. **A revision that will not parse could be SKIPPED**, and the skipped
       revision could be exactly the one that changed the owner. *Closed at the
       caller:* an unreadable revision is an ERROR, never a skip.
    3. **The history could be TRUNCATED** by the caller's own history limit, which
       drops the OLDEST revisions — precisely where the earliest owners live. A
       truncated lineage is a LOWER BOUND. *Closed at the caller:* a lower bound
       that already exceeds the ceiling is still conclusive and still FAILS, but a
       lower bound at or under the ceiling proves nothing and is CANNOT_MEASURE.
    4. **The lineage could be EMPTY** — no committed history at all — and
       `len(()) - 1 == -1` would compare as comfortably under any ceiling.
       *Closed here:* an empty lineage is a defect in its own right, because a
       guard whose owner has never been committed has no record to bound.

    This function owns the RULE and nothing else; the caller owns the derivation.
    Splitting them is what lets the rule be unit-tested without a git repository
    and lets the derivation be planted without re-stating the arithmetic.
    """
    if not lineage:
        return (
            "the guard owner has NO committed history — a re-owning ceiling "
            "cannot be applied to a marker whose lineage is unrecorded, and an "
            "absent record must never read as a lineage of length zero"
        )
    reownings = len(lineage) - 1
    if reownings <= ceiling:
        return ""
    return (
        f"the guard has been RE-OWNED {reownings} times, exceeding the ceiling of "
        f"{ceiling} (operator ruling, ARC 027, CHECK-DEBT D2.31). Committed owner "
        f"lineage, oldest first: {' -> '.join(repr(name) for name in lineage)}. "
        f"{reownings + 1} arcs have now carried this deferral. Each move was a "
        "single live arc and passed every per-value rule; the SEQUENCE is the "
        "unpaid debt. GUARDED escalates to FAIL: discharge the guard, or take "
        "the red — it may not be walked forward again"
    )


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


def _guarded_defect(result: CheckResult, home: Path | None) -> str:
    """Why this GUARDED verdict may not stand, or `''`.

    Split out of `validate_result` so the §5 rules stay one flat chain of guard
    clauses; the GUARDED arm is the only one that has to go to disk.

    ARC 025. The ARC 024 rule was `not guard_owner.strip()`, which is the right
    shape and the wrong strength: `"ARC 025+"` is non-empty and is still nobody.

    ARC 026 (B2). Shape was never the property either. `ARC 025` is a perfect
    single-arc identifier and ARC 025 is over, so the only live guard on the tree
    was pointing at history — the third route to doctrine B.3's furniture.
    Dischargeability needs the completion record, so it needs a tree; with no
    tree the arm is OFF, and an arm that is off must say so rather than letting
    the verdict stand as if it had run. **FAIL CLOSED:** an unreadable completion
    record is a rejection naming the reason, never a quiet pass-through.
    """
    completed: frozenset[int] | None = None
    if home is not None:
        completed, completion_error = completed_arcs(home)
        if completion_error:
            return (
                "engine: GUARDED rejected — the discharging arc cannot be "
                f"checked against the completion record: {completion_error}"
            )
    defect = guard_owner_defect(result.guard_owner, completed)
    return f"engine: GUARDED rejected — {defect}" if defect else ""


def validate_result(result: CheckResult, home: Path | None = None) -> CheckResult:
    """Enforce §5 mechanically rather than trusting the check author.

    A PASS with no evidence measured nothing; a FAIL with no site cannot say
    what is wrong. Both are downgraded to CANNOT_MEASURE — the honest answer
    is 'unknown', never a false assurance.

    `home` (ARC 026, B2) turns on the DISCHARGEABILITY arm of the guard-owner
    rule, which needs to read the completion record and therefore needs a tree.
    Every shipped caller passes it — `engine._execute_inner` from `ctx.nix_home`
    and `actuation.standalone_main` from the resolved home — and
    `scripts/tests/test_status_contract.py` asserts that they do, rather than
    leaving it to convention. **That assertion is the point:** an arm that is
    live only when a caller remembers an argument is an arm that is off, and
    "off but present" is the shape of every gate this project has caught passing
    while measuring nothing.
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
    elif result.status is Status.GUARDED:
        reason = _guarded_defect(result, home)
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
