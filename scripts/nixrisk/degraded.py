"""§12.4's ladder, wired to the things it is supposed to move.

Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §12.4 (*Degraded persistence
≠ degraded trading*), §12.9 (the push alert tiers), §12.10 (Plane 1, **Limiter
sole writer, no new writers, ever**), §9 (the event-sourced write path). Subject
of `checks/check_plane1_degraded.py`; driven by `scripts/plane1_degraded_drill.py`.

§12.4, verbatim and entire:

> Postgres outage: WAL buffers, trading continues, operator alerted.
> **Disk-critical** (WAL cannot append) ⇒ HALT new entries — no audit trail, no
> new risk. Open positions remain protected (stops read memory, not disk).

`scripts/nixrisk/wal.py` already keeps those two failures apart. What it cannot
do — because it is the persistence layer and nothing else — is make either of
them REACH anything:

* `Plane1Wal.admits_new_entries()` returning `False` **halts nothing**. §3's
  authoritative pass is `gate.GatePass`, it refuses an order only when its
  `HaltFlagPort` says so, and no implementation of that port has ever read the
  WAL. A disk-critical WAL and a healthy one produced the same gate verdict.
  `PersistenceHaltFlag` is that missing wire, and it is the ONLY thing in this
  module that can stop a trade.
* `Plane1Wal`'s alert is a `(event, detail)` callback with no tier, while §12.9
  is a three-tier push surface whose alerts must carry *"the cause and the
  relevant snapshot values, not just a code"*. `PersistenceAlerts` is the
  adapter, and it reuses `survival.AlertTier` / `survival.Alert` rather than
  minting a second vocabulary for the same spec section.
* Neither `wal_seq` nor `natural_key` — §2.2 of the Plane-1 schema spec, the
  ordering authority and the exactly-once key — is stamped anywhere.
  `Plane1Enqueuer` stamps them, at **enqueue**, which is the only place they can
  be stamped and still be stable across a re-delivery (see below).

---

## THE HALF THAT IS EASY TO GET BACKWARDS, AND THE HALF THAT IS EASY TO FAKE

Backwards: *"Postgres is down, so stop trading."* §12.4 says the opposite, and
`PersistenceHaltFlag` is written so that `SINK_DEGRADED` is **not** a halt — the
branch is on `admits_new_entries()`, which is False in `DISK_CRITICAL` only.

Faked: *"open positions stay protected"*, proven by reading
`Plane1Wal.protective_exit_allowed()`. That method is `return True, "..."` with
no branch in it: it cannot answer False in any state, so an assertion over it is
an assertion over a literal (the `CHECK-A7` shape — a classifier whose output is
a constant decides nothing). This module therefore does **not** offer a
"protective exit permitted" verb at all. The property is proven where it lives:
an armed `stops.StopBook` breached by a price tick, while the WAL is really
disk-critical, in the same process. See the drill's C2 arm.

---

## WHY `wal_seq` AND `natural_key` ARE STAMPED AT ENQUEUE AND NOWHERE ELSE

A re-delivered buffered record must collide with the row already committed. It
can only collide if it presents the SAME `(natural_key, occurred_at)` pair, and
it can only do that if both were fixed when the record was written to the WAL
and then carried inside it. A sink that minted either at flush time would give
the same logical record a different key on the second delivery, the unique index
would never fire, and exactly-once would be structurally impossible while every
test looked fine.

`Plane1Enqueuer` is therefore a `Plane1Port` DECORATOR rather than a new writer:
`ReservationLedger`, `halt`, `flatten`, `recovery` and every other producer keeps
enqueueing exactly as it does today, and gets stamped for free. It adds no
authority to originate a row — §12.10's *"no new writers, ever"* is about who
authors a row, and this authors none.
"""

from __future__ import annotations

# pylint: disable=duplicate-code
# R0801 across this arc's Plane-1 modules pairs their DECLARATION BLOCKS,
# their `psql` subprocess helpers and their scratch-cluster fixtures. That
# shape is REQUIRED, not accidental: §4.2 makes every check independently
# runnable and self-contained, and four sub-agents wrote against the same
# frozen schema in worktrees that could not see each other. The same
# reasoning a dozen existing checks already state at this exact site.
import dataclasses
import enum
import time
from collections.abc import Callable, Mapping
from typing import Final, Protocol, runtime_checkable

from nixrisk.seam import EventRow
from nixrisk.survival import Alert, AlertSink, AlertTier
from nixrisk.wal import PersistenceState, Plane1Wal, recover

