"""ARC 038 / sub-agent D — the four MONEY-TRUTH findings, each with BOTH halves.

Subjects: `scripts/nixrisk/picture.py` (§3's atomic financial picture, §12.7's
transport) and `scripts/nixrisk/survival.py` (§6.5's net-liq survival watch).
Authority is `docs/nics_risk_subsystem_spec_v1.3.md`; the invariants are §14:972
(*"Survival is watched on net-liq; sizing is computed on cash. Never conflate."*)
and §3:164's ATOMICITY RULE.

------------------------------------------------------------------------------
debug.md §7.12 — WHAT WOULD HAVE TO BE TRUE FOR THIS SUITE TO MEASURE NOTHING
------------------------------------------------------------------------------
1. **ONLY THE PROTECTED HALF RUNS.** ARC 035 measured a control masking itself
   three times: an assertion that the repaired code behaves well is satisfied by
   code that never could have behaved badly. Closed by staging the subject,
   REMOVING the repair from the staged copy by an exact string edit, and
   REQUIRING the bad outcome to appear there — then requiring it gone from the
   shipped module. Every finding below has both halves in one test.

2. **THE STAGED COPY IS NOT THE ONE THAT RAN.** D3.344 measured a plant defeated
   because a child inherited `PYTHONPATH` and imported production. Nothing here
   spawns a child for the plants; they are loaded in-process by
   `importlib.util.spec_from_file_location`, and `_stage` ASSERTS the loaded
   module's `__file__` is the staged path and that the repair's text is provably
   absent from it. A plant that silently loaded production would fail that
   assertion before it could pass a behavioural one.

3. **THE EXIT STATUS IS THE ASSERTION.** Check-contract rule 11 / §18: every
   control below asserts the REASON — the field name in the refusal, the site in
   the message — never a bare truthy value and never an exception TYPE alone.

4. **THE RACE NEVER RACED.** The I7 arm crosses a REAL process boundary over a
   REAL `ipc://` socket and does not end on a clock: it ends on arrival, and it
   REFUSES to judge unless the reader saw `MIN_GENERATIONS` distinct generations.
   Its detector is proven able to count by a publisher that publishes §3's
   COHERENT tear — the one `picture_defects` documents it cannot see.

Sockets live under `tmp_path`; nothing here touches `$XDG_RUNTIME_DIR`. Every
child is reaped in a `finally` and every socket closed (D3.347).
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=protected-access,missing-function-docstring
# pylint: disable=too-few-public-methods,use-implicit-booleaness-not-comparison
# pylint: disable=too-many-locals,consider-using-with
# `too-few-public-methods`: every fake below is a single-verb stand-in for ONE
# port of the frozen seam. A second method would be a fake doing two jobs.
# `use-implicit-booleaness-not-comparison`: `flat.fired == []` is asserting that
# a LIST is empty, and `not flat.fired` would also pass on `None` — which is what
# a broken fake returns. The comparison is the measurement.
# `too-many-locals` / `consider-using-with`: the cross-process arm owns a child
# process and a socket whose lifetimes span the whole race and are reaped in one
# `finally`; a `with` per resource would nest four deep for no added guarantee.
# `invalid-name`: test names SHOUT the property, the house convention.
# `protected-access`: the controls drive private helpers of the subject on
# purpose — a helper made public for a test is a surface the subject did not need.
# `duplicate-code`: the sys.path bootstrap is mandated identical across suites
# (`nix_check_contract.md` §4.2).

from __future__ import annotations

import importlib.util
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
from nixbus import statebus
from nixrisk import picture as pic
from nixrisk import survival as sur
from nixrisk.gate import GatePass, default_manifest
from nixrisk.reservations import ReservationLedger
from nixrisk.seam import (
    FinancialPicture,
    PositionRow,
    PositionState,
    ProposedOrder,
    Side,
    StopMode,
)

FRACTION = 0.70
PAD = 0.10
#: The reader must see at least this many DISTINCT generations before the I7 arm
#: is allowed to conclude anything. Below it the writer did not demonstrably move
#: underneath the reader and a clean sheet is an absence, not a measurement.
MIN_GENERATIONS = 300


# ---------------------------------------------------------------------------
# Staging — the UNPROTECTED half, loaded in-process with its origin PROVEN
# ---------------------------------------------------------------------------


def _stage_named(
    tmp_path: Path, name: str, tag: str, edits: list[tuple[str, str]]
) -> ModuleType:
    """`_stage` with an explicit tag, so two plants of ONE module can coexist."""
    return _stage(tmp_path, name, edits, tag=tag)


def _stage(
    tmp_path: Path, name: str, edits: list[tuple[str, str]], tag: str = ""
) -> ModuleType:
    """Load a copy of `scripts/nixrisk/<name>.py` with `edits` applied.

    Each edit is `(must_be_present, replacement)` and BOTH directions are
    asserted: the text being removed must be found (or the plant planted nothing
    and the test is vacuous) and must be gone afterwards.
    """
    source = (REPO / "scripts" / "nixrisk" / f"{name}.py").read_text()
    for needle, replacement in edits:
        assert needle in source, (
            f"the plant found nothing to remove in {name}.py — the repair's text "
            f"has moved and this control is now vacuous: {needle[:80]!r}"
        )
        source = source.replace(needle, replacement)
    for needle, _ in edits:
        assert needle not in source, f"plant did not take: {needle[:60]!r}"
    staged = tmp_path / f"planted_{name}{tag}.py"
    staged.write_text(source)
    spec = importlib.util.spec_from_file_location(f"planted_{name}{tag}", staged)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # REGISTERED BEFORE `exec_module`, and that is not decoration: `dataclasses`
    # resolves a string annotation by looking `cls.__module__` up in
    # `sys.modules`, so an unregistered staged module raises `AttributeError`
    # inside `dataclasses` before a single behavioural assertion is reached.
    # The name is unique per plant, so nothing shadows a real module.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    # D3.344: PROVE which file ran. A plant that loaded production would satisfy
    # every behavioural assertion below by being correct.
    assert module.__file__ == str(staged), module.__file__
    assert str(REPO / "scripts" / "nixrisk") not in str(module.__file__)
    return module


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


# ---------------------------------------------------------------------------
# FD1 — a REFUSED publish must not advance the Limiter's OWN table
# ---------------------------------------------------------------------------


class _NullPlane1:
    """§9's sink, reduced to the three verbs `ReservationLedger` calls."""

    def __init__(self) -> None:
        self.rows: list[object] = []

    def enqueue(self, row: object) -> None:
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        return len(self.rows)

    def pending(self) -> int:
        return 0


