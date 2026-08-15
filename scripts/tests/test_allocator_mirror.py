"""ARC 031 / Stage 1 A — behaviour of `scripts/nixalloc/mirror.py`, A1 through A4.

Every test here is a HYPOTHESIS DRIVEN, never a property believed. The four
mandated properties and the exact reason each test could have failed:

* **A1 — atomicity is unfalsifiable without concurrency.** A test that publishes
  one snapshot and reads it back cannot tell a mirror that swaps one pointer
  from one that assigns nine fields in a loop. So a READER THREAD is raced
  against a mid-publish WRITER, every published number is linked to ONE
  generation, and the same harness is driven against `_TornMirror` — a
  deliberately non-atomic implementation — which it is REQUIRED to catch.
* **A2 — a half-built mirror is STALE (§12.7, §0i).** A healthy-feed test proves
  nothing. A PARTIAL and an UNSTAMPED reading are delivered and the refusal is
  required, with its reason. EMPTY, PARTIAL, FRESH-while-quiet and STALE are
  required to be four DISTINCT observations out of one object — ARC 027's
  `XPUB_VERBOSE` hazard is that a missed snapshot and a quiet healthy feed look
  identical.
* **A3 — monotonic-by-source, PER KEY (§6.4b).** In-order readings prove
  nothing. An OLDER reading is delivered and required to be DISCARDED, and a
  late update on ES is required not to regress ES while leaving NQ alone.
* **A4 — read-only proven by ATTEMPT (§2).** "Absent from the code" is the
  vacuous version. Mutations are ATTEMPTED and the raised exception is the
  evidence; the same attempt harness is shown to SUCCEED against a writable
  stand-in.

`test_the_REAL_zeromq_ipc_path_*` are the transport half: §12.7 LOCKS ZeroMQ
PUB/SUB + snapshot-on-subscribe, and a mirror proven only against an injected
fake has been proven against the fake.
"""
# pylint: disable=invalid-name,redefined-outer-name,protected-access
# pylint: disable=missing-function-docstring,missing-class-docstring
# pylint: disable=too-few-public-methods,too-many-instance-attributes
# The feeds and falsifiers below are one-verb stand-ins whose NAME states the
# property they exist to have or to lose; `TornMirror` holds nine slots BY
# CONSTRUCTION, because the nine-slot store IS the defect it demonstrates.

from __future__ import annotations

import dataclasses
import operator
import threading
import time
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

import pytest  # pylint: disable=import-error
from nixalloc.mirror import (
    AllocatorMirror,
    MirrorUpdate,
    MirrorUsageError,
    SnapshotFeedPort,
    StateBusFeed,
)
from nixalloc.seam import (
    FinancialPicture,
    MirrorPort,
    MirrorState,
    PositionRow,
    PositionState,
)
from nixbus import statebus
from nixrisk.picture import TOPIC, encode_picture

RACE_GENERATIONS = 3000
FALSIFIER_GENERATIONS = 60
MIN_OBSERVATIONS = 200


# --------------------------------------------------------------------------
# The generation link — what makes a torn read arithmetically VISIBLE
# --------------------------------------------------------------------------


def expected(generation: int) -> dict[str, float]:
    """Every published number as a function of ONE generation."""
    balance = 100_000.0 * generation
    open_margin = 1_000.0 * generation
    reservations = 500.0 * generation
    committed = open_margin + reservations
    return {
        "balance": balance,
        "row_margin": open_margin,
        "margin_es": 10.0 * generation,
        "margin_nq": 20.0 * generation,
        "sum_open_margin": open_margin,
        "sum_reservations": reservations,
        "committed": committed,
        "deployable": max(0.0, 0.70 * balance - committed),
    }


def linked(generation: int, published_ts: float = 1_000.0) -> FinancialPicture:
    """One self-consistent picture at `generation`."""
    want = expected(generation)
    row = PositionRow(
        trade_id="T-1",
        symbol="ES",
        strategy_id="strat-1",
        size=generation,
        margin=want["row_margin"],
        state=PositionState.OPEN,
    )
    return FinancialPicture(
        version=generation,
        published_ts=published_ts,
        balance=want["balance"],
        positions=(row,),
        margin_per_contract=MappingProxyType(
            {"ES": want["margin_es"], "NQ": want["margin_nq"]}
        ),
        sum_open_margin=want["sum_open_margin"],
        sum_reservations=want["sum_reservations"],
        committed=want["committed"],
        deployable=want["deployable"],
    )