# R0903 (too-few-public-methods): `PersistenceStatePort` and `HaltReadPort` are
# single-verb Protocols — DECLARATIONS of the two seams this module reads, and
# nothing else. Same reasoning `wal.py` gives for `CommitSinkPort`.
# pylint: disable=too-few-public-methods

#: §9's documented sentinel for a row with genuinely no trade / no strategy.
#: The schema (`databases/schema/plane1.sql`) makes both columns `NOT NULL` with
#: a non-blank CHECK precisely so that *"this event has no trade"* and *"this
#: row's trade was lost"* cannot be spelled the same way.
NO_TRADE: Final[str] = "-"

#: The field names `Plane1Enqueuer` stamps into `EventRow.fields`. Named
#: constants because the sink reads them back out and a typo on either side
#: would silently produce un-orderable, un-dedupable rows.
WAL_SEQ_FIELD: Final[str] = "wal_seq"
NATURAL_KEY_FIELD: Final[str] = "natural_key"

#: The rule name a persistence-driven denial is attributed to. §3 and §5 both
#: require a denial to NAME the blocking rule.
HALT_RULE: Final[str] = "persistence_disk_critical"


class DegradedError(RuntimeError):
    """A §12.4 wiring operation was refused. Always names what could not be done."""


@runtime_checkable
class PersistenceStatePort(Protocol):
    """The slice of `Plane1Wal` this module reads. Never the whole WAL.

    Declared as a Protocol so the halt flag and the alert adapter can be driven
    against a state the drill puts them in, without either of them acquiring the
    ability to write a Plane-1 row.
    """

    def admits_new_entries(self) -> tuple[bool, str]:
        """§12.4: may the Limiter accept a NEW ENTRY right now? `(ok, reason)`."""

    @property
    def state(self) -> PersistenceState:
        """§12.4's current persistence state."""


@runtime_checkable
class HaltReadPort(Protocol):
    """`gate.HaltFlagPort`'s shape, restated so this module imports no gate.

    `nixrisk.gate` imports the reservation ledger, which imports the seam; this
    module is imported BY the gate's caller and must not import the gate back.
    Conformance is not asserted nominally — `scripts/tests/test_degraded.py`
    proves `PersistenceHaltFlag` satisfies the real `gate.HaltFlagPort` with an
    `isinstance` against the runtime-checkable Protocol itself.
    """

    def is_set(self) -> tuple[bool, str]:
        """`(halted, why)`. §11.5's first atomic read."""


# ---------------------------------------------------------------------------
# The wire from §12.4 to §3's gate
# ---------------------------------------------------------------------------


class PersistenceHaltFlag:
    """§12.4's HALT arm, as the `HaltFlagPort` `gate.GatePass` actually reads.

    `is_set()` is True when, and only when, the WAL cannot append. That is the
    whole of §12.4's halting condition: *no audit trail, no new risk.* A degraded
    SINK is deliberately NOT a halt, and this class is written so that the
    difference is one branch and not a policy sprinkled over call sites.

    `upstream` composes with the operator/invariant HALT flag §12.5 owns, because
    `GatePass` takes exactly one halt port and a system that had to choose
    between them would silence one of them. Upstream is consulted FIRST: an
    operator HALT outranks a machine one, and §12.5 makes operator-HALT clear
    only by operator.
    """

    def __init__(
        self,
        wal: PersistenceStatePort,
        upstream: HaltReadPort | None = None,
    ) -> None:
        if not isinstance(wal, PersistenceStatePort):
            raise DegradedError(
                f"{type(wal).__name__} does not satisfy PersistenceStatePort "
                "(needs admits_new_entries() and state) — a halt flag that "
                "cannot read the persistence state is a halt flag that never "
                "fires, and it would look exactly like one that does"
            )
        if upstream is not None and not isinstance(upstream, HaltReadPort):
            raise DegradedError(
                f"upstream halt port {type(upstream).__name__} declares no "
                "is_set() — §12.5's operator HALT would be DROPPED by this "
                "composition, which is strictly worse than not composing"
            )
        self._wal = wal
        self._upstream = upstream

    def is_set(self) -> tuple[bool, str]:
        """`(halted, why)`. The reason NAMES the rule and carries the cause."""
        if self._upstream is not None:
            halted, why = self._upstream.is_set()
            if halted:
                return True, why
        admits, reason = self._wal.admits_new_entries()
        if admits:
            return False, ""
        return True, f"{HALT_RULE}: {reason}"


