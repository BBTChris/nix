#!/usr/bin/env python3
"""§12.2's crash-loop breaker, DRIVEN UNTIL IT TRIPS — `scripts/nixrisk/supervision.py`.

ONE gate, FOUR properties, and the first of them is the one a gate over a
breaker most easily fails to have: **that the cap is actually reached.** A drive
that restarts a subject twice under a cap of three exercises none of the
tripping branch, and would pass over a breaker whose HALT call had been deleted.

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md` unless another document
is named on the same line.

THE FOUR ARMS

  1. **THE CAP TRIPS.** `max` restarts inside the window, then `max + 1`, driven
     through the SHIPPED `CrashLoopBreaker` against the SHIPPED knobs, and the
     §12.5 `HaltCause.CRASH_LOOP` is read back off the HALT double together with
     the reason string and the alert code. Never an exit code (check contract
     v2 §11).
  2. **THE WINDOW IS REAL, AND ITS BOUNDARY INSTANT IS DRIVEN FROM BOTH SIDES.**
     `max` restarts spread across the window must NOT trip; a restart exactly
     `window_s` old must have EXPIRED and one epsilon younger must still count.
     A falsifier (`_NoWindow`) that counts every restart ever is driven through
     the same spacing and must TRIP, so the negative assertion is proven able to
     fail.
  3. **THE STRATEGY CAP QUARANTINES WITHOUT HALTING** (§4:272-274 — *"while the
     rest of the system keeps trading"*), and the two scopes' wirings are proven
     to be REFUSED when crossed.
  4. **THE SHIPPED SYSTEMD DROP-IN CARRIES THE POLICY THE KNOBS DECLARE**, both
     sides derived: the expected burst and interval come from
     `risks/supervision.config.json` through `SupervisionKnobs`, never from a
     literal in this gate. Then the actuator `scripts/nix_crash_loop_halt.py` is
     driven as a REAL SUBPROCESS, three times, which is how systemd will drive
     it — and the §12.5:634-638 HALT MARKER is read back off disk.

WHY DRIVE RATHER THAN SHELL OUT TO PYTEST. The runtime `.venv` `verify.py` runs
under has no pytest, so a gate that shelled to pytest would be CANNOT_MEASURE on
every real run. This gate imports the modules straight out of `ctx.nix_home`
(the `check_flatten` pattern: path-keyed import with `sys.modules`/`sys.path`
restored) and drives them with hand-built doubles.

§7.12 — WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING?

 1. **The subject could fail to import.** CLOSED: an import failure is
    CANNOT_MEASURE naming the exception (§17), never a PASS.
 2. **The cap could never be reached**, leaving the whole tripping branch
    unexercised. CLOSED: ARM 1 drives `max` and `max + 1` restarts and requires
    the HALT; a run in which no trip occurred is itself a finding.
 3. **The gate could read its expected cap out of the breaker it is judging.**
    CLOSED: the expected figures are read from `risks/supervision.config.json`
    through `scripts/risk_config.py` — a DIFFERENT artifact from the subject —
    and ARM 4 additionally requires the shipped drop-in to agree with them.
 4. **The window could be untested**, so a breaker with no window would pass.
    CLOSED: ARM 2 drives the across-boundary case, the boundary instant from
    both sides, and a falsifier that must trip where the subject must not.
 5. **The systemd half could be asserted rather than measured.** CLOSED: the
    drop-in is PARSED and its directives compared against the knobs, and the
    actuator is run as a subprocess whose JSON and whose written marker are read
    back. What is NOT measured is stated in the evidence: nothing is installed,
    nothing is enabled, no unit on this box is wired to the breaker, and this
    gate takes no `systemctl` action of any kind.
 6. **A green could imply score handling across death works.** CLOSED: the
    evidence PRINTS `supervision.SCORE_BOUNDARY`, which says §4:275-280's
    persist/archive rule is R5 and is not implemented.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code,too-few-public-methods,too-many-locals
# missing-function-docstring,missing-class-docstring: the doubles' verbs are
# named after the ports they stand in for and each arm's name states its own
# property. too-few-public-methods: one-verb stand-ins. too-many-locals: an
# arm's local count is the drive's own inputs and outputs.
# pylint: disable=missing-function-docstring,missing-class-docstring
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = False
DEPENDS_ON: tuple[str, ...] = ()
#: This gate IMPORTS `nixrisk` out of `ctx.nix_home` (shared interpreter import
#: state), RUNS `scripts/nix_crash_loop_halt.py` as a subprocess with the same
#: interpreter, and WRITES its scratch ledger and marker under `/tmp`. Rule 12:
#: declared claims are checked against OBSERVED ones, so every one of those is
#: named here rather than left to be discovered. BOTH interpreter spellings are
#: declared because the observed one depends on WHO RUNS THE GATE: standalone it
#: is the `.venv` `python`, under `verify.py` it is `/usr/bin/python3`, and
#: `check_observed_resource_claims` measured exactly that difference on the
#: first run of this gate.
RESOURCES: tuple[str, ...] = (
    "interpreter:sys.modules",
    "interpreter:sys.path",
    "subprocess:python",
    "subprocess:python3",
    "file-write:/tmp",
)
#: NON-CORRECTABLE: the subject is risk-path source (the §12.2 breaker that
#: declares a money-gating HALT) plus a systemd policy file. A gate empowered to
#: edit either until its own drive came back clean would manufacture green over
#: the mechanism that stops a crash loop from trading.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is risk-path source (scripts/nixrisk/supervision.py declares a "
    "§12.5 HALT) and a systemd unit policy; a repair that edited either to "
    "satisfy its own gate is the class of action risk spec §4 forbids on the "
    "order path, and on the systemd side would be an outward-facing act"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/nixrisk/supervision.py",
    "scripts/nix_crash_loop_halt.py",
    "risks/supervision.config.json",
)

NAME = "check_supervision"

SUPERVISION_FILE = "scripts/nixrisk/supervision.py"
ACTUATOR_FILE = "scripts/nix_crash_loop_halt.py"
DROP_IN_FILE = "scripts/nix-supervision.conf"
UNIT_FILE = "scripts/nix-crash-loop-halt@.service"
PACKAGE = "nixrisk"


class Finding(NamedTuple):
    site: str
    why: str


class Loaded(NamedTuple):
    supervision: ModuleType
    halt: ModuleType
    risk_config: ModuleType
    knobs: Any


# --------------------------------------------------------------------------
# LOADING — out of ctx.nix_home, never this process's own tree by accident
# --------------------------------------------------------------------------


def _purge(saved: dict[str, ModuleType]) -> None:
    for name in [
        key for key in sys.modules if key == PACKAGE or key.startswith(f"{PACKAGE}.")
    ]:
        del sys.modules[name]
    sys.modules.update(saved)


def load(home: Path) -> tuple[Loaded | None, str]:
    saved_path = list(sys.path)
    saved_modules = {
        key: value
        for key, value in sys.modules.items()
        if key == PACKAGE or key.startswith(f"{PACKAGE}.")
    }
    saved_rc = sys.modules.pop("risk_config", None)
    _purge({})
    sys.path.insert(0, str((home / "scripts").resolve()))
    importlib.invalidate_caches()
    try:
        supervision = importlib.import_module(f"{PACKAGE}.supervision")
        halt = importlib.import_module(f"{PACKAGE}.halt")
        risk_config = importlib.import_module("risk_config")
        loaded = risk_config.load_risk_configs(home)
        knobs = supervision.SupervisionKnobs.from_config(
            loaded.modules["supervision"].values
        )
        return Loaded(
            supervision=supervision,
            halt=halt,
            risk_config=risk_config,
            knobs=knobs,
        ), ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"cannot load the §12.2 supervision subject out of {home}: "
            f"{type(exc).__name__}: {exc}"
        )
    finally:
        _purge(saved_modules)
        if saved_rc is not None:
            sys.modules["risk_config"] = saved_rc
        else:
            sys.modules.pop("risk_config", None)
        sys.path[:] = saved_path


# --------------------------------------------------------------------------
# Doubles — each records the REASON, never a call count
# --------------------------------------------------------------------------


class _Alerts:
    def __init__(self) -> None:
        self.raised: list[tuple[str, str]] = []

    def alert(self, code: str, message: str) -> None:
        self.raised.append((code, message))


class _Plane2:
    def __init__(self) -> None:
        self.lines: list[tuple[str, dict]] = []

    def emit(self, event: str, **fields: Any) -> str:
        self.lines.append((event, dict(fields)))
        return event


class _Halts:
    def __init__(self) -> None:
        self.sets: list[tuple[Any, str]] = []

    def set(self, cause: Any, reason: str, *, now: float | None = None) -> Any:
        del now
        self.sets.append((cause, reason))
        return cause


def _breaker(loaded: Loaded, tmp: Path, scope: Any, *, cls: Any = None) -> tuple:
    supervision = loaded.supervision
    alerts, plane2 = _Alerts(), _Plane2()
    halts = _Halts() if scope is supervision.BreakerScope.PROCESS else None
    builder = cls or supervision.CrashLoopBreaker
    breaker = builder(
        knobs=loaded.knobs,
        scope=scope,
        ledger=supervision.RestartLedger(tmp),
        alert=alerts,
        plane2=plane2,
        halt=halts,
    )
    return breaker, alerts, plane2, halts


# --------------------------------------------------------------------------
# ARM 1 — THE CAP ACTUALLY TRIPS
# --------------------------------------------------------------------------


def _arm_trips(loaded: Loaded, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{SUPERVISION_FILE}:cap"
    supervision = loaded.supervision
    knobs = loaded.knobs
    cap = knobs.crash_loop_max
    step = knobs.window_s / (cap + 2)

    breaker, alerts, plane2, halts = _breaker(
        loaded, root / "trip.jsonl", supervision.BreakerScope.PROCESS
    )
    verdicts = [
        breaker.record_restart("nix-limiter.service", now=1000.0 + step * i)
        for i in range(cap + 1)
    ]

    early = verdicts[: cap - 1]
    if any(v.tripped for v in early):
        findings.append(
            Finding(
                site,
                f"the breaker tripped BEFORE {cap} restarts: "
                f"{[(v.restarts_in_window, v.tripped) for v in early]} — a cap "
                "that fires early quarantines a process that has not looped",
            )
        )
    at_cap = verdicts[cap - 1]
    if not at_cap.tripped:
        findings.append(
            Finding(
                site,
                f"{cap} restart(s) inside a {knobs.crash_loop_window_min} min "
                f"window did NOT trip the breaker: {at_cap.reason} — §12.2:617 "
                "is 'N restarts in M minutes ⇒ HALT + operator alert'",
            )
        )
    over_cap = verdicts[cap]
    if not over_cap.tripped:
        findings.append(
            Finding(
                site,
                f"{cap + 1} restarts did not trip either: {over_cap.reason} — a "
                "cap that fires only on the exact Nth restart leaves the loop "
                "running from the (N+1)th onward",
            )
        )
    causes = [cause for cause, _ in (halts.sets if halts else [])]
    if loaded.halt.HaltCause.CRASH_LOOP not in causes:
        findings.append(
            Finding(
                site,
                f"the cap was hit and no §12.5 HALT was declared under "
                f"{loaded.halt.HaltCause.CRASH_LOOP.value!r}; causes seen "
                f"{[getattr(c, 'value', c) for c in causes]} — a breaker that "
                "counts and does not stop the money is blind "
                "restart-into-trading with a log line",
            )
        )
    if not any(code == "supervision.crash-loop-halt" for code, _ in alerts.raised):
        findings.append(
            Finding(
                site,
                f"no operator alert was raised at the cap; alerts seen "
                f"{[c for c, _ in alerts.raised]} — §12.2:617's consequence is "
                "HALT **and** operator alert",
            )
        )
    if not any(
        "CRASH-LOOP CAP HIT" in reason for _, reason in (halts.sets if halts else [])
    ):
        findings.append(
            Finding(
                site,
                "the HALT was declared with no reason naming the cap — check "
                "contract v2 §11: the REASON is the assertion, never the code",
            )
        )
    if not any(line[1].get("cap_hit") for line in plane2.lines):
        findings.append(
            Finding(
                site,
                "§12.10:756 routes 'crash-loop count / cap hit' to Plane 2 and "
                f"no emitted line carries cap_hit: {plane2.lines}",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM 2 — THE WINDOW, and its boundary instant, both sides + a falsifier
# --------------------------------------------------------------------------


def _no_window(loaded: Loaded) -> Any:
    supervision = loaded.supervision

    class _NoWindow(supervision.CrashLoopBreaker):  # type: ignore[name-defined,misc]
        """THE FALSIFIER: no window at all — every restart ever counts."""

        def restarts_in_window(self, subject: str, now: float):
            del now
            return tuple(
                rec
                for rec in self._ledger.records()  # pylint: disable=protected-access
                if rec.subject == subject
            )

    return _NoWindow


def _arm_window(loaded: Loaded, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{SUPERVISION_FILE}:window"
    supervision = loaded.supervision
    knobs = loaded.knobs
    cap = knobs.crash_loop_max
    spread = knobs.window_s * 0.8

    across, _, _, halts = _breaker(
        loaded, root / "across.jsonl", supervision.BreakerScope.PROCESS
    )
    spread_verdicts = [
        across.record_restart("u", now=3000.0 + spread * i) for i in range(cap)
    ]
    if any(v.tripped for v in spread_verdicts):
        findings.append(
            Finding(
                site,
                f"{cap} restarts spread {spread}s apart TRIPPED the breaker: "
                f"{spread_verdicts[-1].reason} — that is a breaker with no "
                "window, and the window is the whole tunable (§12.2:617's M)",
            )
        )
    if halts and halts.sets:
        findings.append(
            Finding(site, "a HALT was declared for restarts outside one window")
        )

    # NON-VACUITY, and it is not an arithmetic identity: the SAME spacing must
    # trip a breaker that has no window.
    falsifier, _, _, _ = _breaker(
        loaded,
        root / "falsifier.jsonl",
        supervision.BreakerScope.PROCESS,
        cls=_no_window(loaded),
    )
    falsified = [
        falsifier.record_restart("u", now=3000.0 + spread * i) for i in range(cap)
    ]
    if not falsified[-1].tripped:
        findings.append(
            Finding(
                f"{site}:falsifier",
                "the windowless falsifier did NOT trip on the same spacing, so "
                "the across-boundary assertion above cannot fail and measures "
                "nothing",
            )
        )

    # THE BOUNDARY INSTANT, from both sides. Half-open: `now - ts < window_s`.
    epsilon = 1e-6
    t0 = 5000.0
    for label, third, expect_trip in (
        ("expired", t0 + knobs.window_s, False),
        ("inside", t0 + knobs.window_s - epsilon, True),
    ):
        breaker, _, _, _ = _breaker(
            loaded, root / f"boundary-{label}.jsonl", supervision.BreakerScope.PROCESS
        )
        for i in range(cap - 1):
            breaker.record_restart("u", now=t0 + epsilon * i)
        verdict = breaker.record_restart("u", now=third)
        if verdict.tripped is not expect_trip:
            findings.append(
                Finding(
                    f"{site}:boundary[{label}]",
                    f"the window is HALF-OPEN: a restart exactly "
                    f"{knobs.window_s}s old must have EXPIRED and one epsilon "
                    f"inside must still COUNT. At the {label!r} instant the "
                    f"breaker answered tripped={verdict.tripped}, expected "
                    f"{expect_trip}: {verdict.reason}",
                )
            )
    return findings


# --------------------------------------------------------------------------
# ARM 3 — the STRATEGY cap quarantines and declares NO HALT
# --------------------------------------------------------------------------


def _arm_quarantine(loaded: Loaded, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{SUPERVISION_FILE}:quarantine"
    supervision = loaded.supervision
    cap = loaded.knobs.crash_loop_max

    breaker, alerts, _, _ = _breaker(
        loaded, root / "quarantine.jsonl", supervision.BreakerScope.STRATEGY
    )
    verdict = None
    for i in range(cap):
        verdict = breaker.record_restart("strat-1", now=8000.0 + i)
    if verdict is None or not verdict.quarantined:
        findings.append(
            Finding(
                site,
                f"{cap} restarts did not quarantine the strategy: "
                f"{verdict.reason if verdict else 'no verdict'} — §4:272-274",
            )
        )
    elif verdict.halted:
        findings.append(
            Finding(
                site,
                "quarantining ONE strategy declared a platform HALT — §4:273 "
                "says the rest of the system keeps trading",
            )
        )
    allowed, why = breaker.may_relaunch("strat-1")
    if allowed:
        findings.append(
            Finding(site, f"a quarantined strategy may still relaunch: {why}")
        )
    elif "quarantine-restore" not in why:
        findings.append(
            Finding(
                site,
                f"the refusal does not name §12.11:779's operator verb: {why} — "
                "§4:274 makes the return operator-driven and NOT automatic",
            )
        )
    if not any(code == "supervision.quarantine" for code, _ in alerts.raised):
        findings.append(
            Finding(site, f"no quarantine alert: {[c for c, _ in alerts.raised]}")
        )
    elif not any(
        supervision.SCORE_BOUNDARY in message
        for code, message in alerts.raised
        if code == "supervision.quarantine"
    ):
        findings.append(
            Finding(
                site,
                "the quarantine alert does not carry the R5 scoring boundary — a "
                "quarantine that reads as 'score archived' claims work §4:275-280 "
                "gives to a process that does not exist",
            )
        )

    # Both mis-wirings REFUSED, and the refusal names what it would cost.
    for scope, halt, phrase in (
        (supervision.BreakerScope.PROCESS, None, "needs the §12.5 HALT flag"),
        (supervision.BreakerScope.STRATEGY, _Halts(), "must NOT hold a HALT flag"),
    ):
        try:
            supervision.CrashLoopBreaker(
                knobs=loaded.knobs,
                scope=scope,
                ledger=supervision.RestartLedger(root / "wire.jsonl"),
                alert=_Alerts(),
                plane2=_Plane2(),
                halt=halt,
            )
            findings.append(
                Finding(
                    f"{site}:wiring",
                    f"a {scope.value} breaker wired with halt={halt!r} was "
                    "ACCEPTED — the scope's consequence is not enforced at "
                    "construction, so it is enforced nowhere",
                )
            )
        except supervision.SupervisionUsageError as exc:
            if phrase not in str(exc):
                findings.append(
                    Finding(
                        f"{site}:wiring",
                        f"the refusal for {scope.value} does not name the rule: {exc}",
                    )
                )
    return findings


# --------------------------------------------------------------------------
# ARM 4 — the systemd FILES, and the actuator as a real subprocess
# --------------------------------------------------------------------------


def _arm_systemd(loaded: Loaded, home: Path, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    supervision = loaded.supervision
    site = DROP_IN_FILE

    drop_in = home / DROP_IN_FILE
    unit = home / UNIT_FILE
    for path in (drop_in, unit):
        if not path.is_file():
            findings.append(
                Finding(str(path), "the shipped systemd file is absent from the tree")
            )
    if findings:
        return findings

    policy = supervision.read_unit_policy(drop_in)
    findings.extend(
        Finding(site, defect)
        for defect in supervision.unit_policy_defects(policy, loaded.knobs)
    )
    # NON-VACUITY: the rule must be able to fail. Plant a burst that disagrees
    # with the config and require the reader to say so.
    planted = root / "planted.conf"
    planted.write_text(
        drop_in.read_text(encoding="utf-8").replace(
            f"StartLimitBurst={loaded.knobs.crash_loop_max}", "StartLimitBurst=99"
        ),
        encoding="utf-8",
    )
    if not supervision.unit_policy_defects(
        supervision.read_unit_policy(planted), loaded.knobs
    ):
        findings.append(
            Finding(
                f"{site}:falsifier",
                "a drop-in whose StartLimitBurst disagrees with "
                "risks/supervision.config.json produced NO defect — the policy "
                "reader agrees with anything and measures nothing",
            )
        )

    findings.extend(_arm_actuator(loaded, home, root))
    return findings


def _arm_actuator(loaded: Loaded, home: Path, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    site = ACTUATOR_FILE
    cap = loaded.knobs.crash_loop_max
    ledger = root / "actuator.jsonl"
    marker = root / "actuator.marker"

    reports = []
    for index in range(cap):
        proc = subprocess.run(
            [
                sys.executable,
                str(home / ACTUATOR_FILE),
                "--unit",
                "nix-ibgateway.service",
                "--home",
                str(home),
                "--ledger",
                str(ledger),
                "--marker",
                str(marker),
                "--now",
                repr(10_000.0 + index),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if not proc.stdout.strip():
            findings.append(
                Finding(site, f"the actuator printed nothing; stderr={proc.stderr!r}")
            )
            return findings
        reports.append(json.loads(proc.stdout.strip()))

    counts = [report["restarts_in_window"] for report in reports]
    if counts != list(range(1, cap + 1)):
        findings.append(
            Finding(
                site,
                f"the actuator counted {counts} across {cap} SEPARATE processes, "
                f"expected {list(range(1, cap + 1))} — a restart counter that "
                "does not survive the process counts to one forever",
            )
        )
    if not reports[-1]["cap_hit"]:
        findings.append(
            Finding(site, f"the actuator did not report the cap hit: {reports[-1]}")
        )
    if any(report["cap_hit"] for report in reports[:-1]):
        findings.append(
            Finding(
                site,
                "the actuator reported a cap hit BELOW the cap — §12.2:618 makes "
                "any single restart safe by design",
            )
        )
    if reports[-1]["cap"] != cap or reports[-1]["window_s"] != loaded.knobs.window_s:
        findings.append(
            Finding(
                site,
                f"the actuator ran on cap={reports[-1]['cap']} window="
                f"{reports[-1]['window_s']}s, but risks/supervision.config.json "
                f"says {cap} / {loaded.knobs.window_s}s",
            )
        )
    if not marker.exists():
        findings.append(
            Finding(
                site,
                "the cap was hit and NO §12.5:634-638 HALT marker was written — "
                "the Limiter may BE the crash-looping process, so the marker is "
                "the only record cold-start reconciliation can replay",
            )
        )
        return findings
    entries = [
        json.loads(line) for line in marker.read_text().splitlines() if line.strip()
    ]
    causes = {entry.get("cause") for entry in entries}
    if causes != {loaded.halt.HaltCause.CRASH_LOOP.value}:
        findings.append(
            Finding(
                site,
                f"the marker records causes {sorted(causes)}, expected only "
                f"{loaded.halt.HaltCause.CRASH_LOOP.value!r}",
            )
        )
    if not any("nix-ibgateway.service" in entry.get("reason", "") for entry in entries):
        findings.append(
            Finding(
                site,
                "the marker's reason does not name the failing unit — an audited "
                "HALT that cannot say what crash-looped (§12.5:633)",
            )
        )
    return findings


# --------------------------------------------------------------------------
# VERDICT
# --------------------------------------------------------------------------

ARMS = 4


def _remove_tree(root: Path) -> None:
    """Delete the scratch directory by ABSOLUTE path, never `shutil.rmtree`.

    MEASURED, ARC 026 (`check_state_bus._remove_tree`): on POSIX `rmtree`
    recurses on directory file descriptors and unlinks with a BARE RELATIVE
    name, which no path-rooted RESOURCES declaration can account for.
    """
    if not root.is_dir():
        return
    for child in sorted(root.iterdir()):
        try:
            child.unlink()
        except OSError:
            continue
    try:
        root.rmdir()
    except OSError:
        pass


def _evidence(loaded: Loaded) -> str:
    knobs = loaded.knobs
    return (
        f"{ARMS} arms driving the SHIPPED {SUPERVISION_FILE} at cap="
        f"{knobs.crash_loop_max} window={knobs.crash_loop_window_min}min "
        f"({knobs.window_s}s), READ FROM risks/supervision.config.json and never "
        f"from a literal here: the cap DRIVEN TO A TRIP at {knobs.crash_loop_max} "
        f"and {knobs.crash_loop_max + 1} restarts with the §12.5 "
        f"{loaded.halt.HaltCause.CRASH_LOOP.value!r} cause read back; the window "
        "proven by an across-boundary drive that must NOT trip, a windowless "
        "falsifier that must, and the boundary instant driven from BOTH sides; "
        "the §4:272-274 quarantine proven to raise an alert and declare NO HALT, "
        "with both scope mis-wirings refused; and the shipped drop-in parsed "
        f"against the same knobs plus {ACTUATOR_FILE} driven as "
        f"{knobs.crash_loop_max} REAL subprocesses whose §12.5:634-638 HALT "
        "marker is read back off disk. "
        f"WHAT IS NOT MEASURED — {loaded.supervision.not_installed([UNIT_FILE, DROP_IN_FILE])}; "
        "no unit on this box is wired to the breaker (adoption is one OnFailure= "
        "line per unit and is OWED, not done), and this gate takes no systemctl "
        f"action of any kind. WHAT IS NOT HERE — {loaded.supervision.SCORE_BOUNDARY}"
    )


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    root = Path("/tmp") / f"nix-{NAME}-{id(ctx):x}"
    try:
        loaded, error = load(ctx.nix_home)
        if loaded is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        root.mkdir(parents=True, exist_ok=True)
        findings: list[Finding] = []
        findings += _arm_trips(loaded, root)
        findings += _arm_window(loaded, root)
        findings += _arm_quarantine(loaded, root)
        findings += _arm_systemd(loaded, ctx.nix_home, root)
        evidence = _evidence(loaded)
        if findings:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in findings),
                evidence=evidence,
                detail="; ".join(f"{site}: {why}" for site, why in findings),
            )
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )
    finally:
        _remove_tree(root)


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
