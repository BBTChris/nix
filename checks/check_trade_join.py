#!/usr/bin/env python3
"""Every `trade_id` resolves to EXACTLY ONE `client_order_id`, and back again.

ARC 034 / sub-agent A. ONE gate, ONE property (`nix_check_contract.md` §5.5):

    the production join is a BIJECTION that is not an identity — every minted
    `trade_id` resolves to exactly one `client_order_id` and that
    `client_order_id` resolves back to the same `trade_id`, no `trade_id` equals
    the order id it was minted from, and `positions.identity_trade_id` cannot be
    the production policy.

Every `§` in this file cites `docs/nics_risk_subsystem_spec_v1.3.md` unless
another document is named on the line. `D3.<n>` cites `docs/CHECK-DEBT.md`.

------------------------------------------------------------------------------
WHY THIS IS A SEPARATE GATE FROM `check_fill_handler`
------------------------------------------------------------------------------
The subject is a REGISTRY and a round trip over it, with no fill in it at all.
`check_fill_handler` drives one confirmed fill and judges the motion §3 and §4
require to be atomic; nothing in that motion is this property, and nothing here
needs a fill, a stop, a picture book or a cap. Merging them would make one gate
own two properties, which `nix_check_contract.md` §5.5 forbids, and would mean a
join defect and a fill-ordering defect reached an operator as one red.

------------------------------------------------------------------------------
THE TRAP, NAMED FIRST — a non-null check passes on a WRONG mapping
------------------------------------------------------------------------------
**A join gate that asserts `origin is not None` passes on every possible wrong
answer.** So does one that asserts `trade_id` is a non-empty string. Both were
available and both are refused here. What is measured instead:

* **THE ROUND TRIP, per order.** `origin_for_order(coid).trade_id` fed back
  through `origin_for_trade` must return an origin whose `client_order_id` is the
  one the trip started from. A registry that returned SOME origin — the first, a
  fixed one, a plausible neighbour's — passes non-null and fails this.
* **INJECTIVITY, over a population where it can fail.** Two orders that received
  one `trade_id` is the collision §3:159 cannot survive: a table with two rows
  under one key is not keyed by it, and `picture.picture_defects` refuses a whole
  snapshot for it. It is invisible with one order, so the floor is two.
* **NON-IDENTITY, per order.** Under `positions.identity_trade_id` the round trip
  passes on EVERY input, because both directions are the same dictionary lookup
  by the same key. A gate that only proved the round trip would therefore be
  green over the exact collapse D3.177's architect ruling forbids, which is why
  non-identity is asserted separately and per order.
* **UNREACHABILITY of the degenerate mint.** `join.production_origins` must
  REFUSE `identity_trade_id`, refuse an anonymous callable that behaves like it,
  and refuse a colliding mint — each driven, each required to name what was
  wrong. A rule enforced only by the mint that happens to be the default is a
  rule that survives exactly until somebody passes a different one.

------------------------------------------------------------------------------
WHAT THIS GATE CANNOT PROVE, stated rather than implied
------------------------------------------------------------------------------
It proves the join is a bijection WITHIN ONE PROCESS over the orders recorded in
it. It cannot prove the mint is unique across a restart (it is not — the sequence
restarts, and `scripts/nixrisk/join.py` says so outright), nor across two Risk
Engines (there is one, §5). It also says nothing about anything CALLING
`production_origins` on a live approval path: the Limiter's approval handler does
not exist yet, and that residual belongs to the arc that built this.

`debug.md` §7.12 — THE STANDING QUESTION, asked where this gate was built.
*What would have to be true for this gate to PASS while measuring nothing?*

1. **The subject is unimportable or resolves to another tree** (D3.124). *Closed:*
   an import failure is CANNOT_MEASURE naming the exception, and each module's
   `__file__` must equal the exact path under the tree under judgement.
2. **One order in the population**, where injectivity cannot fail and a wrong
   reverse lookup returns the only right answer. *Closed:* `MIN_ORDERS` and
   `MIN_DISTINCT_TRADE_IDS`, both floors strictly below today's figures.
3. **The degenerate-mint refusals never fire because the probes cannot produce
   the input** — the ARC 034 / 0.5 finding, fail-closed branches undriven because
   the gate's own doubles cannot reach them. *Closed:* each refusal is driven with
   a REAL callable of the shape it must reject — `identity_trade_id` itself, an
   anonymous function returning `order.client_order_id`, and a constant mint —
   and `MIN_REFUSALS_DRIVEN` counts them.
4. **A refusal is reported for the wrong reason**, so the branch is reached by
   accident. *Closed:* every refusal control requires a NAMED substring in the
   message, never the exception type and never a bare status (check contract v2
   §11).
5. **The round trip is asked of a registry nothing was recorded in.** *Closed:*
   the trip count is read off what was actually recorded and floored, and the
   registry's own `recorded` counter must agree with the population size.
6. **A defect flattens a tallied figure and the floor answers first**, so a
   violation the gate measured is reported as one it could not measure — a
   registry with a wrong reverse lookup closes ZERO round trips, which is
   `MIN_ROUND_TRIPS`. *Closed:* `run` reports defects BEFORE floors. A floor
   exists to stop a vacuous PASS, never to suppress an observed violation, and
   Fail > Cannot-measure in the aggregate for the same reason.

WHAT IS NOT CLOSED, named rather than claimed away. The individual arms are not
separately guarded: an exception raised inside one reaches `run`'s outer handler
and becomes CANNOT_MEASURE, which is a statement about this instrument rather
than about the subject. Only the composed drive in `_measure` is guarded.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

#: Nothing must run first: the modules are files on disk no check produces.
DEPENDS_ON: tuple[str, ...] = ()
#: This gate IMPORTS `nixrisk` out of `ctx.nix_home`, so it mutates `sys.path` and
#: `sys.modules` for the duration and restores both. Declared because check
#: contract v2 rule 12 measures claims against observed behaviour.
RESOURCES: tuple[str, ...] = ("interpreter:sys.modules", "interpreter:sys.path")
#: No timeout, no poll, no sleep. Dictionary lookups over a dozen orders.
TIME_BOUND = False
#: NON-CORRECTABLE.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the repair for a join that collapses trade_id onto client_order_id, or that "
    "maps two orders onto one trade_id, is an architectural decision recorded "
    "against D3.177 by a human. An instrument empowered to edit the mint until "
    "its own round trip closed could satisfy itself with the identity mapping, "
    "which is precisely the policy the ruling forbids and the one that makes "
    "every round-trip measurement vacuous."
)
#: Genuinely MEASURED here: `scripts/nixrisk/join.py` is imported out of the tree
#: under test and DRIVEN — the production factory, the production mint, and three
#: degenerate policies it must refuse. `positions.py` is READ (it owns
#: `EntryOrderOrigins` and has its own gate, `check_origin_write`).
SUBJECTS: tuple[str, ...] = ("scripts/nixrisk/join.py",)

NAME = "check_trade_join"

JOIN = "scripts/nixrisk/join.py"
POSITIONS = "scripts/nixrisk/positions.py"

_MODULES: tuple[tuple[str, str], ...] = (
    ("nixrisk.join", JOIN),
    ("nixrisk.positions", POSITIONS),
    ("nixrisk.seam", "scripts/nixrisk/seam.py"),
)
_PACKAGES = ("nixrisk",)

# --------------------------------------------------------------------------
# THE POPULATION. `(client_order_id, strategy_id, symbol)`.
#
# Four orders across three strategies, and TWO of them share a strategy on
# purpose: a mint that keyed only on `strategy_id` would collide those two, and
# with one order per strategy that collision is invisible.
# --------------------------------------------------------------------------
_ORDERS: tuple[tuple[str, str, str], ...] = (
    ("CO-1", "strat-es", "ES"),
    ("CO-2", "strat-nq", "NQ"),
    ("CO-3", "strat-es", "ES"),
    ("CO-4", "strat-cl", "CL"),
)

# --------------------------------------------------------------------------
# NON-VACUITY FLOORS (`debug.md` §7.12). Every one strictly below today's figure
# and non-zero: today 4 orders, 4 distinct trade ids, 4 closed round trips and
# 3 degenerate policies driven to a refusal.
# --------------------------------------------------------------------------

#: Orders recorded. With one, injectivity cannot fail and a reverse lookup that
#: always returns the first origin is right by construction.
MIN_ORDERS = 2
#: Distinct minted ids. Equal to the order count in a working system; a floor
#: below it is what turns "no collisions" into a statement about something.
MIN_DISTINCT_TRADE_IDS = 2
#: Round trips CLOSED (`coid -> trade_id -> coid`). Read off the drive.
MIN_ROUND_TRIPS = 2
#: Degenerate policies actually driven INTO a refusal. §7.12 note 3: a
#: fail-closed branch the gate's own doubles cannot reach is a branch nothing
#: tests.
MIN_REFUSALS_DRIVEN = 2


class Finding(NamedTuple):
    """One defect: WHERE it is and WHY it is wrong. Never a bare status (§18)."""

    site: str
    why: str


class Loaded(NamedTuple):
    """The subject and the collaborators, imported out of the tree under test."""

    join: ModuleType
    positions: ModuleType
    seam: ModuleType


@dataclass
class Tally:
    """What the drive ACTUALLY did. Non-vacuity is read off this, never asserted."""

    orders: int = 0
    distinct_trade_ids: int = 0
    round_trips: int = 0
    refusals_driven: int = 0
    minted: tuple[str, ...] = field(default_factory=tuple)


def _cannot_measure(detail: str) -> CheckResult:
    """Doctrine B.2: an unread subject is CANNOT_MEASURE, never PASS."""
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


# ==========================================================================
# LOADING
# ==========================================================================


def _purge() -> None:
    """Drop already-imported first-party modules so `home` wins the import."""
    for name in [key for key in sys.modules if key.split(".")[0] in _PACKAGES]:
        del sys.modules[name]


def load(home: Path) -> tuple[Loaded | None, str]:
    """Import the subject out of `home`, leaving the interpreter as it was found."""
    if not (home / JOIN).is_file():
        return None, (
            f"{JOIN}: no such file under {home} — the subject is unavailable, so "
            "nothing was measured (§17: never a PASS)"
        )
    saved_path = list(sys.path)
    saved_modules = dict(sys.modules)
    try:
        sys.path.insert(0, str((home / "scripts").resolve()))
        _purge()
        importlib.invalidate_caches()
        modules: list[ModuleType] = []
        for dotted, rel in _MODULES:
            module = importlib.import_module(dotted)
            got = Path(getattr(module, "__file__", "") or "").resolve()
            want = (home / rel).resolve()
            if got != want:
                return None, (
                    f"{dotted} was imported from {got}, not from the {rel} this "
                    f"gate reports on ({want}) — the import fell through to "
                    "another tree (D3.124), so this gate measured something "
                    "other than what it names (§17: never a PASS)"
                )
            modules.append(module)
        return Loaded(*modules), ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{JOIN}: cannot import the join from {home} — "
            f"{type(exc).__name__}: {exc}. The subject is unavailable, so "
            "nothing was measured (§17: never a PASS)"
        )
    finally:
        sys.path[:] = saved_path
        _purge()
        sys.modules.update(saved_modules)


def _order(loaded: Loaded, row: tuple[str, str, str]) -> Any:
    """One `ProposedOrder`. Only the three join fields matter; the rest is ballast."""
    seam = loaded.seam
    coid, strategy, symbol = row
    return seam.ProposedOrder(
        client_order_id=coid,
        strategy_id=strategy,
        symbol=symbol,
        side=seam.Side.LONG,
        qty=1,
        margin_per_contract=500.0,
        stop_ticks=10,
        stop_mode=seam.StopMode.FIXED,
        signal_ts=1000.0,
    )


# ==========================================================================
# ARM ROUND TRIP — the property a non-null check cannot see
# ==========================================================================


def round_trip_defects(loaded: Loaded, tally: Tally) -> list[Finding]:
    """`coid -> trade_id -> coid` closes, for every order, over one registry."""
    origins = loaded.join.production_origins()
    recorded: dict[str, Any] = {}
    for row in _ORDERS:
        recorded[row[0]] = origins.record(_order(loaded, row))
    tally.orders = len(recorded)
    tally.minted = tuple(sorted(origin.trade_id for origin in recorded.values()))
    tally.distinct_trade_ids = len(set(tally.minted))
    defects = _injectivity_defects(recorded, tally)
    for coid, origin in sorted(recorded.items()):
        defects += _trip_defects(origins, coid, origin, tally)
    if int(getattr(origins, "recorded", -1)) != len(_ORDERS):
        defects.append(
            Finding(
                f"{JOIN}:production_origins.recorded",
                f"the registry reports {origins.recorded} recorded origin(s) "
                f"against {len(_ORDERS)} driven — a registry that cannot say "
                "what it holds can only be believed, not measured, and a round "
                "trip over rows it silently dropped proves nothing",
            )
        )
    return defects


def _injectivity_defects(recorded: dict[str, Any], tally: Tally) -> list[Finding]:
    """Two orders under one `trade_id` is a table that is not keyed by it."""
    if tally.distinct_trade_ids == len(recorded):
        return []
    return [
        Finding(
            f"{JOIN}:SequencedTradeIdMint.mint",
            f"{len(recorded)} orders received {tally.distinct_trade_ids} "
            f"distinct trade_id(s) {list(tally.minted)} — §3:159 keys the "
            "position table BY trade_id, so two rows under one key means the "
            "table is not keyed by it, and picture.picture_defects refuses a "
            "whole snapshot for exactly that",
        )
    ]


def _trip_defects(origins: Any, coid: str, origin: Any, tally: Tally) -> list[Finding]:
    """One order's round trip, and the non-identity assertion beside it."""
    site = f"{JOIN}:production_origins[{coid}]"
    defects: list[Finding] = []
    if origin.trade_id == coid:
        defects.append(
            Finding(
                site,
                f"the minted trade_id {origin.trade_id!r} IS the "
                "client_order_id — D3.177's architect ruling keeps the two keys "
                "DISTINCT, and under an identity mapping the round trip below "
                "passes on every possible input, so it measures nothing at all",
            )
        )
    back = origins.origin_for_trade(origin.trade_id)
    if back is None:
        defects.append(
            Finding(
                site,
                f"trade_id {origin.trade_id!r} resolves to NO origin, so the "
                "reverse direction of the join is missing — §3 keys the position "
                "table by it and nothing could say which order opened the trade",
            )
        )
        return defects
    if back.client_order_id != coid:
        defects.append(
            Finding(
                site,
                f"trade_id {origin.trade_id!r} resolves back to order "
                f"{back.client_order_id!r}, not to {coid!r} — the round trip is "
                "OPEN. A gate asserting only that the lookup is non-null would "
                "be green on this exact answer, which is a real origin belonging "
                "to a different trade",
            )
        )
        return defects
    forward = origins.origin_for_order(coid)
    if forward is None or forward.trade_id != origin.trade_id:
        defects.append(
            Finding(
                site,
                f"order {coid!r} resolves forward to "
                f"{None if forward is None else forward.trade_id!r}, not to the "
                f"{origin.trade_id!r} it was recorded under — the two directions "
                "of the join disagree, so at least one of them is a lie",
            )
        )
        return defects
    if forward.strategy_id != origin.strategy_id:
        defects.append(
            Finding(
                site,
                f"the join carries strategy {forward.strategy_id!r} against the "
                f"recorded {origin.strategy_id!r} — §9 requires strategy_id on "
                "every event row and §3:159 publishes it on every position row, "
                "and it rides the origin so no writer has to look it up in a "
                "table that may have moved",
            )
        )
        return defects
    tally.round_trips += 1
    return defects


