#!/usr/bin/env python3
"""§7.5's contract roll: the identity switch is ATOMIC, and its source is PROVISIONAL.

ONE gate, TWO properties (`nix_check_contract.md` §5.5):

    B3a  every symbol-keyed subsystem (§7.5:521 names six — capture, backfill,
         margin cache, calendar, Renko state, positions) switches front-month
         identity ATOMICALLY at the defined roll instant. No observer, under
         contention, ever sees two subsystems on different contracts for one
         symbol;
    B3b  the roll schedule shipped in this tree is **PROVISIONAL** — rule-derived
         and stamped `high_risk=1` in every row (CHECK-DEBT **D3.170**) — and that
         provenance REACHES the consumer holding the identity.

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md` unless another document
is named on the line.

------------------------------------------------------------------------------
WHAT THIS GATE DOES **NOT** CLAIM, STATED BEFORE WHAT IT DOES
------------------------------------------------------------------------------
**IT DOES NOT CLAIM THE ROLL DATES ARE RIGHT.** §7.5:520 defines the front month
as the **volume leader** — an observation of where liquidity has migrated — and
sources the live schedule from the calendar poller. The artifact this gate reads,
`scripts/crucible/calendar_data/nix_roll_schedule.csv`, observes nothing: every
row is derived from a listing/last-trading-day rule with a fixed lead, and every
row carries `high_risk=1` saying so. `crucible.calendar.Roll`'s own docstring
says so. CHECK-DEBT **D3.170** is the open row.

So a green here means: *the switch mechanism is atomic, and the provenance of the
dates it switches on is carried honestly to whoever keys on them.* It does not
mean the dates match the exchange, and the gate's evidence string says that in
words, because an operator reading `[ok] check_contract_roll` and inferring
"our roll calendar is correct" would have been misled by this instrument.

The gate REDDENS if that provenance is dropped — a laundered flag is worse than
no flag, because it converts an honest unknown into a false certainty.

------------------------------------------------------------------------------
THE TRAP: AN ATOMICITY CLAIM THAT NEVER CROSSES THE ROLL
------------------------------------------------------------------------------
A snapshot sampled entirely on one side of the roll is self-consistent for free,
so "no tear observed" over such a drive is a statement about the drive. Both
atomicity arms therefore (a) resolve an epoch strictly BEFORE the roll instant
and strictly AFTER it and require the two contracts to DIFFER, and (b) run a
writer thread flipping across the roll against reader threads and require the
readers to have observed BOTH contracts before any no-tear assertion is made.

And an atomicity claim with no torn counterpart is guaranteed by construction
rather than measured (the ruling ARC 032 recorded for the published row). So the
same harness is run against `_TornBook`, a subclass that switches the subsystems
in TWO steps — the shape a reasonable implementation reaches for — and the gate
FAILS if that plant does NOT tear.

------------------------------------------------------------------------------
WHY DRIVE RATHER THAN SHELL OUT TO PYTEST
------------------------------------------------------------------------------
The premise this section used to state was FALSE and is corrected here rather
than carried (ARC 034, CHECK-DEBT D3.201). It read *"the runtime `.venv`
`verify.py` runs under has no pytest (dev-only, per the ARC CRUCIBLE-DEPSPLIT
venv split)"*, and **pytest 9.1.1 IS installed in `/home/bbt/nix/.venv`** —
measured, `importlib.util.find_spec("pytest")` resolves under that interpreter.
So the sentence was a claim about the shipped tree that the shipped tree
contradicts, and it was being used to explain why properties this gate could
assert are asserted somewhere else instead.

**WHAT REMAINS TRUE, and it is the reason the structure below is unchanged:** a
check that shelled out to pytest would make one instrument's verdict depend on
another runner's exit code, and `verify.py` is required to be independently
runnable per `docs/nix_check_contract.md` §4.2. So this gate imports `nixrisk.roll` straight
out of `ctx.nix_home` — the `check_flatten` pattern: path-keyed import with
`sys.modules`/`sys.path` restored — and drives it directly.

**WHAT IS NOT SETTLED, and is an architect ruling rather than a docstring
edit:** whether a gate may rely on the pytest suite at all. If it may, several
checks in this tree are duplicate instruments under doctrine C.9; if it may not,
the properties currently living only in `scripts/tests/` owe a retrofit here.
CHECK-DEBT D3.201 holds the question. ARC 034 corrected the false sentence and
deliberately did NOT restructure this gate.

------------------------------------------------------------------------------
`debug.md` §7.12 — WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING?
------------------------------------------------------------------------------
 1. The subject could fail to import, or the vendored artifact could be absent.
    CLOSED: either is CANNOT_MEASURE naming the exception (§17, never a PASS).
 2. **The identity could never shift.** CLOSED: `_arm_atomic` asserts the
    contract BEFORE the roll instant differs from the one AFTER it, over the
    REAL artifact, before it asserts anything about atomicity.
 3. **The race could never race.** CLOSED: the harness asserts a sample floor
    AND that the readers observed BOTH contracts — i.e. the writer really
    crossed the roll while the readers were running.
 4. **The subsystem set could be empty**, making every snapshot trivially
    consistent. CLOSED: the arm asserts the snapshot's cardinality equals
    `len(SYMBOL_KEYED_SUBSYSTEMS) × symbols`, and that the subsystem list is
    §7.5:521's own six.
 5. **The plant could stop tearing**, leaving "the real one passed"
    uninformative. CLOSED: a non-tearing plant is a FAIL naming the falsifier.
 6. **The provisional flag could be trivially true** because nothing sets it, or
    trivially satisfied because the artifact is in fact corroborated. CLOSED:
    `_arm_provenance` reads `high_risk` off the artifact FIRST (the positive
    observation), then requires the epoch to name the symbol, then shows a
    laundering adapter produces a clean-looking epoch over the same contract —
    so the flag is proven to be load-bearing rather than constant.
"""

