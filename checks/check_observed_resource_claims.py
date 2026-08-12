#!/usr/bin/env python3
"""Gate: every check's DECLARED `RESOURCES` accounts for what it ACTUALLY touches.

ARC 025, closing CHECK-DEBT **D2.27**.

D2.27 reads: *"disjointness is proven over declarations, never over actual
resource use, and no static mechanism can close that gap."* Every word of that is
true of static mechanisms. `optimize.py` is static and keeps that bound. This
gate is **dynamic**: it runs each registered check under
`nixverify.observe`'s audit-hook observer, records what the check really did, and
compares that against what the check said it would do.

**The residual D2.27 names is a FALSE DECLARATION** — a check that declares
`RESOURCES = ()` while dialling 4002 — and the row itself says *"this is D3.16
one level up: a claim that names a subject it never drives."* D3.16 was closed by
making the gate DRIVE its subject. This closes the same shape one level up by
making the declaration MEASURED rather than trusted.

## The split with `optimize.py` — doctrine C.9, stated in both files

* `optimize._disjointness` owns **declaration versus declaration** ("do these two
  checks claim the same thing?") and owns **absence of a declaration** ("this
  check never said, so it is ineligible for a parallel block").
* This gate owns **declaration versus reality** ("is what it said TRUE?").

This gate therefore never re-derives disjointness and never reddens a check for
declaring nothing — an undeclared check has made no statement, and you cannot
call a statement false when none was made. That case is `CANNOT_MEASURE` here and
is already loud in `--optimize`.

## THE MASKED-HAZARD RULE — the load-bearing sentence of this file

**A SAFETY PROPERTY PROVEN WHILE ITS SUBJECT IS UNAVAILABLE IS NOT PROVEN.**

The IB Gateway on this box is down. Both Gateway gates get `ECONNREFUSED`, and a
naive observer would record two gates that touched nothing and report green over
the exact collision ARC 024 measured (D1.41). So:

* the connect ATTEMPT is an observed claim regardless of outcome — the port being
  dead today says nothing about tomorrow;
* and any check whose run hit an unreachable endpoint returns **`CANNOT_MEASURE`,
  never `PASS`**, naming the endpoint and the errno, because everything
  downstream of that connect did not execute and is therefore unobserved.

## debug.md §7.12 — the standing question

**What would have to be true for this gate to PASS while measuring nothing?**

1. **The observer could be disarmed** — an audit hook that never fires records
   zero claims for every check, which reads identically to a population that
   touches nothing. *Closed:* zero claims across the WHOLE population is
   `CANNOT_MEASURE` naming the observer itself, asserted on every run.
2. **The population could be empty or tiny** — an empty `checks/` yields "nothing
   undeclared, PASS". *Closed:* `MIN_CREDIBLE_CHECKS`, a floor and not the
   current count.
3. **Every check could decline to declare** — comparing nothing to nothing is a
   green that measured nothing. *Closed:* undeclared is `CANNOT_MEASURE`, and
   `CANNOT_MEASURE` dominates `PASS` in this gate's aggregate exactly as it does
   in the engine's.
4. **The vocabulary could be permissive** — a `covers()` that returns True for
   everything turns every finding into a pass. *Closed:* the table is small,
   closed, unit-tested directly in `test_observe.py`, and an unrecognised
   declared token matches by exact string equality only.
5. **The observations could all have failed** — a child that crashes for every
   check leaves an empty finding set. *Closed:* an unmeasured observation is a
   `CANNOT_MEASURE` finding for that check, never an absence.

## What this gate CANNOT prove

It reports what ONE EXECUTION did. A check that dials 4002 only on a code path
this box does not take is unobserved. That residual is real, it is strictly
narrower than D2.27's (which admitted no runtime evidence at all), and it is
recorded rather than implied.
"""

from __future__ import annotations

import dataclasses
import json
import sys
import time
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status
from nixverify.declarations import Declaration, read_all
from nixverify.observe import ObservedRun, observe_check, undeclared

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