# ==========================================================================
# ARM REFUSAL — the degenerate mint is UNREACHABLE as the production policy
# ==========================================================================


def _colliding_mint(order: Any) -> str:  # pylint: disable=unused-argument
    """A constant mint. Every order gets one trade_id — §3's fatal collision."""
    return "TRD-CONSTANT"


def _anonymous_identity(order: Any) -> str:
    """`identity_trade_id`'s BEHAVIOUR under a different name.

    The reason `production_origins` probes rather than compares against a name:
    this function is not `positions.identity_trade_id` and no identity comparison
    can see it, yet it collapses the join exactly as completely.
    """
    return order.client_order_id


def refusal_defects(loaded: Loaded, tally: Tally) -> list[Finding]:
    """Three degenerate policies, each DRIVEN into a refusal that names it."""
    identity_why = (
        "a mint that returns its input makes the equality hold by construction, "
        "so no observation can contradict it and every round-trip gate over it "
        "passes on every possible input"
    )
    collision_why = (
        "a mint that gives two distinct orders ONE trade_id makes §3:159's "
        "position table stop being keyed by it, which is the defect "
        "picture.picture_defects refuses a whole snapshot for"
    )
    cases: tuple[tuple[str, Callable[[Any], str], str, str], ...] = (
        (
            "identity_trade_id",
            loaded.positions.identity_trade_id,
            "identity_trade_id",
            identity_why,
        ),
        (
            "an anonymous identity mint",
            _anonymous_identity,
            "client_order_id",
            identity_why,
        ),
        ("a colliding constant mint", _colliding_mint, "TRD-CONSTANT", collision_why),
    )
    defects: list[Finding] = []
    for label, policy, must_name, why in cases:
        defects += _refuses(loaded, label, policy, must_name, why, tally)
    return defects


