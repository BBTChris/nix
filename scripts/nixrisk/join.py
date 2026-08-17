"""D3.177's join, made PRODUCTION — a `trade_id` that is not the order's id.

ARC 034 / sub-agent A. Every `§` in this file cites
`docs/nics_risk_subsystem_spec_v1.3.md`; `D3.<n>` cites `docs/CHECK-DEBT.md`.

==============================================================================
THE DEFECT THIS CLOSES — an equality nothing can contradict
==============================================================================
§3:159 keys the published position table by `trade_id`. `ProposedOrder`,
`Reservation`, `StopState` and §4's `(order_id, exec_id)` dedup tuple are all
keyed by `client_order_id`. No sentence in the frozen spec relates the two, so
ARC 033 declared the relationship as a value (`seam.TradeOrigin`), a lookup
(`seam.TradeOriginPort`) and an INJECTED policy (`positions.EntryOrderOrigins`),
and gave it a default: `positions.identity_trade_id`, which returns
`order.client_order_id` unchanged.

**That default IS the collapse the architect ruling forbids.** The ruling keeps
the two keys DISTINCT behind an explicit, gated, Limiter-owned join. An identity
mapping is an equality that holds BY CONSTRUCTION, which means:

* no observation can ever contradict it, so every round-trip gate over it passes
  on every possible input and therefore measures nothing;
* the day the bijection stops holding — a scaling order building one position out
  of several entry orders, a position surviving a session, a venue-side amendment
  re-issuing the order id — every site that wrote one id where the other was
  meant is wrong at once, and none of them is a diff anybody can find.

`fill_seam.NON_IDENTITY_MINT_REQUIRED` states the rule where a gate can read it.
This module is the mint that satisfies it and the FACTORY that makes the
degenerate one structurally unreachable in production.

==============================================================================
`identity_trade_id` IS NOT DELETED, AND THAT IS DELIBERATE
==============================================================================
It is the documented degenerate case: `positions.py` spells out the four scope
facts under which a trade and its entry order are in bijection, and a reader who
cannot see the degenerate case cannot see what the non-degenerate one buys.
Deleting it would also silently retarget `check_origin_write`'s ARM JOIN, which
proves the writer does not ASSUME the identity by driving both bindings.

What this module removes is not the function — it is the possibility of that
function being the PRODUCTION policy. `production_origins()` is the only
constructor the Limiter's wiring calls, and it REFUSES any mint that returns its
input, **by probing it rather than by comparing it to a name**. A name comparison
(`policy is identity_trade_id`) is defeated by `lambda o: o.client_order_id`
written anywhere else; a probe is defeated by nothing, because the property being
refused is the BEHAVIOUR and the probe measures exactly that.

==============================================================================
WHAT THE MINT GUARANTEES, AND WHAT IT DOES NOT
==============================================================================
GUARANTEED, and each one is measured rather than asserted:

* **Non-identity.** `mint` refuses to RETURN a value equal to the order's
  `client_order_id`, whatever the spelling of that id. The check is inside the
  mint, so a `client_order_id` that happens to look like a minted id cannot slip
  through by coincidence.
* **Injective within one process.** A strictly increasing sequence number is part
  of every id, so two orders can never receive one `trade_id`. That is the
  collision §3 cannot tolerate: a table with two rows under one key is not keyed
  by it, and `picture.picture_defects` refuses the whole snapshot for it.
* **Traceable.** The id carries the strategy that owns the trade, so a row in
  §9's Plane-1 log can be read without a second table.

NOT GUARANTEED, stated rather than left to be discovered:

* **Not durable across a restart.** The sequence starts from `start` on every
  construction, so a process restart re-issues ids already used in a previous
  life. §12.1 makes every synthetic state in-memory and §4's cold start refuses
  to adopt inherited positions, so no trade survives to collide — but the day a
  position DOES span a restart, this counter is one of the things that has to
  change, and `EntryOrderOrigins` refusing a collision is what will say so.
* **Not globally unique.** Two Risk Engines minting concurrently would produce
  the same ids. The system is one Limiter (§5's single-threaded loop, §9's sole
  writer), so this is scope rather than luck; it is written down because a second
  engine would break it silently.
"""

from __future__ import annotations

import itertools
from typing import Protocol, runtime_checkable

from nixrisk.positions import EntryOrderOrigins, TradeIdMint, identity_trade_id
from nixrisk.seam import ProposedOrder, Side, StopMode

# R0903 (too-few-public-methods): `TradeIdMintPort` is re-declared as a
# single-verb Protocol for the reason `fill_seam` declares it — a mint is one
# verb, and the narrowness IS the property. A second verb would make it a policy
# object that also does something else.
# pylint: disable=too-few-public-methods

#: The id's leading token. A prefix alone is NOT what makes the mint
#: non-identity — a `client_order_id` could be spelled this way too — so the
#: guarantee is enforced by the equality check inside `mint`, not by this string.
#: It exists so a human reading a log can tell which key they are looking at.
TRADE_ID_PREFIX = "TRD"