class _Clear:
    def is_set(self) -> tuple[bool, str]:
        return (False, "")

    def read(self, symbol: str | None = None) -> tuple[bool, str]:
        del symbol
        return (False, "")


class _NoLock:
    def in_flight(self, strategy_id: str) -> tuple[bool, str]:
        del strategy_id
        return (False, "")


class _Mark:
    """A GENEROUS, honest net-liq mark, so the survival rule is not what denies."""

    def mark(self) -> tuple[float, bool]:
        return (500_000.0, True)


def _gate() -> GatePass:
    clear = _Clear()
    return GatePass(
        halt=clear,
        rules=default_manifest(
            blackout=clear,
            tradability=clear,
            staleness=clear,
            clock_skew=clear,
            in_flight=_NoLock(),
            net_liq=_Mark(),
            deployable_fraction=FRACTION,
            survival_safety_pad=PAD,
            coherence_tolerance=1e-9,
        ),
        ledger=ReservationLedger(_NullPlane1()),
    )


#: 800 contracts x $500 = $400,000 of margin against a $10,000 account. The
#: healthy answer is a clamp; anything else is money the account does not have.
_OVERSIZED = ProposedOrder(
    client_order_id="c-fd1",
    strategy_id="s1",
    symbol="MESU6",
    side=Side.LONG,
    qty=800,
    margin_per_contract=500.0,
    stop_ticks=20,
    stop_mode=StopMode.FIXED,
    signal_ts=1.0,
)

_FD1_REPAIR = """            defects = picture_defects(picture, self._fraction)
            if defects:
                self.refusals += 1
                raise TornPicture("""


def _drive_fd1(picture_mod: ModuleType) -> dict[str, object]:
    """Refuse a commit, then run the FULL §3 gate pass over `current()`."""
    book = picture_mod.FinancialPictureBook(
        balance=10_000.0, deployable_fraction=FRACTION
    )
    book.commit(balance=10_000.0, positions=(_row("T1", 500.0),), sum_reservations=0.0)
    control = _gate().evaluate(_OVERSIZED, book.current(), now=1.0)
    refusal = ""
    try:
        book.commit(sum_reservations=float("-inf"))
    except picture_mod.TornPicture as exc:
        refusal = str(exc)
    after = book.current()
    outcome = _gate().evaluate(_OVERSIZED, after, now=1.0)
    return {
        "control_decision": control.decision.name,
        "control_qty": control.sized_qty if control.sized_qty is not None else 800,
        "refusal": refusal,
        "version": after.version,
        "committed": after.committed,
        "deployable": after.deployable,
        "decision": outcome.decision.name,
        "qty": outcome.sized_qty if outcome.sized_qty is not None else 800,
    }


