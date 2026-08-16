#!/usr/bin/env python3
"""§12.5's HALT state machine, DRIVEN — `scripts/nixrisk/halt.py`.

ONE gate, SEVEN properties. The wiring in front of the machine was already
proven: `checks/check_limiter_gate.py` ARM 3 shows HALT is read FIRST and that a
HALT pass dispatches no rule at all. Nothing proved anything BEHIND the port,
because until this arc nothing implemented it. These arms are that half.

  1. **THE SIX SETTERS ARE THE SPEC'S OWN SENTENCE.** `HaltCause` is compared
     against the setter list PARSED OUT OF THE FROZEN SPEC at run time, not
     against a list typed here — directive 3. A seventh member, or a renamed
     one, reddens.
  2. **OPERATOR HALT DOES NOT AUTO-CLEAR, AND THE HYBRID DOES.** Driven: an
     operator HALT survives an auto-clear sweep at `now = 1e12`; a stale-data
     HALT clears only after BOTH the condition cleared AND the §12.5:632 floor
     ran; a condition that re-arms cancels the pending clear.
  3. **BOTH PLANES, AND THE ROUTING IS READ OFF §12.10's TABLE.** The inventory
     row is parsed from the frozen document — HALT is Plane 1 ✅ *and* Plane 2
     ✅, blackout/roll is Plane 2 ONLY — and one `set()` is required to produce
     exactly one row on each plane. Plane 2 is then proven write-only across a
     full gate pass (§12.10:740: never read by the trading path).
  4. **HALT GATES ENTRY, NEVER EXIT.** A real `GatePass` denies at branch 0
     while a real `ProtectiveFlatten` fires an exit against the SAME flag, and
     the §3:173 onset sweep cancels pending ENTRY orders while issuing no
     flatten at all.
  5. **THE LIMITER-DOWN CASE, WITH THE LIMITER GENUINELY KILLED.** A child
     process is SIGKILLed at the instant it would have booked the row; the WAL
     is proven not to contain it; a SECOND, FRESH process replays the marker and
     the row appears tagged `source=marker_replay`. The control is the same
     child with one variable changed — it does not die — and it books live and
     replays NOTHING.
  6. **THE PRODUCER CLAIMS ARE MEASURED AGAINST THE TREE.** Every artifact
     `PRODUCERS` names must exist; every artifact `AWAITED` names must be
     ABSENT. The day supervision (§12.2, R4-B) lands, this arm reddens and the
     claim must be re-measured rather than aging into false coverage.
  7. **THE DETECTOR'S OWN OUTPUT DRIVES THE SETTER.** A real `SurvivalWatch`
     reconcile and a real `picture_defects` call produce the reasons the HALT is
     declared with — not strings written in this file — and the within-tolerance
     control declares no HALT.

`debug.md` §7.12 — WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING?

 1. The subject could fail to import, or could import from the REAL tree while
    this gate judges another one. CLOSED: CANNOT_MEASURE naming the exception
    (§17, never a PASS), and `_provenance_defect` compares every loaded
    module's own `__file__` against `home` (CHECK-DEBT D3.124 — measured: a
    name-based import walks `_preamble`'s permanent `sys.path` entry and
    silently measures the live tree).
 2. The setter list could be compared against a list typed in this file, which
    would agree with itself forever. CLOSED: the list is parsed from
    `docs/nics_risk_subsystem_spec_v1.3.md` §12.5 at run time, and the arm
    fails loudly if that sentence cannot be found.
 3. The auto-clear arms could pass against a clock that never advances, so
    "did not clear" and "cleared" would be indistinguishable. CLOSED: every
    auto-clear drive passes an EXPLICIT `now`, and each arm asserts BOTH
    directions — not cleared at `floor - 1`, cleared at `floor`.
 4. The operator arm could pass because the sweep never ran at all. CLOSED: the
    same sweep call that leaves the operator HALT standing is required to CLEAR
    a co-active auto cause in the same call, so a no-op sweep fails.
 5. The Limiter-down arm could pass without the process ever dying — the whole
     §0a hypothesis. CLOSED: the child's exit status is asserted to be `-SIGKILL`
    and its pid asserted gone; the WAL is asserted NOT to contain the row before
    the replay; and the no-kill control (same script, one argv flag) is required
    to book LIVE and to replay ZERO rows, so a suite that never killed anything
    would measure the control and nothing else.
 6. The replay could "succeed" by writing a row that a reader cannot tell from
    a live one. CLOSED: the arm asserts the tag (`source=marker_replay`,
    `retroactive=true`), asserts the row's `ts` is the DECLARE stamp and not the
    boot stamp, and asserts the two differ.
 7. The exit-under-HALT arm could pass because the exit path was never actually
    exercised. CLOSED: the broker double records every `flatten` call and the
    arm requires the count to RISE across the exit, and a falsifier executor
    that consults the flag is driven and required to be caught.
 8. The producer arm could pass by naming nothing. CLOSED: non-vacuity floors
    below require a minimum number of claimed and awaited paths, and both maps
    are read from the SUBJECT rather than restated here.
"""

from __future__ import annotations

import importlib
import json
import re
import shutil
import signal
import subprocess  # nosec B404 - fixed argv, shell=False, own children only
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code,too-few-public-methods,too-many-locals
# pylint: disable=too-many-lines
# Over the 1000-line default, and the overflow is seven arms plus the §7.12
# answers each one closes. Splitting the gate across modules would put the
# drives in one file and the properties they prove in another — doctrine C.2
# wants the instrument to name its site, and a gate whose arms live elsewhere
# names a helper.
# pylint: disable=missing-function-docstring,missing-class-docstring
# The doubles' verbs are named after the ports they stand in for and each arm
# function's name states its own property, so a docstring would restate the
# name. `duplicate-code`: the loader and the Plane-1/broker doubles are the
# shape every nixrisk gate uses, and a shared helper module would be a second
# instrument sitting between every gate and its subject (doctrine C.9).
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: Five claims, each one OBSERVED rather than asserted:
#: * `interpreter:sys.modules` / `interpreter:sys.path` — the subject is loaded
#:   out of `ctx.nix_home`, which mutates both and restores them.
#: * `subprocess:python3` / `subprocess:python` — ARM 5's killed child and its
#:   next-boot replay, spawned through `sys.executable`. Both spellings, because
#:   the observer matches a subprocess claim by BASENAME and `sys.executable`
#:   differs between the runners.
#: * `file-write:/tmp` — the child script, the WAL and the marker file all live
#:   under one `mkdtemp` root that this gate removes.
RESOURCES: tuple[str, ...] = (
    "interpreter:sys.modules",
    "interpreter:sys.path",
    "subprocess:python3",
    "subprocess:python",
    "file-write:/tmp",
)
TIME_BOUND = True
#: Two short-lived children (a SIGKILL and a replay boot) plus the control pair.
#: MEASURED ~1.5 s on this node; the budget is loose because a `verify.py` run
#: under load is not a benchmark.
EXPECTED_S = 12.0
ON_FAIL = "continue"
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is risk-path source (scripts/nixrisk/halt.py, the §12.5 HALT "
    "state machine); a repair that edited it to satisfy its own gate is the same "
    "class of action risk spec §4 forbids on the order path"
)
SUBJECTS: tuple[str, ...] = ("scripts/nixrisk/halt.py",)