#: Width of the zero-padded sequence number. Eight digits is ~100M trades in one
#: process lifetime against an intraday-only system (§6.1b) that opens tens per
#: day; the padding is for sortability in a log, and overflow simply widens the
#: field rather than wrapping, so no id is ever reused by rollover.
_SEQ_WIDTH = 8

#: How many synthetic orders `_refuse_degenerate` mints against a candidate
#: policy. TWO, and not one: one probe can prove a mint is not the identity, and
#: it CANNOT prove the mint is injective — a constant mint passes every
#: single-order probe and collides every pair. The collision is the failure §3
#: cannot survive, so the probe population is the smallest one that can see it.
_PROBE_ORDERS = 2


class JoinError(RuntimeError):
    """A join policy this system refuses to run in production. Always says why."""


class CollapsedJoin(JoinError):
    """A mint returned the `client_order_id` it was given (or was asked to).

    The architect ruling on D3.177 keeps `trade_id` and `client_order_id`
    DISTINCT. This is the refusal that makes the ruling structural rather than a
    convention: the collapse is caught at the moment it would happen, naming the
    order and the value, not discovered later as a table whose two keys turned
    out to be one.
    """


class CollidingMint(JoinError):
    """A mint produced ONE `trade_id` for TWO distinct orders.

    §3:159 keys the position table by `trade_id`, so two rows under one key is a
    table that is not keyed by it — the defect `picture.picture_defects` refuses
    a whole snapshot for. `EntryOrderOrigins.record` catches it at record time
    too; this catches it at CONSTRUCTION time, before a single live order has
    been given an id nobody can un-issue.
    """


@runtime_checkable
class TradeIdMintPort(Protocol):
    """How a `trade_id` is minted from the order that opened it (D3.177).

    Structurally identical to `fill_seam.TradeIdMintPort` and deliberately NOT
    imported from it: `fill_seam` is the FILL HANDLER's seam and this module is
    not on the fill path — it is consulted at APPROVAL, which is the one moment
    `trade_id`, `client_order_id` and `strategy_id` are known together. Importing
    the fill seam here would make the approval path depend on the fill path for a
    type, which is the coupling the narrow-port convention exists to avoid. Both
    are `runtime_checkable` Protocols over one verb, so anything satisfying one
    satisfies the other by construction.
    """

    def mint(self, order: ProposedOrder) -> str:
        """This order's `trade_id`. NEVER equal to `order.client_order_id`."""


class SequencedTradeIdMint:
    """The PRODUCTION mint: `TRD-<seq>-<strategy_id>`. Non-identity, injective.

    Stateful on purpose. A stateless mint would have to derive the id from the
    order's own fields, and every such derivation is either a hash (unreadable in
    a log, and a collision nobody can predict) or a function of the
    `client_order_id` (which re-creates the coupling this module exists to break:
    a derived id moves whenever the order id moves, so the two keys are still one
    fact wearing two names).

    The sequence is the whole injectivity argument and it is the reason this is a
    class rather than a function: a counter that lives in a module global would be
    shared by every registry in the process, and a test constructing a second
    origins registry would silently continue the first one's numbering.
    """

    def __init__(self, *, prefix: str = TRADE_ID_PREFIX, start: int = 1) -> None:
        #: Human-facing only. See `TRADE_ID_PREFIX` — it is not the guarantee.
        self._prefix = prefix
        self._seq = itertools.count(start)
        #: How many ids this mint has issued. An observable, for the reason
        #: `EntryOrderOrigins.recorded` is one: a minting policy that cannot say
        #: what it has issued can only be believed, not measured.
        self.issued = 0

    def mint(self, order: ProposedOrder) -> str:
        """Mint this order's `trade_id`, refusing to return the id it was given.

        The equality check is INSIDE the mint rather than in the caller because
        the caller is the thing that would be trusted otherwise. A `prefix` set to
        the empty string and a `client_order_id` spelled `-00000001-strat` is a
        contrived collapse; it is also the only kind that ever happens, and it
        raises here instead of publishing a table keyed by an alias of the order.
        """
        trade_id = (
            f"{self._prefix}-{next(self._seq):0{_SEQ_WIDTH}d}-{order.strategy_id}"
        )
        if trade_id == order.client_order_id:
            raise CollapsedJoin(
                f"minting a trade_id for order {order.client_order_id!r} produced "
                f"{trade_id!r}, which IS that order's client_order_id — D3.177's "
                "ruling keeps the two keys DISTINCT, and an equality that holds "
                "by construction is one no observation can ever contradict, so "
                "every round-trip gate over it would pass on every input"
            )
        self.issued += 1
        return trade_id