def test_FD1_a_REFUSED_commit_leaves_the_OWN_TABLE_STANDING_and_the_gate_CLAMPS(
    tmp_path: Path,
) -> None:
    """The unrepaired half APPROVES $400,000 on $10,000; the repaired half clamps.

    §3 gives the Limiter ONE table and every Phase-B money rule reads it through
    `current()`. The store used to happen BEFORE `publish()` validated, so a
    refused publish left `current()` holding the picture just declared
    unpublishable — and with `sum_reservations = -inf` that picture reports
    `committed = -inf` and `deployable = +inf`, which every cap approves.
    """
    planted = _stage(
        tmp_path,
        "picture",
        [
            (
                _FD1_REPAIR,
                """            if False:
                raise TornPicture(""",
            )
        ],
    )
    bad = _drive_fd1(planted)
    # THE UNPROTECTED HALF — the bad outcome must actually appear.
    assert bad["control_decision"] == "SIZE_DOWN" and bad["control_qty"] == 12, bad
    assert bad["refusal"], "the plant removed the refusal as well as the store order"
    assert bad["version"] == 3, bad
    assert bad["committed"] == float("-inf"), bad
    assert bad["deployable"] == float("inf"), bad
    assert bad["decision"] == "APPROVE" and bad["qty"] == 800, (
        "the plant did not reproduce the fail-open; this control proves nothing "
        f"about the repair: {bad}"
    )
    # THE PROTECTED HALF — the shipped module, same drive.
    good = _drive_fd1(pic)
    assert "refusing to commit version 3" in good["refusal"], good["refusal"]
    assert "sum_reservations is -inf" in good["refusal"], good["refusal"]
    assert "STANDS" in good["refusal"], good["refusal"]
    assert good["version"] == 2, good
    assert good["committed"] == 500.0 and good["deployable"] == 6500.0, good
    assert good["decision"] == "SIZE_DOWN" and good["qty"] == 12, good


def test_FD1_the_refusal_names_the_FIELD_and_the_version_that_STANDS() -> None:
    """§18: the reason is the artifact, not the exception type."""
    book = pic.FinancialPictureBook(balance=10_000.0, deployable_fraction=FRACTION)
    book.commit(balance=10_000.0, positions=(), sum_reservations=0.0)
    with pytest.raises(pic.TornPicture) as red:
        book.commit(balance=float("nan"))
    message = str(red.value)
    assert "balance is nan" in message, message
    assert "version 2" in message and "STANDS" in message, message
    assert book.commits == 1 and book.refusals == 1, (book.commits, book.refusals)
    assert book.current().balance == 10_000.0, book.current().balance


def test_FD1_a_DUPLICATE_trade_id_commit_does_not_INFLATE_committed() -> None:
    """The reachable arm: a caller that merges one row twice (§3 keys BY trade_id)."""
    book = pic.FinancialPictureBook(balance=10_000.0, deployable_fraction=FRACTION)
    book.commit(balance=10_000.0, positions=(_row("T1", 500.0),), sum_reservations=0.0)
    with pytest.raises(pic.TornPicture) as red:
        book.commit(positions=(_row("T1", 500.0), _row("T1", 500.0)))
    assert "appears twice" in str(red.value) and "T1" in str(red.value)
    held = book.current()
    assert held.sum_open_margin == 500.0, held.sum_open_margin
    assert held.deployable == 6500.0, held.deployable


# ---------------------------------------------------------------------------
# FD2 — the survival FLOOR's own input, and §7:483's clamp
# ---------------------------------------------------------------------------


class _Flatten:
    def __init__(self) -> None:
        self.fired: list[tuple[object, str]] = []

    def flatten(self, trigger: object, reason: str) -> None:
        self.fired.append((trigger, reason))


class _Alerts:
    def __init__(self) -> None:
        self.alerts: list[object] = []

    def emit(self, alert: object) -> None:
        self.alerts.append(alert)


class _Broker:
    def __init__(self) -> None:
        self.reading: object = None

    def poll(self) -> object:
        return self.reading


def _watch(module: ModuleType) -> tuple[object, _Flatten, _Alerts, _Broker]:
    flat, alerts, broker = _Flatten(), _Alerts(), _Broker()
    watch = module.SurvivalWatch(
        safety_pad=PAD,
        broker=broker,
        flatten=flat,
        alert=alerts,
        tolerance=1.0,
        clock=lambda: 1_000.0,
    )
    return watch, flat, alerts, broker