from __future__ import annotations

import importlib
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code,too-few-public-methods,too-many-locals
# pylint: disable=missing-function-docstring,missing-class-docstring
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = False
DEPENDS_ON: tuple[str, ...] = ()
#: This gate IMPORTS the roll package out of `ctx.nix_home` and runs a
#: multi-threaded race harness inside its own process.
RESOURCES: tuple[str, ...] = (
    "interpreter:sys.modules",
    "interpreter:sys.path",
    "threads",
)
#: NON-CORRECTABLE: the subject is risk-path source (the front-month identity
#: every symbol-keyed subsystem routes on) plus a vendored calendar artifact. A
#: gate that could edit either until its own drive came back clean would be
#: manufacturing green over the seam §7.5 forbids stitching across.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is risk-path source (scripts/nixrisk/roll.py, §7.5's atomic "
    "front-month identity) over a vendored calendar artifact; a repair that "
    "edited the schedule to satisfy its own gate would silently move a roll "
    "date every symbol-keyed subsystem keys on"
)
SUBJECTS: tuple[str, ...] = ("scripts/nixrisk/roll.py",)

NAME = "check_contract_roll"

ROLL_FILE = "scripts/nixrisk/roll.py"
SCHEDULE_FILE = "scripts/crucible/calendar_data/nix_roll_schedule.csv"
PACKAGE = "nixrisk"

#: The instant the schedule is probed at. Inside the vendored span and inside
#: the shipped symbol scope; the roll instant itself is READ from the artifact,
#: never typed here — a literal would be a second copy of the schedule.
PROBE = datetime(2026, 8, 15, tzinfo=UTC)
SYMBOLS = ("ES", "NQ")
#: How many torn snapshots a reader keeps. The fact to establish is that a tear
#: IS observable; an unbounded list of identical tears costs seconds to prove
#: the same thing once.
TORN_SAMPLE_CAP = 25


class Finding(NamedTuple):
    site: str
    why: str


class Loaded(NamedTuple):
    roll: ModuleType
    calendar_seam: ModuleType
    calendar: ModuleType


def _purge(saved: dict[str, ModuleType]) -> None:
    for name in [
        key
        for key in sys.modules
        if key in (PACKAGE, "crucible") or key.startswith((f"{PACKAGE}.", "crucible."))
    ]:
        del sys.modules[name]
    sys.modules.update(saved)


