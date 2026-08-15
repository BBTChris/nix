#!/usr/bin/env python3
"""§3's atomicity rule, held against a reader that is ACTUALLY RACING a writer.

Subject: `scripts/nixrisk/picture.py`.

Authority — `docs/nics_risk_subsystem_spec_v1.3.md` §3, §11, §12.7: the *FULL
FINANCIAL-PICTURE PUBLISH* and its ATOMICITY RULE, the running aggregates and
precomputed deployable, and the state-table transport (LOCKED v1.3).

Instrument doctrine — `docs/nix_check_contract.md` §4, §5, §17, §18, and
`docs/VERIFY-AND-CHECKS.md` Part C.

ONE property (§5.5): *the financial picture is observable only as one
self-consistent snapshot under one version stamp, and a consumer whose mirror is
not complete and fresh refuses to size.*

**Boundary against `check_state_bus` (§5.5 requires it stated in both).** That
gate owns `scripts/nixbus/statebus.py` — whether the TRANSPORT delivers, serves
snapshots on subscribe, and stamps freshness. This gate owns
`scripts/nixrisk/picture.py` — whether the PICTURE riding that transport is
atomic and whether its mirror refuses when it should. Neither re-measures the
other's subject: this gate would still be able to fail if statebus were perfect,
and check_state_bus would still fail if the picture were torn.

---

## debug.md §7.12 — WHAT WOULD HAVE TO BE TRUE FOR THIS GATE TO PASS WHILE
## MEASURING NOTHING

1. **NOTHING RACES.** A publisher observed only by a reader that never contends
   with it proves nothing about atomicity; the assertion would hold over a
   quiescent object. Closed by `race()`: a writer THREAD mutates balance and the
   position table in a loop while a reader thread reads, and the run does not end
   on a clock — it ends when the reader has recorded `MIN_READS` reads across
   `MIN_VERSIONS` DISTINCT version stamps, which is the proof the writer really
   moved underneath it. Falling short of either floor is CANNOT_MEASURE and names
   the shortfall. (D3.39: arrival terminates, the clock is only a ceiling, so the
   verdict is not a function of machine load.)

2. **THE DETECTOR IS ASLEEP.** This is the sharp one, and it is why three PLANTS
   run on every invocation before the subject is judged at all:

   * `_TwoReadConsumer` — §3's forbidden shape on the CONSUMER side, literally:
     it reads `current()` for the balance, yields, and reads `current()` again
     for the position table. It is the tightest control available, because it
     shares the writer, the cadence and the thread structure with the measured
     arm and differs in exactly one respect — one read or two.
   * `_TwoAttributeBook` — the same shape on the PUBLISHER side: a book that
     keeps balance and the table in two attributes and stores them one after the
     other.
   * `_StopBookJoinBook` — **ARC 032's plant, and the only one with any power
     over the field ARC 032 added.** It is OPTION B, the design the architect
     REFUSED by name (D3.136): a publisher that keeps stop distances in a SECOND
     table on its own clock and JOINS them onto rows read from the first at read
     time. Its first table is the REAL `FinancialPictureBook`, so balance and the
     rows are atomic and the ONLY thing it can tear on is `stop_distance` — which
     is what makes it a measurement of the ruling rather than a restatement of
     it. §6.4: *"independent tables tick on independent clocks"*.

   **Each plant must produce at least `MIN_TEARS` observed tears, and the join
   plant must produce at least `MIN_STOP_TEARS` of them ON THE `stop_distance`
   AXIS, or the gate returns CANNOT_MEASURE.** A concurrency test that never
   observes the failing case is a sleep with an assertion after it, and this gate
   refuses to be one. The stop-axis floor is separate because the two older
   plants tear on `balance`-versus-row and would satisfy a single floor while
   proving nothing whatever about the new field.

3. **THE TEAR IS INVISIBLE ANYWAY.** `picture.picture_defects` catches a snapshot
   whose derived fields disagree with its own inputs — and it CANNOT catch §3's
   actual tear, because a publisher that reads balance at generation *k* and the
   table at *k+1* and then derives consistently produces a perfectly coherent
   snapshot (`picture_defects`' docstring says so). Closed by planting a
   GENERATION LINK into the world the writer publishes: balance carries the
   generation and so does every row's `margin`, its `size` **and its
   `stop_distance`**, so a snapshot assembled from two generations names them
   both. Both detectors run; the second is the one with the power.

   **TWO INDEPENDENT TEAR AXES since ARC 032**, because a re-proof that races the
   old fields and ignores the new one says nothing about the new one:

   * **AXIS 2, the row against ITSELF** — `stop_distance` must belong to the same
     generation as that row's own `size` and `margin`. This axis needs no
     reference to `balance` at all, which is exactly why it can see a cross-table
     join that keeps balance and the table perfectly coherent.
   * **AXIS 1, the row against BALANCE** — a row's `margin` must belong to the
     generation `balance` carries.

   They overlap by construction and the overlap is stated rather than hidden: a
   `stop_distance` disagreeing with `balance` must ALSO disagree either with its
   own row's `margin` (axis 2 fires) or with nothing, in which case that `margin`
   already disagrees with `balance` (axis 1 fires). So the pair is gapless, and
   neither clause is dead: the join plant fires axis 2 and the two older plants
   fire axis 1.

4. **THE WIRE IS NEVER USED.** An in-memory race says nothing about §12.7. Closed
   by `_bus_race`, which decodes every message a real `zmq` SUB actually received
   and holds each to the same two detectors, and by a byte floor: zero wire bytes
   is CANNOT_MEASURE.

5. **THE LATE SUBSCRIBER IS NEVER LATE.** Snapshot-on-subscribe is mandatory, not
   polish (§12.7). Closed by subscribing AFTER the table is populated, and by
   staging the two subscribers SEQUENTIALLY — CHECK-DEBT D3.39 measured that
   back-to-back subscribers make the arm vacuous, because PUB/SUB fans one
   snapshot out to every already-connected peer.

6. **THE STALE RULE IS NEVER EXERCISED.** Closed by `_arm_stale`, which requires
   `PictureMirror.tradable()` to refuse an incomplete mirror AND an over-age one,
   each naming its reason, and to PERMIT a complete fresh one — the control
   without which "always refuses" would pass.

---

## WHAT THIS GATE CANNOT PROVE, STATED RATHER THAN IMPLIED

**AXIS 2's power over the MEASURED ARM is conditional, and saying so is the
point.** `_world` builds one `PositionRow` per generation and the subject
publishes that object whole, so `stop_distance`, `size` and `margin` are
inseparable in the measured arm by construction: axis 2 cannot fire there no
matter what `FinancialPictureBook` does. What axis 2 therefore proves is
narrower than "the measured arm never tore on `stop_distance`" and is worth
stating in the narrow form: *a publisher that REBUILDS rows — joining the
distance on from a second table — is caught, and this publisher does not rebuild
rows.* The join plant supplies the first half over a live race; the second half
is a can-fail control in `scripts/tests/test_check_picture_atomicity.py`
(`..._a_STOP_BOOK_JOIN_in_the_SUBJECT_reddens_the_MEASURED_arm_by_name`), which
puts the join INSIDE the subject and requires the measured arm to redden, so the
claim is a measurement on both halves rather than an argument on one.
Axis 1 has unconditional power over the measured arm (a two-commit
publisher reddens it); axis 2 does not, and a gate that let the two read alike
would be claiming the stronger of them for free.

It runs one process. It does not prove cross-process delivery, fd inheritance, or
behaviour under a real Limiter's load. (`check_allocator_mirror` arm 6 crosses a
real boundary for the CONSUMER's mirror; nothing here does.) It proves nothing
about stop conversion,
protective-exit wiring, session-close flatten, HALT semantics, cold-start
reconciliation, the Sentinel, Scoring or the Allocator — none of which exist yet.
A green here says the picture is atomic and its mirror fails closed; it does NOT
say the Limiter is a safety spine.
"""