NAME = "check_halt"

HALT_FILE = "scripts/nixrisk/halt.py"
HALT_MODULE = "nixrisk.halt"
SEAM_MODULE = "nixrisk.seam"
GATE_MODULE = "nixrisk.gate"
FLATTEN_MODULE = "nixrisk.flatten"
PICTURE_MODULE = "nixrisk.picture"
RESERVATIONS_MODULE = "nixrisk.reservations"
SURVIVAL_MODULE = "nixrisk.survival"
WAL_MODULE = "nixrisk.wal"
PACKAGE = "nixrisk"

SPEC = "docs/nics_risk_subsystem_spec_v1.3.md"

#: NON-VACUITY FLOORS (`debug.md` §7.12). Each is a FLOOR the drive must reach
#: or the gate has measured nothing and says so. Anchored BELOW today's figures
#: on purpose (doctrine C.4): a threshold equal to the current count is a moving
#: anchor that reddens the moment an arm gains a case.
MIN_SETTERS = 6
MIN_TRANSITIONS = 8
MIN_PLANE1_ROWS = 8
MIN_FALSIFIERS = 4
MIN_CLAIMED_PRODUCERS = 2
MIN_AWAITED = 3

#: §12.5's floors, as the shipped `risks/limiter.config.json` carries them. Read
#: from the file rather than typed, so this gate cannot drift from the knob.
FLOOR_KEY = "halt_cooldown_floor_s"
CONFIG_REL = "risks/limiter.config.json"

#: The two §12.10 inventory rows this gate reads out of the frozen document.
HALT_ROW = "HALT set / cleared + cause"
BLACKOUT_ROW = "blackout open/close; contract-roll seam"

#: The §12.5 sentence the setter list is parsed from.
_SETTERS_LINE = re.compile(r"^Setters:\s*(.+?)\s*$", re.MULTILINE)


class Finding(NamedTuple):
    site: str
    why: str


class Loaded(NamedTuple):
    halt: ModuleType
    seam: ModuleType
    gate: ModuleType
    flatten: ModuleType
    picture: ModuleType
    reservations: ModuleType
    survival: ModuleType
    wal: ModuleType


class Tally:
    """What the drive actually reached. The floors are checked against THIS."""

    def __init__(self) -> None:
        self.transitions = 0
        self.plane1_rows = 0
        self.falsifiers = 0
        self.kills = 0


def _purge(saved: dict[str, ModuleType]) -> None:
    for name in [
        key for key in sys.modules if key == PACKAGE or key.startswith(f"{PACKAGE}.")
    ]:
        del sys.modules[name]
    sys.modules.update(saved)


def _provenance_defect(home: Path, loaded: Loaded) -> str:
    """CHECK-DEBT D3.124 — the module imported must live under `home`.

    MEASURED, not hypothesised: `checks/_preamble.py` appends the REAL
    repository's `scripts/` to `sys.path` permanently, so a name-based
    `import_module` walks that path after the `home/scripts` inserted here.
    Pointed at an empty tree, a gate without this guard imports the LIVE module
    and returns PASS over a tree that contained nothing — the exact shape §17
    forbids. The guard compares each module's own `__file__`, which the import
    cannot fake.
    """
    root = (home / "scripts").resolve()
    strays = [
        f"{name} resolved to {origin}"
        for name, origin in (
            (field, Path(getattr(module, "__file__", "") or "").resolve())
            for field, module in zip(loaded._fields, loaded, strict=True)
        )
        if root not in origin.parents
    ]
    if not strays:
        return ""
    return (
        f"{HALT_FILE}: the import resolved OUTSIDE {home} — "
        + "; ".join(strays)
        + ". `checks/_preamble.py` appends the real repository's scripts/ to "
        "sys.path permanently, so a name-based import silently measures the live "
        "tree; a property proven against a different tree is not proven (§17, "
        "CHECK-DEBT D3.124). CANNOT_MEASURE, never a PASS"
    )


def load(home: Path) -> tuple[Loaded | None, str]:
    saved_path = list(sys.path)
    saved_modules = {
        key: value
        for key, value in sys.modules.items()
        if key == PACKAGE or key.startswith(f"{PACKAGE}.")
    }
    _purge({})
    sys.path.insert(0, str((home / "scripts").resolve()))
    importlib.invalidate_caches()
    try:
        loaded = Loaded(
            halt=importlib.import_module(HALT_MODULE),
            seam=importlib.import_module(SEAM_MODULE),
            gate=importlib.import_module(GATE_MODULE),
            flatten=importlib.import_module(FLATTEN_MODULE),
            picture=importlib.import_module(PICTURE_MODULE),
            reservations=importlib.import_module(RESERVATIONS_MODULE),
            survival=importlib.import_module(SURVIVAL_MODULE),
            wal=importlib.import_module(WAL_MODULE),
        )
        stray = _provenance_defect(home, loaded)
        if stray:
            return None, stray
        return loaded, ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{HALT_FILE}: cannot import {HALT_MODULE} from {home} — "
            f"{type(exc).__name__}: {exc}. The subject is unavailable, so nothing "
            "was measured (§17: never a PASS)"
        )
    finally:
        sys.path[:] = saved_path
        _purge(saved_modules)


# --------------------------------------------------------------------------
# Doubles
# --------------------------------------------------------------------------


class _Plane1:
    def __init__(self) -> None:
        self.rows: list[Any] = []
        self.syncs = 0

    def enqueue(self, row: Any) -> None:
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        self.syncs += 1
        return len(self.rows)

    def pending(self) -> int:
        return len(self.rows)

    def of(self, kind: Any) -> list[Any]:
        return [row for row in self.rows if row.kind is kind]


class _Plane2:
    def __init__(self) -> None:
        self.lines: list[tuple[str, dict[str, Any]]] = []

    def emit(self, event: str, **fields: Any) -> str:
        self.lines.append((event, fields))
        return event


class _WriteOnlyPlane2(_Plane2):
    """Every verb but `emit` raises. §12.10:740 — Plane 2 is never READ.

    Not a passive recorder: a machine that ever reached for a field, a count or
    a readback on the operational plane would use it as an input, which is the
    one thing the two-plane model forbids. The failure is loud and immediate.
    """

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(
            f"the trading path READ the Plane-2 sink ({name!r}) — §12.10:740: "
            "diagnostic only, never a reconciliation input, never read by the "
            "trading path"
        )


class _Broker:
    """A `BrokerFlattenPort`. Counts the two verbs the entry/exit split turns on."""

    def __init__(self) -> None:
        self.flatten_calls: list[str | None] = []
        self.cancel_calls: list[str] = []

    def flatten(self, symbol: str | None = None) -> None:
        self.flatten_calls.append(symbol)

    def cancel_order(self, client_order_id: str) -> None:
        self.cancel_calls.append(client_order_id)


class _StrategySink:
    def __init__(self) -> None:
        self.closed: list[tuple[str, str, str, bool]] = []

    def on_closed(
        self, trade_id: str, strategy_id: str, reason: str, *, hard_reset: bool
    ) -> None:
        self.closed.append((trade_id, strategy_id, reason, hard_reset))