def inconsistency(picture: Any) -> str:
    """`""` when every field of this ONE picture came from one generation."""
    generation = getattr(picture, "version", 0)
    want = expected(generation)
    diffs: list[str] = []
    rows: tuple[Any, ...] = getattr(picture, "positions", ())
    if len(rows) != 1:
        diffs.append(f"position table has {len(rows)} row(s), expected 1")
    elif rows[0].margin != want["row_margin"]:
        diffs.append(f"row margin={rows[0].margin!r}, want {want['row_margin']!r}")
    margins = getattr(picture, "margin_per_contract", {})
    for symbol, key in (("ES", "margin_es"), ("NQ", "margin_nq")):
        if margins.get(symbol) != want[key]:
            diffs.append(
                f"margin[{symbol}]={margins.get(symbol)!r}, want {want[key]!r}"
            )
    for field in ("balance", "sum_open_margin", "sum_reservations", "committed"):
        if getattr(picture, field, None) != want[field]:
            diffs.append(f"{field}={getattr(picture, field, None)!r}")
    return f"version {generation}: " + "; ".join(diffs) if diffs else ""


class GenerationFeed:
    """Hands out generation `n` on the nth read. The mid-publish writer's source."""

    def __init__(self, published_ts: float) -> None:
        self._ts = published_ts
        self.generation = 0

    def read(self, timeout_ms: int) -> MirrorUpdate:
        del timeout_ms
        self.generation += 1
        return MirrorUpdate(
            picture=linked(self.generation, self._ts),
            heard=True,
            complete=True,
            source_stamps={"balance": float(self.generation)},
        )


class ScriptedFeed:
    """Returns each scripted update in turn, then repeats the last one forever."""

    def __init__(self, updates: list[MirrorUpdate]) -> None:
        self._updates = updates
        self.reads = 0

    def read(self, timeout_ms: int) -> MirrorUpdate:
        del timeout_ms
        index = min(self.reads, len(self._updates) - 1)
        self.reads += 1
        return self._updates[index]


class TornMirror:
    """FALSIFIER: nine fields in nine slots, with a real window between them."""

    def __init__(self) -> None:
        self.generation = 0
        self._v = 0
        self._balance = 0.0
        self._rows: tuple[Any, ...] = ()
        self._margins: Any = MappingProxyType({})
        self._open = 0.0
        self._reserved = 0.0
        self._committed = 0.0
        self._deployable = 0.0

    def refresh(self, timeout_ms: int = 0) -> Any:
        del timeout_ms
        self.generation += 1
        source = linked(self.generation)
        self._v = source.version
        self._balance = source.balance
        time.sleep(0.0005)  # the window a single pointer swap does not have
        self._rows = source.positions
        self._margins = source.margin_per_contract
        self._open = source.sum_open_margin
        self._reserved = source.sum_reservations
        self._committed = source.committed
        self._deployable = source.deployable
        return self.snapshot()

    def snapshot(self) -> Any:
        from nixalloc.seam import (  # pylint: disable=import-outside-toplevel
            MirrorSnapshot,
        )

        return MirrorSnapshot(
            state=MirrorState.FRESH,
            picture=FinancialPicture(
                version=self._v,
                published_ts=0.0,
                balance=self._balance,
                positions=self._rows,
                margin_per_contract=self._margins,
                sum_open_margin=self._open,
                sum_reservations=self._reserved,
                committed=self._committed,
                deployable=self._deployable,
            ),
            reason="falsifier",
        )


def race(mirror: Any, generations: int) -> tuple[list[int], list[str]]:
    """Race a reader thread against a mid-publish writer. `(seen, torn)`."""
    seen: list[int] = []
    torn: list[str] = []
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            snap = mirror.snapshot()
            picture = snap.picture
            if picture is None or picture.version < 1:
                continue
            seen.append(picture.version)
            why = inconsistency(picture)
            if why:
                torn.append(why)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        for _ in range(generations):
            mirror.refresh(0)
    finally:
        stop.set()
        thread.join(timeout=5.0)
    return seen, torn