from __future__ import annotations

import dataclasses
import secrets
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import (
    CheckResult,
    Context,
    Mode,
    Status,
    result_from_defects,
)

# Deliberately duplicated across every checks/check_*.py: `nix_check_contract.md`
# §4.2 requires each check be independently runnable and map status -> exit code
# identically, and doctrine B.2 requires the crash path return CANNOT_MEASURE in
# both. Those blocks are MANDATED to be the same text.
# pylint: disable=duplicate-code
#
# pylint: disable=too-many-lines
# Six arms, THREE plants (ARC 032 added the stop-book join), a codec probe and a
# §7.12 section that answers six conditions with a named mechanism apiece.
# `nix_check_contract.md` §4.2 requires a check to be a single independently
# runnable artifact, so splitting this across modules would break the contract to
# satisfy a length counter; the honest alternative to the length is fewer
# measurements. Same reasoning `check_allocator_mirror.py` records for itself.
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: `pyzmq` is a `checks/pinned_deps.json` pin; the venv is what makes the bus arm
#: importable at all.
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: TWO claims, declared honestly (D1.54: under-declaring costs correctness,
#: over-declaring costs only parallelism).
#: * `file-write:/tmp` — `tempfile.mkdtemp` plus the absolute-path unlinks in
#:   `_remove_tree`. NEVER `shutil.rmtree`: on POSIX it unlinks through a
#:   directory fd with a bare relative name, which the observer records as an
#:   unattributable `file-write:pic.ipc` that no rooted declaration can cover.
#: * `zmq-ipc` — the AF_UNIX socket libzmq binds and connects. NOT observable by
#:   `check_observed_resource_claims` (libzmq calls `bind(2)` from C, so no
#:   `socket.bind` audit event fires); declared anyway because the PLAN needs to
#:   know, and it is shared with `check_state_bus`, so the two must not run in
#:   one parallel block.
#: * `subprocess:*` is deliberately ABSENT: this gate spawns nothing. The threads
#:   below are threads, and the observer sees no claim for them.
RESOURCES: tuple[str, ...] = ("file-write:/tmp", "zmq-ipc")
TIME_BOUND = True
#: MEASURED on this node, not budgeted: FOUR races (ARC 032 added the stop-book
#: join), one codec probe and three socket rendezvous — 0.70 s, twice. Budgeted
#: with wide headroom because ARRIVAL ends every race and only a race that is
#: BROKEN rather than slow can reach `RACE_CEILING_S` (D3.39).
EXPECTED_S = 20.0
ON_FAIL = "continue"
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is a live concurrency property. There is no on-disk setting to "
    "repair, and a gate that 'corrected' a torn publisher would be rewriting the "
    "code under measurement — the same objection that makes check_state_bus "
    "non-correctable"
)
SUBJECTS: tuple[str, ...] = ("scripts/nixrisk/picture.py",)

NAME = "check_picture_atomicity"

#: The world the writer publishes. `_BASE` is large and round so a generation
#: read back out of `balance` is exact in binary floating point for every
#: generation this gate will ever reach.
_BASE = 1_000_000.0
_ROWS = 3
_FRACTION = 0.70

#: The stop distance in TICKS at generation 0. A row at generation *g* publishes
#: `_STOP_BASE + g`, so the generation is recoverable from `stop_distance` by
#: subtraction and a row whose distance was joined from a different generation is
#: arithmetically visible — the same trick `margin` already plays for balance.
#: It is an OFFSET rather than the bare generation so that the field stays a
#: plausible tick count at generation 0 and so that a row someone forgot to stamp
#: (a literal `stop_distance=20` fixture) reads as generation 0 rather than as
#: whatever generation happens to equal 20.
_STOP_BASE = 20

#: The token every AXIS-2 defect carries, so the stop-axis tears can be counted
#: out of the tear list without a second detector. Doctrine C.9: one instrument.
_STOP_AXIS = "stop_distance axis"

#: Non-vacuity floors (`debug.md` §7.12), each a count the gate must REACH or it
#: says it measured nothing. Floors, not today's numbers (doctrine C.4).
MIN_READS = 2_000
MIN_VERSIONS = 40
MIN_TEARS = 1
#: The join plant's floor, on the `stop_distance` AXIS specifically. Separate
#: from `MIN_TEARS` on purpose: the two older plants tear on balance-versus-row,
#: so a single tear floor is satisfiable while the harness has no power at all
#: over the field ARC 032 added.
MIN_STOP_TEARS = 1
MIN_BUS_MESSAGES = 20
#: Ceiling on ONE race. ARRIVAL ends it; this only bounds a race that is BROKEN
#: rather than slow, which is why it can afford to be enormous (D3.39).
RACE_CEILING_S = 20.0
#: Ceiling on one subscriber's rendezvous. Same reasoning.
RENDEZVOUS_CEILING_MS = 10_000
#: CPython's GIL slice for the duration of the drive. See `_drive`.
SWITCH_INTERVAL_S = 1e-5
PUMP_SERVICE_MS = 50
PUMP_DRAIN_MS = 20
#: Age ceiling the stale arm holds `PictureMirror` to, and the age it plants.
FRESH_S = 5.0
STALE_AGE_S = 3_600.0