def _refuses(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    loaded: Loaded,
    label: str,
    policy: Any,
    must_name: str,
    why: str,
    tally: Tally,
) -> list[Finding]:
    """`production_origins` must REFUSE this policy, and the message must say why.

    Check contract v2 §11: a can-fail control asserts the REASON, never the
    exception type alone. An exception raised because the probe order could not
    be constructed would reach the same `except` as a real refusal.
    """
    site = f"{JOIN}:production_origins[{label}]"
    try:
        loaded.join.production_origins(mint=policy)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        if must_name not in str(exc):
            return [
                Finding(
                    site,
                    f"refused with {type(exc).__name__}: {exc} — the refusal does "
                    f"not name {must_name!r}, so an operator cannot tell WHICH "
                    "policy was rejected, and a refusal raised for an unrelated "
                    "reason would look identical",
                )
            ]
        tally.refusals_driven += 1
        return []
    return [
        Finding(
            site,
            f"{label} was ACCEPTED as the production join policy — it mints "
            f"{policy(_order(loaded, _ORDERS[0]))!r} for order "
            f"{_ORDERS[0][0]!r}. D3.177's architect ruling keeps trade_id and "
            f"client_order_id DISTINCT behind an explicit, gated join: {why}",
        )
    ]


def default_defects(loaded: Loaded) -> list[Finding]:
    """The DEFAULT production policy — the one nobody chooses — is non-identity.

    The hazard this closes is stated backwards elsewhere and forwards here: it is
    not that somebody will pass the degenerate mint, it is that NOBODY will pass
    anything and the default becomes the production policy by inaction, which
    leaves no diff for a reviewer to find.
    """
    origins = loaded.join.production_origins()
    order = _order(loaded, ("CO-DEFAULT", "strat-default", "ES"))
    origin = origins.record(order)
    if origin.trade_id == order.client_order_id:
        return [
            Finding(
                f"{JOIN}:production_origins[default]",
                f"the DEFAULT policy minted {origin.trade_id!r} for order "
                f"{order.client_order_id!r} — they are equal, so the join "
                "collapses for any caller that simply takes the default",
            )
        ]
    return []