# --------------------------------------------------------------------------
# A1 — ATOMICITY UNDER A REAL RACE
# --------------------------------------------------------------------------


def test_A1_a_reader_racing_a_writer_NEVER_sees_a_half_applied_snapshot() -> None:
    """§3's ATOMICITY RULE, measured the only way it can be: concurrently."""
    mirror = AllocatorMirror(GenerationFeed(time.time()), max_age_s=600.0)
    seen, torn = race(mirror, RACE_GENERATIONS)
    assert not torn, f"{len(torn)} torn observation(s); first: {torn[0]}"
    assert len(seen) >= MIN_OBSERVATIONS, (
        f"the reader made only {len(seen)} observations — a race nobody watched "
        "proves nothing about atomicity"
    )
    assert mirror.applied == RACE_GENERATIONS, mirror.applied


def test_A1_the_SAME_harness_catches_a_deliberately_non_atomic_mirror() -> None:
    """The falsifier. Without this, the test above is a green over nothing."""
    _seen, torn = race(TornMirror(), FALSIFIER_GENERATIONS)
    assert torn, (
        "the harness raced a mirror that assigns nine fields in sequence with a "
        "500us window and detected NO tear — it cannot catch a broken "
        "implementation, so its clean result is worthless"
    )


def test_A1_a_snapshot_and_its_version_come_from_ONE_cell() -> None:
    """`version()` and `snapshot()` are two reads of the same single store."""
    mirror = AllocatorMirror(GenerationFeed(time.time()), max_age_s=600.0)
    mirror.refresh()
    snap = mirror.snapshot()
    assert snap.picture is not None
    assert mirror.version() == snap.picture.version
    assert mirror.version() == 1


def test_A1_an_untouched_mirror_reports_a_NEGATIVE_version() -> None:
    """Zero is a plausible first version; the seam requires a negative sentinel."""
    mirror = AllocatorMirror(ScriptedFeed([MirrorUpdate()]), max_age_s=1.0)
    assert mirror.version() < 0


# --------------------------------------------------------------------------
# A2 — A HALF-BUILT MIRROR IS STALE (§12.7, §0i)
# --------------------------------------------------------------------------


@pytest.fixture
def clocked() -> tuple[AllocatorMirror, list[float], ScriptedFeed]:
    """A mirror on a settable clock, fed a scripted EMPTY -> ... -> quiet sequence."""
    now = 1_000.0
    clock = [now]
    unstamped = dataclasses.replace(linked(1, now), version=0)
    feed = ScriptedFeed(
        [
            MirrorUpdate(heard=False, note="nothing has ever arrived"),
            MirrorUpdate(
                heard=True, complete=False, note="no snapshot yet for ('tbl.x',)"
            ),
            MirrorUpdate(picture=unstamped, heard=True, complete=True),
            MirrorUpdate(picture=linked(7, now), heard=True, complete=True),
            MirrorUpdate(heard=True, complete=False, note="publisher is quiet"),
        ]
    )
    return AllocatorMirror(feed, max_age_s=2.0, clock=lambda: clock[0]), clock, feed


def test_A2_the_four_states_are_FOUR_distinct_observations(
    clocked: tuple[AllocatorMirror, list[float], ScriptedFeed],
) -> None:
    """§12.7's hazard is that a missed snapshot looks like a quiet healthy feed."""
    mirror, clock, _feed = clocked

    assert mirror.snapshot().reason == "no snapshot has been received"
    empty = mirror.refresh()
    assert empty.state is MirrorState.EMPTY
    assert empty.sizeable is False
    assert "nothing has ever arrived" in empty.reason

    partial = mirror.refresh()
    assert partial.state is MirrorState.PARTIAL, partial
    assert partial.sizeable is False
    assert "no snapshot yet" in partial.reason

    # THE DISTINCTION THAT MATTERS: never-heard and heard-but-incomplete are not
    # the same fact, and a two-valued mirror cannot tell an operator which.
    assert empty.state is not partial.state

    unstamped = mirror.refresh()
    assert unstamped.state is MirrorState.PARTIAL
    assert unstamped.sizeable is False
    assert "UNSTAMPED" in unstamped.reason

    fresh = mirror.refresh()
    assert fresh.state is MirrorState.FRESH
    assert fresh.sizeable is True

    clock[0] = 1_000.5
    quiet = mirror.refresh()
    assert quiet.state is MirrorState.FRESH, "quiet-and-current is not stale"
    assert quiet.sizeable is True

    clock[0] = 1_030.0
    stale = mirror.snapshot()
    assert stale.state is MirrorState.STALE
    assert stale.sizeable is False
    assert "ceiling" in stale.reason