def load(home: Path) -> tuple[Loaded | None, str]:
    saved_path = list(sys.path)
    saved_modules = {
        key: value
        for key, value in sys.modules.items()
        if key in (PACKAGE, "crucible") or key.startswith((f"{PACKAGE}.", "crucible."))
    }
    _purge({})
    sys.path.insert(0, str((home / "scripts").resolve()))
    importlib.invalidate_caches()
    try:
        loaded = Loaded(
            roll=importlib.import_module("nixrisk.roll"),
            calendar_seam=importlib.import_module("nixrisk.calendar_seam"),
            calendar=importlib.import_module("crucible.calendar"),
        )
        # The artifact has to be READABLE, not merely importable: a missing CSV
        # raises only on first query, and a gate that imported cleanly and then
        # measured nothing would be the §17 masking case.
        loaded.calendar.known_symbols()
        # THE SUBJECT MUST BE THE ONE UNDER `home`. `sys.path` may already carry
        # the canonical tree (a test process, another check), and an import that
        # silently resolved there would drive the SHIPPED module while claiming
        # to drive the copy — a gate measuring a different file than it names,
        # which is exactly §17's masking case wearing a green.
        root = str(home.resolve())
        for name, module in loaded._asdict().items():
            origin = getattr(module, "__file__", "") or ""
            if not origin.startswith(root):
                return None, (
                    f"{ROLL_FILE}: {name} resolved to {origin!r}, which is "
                    f"OUTSIDE {root} — the subject under measurement is not the "
                    "one named, so nothing was measured (§17: never a PASS)"
                )
        return loaded, ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{ROLL_FILE}: cannot import nixrisk.roll / read {SCHEDULE_FILE} from "
            f"{home} — {type(exc).__name__}: {exc}. The subject is unavailable, "
            "so nothing was measured (§17: never a PASS)"
        )
    finally:
        sys.path[:] = saved_path
        _purge(saved_modules)


# --------------------------------------------------------------------------
# Doubles — a schedule whose answer really CHANGES at a defined instant
# --------------------------------------------------------------------------


class _DrivenSchedule:
    def __init__(self, loaded: Loaded, roll_at: datetime) -> None:
        self._identity = loaded.calendar_seam.ContractIdentity
        self._state = loaded.calendar_seam.CacheState
        self.roll_at = roll_at

    def front_contract(self, symbol: str, at: datetime) -> Any:
        if symbol not in SYMBOLS:
            return None
        old = at < self.roll_at
        return self._identity(
            symbol=symbol,
            contract=f"{symbol}{'U26' if old else 'Z26'}",
            front_from=self.roll_at - timedelta(days=90) if old else self.roll_at,
            roll_at=self.roll_at if old else self.roll_at + timedelta(days=90),
        )

    def next_roll(self, symbol: str, at: datetime) -> datetime | None:
        del symbol
        return self.roll_at if at <= self.roll_at else None

    def state(self) -> Any:
        return self._state.FRESH


def _torn_book_class(loaded: Loaded) -> Any:
    """THE PLANT, built against the loaded subject: a TWO-STEP switch.

    It yields mid-switch, and that is the microscope rather than the defect: the
    defect is that a partially-applied state EXISTS at all, and the yield only
    decides how often a reader lands in it. The real book cannot be given the
    same yield because there is no point inside its `advance` at which a partial
    state is bound to the attribute a reader loads — which is the claim.
    """

    # `loaded.roll` is imported at RUNTIME out of ctx.nix_home, so mypy cannot
    # see the base class at all — the ignore covers the dynamic base.
    class _TornBook(loaded.roll.RollIdentityBook):  # type: ignore[misc,name-defined]
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._torn: dict[tuple[str, str], str] = {}

        def advance(self, at: datetime) -> Any:
            epoch = super().advance(at)
            for subsystem in loaded.roll.SYMBOL_KEYED_SUBSYSTEMS:
                for symbol, identity in epoch.identities.items():
                    self._torn[(subsystem, symbol)] = identity.contract
                time.sleep(0)
            return epoch

        def snapshot(self) -> Any:
            return dict(self._torn.items())

    return _TornBook


def _race(
    loaded: Loaded, book: Any, roll_at: datetime, *, readers: int = 3, flips: int = 30
):
    """Hammer `snapshot()` from N threads while a writer flips across the roll.

    Returns `(torn, contracts_seen, samples)`. The writer yields between flips:
    without it CPython's GIL lets it finish every flip inside one switch
    interval and the readers only ever observe one side — which is why every
    caller asserts `contracts_seen` before asserting anything about tearing.
    """
    before = roll_at - timedelta(seconds=1)
    after = roll_at + timedelta(seconds=1)
    torn: list[dict] = []
    seen: set[str] = set()
    samples = [0]
    stop = threading.Event()
    lock = threading.Lock()

    def writer() -> None:
        for index in range(flips):
            book.advance(before if index % 2 == 0 else after)
            time.sleep(0)
        stop.set()

    def reader() -> None:
        local_torn: list[dict] = []
        local_seen: set[str] = set()
        count = 0
        while not stop.is_set():
            try:
                snap = book.snapshot()
            except loaded.roll.NoFrontContract:
                continue
            count += 1
            per_symbol: dict[str, set[str]] = {}
            for (_subsystem, symbol), contract in snap.items():
                per_symbol.setdefault(symbol, set()).add(contract)
                local_seen.add(contract)
            if (
                any(len(values) > 1 for values in per_symbol.values())
                and len(local_torn) < TORN_SAMPLE_CAP
            ):
                local_torn.append(dict(snap))
        with lock:
            torn.extend(local_torn)
            seen.update(local_seen)
            samples[0] += count

    threads = [threading.Thread(target=reader) for _ in range(readers)]
    for thread in threads:
        thread.start()
    writer()
    for thread in threads:
        thread.join()
    return torn, seen, samples[0]