DEPENDS_ON: tuple[str, ...] = ()
#: This gate RE-EXECUTES every other registered check in a child process, so it
#: transitively touches everything they touch. That claim cannot be spelled as a
#: literal without restating the population (directive 3), so it is declared as
#: one opaque token AND enforced structurally instead: `_coscheduling_defect`
#: reads `registry.json` every run and FAILS if this check has been placed in a
#: parallel block beside anything else. A declaration nobody can compute is
#: replaced by a measurement anybody can.
RESOURCES: tuple[str, ...] = ("reexecution-of-every-registered-check",)
TIME_BOUND = True
#: Derived from TOTAL_BUDGET_S below — this gate's own bound — never from an
#: observed run (§4.4).
EXPECTED_S = 120.0
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the repair for a false declaration is a human deciding what the check really "
    "claims; an instrument that rewrote RESOURCES to match what it just observed "
    "would make every declaration true by construction and measure nothing"
)
SUBJECTS: tuple[str, ...] = ("scripts/nixverify/observe.py",)

NAME = "check_observed_resource_claims"
REGISTRY = "registry.json"

#: Below this the population is not credible and the gate refuses to report.
#: A floor, not today's count — a threshold equal to the current number is an
#: anchor that moves (doctrine C.4).
MIN_CREDIBLE_CHECKS = 5

#: Wall-clock ceiling on the WHOLE sweep. Exhausting it makes the remaining
#: checks CANNOT_MEASURE, never silently-absent: a gate whose scope quietly
#: shrinks under load is this project's recurring defect class.
TOTAL_BUDGET_S = 120.0

FAIL = "fail"
UNKNOWN = "cannot_measure"
OK = "pass"  # nosec B105 - verdict token, not a credential


@dataclasses.dataclass(frozen=True)
class Finding:
    """One check's comparison of declaration against reality."""

    check: str
    verdict: str
    site: str
    reason: str


def classify(
    observed: ObservedRun, declaration: Declaration, nix_home: Path
) -> tuple[Finding, ...]:
    """Compare one observation with one declaration. The whole rule, in one place.

    **Order is the ruling.** A positively-observed undeclared claim outranks
    masking: it is direct evidence of a false declaration, and a check that was
    caught dialling an endpoint it did not declare has been caught whether or not
    something else about the run was unobservable. Only when there is no such
    evidence does unreachability decide, and it decides toward CANNOT_MEASURE.
    """
    if not observed.measured and not observed.claims:
        return (Finding(observed.check, UNKNOWN, observed.check, observed.error),)

    if declaration.declares_resources:
        missing = undeclared(observed.claims, declaration.resources, nix_home)
        if missing:
            return tuple(
                Finding(
                    check=observed.check,
                    verdict=FAIL,
                    site=f"{observed.check}:{claim}",
                    reason=(
                        f"{observed.check} was OBSERVED using {claim} and its "
                        f"declaration RESOURCES={list(declaration.resources)} does "
                        "not account for it — a false declaration (D2.27)"
                    ),
                )
                for claim in missing
            )

    if observed.unreachable:
        endpoints = ", ".join(
            f"{target} ({code})" for target, code in observed.unreachable
        )
        return (
            Finding(
                check=observed.check,
                verdict=UNKNOWN,
                site=f"{observed.check}:{observed.unreachable[0][0]}",
                reason=(
                    f"{observed.check} could not reach {endpoints}; the attempt is "
                    "recorded as a claim, but everything downstream of it did not "
                    "execute, so this check's remaining resource use is UNOBSERVED. "
                    "A safety property proven while its subject is unavailable is "
                    "not proven — CANNOT_MEASURE, never PASS"
                ),
            ),
        )

    if not observed.measured:
        return (Finding(observed.check, UNKNOWN, observed.check, observed.error),)

    if not declaration.declares_resources:
        return (
            Finding(
                check=observed.check,
                verdict=UNKNOWN,
                site=observed.check,
                reason=(
                    f"{observed.check} declares no RESOURCES, so there is no "
                    f"statement to falsify; OBSERVED {list(observed.claims)}. "
                    "Undeclared is `--optimize`'s property, not this gate's"
                ),
            ),
        )

    return (
        Finding(
            check=observed.check,
            verdict=OK,
            site="",
            reason=(
                f"{observed.check}: declared {list(declaration.resources)} accounts "
                f"for observed {list(observed.claims)}"
            ),
        ),
    )