def _cannot(detail: str, evidence: list[str]) -> CheckResult:
    """CANNOT_MEASURE with whatever was learned before the wall."""
    return CheckResult(
        name=NAME,
        status=Status.CANNOT_MEASURE,
        detail=detail,
        evidence="; ".join(evidence),
    )


def _import_subjects() -> tuple[Any, Any, str]:
    """Lazy import so an unimportable subject is CANNOT_MEASURE, not a load error."""
    try:
        # pylint: disable=import-outside-toplevel
        from nixbus import statebus
        from nixrisk import picture
    except ImportError as exc:
        return None, None, f"cannot import the subjects under {sys.executable}: {exc!r}"
    return picture, statebus, ""


# ---------------------------------------------------------------------------
# The world, and the two detectors
# ---------------------------------------------------------------------------


def _world(seam: Any, generation: int) -> tuple[float, tuple[Any, ...]]:
    """ONE consistent world state, with the generation encoded in EVERY half.

    That link is the whole instrument. Without it a snapshot built from a stale
    balance and a fresh table is internally perfect and undetectable.

    **FOUR carriers since ARC 032, not two:** `balance`, and each row's `margin`,
    `size` and `stop_distance`. The three row fields are what make AXIS 2 — the
    row judged against ITSELF — expressible at all, and axis 2 is the only axis
    a cross-table join can be caught on, because such a join leaves `balance` and
    the position table perfectly coherent with each other.
    """
    rows = tuple(
        seam.PositionRow(
            trade_id=f"T{index}",
            symbol="MESU6",
            strategy_id="drill",
            size=generation,
            margin=float(generation),
            state=seam.PositionState.OPEN,
            stop_distance=_STOP_BASE + generation,
        )
        for index in range(_ROWS)
    )
    return _BASE + generation, rows


def _row_defect(snapshot: Any, row: Any) -> str:
    """AXIS 2: `""` when this ONE row's three carriers agree with each other.

    Deliberately makes NO reference to `snapshot.balance`. That independence is
    the point: §6.4's cross-table skew — a stop distance kept in a second table
    and joined on at read time — produces a snapshot whose balance and position
    table are mutually perfect, so an axis that consults balance cannot see it.
    """
    stop_generation = row.stop_distance - _STOP_BASE
    if stop_generation == row.size and float(stop_generation) == row.margin:
        return ""
    return (
        f"TORN ROW at version {snapshot.version} [{_STOP_AXIS}]: row "
        f"{row.trade_id} carries stop_distance {row.stop_distance!r} "
        f"(generation {stop_generation}) against size {row.size!r} (generation "
        f"{row.size}) and margin {row.margin!r} (generation {row.margin:.0f}) — "
        "a FRESH stop_distance joined onto a STALE size is the cross-table skew "
        "§6.4 refuses in the same breath as it fixes one snapshot, and §7:501 "
        "would price this held position off a distance that was never true of it"
    )


def _generation_defect(snapshot: Any) -> str:
    """`""` when every field of this ONE snapshot belongs to ONE generation.

    Two axes, checked row-internal FIRST. See the module docstring for why the
    pair is gapless and why neither clause is dead.
    """
    generation = snapshot.balance - _BASE
    for row in snapshot.positions:
        if defect := _row_defect(snapshot, row):
            return defect
        if row.margin != generation:
            return (
                f"TORN READ at version {snapshot.version}: balance {snapshot.balance!r} "
                f"is generation {generation:.0f} while row {row.trade_id} carries "
                f"margin {row.margin!r} (generation {row.margin:.0f}), size "
                f"{row.size!r} and stop_distance {row.stop_distance!r} — §3's "
                "atomicity rule says balance and the position table publish "
                "together as one snapshot, never two separate reads"
            )
    expected = generation * len(snapshot.positions)
    if snapshot.positions and abs(snapshot.sum_open_margin - expected) > 1e-9:
        return (
            f"TORN AGGREGATE at version {snapshot.version}: sum_open_margin "
            f"{snapshot.sum_open_margin!r} is not generation {generation:.0f} x "
            f"{len(snapshot.positions)} rows = {expected!r}"
        )
    return ""


@dataclass
class RaceResult:  # pylint: disable=too-many-instance-attributes
    """What one race actually observed. Every field is a count, not a claim.

    Eight fields, and every one is an OBSERVATION the verdict or the evidence
    reads. Dropping one to satisfy a default threshold of seven would either
    lose a measurement or push it into a nested struct that the arms must then
    unpack — the same objection `seam.py` records for its own value types.
    """

    label: str
    reads: int = 0
    versions: int = 0
    generations: int = 0
    tears: list[str] = field(default_factory=list)
    coherence: list[str] = field(default_factory=list)
    seconds: float = 0.0
    crashed: str = ""

    @property
    def raced(self) -> bool:
        """True when the reader genuinely saw the writer move underneath it."""
        return self.reads >= MIN_READS and self.versions >= MIN_VERSIONS

    @property
    def tear_rate(self) -> float:
        """Tears per read. The PLANTS' rates are this gate's statement of power.

        A measured arm reporting zero tears means nothing on its own; it means
        something against a plant that tore at this rate over the same number of
        reads, under the same writer, in the same process.
        """
        return len(self.tears) / max(1, self.reads)

    @property
    def stop_tears(self) -> int:
        """Tears on AXIS 2 — the `stop_distance` axis — counted, not assumed.

        Read out of the tear TEXT rather than from a second detector, because a
        second detector is a second instrument for one property (doctrine C.9)
        and could drift from the one whose message the evidence quotes.
        """
        return sum(1 for tear in self.tears if _STOP_AXIS in tear)

    @property
    def stop_tear_rate(self) -> float:
        """Stop-axis tears per read. THE figure ARC 032's re-proof turns on."""
        return self.stop_tears / max(1, self.reads)

    def summary(self) -> str:
        """One line of narration for the evidence string."""
        return (
            f"{self.label}: {self.reads} read(s) across {self.versions} distinct "
            f"version(s), writer reached generation {self.generations}, "
            f"{len(self.tears)} tear(s) ({self.tear_rate:.1%}), of which "
            f"{self.stop_tears} on the {_STOP_AXIS} ({self.stop_tear_rate:.1%}), "
            f"{len(self.coherence)} incoherent, {self.seconds:.2f}s"
        )


