"""ARC 033 / Stage 1 / B — §7.5's contract roll, driven ACROSS the roll instant.

The can-fail suite for `scripts/nixrisk/roll.py`. Every `§` cites
`docs/nics_risk_subsystem_spec_v1.3.md` unless another document is named.

THE HAZARDS THIS BRIEF NAMES, TREATED AS HYPOTHESES AND MEASURED:

* **A roll test where identity never actually shifts proves nothing.** Every
  atomicity control resolves an epoch strictly BEFORE the roll instant and
  strictly AFTER it and asserts the two contracts DIFFER before any atomicity
  assertion runs. `test_the_IDENTITY_REALLY_SHIFTS_...` is the standalone
  statement of that floor.
* **A race that never races proves nothing.** The harness runs a writer thread
  flipping the epoch across the roll against N reader threads, and asserts the
  readers observed BOTH contracts — the window really was crossed under
  contention — before asserting no reader observed a MIXED snapshot.
* **An atomicity claim with no torn counterpart is guaranteed by construction,
  not measured.** `_TornBook` switches the subsystems in TWO steps, exactly the
  shape a reasonable implementation reaches for, and is required to TEAR under
  the same harness the real book survives. A falsifier that stops falsifying is
  reported as a broken instrument.
* **The roll schedule is PROVISIONAL** (CHECK-DEBT D3.170): every row in
  `nix_roll_schedule.csv` is rule-derived and stamped `high_risk=1`, and §7.5:520
  defines front month as the VOLUME LEADER, which no offline artifact observes.
  The provenance is asserted to reach the consumer, and the plant that drops it
  is required to be detectable.

`debug.md` §7.12 is answered per control in its docstring.
"""
# pylint: disable=invalid-name,redefined-outer-name,protected-access
# pylint: disable=missing-function-docstring,too-few-public-methods
# pylint: disable=duplicate-code,wrong-import-position
# invalid-name: the test names are sentences. protected-access: the plant reaches
# the book's single mutable attribute to build a WRONG variant — that is how a
# falsifier is written.

from __future__ import annotations

import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from crucible import calendar as cal  # pylint: disable=wrong-import-position
from nixrisk.calendar_seam import CacheState, ContractIdentity
from nixrisk.roll import (
    SYMBOL_KEYED_SUBSYSTEMS,
    IdentityEpoch,
    NoFrontContract,
    RollError,
    RollIdentityBook,
    TornIdentity,
    VendoredRollSchedule,
)

SPEC = REPO / "docs" / "nics_risk_subsystem_spec_v1.3.md"

#: The ES roll the vendored artifact declares, read from it rather than typed.
#: A literal here would be a second copy of the schedule that could disagree.
_PROBE = datetime(2026, 8, 15, tzinfo=UTC)

#: How many torn snapshots a reader keeps. See `_race`.
_TORN_SAMPLE_CAP = 25


@pytest.fixture(scope="module")
def roll_instant() -> datetime:
    """ES's next roll instant, off the vendored artifact."""
    instant = cal.next_roll("ES", _PROBE)
    assert instant is not None, (
        "the vendored schedule covers no ES roll after the probe"
    )
    return instant


# ==========================================================================
# Doubles — a schedule the harness can drive without touching the artifact
# ==========================================================================


class DrivenSchedule:
    """A `RollScheduleReadPort` over two contracts and one roll instant.

    Not a stub with a constant answer: the whole subject is that the answer
    CHANGES at a defined instant, and a constant schedule could not express a
    roll at all.
    """

    def __init__(self, roll_at: datetime, symbols: tuple[str, ...] = ("ES", "NQ")):
        self.roll_at = roll_at
        self.symbols = symbols

    def front_contract(self, symbol: str, at: datetime) -> ContractIdentity | None:
        if symbol not in self.symbols:
            return None
        old = at < self.roll_at
        return ContractIdentity(
            symbol=symbol,
            contract=f"{symbol}{'U26' if old else 'Z26'}",
            front_from=self.roll_at - timedelta(days=90) if old else self.roll_at,
            roll_at=self.roll_at if old else self.roll_at + timedelta(days=90),
        )

    def next_roll(self, symbol: str, at: datetime) -> datetime | None:
        del symbol
        return self.roll_at if at <= self.roll_at else None

    def state(self):

        return CacheState.FRESH