_FD2_FINITE = '            _finite("sum_open_margin", sum_open_margin),\n'
_FD2_CLAMP = "return max(0.0, sum_open_margin) * (1.0 + self._safety_pad)"
_FD2_UNCLAMP = (
    _FD2_CLAMP,
    _FD2_CLAMP.replace("max(0.0, sum_open_margin)", "sum_open_margin"),
)
#: BOTH repairs removed = the code as ARC 029 shipped it. The two are COUPLED and
#: that was measured: with the clamp present but the finite check gone,
#: `max(0.0, nan)` is `0.0` — CPython's `max` keeps its first argument because
#: `nan > 0.0` is False — so the floor becomes ZERO and the watch still never
#: fires. Neither repair alone closes the hole; the pair does.
_FD2_PLANT_BOTH = [(_FD2_FINITE, ""), _FD2_UNCLAMP]


def test_FD2_a_NON_FINITE_SIGMA_OPEN_MARGIN_is_REFUSED_not_judged_SAFE(
    tmp_path: Path,
) -> None:
    """Unrepaired, a NaN Σ open margin makes the floor NaN and the watch NEVER fires.

    `SurvivalReading.breached` is `net_liq < floor`. With `floor = nan` that
    comparison is False for every net-liq, so §6.5's force-flatten — the thing
    that stands between this account and a broker liquidation — is silent, and
    silent is exactly what a healthy account looks like.
    """
    planted = _stage(tmp_path, "survival", _FD2_PLANT_BOTH)
    watch, flat, alerts, _ = _watch(planted)
    out = watch.mark(cash=50_000.0, net_liq=9_000.0, sum_open_margin=float("nan"))
    # THE UNPROTECTED HALF — the code exactly as it shipped.
    assert math.isnan(out.reading.floor), out.reading.floor
    assert out.breached is False and out.fired is False, out
    assert flat.fired == [] and alerts.alerts == [], (flat.fired, alerts.alerts)
    # AND the half-repair, so nobody reads either edit as sufficient on its own:
    # clamp WITHOUT the finite check silently floors at ZERO and still never fires.
    half_mod = _stage_named(tmp_path, "survival", "half", [(_FD2_FINITE, "")])
    watch2, flat2, _, _ = _watch(half_mod)
    out2 = watch2.mark(cash=50_000.0, net_liq=9_000.0, sum_open_margin=float("nan"))
    assert out2.reading.floor == 0.0, out2.reading.floor
    assert out2.breached is False and flat2.fired == [], out2
    # THE PROTECTED HALF — same drive against the shipped module.
    watch, flat, _, _ = _watch(sur)
    with pytest.raises(sur.SurvivalWatchError) as red:
        watch.mark(cash=50_000.0, net_liq=9_000.0, sum_open_margin=float("nan"))
    assert "sum_open_margin is nan" in str(red.value), str(red.value)
    assert "§17" in str(red.value) or "not proven" in str(red.value), str(red.value)
    # and the CONTROL that keeps this from being "always refuses": a real breach
    # on finite inputs still fires.
    watch, flat, alerts, _ = _watch(sur)
    out = watch.mark(cash=50_000.0, net_liq=9_000.0, sum_open_margin=10_000.0)
    assert out.reading.floor == pytest.approx(11_000.0), out.reading.floor
    assert out.breached and out.fired and len(flat.fired) == 1, out
    assert "net_liq" in flat.fired[0][1] and "9000.0" in flat.fired[0][1]


def test_FD2_ONE_broker_row_with_a_NaN_margin_cannot_SILENCE_the_reconcile(
    tmp_path: Path,
) -> None:
    """§4's reconcile derives Σ open margin from the poll — so the poll can poison it."""
    poisoned = (
        PositionRow(
            trade_id="T1",
            symbol="MESU6",
            strategy_id="s1",
            size=1,
            margin=float("nan"),
            state=PositionState.OPEN,
            stop_distance=20,
        ),
    )
    planted = _stage(tmp_path, "survival", _FD2_PLANT_BOTH)
    watch, flat, _, broker = _watch(planted)
    broker.reading = planted.BrokerReading(
        cash=50_000.0, net_liq=9_000.0, positions=poisoned, venue_ts=1.0
    )
    outcome = watch.reconcile("orphan")
    assert outcome.applied is True, outcome
    assert math.isnan(outcome.reading.floor) and outcome.breached is False, outcome
    assert flat.fired == [], flat.fired
    # PROTECTED: the same poll is refused, naming the field, and NOTHING is stored.
    watch, flat, _, broker = _watch(sur)
    broker.reading = sur.BrokerReading(
        cash=50_000.0, net_liq=9_000.0, positions=poisoned, venue_ts=1.0
    )
    with pytest.raises(sur.SurvivalWatchError) as red:
        watch.reconcile("orphan")
    assert "reconcile:orphan" in str(red.value), str(red.value)
    assert "sum_open_margin is nan" in str(red.value), str(red.value)
    with pytest.raises(sur.SurvivalNotReady):
        watch.read()