def race(  # pylint: disable=too-many-locals
    picture_mod: Any, seam: Any, label: str, reader: Any, book: Any
) -> RaceResult:
    """Run ONE writer thread against `reader` until the floors are reached.

    `reader()` returns a snapshot; whatever assembles it — the book itself or a
    planted two-read consumer — is the thing under measurement.
    """
    out = RaceResult(label=label)
    stop = threading.Event()
    # Two separate typed cells rather than one `dict[str, object]`: the writer
    # thread's only outputs are a counter and a failure string, and mixing them
    # into one mapping costs the reader its types for no gain.
    reached: list[int] = [0]
    failure: list[str] = []

    def writer() -> None:
        generation = 1
        while not stop.is_set():
            balance, rows = _world(seam, generation)
            try:
                book.commit(balance=balance, positions=rows)
            except Exception as exc:  # noqa: BLE001 pylint: disable=broad-except
                failure.append(f"{type(exc).__name__}: {exc}")
                return
            reached[0] = generation
            generation += 1

    thread = threading.Thread(target=writer, name=f"wal-race-{label}", daemon=True)
    started = time.monotonic()
    thread.start()
    try:
        versions: set[int] = set()
        deadline = started + RACE_CEILING_S
        while time.monotonic() < deadline:
            snapshot = reader()
            out.reads += 1
            versions.add(snapshot.version)
            if defect := _generation_defect(snapshot):
                out.tears.append(defect)
            out.coherence.extend(picture_mod.picture_defects(snapshot, _FRACTION))
            if out.reads >= MIN_READS and len(versions) >= MIN_VERSIONS:
                break
        out.versions = len(versions)
    finally:
        stop.set()
        thread.join(timeout=5.0)
    out.seconds = time.monotonic() - started
    out.generations = reached[0]
    out.crashed = failure[0] if failure else ""
    return out


# ---------------------------------------------------------------------------
# The three PLANTS. None touches a production artifact (doctrine C.8).
# ---------------------------------------------------------------------------


class _TwoReadConsumer:  # pylint: disable=too-few-public-methods
    # One public verb (`__call__`) because it IS one verb: a reader. A second
    # method would be a plant doing something the measured arm's reader does
    # not, which is exactly what would break the control.
    """§3's forbidden shape on the CONSUMER side: `current()` twice, one snapshot.

    THE TIGHTEST CONTROL THIS GATE HAS. It shares the writer, the cadence, the
    thread structure and the real `FinancialPictureBook` with the measured arm,
    and differs in exactly one respect: it takes TWO reads where the measured arm
    takes one. If it does not tear, the harness has no power and the measured
    arm's clean sheet means nothing.
    """

    def __init__(self, seam: Any, book: Any) -> None:
        self._seam = seam
        self._book = book

    def __call__(self) -> Any:
        first = self._book.current()
        time.sleep(0)  # the window §3 forbids, opened deliberately
        second = self._book.current()
        rows = second.positions
        open_margin = sum(row.margin for row in rows)
        return self._seam.FinancialPicture(
            version=first.version,
            published_ts=first.published_ts,
            balance=first.balance,
            positions=rows,
            margin_per_contract={},
            sum_open_margin=open_margin,
            sum_reservations=0.0,
            committed=open_margin,
            deployable=max(0.0, _FRACTION * first.balance - open_margin),
        )


class _TwoAttributeBook:
    """§3's forbidden shape on the PUBLISHER side: two attributes, two stores."""

    def __init__(self, seam: Any) -> None:
        self._seam = seam
        self._version = 0
        self._balance = _BASE
        self._positions: tuple[Any, ...] = ()

    def commit(self, *, balance: float, positions: tuple[Any, ...]) -> None:
        """Store the two halves separately. THE PLANT."""
        self._version += 1
        self._balance = balance
        time.sleep(0)
        self._positions = positions

    def current(self) -> Any:
        """Read the two halves separately, exactly as §3 forbids."""
        balance = self._balance
        time.sleep(0)
        rows = self._positions
        open_margin = sum(row.margin for row in rows)
        return self._seam.FinancialPicture(
            version=max(1, self._version),
            published_ts=time.time(),
            balance=balance,
            positions=rows,
            margin_per_contract={},
            sum_open_margin=open_margin,
            sum_reservations=0.0,
            committed=open_margin,
            deployable=max(0.0, _FRACTION * balance - open_margin),
        )


class _StopBookJoinBook:
    """PLANT THREE: **OPTION B**, the design the architect refused (D3.136).

    A publisher that keeps stop distances in a SECOND TABLE on its own clock and
    JOINS them onto rows read out of the first table at read time. §6.4 refuses
    it by name — *"independent tables tick on independent clocks, so a sizing
    pass could read fresh margin against slightly stale balance — cross-table
    skew, the same split-brain we removed for balance, reintroduced at a new
    seam"* — and the whole of ARC 032's seam widening is the alternative.

    **This plant is why the re-proof is a re-proof.** Its FIRST table is the real
    `FinancialPictureBook`, so balance, `size` and `margin` are atomic and
    mutually perfect; the only field it can possibly tear on is `stop_distance`.
    If it does not tear, the harness has no power over the field this arc added
    and the measured arm's clean sheet ON THAT FIELD means nothing — which is the
    exact shape of a re-proof that races the old fields and ignores the new one.

    Doctrine C.8: it touches no production artifact. It CONSUMES the real book
    and strips the distance out of what it stores there, which is precisely what
    a publisher with a separate stop book would have to publish.
    """

    def __init__(self, picture_mod: Any, seam: Any) -> None:
        del seam
        self._book = _new_book(picture_mod)
        #: THE SECOND TABLE. Its own dict, its own store, its own clock.
        self._stops: dict[str, int] = {}

    def commit(self, *, balance: float, positions: tuple[Any, ...]) -> None:
        """Advance the two tables SEPARATELY. The forbidden shape, on purpose."""
        stripped = tuple(
            dataclasses.replace(row, stop_distance=_STOP_BASE) for row in positions
        )
        self._book.commit(balance=balance, positions=stripped)
        time.sleep(0)  # the window two independent clocks always have
        self._stops = {row.trade_id: row.stop_distance for row in positions}

    def current(self) -> Any:
        """Read table one, then table two, then JOIN. Two reads, one snapshot."""
        picture = self._book.current()  # table 1 — atomic, one version stamp
        time.sleep(0)
        stops = self._stops  # table 2 — a SECOND read, on a different clock
        rows = tuple(
            dataclasses.replace(row, stop_distance=stops.get(row.trade_id, _STOP_BASE))
            for row in picture.positions
        )
        return dataclasses.replace(picture, positions=rows)