class _TornBook(RollIdentityBook):
    """THE PLANT. Switches the subsystems in TWO steps instead of one store.

    This is the shape a reasonable implementation reaches for — a per-subsystem
    map filled in a loop — and it is the §12.7 torn read one layer up: a reader
    arriving between the two steps sees `capture` on the new contract and
    `positions` on the old. The plant lives in the SUBJECT (doctrine C.8): it is
    a subclass of the real book, overriding only the switch and the read.

    **IT YIELDS MID-SWITCH, AND THAT IS NOT THE DEFECT — IT IS THE MICROSCOPE.**
    The defect is that a partially-applied state EXISTS at all; `time.sleep(0)`
    only decides how often a reader lands in it, turning a flaky race into a
    deterministic one. The real book cannot be given the same yield, because
    there is no point inside `advance` at which a partial state is bound to the
    attribute a reader loads — which is the whole claim, stated as the reason
    the two harness runs are not symmetrical.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._torn: dict[tuple[str, str], str] = {}

    def advance(self, at: datetime) -> IdentityEpoch:
        epoch = super().advance(at)
        # THE DEFECT: per-(subsystem, symbol) writes, visible half-applied.
        for subsystem in SYMBOL_KEYED_SUBSYSTEMS:
            for symbol, identity in epoch.identities.items():
                self._torn[(subsystem, symbol)] = identity.contract
            time.sleep(0)  # a scheduling point INSIDE the switch
        return epoch

    def snapshot(self):  # type: ignore[override]
        # THE DEFECT: N loads instead of one. Each key is read independently.
        return dict(self._torn.items())


# ==========================================================================
# NON-VACUITY FIRST — the identity really shifts, over the REAL artifact
# ==========================================================================


def test_the_IDENTITY_REALLY_SHIFTS_across_the_ROLL_INSTANT(
    roll_instant: datetime,
) -> None:
    """THE FLOOR. Every atomicity claim below is meaningless without this.

    `debug.md` §7.12: a roll suite passes while measuring nothing if it only
    ever samples one side of the roll — every snapshot is then trivially
    self-consistent. Driven over the REAL vendored artifact, one second either
    side of the instant it declares.
    """
    schedule = VendoredRollSchedule()
    book = RollIdentityBook(schedule=schedule, symbols=("ES", "NQ"))

    before = book.advance(roll_instant - timedelta(seconds=1))
    before_es = before.contract_for("positions", "ES")

    after = book.advance(roll_instant + timedelta(seconds=1))
    after_es = after.contract_for("positions", "ES")

    assert before_es != after_es, (
        f"the identity did not move across {roll_instant.isoformat()} "
        f"({before_es!r} both sides) — nothing about a roll was measured"
    )
    assert after.version == before.version + 1


def test_the_ROLL_INSTANT_is_the_EXACT_BOUNDARY_half_open(
    roll_instant: datetime,
) -> None:
    """AT the instant is the NEW contract; one microsecond before is the old.

    §7.5:522's *defined roll instant* has to be a point, not a fuzzy band, or
    the Renko seam §7.5:525-526 defines has no location.
    """
    book = RollIdentityBook(schedule=VendoredRollSchedule(), symbols=("ES",))

    just_before = book.advance(roll_instant - timedelta(microseconds=1)).contract_for(
        "capture", "ES"
    )
    exactly_at = book.advance(roll_instant).contract_for("capture", "ES")

    assert just_before != exactly_at, (just_before, exactly_at)


def test_the_SUBSYSTEM_SET_is_SECTION_7_5_s_OWN_LIST_and_is_NOT_EMPTY() -> None:
    """`debug.md` §7.12 answer 4: a snapshot over zero subsystems cannot tear.

    The list is parsed from the frozen spec sentence, so a member invented here
    or dropped from there reddens this — the same discipline `test_flatten.py`
    applies to the trigger vocabulary.
    """
    text = " ".join(SPEC.read_text(encoding="utf-8").split())
    named = text.split("all symbol-keyed subsystems (", 1)[1].split(")", 1)[0]
    spec_set = {
        part.strip().replace(" ", "_").lower()
        for part in named.split(",")
        if part.strip()
    }

    assert spec_set == set(SYMBOL_KEYED_SUBSYSTEMS), spec_set.symmetric_difference(
        SYMBOL_KEYED_SUBSYSTEMS
    )
    assert len(SYMBOL_KEYED_SUBSYSTEMS) == 6


# ==========================================================================
# THE ATOMIC SWITCH — proven under a real race, with the torn plant beside it
# ==========================================================================


def _race(book, roll_at: datetime, *, readers: int = 3, flips: int = 60):
    """Hammer `snapshot()` from N threads while a writer flips across the roll.

    Returns `(torn, contracts_seen, samples)`. `torn` holds every snapshot in
    which two `(subsystem, symbol)` pairs for the SAME symbol disagreed.

    The writer yields (`time.sleep(0)`) between flips so the readers really run
    while the epoch is moving. Without it CPython's GIL lets the writer finish
    all 300 flips inside one switch interval and the readers only ever observe
    one side — measured, and the reason the `contracts_seen` assertion exists in
    every caller: a harness that did not cross the roll under contention is
    reported rather than passed.
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
            except NoFrontContract:
                continue
            count += 1
            per_symbol: dict[str, set[str]] = {}
            for (_subsystem, symbol), contract in snap.items():
                per_symbol.setdefault(symbol, set()).add(contract)
                local_seen.add(contract)
            if any(len(values) > 1 for values in per_symbol.values()) and (
                len(local_torn) < _TORN_SAMPLE_CAP
            ):
                # Capped: the fact to establish is that a tear IS observable,
                # and an unbounded list of thousands of identical tears costs
                # seconds of wall clock to prove the same thing once.
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