def test_A2_a_falsifier_that_forgets_HEARD_collapses_PARTIAL_into_EMPTY(
    clocked: tuple[AllocatorMirror, list[float], ScriptedFeed],
) -> None:
    """Proves the EMPTY/PARTIAL assertion above is not satisfied by any mirror."""
    _mirror, _clock, _feed = clocked

    class HeardBlind(AllocatorMirror):
        def _absent(self, update: MirrorUpdate) -> None:
            self._refuse(update.note, heard=False)  # WRONG: drops `heard`

    blind = HeardBlind(
        ScriptedFeed(
            [
                MirrorUpdate(heard=False, note="nothing"),
                MirrorUpdate(heard=True, complete=False, note="no snapshot yet"),
            ]
        ),
        max_age_s=2.0,
    )
    blind.refresh()
    assert blind.refresh().state is MirrorState.EMPTY, (
        "the heard-blind falsifier reported PARTIAL anyway — it no longer "
        "falsifies, so the distinction above is untested"
    )


def test_A2_a_falsifier_that_drops_the_half_built_rule_holds_an_UNSTAMPED_picture() -> (
    None
):
    """§12.7's *never sizes on a half-built mirror*, shown to be load-bearing."""

    class Lax(AllocatorMirror):
        def _incoherent(self, picture: FinancialPicture) -> str:
            del picture
            return ""  # WRONG: the half-built rule deleted

    unstamped = dataclasses.replace(linked(1, 1_000.0), version=0)
    lax = Lax(
        ScriptedFeed([MirrorUpdate(picture=unstamped, heard=True, complete=True)]),
        max_age_s=1e9,
        clock=lambda: 1_000.0,
    )
    assert lax.refresh().state is MirrorState.FRESH, (
        "the accepts-unstamped falsifier still refused — it no longer falsifies"
    )


def test_A2_a_reading_the_mirror_refuses_does_not_disturb_a_GOOD_held_one() -> None:
    """A malformed message must not turn into an outage."""
    good = linked(5, 1_000.0)
    bad = dataclasses.replace(linked(6, 1_000.0), committed=-1.0)
    mirror = AllocatorMirror(
        ScriptedFeed(
            [
                MirrorUpdate(picture=good, heard=True, complete=True),
                MirrorUpdate(picture=bad, heard=True, complete=True),
            ]
        ),
        max_age_s=1e9,
        clock=lambda: 1_000.0,
    )
    mirror.refresh()
    after = mirror.refresh()
    assert after.state is MirrorState.FRESH
    assert mirror.version() == 5
    assert mirror.refused_incoherent == 1
    assert "disagrees with itself" in mirror.last_refusal


def test_A2_the_freshness_ceiling_has_no_silent_default() -> None:
    """§12A owns the value; a ceiling with a default is a ceiling nobody chose."""
    with pytest.raises(MirrorUsageError) as excinfo:
        AllocatorMirror(ScriptedFeed([MirrorUpdate()]), max_age_s=0.0)
    assert "ceiling nobody chose" in str(excinfo.value)


# --------------------------------------------------------------------------
# A3 — MONOTONIC-BY-SOURCE, PER KEY (§6.4b)
# --------------------------------------------------------------------------


def keyed(version: int, es: float, nq: float, ts: float = 1_000.0) -> FinancialPicture:
    """A picture whose per-symbol margins are independently settable."""
    row = PositionRow(
        trade_id="T-1",
        symbol="ES",
        strategy_id="strat-1",
        size=1,
        margin=1_000.0,
        state=PositionState.OPEN,
    )
    return FinancialPicture(
        version=version,
        published_ts=ts,
        balance=100_000.0,
        positions=(row,),
        margin_per_contract=MappingProxyType({"ES": es, "NQ": nq}),
        sum_open_margin=1_000.0,
        sum_reservations=0.0,
        committed=1_000.0,
        deployable=max(0.0, 0.70 * 100_000.0 - 1_000.0),
    )


