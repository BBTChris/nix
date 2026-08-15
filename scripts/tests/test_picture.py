"""`scripts/nixrisk/picture.py` — §3's atomic snapshot and §12.7's mirror rule.

What each test proves:

* the atomicity MECHANISM is a property of the object, not a discipline: a
  picture handed out before a commit is unchanged by it, and `current()` returns
  the whole new snapshot in one step;
* `commit` derives §3's four aggregates and REFUSES to be handed them;
* `deployable` has the definition D3.42 asked the publisher to state;
* `publish` refuses an incoherent snapshot and names the field;
* `picture_defects` catches the tears it can — and provably does NOT catch the
  coherent stale-balance tear, which is asserted so nobody believes it stronger
  than it is;
* the wire round-trips, and the `_schema` regression stays fixed;
* `PictureMirror` refuses an incomplete mirror and an over-age one, and PERMITS
  a fresh complete one.

Every assertion names the field or the reason, never a bare truth value.
All sockets live under `tmp_path`; nothing here touches `$XDG_RUNTIME_DIR`.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=protected-access,missing-function-docstring
# `invalid-name`: test names SHOUT the property under measurement, which is the
# house convention (`scripts/tests/test_statebus.py`) and is what makes a red
# line in the suite output readable without opening the file.
# `protected-access`: a can-fail control drives the gate's ARMS and helpers,
# which are private by design — a helper made public so a test could reach it
# would be a surface the gate did not need, invented for the test.
# `redefined-outer-name`: pytest fixtures are injected by name; that IS the API.
# `duplicate-code`: the sys.path bootstrap and the `--correct` refusal probe are
# MANDATED to be identical across suites (`nix_check_contract.md` §4.2).
# `missing-function-docstring`: a handful of one-line controls whose NAME is the
# whole statement; the rest carry docstrings.

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
from nixbus import statebus
from nixrisk import picture as pic
from nixrisk.seam import FinancialPicture, PositionRow, PositionState

FRACTION = 0.70


def _row(trade_id: str, margin: float, state: PositionState = PositionState.OPEN):
    return PositionRow(
        trade_id=trade_id,
        symbol="MESU6",
        strategy_id="s1",
        size=1,
        margin=margin,
        state=state,
        stop_distance=20,
    )


def _book(**kwargs):
    return pic.FinancialPictureBook(
        balance=100_000.0, deployable_fraction=FRACTION, **kwargs
    )


@pytest.fixture
def closing() -> Iterator[list]:
    """Every socket opened by a test is closed here, even when it fails."""
    opened: list = []
    try:
        yield opened
    finally:
        for item in reversed(opened):
            item.close()


# ---------------------------------------------------------------------------
# The mechanism
# ---------------------------------------------------------------------------


def test_a_picture_HELD_across_a_commit_is_UNCHANGED_by_it() -> None:
    """§3's atomicity as a property of the TYPE, not of the writer's discipline."""
    book = _book()
    held = book.current()
    book.commit(balance=222_222.0, positions=(_row("T1", 5_000.0),))
    assert held.balance == 100_000.0, held.balance
    assert not held.positions, held.positions
    assert book.current().balance == 222_222.0, book.current().balance
    assert book.current() is not held, "the store must rebind, never mutate"


def test_commit_advances_balance_and_the_TABLE_under_ONE_version() -> None:
    """Never two versions: there is no verb that moves one half without the other."""
    book = _book()
    before = book.current().version
    after = book.commit(balance=5.0, positions=(_row("T1", 1.0),))
    assert after.version == before + 1, (before, after.version)
    assert after.balance == 5.0 and len(after.positions) == 1, after


def test_the_DERIVED_fields_follow_SS3s_arithmetic_and_D3_42s_answer() -> None:
    """`committed = Σ open + Σ res`; `deployable = max(0, f×bal − committed)`."""
    book = _book()
    snapshot = book.commit(
        balance=100_000.0,
        positions=(
            _row("T1", 10_000.0),
            _row("T2", 4_000.0, PositionState.CLOSING),
            _row("T3", 99_000.0, PositionState.RESERVED),
            _row("T4", 88_000.0, PositionState.CLOSED),
        ),
        sum_reservations=6_000.0,
    )
    assert snapshot.sum_open_margin == 14_000.0, snapshot.sum_open_margin
    assert snapshot.committed == 20_000.0, snapshot.committed
    assert snapshot.deployable == pytest.approx(50_000.0), snapshot.deployable
    assert not pic.picture_defects(snapshot, FRACTION), pic.picture_defects(snapshot)


def test_RESERVED_and_PENDING_rows_are_NOT_double_counted() -> None:
    """§3 counts their margin in Σ reservations; counting it twice denies everything."""
    book = _book()
    snapshot = book.commit(
        positions=(
            _row("T1", 7.0, PositionState.RESERVED),
            _row("T2", 9.0, PositionState.PENDING),
        ),
        sum_reservations=16.0,
    )
    assert snapshot.sum_open_margin == 0.0, snapshot.sum_open_margin
    assert snapshot.committed == 16.0, snapshot.committed


def test_a_SECOND_writer_is_REFUSED_and_not_serialised() -> None:
    """§9/§12.10: the Limiter is sole writer. A lock would hide the violation.

    The re-entry happens where a second writer really could: inside `_next`,
    while `tuple(positions)` walks the caller's iterable and `_writing` is set.
    """
    book = _book()

    class _ReentrantRows(tuple):
        """A positions iterable that commits again while it is being consumed."""

        def __iter__(self):
            book.commit(balance=3.0)
            return super().__iter__()

    with pytest.raises(pic.ConcurrentWriter) as red:
        book.commit(positions=_ReentrantRows())
    assert "SOLE writer" in str(red.value), str(red.value)
    assert book.refusals == 1, book.refusals
    # And the flag is RELEASED, so the refusal is not a permanent wedge.
    assert book.commit(balance=4.0).balance == 4.0, book.current()


def test_publish_REFUSES_an_incoherent_snapshot_and_NAMES_the_field() -> None:
    """A mirror has no defence against a snapshot that arrived complete and wrong."""
    book = _book()
    bad = FinancialPicture(
        version=2,
        published_ts=time.time(),
        balance=100.0,
        positions=(_row("T1", 10.0),),
        margin_per_contract={},
        sum_open_margin=10.0,
        sum_reservations=0.0,
        committed=999.0,  # THE PLANT
        deployable=0.0,
    )
    with pytest.raises(pic.TornPicture) as red:
        book.publish(bad)
    assert "committed=999.0" in str(red.value), str(red.value)
    assert book.refusals == 1, book.refusals


# ---------------------------------------------------------------------------
# The detector, and its measured blind spot
# ---------------------------------------------------------------------------


def test_picture_defects_names_a_DUPLICATE_trade_id() -> None:
    """§3 keys the table BY trade_id; two rows for one key is not keyed."""
    snapshot = FinancialPicture(
        version=1,
        published_ts=0.0,
        balance=0.0,
        positions=(_row("T1", 0.0), _row("T1", 0.0)),
        margin_per_contract={},
        sum_open_margin=0.0,
        sum_reservations=0.0,
        committed=0.0,
        deployable=0.0,
    )
    defects = pic.picture_defects(snapshot, FRACTION)
    assert any("appears twice" in d and "T1" in d for d in defects), defects


def test_picture_defects_CANNOT_see_the_coherent_STALE_BALANCE_tear() -> None:
    """The blind spot, asserted so it is never mistaken for a guarantee.

    A publisher that reads balance at generation k and the table at k+1 and then
    derives consistently produces a snapshot every predicate here accepts. This
    is exactly why `check_picture_atomicity` plants a generation LINK between
    balance and every row's margin; a gate running only this predicate under
    concurrency would race hard and observe nothing.
    """
    stale_balance = 100_000.0
    fresh_rows = (_row("T1", 3_000.0),)
    torn = FinancialPicture(
        version=9,
        published_ts=0.0,
        balance=stale_balance,
        positions=fresh_rows,
        margin_per_contract={},
        sum_open_margin=3_000.0,
        sum_reservations=0.0,
        committed=3_000.0,
        deployable=max(0.0, FRACTION * stale_balance - 3_000.0),
    )
    assert not pic.picture_defects(torn, FRACTION), (
        "if this ever starts failing the predicate has become stronger and the "
        "gate's generation-link plant should be revisited"
    )


# ---------------------------------------------------------------------------
# The wire
# ---------------------------------------------------------------------------


def test_the_wire_ROUND_TRIPS_every_field() -> None:
    book = _book()
    snapshot = book.commit(
        balance=12_345.67,
        positions=(_row("T1", 100.0), _row("T2", 7.0, PositionState.CLOSING)),
        margin_per_contract={"MESU6": 1_234.5},
        sum_reservations=42.0,
    )
    back = pic.decode_picture(pic.encode_picture(snapshot))
    assert back == snapshot, (back, snapshot)


def test_the_schema_key_is_NOT_underscore_prefixed_REGRESSION() -> None:
    """`statebus._decode` strips every `_`-prefixed key. Measured, ARC 028 S2.

    The first spelling was `_schema`; the transport stripped it, `decode_picture`
    refused every message, and the gate reported 18.9 MB carried and zero
    pictures decoded. A leading underscore on this wire is the TRANSPORT's
    namespace.
    """
    body = pic.encode_picture(_book().current())
    assert "schema" in body, sorted(body)
    assert not any(key.startswith("_") for key in body), sorted(body)


def test_decode_REFUSES_an_unknown_schema_and_says_so() -> None:
    body = pic.encode_picture(_book().current())
    body["schema"] = 99
    with pytest.raises(pic.PictureError) as red:
        pic.decode_picture(body)
    assert "wire schema 99" in str(red.value), str(red.value)


def test_a_picture_survives_the_REAL_state_bus(tmp_path: Path, closing: list) -> None:
    """End to end over `ipc://`: publish, subscribe, mirror, decode, compare."""
    endpoint = statebus.endpoint_for("pic", root=tmp_path)
    publisher = statebus.StatePublisher(endpoint)
    closing.append(publisher)
    sink = pic.StateBusPictureSink(publisher)
    book = pic.FinancialPictureBook(
        balance=50_000.0, deployable_fraction=FRACTION, sink=sink
    )
    sent = book.commit(balance=51_000.0, positions=(_row("T9", 900.0),))
    subscriber = statebus.StateSubscriber(endpoint, [pic.TOPIC])
    closing.append(subscriber)
    mirror = pic.PictureMirror(subscriber, max_age_s=60.0)
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        sink.service(50)
        mirror.drain(20)
        if subscriber.mirror.complete:
            break
    assert subscriber.mirror.complete, subscriber.mirror.missing
    assert subscriber.bytes_received > 0, "zero wire bytes is a vacuous round trip"
    got = mirror.picture()
    assert got is not None, mirror.decode_errors
    assert got == sent, (got, sent)


# ---------------------------------------------------------------------------
# §12.7's fast-drop rule
# ---------------------------------------------------------------------------


def test_an_INCOMPLETE_mirror_DENIES_and_names_the_missing_topic(
    tmp_path: Path, closing: list
) -> None:
    endpoint = statebus.endpoint_for("empty", root=tmp_path)
    publisher = statebus.StatePublisher(endpoint)
    closing.append(publisher)
    subscriber = statebus.StateSubscriber(endpoint, [pic.TOPIC])
    closing.append(subscriber)
    ok, why = pic.PictureMirror(subscriber, max_age_s=60.0).tradable()
    assert ok is False, why
    assert "mirror incomplete" in why and pic.TOPIC in why, why


def test_an_OVER_AGE_mirror_DENIES_and_a_FRESH_one_PERMITS(
    tmp_path: Path, closing: list
) -> None:
    """The control is the second half: without it 'always denies' would pass."""
    endpoint = statebus.endpoint_for("aged", root=tmp_path)
    publisher = statebus.StatePublisher(endpoint)
    closing.append(publisher)
    sink = pic.StateBusPictureSink(publisher)
    book = pic.FinancialPictureBook(
        balance=1_000.0, deployable_fraction=FRACTION, sink=sink
    )
    book.commit(positions=(_row("T1", 10.0),))
    subscriber = statebus.StateSubscriber(endpoint, [pic.TOPIC])
    closing.append(subscriber)
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        sink.service(50)
        subscriber.drain(20)
        if subscriber.mirror.complete:
            break
    assert subscriber.mirror.complete, subscriber.mirror.missing

    fresh_ok, fresh_why = pic.PictureMirror(subscriber, max_age_s=60.0).tradable()
    assert fresh_ok is True, fresh_why
    aged_ok, aged_why = pic.PictureMirror(
        subscriber, max_age_s=1.0, clock=lambda: time.time() + 3_600.0
    ).tradable()
    assert aged_ok is False, aged_why
    assert "stale" in aged_why and "3600." in aged_why, aged_why


def test_a_TORN_mirrored_picture_DENIES_and_names_the_field(
    tmp_path: Path, closing: list
) -> None:
    """A mirror that arrived complete and WRONG still refuses to size."""
    endpoint = statebus.endpoint_for("torn", root=tmp_path)
    publisher = statebus.StatePublisher(endpoint)
    closing.append(publisher)
    subscriber = statebus.StateSubscriber(endpoint, [pic.TOPIC])
    closing.append(subscriber)
    body = pic.encode_picture(_book().commit(positions=(_row("T1", 10.0),)))
    body["committed"] = 4_242.0  # THE PLANT, on the wire, not in the publisher
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        publisher.publish(pic.TOPIC, body)
        publisher.service(50)
        subscriber.drain(20)
        if subscriber.mirror.complete:
            break
    assert subscriber.mirror.complete, subscriber.mirror.missing
    ok, why = pic.PictureMirror(subscriber, max_age_s=60.0).tradable()
    assert ok is False, why
    assert "committed=4242.0" in why, why


# ---------------------------------------------------------------------------
# The race, in miniature — the gate owns the full instrument
# ---------------------------------------------------------------------------


def test_a_reader_RACING_a_writer_never_sees_two_generations() -> None:
    """The gate's property, held once here so a broken book reddens the SUITE too."""
    base = 1_000_000.0
    book = _book()
    stop = threading.Event()

    def writer() -> None:
        generation = 1
        while not stop.is_set():
            book.commit(
                balance=base + generation,
                positions=(_row("T1", float(generation)),),
            )
            generation += 1

    previous = sys.getswitchinterval()
    sys.setswitchinterval(1e-5)
    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    try:
        tears = []
        versions = set()
        for _ in range(2_000):
            snapshot = book.current()
            versions.add(snapshot.version)
            generation = snapshot.balance - base
            tears += [
                f"balance gen {generation:.0f} vs row margin {row.margin:.0f}"
                for row in snapshot.positions
                if row.margin != generation
            ]
    finally:
        stop.set()
        thread.join(timeout=5.0)
        sys.setswitchinterval(previous)
    assert len(versions) > 1, "the writer never moved: this raced nothing"
    assert not tears, tears[:3]