def test_the_REAL_BOOK_NEVER_TEARS_under_a_RACE_that_really_CROSSES_the_roll(
    roll_instant: datetime,
) -> None:
    """§7.5:522's *atomically at a defined roll instant*, MEASURED.

    `debug.md` §7.12: this passes while measuring nothing if (a) the readers
    never sampled, (b) the writer never crossed the roll, or (c) the subsystem
    set were empty. All three are asserted BEFORE the no-tear assertion, so a
    green here cannot be a green over an idle harness.
    """
    schedule = DrivenSchedule(roll_instant)
    book = RollIdentityBook(schedule=schedule, symbols=("ES", "NQ"))
    book.advance(roll_instant - timedelta(seconds=1))

    torn, seen, samples = _race(book, roll_instant)

    assert samples > 100, f"the readers barely sampled ({samples}) — no race happened"
    assert {"ESU26", "ESZ26"} <= seen, (
        f"the writer never crossed the roll under contention; seen={sorted(seen)}"
    )
    assert len(book.snapshot()) == len(SYMBOL_KEYED_SUBSYSTEMS) * 2
    assert not torn, f"{len(torn)} torn snapshot(s); first={torn[0] if torn else None}"


def test_the_TORN_PLANT_REALLY_TEARS_under_the_SAME_harness(
    roll_instant: datetime,
) -> None:
    """The falsifier must LOSE the property, or the control above measures nothing.

    `_TornBook` writes one `(subsystem, symbol)` key at a time and reads them
    back independently — a two-step switch. If this ever stops tearing, the
    no-tear assertion above is not a discriminator and THIS control says so.
    """
    schedule = DrivenSchedule(roll_instant)
    plant = _TornBook(schedule=schedule, symbols=("ES", "NQ"))
    plant.advance(roll_instant - timedelta(seconds=1))

    torn, seen, samples = _race(plant, roll_instant)

    assert samples > 100, samples
    assert {"ESU26", "ESZ26"} <= seen, sorted(seen)
    assert torn, (
        "the two-step plant produced NO torn snapshot — it no longer falsifies, "
        "so the real book's clean run proves nothing about atomicity"
    )
    mixed = torn[0]
    per_symbol: dict[str, set[str]] = {}
    for (_subsystem, symbol), contract in mixed.items():
        per_symbol.setdefault(symbol, set()).add(contract)
    assert any(len(values) > 1 for values in per_symbol.values()), per_symbol