def stamped(picture: FinancialPicture, **stamps: float) -> MirrorUpdate:
    return MirrorUpdate(
        picture=picture, heard=True, complete=True, source_stamps=dict(stamps)
    )


MONOTONIC_SCRIPT_KEYS = ("balance", "margin:ES", "margin:NQ")


def monotonic_script() -> list[MirrorUpdate]:
    """Held(v5) -> ES regresses -> NQ regresses -> version regresses -> all newer."""
    return [
        stamped(
            keyed(5, 5_000.0, 7_000.0), **dict.fromkeys(MONOTONIC_SCRIPT_KEYS, 100.0)
        ),
        stamped(
            keyed(6, 4_000.0, 7_500.0),
            **{"balance": 110.0, "margin:ES": 90.0, "margin:NQ": 110.0},
        ),
        stamped(
            keyed(7, 5_500.0, 6_000.0),
            **{"balance": 120.0, "margin:ES": 120.0, "margin:NQ": 90.0},
        ),
        stamped(keyed(4, 1.0, 1.0), **dict.fromkeys(MONOTONIC_SCRIPT_KEYS, 900.0)),
        stamped(
            keyed(8, 5_500.0, 7_500.0), **dict.fromkeys(MONOTONIC_SCRIPT_KEYS, 130.0)
        ),
    ]


def held_margin(mirror: AllocatorMirror, symbol: str) -> Any:
    snap = mirror.snapshot()
    return (
        None if snap.picture is None else snap.picture.margin_per_contract.get(symbol)
    )


@pytest.fixture
def monotonic() -> AllocatorMirror:
    mirror = AllocatorMirror(
        ScriptedFeed(monotonic_script()), max_age_s=1e9, clock=lambda: 1_000.0
    )
    mirror.refresh()
    return mirror


def test_A3_an_OUT_OF_ORDER_reading_is_DISCARDED_not_applied(
    monotonic: AllocatorMirror,
) -> None:
    """§6.4b, verbatim: *anything older is discarded, not applied*."""
    assert monotonic.version() == 5
    monotonic.refresh()
    assert monotonic.version() == 5, "the older-on-ES reading was applied"
    assert monotonic.discarded_older == 1
    assert "margin:ES" in monotonic.last_refusal
    assert "OLDER" in monotonic.last_refusal


def test_A3_the_guard_is_PER_KEY_and_a_late_ES_update_never_regresses_NQ(
    monotonic: AllocatorMirror,
) -> None:
    """§6.4b: *a late update on one key can never regress another*."""
    assert held_margin(monotonic, "ES") == 5_000.0
    assert held_margin(monotonic, "NQ") == 7_000.0
    monotonic.refresh()  # ES stamp older, NQ stamp newer, ES VALUE regressed
    assert held_margin(monotonic, "ES") == 5_000.0, "ES regressed to a stale value"
    assert held_margin(monotonic, "NQ") == 7_000.0, (
        "NQ was moved by an ES-stale reading"
    )
    monotonic.refresh()  # now NQ's stamp is the older one — a DIFFERENT key
    assert monotonic.version() == 5
    assert "margin:NQ" in monotonic.last_refusal, (
        "the guard fired on ES but not on NQ — it is watching one privileged key, "
        "not every key"
    )


def test_A3_an_older_PICTURE_VERSION_is_discarded_too(
    monotonic: AllocatorMirror,
) -> None:
    """The transport-order tier, distinct from the venue-order tier."""
    for _ in range(3):
        monotonic.refresh()
    assert monotonic.version() == 5
    assert monotonic.discarded_older == 3
    assert "not newer than the held" in monotonic.last_refusal


def test_A3_a_reading_newer_on_EVERY_key_IS_applied(
    monotonic: AllocatorMirror,
) -> None:
    """A guard that discards everything is not a guard."""
    for _ in range(4):
        monotonic.refresh()
    assert monotonic.version() == 8
    assert held_margin(monotonic, "ES") == 5_500.0
    assert held_margin(monotonic, "NQ") == 7_500.0
    assert monotonic.applied == 2


