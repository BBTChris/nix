"""§4's lifecycle REFLECTION: a strategy mid-recovery is not eligible for new capital.

ARC 032 Stage 1 / sub-agent C. Authority is the frozen risk spec,
`docs/nics_risk_subsystem_spec_v1.3.md`: **§4:281-286** (*Allocator visibility
throughout*, LOCKED), §3:154-164 (the full financial-picture publish, whose
per-position rows carry lifecycle state), and §6.6:429-468 (contention, which is
what this screen sits in front of).

THE ONE RULE THIS MODULE OWNS, transcribed from §4:281-286 rather than
paraphrased::

    **Allocator visibility throughout (locked):** every recovery action reaches
    the Allocator via the same mirrored snapshot — flatten (positions→closed,
    reservations released, capital returns to deployable), deregistration
    (strategy leaves active set), quarantine (withdrawn from contention). The
    **transitional state is visible too**: a strategy mid-recovery reads as
    **in-flight-closing**, NOT normal-and-available, so it is never counted
    eligible for new capital while dying. (This is why the published table
    carries per-position lifecycle state, not just aggregates.)

REFLECTS, NEVER DRIVES — AND THAT DISTINCTION IS THE MODULE
-----------------------------------------------------------
§4:260-274 gives recovery to the Limiter and the supervisor: heartbeat miss ⇒
presumed dead, **flatten first**, **force-deregister in the Risk Engine**, **kill
+ relaunch**, and a **crash-loop cap** that quarantines. Not one of those verbs
is here, and their absence is the declaration — the same move
`nixalloc/seam.py` makes by giving `MirrorPort` no mutating verb and
`nixalloc/contention.py` makes by having no `award`. This module reads ONE
published snapshot and answers ONE question: *may this strategy be handed new
capital right now?* `checks/check_allocator_lifecycle.py` ARM 5 proves the
absence BY ATTEMPT — it reaches for every recovery-driving verb on the imported
module and requires every reach to come back empty.

WHO PRODUCES A `CLOSING` ROW, MEASURED RATHER THAN ASSUMED
-----------------------------------------------------------
This is the sentence a reader of a green gate most needs, and the arc brief that
commissioned this module had it backwards, so it is written out with the
measurement beside it (`RECOVERY_PRODUCER` below is the one place it lives, and
the gate prints that constant rather than restating it):

* **The strategy-death recovery path — heartbeat detection, flatten-on-death,
  force-deregister, kill/relaunch, the crash-loop cap and quarantine — is ARC
  R5** (§12B:878-880: *"strategy-death recovery (flatten→deregister→relaunch,
  quarantine, score archive)"*) **and does not exist in this tree.**
* **Supervision and the crash-loop breaker are ARC R4**, not R5 (§12B:872-876,
  and §12.2:616-618), and do not exist either.
* **But an in-flight-closing ROW already has a live producer**:
  `scripts/nixrisk/flatten.py:_confirmed_rows` (ARC 029, R2) republishes a
  position as `CLOSING` when a protective flatten fired and broker truth still
  shows the symbol held — the §12.6 halted-market case. It goes out through the
  real `FinancialPictureBook.commit()`, under one version stamp, on the same
  mirrored snapshot §4:281 names. So the state this module screens on is
  reachable in production today; what is absent is the *recovery* machinery that
  would be the OTHER reason to see it.

Nothing here may be read as coverage of the absent halves. A green says the
Allocator REFLECTS a published in-flight-closing state correctly. It says
nothing about heartbeat detection, orphan recovery, the crash-loop cap or
quarantine, because none of those exist to be measured.

SCORE PERSISTENCE IS NOT THIS MODULE AND NOT THIS ARC
------------------------------------------------------
§4:275-280 locks what happens to a strategy's score across death — a normal
crash-restart **persists** the realized-P&L history (keyed by strategy×symbol,
so a crash books no phantom zero), and quarantine **archives rather than
destroys** it. §6.6:457-461 gives that table exactly one writer, the **Scoring
process**, and says *"Nobody but the Scoring process COMPUTES the score."*
Scoring is R5 and does not exist. **This module therefore implements no
persistence, no archive, no EMA and no write of any kind**; it does not touch
the ranking table at all, and `nixalloc/contention.py` next door READS it and
only reads it. `SCORE_BOUNDARY` below states that in the one place it lives.

WHY A NEW MODULE AND NOT AN EXTENSION (doctrine C.9)
-----------------------------------------------------
C.9 forbids a SECOND instrument for a property some instrument already owns. The
property here is *capital eligibility per strategy, derived from published
lifecycle state*, and the census says nothing owned it:

* `nixalloc/mirror.py` owns whether the mirror is FRESH — a property of the
  SNAPSHOT, not of a strategy inside it;
* `nixalloc/sizing.py` owns §7's `min(...)` terms — arithmetic over one symbol;
* `nixalloc/wiring.py`'s `COUNTED_STATES` owns which rows contribute EXPOSURE to
  a correlation bucket. That is a different question with a different answer:
  it counts `RESERVED/PENDING/OPEN` because reservations are committed capital,
  and it says nothing about whether the OWNING STRATEGY may be handed more;
* `nixalloc/contention.py` owns the ORDER of a race (§6.6), not who may enter it.

So the predicate lands here, and the CONTENTION PASS is extended rather than
duplicated: `contention.rank_eligible` screens with this module and then
delegates to the existing `rank`. There is no second ordering anywhere.

`debug.md` §7.12 — THE STANDING QUESTION for `eligibility`: *what would have to
be true for this to answer while measuring nothing?*
  1. **The strategy owns no published rows**, so "no closing row" is true
     vacuously and every strategy on earth is eligible. GUARDED, never hidden:
     `CapitalEligibility.rows` reports the count and `observed_states` reports
     what was actually seen, so a caller and the gate can tell "flat" from
     "absent from the table" from "screened nothing".
  2. **No snapshot ever carries a CLOSING row**, so the refusing branch is dead
     code that no test distinguishes from a `return True`. CLOSED IN THE GATE,
     which is where it can be closed: `check_allocator_lifecycle` ARM 2 drives
     the REAL producer (`nixrisk.flatten`) into publishing one, over the real
     bus, and asserts the eligibility VALUE CHANGED across the transition and
     changed BACK.
  3. **The picture is absent or stale** and the answer is computed off nothing.
     CLOSED: `eligibility_from_mirror` refuses on any non-FRESH mirror and names
     the `MirrorState` (§12.7's "never sizes on a half-built mirror"), so the
     unmeasurable case is a REFUSAL rather than an admission.
  4. **The screen is applied to a caller who never passes a view.** CLOSED in
     `contention.rank_eligible`, whose lifecycle argument is REQUIRED and has no
     default: an omitted safety screen must never be spelled the same way as a
     deliberately absent one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

from nixalloc.seam import (
    FinancialPicture,
    MirrorPort,
    MirrorSnapshot,
    PositionRow,
    PositionState,
)

# pylint: disable=too-few-public-methods
# `LifecycleViewPort` is a one-verb Protocol and `PictureLifecycle` /
# `MirrorLifecycle` are the two objects that satisfy it. A second method
# invented to clear a class-shape heuristic would be surface invented on the
# Allocator's side, and on this boundary surface IS authority (§2) — the same
# reasoning `nixalloc/seam.py` and `nixalloc/mirror.py` each record.

__all__ = [
    "IN_FLIGHT_CLOSING",
    "RECOVERY_PRODUCER",
    "SCORE_BOUNDARY",
    "CapitalEligibility",
    "LifecycleViewPort",
    "MirrorLifecycle",
    "PictureLifecycle",
    "eligibility",
    "eligibility_by_strategy",
    "eligibility_from_mirror",
    "strategy_rows",
]

#: §4:284's *in-flight-closing*, as published lifecycle state. ONE member, and
#: the choice is the spec's own vocabulary rather than this module's: §3:157
#: publishes `reserved / pending / open / closing / closed`, §4:283 makes the
#: completed flatten `positions→closed`, and the only state left naming a close
#: still IN FLIGHT is `CLOSING`. `check_allocator_lifecycle` ARM 1 does not take
#: that on trust — it parses the hyphenated phrase out of §4's own sentence in
#: the frozen document at run time and maps it onto `PositionState` BY VALUE, so
#: this set has a reference side that is not itself.
IN_FLIGHT_CLOSING: Final[frozenset[PositionState]] = frozenset({PositionState.CLOSING})

#: WHO PUBLISHES THE STATE THIS MODULE SCREENS ON. One string, one home, printed
#: by the gate rather than restated in it (directive 3). See the module
#: docstring for the measurement behind each clause.
RECOVERY_PRODUCER: Final[str] = (
    "the state screened here is PUBLISHED, never produced here. It now has TWO "
    "live producers and they reach it by different code. (1) "
    "scripts/nixrisk/flatten.py:_confirmed_rows (ARC 029 / R2) republishes a "
    "position as CLOSING when a protective flatten fired and broker truth still "
    "shows the symbol held (§12.6 halted market). (2) "
    "scripts/nixrisk/recovery.py:RecoverySequencer (ARC 034 / sub-agent C) is "
    "the OTHER producer §4:260-274 names — heartbeat miss, flatten-on-death, "
    "force-deregister, kill+relaunch, crash-loop cap, quarantine — and it "
    "republishes the dying strategy's rows as CLOSING immediately after the "
    "flatten fires, which is §4:284's transitional in-flight-closing state. "
    "That HEARTBEAT-ORIGINATED row is what CHECK-DEBT D3.155 asked for and it "
    "is driven by checks/check_orphan_recovery.py through a real death. WHAT IS "
    "STILL ABSENT: score handling across death (§4:275-280) is ARC R5 — see "
    "SCORE_BOUNDARY — and no systemd unit on this box is yet wired to the "
    "crash-loop breaker, so §12.2's counter exists and nothing feeds it in "
    "production. A green over this module remains the Allocator REFLECTING a "
    "published state and is never coverage of either absent half"
)

#: THE OTHER BOUNDARY, stated once. §4:275-280 and §6.6:457-461.
SCORE_BOUNDARY: Final[str] = (
    "score-across-death (§4:275-280: a crash persists the strategy×symbol "
    "realized history and books no phantom zero; quarantine ARCHIVES rather "
    "than destroys) belongs to the Scoring process, which §6.6:457-461 makes "
    "the SOLE writer of the ranking table and which is R5 and does not exist. "
    "This module implements no persistence, no archive and no EMA, and reads "
    "the ranking table not at all; nixalloc/contention.py READS it and only "
    "reads it"
)

_SITE: Final[str] = "scripts/nixalloc/lifecycle.py"


@dataclass(frozen=True)
class CapitalEligibility:
    """May this strategy be handed NEW capital, off THIS published snapshot?

    `reason` is required on both answers and not only on the refusal (§18: the
    reason, never the code). An admission that cannot say what it looked at is
    indistinguishable from an admission that looked at nothing, which is §7.12/1
    exactly — so `rows` and `observed_states` ride along and say what was seen.
    """

    strategy_id: str
    eligible: bool
    reason: str
    #: The published version every field above was derived from, or `None` when
    #: there was no picture to derive them from. `None` rather than a negative
    #: sentinel: the mirror's own `NO_VERSION` is that module's contract and
    #: restating it here would be a second spelling of one fact (directive 3).
    snapshot_version: int | None
    #: `trade_id`s of this strategy's rows in an in-flight-closing state.
    closing_trades: tuple[str, ...]
    #: Every lifecycle state observed for this strategy, sorted. §7.12/1.
    observed_states: tuple[str, ...]
    #: How many published rows this strategy owned. Zero means FLAT, and the
    #: reason says so — it never silently reads as "screened".
    rows: int


def strategy_rows(
    picture: FinancialPicture, strategy_id: str
) -> tuple[PositionRow, ...]:
    """Every published row §3:159 keys to this strategy. Read-only, O(rows)."""
    return tuple(row for row in picture.positions if row.strategy_id == strategy_id)


def eligibility(picture: FinancialPicture, strategy_id: str) -> CapitalEligibility:
    """§4:284-286, applied to ONE published snapshot. Total; never raises.

    A strategy with ANY row in an in-flight-closing state is refused, whatever
    else it holds: §4:285 says it *"is never counted eligible for new capital
    while dying"*, and a strategy that is half dying is dying. The refusal names
    the state, the trades and the version, because three different snapshots can
    produce the same boolean and only the reason tells them apart.
    """
    rows = strategy_rows(picture, strategy_id)
    states = tuple(sorted({row.state.value for row in rows}))
    closing = tuple(row.trade_id for row in rows if row.state in IN_FLIGHT_CLOSING)
    if closing:
        return CapitalEligibility(
            strategy_id=strategy_id,
            eligible=False,
            reason=(
                f"{_SITE}: strategy {strategy_id!r} has {len(closing)} of "
                f"{len(rows)} published position row(s) in an IN-FLIGHT-CLOSING "
                f"state {sorted(s.value for s in IN_FLIGHT_CLOSING)} "
                f"(trade_id(s) {list(closing)}, states observed {list(states)}) "
                f"at published snapshot version {picture.version} — §4:284-286 "
                "makes a strategy mid-recovery read as in-flight-closing, NOT "
                "normal-and-available, so it is never counted eligible for new "
                "capital while dying"
            ),
            snapshot_version=picture.version,
            closing_trades=closing,
            observed_states=states,
            rows=len(rows),
        )
    held = "flat — it owns no published row" if not rows else f"states {list(states)}"
    return CapitalEligibility(
        strategy_id=strategy_id,
        eligible=True,
        reason=(
            f"{_SITE}: strategy {strategy_id!r} is {held} across "
            f"{len(rows)} published row(s) at snapshot version "
            f"{picture.version}; none is in an in-flight-closing state "
            f"{sorted(s.value for s in IN_FLIGHT_CLOSING)}, so §4:284-286 does "
            "not withhold capital. This says nothing about SIZE — §7's terms "
            "and §3's Phase B still decide that"
        ),
        snapshot_version=picture.version,
        closing_trades=(),
        observed_states=states,
        rows=len(rows),
    )


def eligibility_from_mirror(
    snapshot: MirrorSnapshot, strategy_id: str
) -> CapitalEligibility:
    """The same rule, read off the Allocator's private mirror. FAILS CLOSED.

    A mirror that is EMPTY, PARTIAL or STALE has no snapshot to screen against,
    and §12.7's rule for that is refuse — *"never sizes on a half-built mirror"*
    — so this returns INELIGIBLE naming the `MirrorState`, never an admission.
    `MirrorSnapshot.sizeable` is the seam's single predicate and is the one
    consulted here; this function does not invent a second freshness rule.
    """
    if not snapshot.sizeable or snapshot.picture is None:
        return CapitalEligibility(
            strategy_id=strategy_id,
            eligible=False,
            reason=(
                f"{_SITE}: the Allocator's mirror is {snapshot.state.value.upper()}"
                f", not FRESH, so there is no published snapshot to screen "
                f"{strategy_id!r} against — §12.7 treats that mirror as stale "
                "and fast-drops rather than sizing, and an eligibility answer "
                "computed off no picture would be an admission dressed as a "
                f"measurement. The mirror says: {snapshot.reason}"
            ),
            snapshot_version=None,
            closing_trades=(),
            observed_states=(),
            rows=0,
        )
    return eligibility(snapshot.picture, strategy_id)


@runtime_checkable
class LifecycleViewPort(Protocol):
    """What a contention pass consults to screen a contender. READ-ONLY.

    One verb, and the shape is the authority: there is nothing here that takes a
    picture, a strategy state, or a recovery instruction. SYNCHRONOUS for the
    reason `nixalloc/seam.py` gives every one of its verbs — this is consulted
    inside a single-pass §16 U1 sizing/contention pass, and a suspension point
    in the middle of one is a place the picture can change underneath it.
    """

    def eligibility(self, strategy_id: str) -> CapitalEligibility:
        """May this strategy be handed new capital? Never raises for a caller."""


@dataclass(frozen=True)
class PictureLifecycle:
    """A view over ONE held picture. Deterministic and version-pinned.

    Frozen and holding the picture itself, not a callable that fetches one: two
    contenders screened in one pass must be screened against the SAME version,
    and a view that re-read the mirror per contender could straddle a publish —
    the cross-read §3's atomicity rule exists to forbid, reproduced inside a
    single contention race.
    """

    picture: FinancialPicture

    def eligibility(self, strategy_id: str) -> CapitalEligibility:
        """§4:284-286 against the pinned snapshot."""
        return eligibility(self.picture, strategy_id)


@dataclass(frozen=True)
class MirrorLifecycle:
    """A view that takes ONE snapshot off the real mirror, then pins it.

    `pin()` is the whole point: `snapshot()` is called ONCE and the resulting
    `PictureLifecycle` is what screens the race. Screening straight off the
    mirror per contender would re-read it per contender.
    """

    mirror: MirrorPort

    def pin(self) -> PictureLifecycle | None:
        """One read. `None` when the mirror has nothing FRESH to pin."""
        # E1111: `MirrorPort` is a Protocol, so `snapshot`'s body is a
        # docstring and pylint reads it as returning None. The object passed in
        # is a real mirror; the port is the declaration, not the implementation.
        snapshot = self.mirror.snapshot()  # pylint: disable=assignment-from-no-return
        if not snapshot.sizeable or snapshot.picture is None:
            return None
        return PictureLifecycle(snapshot.picture)

    def eligibility(self, strategy_id: str) -> CapitalEligibility:
        """One read of the mirror, screened. FAILS CLOSED on a non-FRESH one."""
        snapshot = self.mirror.snapshot()  # pylint: disable=assignment-from-no-return
        return eligibility_from_mirror(snapshot, strategy_id)


def eligibility_by_strategy(
    picture: FinancialPicture,
) -> Mapping[str, CapitalEligibility]:
    """Every strategy the published table names, screened. A REPORT, not a gate.

    Only strategies with published rows appear: a strategy absent from the table
    is flat and eligible by `eligibility()` above, and inventing a row for it
    here would make this mapping a second, weaker source of truth about who
    exists (§2 — registration is the Limiter's, not the Allocator's).
    """
    return {
        strategy_id: eligibility(picture, strategy_id)
        for strategy_id in sorted({row.strategy_id for row in picture.positions})
    }