def test_EVERY_SUBSYSTEM_reads_ONE_IDENTITY_because_there_IS_only_one(
    roll_instant: datetime,
) -> None:
    """The atomicity is the TYPE's, not a discipline the writer keeps.

    An `IdentityEpoch` holds one identity per SYMBOL; a per-subsystem identity
    map is not representable by it at all. Asserted by reading every subsystem
    off one epoch and requiring one distinct answer per symbol.
    """
    book = RollIdentityBook(schedule=DrivenSchedule(roll_instant), symbols=("ES", "NQ"))
    epoch = book.advance(roll_instant)

    answers = {
        symbol: {epoch.contract_for(sub, symbol) for sub in SYMBOL_KEYED_SUBSYSTEMS}
        for symbol in ("ES", "NQ")
    }

    assert answers == {"ES": {"ESZ26"}, "NQ": {"NQZ26"}}, answers


def test_an_EPOCH_WHOSE_MAP_AND_VALUE_DISAGREE_is_REFUSED_at_CONSTRUCTION() -> None:
    """A torn identity cannot be built, let alone observed (directive 4)."""
    identity = ContractIdentity(
        symbol="NQ",
        contract="NQZ26",
        front_from=datetime(2026, 9, 14, tzinfo=UTC),
        roll_at=datetime(2026, 12, 18, tzinfo=UTC),
    )

    with pytest.raises(TornIdentity) as caught:
        IdentityEpoch(
            resolved_for=datetime(2026, 9, 15, tzinfo=UTC),
            version=1,
            identities={"ES": identity},
            provisional=frozenset(),
        )

    assert "torn identity" in str(caught.value), caught.value
    assert "'ES'" in str(caught.value) and "'NQ'" in str(caught.value), caught.value


def test_an_EPOCH_over_ZERO_SUBSYSTEMS_is_REFUSED() -> None:
    """`debug.md` §7.12 answer 4: self-consistent for free is not a proof."""
    with pytest.raises(TornIdentity) as caught:
        IdentityEpoch(
            resolved_for=datetime(2026, 9, 15, tzinfo=UTC),
            version=1,
            identities={},
            provisional=frozenset(),
            subsystems=(),
        )

    assert "ZERO symbol-keyed subsystems" in str(caught.value), caught.value


def test_a_BOOK_over_ZERO_SYMBOLS_or_ZERO_SUBSYSTEMS_is_REFUSED() -> None:
    """The vacuous configurations are refused where they are configured."""
    schedule = DrivenSchedule(datetime(2026, 9, 14, 21, 0, tzinfo=UTC))

    with pytest.raises(RollError) as no_symbols:
        RollIdentityBook(schedule=schedule, symbols=())
    assert "ZERO symbols" in str(no_symbols.value)

    with pytest.raises(RollError) as no_subsystems:
        RollIdentityBook(schedule=schedule, symbols=("ES",), subsystems=())
    assert "cannot tear" in str(no_subsystems.value)


def test_READING_BEFORE_THE_FIRST_ADVANCE_is_a_LOUD_REFUSAL_not_a_LAZY_RESOLVE() -> (
    None
):
    """A lazy first read would let the first caller's instant decide for everyone."""
    book = RollIdentityBook(
        schedule=DrivenSchedule(datetime(2026, 9, 14, 21, 0, tzinfo=UTC)),
        symbols=("ES",),
    )

    with pytest.raises(NoFrontContract) as caught:
        book.snapshot()

    assert "has no epoch" in str(caught.value), caught.value


def test_an_UNCOVERED_INSTANT_is_REFUSED_never_GUESSED() -> None:
    """§7.5:525-526 — a guessed identity is the phantom stitch across contracts."""
    book = RollIdentityBook(schedule=VendoredRollSchedule(), symbols=("ES",))

    with pytest.raises(NoFrontContract) as caught:
        book.advance(datetime(1999, 1, 1, tzinfo=UTC))

    assert "ES" in str(caught.value), caught.value
    assert "never guessed" in str(caught.value), caught.value


def test_an_UNLISTED_SUBSYSTEM_is_REFUSED_rather_than_QUIETLY_ANSWERED(
    roll_instant: datetime,
) -> None:
    """A subsystem no roll was arranged for must not be handed a front month."""
    book = RollIdentityBook(schedule=DrivenSchedule(roll_instant), symbols=("ES",))
    book.advance(roll_instant)

    with pytest.raises(NoFrontContract) as caught:
        book.contract_for("dashboard", "ES")

    assert "dashboard" in str(caught.value), caught.value
    assert "§7.5:521" in str(caught.value), caught.value