class _ScoringSink:
    def book_realized(
        self,
        *,
        closed_trades: tuple[str, ...],
        realized_delta: float,
        confirmed_balance: float,
        ts: float,
    ) -> None:
        del closed_trades, realized_delta, confirmed_balance, ts


class _PendingBook:
    def __init__(self, entries: tuple[Any, ...]) -> None:
        self._entries = entries

    def pending_entries(self) -> tuple[Any, ...]:
        return self._entries


class _OpenFlag:
    """A never-blocking §11.1 cache, so branch 0 is the only thing that can deny."""

    def read(self, symbol: str | None = None) -> tuple[bool, str]:
        del symbol
        return (False, "")


def _floors(home: Path) -> dict[str, float]:
    raw = json.loads((home / CONFIG_REL).read_text(encoding="utf-8"))
    return {str(k): float(v) for k, v in raw[FLOOR_KEY].items()}


def _spec_text(home: Path) -> str:
    return (home / SPEC).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# ARM 1 — the six setters are the FROZEN SPEC's own sentence
# --------------------------------------------------------------------------


def _arm_setters(loaded: Loaded, home: Path, tally: Tally) -> list[Finding]:
    findings: list[Finding] = []
    halt = loaded.halt
    site = f"{HALT_FILE}:setters"

    match = _SETTERS_LINE.search(_spec_text(home))
    if match is None:
        return [
            Finding(
                site,
                f"{SPEC}: §12.5's 'Setters:' sentence was not found, so the "
                "setter set could not be derived from the frozen spec — the "
                "comparison would have been this file against itself",
            )
        ]
    spelled = tuple(
        part.strip().rstrip(".").replace("-", "_").replace(" ", "_")
        for part in match.group(1).split(",")
    )
    declared = tuple(cause.value for cause in halt.HaltCause)
    if len(spelled) < MIN_SETTERS:
        findings.append(
            Finding(
                site,
                f"{SPEC} §12.5 yielded only {len(spelled)} setters "
                f"({spelled!r}); the floor is {MIN_SETTERS}",
            )
        )
    if set(spelled) != set(declared):
        findings.append(
            Finding(
                site,
                f"HaltCause is {declared!r} but §12.5's own sentence names "
                f"{spelled!r} — the enumeration is the SPEC's list, never the "
                "implementation's",
            )
        )
    auto = {cause.value for cause in halt.HaltCause if cause.auto_clearable}
    if auto != set(declared) - {"operator"}:
        findings.append(
            Finding(
                site,
                f"auto_clearable is {sorted(auto)!r} — §12.5:633 makes exactly "
                "one cause (operator) non-auto-clearing",
            )
        )

    # FALSIFIER 1 — a floor map naming `operator` must be REFUSED at construction:
    # a floor for a cause that clears only by operator implies an auto-clear.
    floors = _floors(home)
    try:
        halt.HaltFlag(
            plane1=_Plane1(),
            plane2=_Plane2(),
            floors={**floors, "operator": 60},
        )
        findings.append(
            Finding(
                f"{site}:falsifier",
                "a cooldown floor for `operator` was ACCEPTED — the machine "
                "would imply an auto-clear §12.5:633 forbids",
            )
        )
    except halt.KnobError as exc:
        tally.falsifiers += 1
        if "operator" not in str(exc):
            findings.append(
                Finding(f"{site}:falsifier", f"refusal did not name operator: {exc}")
            )

    # FALSIFIER 2 — a MISSING floor reads as zero, i.e. no cooldown at all.
    short = {k: v for k, v in floors.items() if k != "stale_data"}
    try:
        halt.HaltFlag(plane1=_Plane1(), plane2=_Plane2(), floors=short)
        findings.append(
            Finding(
                f"{site}:falsifier",
                "a floor map MISSING stale_data was accepted — the missing floor "
                "would read as zero, an auto-clear with no cooldown",
            )
        )
    except halt.KnobError as exc:
        tally.falsifiers += 1
        if "stale_data" not in str(exc):
            findings.append(
                Finding(f"{site}:falsifier", f"refusal did not name the gap: {exc}")
            )
    return findings


# --------------------------------------------------------------------------
# ARM 2 — operator HALT does NOT auto-clear; the hybrid does
# --------------------------------------------------------------------------


def _expect_refusal(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    findings: list[Finding],
    site: str,
    verb,
    exc_type: type[BaseException],
    phrase: str,
    why: str,
) -> None:
    """Drive one refusal. EVERY outcome lands as a finding or as nothing.

    MEASURED, and it is why this helper exists rather than a bare `try`. The
    first version of this arm let an unexpected SUCCESS fall through, and the
    call after it then raised `NotHalted` out of the arm entirely — so a planted
    defect that made a refusal stop refusing came back as CANNOT_MEASURE. That is
    not a PASS, so nothing unsafe shipped, but it is the wrong verdict: the gate
    HAD caught the defect and reported that it could not look. A control that
    turns a caught defect into "cannot measure" hides it in the aggregate.

    Check contract v2 §11: the REASON is asserted, never the exception type
    alone — a wrong-but-related exception is a different defect from the one
    this drive is about.
    """
    try:
        verb()
    except exc_type as exc:
        if phrase not in str(exc):
            findings.append(
                Finding(site, f"{why}: the refusal did not name {phrase!r}: {exc}")
            )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        findings.append(
            Finding(site, f"{why}: raised {type(exc).__name__} instead: {exc}")
        )
    else:
        findings.append(Finding(site, why))


def _guarded(findings: list[Finding], site: str, verb, why: str):
    """Drive a call that MUST succeed. A raise is a finding, never an escape."""
    try:
        return verb()
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        findings.append(Finding(site, f"{why}: raised {type(exc).__name__}: {exc}"))
        return None


def _fresh_flag(halt, floors, plane1=None):
    """One machine per sub-drive. A drive whose refusal unexpectedly SUCCEEDS
    must not leave state the next drive reads as its own result."""
    return halt.HaltFlag(plane1=plane1 or _Plane1(), plane2=_Plane2(), floors=floors)


def _hybrid_refusals(halt, floors, site: str, tally: Tally) -> list[Finding]:
    """§12.5:632 is a HYBRID: condition-clear AND a floor. Neither alone clears."""
    findings: list[Finding] = []
    floor = floors["stale_data"]

    # -- the condition is still LIVE: neither route may clear ------------------
    live = _fresh_flag(halt, floors)
    live.set(halt.HaltCause.STALE_DATA, "price feed silent 4200ms", now=100.0)
    tally.transitions += 1
    if live.auto_clear(1e12):
        findings.append(
            Finding(site, "auto_clear cleared a cause whose condition never cleared")
        )
    _expect_refusal(
        findings,
        site,
        lambda: live.clear(halt.HaltCause.STALE_DATA, "premature", now=1e12),
        halt.ConditionStillActive,
        "condition-clear",
        "clear() succeeded while the condition was still active",
    )

    # -- the condition cleared, the FLOOR has not run -------------------------
    early = _fresh_flag(halt, floors)
    early.set(halt.HaltCause.STALE_DATA, "silent", now=100.0)
    early.condition_cleared(halt.HaltCause.STALE_DATA, 200.0)
    tally.transitions += 1
    _expect_refusal(
        findings,
        site,
        lambda: early.clear(
            halt.HaltCause.STALE_DATA, "too soon", now=200.0 + floor - 1.0
        ),
        halt.CooldownNotElapsed,
        "floor",
        "clear() succeeded before the floor elapsed",
    )
    if early.auto_clear(200.0 + floor - 1.0):
        findings.append(
            Finding(site, "auto_clear fired before the §12.5:632 floor elapsed")
        )

    # -- a condition that RE-ARMS cancels the pending clear -------------------
    flap = _fresh_flag(halt, floors)
    flap.set(halt.HaltCause.STALE_DATA, "silent", now=100.0)
    flap.condition_cleared(halt.HaltCause.STALE_DATA, 200.0)
    flap.condition_returned(halt.HaltCause.STALE_DATA)
    tally.transitions += 1
    if flap.auto_clear(1e12) or not flap.is_set()[0]:
        findings.append(
            Finding(
                site,
                "auto_clear cleared a cause whose condition RE-ARMED — a flapping "
                "feed would clear the HALT its own condition had just re-set",
            )
        )
    return findings


