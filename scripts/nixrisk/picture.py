"""§3's ONE atomic financial-picture snapshot, and §12.7's transport for it.

Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §3 (*FULL FINANCIAL-PICTURE
PUBLISH* and its **ATOMICITY RULE**), §11.3–§11.4 (running aggregates, deployable
precomputed on account-state change), §12.7 (*Cache distribution & restart
rebuild — state-table transport*, LOCKED v1.3). The types are the FROZEN
`scripts/nixrisk/seam.py`; nothing here re-declares them.

§3, verbatim, because the sentence is the whole design:

> ATOMICITY RULE: balance and the position table publish together as one
> snapshot — never two separate reads — so the Allocator can never compute
> headroom off a stale balance + fresh commitment (or vice versa).

---

## HOW ATOMICITY IS OBTAINED, AND WHY IT IS A PROPERTY RATHER THAN A DISCIPLINE

`FinancialPictureBook`'s ENTIRE state is one immutable `FinancialPicture`. There
is no `self._balance` and no `self._positions`; there is `self._current`, and a
mutation builds a whole new picture and rebinds that one name. So:

* a reader does **one attribute load** and walks away holding a complete,
  self-consistent object. There is no window in which balance is new and the
  position table is old, because at no instant do the two live in separate
  places a reader could visit separately;
* the object it holds is a frozen dataclass over a tuple and a mapping proxy, so
  the writer cannot mutate it out from under the reader afterwards either.

This is the §8 rule — *"single-writer, lock-free readers (ring buffer / seqlock)
— no torn reads"* — obtained without a seqlock, because immutability plus a
single pointer swap needs no version-parity dance. There is no lock, and there
must not be one: §11 makes the entry pathway *"cache reads + arithmetic only"*,
and a mutex on `current()` puts an unbounded wait on the hot path.

**What that costs, stated rather than implied.** A read-modify-write on
`_current` is NOT atomic against a second WRITER. That is safe here and only
here, because §9 and §12.10 make the Limiter the sole writer and §5 makes it a
single-threaded loop. `commit()` therefore refuses re-entry (`_writing`) rather
than serialising: a second writer is a design violation, and a lock would make
it work quietly instead of failing loudly.

---

## THE DERIVED FIELDS ARE DERIVED HERE, ONCE

§3 publishes `Σ open margin · Σ reservations · committed · uncommitted
(deployable)`. Three of the four are functions of the other fields, and a
publisher that let a caller pass them in would be publishing a snapshot whose
own arithmetic could disagree with itself — which is a torn read that never
crossed a version boundary. `commit()` accepts only INPUTS (balance, the
position table, Σ reservations, the margin cache) and derives the rest.

**`deployable` — D3.42, answered.** `checks/../gate.py`'s `DeployableCeilingRule`
records that §3 lists `committed + proposed < 70% × balance` and *"buffer/
deployable ceiling fit"* as two bullets while describing the published figure
only as *"uncommitted (deployable) liquidity"*, and that the publisher owns the
choice. **This publisher chooses `deployable = max(0, fraction × balance −
committed)`** — §3's own headroom arithmetic (*"headroom_$ = 0.70 × balance −
COMMITTED"*, with the Allocator's `clamp ≥ 0`), so the Allocator's pre-size and
the Limiter's ceiling read the same number rather than two definitions of one
word. The consequence is written down and not glossed: under this definition
`DeployableCeilingRule` cannot be the binding constraint, and D3.42 records that
retiring one of the two bullets is now a decision an arc can take **with a
measurement**.

---

## WHAT THIS MODULE IS NOT

It is not a second transport. §12.7's bus is `scripts/nixbus/statebus.py`, built
and gated in ARC 026; `StateBusPictureSink` is a thin adapter that turns one
picture into one wire message on that bus. It is not the Allocator, it does not
size, and it takes no reservation — `scripts/nixrisk/reservations.py` owns Σ
reservations and this module receives the figure it maintains.

**Explicitly not in this arc, and no green here may be read as covering them:**
stop conversion and trailing maintenance, protective-exit wiring to
broker-order, session-close flatten, full HALT semantics and auto-clear,
cold-start reconciliation, the Sentinel, Scoring, the Allocator. A Limiter that
publishes a correct picture but cannot exit is not a safety spine yet.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable, Mapping
from types import MappingProxyType
from typing import Any, Final, Protocol

from nixrisk.seam import FinancialPicture, PositionRow, PositionState

# R0903 (too-few-public-methods): `PictureSink` is a single-verb Protocol — a
# DECLARATION with exactly the surface §12.7 gives it. A second method would be a
# sink doing two jobs.
# pylint: disable=too-few-public-methods

#: §3:131's fraction. NO DEFAULT IS APPLIED SILENTLY anywhere below — this is the
#: value §12A owns and `FinancialPictureBook` requires it explicitly, for the
#: same reason `AggregateMarginCapRule` does: a cap with a default is a cap
#: nobody chose.
SPEC_DEPLOYABLE_FRACTION: Final[float] = 0.70

#: Which position states contribute to Σ OPEN margin, and why the other three do
#: not. §3: a reservation is *"taken at approval → released on: fill (converts to
#: open-margin)"*, and `committed = Σ open margin + Σ PENDING RESERVATIONS`. So a
#: RESERVED or PENDING row's margin is already counted by Σ reservations, and
#: counting it here as well would DOUBLE-count it — inflating `committed`, which
#: is the safe direction, but making the published `committed` disagree with
#: `PictureCoherenceRule`'s reconstruction of it and denying every entry. CLOSED
#: contributes nothing because the margin is returned.
OPEN_MARGIN_STATES: Final[frozenset[PositionState]] = frozenset(
    {PositionState.OPEN, PositionState.CLOSING}
)

#: Float slack for the coherence predicate. Same order as
#: `reservations.AUDIT_TOLERANCE` and for the same reason: below this a
#: disagreement between a running aggregate and a full re-derivation is binary
#: representation, not a lost commitment.
COHERENCE_TOLERANCE: Final[float] = 1e-9

#: The state-bus topic the financial picture publishes under. One table, one
#: topic; §12.7's mirror model keys on it and `Mirror.required` names it.
TOPIC: Final[str] = "tbl.financial_picture"

#: Wire schema stamp. Rides every message so a consumer that mirrors a shape it
#: does not understand says so instead of reading fields positionally.
#:
#: **Spelled `schema` and NOT `_schema`, and that was found by measurement.** The
#: first spelling was `_schema`, and `statebus._decode` strips EVERY `_`-prefixed
#: key out of the payload before the mirror ever sees it — deliberately, so that
#: transport bookkeeping (`_seq`, `_stamp`, `_kind`) cannot masquerade as owner
#: state. The result was a subscriber that took 18.9 MB off the wire and decoded
#: exactly zero pictures, which the gate reported as CANNOT_MEASURE rather than
#: as agreement. A leading underscore on this wire is the transport's namespace,
#: not ours.
#:
#: **BUMPED 1 -> 2 by ARC 032**, in the same edit that put `stop_distance` on
#: `PositionRow`. The bump is not bookkeeping: `_decode_row` requires the key,
#: so a version-1 body decoded by this code would raise `PictureError` naming a
#: missing key rather than naming the schema. Bumping makes the refusal say the
#: true thing — *this consumer does not understand that shape* — at the one
#: place a consumer can act on it, which is the whole reason the stamp exists.
WIRE_SCHEMA: Final[int] = 2


class PictureError(RuntimeError):
    """A financial-picture operation was refused. Always says what and why."""


class ConcurrentWriter(PictureError):
    """A second writer entered `commit`. §9/§12.10: the Limiter is SOLE writer.

    Raised rather than serialised. A lock here would make a second writer work
    quietly, and the whole single-writer guarantee — the thing §12.7 says raw
    shared state tables *"reduce to fiction"* — would be gone with no event.
    """


class TornPicture(PictureError):
    """A picture whose own fields disagree. Carries every disagreement found."""


class PictureSink(Protocol):
    """Where one published snapshot goes. §12.7's outward half, and nothing more."""

    def emit(self, picture: FinancialPicture) -> None:
        """Put ONE self-consistent snapshot on the wire. One version, one write."""