def test_FD2_the_FLOOR_CLAMPS_at_zero_per_SS7_483(tmp_path: Path) -> None:
    """A negative Σ open margin used to place the floor BELOW zero (§7:483)."""
    planted = _stage(tmp_path, "survival", [_FD2_UNCLAMP])
    watch, flat, _, _ = _watch(planted)
    out = watch.mark(cash=50_000.0, net_liq=-5_000.0, sum_open_margin=-10_000.0)
    # THE UNPROTECTED HALF: an account already underwater reads SAFE.
    assert out.reading.floor == pytest.approx(-11_000.0), out.reading.floor
    assert out.breached is False and flat.fired == [], out
    # PROTECTED: the clamp makes the floor 0.0, and a negative net-liq breaches it.
    watch, flat, _, _ = _watch(sur)
    out = watch.mark(cash=50_000.0, net_liq=-5_000.0, sum_open_margin=-10_000.0)
    assert out.reading.floor == 0.0, out.reading.floor
    assert out.breached and out.fired, out
    assert "net_liq" in flat.fired[0][1], flat.fired[0][1]
    # and the clamp is the IDENTITY on every legitimate input.
    watch, _, _, _ = _watch(sur)
    out = watch.mark(cash=1.0, net_liq=1.0, sum_open_margin=10_000.0)
    assert out.reading.floor == pytest.approx(11_000.0), out.reading.floor


def test_FD2_the_two_figures_are_read_through_two_DIFFERENT_verbs_SS15_C2() -> None:
    """I6 itself: with the floor BETWEEN them, cash and net-liq give OPPOSITE verdicts."""
    watch, flat, _, _ = _watch(sur)
    out = watch.mark(cash=100_000.0, net_liq=40_000.0, sum_open_margin=50_000.0)
    assert watch.sizing_liquidity() == 100_000.0, watch.sizing_liquidity()
    assert out.breached and out.fired, "the flatten must track NET-LIQ"
    watch, flat, _, _ = _watch(sur)
    out = watch.mark(cash=40_000.0, net_liq=100_000.0, sum_open_margin=50_000.0)
    assert watch.sizing_liquidity() == 40_000.0, watch.sizing_liquidity()
    assert not out.breached and flat.fired == [], "cash must NOT trigger the flatten"


# ---------------------------------------------------------------------------
# FD3 — `published_ts` is §12.7's FRESHNESS STAMP and was never validated
# ---------------------------------------------------------------------------


class _FakeMirror:
    def __init__(self, body: dict[str, object]) -> None:
        self._body = body

    @property
    def complete(self) -> bool:
        return True

    @property
    def missing(self) -> tuple[str, ...]:
        return ()

    def table(self, topic: str) -> dict[str, object]:
        del topic
        return dict(self._body)


class _FakeSubscriber:
    def __init__(self, body: dict[str, object]) -> None:
        self.mirror = _FakeMirror(body)

    def drain(self, timeout_ms: int) -> list[object]:
        del timeout_ms
        return []


_FD3_REPAIR = '            ("published_ts", picture.published_ts),\n'


def _body(module: ModuleType, published_ts: float) -> dict[str, object]:
    book = module.FinancialPictureBook(balance=10_000.0, deployable_fraction=FRACTION)
    snapshot = book.commit(
        balance=10_000.0, positions=(_row("T1", 500.0),), sum_reservations=0.0
    )
    encoded = module.encode_picture(snapshot)
    encoded["published_ts"] = published_ts
    return encoded


@pytest.mark.parametrize("stamp", [float("nan"), float("inf")])
def test_FD3_a_NON_FINITE_FRESHNESS_STAMP_cannot_make_a_mirror_ETERNALLY_TRADABLE(
    tmp_path: Path, stamp: float
) -> None:
    """`age = clock() - nan` is `nan`, and `nan > ceiling` is FALSE — forever.

    §12.7: *"freshness stamps ride each update"*; §6.4's rule for a stale cache
    is refuse. The staleness arm is the only thing standing between a consumer
    and sizing on an arbitrarily old picture, and one unvalidated field disabled
    it in the permissive direction.
    """
    planted = _stage(tmp_path, "picture", [(_FD3_REPAIR, "")])
    body = _body(planted, stamp)
    assert planted.picture_defects(planted.decode_picture(body), FRACTION) == ()
    mirror = planted.PictureMirror(
        _FakeSubscriber(body), max_age_s=0.5, fraction=FRACTION
    )
    ok, why = mirror.tradable()
    # THE UNPROTECTED HALF: permitted, and the reason itself is nonsense.
    assert ok is True, (ok, why)
    assert "age nans" in why or "age -infs" in why, why
    # PROTECTED: refused, naming the field.
    body = _body(pic, stamp)
    defects = pic.picture_defects(pic.decode_picture(body), FRACTION)
    assert any("published_ts is" in d for d in defects), defects
    mirror = pic.PictureMirror(_FakeSubscriber(body), max_age_s=0.5, fraction=FRACTION)
    ok, why = mirror.tradable()
    assert ok is False, (ok, why)
    assert "published_ts is" in why, why
    # CONTROL, without which "always refuses" would pass: an honest stamp permits.
    body = _body(pic, time.time())
    mirror = pic.PictureMirror(_FakeSubscriber(body), max_age_s=30.0, fraction=FRACTION)
    ok, why = mirror.tradable()
    assert ok is True, (ok, why)
    assert "age" in why and "version" in why, why