# ==========================================================================
# THE VERDICT
# ==========================================================================


def _floor_refusal(tally: Tally) -> CheckResult | None:
    """`debug.md` §7.12: a run that reached nothing reports so, never PASS."""
    floors = (
        (tally.orders, MIN_ORDERS, "order(s) recorded"),
        (tally.distinct_trade_ids, MIN_DISTINCT_TRADE_IDS, "distinct trade_id(s)"),
        (tally.round_trips, MIN_ROUND_TRIPS, "CLOSED round trip(s)"),
        (
            tally.refusals_driven,
            MIN_REFUSALS_DRIVEN,
            "degenerate policy/policies driven into a refusal",
        ),
    )
    for observed, floor, what in floors:
        if observed < floor:
            return _cannot_measure(
                f"{JOIN}: the drive produced {observed} {what}, below the floor "
                f"of {floor}. Below it the round trip cannot fail — one order "
                "resolves to the only answer there is — so a green would be a "
                "statement about nothing (§5.3: an empty scope is never a PASS)"
            )
    return None


def _evidence(tally: Tally) -> str:
    """Every figure this run actually observed. Never a restatement."""
    return (
        f"recorded {tally.orders} order(s) through the SHIPPED "
        f"production_origins; minted {tally.distinct_trade_ids} distinct "
        f"trade_id(s) {list(tally.minted)}, none equal to its own "
        f"client_order_id; {tally.round_trips} round trip(s) CLOSED "
        f"(coid -> trade_id -> coid, both directions agreeing on the strategy); "
        f"{tally.refusals_driven} degenerate policy/policies DRIVEN into a "
        "refusal that named it. UNBOUND: nothing here proves a live approval "
        "path calls production_origins — the Limiter's approval handler does "
        "not exist yet"
    )