# ---------------------------------------------------------------------------
# The coherence predicate — the detector every atomicity control stands on
# ---------------------------------------------------------------------------


def _finite(name: str, value: float) -> str:
    """`""` when `value` is a real number; else why it is not publishable."""
    if math.isnan(value) or math.isinf(value):
        return f"{name} is {value!r} — a snapshot carrying NaN/Inf gates money on it"
    return ""


def _derived_defects(picture: FinancialPicture, fraction: float) -> list[str]:
    """Disagreements between a picture's derived fields and its own inputs."""
    open_margin = sum(
        row.margin for row in picture.positions if row.state in OPEN_MARGIN_STATES
    )
    committed = picture.sum_open_margin + picture.sum_reservations
    deployable = max(0.0, fraction * picture.balance - picture.committed)
    checks = (
        ("sum_open_margin", picture.sum_open_margin, open_margin, "Σ over the rows"),
        ("committed", picture.committed, committed, "Σ open margin + Σ reservations"),
        ("deployable", picture.deployable, deployable, f"max(0, {fraction:g}×bal−cmt)"),
    )
    return [
        f"{field}={published!r} but {how} = {expected!r} "
        f"(drift {published - expected:+.9g}, picture version {picture.version})"
        for field, published, expected, how in checks
        if abs(published - expected) > COHERENCE_TOLERANCE
    ]