# ---------------------------------------------------------------------------
# The wire from §12.4 to §12.9's push tiers
# ---------------------------------------------------------------------------


class TierSource(enum.Enum):
    """Whether a tier is transcribed from §12.9 or DERIVED from §12.4.

    Kept as data rather than a comment because the difference is the difference
    between quoting the spec and making a ruling. Directive 3: an arc that
    silently upgrades a derivation to a transcription is how a spec acquires
    text nobody wrote.
    """

    #: §12.9 names this exact case at this exact tier.
    SPEC_12_9 = "transcribed from §12.9"
    #: §12.9 names no tier for this case; the tier is this module's ruling.
    DERIVED = "DERIVED — §12.9 names no tier for this case"


@dataclasses.dataclass(frozen=True)
class TierRule:
    """One WAL alert event's §12.9 routing, with its provenance and citation."""

    tier: AlertTier
    source: TierSource
    citation: str


#: `Plane1Wal`'s alert vocabulary, routed to §12.9's tiers.
#:
#: `wal_sink_degraded` is TRANSCRIBED: §12.9's Warning list ends with *"Postgres
#: down ⇒ degraded persistence"*, which is this event and no other.
#:
#: `wal_disk_critical` is **DERIVED and that is a finding, not a detail.** §12.9
#: names disk-critical at no tier, and §12.5's setter list (stale-data,
#: clock-skew, crash-loop, invariant breach, aggregate-drift, operator) does not
#: contain it either — yet §12.4 makes it the failure that HALTs new entries.
#: Routed CRITICAL by the fail-closed default: the halting failure of the two
#: cannot be quieter than the non-halting one. Recorded as a spec gap rather
#: than presented as spec text.
ALERT_ROUTING: Final[Mapping[str, TierRule]] = {
    "wal_sink_degraded": TierRule(
        AlertTier.WARNING,
        TierSource.SPEC_12_9,
        "§12.9 Warning: 'Postgres down ⇒ degraded persistence'",
    ),
    "wal_sink_restored": TierRule(
        AlertTier.INFO,
        TierSource.DERIVED,
        "§12.9 names no tier for a RECOVERY; Info is the quietest tier it has",
    ),
    "wal_disk_critical": TierRule(
        AlertTier.CRITICAL,
        TierSource.DERIVED,
        "§12.4: disk-critical HALTs new entries; §12.9 names no tier for it",
    ),
}

#: Anything the routing table does not name. Loud on purpose: an unrecognised
#: persistence alert is raised at the HIGHEST tier rather than dropped or
#: defaulted quiet, because the failure mode of the alternative is an alert
#: about money that nobody was paged for. Fail closed and loud (directive 4).
UNROUTED: Final[TierRule] = TierRule(
    AlertTier.CRITICAL,
    TierSource.DERIVED,
    "UNROUTED persistence event — escalated rather than dropped",
)


class PersistenceAlerts:
    """`wal.AlertFn` -> §12.9 `Alert`. Carries the snapshot, not just a code.

    Callable, so it is passed straight to `Plane1Wal(path, alert=...)` and the
    WAL keeps its one-verb callback. The snapshot is read at EMIT time from the
    bound WAL (and, if bound, the writer's backlog), because §12.9 requires the
    operator to be able to triage *"without logging into the box"* and a tier
    plus an event name is not that.

    `raised` is kept for the drill and for evidence; it is not the alert
    transport, and this class never claims to be one.
    """

    def __init__(self, sink: AlertSink) -> None:
        if not isinstance(sink, AlertSink):
            raise DegradedError(
                f"{type(sink).__name__} declares no emit() — §12.9's alerts "
                "would be constructed and dropped, which is indistinguishable "
                "from a system that never alerted"
            )
        self._sink = sink
        self._wal: PersistenceStatePort | None = None
        self._backlog: Callable[[], int] | None = None
        self.raised: list[Alert] = []

    def bind(
        self,
        wal: PersistenceStatePort,
        *,
        backlog: Callable[[], int] | None = None,
    ) -> None:
        """Attach the WAL (and optionally the writer's backlog) for snapshots."""
        self._wal = wal
        self._backlog = backlog

    def __call__(self, event: str, detail: str) -> None:
        """One `AlertFn` call -> one §12.9 alert at its routed tier."""
        rule = ALERT_ROUTING.get(event, UNROUTED)
        snapshot: dict[str, str] = {
            "cause": detail,
            "tier_source": rule.source.value,
            "citation": rule.citation,
        }
        if self._wal is None:
            snapshot["wal_state"] = "UNBOUND — no persistence state was readable"
        else:
            admits, why = self._wal.admits_new_entries()
            snapshot["wal_state"] = self._wal.state.value
            snapshot["admits_new_entries"] = str(admits)
            snapshot["admits_reason"] = why
        if self._backlog is not None:
            snapshot["backlog_rows"] = str(self._backlog())
        alert = Alert(tier=rule.tier, event=event, detail=detail, snapshot=snapshot)
        self.raised.append(alert)
        self._sink.emit(alert)