# ---------------------------------------------------------------------------
# Drivers — each returns OBSERVATIONS, never a verdict
# ---------------------------------------------------------------------------


def _new_book(picture_mod: Any) -> Any:
    return picture_mod.FinancialPictureBook(
        balance=_BASE, deployable_fraction=_FRACTION
    )


#: The plants whose tears give the measured arm its power, and the AXIS each one
#: has power on. Read by `_arm_plants` and by `_arm_measured`, so the floor and
#: the power statement can never name different populations.
PLANT_KEYS: tuple[str, ...] = ("plant_consumer", "plant_publisher", "plant_join")
#: The one plant that can tear on `stop_distance`, named once.
STOP_PLANT_KEY = "plant_join"


def run_races(picture_mod: Any, seam: Any) -> dict[str, RaceResult]:
    """The measured arm and all three plants, under one harness."""
    measured_book = _new_book(picture_mod)
    plant_book = _new_book(picture_mod)
    torn_book = _TwoAttributeBook(seam)
    join_book = _StopBookJoinBook(picture_mod, seam)
    return {
        "measured": race(
            picture_mod, seam, "measured", measured_book.current, measured_book
        ),
        "plant_consumer": race(
            picture_mod,
            seam,
            "PLANT two-read consumer",
            _TwoReadConsumer(seam, plant_book),
            plant_book,
        ),
        "plant_publisher": race(
            picture_mod, seam, "PLANT two-attribute book", torn_book.current, torn_book
        ),
        STOP_PLANT_KEY: race(
            picture_mod, seam, "PLANT stop-book join", join_book.current, join_book
        ),
    }


def _endpoint(statebus: Any, root: Path, name: str) -> str:
    return str(statebus.endpoint_for(name, root=root))