def picture_defects(
    picture: FinancialPicture, fraction: float = SPEC_DEPLOYABLE_FRACTION
) -> tuple[str, ...]:
    """Every way this ONE snapshot disagrees with itself. Empty = self-consistent.

    **This is the torn-read detector**, and it is a function of a SINGLE picture
    on purpose: §3's hazard is a consumer computing headroom from fields that
    were never simultaneously true, and the observable signature of that is a
    snapshot whose derived fields do not follow from the inputs beside them. A
    detector that needed two observations to fire could not tell a tear from a
    legitimate update between them.

    It is deliberately in production code rather than in a gate: the Limiter can
    refuse to publish a picture that fails it, and `gate.PictureCoherenceRule`
    already denies on one of the three arms at evaluation time.

    ------------------------------------------------------------------------
    WHAT IT CANNOT SEE, AND IT IS THE TEAR §3 ACTUALLY NAMES
    ------------------------------------------------------------------------
    §3's hazard is *"headroom off a stale balance + fresh commitment"*. A
    publisher that reads balance at generation *k*, reads the position table at
    *k+1*, and then derives Σ open margin, `committed` and `deployable` from
    what it read produces a snapshot that passes **every predicate here**: the
    derived fields follow perfectly from the inputs beside them, and `balance`
    is an INDEPENDENT input that nothing else in the snapshot constrains. One
    snapshot simply does not carry the information.

    So this predicate catches the *incoherent* tear — a publisher that refreshes
    some derived fields and not others — and cannot catch the *coherent* one.
    The coherent tear is only observable against knowledge of what the writer's
    world looked like, which is why the atomicity instrument
    (`checks/check_picture_atomicity.py`) plants a GENERATION LINK between
    balance and every row's margin and requires one generation per snapshot. A
    gate that ran only this predicate under concurrency would race hard, observe
    nothing, and pass.
    """
    defects = [
        note
        for name, value in (
            ("balance", picture.balance),
            ("sum_open_margin", picture.sum_open_margin),
            ("sum_reservations", picture.sum_reservations),
            ("committed", picture.committed),
            ("deployable", picture.deployable),
            # ARC 038 / sub-agent D, finding FD3. `published_ts` was the ONE
            # field the sweep omitted, and it is §12.7's *"freshness stamps ride
            # each update"* — the whole of `PictureMirror.tradable()`'s staleness
            # arm. MEASURED: with `published_ts = nan`, `age = clock() - nan` is
            # `nan`, `nan > max_age_s` is **False**, and the mirror reported
            # `(True, "picture version 2, age nans")` FOREVER; with `+inf` the
            # age is `-inf` and it reported tradable forever too. A stamp that
            # cannot be compared is not a freshness stamp, and §6.4's rule for a
            # stale cache is refuse — so a non-finite one is a defect here, at
            # the one place both the publisher's refusal and the consumer's
            # fast-drop already read.
            ("published_ts", picture.published_ts),
        )
        if (note := _finite(name, value))
    ]
    seen: set[str] = set()
    for row in picture.positions:
        if row.trade_id in seen:
            defects.append(
                f"trade_id {row.trade_id!r} appears twice — §3 keys the position "
                "table BY trade_id, and a table with two rows for one key is not "
                "keyed by it"
            )
        seen.add(row.trade_id)
    if picture.version <= 0:
        defects.append(
            f"version={picture.version!r} — the version stamp is what makes a torn "
            "read observable from outside, so an unset one is not publishable"
        )
    defects.extend(_derived_defects(picture, fraction))
    return tuple(defects)