def _coscheduling_defect(home: Path) -> Finding | None:
    """FAIL if the registry puts this gate in a parallel block beside anything else.

    This gate's real resource claim is the union of everything it re-executes, and
    that union cannot honestly be written as a literal. Rather than declare a
    convenient fiction, the hazard the declaration would have prevented is
    measured directly: co-scheduled with the Gateway gates, this gate's child
    would dial 4002 concurrently with them — D1.41 reintroduced by the very
    instrument built to catch it.
    """
    path = home / "checks" / REGISTRY
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Finding(NAME, UNKNOWN, str(path), f"registry unreadable: {exc!r}")
    for block in payload.get("blocks", []):
        members = list(block.get("checks", []))
        if NAME in members and block.get("parallel", False) and len(members) > 1:
            others = [name for name in members if name != NAME]
            return Finding(
                check=NAME,
                verdict=FAIL,
                site=f"{REGISTRY}:{block.get('name', '?')}",
                reason=(
                    f"{NAME} is in PARALLEL block {block.get('name', '?')!r} beside "
                    f"{others} — it re-executes every registered check, so it "
                    "transitively claims every resource they claim and can never "
                    "share a parallel block"
                ),
            )
    return None


def _sweep(home: Path, subjects: list[str]) -> tuple[list[ObservedRun], float]:
    """Observe each subject in turn, inside the gate's own wall-clock budget."""
    checks_dir = home / "checks"
    started = time.perf_counter()
    runs: list[ObservedRun] = []
    for name in subjects:
        if time.perf_counter() - started > TOTAL_BUDGET_S:
            runs.append(
                ObservedRun(
                    check=name,
                    error=(
                        f"observation budget of {TOTAL_BUDGET_S}s exhausted before "
                        "this check was reached — UNOBSERVED, not clean"
                    ),
                )
            )
            continue
        runs.append(observe_check(checks_dir, name, home))
    return runs, round(time.perf_counter() - started, 3)


def _verdict(findings: list[Finding], evidence: str) -> CheckResult:
    """Aggregate findings with the engine's own dominance order: FAIL > ?? > PASS."""
    failures = [f for f in findings if f.verdict == FAIL]
    if failures:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site="; ".join(f.site for f in failures),
            evidence=evidence,
            detail="; ".join(f.reason for f in failures),
        )
    unknowns = [f for f in findings if f.verdict == UNKNOWN]
    if unknowns:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            evidence=evidence,
            detail="; ".join(f.reason for f in unknowns),
        )
    return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Observe the whole registered population and compare against declarations."""
    home = Path(ctx.nix_home)
    declarations = read_all(home / "checks")
    # Never observe itself: the child would load this module and sweep again.
    subjects = sorted(name for name in declarations if name != NAME)
    if len(subjects) < MIN_CREDIBLE_CHECKS:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=(
                f"only {len(subjects)} observable check(s) found under "
                f"{home / 'checks'}, below the credibility floor of "
                f"{MIN_CREDIBLE_CHECKS} — a tiny population makes every "
                "declaration trivially true"
            ),
        )

    runs, elapsed = _sweep(home, subjects)
    if not any(run_.claims for run_ in runs):
        # NON-VACUITY, ASSERTED EVERY RUN (doctrine C.3, §5.3). Not one claim
        # anywhere means the audit hook is not firing, and a disarmed observer
        # reports a clean tree that it never looked at.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=(
                f"the observer recorded ZERO claims across all {len(subjects)} "
                "checks — that is the signature of a disarmed observer, not of a "
                "population that touches nothing"
            ),
        )

    findings: list[Finding] = []
    for run_ in runs:
        findings.extend(classify(run_, declarations[run_.check], home))
    coschedule = _coscheduling_defect(home)
    if coschedule is not None:
        findings.append(coschedule)

    observed_total = sum(len(run_.claims) for run_ in runs)
    compared = sum(1 for name in subjects if declarations[name].declares_resources)
    evidence = (
        f"{len(subjects)} check(s) observed in {elapsed}s; {observed_total} runtime "
        f"resource claim(s) recorded; {compared} check(s) had a RESOURCES "
        f"declaration to compare against. Observed classes: sockets, unix sockets, "
        f"file WRITES, subprocesses. NOT observed: file reads, resource use inside "
        f"spawned children, and code paths this run did not take."
    )
    return _verdict(findings, evidence)


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