def _operator_stands(halt, seam, floors, site: str, tally: Tally) -> list[Finding]:
    """ONE sweep: the auto cause clears and the OPERATOR halt does not."""
    findings: list[Finding] = []
    floor = floors["stale_data"]

    # -- ONE sweep, both halves: the auto cause clears, the operator stands ---
    plane1 = _Plane1()
    both = _fresh_flag(halt, floors, plane1)
    both.set(halt.HaltCause.OPERATOR, "operator kill switch", now=100.0)
    both.set(halt.HaltCause.STALE_DATA, "silent", now=100.0)
    both.condition_cleared(halt.HaltCause.STALE_DATA, 300.0)
    tally.transitions += 2
    made = both.auto_clear(300.0 + floor)
    tally.transitions += len(made)
    if [t.cause for t in made] != [halt.HaltCause.STALE_DATA]:
        findings.append(
            Finding(
                site,
                f"the sweep made {[t.cause for t in made]!r} — it must clear "
                "stale_data and NOTHING else. A sweep that also took the operator "
                "HALT is §12.5:633 broken; a no-op sweep would leave the operator "
                "half below measuring nothing",
            )
        )
    halted, why = both.is_set()
    if not halted or "operator" not in why:
        findings.append(
            Finding(
                site,
                f"after the sweep the flag reads {(halted, why)!r} — §12.5:633: "
                "'Operator HALT clears only by operator', so the flag must still "
                "be SET and must name the operator cause",
            )
        )
    _expect_refusal(
        findings,
        site,
        lambda: both.clear(halt.HaltCause.OPERATOR, "auto", now=1e12),
        halt.OperatorHaltPersists,
        "clear_by_operator",
        "the auto-clear route cleared an OPERATOR halt",
    )
    _expect_refusal(
        findings,
        site,
        lambda: both.condition_cleared(halt.HaltCause.OPERATOR, 1e12),
        halt.OperatorHaltPersists,
        "only by operator",
        "condition_cleared armed a cooldown on an OPERATOR halt",
    )
    cleared = _guarded(
        findings,
        site,
        lambda: both.clear_by_operator(
            halt.HaltCause.OPERATOR, "operator restored", now=400.0
        ),
        "the operator verb could not clear the operator HALT",
    )
    tally.transitions += 1
    if cleared is not None and (both.is_set()[0] or cleared.halted_after):
        findings.append(
            Finding(site, f"the operator clear left the flag set: {both.is_set()!r}")
        )

    rows = plane1.of(seam.EventKind.HALT_SET) + plane1.of(seam.EventKind.HALT_CLEARED)
    tally.plane1_rows += len(rows)
    if any(not row.reason.strip() for row in rows):
        findings.append(
            Finding(
                site,
                "a HALT row carries no reason — §12.5:633: every set/clear is an "
                "audited event WITH reason",
            )
        )
    return findings


def _reset_is_not_a_transition(halt, floors, site: str, tally: Tally) -> list[Finding]:
    """§9's log is one row per TRANSITION; a polling producer must not bury edges."""
    findings: list[Finding] = []

    # -- a re-set of a LIVE cause is not a transition and books NO row --------
    repeat_plane1 = _Plane1()
    repeated = _fresh_flag(halt, floors, repeat_plane1)
    first = repeated.set(halt.HaltCause.STALE_DATA, "silent", now=500.0)
    again = repeated.set(halt.HaltCause.STALE_DATA, "still silent", now=501.0)
    tally.transitions += 1
    tally.plane1_rows += len(repeat_plane1.rows)
    if again.booked or len(repeat_plane1.rows) != 1:
        findings.append(
            Finding(
                site,
                f"a re-set of a live cause booked a row ({again!r}) — §9's log is "
                "one row per TRANSITION, and a polling producer would bury the edges",
            )
        )
    if not first.booked:
        findings.append(Finding(site, "the first set of a cause booked nothing"))
    return findings