# ---------------------------------------------------------------------------
# The book (§3, §11.3, §11.4, §12.7's owner half)
# ---------------------------------------------------------------------------


class FinancialPictureBook:  # pylint: disable=too-many-instance-attributes
    # Eight attributes, and four of them are COUNTERS (`commits`, `publishes`,
    # `refusals`, plus the re-entry flag). They exist for the reason
    # `StatePublisher`'s four do: a publisher that cannot say what it published
    # cannot be measured, only believed. The threshold is about behavioural
    # classes accreting state; these are the observables the gate reads.
    """The Limiter's OWN table (§12.7 mirror model). Satisfies `FinancialPicturePort`.

    Single writer by construction and by refusal: the table lives in this
    object's memory, consumers receive copies over the bus, and there is no verb
    by which a consumer can write back.

    `publishes`, `commits` and `refusals` are counters for the same reason
    `StatePublisher`'s four are: a publisher that cannot say what it published
    cannot be measured, only believed.
    """

    def __init__(
        self,
        *,
        balance: float,
        deployable_fraction: float,
        sink: PictureSink | None = None,
        margin_per_contract: Mapping[str, float] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not 0.0 < deployable_fraction <= 1.0:
            raise PictureError(
                f"deployable fraction must be in (0, 1], got {deployable_fraction!r} "
                "— §3:131's 0.70; §12A owns the value and this class takes no default"
            )
        self._fraction = float(deployable_fraction)
        self._sink = sink
        self._clock = clock
        self._writing = False
        self.commits = 0
        self.publishes = 0
        self.refusals = 0
        self._current = self._build(
            version=1,
            balance=float(balance),
            positions=(),
            margin_per_contract=dict(margin_per_contract or {}),
            sum_reservations=0.0,
        )

    # -- the port ---------------------------------------------------------

    def current(self) -> FinancialPicture:
        """The Limiter's own copy — ONE attribute load, and that is the mechanism.

        §11.3 makes every gate check O(1); this is O(1) in the literal sense of
        a single `LOAD_ATTR`. A reader never sees a half-built table because a
        half-built table is never bound to this name.
        """
        return self._current

    def publish(self, picture: FinancialPicture) -> None:
        """Put ONE self-consistent snapshot on the wire (§3, §12.7).

        REFUSES an incoherent picture rather than sending it. §12.7's consumers
        treat an incomplete mirror as stale and fast-drop; they have no defence
        at all against a mirror that arrived complete and wrong.

        SECOND REFUSAL — ARC 041 (I7, D3.386). What goes on the wire must be the
        picture this book CURRENTLY HOLDS, and identity is the check: §3:162's
        atomicity rule is *"balance and the position table publish together as
        one snapshot ... every consumer reads a self-consistent picture"*, and a
        consumer's mirror is only self-consistent WITH THE WRITER if the writer
        emitted its own canonical state rather than some other object that
        happens to be internally coherent. A picture can pass every
        `picture_defects` test and still be the WRONG one — an older version, or
        a foreign object built elsewhere — and §12.7's mirror has no defence
        against a snapshot that arrived complete and stale.

        The two refusals are ORDERED defects-first deliberately: a caller handing
        in a defective foreign picture gets told WHICH FIELD is wrong, which is
        the more actionable reason, and the identity refusal then catches the
        clean-but-not-ours case that the defect scan cannot see by construction.
        """
        defects = picture_defects(picture, self._fraction)
        if defects:
            self.refusals += 1
            raise TornPicture(
                f"refusing to publish version {picture.version}: " + "; ".join(defects)
            )
        if picture is not self._current:
            self.refusals += 1
            raise TornPicture(
                f"refusing to publish version {picture.version}: this book holds "
                f"version {self._current.version}, so the argument is NOT the "
                "canonical state. §3:162 has balance and the position table "
                "publish together as ONE snapshot and every consumer read a "
                "self-consistent picture; emitting a picture this writer does "
                "not hold puts a mirror out of step with the book it mirrors, "
                "and §12.7's freshness stamp cannot detect it because the "
                "snapshot is complete and internally coherent"
            )
        if self._sink is not None:
            self._sink.emit(picture)
        self.publishes += 1

    # -- the writer -------------------------------------------------------

    def commit(
        self,
        *,
        balance: float | None = None,
        positions: Iterable[PositionRow] | None = None,
        margin_per_contract: Mapping[str, float] | None = None,
        sum_reservations: float | None = None,
    ) -> FinancialPicture:
        """Apply changes as ONE version and publish it. The whole atomicity story.

        Every argument left `None` carries forward. Whatever the caller changes,
        the balance and the position table advance together under one version
        stamp: there is no verb on this object that moves one without the other.
        """
        if self._writing:
            self.refusals += 1
            raise ConcurrentWriter(
                "a second writer entered commit() — §9 and §12.10 make the "
                "Limiter the SOLE writer of this table and §5 makes it a "
                "single-threaded loop, so this is a design violation and is "
                "refused rather than serialised behind a lock"
            )
        self._writing = True
        try:
            picture = self._next(
                balance, positions, margin_per_contract, sum_reservations
            )
            # ARC 038 / sub-agent D, finding FD1. VALIDATE BEFORE THE STORE.
            #
            # This check used to live only in `publish()`, which runs AFTER the
            # store below — so a refused publish still advanced `_current`, and
            # the Limiter's OWN table was left holding the picture it had just
            # declared unpublishable while the mirror kept the last good one.
            # MEASURED end to end: `commit(sum_reservations=float("-inf"))` on a
            # $10,000 account left `current()` at `committed=-inf`,
            # `deployable=inf`, and the full §3 `GatePass` then **APPROVED 800
            # contracts / $400,000 of margin** where the same order against the
            # healthy picture was SIZE_DOWN to 12 by `aggregate_margin_cap`. A
            # NaN balance instead left `deployable=0.0` and made `_largest_fit`
            # raise. Directive 4 and §17: a refusal must not mutate the state it
            # refused, and the mirror and the own table must not diverge.
            defects = picture_defects(picture, self._fraction)
            if defects:
                self.refusals += 1
                raise TornPicture(
                    f"refusing to commit version {picture.version}: "
                    + "; ".join(defects)
                    + " — the previous picture (version "
                    f"{self._current.version}) STANDS; a refused commit does not "
                    "advance the Limiter's own table"
                )
            self._current = picture  # <- THE single store. Atomicity lives here.
            self.commits += 1
            # ARC 041 / I7, CHECK-DEBT D3.386. THE PUBLISH IS INSIDE THE GUARD.
            #
            # It used to sit after the `finally` below, so `self._writing` was
            # already False when the sink ran and a sink that called back into
            # `commit()` was NOT refused. MEASURED on this tree before the
            # change, with a sink whose `emit` re-enters: no `ConcurrentWriter`
            # was raised and the wire received **[3, 2]** — the inner commit's
            # version 3 reached the sink BEFORE the outer's version 2. A mirror
            # applying wire order ends holding v2 while the book holds v3, and
            # nothing detects it: the transport `_seq` is monotone by
            # construction so it rises across both sends, and
            # `picture_defects()` is empty on both because each picture is
            # internally coherent. §9/§12.10 make the Limiter the SOLE writer
            # and §5 makes it a single-threaded loop, so a re-entrant commit is
            # a design violation and §17's fail-closed answer is to REFUSE IT BY
            # NAME rather than to serialise it quietly behind a lock.
            #
            # WHAT THIS DOES NOT CHANGE, stated because ARC 038 named it as the
            # cost of this repair: the STORE still precedes the PUBLISH exactly
            # as before, so a sink/transport failure still leaves `_current`
            # advanced with nothing on the wire. That was already true when
            # `publish` sat outside the guard — moving it inside changes WHO MAY
            # RE-ENTER, not the order of the two operations — and the designed
            # degradation for it is §12.7's: the mirror goes stale and consumers
            # fast-drop. Making a transport failure roll the book back is a
            # different and larger ruling; it is recorded, not taken here.
            self.publish(picture)
        finally:
            self._writing = False
        return picture

    def _next(
        self,
        balance: float | None,
        positions: Iterable[PositionRow] | None,
        margin_per_contract: Mapping[str, float] | None,
        sum_reservations: float | None,
    ) -> FinancialPicture:
        """Build the next picture from the current one plus the changes."""
        previous = self._current
        return self._build(
            version=previous.version + 1,
            balance=previous.balance if balance is None else float(balance),
            positions=(previous.positions if positions is None else tuple(positions)),
            margin_per_contract=(
                dict(previous.margin_per_contract)
                if margin_per_contract is None
                else dict(margin_per_contract)
            ),
            sum_reservations=(
                previous.sum_reservations
                if sum_reservations is None
                else float(sum_reservations)
            ),
        )

    def _build(
        self,
        *,
        version: int,
        balance: float,
        positions: tuple[PositionRow, ...],
        margin_per_contract: dict[str, float],
        sum_reservations: float,
    ) -> FinancialPicture:
        """Derive §3's four aggregates and freeze the lot into one snapshot."""
        sum_open_margin = sum(
            row.margin for row in positions if row.state in OPEN_MARGIN_STATES
        )
        committed = sum_open_margin + sum_reservations
        return FinancialPicture(
            version=version,
            published_ts=self._clock(),
            balance=balance,
            positions=positions,
            margin_per_contract=MappingProxyType(margin_per_contract),
            sum_open_margin=sum_open_margin,
            sum_reservations=sum_reservations,
            committed=committed,
            deployable=max(0.0, self._fraction * balance - committed),
        )


# ---------------------------------------------------------------------------
# The wire (§12.7) — one picture, one message, one version
# ---------------------------------------------------------------------------


def encode_picture(picture: FinancialPicture) -> dict[str, Any]:
    """One picture -> one JSON-able body. EVERY field, or none of them.

    There is no partial encoding and no second message. §3's atomicity rule is a
    statement about what a consumer can observe, so a codec that split the
    position table into its own topic would satisfy every test in this file and
    break the rule on the wire.
    """
    return {
        "schema": WIRE_SCHEMA,
        "version": picture.version,
        "published_ts": picture.published_ts,
        "balance": picture.balance,
        "positions": [
            {
                "trade_id": row.trade_id,
                "symbol": row.symbol,
                "strategy_id": row.strategy_id,
                "size": row.size,
                "margin": row.margin,
                "state": row.state.value,
                # ARC 032 / SEAM_REV 1.1.0. On the SAME message as balance and
                # the rest — §7:501 needs it to price a held position and §6.4
                # forbids a second table, so it rides here or it skews.
                "stop_distance": row.stop_distance,
            }
            for row in picture.positions
        ],
        "margin_per_contract": dict(picture.margin_per_contract),
        "sum_open_margin": picture.sum_open_margin,
        "sum_reservations": picture.sum_reservations,
        "committed": picture.committed,
        "deployable": picture.deployable,
    }


def _decode_row(raw: Mapping[str, Any]) -> PositionRow:
    """One wire row -> one `PositionRow`. Raises `PictureError`, never KeyError."""
    try:
        return PositionRow(
            trade_id=str(raw["trade_id"]),
            symbol=str(raw["symbol"]),
            strategy_id=str(raw["strategy_id"]),
            size=int(raw["size"]),
            margin=float(raw["margin"]),
            state=PositionState(raw["state"]),
            # `raw["stop_distance"]` and NOT `raw.get("stop_distance", 0)`:
            # a defaulted decode would turn a version-1 body into a picture
            # whose held positions price at zero dollar risk, which is D3.136's
            # fail-open reintroduced by the codec. Missing key -> KeyError ->
            # PictureError, and the mirror stays STALE rather than sizing on a
            # table it invented.
            stop_distance=int(raw["stop_distance"]),
        )
    # `OverflowError` is in the tuple and was ADDED BY MEASUREMENT (ARC 038 /
    # sub-agent D, finding FD4): `int(float("inf"))` raises `OverflowError`,
    # which is an `ArithmeticError` and NOT a `ValueError`, so a wire body
    # carrying `"size": Infinity` — which `json` both emits and parses — escaped
    # this handler, escaped `decode_picture`, and came out of
    # `PictureMirror.tradable()`, a verb whose docstring says *"Never raises"*
    # and whose whole job is to DENY. A fast-drop verb that raises does not
    # fast-drop.
    except (KeyError, OverflowError, TypeError, ValueError) as exc:
        raise PictureError(f"undecodable position row {raw!r}: {exc!r}") from exc


def decode_picture(payload: Mapping[str, Any]) -> FinancialPicture:
    """One wire body -> one picture. A shape it does not understand is refused."""
    schema = payload.get("schema")
    if schema != WIRE_SCHEMA:
        raise PictureError(
            f"wire schema {schema!r} is not {WIRE_SCHEMA} — a consumer that read "
            "an unknown shape positionally would mirror a table it invented"
        )
    try:
        rows = tuple(_decode_row(raw) for raw in payload["positions"])
        return FinancialPicture(
            version=int(payload["version"]),
            published_ts=float(payload["published_ts"]),
            balance=float(payload["balance"]),
            positions=rows,
            margin_per_contract=MappingProxyType(
                {str(k): float(v) for k, v in payload["margin_per_contract"].items()}
            ),
            sum_open_margin=float(payload["sum_open_margin"]),
            sum_reservations=float(payload["sum_reservations"]),
            committed=float(payload["committed"]),
            deployable=float(payload["deployable"]),
        )
    # `OverflowError` — see `_decode_row`. MEASURED on `"version": Infinity`.
    except (AttributeError, KeyError, OverflowError, TypeError, ValueError) as exc:
        raise PictureError(f"undecodable financial picture: {exc!r}") from exc


class StateBusPictureSink:
    """§12.7's transport, bound to §3's table. A thin adapter, deliberately.

    It holds a `nixbus.statebus.StatePublisher` and does exactly one thing with
    it: turn one picture into one `publish(TOPIC, body)`. It does NOT own a
    second bus, a second topic, or a delta encoding — a delta would let a late
    subscriber mirror a table assembled from fragments that were never
    simultaneously true, which is §3's hazard moved onto the wire.

    Snapshot-on-subscribe is the publisher's, not this adapter's:
    `StatePublisher.service()` re-sends the whole stored table on every
    subscription (with `XPUB_VERBOSE`, on every subscription and not merely the
    first). The owner's loop must call it — see `service`.
    """

    def __init__(self, publisher: Any, topic: str = TOPIC) -> None:
        self._publisher = publisher
        self.topic = topic
        self.emitted = 0

    def emit(self, picture: FinancialPicture) -> None:
        """One picture, one wire message, one version stamp."""
        self._publisher.publish(self.topic, encode_picture(picture))
        self.emitted += 1

    def service(self, timeout_ms: int = 0) -> int:
        """Answer pending subscriptions with a full snapshot (§12.7). Mandatory."""
        return int(self._publisher.service(timeout_ms))


class PictureMirror:
    """A consumer's PRIVATE read-only mirror of §3's table, and its stale rule.

    §12.7: *"mirror incomplete ⇒ treated as stale ⇒ fast-drop/deny until snapshot
    lands"*, and *"it never sizes on a half-built mirror"*. `tradable()` is that
    sentence as a verb, and it FAILS CLOSED in every direction it can:

    * no snapshot yet ⇒ deny, naming the missing topic;
    * a body this consumer cannot decode ⇒ deny, naming the decode error;
    * a decoded picture that disagrees with itself ⇒ deny, naming the field
      (`picture_defects`);
    * a picture older than `max_age_s` ⇒ deny, naming the age. §12.7 says
      *"freshness stamps ride each update"* and §6.4's standing rule for a stale
      cache is halt, not "carry on with the last value".
    """

    def __init__(
        self,
        subscriber: Any,
        *,
        max_age_s: float,
        fraction: float = SPEC_DEPLOYABLE_FRACTION,
        topic: str = TOPIC,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._subscriber = subscriber
        self._max_age_s = float(max_age_s)
        self._fraction = float(fraction)
        self._topic = topic
        self._clock = clock
        self.decode_errors: tuple[str, ...] = ()

    def drain(self, timeout_ms: int) -> int:
        """Take everything available off the socket. Returns messages applied."""
        return len(self._subscriber.drain(timeout_ms))

    def picture(self) -> FinancialPicture | None:
        """The mirrored snapshot, or `None` with the reason recorded."""
        mirror = self._subscriber.mirror
        if not mirror.complete:
            self.decode_errors = (
                f"mirror incomplete: no snapshot yet for {mirror.missing}",
            )
            return None
        try:
            picture = decode_picture(mirror.table(self._topic))
        except PictureError as exc:
            self.decode_errors = (str(exc),)
            return None
        self.decode_errors = ()
        return picture

    def tradable(self) -> tuple[bool, str]:
        """§12.7's fast-drop verb: `(may size, reason)`. Never raises."""
        picture = self.picture()
        if picture is None:
            return False, "; ".join(self.decode_errors)
        defects = picture_defects(picture, self._fraction)
        if defects:
            return False, (
                f"mirrored picture version {picture.version} disagrees with "
                "itself: " + "; ".join(defects)
            )
        age = self._clock() - picture.published_ts
        if age > self._max_age_s:
            return False, (
                f"mirrored picture version {picture.version} is {age:.3f}s old, "
                f"over the {self._max_age_s:.3f}s ceiling — §12.7's freshness "
                "stamp says this mirror is stale, and §6.4's rule for a stale "
                "cache is refuse, never carry on with the last value"
            )
        return True, f"picture version {picture.version}, age {age:.3f}s"