def test_A3_the_UNGUARDED_falsifier_really_does_regress_ES() -> None:
    """Without this, the four tests above are green over a mirror with no guard."""

    class Unguarded(AllocatorMirror):
        def _regression(self, picture: FinancialPicture, stamps: Any) -> str:
            del picture, stamps
            return ""  # WRONG: §6.4b's guard deleted

    fake = Unguarded(
        ScriptedFeed(monotonic_script()), max_age_s=1e9, clock=lambda: 1_000.0
    )
    fake.refresh()
    fake.refresh()
    assert held_margin(fake, "ES") == 4_000.0, (
        "the unguarded falsifier did not regress ES — it no longer falsifies"
    )


def test_A3_an_unstamped_reading_falls_back_to_published_ts_and_COUNTS_it() -> None:
    """D3.121: the published snapshot carries no venue stamps, and that is LOUD."""
    mirror = AllocatorMirror(
        ScriptedFeed(
            [
                MirrorUpdate(
                    picture=keyed(5, 1.0, 1.0, 10.0), heard=True, complete=True
                ),
                MirrorUpdate(
                    picture=keyed(6, 2.0, 2.0, 5.0), heard=True, complete=True
                ),
            ]
        ),
        max_age_s=1e9,
        clock=lambda: 10.0,
    )
    mirror.refresh()
    mirror.refresh()
    assert mirror.degraded_source_stamps == 2, "the degradation was not counted"
    assert mirror.version() == 5, "a reading published EARLIER was applied"
    assert mirror.discarded_older == 1


# --------------------------------------------------------------------------
# A4 — READ-ONLY PROVEN BY ATTEMPT (§2)
# --------------------------------------------------------------------------


def attempt_mutations(snap: Any) -> tuple[list[str], list[str]]:
    """`(mutations that SUCCEEDED, exceptions the attempts RAISED)`."""
    succeeded: list[str] = []
    raised: list[str] = []
    picture = snap.picture
    attempts = (
        ("balance", lambda: setattr(picture, "balance", 1.0)),
        ("positions[0]", lambda: operator.setitem(picture.positions, 0, None)),
        (
            "margin_per_contract['ES']",
            lambda: operator.setitem(picture.margin_per_contract, "ES", 1.0),
        ),
        ("MirrorSnapshot.state", lambda: setattr(snap, "state", None)),
    )
    for label, attempt in attempts:
        try:
            attempt()
        except (dataclasses.FrozenInstanceError, TypeError, AttributeError) as exc:
            raised.append(f"{label} -> {type(exc).__name__}")
            continue
        succeeded.append(label)
    return succeeded, raised


@dataclasses.dataclass
class WritablePicture:
    """FALSIFIER: a picture whose containers really do admit writes."""

    version: int
    published_ts: float
    balance: float
    positions: list[Any]
    margin_per_contract: dict[str, float]


def test_A4_every_mutation_ATTEMPTED_against_the_mirror_is_REFUSED() -> None:
    """The evidence is the RAISED exception, not the absence of a change."""
    mirror = AllocatorMirror(
        ScriptedFeed([MirrorUpdate(picture=linked(3), heard=True, complete=True)]),
        max_age_s=1e9,
        clock=lambda: 1_000.0,
    )
    snap = mirror.refresh()
    succeeded, raised = attempt_mutations(snap)
    assert not succeeded, f"mutations SUCCEEDED against a read-only mirror: {succeeded}"
    assert raised == [
        "balance -> FrozenInstanceError",
        "positions[0] -> TypeError",
        "margin_per_contract['ES'] -> TypeError",
        "MirrorSnapshot.state -> FrozenInstanceError",
    ], raised
    assert mirror.snapshot() == snap, "the held snapshot changed under the attempts"


def test_A4_the_SAME_attempt_harness_SUCCEEDS_against_a_writable_stand_in() -> None:
    """An attempt harness that cannot succeed anywhere measures its own try block."""
    from nixalloc.seam import (  # pylint: disable=import-outside-toplevel
        MirrorSnapshot,
    )

    fake = MirrorSnapshot(
        state=MirrorState.FRESH,
        # cast, because the WHOLE POINT of this stand-in is that it is not a
        # `FinancialPicture`: it is the mutable object the real one refuses to be.
        picture=cast(
            Any,
            WritablePicture(
                version=1,
                published_ts=0.0,
                balance=1.0,
                positions=[None],
                margin_per_contract={"ES": 1.0},
            ),
        ),
        reason="falsifier",
    )
    succeeded, _raised = attempt_mutations(fake)
    assert succeeded == ["balance", "positions[0]", "margin_per_contract['ES']"], (
        succeeded
    )