def test_FD3_the_PUBLISHER_also_refuses_a_non_finite_stamp() -> None:
    """The same predicate guards the wire, so the tear cannot leave the process."""
    book = pic.FinancialPictureBook(balance=10_000.0, deployable_fraction=FRACTION)
    good = book.commit(balance=10_000.0, positions=(), sum_reservations=0.0)
    torn = FinancialPicture(
        version=good.version + 1,
        published_ts=float("nan"),  # THE PLANT
        balance=good.balance,
        positions=good.positions,
        margin_per_contract=good.margin_per_contract,
        sum_open_margin=good.sum_open_margin,
        sum_reservations=good.sum_reservations,
        committed=good.committed,
        deployable=good.deployable,
    )
    with pytest.raises(pic.TornPicture) as red:
        book.publish(torn)
    assert "published_ts is nan" in str(red.value), str(red.value)


# ---------------------------------------------------------------------------
# FD4 — the codec's handler tuple, and a fast-drop verb that RAISED
# ---------------------------------------------------------------------------

_FD4_ROW = "except (KeyError, OverflowError, TypeError, ValueError) as exc:"
_FD4_PIC = (
    "except (AttributeError, KeyError, OverflowError, TypeError, ValueError) as exc:"
)


@pytest.mark.parametrize("key", ["version", "size"])
def test_FD4_an_INFINITE_int_on_the_wire_is_REFUSED_and_never_RAISES(
    tmp_path: Path, key: str
) -> None:
    """`int(float("inf"))` raises `OverflowError`, which is NOT a `ValueError`.

    `PictureMirror.tradable()` is §12.7's fast-drop verb and its docstring says
    *"Never raises"*. `json` both emits and parses `Infinity`, and D3.316
    measured that an `ipc://` bind is not exclusive — so an `Infinity` on this
    wire is reachable, and a fast-drop verb that raises does not fast-drop.
    """
    planted = _stage(
        tmp_path,
        "picture",
        [
            (_FD4_ROW, _FD4_ROW.replace("OverflowError, ", "")),
            (_FD4_PIC, _FD4_PIC.replace("OverflowError, ", "")),
        ],
    )
    for module, expect_raise in ((planted, True), (pic, False)):
        body = _body(module, time.time())
        if key == "version":
            body["version"] = float("inf")
        else:
            body["positions"][0]["size"] = float("inf")  # type: ignore[index]
        mirror = module.PictureMirror(
            _FakeSubscriber(body), max_age_s=60.0, fraction=FRACTION
        )
        if expect_raise:
            # THE UNPROTECTED HALF.
            with pytest.raises(OverflowError) as red:
                mirror.tradable()
            assert "cannot convert float infinity" in str(red.value), str(red.value)
        else:
            ok, why = mirror.tradable()
            assert ok is False, (ok, why)
            assert "OverflowError" in why, why
            assert "undecodable" in why, why


# ---------------------------------------------------------------------------
# I7 — a REAL reader PROCESS against a REAL publisher PROCESS, tears COUNTED
# ---------------------------------------------------------------------------

_PUBLISHER = r'''
import sys, time
sys.path.insert(0, {scripts!r})
from nixbus import statebus
from nixrisk import picture as P
from nixrisk.seam import PositionRow, PositionState

BASE, FRACTION, NROWS = 100_000.0, 0.70, 4
PLANT = {plant!r}

def world(g):
    rows = tuple(
        PositionRow(trade_id="T%d" % k, symbol="MESU6", strategy_id="s1", size=g,
                    margin=float(g * 1000 + k), state=PositionState.OPEN,
                    stop_distance=g)
        for k in range(NROWS))
    return BASE + g, rows, float(3 * g)

class CoherentTornSink:
    """The §0a PLANT: §3's hazard verbatim — balance from generation k, the table
    from k+1, every aggregate DERIVED from what was read. Perfectly
    self-consistent, and `picture_defects` says so."""
    def __init__(self, publisher):
        self._p, self.emitted, self._stale = publisher, 0, None
    def emit(self, pic):
        body = P.encode_picture(pic)
        if self._stale is not None:
            cmt = body["sum_open_margin"] + body["sum_reservations"]
            body["balance"] = self._stale
            body["committed"] = cmt
            body["deployable"] = max(0.0, FRACTION * self._stale - cmt)
        self._stale = pic.balance
        self._p.publish(P.TOPIC, body)
        self.emitted += 1

endpoint = sys.argv[1]
gens = int(sys.argv[2])
pub = statebus.StatePublisher(endpoint)
sink = CoherentTornSink(pub) if PLANT else P.StateBusPictureSink(pub)
book = P.FinancialPictureBook(balance=BASE, deployable_fraction=FRACTION, sink=sink)
deadline = time.monotonic() + 20.0
while time.monotonic() < deadline and pub.subscribes_seen == 0:
    pub.service(50)
bal, rows, res = world(1)
book.commit(balance=bal, positions=rows, sum_reservations=res)
for _ in range(20):
    pub.refresh_all(); pub.service(1)
try:
    for g in range(2, gens + 2):
        bal, rows, res = world(g)
        book.commit(balance=bal, positions=rows, sum_reservations=res)
        pub.service(0)
finally:
    pub.close()
'''

