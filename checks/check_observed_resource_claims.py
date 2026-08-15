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

## BOTH DOCUMENTED LAUNCH MODES, OR IT IS NOT MEASURED (CHECK-DEBT D3.140)

An observation is made by a child process, and the interpreter that runs that
child is an INPUT to the result. D3.140 measured what that hides, on this tree,
at one commit, with nothing changed but the launch: `check_extract_sources`
spawns `sys.executable` and declares `subprocess:python`, which `covers` matches
by basename. Under `.venv/bin/python` the declaration is TRUE and this gate said
CANNOT_MEASURE; under `/usr/bin/python3` the same declaration is FALSE and this
gate said FAIL. **Both verdicts were correct. Which one you got depended on how
the run was launched, and nothing in the report said so.**

`verify.py` documents both launch modes — its own docstring ("Stdlib only (§9.1)
so it runs under system python3 before .venv exists") and every
`nix-verify*.service` `ExecStart` pin the system interpreter, while a developer
runs it from the venv. So a declaration verified under ONE of two supported
launch modes is UNMEASURED in the other, and this gate now sweeps the population
under BOTH before it may report PASS.

**The gate that would measure nothing here is the one that runs the same
interpreter twice**, so the distinction is PROVEN rather than assumed, and it is
proven from what the children report about themselves:

* each documented interpreter is RUN and asked for its own `sys.executable`
  before any sweep starts — an executable bit is not an interpreter;
* the two reported values must DIFFER, and if they do not, the verdict is
  CANNOT_MEASURE naming both. **`os.path.realpath` is deliberately NOT the
  discriminator**: on this box `.venv/bin/python` is a symlink to
  `/usr/bin/python3.14` and so is `/usr/bin/python3`, so realpath collapses the
  two launch modes into one and a realpath test would refuse to measure a split
  that is live and reproducible. What differs — and what `covers` matches on —
  is `sys.executable` itself, and its basename;
* every child's reported interpreter is compared against the one that was
  requested, so "I asked for the system interpreter" cannot be mistaken for
  "the system interpreter ran".

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
6. **The two "different" interpreters could be the same one** (ARC 032, D3.140)
   — sweeping `sys.executable` twice, or resolving both launch modes to one
   path, produces two identical passes and reads exactly like a declaration
   proven under both. *Closed:* each documented interpreter is run and asked for
   its own `sys.executable` before any sweep, the two answers must DIFFER, and
   every child's reported interpreter is compared against the one requested. Any
   of those failing is `CANNOT_MEASURE` naming the interpreters — never PASS.
7. **One documented launch mode could be absent from the box** (ARC 032, D3.140)
   — a missing `/usr/bin/python3` would leave one sweep to carry a verdict about
   two. *Closed:* an interpreter that cannot be run is `CANNOT_MEASURE` naming
   which one and why, per check-contract rule 10 / §17. A safety property proven
   while one of its two subjects is unavailable is not proven.

## What this gate CANNOT prove

It reports what ONE EXECUTION did. A check that dials 4002 only on a code path
this box does not take is unobserved. That residual is real, it is strictly
narrower than D2.27's (which admitted no runtime evidence at all), and it is
recorded rather than implied.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess  # nosec B404 - fixed argv, shell=False, interpreter probe only
import sys
import time
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status
from nixverify.declarations import Declaration, read_all
from nixverify.observe import (
    ObservedRun,
    documented_interpreters,
    observe_check,
    undeclared,
)

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
#: observed run (§4.4). It moved 120 -> 240 in ARC 032 because the BOUND moved:
#: the gate now sweeps the population once per documented launch mode. The real
#: wall clock WAS measured (ARC 032, this tree: 43.337s + 43.212s = 86.7s over
#: 50 checks) and it is evidence that the bound is adequate — it is NOT where
#: this number comes from, and moving it to track a measured run would be the
#: moving anchor §4.4 and doctrine C.4 both forbid.
EXPECTED_S = 240.0
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

#: Wall-clock ceiling on the WHOLE gate — BOTH launch-mode sweeps together, not
#: each. Exhausting it makes the remaining checks CANNOT_MEASURE, never
#: silently-absent: a gate whose scope quietly shrinks under load is this
#: project's recurring defect class. Doubled in ARC 032 with the second sweep.
TOTAL_BUDGET_S = 240.0

#: Ceiling on the one-line "what are you?" probe. An interpreter that cannot
#: answer that in this long is not one this gate can sweep under.
PROBE_TIMEOUT_S = 30.0

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
    #: Every launch mode under which this exact finding was observed (D3.140).
    #: A tuple and not a string because the same finding usually holds under
    #: both, and a report that printed it twice would bury the one that holds
    #: under only ONE — which is the entire subject of D3.140. Empty for
    #: findings that are not an observation at all (the registry arm below).
    interpreters: tuple[str, ...] = ()


def classify(
    observed: ObservedRun, declaration: Declaration, nix_home: Path
) -> tuple[Finding, ...]:
    """Compare one observation with one declaration, TAGGED with its launch mode.

    The comparison is `_compare`'s; this adds the one fact D3.140 proved the
    result is meaningless without — WHICH interpreter made the observation. It
    is taken from the child's own report (`ObservedRun.interpreter`), never from
    what the caller asked for.
    """
    modes = (observed.interpreter,) if observed.interpreter else ()
    return tuple(
        dataclasses.replace(finding, interpreters=modes)
        for finding in _compare(observed, declaration, nix_home)
    )


def _compare(
    observed: ObservedRun, declaration: Declaration, nix_home: Path
) -> tuple[Finding, ...]:
    """The comparison rule itself, in one place, launch mode aside.

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


def _sweep(
    home: Path, subjects: list[str], executable: str, deadline: float
) -> tuple[list[ObservedRun], float]:
    """Observe each subject in turn under ONE launch mode, inside the budget.

    `deadline` is an absolute `perf_counter` instant shared by every sweep, not
    a per-sweep allowance: the budget is the GATE's, and a second sweep given a
    fresh budget would let the gate run for twice its declared bound.
    """
    checks_dir = home / "checks"
    started = time.perf_counter()
    runs: list[ObservedRun] = []
    for name in subjects:
        if time.perf_counter() > deadline:
            runs.append(
                ObservedRun(
                    check=name,
                    error=(
                        f"observation budget of {TOTAL_BUDGET_S}s exhausted before "
                        f"this check was reached under {executable} — UNOBSERVED, "
                        "not clean"
                    ),
                )
            )
            continue
        runs.append(observe_check(checks_dir, name, home, executable=executable))
    return runs, round(time.perf_counter() - started, 3)


def _probe_interpreter(path: str) -> tuple[str, str]:
    """RUN one interpreter and ask what it is. Returns (sys.executable, error).

    A path test is not an answer: an executable bit, a dangling symlink and a
    shell wrapper all pass `Path.exists()` and none of them is an interpreter
    this gate can sweep under. The reported `sys.executable` is also the only
    value that can be compared against what the observed children report, which
    is what makes "I ran both launch modes" checkable rather than asserted.
    """
    try:
        proc = subprocess.run(  # nosec B603 - argv built here, no shell
            [path, "-c", "import sys; sys.stdout.write(sys.executable)"],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return "", f"could not be run: {exc!r}"
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-200:]
        return "", f"exited {proc.returncode}: {tail or '-'}"
    reported = proc.stdout.strip()
    if not reported:
        return "", "ran but reported an empty sys.executable"
    return reported, ""


@dataclasses.dataclass(frozen=True)
class LaunchMode:
    """One documented way to launch `verify.py`, PROVEN present (D3.140)."""

    label: str
    #: What this gate asked for.
    requested: str
    #: What the interpreter said it was. The two differ legitimately (a `python3`
    #: symlink), and the REPORTED value is the one every comparison uses.
    reported: str


def _launch_modes(home: Path) -> tuple[tuple[LaunchMode, ...], str]:
    """The documented launch modes, each RUN and identified. Or the refusal.

    Returns `((), reason)` whenever this gate cannot honestly claim to have two
    distinct launch modes to sweep under — a missing interpreter, one that will
    not run, or two that turn out to be the same one. Every one of those is
    CANNOT_MEASURE at the call site and never PASS (rule 10 / §17): a
    declaration verified under one of two supported launch modes is UNMEASURED
    in the other, and two sweeps of the same interpreter measure one.
    """
    modes: list[LaunchMode] = []
    for label, path in documented_interpreters(home):
        reported, error = _probe_interpreter(path)
        if error:
            return (), (
                f"the {label} launch mode ({path}) is UNAVAILABLE — it {error}. "
                "This gate compares declarations against reality under BOTH "
                "interpreters verify.py documents; with one of them missing, "
                "every declaration is UNMEASURED under that launch mode. A "
                "safety property proven while its subject is unavailable is not "
                "proven — CANNOT_MEASURE, never PASS"
            )
        modes.append(LaunchMode(label=label, requested=path, reported=reported))
    identities = [mode.reported for mode in modes]
    if len(set(identities)) < len(identities):
        return (), (
            "the documented launch modes resolved to the SAME interpreter — "
            + "; ".join(f"{m.label} {m.requested} -> {m.reported}" for m in modes)
            + ". Sweeping one interpreter twice measures one launch mode, not "
            "two, and would report a declaration proven under both when it was "
            "proven under neither — CANNOT_MEASURE, never PASS"
        )
    return tuple(modes), ""


def _interpreter_conformance(
    runs: list[ObservedRun], mode: LaunchMode
) -> tuple[Finding, ...]:
    """Findings for children that did not run under the interpreter requested.

    The gap between "I launched `/usr/bin/python3`" and "`/usr/bin/python3` ran"
    is exactly the gap D3.140 lived in, one level down. A child that re-execs,
    that a wrapper redirects, or that a venv `pyvenv.cfg` reparents would report
    a different `sys.executable`, and this mode's sweep would then be a sweep of
    something else wearing its label.
    """
    return tuple(
        Finding(
            check=run_.check,
            verdict=UNKNOWN,
            site=f"{run_.check}:{mode.label}",
            reason=(
                f"{run_.check} was observed for the {mode.label} launch mode "
                f"{mode.requested} (which reports {mode.reported}) but the child "
                f"reported sys.executable={run_.interpreter!r} — this observation "
                f"is not of the {mode.label} launch mode, so that mode is "
                "UNOBSERVED for this check"
            ),
        )
        for run_ in runs
        if run_.measured and run_.interpreter != mode.reported
    )


def _merge(findings: list[Finding]) -> list[Finding]:
    """Collapse one finding seen under several launch modes into one, union-tagged.

    Not cosmetic. A declaration that is false under BOTH interpreters and one
    that is false under ONE are different findings with different repairs, and a
    report that printed each sweep's findings end to end would render them
    identically apart from a duplicate line.
    """
    order: list[tuple[str, str, str, str]] = []
    modes: dict[tuple[str, str, str, str], list[str]] = {}
    for finding in findings:
        key = (finding.check, finding.verdict, finding.site, finding.reason)
        if key not in modes:
            modes[key] = []
            order.append(key)
        for interpreter in finding.interpreters:
            if interpreter not in modes[key]:
                modes[key].append(interpreter)
    return [
        Finding(
            check=key[0],
            verdict=key[1],
            site=key[2],
            reason=key[3],
            interpreters=tuple(modes[key]),
        )
        for key in order
    ]


def _detail(finding: Finding) -> str:
    """One finding's message, NAMING the launch mode(s) it was observed under.

    Rule 11 / §18: a can-fail control asserts the REASON, and after D3.140 the
    reason for a resource finding is incomplete without the interpreter — the
    same declaration was true under one and false under the other, and a message
    that omitted which would send a reader to look for a defect that is only
    there half the time.
    """
    if not finding.interpreters:
        return finding.reason
    return f"{finding.reason} [observed under: {', '.join(finding.interpreters)}]"


#: One launch mode's whole sweep: what ran it, what it saw, how long it took.
Sweep = tuple[LaunchMode, list[ObservedRun], float]


def _sweep_all(
    home: Path, subjects: list[str], modes: tuple[LaunchMode, ...]
) -> list[Sweep]:
    """One sweep of the whole population per launch mode, under ONE budget.

    The deadline is computed once and shared: the budget is the GATE's, and
    giving each sweep a fresh one would let the gate run for as many times its
    declared bound as there are launch modes.
    """
    deadline = time.perf_counter() + TOTAL_BUDGET_S
    sweeps: list[Sweep] = []
    for launch in modes:
        # The REQUESTED path, not the reported one: the documented launch mode
        # is the argv `install.sh` and a developer actually type, and a sweep
        # that silently substituted the resolved path would stop exercising it.
        runs, elapsed = _sweep(home, subjects, launch.requested, deadline)
        sweeps.append((launch, runs, elapsed))
    return sweeps


def _findings(
    sweeps: list[Sweep], declarations: dict[str, Declaration], home: Path
) -> list[Finding]:
    """Every sweep's comparison, plus its interpreter-conformance arm, merged."""
    findings: list[Finding] = []
    for launch, runs, _ in sweeps:
        for run_ in runs:
            findings.extend(classify(run_, declarations[run_.check], home))
        findings.extend(_interpreter_conformance(runs, launch))
    return _merge(findings)


def _evidence(
    sweeps: list[Sweep],
    subjects: list[str],
    declarations: dict[str, Declaration],
) -> str:
    """What was measured, stated so a reader can tell it apart from an opinion.

    Names EVERY launch mode, both the requested path and what that interpreter
    reported itself to be, and each sweep's wall clock — because after D3.140
    "the declarations were checked" is not a claim anyone can act on without
    knowing which interpreters did the checking.
    """
    per_mode = "; ".join(
        f"{launch.label}={launch.requested} -> {launch.reported} ({elapsed}s)"
        for launch, _, elapsed in sweeps
    )
    observed_total = sum(len(r.claims) for _, runs, _ in sweeps for r in runs)
    compared = sum(1 for name in subjects if declarations[name].declares_resources)
    return (
        f"{len(subjects)} check(s) observed under {len(sweeps)} DISTINCT documented "
        f"launch mode(s) [{per_mode}]; {observed_total} runtime resource claim(s) "
        f"recorded; {compared} check(s) had a RESOURCES declaration to compare "
        "against. Observed classes: sockets, unix sockets, file WRITES, "
        "subprocesses. NOT observed: file reads, resource use inside spawned "
        "children, and code paths this run did not take."
    )


def _verdict(findings: list[Finding], evidence: str) -> CheckResult:
    """Aggregate findings with the engine's own dominance order: FAIL > ?? > PASS."""
    failures = [f for f in findings if f.verdict == FAIL]
    if failures:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site="; ".join(f.site for f in failures),
            evidence=evidence,
            detail="; ".join(_detail(f) for f in failures),
        )
    unknowns = [f for f in findings if f.verdict == UNKNOWN]
    if unknowns:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            evidence=evidence,
            detail="; ".join(_detail(f) for f in unknowns),
        )
    return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Observe the population under BOTH documented launch modes and compare.

    Both, before it may report PASS (CHECK-DEBT D3.140). The launch mode is an
    input to every observation this gate makes, and one sweep answers for one
    input.
    """
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

    modes, refusal = _launch_modes(home)
    if refusal:
        return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=refusal)

    sweeps = _sweep_all(home, subjects, modes)
    every_run = [run_ for _, runs, _ in sweeps for run_ in runs]
    if not any(run_.claims for run_ in every_run):
        # NON-VACUITY, ASSERTED EVERY RUN (doctrine C.3, §5.3). Not one claim
        # anywhere means the audit hook is not firing, and a disarmed observer
        # reports a clean tree that it never looked at.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=(
                f"the observer recorded ZERO claims across all {len(subjects)} "
                f"checks under {len(modes)} launch mode(s) — that is the signature "
                "of a disarmed observer, not of a population that touches nothing"
            ),
        )

    findings = _findings(sweeps, declarations, home)
    coschedule = _coscheduling_defect(home)
    if coschedule is not None:
        findings.append(coschedule)
    return _verdict(findings, _evidence(sweeps, subjects, declarations))


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