# --------------------------------------------------------------------------
# ARM 1 (B3a) — the ATOMIC switch, driven ACROSS the roll instant
# --------------------------------------------------------------------------


def _arm_atomic(loaded: Loaded) -> list[Finding]:
    roll = loaded.roll
    site = f"{ROLL_FILE}:atomic"
    findings: list[Finding] = []

    schedule = roll.VendoredRollSchedule()
    roll_at = schedule.next_roll("ES", PROBE)
    if roll_at is None:
        return [
            Finding(
                site,
                f"the vendored schedule declares no ES roll after "
                f"{PROBE.isoformat()} — nothing to drive across",
            )
        ]

    # (a) NON-VACUITY: the identity really moves, over the REAL artifact.
    real = roll.RollIdentityBook(schedule=schedule, symbols=SYMBOLS)
    before = real.advance(roll_at - timedelta(seconds=1)).contract_for(
        "positions", "ES"
    )
    after = real.advance(roll_at + timedelta(seconds=1)).contract_for("positions", "ES")
    if before == after:
        findings.append(
            Finding(
                site,
                f"the ES identity did not move across {roll_at.isoformat()} "
                f"({before!r} both sides) — no roll was crossed, so nothing "
                "about atomicity was measured",
            )
        )
        return findings

    # (b) the subsystem set is §7.5:521's own six, and it is not empty.
    subsystems = roll.SYMBOL_KEYED_SUBSYSTEMS
    if len(subsystems) != 6:
        findings.append(
            Finding(
                site,
                f"SYMBOL_KEYED_SUBSYSTEMS holds {len(subsystems)} member(s) "
                f"{subsystems}, and §7.5:521 names six",
            )
        )

    # (c) THE RACE, over a driven schedule so the crossing is dense.
    driven = _DrivenSchedule(loaded, roll_at)
    book = roll.RollIdentityBook(schedule=driven, symbols=SYMBOLS)
    book.advance(roll_at - timedelta(seconds=1))
    torn, seen, samples = _race(loaded, book, roll_at)

    if samples < 100:
        findings.append(
            Finding(
                site, f"the readers sampled only {samples} time(s) — no race happened"
            )
        )
    if not {"ESU26", "ESZ26"} <= seen:
        findings.append(
            Finding(
                site,
                f"the writer never crossed the roll under contention; observed "
                f"{sorted(seen)} — the no-tear result below would be vacuous",
            )
        )
    expected = len(subsystems) * len(SYMBOLS)
    if len(book.snapshot()) != expected:
        findings.append(
            Finding(
                site,
                f"a snapshot holds {len(book.snapshot())} pair(s), expected "
                f"{expected} — a snapshot over fewer subsystems tears less",
            )
        )
    if torn:
        example = torn[0]
        findings.append(
            Finding(
                site,
                f"{len(torn)} TORN snapshot(s): two symbol-keyed subsystems on "
                f"different contracts for one symbol — §7.5:522 requires the "
                f"switch be atomic. Example: {sorted(example.items())[:4]}",
            )
        )

    # (d) THE PLANT: a two-step switch must TEAR under the same harness.
    plant = _torn_book_class(loaded)(schedule=driven, symbols=SYMBOLS)
    plant.advance(roll_at - timedelta(seconds=1))
    plant_torn, plant_seen, plant_samples = _race(loaded, plant, roll_at)
    if plant_samples < 100 or not {"ESU26", "ESZ26"} <= plant_seen:
        findings.append(
            Finding(
                f"{ROLL_FILE}:falsifier[atomic]",
                f"the plant's harness did not race ({plant_samples} samples, "
                f"{sorted(plant_seen)}) — its result says nothing",
            )
        )
    elif not plant_torn:
        findings.append(
            Finding(
                f"{ROLL_FILE}:falsifier[atomic]",
                "the TWO-STEP plant produced NO torn snapshot — it no longer "
                "falsifies, so the real book's clean run proves nothing about "
                "atomicity (the claim would be by construction, not measured)",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM 2 (B3b) — D3.170: the schedule is PROVISIONAL and says so
# --------------------------------------------------------------------------


def _arm_provenance(loaded: Loaded) -> list[Finding]:
    roll = loaded.roll
    site = f"{ROLL_FILE}:provenance"
    findings: list[Finding] = []

    # (a) POSITIVE OBSERVATION on the artifact itself. Asserting "the flag is
    #     set" would measure nothing if the artifact were in fact corroborated.
    schedule = roll.VendoredRollSchedule()
    provisional = schedule.provisional_symbols(PROBE)
    covered = {
        symbol
        for symbol in loaded.calendar.known_symbols()
        if loaded.calendar.front_contract(symbol, PROBE) is not None
    }
    if not covered:
        return [
            Finding(
                site,
                f"{SCHEDULE_FILE} covers no symbol at {PROBE.isoformat()} — "
                "nothing to state a provenance about",
            )
        ]
    if provisional != covered:
        findings.append(
            Finding(
                site,
                f"D3.170 says EVERY row of {SCHEDULE_FILE} is rule-derived and "
                f"high_risk=1, but the provisional set {sorted(provisional)} is "
                f"not the covered set {sorted(covered)} — either the artifact "
                "changed or the flag is not being read off it",
            )
        )

    # (b) the provenance REACHES the epoch a consumer holds.
    book = roll.RollIdentityBook(
        schedule=schedule, symbols=SYMBOLS, provisional_symbols=provisional
    )
    book.advance(PROBE)
    if set(SYMBOLS) - set(book.provisional_symbols()):
        findings.append(
            Finding(
                site,
                f"the epoch names {sorted(book.provisional_symbols())} provisional, "
                f"dropping {sorted(set(SYMBOLS) - set(book.provisional_symbols()))} "
                "— a consumer keying capture/backfill/positions on a rule-derived "
                "roll date cannot learn that it is doing so",
            )
        )

    # (c) THE PLANT: an adapter that DROPS the flag. It must be DISTINGUISHABLE
    #     from the honest one — otherwise the flag is decoration.
    laundered = roll.RollIdentityBook(
        schedule=schedule, symbols=SYMBOLS, provisional_symbols=()
    )
    laundered.advance(PROBE)
    if laundered.provisional_symbols():
        findings.append(
            Finding(
                f"{ROLL_FILE}:falsifier[provenance]",
                "the laundering plant reported a provenance it was never given — "
                "it no longer falsifies, so the arm above is not a discriminator",
            )
        )
    if laundered.contract_for("capture", "ES") != book.contract_for("capture", "ES"):
        findings.append(
            Finding(
                f"{ROLL_FILE}:falsifier[provenance]",
                "the laundering plant changed the CONTRACT as well as the flag — "
                "the plant must isolate provenance, or it is testing two things",
            )
        )
    return findings


# --------------------------------------------------------------------------
# VERDICT
# --------------------------------------------------------------------------


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    try:
        loaded, error = load(ctx.nix_home)
        if loaded is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        findings: list[Finding] = []
        findings += _arm_atomic(loaded)
        findings += _arm_provenance(loaded)
        evidence = (
            f"{ROLL_FILE}: drove the §7.5 front-month identity ACROSS the roll "
            f"instant the vendored schedule declares (identity SHIFTS, asserted "
            f"first), then raced {len(loaded.roll.SYMBOL_KEYED_SUBSYSTEMS)} "
            f"symbol-keyed subsystems x {len(SYMBOLS)} symbols under a writer "
            "flipping across the roll — no torn snapshot, and a TWO-STEP plant "
            "proven to tear under the same harness. "
            f"PROVISIONAL: every row of {SCHEDULE_FILE} is RULE-DERIVED and "
            "stamped high_risk=1 (CHECK-DEBT D3.170); §7.5:520 defines the front "
            "month as the VOLUME LEADER, which no offline artifact observes. This "
            "gate measures the ATOMICITY of the switch and that the provenance "
            "reaches the consumer — it asserts NOTHING about the roll dates being "
            "exchange-observed, and a green here must not be read as saying so"
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