def _arm_auto_clear(loaded: Loaded, home: Path, tally: Tally) -> list[Finding]:
    halt = loaded.halt
    site = f"{HALT_FILE}:auto_clear"
    floors = _floors(home)
    findings: list[Finding] = []
    findings += _hybrid_refusals(halt, floors, site, tally)
    findings += _operator_stands(halt, loaded.seam, floors, site, tally)
    findings += _reset_is_not_a_transition(halt, floors, site, tally)

    # FALSIFIER — a machine whose floor is ignored clears the instant the
    # condition does. The floor drive above is what must catch it.
    class _NoFloor(halt.HaltFlag):  # type: ignore[name-defined,misc]
        def eligible_at(self, cause):
            record = self.record(cause)
            if record is None or not cause.auto_clearable:
                return None
            return record.condition_cleared_ts  # PLANTED: floor dropped

    fake = _NoFloor(plane1=_Plane1(), plane2=_Plane2(), floors=floors)
    fake.set(halt.HaltCause.STALE_DATA, "silent", now=100.0)
    fake.condition_cleared(halt.HaltCause.STALE_DATA, 200.0)
    if fake.auto_clear(200.0):
        tally.falsifiers += 1
    else:
        findings.append(
            Finding(
                f"{site}:falsifier",
                "the dropped-floor falsifier still refused to clear early — it no "
                "longer falsifies, so the floor assertion above proves nothing",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM 3 — both planes, routed by §12.10's OWN TABLE; Plane 2 never read
# --------------------------------------------------------------------------


def _inventory_row(text: str, label: str) -> tuple[str, str] | None:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or label not in stripped:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) >= 3:
            return cells[1], cells[2]
    return None


def _arm_planes(loaded: Loaded, home: Path, tally: Tally) -> list[Finding]:
    findings: list[Finding] = []
    halt = loaded.halt
    seam = loaded.seam
    site = f"{HALT_FILE}:planes"
    text = _spec_text(home)

    halt_row = _inventory_row(text, HALT_ROW)
    black_row = _inventory_row(text, BLACKOUT_ROW)
    if halt_row is None or black_row is None:
        return [
            Finding(
                site,
                f"{SPEC} §12.10's event inventory does not carry the rows "
                f"{HALT_ROW!r} / {BLACKOUT_ROW!r} — the routing could not be "
                "derived from the frozen document",
            )
        ]
    if "✅" not in halt_row[0] or "✅" not in halt_row[1]:
        findings.append(
            Finding(
                site,
                f"§12.10 routes {HALT_ROW!r} to {halt_row!r}; this gate requires "
                "BOTH planes ticked",
            )
        )
    if "next boot" not in halt_row[0]:
        findings.append(
            Finding(
                site,
                f"§12.10's Plane-1 note for {HALT_ROW!r} is {halt_row[0]!r} and "
                "does not carry the Limiter-down clause",
            )
        )
    if "✅" in black_row[0] or "✅" not in black_row[1]:
        findings.append(
            Finding(
                site,
                f"§12.10 routes {BLACKOUT_ROW!r} to {black_row!r} — this gate "
                "reads it as Plane 2 ONLY, and any Plane-1 tick here would "
                "contradict the table",
            )
        )

    plane1, plane2 = _Plane1(), _Plane2()
    flag = halt.HaltFlag(plane1=plane1, plane2=plane2, floors=_floors(home))
    flag.set(halt.HaltCause.INVARIANT_BREACH, "committed drift +812.50", now=10.0)
    tally.transitions += 1
    tally.plane1_rows += len(plane1.rows)
    if len(plane1.of(seam.EventKind.HALT_SET)) != 1 or len(plane2.lines) != 1:
        findings.append(
            Finding(
                site,
                f"one set() produced {len(plane1.rows)} Plane-1 row(s) and "
                f"{len(plane2.lines)} Plane-2 line(s); §12.10 requires exactly "
                "one on each",
            )
        )
    row = plane1.of(seam.EventKind.HALT_SET)[0]
    for field, want in (("cause", "invariant_breach"), ("retroactive", "false")):
        if row.fields.get(field) != want:
            findings.append(
                Finding(site, f"the Plane-1 row's {field} is {row.fields.get(field)!r}")
            )
    if plane2.lines[0][1].get("cause") != "invariant_breach":
        findings.append(Finding(site, "the Plane-2 line carries no cause"))

    # Plane 2 is WRITE-ONLY across a full gate pass (§12.10:740).
    strict = halt.HaltFlag(
        plane1=_Plane1(), plane2=_WriteOnlyPlane2(), floors=_floors(home)
    )
    strict.set(halt.HaltCause.CLOCK_SKEW, "skew 812ms > 250ms", now=20.0)
    tally.transitions += 1
    passer = loaded.gate.GatePass(
        strict,
        (
            loaded.gate.SymbolFlagRule("blackout_window", _OpenFlag(), "§6.1-6.3"),
            loaded.gate.PictureCoherenceRule("picture_coherence", 0.01),
        ),
    )
    order, picture = _proposal(loaded)
    outcome = passer.evaluate(order, picture, 30.0)
    if outcome.rule != loaded.gate.HALT_RULE:
        findings.append(Finding(site, f"branch 0 did not deny under HALT: {outcome!r}"))
    return findings


def _proposal(loaded: Loaded) -> tuple[Any, Any]:
    seam = loaded.seam
    book = loaded.picture.FinancialPictureBook(
        balance=50000.0, deployable_fraction=0.70
    )
    order = seam.ProposedOrder(
        client_order_id="COID-1",
        strategy_id="strat-1",
        symbol="MESU6",
        side=seam.Side.LONG,
        qty=1,
        margin_per_contract=1000.0,
        stop_ticks=20,
        stop_mode=seam.StopMode.FIXED,
        signal_ts=1.0,
    )
    return order, book.current()


# --------------------------------------------------------------------------
# ARM 4 — HALT gates ENTRY, never EXIT (§3:167-174, §3:173)
# --------------------------------------------------------------------------


def _executor(loaded: Loaded, broker: _Broker, plane1: _Plane1, cls: Any = None):
    book = loaded.picture.FinancialPictureBook(
        balance=50000.0, deployable_fraction=0.70
    )
    ledger = loaded.reservations.ReservationLedger(plane1)
    executor_cls = cls or loaded.flatten.ProtectiveFlatten
    return (
        executor_cls(
            broker=broker,
            ledger=ledger,
            picture=book,
            strategy=_StrategySink(),
            plane1=plane1,
            scoring=_ScoringSink(),
            clock=lambda: 42.0,
        ),
        ledger,
    )


def _onset_defects(broker, ledger, seam, transition, site: str) -> list[Finding]:
    """§3:173: the onset cancels every pending ENTRY and touches no exit."""
    findings: list[Finding] = []
    if not transition.swept or broker.cancel_calls != ["COID-1"]:
        findings.append(
            Finding(
                site,
                f"HALT onset cancelled {broker.cancel_calls!r} (swept="
                f"{transition.swept!r}) — §3:173 cancels every pending ENTRY order",
            )
        )
    if broker.flatten_calls:
        findings.append(
            Finding(
                site,
                f"HALT onset issued {broker.flatten_calls!r} — §3:173: exits are "
                "UNTOUCHED; cancelling a pending entry is not closing a position",
            )
        )
    released = [
        r for r in ledger.released() if r.released_via is seam.TerminalPath.HALT_ONSET
    ]
    if not released:
        findings.append(
            Finding(
                site,
                "the onset released no reservation under HALT_ONSET (SPEC-A7) — "
                "booking it as a bare CANCEL erases the cause from §9's record",
            )
        )
    return findings


def _entry_denied_defects(loaded: Loaded, flag, order, picture, site: str):
    """Branch 0 denies, and a HALT pass dispatches no rule at all (§3:138)."""
    findings: list[Finding] = []
    seam = loaded.seam
    passer = loaded.gate.GatePass(
        flag,
        (
            loaded.gate.SymbolFlagRule("blackout_window", _OpenFlag(), "§6.1-6.3"),
            loaded.gate.PictureCoherenceRule("picture_coherence", 0.01),
        ),
    )
    outcome = passer.evaluate(order, picture, 60.0)
    if (
        outcome.decision is not seam.Decision.DENY
        or outcome.rule != loaded.gate.HALT_RULE
    ):
        findings.append(
            Finding(site, f"an ENTRY was not denied under HALT: {outcome!r}")
        )
    if outcome.evaluated != (loaded.gate.HALT_RULE,):
        findings.append(
            Finding(site, f"a HALT pass dispatched rules: {outcome.evaluated!r}")
        )
    return findings


def _exit_fires_defects(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    loaded, flag, executor, broker, plane1, site: str, tally: Tally
) -> list[Finding]:
    """THE DANGEROUS HALF: a protective exit must FIRE while the flag is SET."""
    findings: list[Finding] = []
    seam, flatten = loaded.seam, loaded.flatten
    before = len(broker.flatten_calls)
    action = executor.fire(
        seam.FlattenTrigger.SYNTHETIC_STOP,
        symbol="MESU6",
        targets=(
            flatten.CloseTarget(trade_id="T-1", symbol="MESU6", strategy_id="strat-1"),
        ),
    )
    if not flag.is_set()[0]:
        findings.append(Finding(site, "the flag was not set while the exit was driven"))
    if len(broker.flatten_calls) <= before:
        findings.append(
            Finding(
                site,
                "the protective exit issued NO broker flatten while HALT was set — "
                "§3:167-174 gives the exit path zero dependency on the entry path, "
                "and a HALT that froze exits would strand open positions",
            )
        )
    if not action.outcomes or not action.outcomes[0].executed:
        findings.append(
            Finding(site, f"the exit did not execute under HALT: {action!r}")
        )
    if not plane1.of(seam.EventKind.PROTECTIVE_EXIT):
        findings.append(
            Finding(site, "the exit under HALT booked no PROTECTIVE_EXIT row")
        )
    tally.plane1_rows += len(plane1.rows)
    return findings


def _arm_entry_not_exit(loaded: Loaded, home: Path, tally: Tally) -> list[Finding]:
    halt, seam, flatten = loaded.halt, loaded.seam, loaded.flatten
    site = f"{HALT_FILE}:entry_not_exit"

    broker = _Broker()
    plane1 = _Plane1()
    executor, ledger = _executor(loaded, broker, plane1)
    order, picture = _proposal(loaded)
    ledger.take(order, 1.0)

    pending = (
        flatten.PendingEntry(
            client_order_id="COID-1", strategy_id="strat-1", symbol="MESU6"
        ),
    )
    flag = halt.HaltFlag(
        plane1=plane1,
        plane2=_Plane2(),
        floors=_floors(home),
        onset=executor,
        pending=_PendingBook(pending),
    )
    transition = flag.set(
        halt.HaltCause.AGGREGATE_DRIFT, "net-liq drift +900.00", now=50.0
    )
    tally.transitions += 1

    findings = _onset_defects(broker, ledger, loaded.seam, transition, site)
    findings += _entry_denied_defects(loaded, flag, order, picture, site)
    findings += _exit_fires_defects(loaded, flag, executor, broker, plane1, site, tally)

    # FALSIFIER — an executor that consults the flag drops the exit. The
    # assertion above is what must catch it.
    class _HaltAware(flatten.ProtectiveFlatten):  # type: ignore[name-defined,misc]
        halt_flag: Any = None

        def request_close(self, target, authority, reason):
            if self.halt_flag.is_set()[0]:  # PLANTED: HALT gates the EXIT
                return flatten.CloseOutcome(
                    executed=False,
                    record=flatten.ClosedRecord(
                        trade_id=target.trade_id,
                        symbol=target.symbol,
                        strategy_id=target.strategy_id,
                        authority=authority,
                        reason=reason,
                        closed_ts=0.0,
                        hard_reset=False,
                        superseded=None,
                    ),
                    dropped_reason="PLANTED: refused because HALT is set",
                )
            return super().request_close(target, authority, reason)

    fake_broker = _Broker()
    fake, _ = _executor(loaded, fake_broker, _Plane1(), cls=_HaltAware)
    fake.halt_flag = flag
    fake_action = fake.fire(
        seam.FlattenTrigger.SYNTHETIC_STOP,
        symbol="MESU6",
        targets=(
            flatten.CloseTarget(trade_id="T-2", symbol="MESU6", strategy_id="strat-1"),
        ),
    )
    if fake_broker.flatten_calls or fake_action.outcomes[0].executed:
        findings.append(
            Finding(
                f"{site}:falsifier",
                "the HALT-aware falsifier still fired the exit — it no longer "
                "falsifies, so the exit assertion above proves nothing",
            )
        )
    else:
        tally.falsifiers += 1
    return findings


# --------------------------------------------------------------------------
# ARM 5 — the Limiter-down case, with the Limiter GENUINELY killed
# --------------------------------------------------------------------------

_CHILD = '''\
"""ARC 033 / check_halt ARM 5 child. Argv: scripts_dir wal marker mode."""
import os
import signal
import sys

sys.path.insert(0, sys.argv[1])
from nixrisk.halt import HaltCause, HaltFlag, HaltMarker  # noqa: E402
from nixrisk.wal import Plane1Wal  # noqa: E402

DECLARE_TS = 1234.5
FLOORS = {
    "stale_data": 60,
    "clock_skew": 300,
    "crash_loop": 900,
    "invariant_breach": 900,
    "aggregate_drift": 900,
}


class Dies:
    """The Limiter dying at the instant it would have booked the row.

    Not an exception: SIGKILL, so no `finally`, no `atexit` and no buffered
    write can run. If the machine booked Plane 1 BEFORE the marker, this death
    leaves no marker at all and the parent's replay recovers nothing.
    """

    def enqueue(self, row):
        os.kill(os.getpid(), signal.SIGKILL)

    def sync_to_disk(self):
        return 0

    def pending(self):
        return 0


class P2:
    def emit(self, event, **fields):
        return event


wal = Plane1Wal(sys.argv[2])
marker = HaltMarker(sys.argv[3])
plane1 = Dies() if sys.argv[4] == "die" else wal
flag = HaltFlag(plane1=plane1, plane2=P2(), marker=marker, floors=FLOORS)
flag.set(HaltCause.CRASH_LOOP, "risk engine restarted 3x in 60s", now=DECLARE_TS)
wal.sync_to_disk()
print("SURVIVED")
'''

_BOOT = '''\
"""ARC 033 / check_halt ARM 5 next-boot replay. Argv: scripts_dir wal marker."""
import json
import sys

sys.path.insert(0, sys.argv[1])
from nixrisk.halt import HaltMarker, replay_markers  # noqa: E402
from nixrisk.wal import Plane1Wal  # noqa: E402

BOOT_TS = 999999.0
rows = replay_markers(HaltMarker(sys.argv[3]), Plane1Wal(sys.argv[2]), BOOT_TS)
print(json.dumps({"booked": len(rows), "boot_ts": BOOT_TS}))
'''

DECLARE_TS = 1234.5
BOOT_TS = 999999.0


def _spawn(script: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 - fixed argv, shell=False, own child
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _killed_case(
    loaded: Loaded, site: str, root: Path, scripts: str, tally: Tally
) -> list[Finding]:
    """The Limiter dies at the instant it would have booked. Three facts asserted.

    Split out of the arm so each half of §12.5:634-638 is one readable drive:
    the death is genuine, the log did NOT get the row, and the marker DID.
    """
    findings: list[Finding] = []
    wal, marker = str(root / "die.wal"), str(root / "die.marker")
    killed = _spawn(root / "child.py", [scripts, wal, marker, "die"])
    if killed.returncode != -signal.SIGKILL:
        findings.append(
            Finding(
                site,
                f"the child exited {killed.returncode!r} with stdout "
                f"{killed.stdout.strip()!r} / stderr "
                f"{killed.stderr.strip()[-300:]!r} — it was NOT SIGKILLed, so the "
                "Limiter was never genuinely unavailable and the retroactive path "
                "was never exercised (§0a)",
            )
        )
    else:
        tally.kills += 1
    if "SURVIVED" in killed.stdout:
        findings.append(Finding(site, "the child ran past the kill point"))
    if [
        r
        for r in loaded.wal.recover(wal).rows
        if r.kind is loaded.seam.EventKind.HALT_SET
    ]:
        findings.append(
            Finding(
                site,
                "the WAL already held the HALT row before the replay — the "
                "Limiter-down case did not occur, and the replay below would "
                "measure a row that was booked live",
            )
        )
    entries = loaded.halt.HaltMarker(marker).entries()
    if not [e for e in entries if e.rec == "set"]:
        findings.append(
            Finding(
                site,
                "the killed child left NO marker `set` record — §12.1:610's marker "
                "is written BEFORE acting, and without it §12.5:637 has nothing to "
                "book at the next boot",
            )
        )
    if [e for e in entries if e.rec == "booked"]:
        findings.append(
            Finding(site, "the killed child recorded a `booked` half it never reached")
        )
    return findings


def _replayed_row_defects(loaded: Loaded, site: str, wal: str, tally: Tally):
    """Every way the row the next boot wrote could fail to be a retroactive one."""
    findings: list[Finding] = []
    rows = [
        r
        for r in loaded.wal.recover(wal).rows
        if r.kind is loaded.seam.EventKind.HALT_SET
    ]
    tally.plane1_rows += len(rows)
    if len(rows) != 1:
        return [
            Finding(
                site,
                f"the next boot booked {len(rows)} HALT_SET row(s); §12.5:637 books "
                "the row exactly once",
            )
        ]
    row = rows[0]
    if row.fields.get("source") != loaded.halt.SOURCE_REPLAY:
        findings.append(
            Finding(
                site,
                f"the replayed row's source is {row.fields.get('source')!r} — a "
                "reader cannot tell a retroactive booking from a live one",
            )
        )
    if row.fields.get("retroactive") != "true":
        findings.append(Finding(site, "the replayed row is not tagged retroactive"))
    if row.ts != DECLARE_TS:
        findings.append(
            Finding(
                site,
                f"the replayed row's ts is {row.ts!r}, not the declare stamp "
                f"{DECLARE_TS!r} — a retroactive row carrying the boot time moves a "
                "money-gating event by the length of the outage",
            )
        )
    if row.fields.get("booked_at") != repr(BOOT_TS):
        findings.append(Finding(site, f"booked_at is {row.fields.get('booked_at')!r}"))
    return findings


def _next_boot(loaded: Loaded, site: str, root: Path, scripts: str, tally: Tally):
    """A FRESH process replays the marker. Nothing else may have written the row."""
    wal, marker = str(root / "die.wal"), str(root / "die.marker")
    replayed = _spawn(root / "boot.py", [scripts, wal, marker])
    if replayed.returncode != 0:
        return [
            Finding(site, f"the next-boot replay failed: {replayed.stderr[-400:]!r}")
        ]
    findings = _replayed_row_defects(loaded, site, wal, tally)
    if Path(marker).exists():
        findings.append(
            Finding(site, "the marker was not archived — a second boot would replay it")
        )
    if not list(root.glob("die.marker.*.replayed")):
        findings.append(Finding(site, "no archived marker was left behind"))
    return findings


def _live_control(
    loaded: Loaded, site: str, root: Path, scripts: str, tally: Tally
) -> list[Finding]:
    """The SAME child with ONE variable changed: it does not die.

    This is what makes ARM 5 a measurement rather than a story. The killed case
    and this one run the same bytes; the only difference is whether the process
    survives to book. If the retroactive path were reachable without a death,
    this control would book a replayed row too — and it must book NONE.
    """
    findings: list[Finding] = []
    wal, marker = str(root / "live.wal"), str(root / "live.marker")
    alive = _spawn(root / "child.py", [scripts, wal, marker, "live"])
    if alive.returncode != 0 or "SURVIVED" not in alive.stdout:
        findings.append(
            Finding(
                f"{site}:control",
                f"the no-kill control did not survive ({alive.returncode!r}): "
                f"{alive.stderr[-300:]!r}",
            )
        )
    live_rows = [
        r
        for r in loaded.wal.recover(wal).rows
        if r.kind is loaded.seam.EventKind.HALT_SET
    ]
    if (
        len(live_rows) != 1
        or live_rows[0].fields.get("source") != loaded.halt.SOURCE_LIVE
    ):
        findings.append(
            Finding(
                f"{site}:control",
                f"the live path booked {live_rows!r} — it must book exactly one row "
                f"tagged {loaded.halt.SOURCE_LIVE!r}",
            )
        )
    booked = json.loads(
        _spawn(root / "boot.py", [scripts, wal, marker]).stdout or "{}"
    ).get("booked", -1)
    if booked != 0:
        findings.append(
            Finding(
                f"{site}:control",
                f"replaying a marker whose row was booked LIVE booked {booked} more "
                "row(s) — §9's log is append-only and would carry two HALTs where "
                "one happened",
            )
        )
    else:
        tally.falsifiers += 1
    return findings


def _arm_limiter_down(loaded: Loaded, home: Path, tally: Tally) -> list[Finding]:
    site = f"{HALT_FILE}:limiter_down"
    scripts = str((home / "scripts").resolve())
    root = Path(tempfile.mkdtemp(prefix="nix-halt-"))
    try:
        (root / "child.py").write_text(_CHILD, encoding="utf-8")
        (root / "boot.py").write_text(_BOOT, encoding="utf-8")
        return (
            _killed_case(loaded, site, root, scripts, tally)
            + _next_boot(loaded, site, root, scripts, tally)
            + _live_control(loaded, site, root, scripts, tally)
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --------------------------------------------------------------------------
# ARM 6 — the producer claims are MEASURED; the R4-B deferral is stated
# --------------------------------------------------------------------------


def _arm_producers(loaded: Loaded, home: Path) -> list[Finding]:
    findings: list[Finding] = []
    halt = loaded.halt
    site = f"{HALT_FILE}:producers"

    claimed = [rel for paths in halt.PRODUCERS.values() for rel in paths]
    awaited = [rel for paths in halt.AWAITED.values() for rel in paths]
    if len(claimed) < MIN_CLAIMED_PRODUCERS or len(awaited) < MIN_AWAITED:
        findings.append(
            Finding(
                site,
                f"the subject claims {len(claimed)} producer path(s) and "
                f"{len(awaited)} awaited path(s); the floors are "
                f"{MIN_CLAIMED_PRODUCERS}/{MIN_AWAITED} — a map that names "
                "nothing cannot be wrong",
            )
        )
    findings.extend(
        Finding(
            site,
            f"{rel} is claimed as a producer of a §12.5 HALT condition and does "
            "not exist under the tree being judged",
        )
        for rel in claimed
        if not (home / rel).exists()
    )
    findings.extend(
        Finding(
            site,
            f"{rel} EXISTS. It is declared as still-awaited, so a §12.5 cause "
            "this module reports as having no producer may now have one — "
            "re-measure the claim rather than letting it age into false coverage",
        )
        for rel in awaited
        if (home / rel).exists()
    )
    text = (home / HALT_FILE).read_text(encoding="utf-8")
    for phrase, why in (
        ("Sentinel deadman (§12.1) is NOT built", "the Sentinel deferral"),
        ("crash-loop breaker (§12.2) are NOT built", "the supervision deferral"),
        ("unprotected position until the Sentinel", "the residual-risk sentence"),
    ):
        if phrase not in text:
            findings.append(
                Finding(
                    site,
                    f"{why} is not stated in the subject — a blackout calendar "
                    "without the Sentinel is not the full non-stop guarantee, and "
                    "a gate that does not say so implies coverage it does not have",
                )
            )
    return findings


# --------------------------------------------------------------------------
# ARM 7 — the DETECTOR'S OWN OUTPUT drives the setter
# --------------------------------------------------------------------------


class _DriftBroker:
    def __init__(self, seam: ModuleType, readings: list[tuple[float, float]]) -> None:
        self._seam = seam
        self._readings = readings
        self._survival: Any = None

    def bind(self, survival: ModuleType) -> None:
        self._survival = survival

    def poll(self) -> Any:
        cash, venue_ts = self._readings.pop(0)
        return self._survival.BrokerReading(
            cash=cash, net_liq=cash, positions=(), venue_ts=venue_ts
        )


class _NoFlatten:
    def flatten(self, trigger: Any, reason: str) -> None:
        del trigger, reason


class _NoAlert:
    def emit(self, alert: Any) -> None:
        del alert


def _arm_real_detectors(loaded: Loaded, home: Path, tally: Tally) -> list[Finding]:
    findings: list[Finding] = []
    halt, seam, survival = loaded.halt, loaded.seam, loaded.survival
    site = f"{HALT_FILE}:real_detectors"
    plane1 = _Plane1()
    flag = halt.HaltFlag(plane1=plane1, plane2=_Plane2(), floors=_floors(home))

    # AGGREGATE_DRIFT — from a REAL SurvivalWatch reconcile, not a string.
    # Third reading is within `tolerance` of the SECOND, not of the first: the
    # watch adopts broker truth on every poll, so a control that returned to the
    # ORIGINAL figure would be a second 10k drift and would "correct" again —
    # measured, and it is why this list is not the obvious one.
    broker = _DriftBroker(seam, [(50000.0, 1.0), (40000.0, 2.0), (40000.5, 3.0)])
    broker.bind(survival)
    watch = survival.SurvivalWatch(
        safety_pad=0.25,
        broker=broker,
        flatten=_NoFlatten(),
        alert=_NoAlert(),
        tolerance=1.0,
    )
    watch.reconcile("boot")
    outcome = watch.reconcile("fill")
    if not outcome.corrected:
        findings.append(
            Finding(
                site,
                f"the real SurvivalWatch reported no drift ({outcome!r}) — the "
                "detector, not this gate, must be what declares the condition",
            )
        )
    else:
        flag.set(
            halt.HaltCause.AGGREGATE_DRIFT,
            f"§11.7 aggregate drift {outcome.drift:+.2f} beyond tolerance",
            now=10.0,
        )
        tally.transitions += 1
        row = plane1.of(seam.EventKind.HALT_SET)[-1]
        if f"{outcome.drift:+.2f}" not in row.reason:
            findings.append(
                Finding(
                    site, f"the row does not carry the measured drift: {row.reason!r}"
                )
            )

    # The within-tolerance CONTROL declares nothing.
    control = watch.reconcile("quiet")
    if control.corrected:
        findings.append(
            Finding(
                f"{site}:control",
                "a poll back within tolerance still reported a correction, so the "
                "drive is insensitive to the detector",
            )
        )
    else:
        tally.falsifiers += 1

    # INVARIANT_BREACH — from a REAL picture_defects call over a torn snapshot.
    torn = seam.FinancialPicture(
        version=7,
        published_ts=1.0,
        balance=50000.0,
        positions=(),
        margin_per_contract={},
        sum_open_margin=0.0,
        sum_reservations=0.0,
        committed=812.5,  # disagrees with its own inputs
        deployable=35000.0,
    )
    defects = loaded.picture.picture_defects(torn, 0.70)
    if not defects:
        findings.append(
            Finding(
                site,
                "the real picture_defects detector found nothing in a torn snapshot",
            )
        )
    else:
        flag.set(halt.HaltCause.INVARIANT_BREACH, "; ".join(defects), now=20.0)
        tally.transitions += 1
        row = plane1.of(seam.EventKind.HALT_SET)[-1]
        if defects[0] not in row.reason:
            findings.append(
                Finding(site, f"the row does not carry the real defect: {row.reason!r}")
            )
    tally.plane1_rows += len(plane1.rows)
    return findings


# --------------------------------------------------------------------------
# The runner
# --------------------------------------------------------------------------


def _vacuity(tally: Tally) -> list[Finding]:
    site = f"{HALT_FILE}:non_vacuity"
    return [
        Finding(site, f"{label}: reached {value}, floor {floor}")
        for label, value, floor in (
            ("transitions driven", tally.transitions, MIN_TRANSITIONS),
            ("Plane-1 rows observed", tally.plane1_rows, MIN_PLANE1_ROWS),
            ("falsifiers caught", tally.falsifiers, MIN_FALSIFIERS),
            ("genuine SIGKILLs", tally.kills, 1),
        )
        if value < floor
    ]


def _arm(label: str, verb) -> list[Finding]:
    """Run one arm. An arm that RAISES is a FAIL naming it, never a cannot-measure.

    MEASURED, and the distinction is the whole point. `load()` failing means the
    SUBJECT IS UNAVAILABLE and is Cannot-measure (§17). An arm raising means the
    subject is present and misbehaving — a planted `auto_clearable` that made the
    machine refuse to construct against its own shipped config came back as
    CANNOT_MEASURE, which is not a PASS but is still the wrong verdict: the
    defect was caught and reported as "could not look".
    """
    try:
        return verb()
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return [
            Finding(
                f"{HALT_FILE}:{label}",
                f"the arm raised {type(exc).__name__}: {exc} — the subject is "
                "present, so this is a defect in it and not an unmeasurable "
                "subject (§17 draws that line at availability, not at behaviour)",
            )
        ]


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    try:
        loaded, error = load(ctx.nix_home)
        if loaded is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        home = ctx.nix_home
        tally = Tally()
        findings: list[Finding] = []
        findings += _arm("setters", lambda: _arm_setters(loaded, home, tally))
        findings += _arm("auto_clear", lambda: _arm_auto_clear(loaded, home, tally))
        findings += _arm("planes", lambda: _arm_planes(loaded, home, tally))
        findings += _arm(
            "entry_not_exit", lambda: _arm_entry_not_exit(loaded, home, tally)
        )
        findings += _arm("limiter_down", lambda: _arm_limiter_down(loaded, home, tally))
        findings += _arm("producers", lambda: _arm_producers(loaded, home))
        findings += _arm(
            "real_detectors", lambda: _arm_real_detectors(loaded, home, tally)
        )
        findings += _vacuity(tally)
        evidence = (
            f"{HALT_FILE}: drove §12.5's six setters against the FROZEN spec's own "
            "sentence, the operator-only clear against an auto-clear sweep, the "
            "condition-clear+floor hybrid in both directions, §12.10's inventory "
            "row read off the table (HALT = Plane 1 AND Plane 2; blackout/roll = "
            "Plane 2 only), HALT-gates-ENTRY-never-EXIT with a real protective "
            "flatten firing under a set flag, and the Limiter-down retroactive "
            f"booking across a GENUINE SIGKILL ({tally.kills} kill(s), "
            f"{tally.transitions} transitions, {tally.plane1_rows} Plane-1 rows, "
            f"{tally.falsifiers} falsifiers caught) — 7 arms"
        )
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


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