# ==========================================================================
# D3.170 — THE SCHEDULE IS PROVISIONAL, AND THE PROVENANCE REACHES THE READER
# ==========================================================================


def test_the_VENDORED_SCHEDULE_really_IS_all_HIGH_RISK_rule_derived() -> None:
    """CHECK-DEBT D3.170, observed POSITIVELY on the shipped artifact.

    `debug.md` §7.12: asserting "the provisional flag is set" measures nothing if
    the artifact were in fact corroborated — the flag would just be wrong. So
    the artifact's OWN `high_risk` column is read first, and the flag is then
    required to agree with it.
    """
    rows = list(cal._load_rolls().items())

    assert rows, "the vendored roll schedule is empty"
    for symbol, symbol_rows in rows:
        assert symbol_rows, symbol
        assert all(row.high_risk for row in symbol_rows), (
            f"{symbol}: some rows are NOT high_risk — D3.170 says every roll date "
            "in this artifact is rule-derived, and this control is now stale"
        )


def test_the_PROVISIONAL_PROVENANCE_REACHES_the_EPOCH_the_consumer_holds() -> None:
    """§7.5:520 defines front month as the VOLUME LEADER — an observation.

    The vendored artifact observes nothing; it applies a rule. A consumer keying
    capture, backfill and the position table on that date must be able to learn
    so, and `IdentityEpoch.provisional` is where it learns it.
    """
    schedule = VendoredRollSchedule()
    provisional = schedule.provisional_symbols(_PROBE)
    assert {"ES", "NQ"} <= provisional, sorted(provisional)

    book = RollIdentityBook(
        schedule=schedule, symbols=("ES", "NQ"), provisional_symbols=provisional
    )
    book.advance(_PROBE)

    assert book.provisional_symbols() == frozenset({"ES", "NQ"})
    assert book.epoch().provisional == frozenset({"ES", "NQ"})


def test_a_LAUNDERED_PROVENANCE_is_DETECTABLE_the_flag_is_not_DECORATION() -> None:
    """THE PLANT for D3.170: an adapter that DROPS `high_risk`.

    A provenance flag nothing reads is decoration. This builds the same book
    from a schedule whose provisional set is empty — the laundering — and shows
    the epoch then claims a clean provenance it does not have, which is exactly
    the state the gate reddens on.
    """
    schedule = VendoredRollSchedule()
    honest = RollIdentityBook(
        schedule=schedule,
        symbols=("ES",),
        provisional_symbols=schedule.provisional_symbols(_PROBE),
    )
    laundered = RollIdentityBook(
        schedule=schedule, symbols=("ES",), provisional_symbols=()
    )

    honest.advance(_PROBE)
    laundered.advance(_PROBE)

    assert honest.provisional_symbols() == frozenset({"ES"})
    assert laundered.provisional_symbols() == frozenset(), (
        "the laundering plant no longer launders — it reports the provenance it "
        "was never given, so this control is not a discriminator"
    )
    # The two agree on the CONTRACT and disagree only on its provenance, which is
    # what makes laundering invisible to any check that only reads the identity.
    assert honest.contract_for("capture", "ES") == laundered.contract_for(
        "capture", "ES"
    )


def test_this_MODULE_MINTS_NO_WINDOW_the_roll_blackout_stays_DATA() -> None:
    """§7.5:523 / §6.5 — *a window, data, not code*.

    Asserted on the module's own source: a `Window(` construction here would put
    a blackout rule in a second place, beside the window evaluator that owns it.
    The instant is what this module owes; the window is somebody else's row.
    """
    source = (REPO / "scripts" / "nixrisk" / "roll.py").read_text(encoding="utf-8")
    code = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )

    assert "Window(" not in code, "roll.py constructs a Window — §7.5:523 says data"
    assert "WindowKind" not in code, "roll.py branches on a window kind"

    book = RollIdentityBook(schedule=VendoredRollSchedule(), symbols=("ES",))
    instant = book.next_roll_instant("ES", _PROBE)
    assert isinstance(instant, datetime) and instant.tzinfo is not None