def _measure(home: Path) -> tuple[list[Finding], Tally | None, str]:
    """Run every arm. Returns `(defects, tally, refusal_detail)`."""
    loaded, complaint = load(home)
    if loaded is None:
        return [], None, complaint
    tally = Tally()
    try:
        defects = round_trip_defects(loaded, tally)
        defects += refusal_defects(loaded, tally)
        defects += default_defects(loaded)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # §7.12 note 3 / §18: recording four orders in a fresh registry is the
        # ordinary case, so a raise is a statement about the SUBJECT.
        return (
            [
                Finding(
                    f"{JOIN}:production_origins",
                    f"driving the shipped join raised {type(exc).__name__}: "
                    f"{exc}. Recording distinct approved orders in a fresh "
                    "registry is the ordinary case §4 describes, so refusing it "
                    "is a defect in the subject and not a limit of this "
                    "instrument",
                )
            ],
            None,
            "",
        )
    return defects, tally, ""


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Hold the production join against D3.177: a bijection, and not an identity."""
    try:
        defects, tally, refusal = _measure(ctx.nix_home)
        if tally is None and not defects:
            return _cannot_measure(
                refusal
                or f"{JOIN}: neither a reading nor a refusal — a gate's own "
                "pre-flight returning nothing is never a verdict"
            )
        evidence = _evidence(tally) if tally is not None else ""
        # DEFECTS BEFORE THE FLOOR, and the order is load-bearing. A floor exists
        # to stop a VACUOUS PASS, never to suppress a violation the run actually
        # observed: a defect that also drove a tallied figure to zero — a handler
        # that issues no IOC cancel drives `cancels` to zero, which is exactly the
        # §4 breach the arm caught — would otherwise be reported as "this gate
        # could not measure" when the gate measured it precisely. MEASURED: five
        # controls in this file's own suite reached CANNOT_MEASURE that way before
        # this order was fixed. Fail > Cannot-measure in the aggregate for the
        # same reason.
        if defects:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in defects),
                evidence=evidence,
                detail="; ".join(f"{site}: {why}" for site, why in defects),
            )
        if tally is not None:
            floor = _floor_refusal(tally)
            if floor is not None:
                return floor
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


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