def test_A4_no_public_verb_of_the_mirror_ACCEPTS_a_picture() -> None:
    """§2: nothing may install a picture the Limiter never sent."""
    import inspect as _inspect  # pylint: disable=import-outside-toplevel

    offenders: list[str] = []
    for name in dir(AllocatorMirror):
        if name.startswith("_"):
            continue
        member = getattr(AllocatorMirror, name, None)
        if not callable(member):
            continue
        for parameter in _inspect.signature(member).parameters.values():
            if "FinancialPicture" in str(parameter.annotation) or (
                parameter.name == "picture"
            ):
                offenders.append(f"{name}({parameter.name})")
    assert not offenders, offenders


def test_A4_a_picture_whose_containers_admit_WRITES_is_never_held() -> None:
    """A mirror the Allocator could write is not a read-only mirror (§2, §9)."""
    writable = FinancialPicture(
        version=9,
        published_ts=1_000.0,
        balance=1_000.0,
        positions=(),
        margin_per_contract={"ES": 5.0},  # a real dict
        sum_open_margin=0.0,
        sum_reservations=0.0,
        committed=0.0,
        deployable=700.0,
    )
    mirror = AllocatorMirror(
        ScriptedFeed([MirrorUpdate(picture=writable, heard=True, complete=True)]),
        max_age_s=1e9,
        clock=lambda: 1_000.0,
    )
    snap = mirror.refresh()
    assert snap.state is MirrorState.PARTIAL
    assert snap.sizeable is False
    assert "item assignment" in snap.reason


def test_A4_a_MUTABLE_position_table_is_refused_too() -> None:
    """Both containers, because either one is a write the event log never sees."""
    mutable_rows = FinancialPicture(
        version=9,
        published_ts=1_000.0,
        balance=1_000.0,
        positions=cast(Any, []),  # a real list
        margin_per_contract=MappingProxyType({}),
        sum_open_margin=0.0,
        sum_reservations=0.0,
        committed=0.0,
        deployable=700.0,
    )
    mirror = AllocatorMirror(
        ScriptedFeed([MirrorUpdate(picture=mutable_rows, heard=True, complete=True)]),
        max_age_s=1e9,
        clock=lambda: 1_000.0,
    )
    snap = mirror.refresh()
    assert snap.state is MirrorState.PARTIAL
    assert "position table is a list" in snap.reason


def test_A4_the_mirror_satisfies_the_frozen_MirrorPort() -> None:
    """The seam declares two verbs and no mutating one; this is that, at runtime."""
    mirror = AllocatorMirror(ScriptedFeed([MirrorUpdate()]), max_age_s=1.0)
    assert isinstance(mirror, MirrorPort)
    assert isinstance(ScriptedFeed([]), SnapshotFeedPort)


# --------------------------------------------------------------------------
# THE REAL §12.7 TRANSPORT — ZeroMQ ipc://, snapshot-on-subscribe
# --------------------------------------------------------------------------


def wire_body(picture: FinancialPicture, stamps: dict[str, Any]) -> dict[str, Any]:
    from nixalloc.mirror import (  # pylint: disable=import-outside-toplevel
        SOURCE_STAMPS_FIELD,
    )

    body = dict(encode_picture(picture))
    body[SOURCE_STAMPS_FIELD] = stamps
    return body