# ---------------------------------------------------------------------------
# §2.2's ordering authority and exactly-once key, stamped at enqueue
# ---------------------------------------------------------------------------


class Plane1Enqueuer:
    """A `Plane1Port` decorator that stamps `wal_seq` and `natural_key`.

    NOT a writer. It originates no row: every row it stamps was authored by a
    producer upstream and is handed to the same `Plane1Wal` that producer would
    otherwise have been handed. §12.10's *"no new writers, ever"* is a statement
    about authorship, and wrapping the port adds none.

    `next_seq` resumes from the WAL already on disk, so a restarted Limiter does
    not re-issue sequence numbers that a previous run's rows already carry. Read
    from the FILE (`recover`), never from a counter that died with the process.
    """

    def __init__(self, wal: Plane1Wal, *, next_seq: int | None = None) -> None:
        self._wal = wal
        if next_seq is None:
            next_seq = len(recover(wal.path).rows)
        if next_seq < 0:
            raise DegradedError(f"next_seq must be >= 0, got {next_seq!r}")
        self._next_seq = next_seq

    @property
    def next_seq(self) -> int:
        """The sequence number the next enqueued row will carry."""
        return self._next_seq

    @property
    def wal(self) -> Plane1Wal:
        """The wrapped WAL. For evidence and for the halt flag's state read."""
        return self._wal

    def enqueue(self, row: EventRow) -> None:
        """Stamp `wal_seq` + `natural_key`, then append. Raises what the WAL raises.

        A `DiskCritical` from the WAL propagates UNCHANGED and the sequence is
        NOT consumed: a row that never reached the WAL has no WAL record number,
        and burning a sequence number for it would put a permanent hole in the
        ordering authority that §2.2 says is authoritative.
        """
        seq = self._next_seq
        fields = dict(row.fields)
        fields.setdefault(WAL_SEQ_FIELD, str(seq))
        fields.setdefault(
            NATURAL_KEY_FIELD,
            natural_key(row, seq),
        )
        self._wal.enqueue(dataclasses.replace(row, fields=fields))
        self._next_seq = seq + 1

    def sync_to_disk(self) -> int:
        """Delegate. Durability is an explicit verb and stays the WAL's."""
        return self._wal.sync_to_disk()

    def pending(self) -> int:
        """Delegate. Rows enqueued but not yet durable."""
        return self._wal.pending()


def natural_key(row: EventRow, seq: int) -> str:
    """The event's identity for exactly-once replay (schema spec §2.2).

    Includes `seq` deliberately. Two genuinely distinct events of the same kind
    for the same trade at the same microsecond would otherwise collide and the
    second would be SILENTLY DROPPED by the sink's `ON CONFLICT DO NOTHING` — a
    dedup key that is too coarse loses rows, and losing a Plane-1 row is the
    worst failure this path can have. With the WAL record number in it, the key
    collides on exactly one thing: the same WAL record delivered twice, which is
    §12.4's reconnect case and the one this key exists for.

    A producer that owns a stronger domain identity (a broker execution id, say)
    puts it in `fields['natural_key']` and `Plane1Enqueuer` leaves it alone.
    """
    return (
        f"{row.kind.value}|{row.strategy_id or NO_TRADE}|"
        f"{row.trade_id or NO_TRADE}|{seq}"
    )


def instrumented_wal(
    path: str,
    sink: AlertSink,
    *,
    clock: Callable[[], float] = time.time,
) -> tuple[Plane1Wal, PersistenceAlerts]:
    """Build a WAL whose §12.4 alerts are already routed to §12.9's tiers.

    One call, because the two are mutually referential — the WAL needs the alert
    callback at construction and the callback needs the WAL for its snapshot —
    and a two-step construction leaves a window in which an alert can fire with
    no state to report. Bind the writer's backlog afterwards with
    `alerts.bind(wal, backlog=writer.backlog)`.
    """
    alerts = PersistenceAlerts(sink)
    wal = Plane1Wal(path, alert=alerts, clock=clock)
    alerts.bind(wal)
    return wal, alerts