def _bus_race(  # pylint: disable=too-many-locals
    picture_mod: Any, statebus: Any, seam: Any, root: Path
) -> dict[str, Any]:
    """A real SUB socket racing a real publisher. Every message is judged."""
    endpoint = _endpoint(statebus, root, "pic")
    publisher = statebus.StatePublisher(endpoint)
    sink = picture_mod.StateBusPictureSink(publisher)
    book = picture_mod.FinancialPictureBook(
        balance=_BASE, deployable_fraction=_FRACTION, sink=sink
    )
    subscriber = statebus.StateSubscriber(endpoint, [picture_mod.TOPIC])
    stop = threading.Event()
    seen: list[Any] = []
    tears: list[str] = []
    errors: list[str] = []

    def writer() -> None:
        generation = 1
        while not stop.is_set():
            balance, rows = _world(seam, generation)
            book.commit(balance=balance, positions=rows)
            generation += 1
            time.sleep(0.0005)

    thread = threading.Thread(target=writer, name="bus-race", daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + RACE_CEILING_S
        while time.monotonic() < deadline and len(seen) < MIN_BUS_MESSAGES * 2:
            for message in subscriber.drain(PUMP_DRAIN_MS):
                try:
                    snapshot = picture_mod.decode_picture(message.payload)
                except picture_mod.PictureError as exc:
                    errors.append(str(exc))
                    continue
                seen.append(snapshot)
                if defect := _generation_defect(snapshot):
                    tears.append(defect)
                tears.extend(picture_mod.picture_defects(snapshot, _FRACTION))
    finally:
        stop.set()
        thread.join(timeout=5.0)
        subscriber.close()
        publisher.close()
    return {
        "messages": len(seen),
        "bytes": subscriber.bytes_received,
        "tears": tears,
        "errors": errors,
        "emitted": sink.emitted,
        "versions": len({s.version for s in seen}),
    }


def _serve_until_mirrored(sink: Any, name: str, subscriber: Any) -> dict[str, Any]:
    """Pump both ends until this subscriber's mirror completes. ARRIVAL terminates.

    D3.39's repair, applied here rather than re-derived: `service()` returns the
    instant it answers ANY subscription, so a single call captures only whichever
    subscribe frames happened to be queued. The ceiling only bounds a bus that is
    broken rather than slow.
    """
    started = time.monotonic()
    deadline = started + RENDEZVOUS_CEILING_MS / 1000.0
    served = 0
    while True:
        served += sink.service(PUMP_SERVICE_MS)
        subscriber.drain(PUMP_DRAIN_MS)
        waited = time.monotonic() - started
        if subscriber.mirror.complete:
            return {"name": name, "served": served, "waited_s": waited, "ok": True}
        if time.monotonic() >= deadline:
            return {
                "name": name,
                "served": served,
                "waited_s": waited,
                "ok": False,
                "missing": list(subscriber.mirror.missing),
                "received": subscriber.received,
                "bytes": subscriber.bytes_received,
            }


def _late_subscribers(  # pylint: disable=too-many-locals
    picture_mod: Any, statebus: Any, seam: Any, root: Path
) -> dict[str, Any]:
    """§12.7 snapshot-on-subscribe, SEQUENTIALLY staged (D3.39's second finding)."""
    endpoint = _endpoint(statebus, root, "late")
    publisher = statebus.StatePublisher(endpoint)
    sink = picture_mod.StateBusPictureSink(publisher)
    book = picture_mod.FinancialPictureBook(
        balance=_BASE, deployable_fraction=_FRACTION, sink=sink
    )
    balance, rows = _world(seam, 7)
    book.commit(balance=balance, positions=rows)
    opened: list[Any] = []
    try:
        first = statebus.StateSubscriber(endpoint, [picture_mod.TOPIC])
        opened.append(first)
        first_rv = _serve_until_mirrored(sink, "first", first)
        # ONLY NOW does the second join: the topic is already subscribed AND
        # already answered, which is the exact state first-subscribe-only
        # delivery swallows.
        second = statebus.StateSubscriber(endpoint, [picture_mod.TOPIC])
        opened.append(second)
        second_rv = _serve_until_mirrored(sink, "second", second)
        mirrors = [
            picture_mod.PictureMirror(sub, max_age_s=FRESH_S) for sub in (first, second)
        ]
        return {
            "first": first_rv,
            "second": second_rv,
            "tradable": [mirror.tradable() for mirror in mirrors],
            "generations": [
                None if (p := mirror.picture()) is None else p.balance - _BASE
                for mirror in mirrors
            ],
            #: The SAME generation, recovered from `stop_distance` instead of
            #: from `balance`. A field that never crossed the wire, or crossed it
            #: defaulted, shows up here as generation 0 while `generations` still
            #: reads 7 — which is exactly D3.136's fail-open wearing a mirror.
            "stop_generations": [
                None
                if (p := mirror.picture()) is None
                else sorted({row.stop_distance - _STOP_BASE for row in p.positions})
                for mirror in mirrors
            ],
            "bytes": [sub.bytes_received for sub in opened],
        }
    finally:
        for sub in opened:
            sub.close()
        publisher.close()


def _strip_stops(body: dict[str, Any], *, schema: int | None) -> dict[str, Any]:
    """A copy of `body` with `stop_distance` GONE from every row.

    Not a version-2 body with its stamp edited — the rows really lose the key,
    which is the shape `WIRE_SCHEMA` 1 actually emitted. A "version-1 body" made
    by editing one integer would still carry the field, so a decoder that ignored
    the stamp entirely would pass. That is the manufactured input this probe
    exists not to take.
    """
    out = dict(body)
    out["positions"] = [
        {key: value for key, value in row.items() if key != "stop_distance"}
        for row in body["positions"]
    ]
    if schema is not None:
        out["schema"] = schema
    return out


def _refusal(picture_mod: Any, body: dict[str, Any]) -> str:
    """The message `decode_picture` refused with, or `""` if it ACCEPTED."""
    try:
        picture_mod.decode_picture(body)
    except picture_mod.PictureError as exc:
        return str(exc)
    return ""


def _codec_probe(picture_mod: Any, seam: Any) -> dict[str, Any]:
    """§12.7's codec, BOTH directions, over the wider row (D3.122's concrete half).

    `encode_picture` and `decode_picture` are the only thing standing between the
    Limiter's table and a consumer's mirror, so a field the seam carries and the
    codec drops is a field that does not exist anywhere it matters.
    """
    book = _new_book(picture_mod)
    balance, rows = _world(seam, 13)
    picture = book.commit(balance=balance, positions=rows)
    body = picture_mod.encode_picture(picture)
    # TOTAL, deliberately: a codec that refuses its OWN output is a finding for
    # `_arm_codec` to report, not an exception that turns the whole drive into
    # "could not be driven" and loses every other measurement in this run.
    back, error = None, ""
    try:
        back = picture_mod.decode_picture(body)
    except picture_mod.PictureError as exc:
        error = str(exc)
    return {
        "schema": body["schema"],
        "encoded_stops": [row["stop_distance"] for row in body["positions"]],
        "decoded_stops": (
            [] if back is None else [row.stop_distance for row in back.positions]
        ),
        "round_trip_equal": back == picture,
        "round_trip_error": error,
        # A TRUE version-1 body: rows without the key AND the old stamp.
        "v1_refusal": _refusal(picture_mod, _strip_stops(body, schema=1)),
        # THE CONTROL. The same stripped rows under the CURRENT stamp: the
        # refusal must move from the schema to the FIELD, which is what proves
        # the line above is the schema clause firing and not the key clause
        # wearing the schema's name.
        "stripped_refusal": _refusal(picture_mod, _strip_stops(body, schema=None)),
    }


def _stale_rule(
    picture_mod: Any, statebus: Any, seam: Any, root: Path
) -> dict[str, Any]:
    """§12.7's fast-drop verb: incomplete refuses, over-age refuses, fresh permits."""
    endpoint = _endpoint(statebus, root, "stale")
    publisher = statebus.StatePublisher(endpoint)
    sink = picture_mod.StateBusPictureSink(publisher)
    book = picture_mod.FinancialPictureBook(
        balance=_BASE, deployable_fraction=_FRACTION, sink=sink
    )
    subscriber = None
    try:
        subscriber = statebus.StateSubscriber(endpoint, [picture_mod.TOPIC])
        empty = picture_mod.PictureMirror(subscriber, max_age_s=FRESH_S).tradable()
        balance, rows = _world(seam, 11)
        book.commit(balance=balance, positions=rows)
        _serve_until_mirrored(sink, "stale-arm", subscriber)
        fresh = picture_mod.PictureMirror(subscriber, max_age_s=FRESH_S).tradable()
        aged = picture_mod.PictureMirror(
            subscriber, max_age_s=FRESH_S, clock=lambda: time.time() + STALE_AGE_S
        ).tradable()
        return {"empty": empty, "fresh": fresh, "aged": aged}
    finally:
        if subscriber is not None:
            subscriber.close()
        publisher.close()


# ---------------------------------------------------------------------------
# Arms — each appends `(site, why)` or a narration line, and returns None
# ---------------------------------------------------------------------------

_SITE_BOOK = "scripts/nixrisk/picture.py:FinancialPictureBook.commit"
_SITE_WIRE = "scripts/nixrisk/picture.py:encode_picture/decode_picture"
_SITE_SINK = "scripts/nixrisk/picture.py:StateBusPictureSink.service"
_SITE_MIRROR = "scripts/nixrisk/picture.py:PictureMirror.tradable"


def _arm_measured(races: dict[str, RaceResult], defects: list, ev: list) -> None:
    """The subject: the real book, under the race both plants tore under."""
    result = races["measured"]
    if result.crashed:
        defects.append((_SITE_BOOK, f"the writer thread died: {result.crashed}"))
        return
    if result.tears or result.coherence:
        defects.append(
            (
                _SITE_BOOK,
                f"{len(result.tears)} torn read(s) and {len(result.coherence)} "
                f"incoherent snapshot(s) over {result.reads} read(s): "
                + "; ".join((result.tears + result.coherence)[:2]),
            )
        )
        return
    weakest = min(races[key].tear_rate for key in PLANT_KEYS)
    stop_plant = races[STOP_PLANT_KEY]
    ev.append(
        result.summary()
        + f" — POWER: the weakest of the three plants tore at {weakest:.1%} of reads "
        f"under this same harness, so a clean sheet over {result.reads} read(s) is "
        "a measurement and not an absence; and the stop-book-join plant tore at "
        f"{stop_plant.stop_tear_rate:.1%} ON THE {_STOP_AXIS} over "
        f"{stop_plant.reads} read(s), so a publisher that JOINED the distance from "
        "a second table would be caught — which is exactly what this publisher's "
        "clean sheet on that axis is a measurement of, and no more"
    )


def _arm_plants(races: dict[str, RaceResult], defects: list, ev: list) -> None:
    """All three plants must TEAR. A detector that saw nothing measured nothing."""
    for key in PLANT_KEYS:
        result = races[key]
        if len(result.tears) < MIN_TEARS:
            defects.append(
                (
                    f"{_SITE_BOOK} [{result.label}]",
                    (
                        f"the PLANT produced {len(result.tears)} tear(s), below the "
                        f"floor of {MIN_TEARS}, over {result.reads} read(s) across "
                        f"{result.versions} version(s) — the detector was never shown "
                        "the failing case, so the measured arm's clean sheet is about "
                        "a harness with no power"
                    ),
                )
            )
            return
        ev.append(result.summary() + f" — first: {result.tears[0][:120]}")
    join = races[STOP_PLANT_KEY]
    if join.stop_tears < MIN_STOP_TEARS:
        defects.append(
            (
                f"{_SITE_BOOK} [{join.label}]",
                (
                    f"the stop-book-join PLANT produced {join.stop_tears} tear(s) on "
                    f"the {_STOP_AXIS}, below the floor of {MIN_STOP_TEARS}, over "
                    f"{join.reads} read(s) across {join.versions} version(s) and "
                    f"{len(join.tears)} tear(s) in total — so the harness has NO "
                    "POWER over stop_distance, and a re-proof that races the old "
                    "fields and ignores the new one proves the old row still works "
                    "and says NOTHING about the field this arc added. §6.4's "
                    "cross-table skew is the one thing this plant exists to show, "
                    "and it did not show it"
                ),
            )
        )


def _arm_bus(bus: dict[str, Any], defects: list, ev: list) -> None:
    """Every message a real SUB took off the wire, judged by both detectors."""
    if bus["errors"]:
        defects.append((_SITE_WIRE, f"undecodable message(s): {bus['errors'][0]}"))
        return
    if bus["tears"]:
        defects.append((_SITE_WIRE, f"torn snapshot on the wire: {bus['tears'][0]}"))
        return
    ev.append(
        f"bus: {bus['messages']} message(s) decoded across {bus['versions']} "
        f"version(s), {bus['bytes']} wire byte(s), {bus['emitted']} emitted, 0 torn"
    )


def _because(codec: dict[str, Any]) -> str:
    """The round-trip refusal, quoted, when there was one. §18: name the reason."""
    error = codec["round_trip_error"]
    return f" — the codec REFUSED its own output: {error}" if error else ""


def _arm_codec(codec: dict[str, Any], defects: list, ev: list) -> None:
    """The wire carries `stop_distance` both ways, or refuses and says WHICH."""
    expected = [_STOP_BASE + 13] * _ROWS
    if codec["encoded_stops"] != expected or codec["decoded_stops"] != expected:
        defects.append(
            (
                _SITE_WIRE,
                (
                    f"the codec carried stop_distance {codec['encoded_stops']} out "
                    f"and {codec['decoded_stops']} back, expected {expected} on "
                    "every row — a field the seam carries and the wire drops is a "
                    f"field the Allocator never sees{_because(codec)}"
                ),
            )
        )
        return
    if not codec["round_trip_equal"]:
        defects.append((_SITE_WIRE, "encode -> decode did not reproduce the picture"))
        return
    stripped = codec["stripped_refusal"]
    if "KeyError('stop_distance')" not in stripped:
        defects.append(
            (
                _SITE_WIRE,
                (
                    f"a row with NO stop_distance decoded with {stripped!r} rather "
                    "than being refused by name — a defaulted decode publishes a "
                    "held position priced at ZERO dollar risk, which makes the "
                    "bucket look emptier than it is and ADMITS more: D3.136's "
                    "fail-open reintroduced by the codec"
                ),
            )
        )
        return
    v1 = codec["v1_refusal"]
    if f"wire schema 1 is not {codec['schema']}" not in v1:
        defects.append(
            (
                _SITE_WIRE,
                (
                    f"a genuine WIRE_SCHEMA 1 body was refused with {v1!r}, which "
                    "does not name the SCHEMA. The stamp was bumped precisely so "
                    "the refusal says 'this consumer does not understand that "
                    "shape' — the thing a consumer can act on — instead of naming "
                    "one missing key, which reads as a corrupt message"
                ),
            )
        )
        return
    ev.append(
        f"codec: stop_distance round-tripped {expected} on {_ROWS} row(s) under "
        f"schema {codec['schema']}; a stripped row is REFUSED naming the field "
        f"({stripped[:60]}...); a genuine schema-1 body is refused naming the "
        "SCHEMA, not the key"
    )


def _arm_late(late: dict[str, Any], defects: list, ev: list) -> None:
    """§12.7 snapshot-on-subscribe: BOTH late subscribers mirror a whole picture."""
    for key in ("first", "second"):
        rendezvous = late[key]
        if not rendezvous["ok"]:
            defects.append(
                (
                    _SITE_SINK,
                    (
                        f"the {key} late subscriber went UNSERVED after "
                        f"{rendezvous['waited_s'] * 1000:.0f} ms: mirror still missing "
                        f"{rendezvous.get('missing')}, it took "
                        f"{rendezvous.get('received')} message(s) / "
                        f"{rendezvous.get('bytes')} wire byte(s). §12.7 makes "
                        "snapshot-on-subscribe mandatory, not polish"
                    ),
                )
            )
            return
    for index, (ok, why) in enumerate(late["tradable"]):
        if not ok:
            defects.append(
                (_SITE_MIRROR, f"late subscriber {index} mirrored but refuses: {why}")
            )
            return
    if set(late["generations"]) != {7.0}:
        defects.append(
            (
                _SITE_SINK,
                (
                    f"late subscribers mirrored generations {late['generations']}, "
                    "not the single generation 7 the publisher's table held — a "
                    "snapshot assembled from fragments"
                ),
            )
        )
        return
    if late["stop_generations"] != [[7], [7]]:
        defects.append(
            (
                _SITE_WIRE,
                (
                    f"the mirrored rows' stop_distance recovers generations "
                    f"{late['stop_generations']}, not [[7], [7]] — the field either "
                    "did not survive snapshot-on-subscribe or arrived DEFAULTED, "
                    "which is D3.136's fail-open (an unpriced position reads as "
                    "zero risk, the bucket looks emptier than it is, and an emptier "
                    "bucket ADMITS more) reintroduced on the wire"
                ),
            )
        )
        return
    ev.append(
        f"late subscribers served sequentially: "
        f"{late['first']['served']}+{late['second']['served']} snapshot(s), "
        f"{late['bytes']} wire byte(s), both mirroring generation 7 on balance AND "
        f"on stop_distance (rows carry {_STOP_BASE + 7} ticks)"
    )


def _arm_stale(stale: dict[str, Any], defects: list, ev: list) -> None:
    """Incomplete refuses, over-age refuses, fresh PERMITS. The control matters."""
    empty_ok, empty_why = stale["empty"]
    if empty_ok or "mirror incomplete" not in empty_why:
        defects.append(
            (
                _SITE_MIRROR,
                (
                    f"an EMPTY mirror answered {(empty_ok, empty_why)!r} — §12.7 says "
                    "mirror incomplete => stale => fast-drop/deny until the snapshot "
                    "lands, and a half-built mirror is never sized on"
                ),
            )
        )
        return
    aged_ok, aged_why = stale["aged"]
    if aged_ok or "stale" not in aged_why:
        defects.append(
            (_SITE_MIRROR, f"an OVER-AGE mirror answered {(aged_ok, aged_why)!r}")
        )
        return
    fresh_ok, fresh_why = stale["fresh"]
    if not fresh_ok:
        defects.append(
            (
                _SITE_MIRROR,
                (
                    f"the CONTROL failed: a complete, fresh mirror refused with "
                    f"{fresh_why!r}. Without this arm 'always refuses' would pass"
                ),
            )
        )
        return
    ev.append(f"stale rule: empty denies, aged denies, fresh permits ({fresh_why})")


# ---------------------------------------------------------------------------


def _remove_tree(root: Path) -> None:
    """Absolute-path unlinks, never `shutil.rmtree` — see the RESOURCES note."""
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


def _drive(picture_mod: Any, statebus: Any, seam: Any, root: Path) -> dict[str, Any]:
    """Every driver, once, at a HOSTILE thread-switch interval.

    `sys.setswitchinterval(SWITCH_INTERVAL_S)` shortens CPython's GIL slice for
    the duration of the drive. It makes the race HARDER, never easier: the reader
    and the writer interleave far more finely, so any window between two stores
    is far likelier to be caught. MEASURED — the two-read consumer plant at the
    5 ms default reached 2000 reads in 10.1s with 1952 tears; at 10 µs it reached
    the same 2000 reads in 0.24s with 2000 tears. The interval is restored in
    `finally`, because leaving a process-global tuned is how one gate makes
    another gate's timing its own business.
    """
    previous = sys.getswitchinterval()
    sys.setswitchinterval(SWITCH_INTERVAL_S)
    try:
        return {
            "races": run_races(picture_mod, seam),
            "codec": _codec_probe(picture_mod, seam),
            "bus": _bus_race(picture_mod, statebus, seam, root),
            "late": _late_subscribers(picture_mod, statebus, seam, root),
            "stale": _stale_rule(picture_mod, statebus, seam, root),
        }
    finally:
        sys.setswitchinterval(previous)


def _nonvacuity(observed: dict[str, Any], evidence: list[str]) -> CheckResult | None:
    """Every floor, checked BEFORE any arm contributes a verdict."""
    for result in observed["races"].values():
        if not result.raced:
            return _cannot(
                f"{result.label} reached only {result.reads} read(s) across "
                f"{result.versions} version(s), below the floors of {MIN_READS} "
                f"and {MIN_VERSIONS} — the reader did not demonstrably race the "
                "writer, and an atomicity verdict over a quiescent object is "
                "deliberately never PASS",
                evidence,
            )
    bus = observed["bus"]
    if bus["bytes"] == 0 or bus["messages"] < MIN_BUS_MESSAGES:
        return _cannot(
            f"the bus carried {bus['bytes']} byte(s) and {bus['messages']} "
            f"decodable message(s), below the floor of {MIN_BUS_MESSAGES} — a "
            "subscriber that received nothing cannot report that the picture is "
            "atomic on the wire. CANNOT_MEASURE, deliberately never PASS",
            evidence,
        )
    evidence.append(
        f"nonce {observed['nonce']}; races reached their floors; the bus carried "
        f"{bus['bytes']} real wire byte(s)"
    )
    return None


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Race the publisher, plant the tear, judge the subject. Never repairs."""
    evidence: list[str] = []
    picture_mod, statebus, complaint = _import_subjects()
    if complaint:
        return _cannot(complaint, evidence)
    try:
        from nixrisk import seam  # pylint: disable=import-outside-toplevel
    except ImportError as exc:  # pragma: no cover - picture.py imports seam already
        return _cannot(f"cannot import nixrisk.seam: {exc!r}", evidence)
    root = Path(tempfile.mkdtemp(prefix="nixpic-"))
    try:
        observed = _drive(picture_mod, statebus, seam, root)
        observed["nonce"] = f"ARC028S2-{secrets.token_hex(6)}"
    except Exception as exc:  # noqa: BLE001 pylint: disable=broad-except
        return _cannot(f"the picture could not be driven: {exc!r}", evidence)
    finally:
        _remove_tree(root)

    refusal = _nonvacuity(observed, evidence)
    if refusal is not None:
        return refusal

    defects: list[tuple[str, str]] = []
    _arm_plants(observed["races"], defects, evidence)
    _arm_measured(observed["races"], defects, evidence)
    _arm_codec(observed["codec"], defects, evidence)
    _arm_bus(observed["bus"], defects, evidence)
    _arm_late(observed["late"], defects, evidence)
    _arm_stale(observed["stale"], defects, evidence)
    return result_from_defects(NAME, defects, "; ".join(evidence))


# Deliberately duplicated across every checks/check_*.py: the check
# contract (§4.2) requires each module be independently runnable, so this
# block cannot be factored into a shared helper without breaking that.
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