def test_the_REAL_zeromq_ipc_path_delivers_a_snapshot_to_a_LATE_subscriber(
    tmp_path: Path,
) -> None:
    """§12.7 LOCKS the transport; a mirror proven only on a fake is proven on a fake.

    The table is published BEFORE the subscriber exists and never published
    again, so the ONLY thing that can deliver it is snapshot-on-subscribe.
    """
    endpoint = statebus.endpoint_for("t-alloc", root=tmp_path)
    publisher = statebus.StatePublisher(endpoint)
    subscriber = None
    try:
        publisher.publish(
            TOPIC,
            wire_body(keyed(11, 4_242.0, 8_484.0, time.time()), {"margin:ES": 100.0}),
        )
        subscriber = statebus.StateSubscriber(endpoint, [TOPIC])
        mirror = AllocatorMirror(StateBusFeed(subscriber), max_age_s=60.0)
        publisher.service(1500)
        snap = mirror.refresh(750)
        assert subscriber.bytes_received > 0, (
            "zero bytes off the socket measures nothing"
        )
        assert snap.state is MirrorState.FRESH, snap.reason
        assert snap.sizeable is True
        assert snap.picture is not None
        assert snap.picture.margin_per_contract["ES"] == 4_242.0
        assert Path(endpoint.removeprefix("ipc://")).exists()

        # §6.4b over the SAME live socket: a delta whose ES stamp regressed.
        publisher.publish(
            TOPIC,
            wire_body(keyed(12, 1.0, 1.0, time.time()), {"margin:ES": 90.0}),
        )
        mirror.refresh(750)
        assert mirror.version() == 11, "a stale-keyed delta was applied over the wire"
        assert mirror.discarded_older == 1
        assert "margin:ES" in mirror.last_refusal
    finally:
        if subscriber is not None:
            subscriber.close()
        publisher.close()


def test_the_REAL_zeromq_ipc_path_CONTROL_receives_nothing_without_service(
    tmp_path: Path,
) -> None:
    """Without the CONTROL, arrival above is not evidence the mechanism works."""
    endpoint = statebus.endpoint_for("t-ctl", root=tmp_path)
    publisher = statebus.StatePublisher(endpoint)
    subscriber = None
    try:
        publisher.publish(TOPIC, wire_body(keyed(11, 1.0, 1.0, time.time()), {}))
        subscriber = statebus.StateSubscriber(endpoint, [TOPIC])
        mirror = AllocatorMirror(StateBusFeed(subscriber), max_age_s=60.0)
        snap = mirror.refresh(750)  # service() deliberately never called
        assert subscriber.bytes_received == 0
        assert snap.sizeable is False
        assert snap.state in (MirrorState.EMPTY, MirrorState.PARTIAL)
    finally:
        if subscriber is not None:
            subscriber.close()
        publisher.close()


def test_the_REAL_zeromq_ipc_path_leaves_a_DELTA_ONLY_mirror_partial(
    tmp_path: Path,
) -> None:
    """§12.7: *mirror incomplete => treated as stale => fast-drop until snapshot*.

    This is ARC 027's `XPUB_VERBOSE` hazard from the consumer's seat: real bytes
    arrived, the feed looks healthy, and the mirror is NOT sizeable.
    """
    endpoint = statebus.endpoint_for("t-dlt", root=tmp_path)
    publisher = statebus.StatePublisher(endpoint)
    subscriber = None
    try:
        subscriber = statebus.StateSubscriber(endpoint, [TOPIC])
        mirror = AllocatorMirror(StateBusFeed(subscriber), max_age_s=60.0)
        body = wire_body(keyed(11, 1.0, 1.0, time.time()), {})
        snap = mirror.snapshot()
        for _ in range(60):
            publisher.publish(TOPIC, body)  # a DELTA; service() never called
            snap = mirror.refresh(25)
            if subscriber.bytes_received:
                break
        assert subscriber.bytes_received > 0, "no delta was ever delivered"
        assert snap.state is MirrorState.PARTIAL, snap.reason
        assert snap.sizeable is False
        assert "no snapshot yet" in snap.reason
    finally:
        if subscriber is not None:
            subscriber.close()
        publisher.close()


def test_the_REAL_wire_refuses_an_unreadable_source_stamp(tmp_path: Path) -> None:
    """§6.4b orders by source time; a stamp that cannot be read is refused."""
    endpoint = statebus.endpoint_for("t-bad", root=tmp_path)
    publisher = statebus.StatePublisher(endpoint)
    subscriber = None
    try:
        publisher.publish(
            TOPIC,
            wire_body(keyed(11, 1.0, 1.0, time.time()), {"margin:ES": "yesterday"}),
        )
        subscriber = statebus.StateSubscriber(endpoint, [TOPIC])
        mirror = AllocatorMirror(StateBusFeed(subscriber), max_age_s=60.0)
        publisher.service(1500)
        snap = mirror.refresh(750)
        assert subscriber.bytes_received > 0
        assert snap.state is MirrorState.PARTIAL, snap.reason
        assert "unreadable entry" in snap.reason
    finally:
        if subscriber is not None:
            subscriber.close()
        publisher.close()