_BASE = 100_000.0
_NROWS = 4


def _true_derived(g: int) -> tuple[float, float, float, float, float]:
    som = float(sum(g * 1000 + k for k in range(_NROWS)))
    res = float(3 * g)
    cmt = som + res
    bal = _BASE + g
    return bal, som, res, cmt, max(0.0, FRACTION * bal - cmt)


def _identity_defects(snapshot: FinancialPicture) -> list[str]:
    """Every way ONE decoded snapshot fails the generation identity.

    THE IDENTITY: generation `g` is stamped into BOTH halves — `balance` is
    `BASE + g`, every row carries `margin = g*1000+k`, `size = g` and
    `stop_distance = g`, and `sum_reservations` is `3g`. So a snapshot assembled
    from two generations violates arithmetic and is COUNTED, never eyeballed.
    This is what `picture_defects` provably cannot do (its own docstring), which
    is why the detector is here and not borrowed from the subject.
    """
    out: list[str] = []
    offset = snapshot.balance - _BASE
    if offset != int(offset):
        return [f"balance {snapshot.balance!r} is not BASE + an integer generation"]
    g = int(offset)
    for row in snapshot.positions:
        for axis, carried in (
            ("margin", int(row.margin) // 1000),
            ("size", row.size),
            ("stop_distance", row.stop_distance),
        ):
            if carried != g:
                out.append(
                    f"TORN {axis}: balance carries generation {g} but row "
                    f"{row.trade_id} carries {carried}"
                )
    if snapshot.sum_reservations != 3 * g:
        out.append(
            f"TORN sum_reservations: generation {g} but "
            f"sum_reservations={snapshot.sum_reservations!r}"
        )
    _, som, _, cmt, dep = _true_derived(g)
    for field, got, want in (
        ("sum_open_margin", snapshot.sum_open_margin, som),
        ("committed", snapshot.committed, cmt),
        ("deployable", snapshot.deployable, dep),
    ):
        if abs(got - want) > 1e-9:
            out.append(
                f"HEADROOM CONSEQUENCE: {field}={got!r} but generation {g}'s true "
                f"value is {want!r} (delta {got - want:+.9g})"
            )
    return out


def _cross_process_race(tmp_path: Path, *, plant: bool, gens: int) -> dict[str, object]:
    """One publisher PROCESS, one reader (this one), one real `ipc://` socket."""
    root = tmp_path / f"bus{os.getpid()}"
    root.mkdir(parents=True, exist_ok=True)
    endpoint = statebus.endpoint_for(f"arc038d{os.getpid()}", root=root)
    driver = tmp_path / f"pub_{int(plant)}.py"
    driver.write_text(_PUBLISHER.format(scripts=str(REPO / "scripts"), plant=plant))
    # D3.344: the child's environment is NAMED, never inherited.
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "scripts")
    child = subscriber = None
    try:
        child = subprocess.Popen(
            [sys.executable, str(driver), endpoint, str(gens)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        time.sleep(0.5)
        subscriber = statebus.StateSubscriber(endpoint, [pic.TOPIC])
        seen = 0
        generations: set[int] = set()
        versions: set[int] = set()
        identity: list[str] = []
        production: list[str] = []
        errors: list[str] = []
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            messages = subscriber.drain(200)
            for message in messages:
                try:
                    snapshot = pic.decode_picture(message.payload)
                except pic.PictureError as exc:
                    errors.append(str(exc))
                    continue
                seen += 1
                versions.add(snapshot.version)
                generations.add(int(snapshot.balance - _BASE))
                identity.extend(_identity_defects(snapshot))
                production.extend(pic.picture_defects(snapshot, FRACTION))
            if len(generations) >= gens:
                break
            if child.poll() is not None and not messages:
                break
        return {
            "messages": seen,
            "generations": len(generations),
            "versions": len(versions),
            "bytes": subscriber.bytes_received,
            "identity_tears": identity,
            "production_defects": production,
            "decode_errors": errors,
            "out_of_order": subscriber.mirror.out_of_order,
            "child_rc": child.poll(),
        }
    finally:
        if subscriber is not None:
            subscriber.close()
        if child is not None:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=15)
            if child.stderr is not None:
                child.stderr.close()
        shutil.rmtree(root, ignore_errors=True)


def test_I7_a_REAL_reader_PROCESS_never_observes_a_TORN_picture(
    tmp_path: Path,
) -> None:
    """The measured arm and its can-fail, both over a real process boundary.

    The PLANT runs first (ARC 035's rule): a publisher emitting §3's COHERENT
    tear must produce COUNTED violations through this exact harness, or a clean
    sheet from the subject proves nothing. `picture_defects` is required to see
    NOTHING under that plant, which is the measurement that the identity — not
    the production predicate — is what has power here.
    """
    plantted = _cross_process_race(tmp_path, plant=True, gens=MIN_GENERATIONS)
    assert plantted["generations"] >= MIN_GENERATIONS, plantted
    assert len(plantted["identity_tears"]) > 0, (
        "the coherent-tear plant produced NO counted tear — this harness cannot "
        f"see §3's tear and the measured arm below is vacuous: {plantted}"
    )
    assert plantted["production_defects"] == [], (
        "`picture_defects` fired on the COHERENT tear; its documented blind spot "
        "has closed and this suite's identity is no longer the only detector "
        f"with power: {plantted['production_defects'][:3]}"
    )
    sample = plantted["identity_tears"][0]
    assert "TORN" in sample or "HEADROOM CONSEQUENCE" in sample, sample

    measured = _cross_process_race(tmp_path, plant=False, gens=MIN_GENERATIONS)
    assert measured["generations"] >= MIN_GENERATIONS, measured
    assert measured["bytes"] > 0, measured
    assert measured["identity_tears"] == [], measured["identity_tears"][:3]
    assert measured["production_defects"] == [], measured["production_defects"][:3]
    assert measured["decode_errors"] == [], measured["decode_errors"][:2]
    assert measured["out_of_order"] == 0, measured["out_of_order"]


def test_I7_a_SECOND_WRITER_is_refused_and_leaves_NO_half_published_picture() -> None:
    """Real threads in `commit()` at once: the guard fires and nothing tears.

    The residual is stated rather than glossed: `_writing` is a non-atomic
    check-then-set, so the absence of a duplicate version stamp below is a
    measurement under this interpreter's GIL and not a proof under a
    free-threaded build. What IS proven is that no picture reaching the sink was
    ever incoherent and that `current()` matches the last one published.
    """
    import threading  # pylint: disable=import-outside-toplevel

    bodies: list[dict[str, object]] = []
    lock = threading.Lock()

    class _Sink:
        def emit(self, picture: FinancialPicture) -> None:
            body = pic.encode_picture(picture)
            with lock:
                bodies.append(body)

    book = pic.FinancialPictureBook(
        balance=_BASE, deployable_fraction=FRACTION, sink=_Sink()
    )
    refusals: list[str] = []
    barrier = threading.Barrier(4)

    def writer(tid: int) -> None:
        barrier.wait()
        for k in range(1_500):
            g = tid * 1_000_000 + k + 1
            balance, som, res, _, _ = _true_derived(g)
            rows = tuple(
                PositionRow(
                    trade_id=f"T{i}",
                    symbol="MESU6",
                    strategy_id="s1",
                    size=g,
                    margin=float(g * 1000 + i),
                    state=PositionState.OPEN,
                    stop_distance=g,
                )
                for i in range(_NROWS)
            )
            del som
            try:
                book.commit(balance=balance, positions=rows, sum_reservations=res)
            except pic.ConcurrentWriter as exc:
                refusals.append(str(exc))

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert refusals, "no second writer was ever refused — this arm did not race"
    assert "SOLE writer" in refusals[0], refusals[0]
    assert book.commits + len(refusals) == 4 * 1_500, (book.commits, len(refusals))
    tears: list[str] = []
    versions: list[int] = []
    for body in bodies:
        snapshot = pic.decode_picture(body)
        versions.append(snapshot.version)
        tears.extend(_identity_defects(snapshot))
        tears.extend(pic.picture_defects(snapshot, FRACTION))
    assert tears == [], tears[:3]
    assert len(versions) == len(set(versions)), "a version stamp was published twice"
    assert book.current().version == versions[-1], (
        book.current().version,
        versions[-1],
    )