def _probe_order(index: int) -> ProposedOrder:
    """One synthetic order for `_refuse_degenerate`. Never placed, never sized.

    Deliberately spelled with a token no live `client_order_id` uses, so a probe
    can never be mistaken for an order in a log, and so the probe's own id cannot
    coincide with a real one and turn a genuine collapse into a green.
    """
    return ProposedOrder(
        client_order_id=f"PROBE-MINT-{index}",
        strategy_id=f"probe-strategy-{index}",
        symbol="PROBE",
        side=Side.LONG,
        qty=1,
        margin_per_contract=1.0,
        stop_ticks=1,
        stop_mode=StopMode.FIXED,
        signal_ts=0.0,
    )


def _refuse_degenerate(mint: TradeIdMint) -> tuple[str, ...]:
    """DRIVE the candidate policy and refuse it if it collapses or collides.

    A BEHAVIOURAL probe, and that is the load-bearing choice. Comparing the
    candidate against `positions.identity_trade_id` by identity would be defeated
    by `lambda order: order.client_order_id` written anywhere else in the tree,
    by `functools.partial`, and by a subclass — the property being refused is what
    the policy DOES, so what is measured is what it does.

    Returns the ids the probe minted, so a caller can put them in evidence rather
    than assert that a check ran.
    """
    minted: list[str] = []
    for index in range(_PROBE_ORDERS):
        order = _probe_order(index)
        value = mint(order)
        if not isinstance(value, str) or not value:
            raise CollapsedJoin(
                f"the candidate mint returned {value!r} for probe order "
                f"{order.client_order_id!r} — §3:159 keys the position table by "
                "trade_id, and a blank or non-string key collides every row"
            )
        if value == order.client_order_id:
            raise CollapsedJoin(
                f"the candidate mint returned {value!r} for probe order "
                f"{order.client_order_id!r}, which is the client_order_id it was "
                "given — this is positions.identity_trade_id's behaviour, and "
                "D3.177's architect ruling forbids it in production. The "
                "degenerate mint is kept as documentation of the scope in which "
                "the bijection holds; it may not be the policy that runs"
            )
        minted.append(value)
    if len(set(minted)) != len(minted):
        raise CollidingMint(
            f"the candidate mint produced {sorted(minted)} for "
            f"{_PROBE_ORDERS} DISTINCT probe orders — two orders under one "
            "trade_id makes §3:159's position table stop being keyed by it, and "
            "picture.picture_defects refuses a whole snapshot for exactly that"
        )
    return tuple(minted)


def _as_callable(mint: TradeIdMintPort | TradeIdMint | None) -> TradeIdMint:
    """Normalise the three ways a policy can arrive into the one thing it is.

    A PORT (an object with `mint`), a bare callable — which is what
    `EntryOrderOrigins` itself takes, and therefore the shape a caller reaching
    for `identity_trade_id` will use — or `None` for this module's own default.
    All three are accepted because refusing the bare callable would leave the
    degenerate policy reachable through the constructor this factory exists to
    replace, which is the hole rather than a narrowing of it.
    """
    if mint is None:
        return SequencedTradeIdMint().mint
    if isinstance(mint, TradeIdMintPort):
        return mint.mint
    if callable(mint):
        return mint
    raise CollapsedJoin(
        f"the production mint {mint!r} is neither a TradeIdMintPort nor a "
        "callable, so it cannot mint anything — §3:159 keys the position table "
        "by trade_id and a registry with no minting policy has no key to publish"
    )


def production_origins(
    *, mint: TradeIdMintPort | TradeIdMint | None = None
) -> EntryOrderOrigins:
    """The ONE constructor the Limiter's approval path calls. Refuses a collapse.

    `EntryOrderOrigins` takes the minting policy as a plain callable and defaults
    it to `identity_trade_id`, which is right for that module — it is the seam,
    and a seam that refused the degenerate case could not document it. **The
    refusal belongs here, at the production wiring point**, and it is the whole
    reason this factory exists rather than a call to the constructor: a default
    that nobody chose becomes the production policy by inaction, and inaction
    leaves no diff.

    The probe runs BEFORE the registry is built, so a degenerate policy never
    reaches a live order at all. It costs `_PROBE_ORDERS` sequence numbers from a
    counting mint, which is why the ids in a log start above `start`; that is a
    visible cost of a real measurement and it is preferred to trusting a name.
    """
    policy = _as_callable(mint)
    if policy is identity_trade_id:
        # Fast, exact, and NOT the guarantee — `_refuse_degenerate` below catches
        # this same policy under any other spelling. Named separately only so the
        # message can say WHICH function was passed, which a probe cannot.
        raise CollapsedJoin(
            "positions.identity_trade_id was passed as the production mint. It "
            "returns order.client_order_id unchanged, which is the hard-coded "
            "equality D3.177's architect ruling forbids; it is retained as the "
            "documented degenerate case and must never be the policy that runs"
        )
    _refuse_degenerate(policy)
    return EntryOrderOrigins(mint=policy)
