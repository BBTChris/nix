"""§12.5's HALT state machine — the six setters, auto-clear, and the marker replay.

Every `§` in this module cites `docs/nics_risk_subsystem_spec_v1.3.md`, the
frozen risk spec, unless another document is named on the same line.

ARC 033 / Stage 1 / sub-agent D. Built BEHIND the wiring that already exists:
`scripts/nixrisk/gate.py` reads `HaltFlagPort.is_set()` as §3:138's **branch 0**,
the first atomic read of the pre-gate (§11:590), before the rule manifest, on
every pass — and `checks/check_limiter_gate.py` ARM 3 already proves that. What
did **not** exist was anything that implements that port: no state, no setter, no
clear, no cooldown, no audited row. This module is that machine, and it changes
neither `gate.py` nor the shape of the port it satisfies.

------------------------------------------------------------------------------
THE SIX SETTERS ARE TRANSCRIBED, NOT DESIGNED (§12.5:631)
------------------------------------------------------------------------------
Verbatim: *"Setters: stale-data, clock-skew, crash-loop, invariant breach,
aggregate-drift, operator."* `HaltCause` is that sentence and nothing else — the
same discipline `TerminalPath` and `FlattenTrigger` are held to in the seam: a
cause the implementation reaches that §12.5 does not name is a finding about the
spec to be REPORTED, never a member quietly added here.

**Which of the six has a producer wired to it today is a measured fact, not a
claim** — see `PRODUCERS` and `AWAITED` below, and `checks/check_halt.py`, which
reads the filesystem rather than this prose.

------------------------------------------------------------------------------
WHY THE FLAG HOLDS A SET OF CAUSES AND NOT ONE SLOT
------------------------------------------------------------------------------
§12.5 names six setters and gives them different clear rules: five may auto-clear
on condition-clear plus a floor; **operator HALT clears only by operator**
(§12.5:633, §12.11:773). A single-slot flag cannot hold both at once, so the
second setter would overwrite the first — and the direction that overwrite fails
is the dangerous one: a stale-data condition clearing would wipe an operator HALT
that no operator ever cleared. The flag is therefore SET while ANY cause is
active and clears only when the LAST one does (directive 4, fail closed).

`is_set()` stays O(1) as §11:590 requires: the `(halted, why)` pair is cached and
recomputed only on a transition, never per pass. Branch 0 runs on every proposal.

------------------------------------------------------------------------------
THE AUTO-CLEAR IS A HYBRID, AND THE SPEC'S SENTENCE IS AMBIGUOUS — STATED
------------------------------------------------------------------------------
§12.5:632: *"Auto-set conditions may auto-clear on condition-clear + minimum
floor (cooldown discipline)."* §4:300 gives the same hybrid for post-protective
cooldown: *"condition-clear AND minimum-time floor"*. Neither says what the floor
is measured FROM. Two readings exist:

  (a) floor from the moment the HALT was SET — a minimum dwell in HALT;
  (b) floor from the moment the CONDITION cleared — an anti-flap cooldown.

This module takes `max(set_ts, condition_cleared_ts) + floor`, which is the
strictest of the two and therefore satisfies both. The argument is not taste: a
cooldown that can expire before the condition even cleared is not a cooldown, and
reading (a) alone permits exactly that on a condition that outlasts the floor. The
ambiguity is reported as CHECK-DEBT rather than resolved silently here.

A condition that RE-ARMS cancels the pending clear (`condition_returned`). Without
that, a feed flapping across the staleness threshold would clear the HALT on the
strength of a gap that had already closed and reopened.

------------------------------------------------------------------------------
THE LIMITER-DOWN CASE (§12.5:634-638) — WHY NO SECOND WRITER IS NEEDED
------------------------------------------------------------------------------
§12.5, verbatim: if a HALT condition arises while the Limiter is unavailable
(e.g. the Risk Engine itself is the crash-looping process) the system is already
**fail-closed** — nothing reaches the broker without the Limiter — so no separate
flag is needed for safety. The `HALT set` row is **booked retroactively at next
boot by cold-start reconciliation**, the same pattern as the Sentinel marker
replay (§12.1:608-614): Plane-1 completeness holds without a second writer.

`HaltMarker` is that marker file and it is built to §12.1's construction: a local
append-only file, one `write(2)` plus one `fsync(2)` per record, no Postgres, no
shared writer, nothing to fail. It is deliberately a STANDALONE object usable by
a process that is not the Limiter, because in the case the spec describes the
Limiter is the dead process. `HaltFlag` writes through it too, BEFORE booking to
Plane 1 and again AFTER (§12.1's *"before and after acting"*), so a set that
reached the marker and not the log — the Limiter died between the two — is
booked at the next boot exactly once.

`replay_markers` is that booking. It goes through the Limiter's OWN `Plane1Port`,
at boot, which is why §9:557's sole-writer invariant and §12.10:736's *"no new
writers, ever"* both stand: the marker file is not Plane 1, and nothing but the
Limiter ever appends to Plane 1.

**A retroactive row is TAGGED.** `source=marker_replay` (§12.1:613 tags the
Sentinel's replayed rows `source=sentinel`), `retroactive=true`, and `booked_at`
carries the boot stamp while the row's own `ts` stays the moment the HALT was
declared. A reader that cannot tell a retroactive booking from a live one cannot
reconstruct when money was actually gated.

------------------------------------------------------------------------------
BOTH PLANES, AND PLANE 2 IS NEVER READ BACK (§12.10:753, §12.10:740)
------------------------------------------------------------------------------
§12.10's event inventory routes *"HALT set / cleared + cause"* to **Plane 1
✅ (added)** — *"it gates money; Limiter-down ⇒ booked at next boot, §12.5"* —
**and Plane 2 ✅**. Both sinks are therefore REQUIRED constructor arguments with
no defaults: a machine that could be built without one would emit half the
inventory row and nothing would disagree.

Plane 2 is *"diagnostic only — never a reconciliation input, never read by the
trading path"* (§12.10:740). So nothing in this module ever READS the Plane-2
sink: `is_set()`, `auto_clear()` and every decision here are computed from
in-memory state, and `checks/check_halt.py` proves it by handing the machine a
Plane-2 double that raises on every verb except `emit`.

------------------------------------------------------------------------------
HALT GATES ENTRY. IT DOES NOT GATE EXIT. (§3:167-174)
------------------------------------------------------------------------------
§3's exit path is `Limiter → broker-order → sender thread → flatten` with ZERO
wire dependency, and it does not pass through the pre-gate at all. A HALT that
also froze exits would strand open positions, which is the opposite of what HALT
is for. Nothing in this module is consulted by `nixrisk.flatten`; the property is
proven by DRIVING a real protective exit while this flag is set, not by asserting
the absence of an import.

The one thing HALT onset DOES touch is §3:173: *"Blackout/HALT onset ⇒ Limiter
cancels all pending ENTRY orders (exits untouched)"*. That sweep is wired here,
on the 0→1 edge only, through the ports below — the executor that performs it
(`nixrisk.flatten.ProtectiveFlatten.cancel_entries_on_onset`) already exists and
already books the release under `TerminalPath.HALT_ONSET` (SPEC-A7). A second
cause arriving while HALT is already set is not an onset and does not re-sweep.

------------------------------------------------------------------------------
WHAT THIS MODULE DOES NOT DO — stated, so no green here implies it
------------------------------------------------------------------------------
* **The Sentinel deadman (§12.1) is NOT built. It is R4-B.** This module borrows
  the marker-replay PATTERN and nothing else. A killed Risk Engine is still an
  unprotected position until the Sentinel exists: synthetic stops die with the
  process holding them.
* **Supervision and the crash-loop breaker (§12.2) LANDED IN ARC 034** (sub-agent
  C), and this bullet says so because it previously said the opposite and the
  gate that reads it was built to redden on exactly this transition.
  `scripts/nixrisk/supervision.py` counts restarts against
  `risks/supervision.config.json`'s two knobs and declares
  `HaltCause.CRASH_LOOP` at the cap, so the cause has a producer now. Read the
  qualifier exactly, because it is the same one every other entry in `PRODUCERS`
  carries: the producer's own output drives this setter end-to-end, and NO unit
  on this box is wired to that producer — adopting it is an `OnFailure=` line
  per unit and is OWED work, not done work.
* **Stale-data and clock-skew conditions are produced elsewhere in this arc** and
  are not in this worktree. The machine accepts them; no detector calls it here.
* **Nothing calls `replay_markers` at boot, because nothing in this tree HAS a
  boot sequence.** §12.5:637 names cold-start reconciliation as the caller;
  `nixrisk.coldstart` was not edited by this arc and the wiring is owed as debt.
* Alert transport (§12.9), the operator control path's authenticated transport
  (§12.11), and the §5 manifest loader are all elsewhere.
"""

from __future__ import annotations

import dataclasses
import enum
import json
import os
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from nixrisk.seam import EventKind, EventRow, Plane1Port, TerminalPath

# duplicate-code: ARC 034's `nixrisk/supervision.py` writes its restart ledger
# with the same append-and-fsync-per-record discipline `HaltMarker` uses, and
# reads it back with the same refuse-rather-than-skip rule. That is the SAME
# construction §12.1:610 fixes ("a local append-only marker file ... nothing to
# fail") applied to a second thing that must survive the process writing it, not
# copied logic. Factoring the two together would put the §12.5 HALT marker and
# the §12.2 restart counter behind one abstraction either could change
# underneath the other.
# pylint: disable=duplicate-code
# pylint: disable=too-many-lines
# The module is over the 1000-line default and the overflow is DOCSTRING, not
# code: §12.5 is nine lines of frozen spec that decide when money stops, and the
# reasoning behind each refusal (which reading of the ambiguous floor sentence,
# why the flag is a SET, why the marker is written before the row) is the part a
# future arc cannot re-derive. Splitting the file to satisfy a line count would
# put the marker in one module and the machine that depends on its ordering in
# another, which is the coupling this file exists to keep visible.

#: The `strategy_id` a system-level Plane-1 row carries. A HALT is declared by
#: the system, not by a strategy — even the operator verb lands at the Limiter
#: (§12.11:784) — so borrowing a real `strategy_id` would attribute a global gate
#: to whichever strategy happened to be running. Same sentinel `coldstart.py`
#: uses, for the same reason.
SYSTEM_ACTOR = "__system__"

#: §12.1:613 tags a replayed Sentinel row `source=sentinel`. A replayed HALT row
#: is tagged with its own source for the same reason: the field is what lets a
#: reader tell a row booked when it happened from a row booked at the next boot.
SOURCE_LIVE = "limiter"
SOURCE_REPLAY = "marker_replay"

#: The §12.11:773 verb name an operator clear is booked under. Spelled once.
OPERATOR_VERB = "HALT clear"


class HaltCause(enum.Enum):
    """§12.5:631's setter list, TRANSCRIBED and closed.

    Verbatim: *"Setters: stale-data, clock-skew, crash-loop, invariant breach,
    aggregate-drift, operator."*

    This enumeration is the SPEC's list, not the implementation's — the rule
    `TerminalPath` and `FlattenTrigger` are held to in `seam.py`. A condition the
    implementation meets that §12.5 does not name is a finding to be reported, not
    a member added here, because deriving the cause set from the code and then
    proving the code covers it is circular and passes while measuring nothing.

    Some of the six name mechanisms produced outside this worktree
    (`STALE_DATA`, `CLOCK_SKEW`) or by a human (`OPERATOR`). Declaring the cause
    fixes the vocabulary; it does not claim the detector. `CRASH_LOOP` was in
    that set until ARC 034 built §12.2's counter. See `PRODUCERS` / `AWAITED`.
    """

    STALE_DATA = "stale_data"
    CLOCK_SKEW = "clock_skew"
    CRASH_LOOP = "crash_loop"
    INVARIANT_BREACH = "invariant_breach"
    AGGREGATE_DRIFT = "aggregate_drift"
    OPERATOR = "operator"

    @property
    def auto_clearable(self) -> bool:
        """May this cause clear without an operator? §12.5:632-633.

        *"Auto-set conditions may auto-clear on condition-clear + minimum floor
        (cooldown discipline). **Operator HALT clears only by operator.**"* The
        asymmetry is the whole rule, so it is a property of the cause rather than
        a condition written at each call site where it could be forgotten once.
        """
        return self is not HaltCause.OPERATOR


#: **MEASURED CLAIMS, not prose.** For each cause, the artifacts in this tree
#: that DETECT the condition today. `checks/check_halt.py` requires every path
#: here to exist under the tree it is judging — so a claim that rots (a module
#: renamed or deleted) reddens instead of quietly becoming false.
#:
#: Read the qualifier exactly: most of these modules produce the SIGNAL and stop
#: there — wiring a detector to a setter means editing that detector, and ARC 033
#: owned none of those files. What the check proves for them is that the
#: DETECTOR'S OWN OUTPUT drives the setter end-to-end, not that the call site
#: exists in production.
#:
#: **TWO ENTRIES ARE NOW STRONGER THAN THAT AND THE DIFFERENCE IS RECORDED RATHER
#: THAN AVERAGED AWAY.** `scripts/nixrisk/supervision.py` (ARC 034) calls
#: `set(CRASH_LOOP, ...)` at §12.2's cap, and `scripts/nixrisk/drift_audit.py`
#: (ARC 035) calls `set(AGGREGATE_DRIFT, ...)` on §11.7 material drift. Those two
#: are call sites in shipped code, not signals awaiting a wire. The blanket
#: sentence that used to stand here — *"None of them calls this machine yet"* —
#: was true when it was written and is now false for two causes, which is exactly
#: the stale restatement directive 3 forbids leaving in place.
#:
#: What is STILL true of all of them, including those two, is one layer up: no
#: daemon in `scripts/` constructs a `HaltFlag` or a `DriftAudit` at all, so a
#: call site here is a call site inside an object graph nothing roots. That bound
#: belongs to the uncalled-entry-point ledger, not to this map.
PRODUCERS: Mapping[HaltCause, tuple[str, ...]] = {
    HaltCause.INVARIANT_BREACH: ("scripts/nixrisk/picture.py",),
    #: ARC 035 / sub-agent D. `drift_audit.py` is §11.7's full-scan reconcile and
    #: it ACTUATES this setter — the first AGGREGATE_DRIFT producer that does.
    #: `survival.py` and `gate.py` remain: both detect a drift of their own and
    #: neither calls `set`, and dropping them because a third arrived would
    #: shrink the claim rather than sharpen it.
    HaltCause.AGGREGATE_DRIFT: (
        "scripts/nixrisk/survival.py",
        "scripts/nixrisk/gate.py",
        "scripts/nixrisk/drift_audit.py",
    ),
    #: ARC 034 / sub-agent C. §12.2's breaker counts restarts against
    #: `risks/supervision.config.json` and calls `set(CRASH_LOOP, ...)` at the
    #: cap. It moved here FROM `AWAITED` because the artifact landed, which is
    #: the re-measurement this pair of maps was built to force.
    HaltCause.CRASH_LOOP: ("scripts/nixrisk/supervision.py",),
}

#: **The other half of the same measurement, and the more important half.** For
#: each cause with NO detector, the artifact that would carry one. The check
#: requires every path here to be ABSENT — so the day supervision lands, this
#: gate goes red and the claim below must be re-measured rather than aging into a
#: false statement of coverage.
#:
#: `STALE_DATA` and `CLOCK_SKEW` are produced by another sub-agent of this arc,
#: in another worktree. `OPERATOR`'s "producer" is a human, and §12.11's
#: authenticated transport that carries the verb to the Limiter does not exist
#: either. `CRASH_LOOP` LEFT THIS SET in ARC 034 — see `PRODUCERS`.
AWAITED: Mapping[HaltCause, tuple[str, ...]] = {
    HaltCause.STALE_DATA: ("scripts/nixrisk/staleness.py",),
    HaltCause.CLOCK_SKEW: ("scripts/nixrisk/clock.py",),
    HaltCause.OPERATOR: ("scripts/nixrisk/operator.py",),
}


class HaltError(RuntimeError):
    """Base for every refusal this machine raises. Never caught internally."""


class OperatorHaltPersists(HaltError):
    """An attempt to clear an operator HALT by any route but an operator.

    §12.5:633 / §12.11:773: *"Operator HALT clears only by operator."* Raised —
    not returned, not silently skipped — because the caller that asks is a
    condition producer or an auto-clear sweep, and a refusal it cannot see is a
    refusal it will retry forever without anyone learning why.
    """


class ConditionStillActive(HaltError):
    """A clear attempted while the condition that set the HALT is still live."""


class CooldownNotElapsed(HaltError):
    """A clear attempted before the §12.5:632 minimum floor had run."""


class NotHalted(HaltError):
    """A clear for a cause that is not currently set."""


class KnobError(ValueError):
    """A §12A-shaped tunable outside its admissible range. Raised at construction."""


class MarkerError(HaltError):
    """The §12.1-pattern marker file could not be written or could not be read.

    Raised rather than swallowed. The marker exists precisely for the case where
    the Limiter dies before Plane 1 sees the row; a marker write that failed
    quietly would leave that case with no record at all, which is the sole-writer
    gap §12.1:608 exists to close.
    """


@dataclasses.dataclass(frozen=True)
class HaltRecord:
    """One active cause, as the machine holds it.

    `condition_cleared_ts` is `None` while the condition is still live. It is a
    stamp rather than a bool because the §12.5:632 floor is measured against it.
    """

    cause: HaltCause
    reason: str
    set_ts: float
    condition_cleared_ts: float | None = None


@dataclasses.dataclass(frozen=True)
class HaltTransition:  # pylint: disable=too-many-instance-attributes
    # Eight fields, and each is one fact §12.5:633's audit needs: the cause, the
    # verb, the reason, the stamp, whether the flag is still set afterwards,
    # whether a row was booked, whether the booking was retroactive, and whether
    # the §3:173 onset sweep ran. A frozen value type with no behaviour; the
    # threshold is about behavioural classes accreting state.
    """One audited set or clear (§12.5:633: *"every set/clear is an audited event
    with reason"*).

    `booked` is False exactly when nothing changed — a re-set of an already-active
    cause. That is not a transition and it does not get a Plane-1 row: §9's log is
    append-only and one row per TRANSITION, and a polling producer that re-asserted
    a live condition every second would otherwise bury the real edges.
    """

    cause: HaltCause
    action: str
    reason: str
    ts: float
    halted_after: bool
    booked: bool
    retroactive: bool = False
    swept: bool = False


# ---------------------------------------------------------------------------
# The collaborators (injected, never constructed here)
# ---------------------------------------------------------------------------
#
# R0903 (too-few-public-methods) disabled: each is a Protocol declaring exactly
# the surface §12.10 or §3:173 gives it. A second verb would be a port doing two
# jobs.
# pylint: disable=too-few-public-methods


@runtime_checkable
class Plane2Port(Protocol):
    """§12.10:737's operational plane. One structured line per event.

    Structurally satisfied by `scripts/nixverify/plane2.py`'s `Plane2`, and
    declared here rather than imported so the risk path takes no dependency on
    the verifier package. **Write-only by contract** (§12.10:740: diagnostic
    only, never a reconciliation input, never read by the trading path) — this
    module never calls anything on it but `emit`.
    """

    def emit(self, event: str, **fields: Any) -> str:
        """Emit one structured operational line. The return is not consulted."""


@runtime_checkable
class PendingEntriesPort(Protocol):
    """Where the pending ENTRY orders §3:173 cancels on onset are listed."""

    def pending_entries(self) -> Sequence[Any]:
        """Every pending ENTRY order. Exits are not in this set and never are."""


@runtime_checkable
class OnsetSweepPort(Protocol):
    """§3:173's onset sweep. Structurally `ProtectiveFlatten` — not imported.

    Declared with the shape the existing executor already has so the real one
    satisfies it without an edit to `flatten.py`. The `cause` argument is a
    `TerminalPath`, supplied by this module as `HALT_ONSET` (SPEC-A7) so the
    reservation release records the HALT and not a blackout.
    """

    def cancel_entries_on_onset(self, cause: Any, pending: Sequence[Any]) -> Any:
        """Cancel every pending ENTRY order under `cause`. Exits untouched."""


# ---------------------------------------------------------------------------
# The §12.1-pattern marker (the Limiter-down case, §12.5:634-638)
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class MarkerEntry:
    """One line of the marker file. `rec` is `set` or `booked`.

    **`boot` and `seq` TOGETHER identify a record. ARC 034 (D3.195).**

    `seq` alone does not, and the file is append-only ACROSS PROCESSES: the case
    §12.5:634 describes is the Limiter dying, so the second writer of this file
    is by construction a different process from the first. `HaltFlag._seq` starts
    at 0 in every one of them, so boot 1's first HALT and boot 2's first HALT
    both write `seq=1`. `replay_markers` matched `set` against `booked` on `seq`
    alone, which made boot 1's `booked` suppress boot 2's UNBOOKED `set` — a
    HALT that was declared, never reached Plane 1, and was then discarded by the
    very function §12.5:637 names as the thing that recovers it. `marker.archive`
    then renamed the evidence away. Measured: two boots, one collision, ZERO rows
    replayed where one was owed.
    """

    rec: str
    cause: HaltCause
    reason: str
    ts: float
    seq: int
    #: The identity of the PROCESS that wrote this record. Opaque and unordered
    #: — nothing compares two boot ids, they are only ever tested for equality,
    #: so a random token is the whole requirement and a counter would need a
    #: durable home that the crash this file exists for could take with it.
    boot: str

    @property
    def key(self) -> tuple[str, int]:
        """The identity a `booked` record must share with the `set` it books."""
        return (self.boot, self.seq)


class HaltMarker:
    """A local append-only marker file. §12.1:610's construction, for §12.5:637.

    *"a local append-only marker file (timestamp, trigger cause, symbols, broker
    acks) before and after acting — no Postgres, no shared writer, nothing to
    fail."*

    Deliberately dependency-minimal and deliberately STANDALONE: in the case
    §12.5:634 describes, the Limiter is the dead process, so the writer of this
    file may be a different process entirely. Every record is one `write(2)`
    followed by one `fsync(2)` — durable before the call returns, because a
    marker that is still in the page cache when the process is killed records
    nothing. That cost is paid on a rare event, never on the hot path.

    This file is **not Plane 1**. Nothing here is the event log, nothing here is
    read by the trading path, and the only thing that ever turns a marker into a
    Plane-1 row is `replay_markers`, running through the Limiter's own port
    (§9:557, §12.10:736 — no new writers, ever).
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise MarkerError(
                f"cannot create marker directory for {self.path}: {exc!r}"
            ) from exc

    def record_set(
        self, cause: HaltCause, reason: str, ts: float, seq: int, boot: str
    ) -> None:
        """The BEFORE half: the HALT was declared. Durable before this returns."""
        self._append("set", cause, reason, ts, seq, boot)

    def record_booked(self, cause: HaltCause, ts: float, seq: int, boot: str) -> None:
        """The AFTER half: the row reached Plane 1 alive, so replay must not re-book.

        Without it, a set that DID reach the log would be booked a second time at
        the next boot, and §9's append-only record would carry two HALTs where one
        happened. The pair `(set, booked)` is what makes the replay idempotent, and
        it is exactly §12.1's *"before and after acting"*.

        **`boot` is passed for the same reason `seq` is (ARC 034, D3.195): the
        pair is the identity.** A `booked` carrying only `seq` books whichever
        `set` happens to share that integer, and across two boots that is not the
        one it belongs to.
        """
        self._append("booked", cause, "", ts, seq, boot)

    def _append(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, rec: str, cause: HaltCause, reason: str, ts: float, seq: int, boot: str
    ) -> None:
        line = (
            json.dumps(
                {
                    "rec": rec,
                    "cause": cause.value,
                    "reason": reason,
                    "ts": ts,
                    "seq": seq,
                    "boot": boot,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        except OSError as exc:
            raise MarkerError(f"cannot open marker {self.path}: {exc!r}") from exc
        try:
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        except OSError as exc:
            raise MarkerError(f"cannot append to marker {self.path}: {exc!r}") from exc
        finally:
            os.close(fd)

    def entries(self) -> tuple[MarkerEntry, ...]:
        """Every parsable record, in file order. A damaged line is REPORTED, not
        repaired: `MarkerError` names it, because discarding it would destroy the
        only evidence that a HALT was declared (§9's crash-gap reasoning)."""
        if not self.path.exists():
            return ()
        try:
            blob = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            raise MarkerError(f"cannot read marker {self.path}: {exc!r}") from exc
        found: list[MarkerEntry] = []
        for index, line in enumerate(blob.splitlines()):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                found.append(
                    MarkerEntry(
                        rec=str(raw["rec"]),
                        cause=HaltCause(raw["cause"]),
                        reason=str(raw["reason"]),
                        ts=float(raw["ts"]),
                        seq=int(raw["seq"]),
                        # REQUIRED, never defaulted. ARC 034 (D3.195): a record
                        # with no boot id cannot be told apart from a record of
                        # a different boot that shares its `seq`, which is the
                        # whole defect. Defaulting it to `""` would put every
                        # legacy record into one shared identity space and
                        # rebuild the collision quietly; a missing key is a
                        # `KeyError` -> `MarkerError`, which is loud and is the
                        # direction this file already fails in for a damaged
                        # line.
                        boot=str(raw["boot"]),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise MarkerError(
                    f"{self.path}:{index + 1} is not a marker record ({exc!r}) — "
                    "refusing to skip it: a HALT that was declared and cannot be "
                    "parsed is exactly the row §12.5:637 exists to recover"
                ) from exc
        return tuple(found)

    def archive(self, now: float) -> Path:
        """Archive the marker once replayed (§12.1:613: *"then archives the marker"*).

        A rename, never a delete: the marker is the only evidence of what the dead
        process saw, and directive 6 (append history, never rewrite banked
        evidence) applies to it as much as to the log it fed.
        """
        target = self.path.with_name(f"{self.path.name}.{now:.6f}.replayed")
        try:
            self.path.rename(target)
        except OSError as exc:
            raise MarkerError(f"cannot archive marker {self.path}: {exc!r}") from exc
        return target


def replay_markers(
    marker: HaltMarker, plane1: Plane1Port, now: float
) -> tuple[EventRow, ...]:
    """§12.5:637's retroactive booking. Runs at NEXT BOOT, through the sole writer.

    *"The `HALT set` row is booked retroactively at next boot by cold-start
    reconciliation, same pattern as the Sentinel marker replay (§12.1):
    Plane-1 completeness holds without a second writer."*

    Each `set` record with no matching `booked` record is a HALT the machine
    declared and the log never received — the Limiter died in between — and it is
    booked here with:

      * the row's `ts` = **when the HALT happened**, not now. A retroactive row
        that carried the boot time would move a money-gating event by however long
        the box was down;
      * `source=marker_replay` and `retroactive=true` — the tag §12.1:613 gives
        the Sentinel's replayed rows, so a reader can tell the two apart;
      * `booked_at` = the boot stamp, so the delay itself is on the record.

    A `set` that DOES have a `booked` partner is skipped: it reached Plane 1 while
    the process lived, and booking it again would put two HALTs in an append-only
    log where one happened. Then the marker is archived, so a second boot replays
    nothing.

    Returns the rows booked — empty when there was nothing to recover, which is
    the ordinary case and is not an error.
    """
    entries = marker.entries()
    if not entries:
        return ()
    # ARC 034 (D3.195): keyed on `(boot, seq)`, not on `seq`. See `MarkerEntry`.
    booked = {entry.key for entry in entries if entry.rec == "booked"}
    rows: list[EventRow] = []
    for entry in entries:
        if entry.rec != "set" or entry.key in booked:
            continue
        row = EventRow(
            kind=EventKind.HALT_SET,
            ts=entry.ts,
            strategy_id=SYSTEM_ACTOR,
            reason=entry.reason,
            fields={
                "cause": entry.cause.value,
                "source": SOURCE_REPLAY,
                "retroactive": "true",
                "booked_at": repr(now),
                "marker": str(marker.path),
                "seq": str(entry.seq),
                # ARC 034 (D3.195). The replayed row carries the boot it was
                # DECLARED in, so §9's reader can attribute a retroactive HALT
                # to the process that saw it rather than to the one that
                # recovered it. Without this the log holds two rows whose only
                # distinguishing field is a per-process counter that restarts.
                "boot": entry.boot,
            },
        )
        plane1.enqueue(row)
        rows.append(row)
    plane1.sync_to_disk()
    marker.archive(now)
    return tuple(rows)


# ---------------------------------------------------------------------------
# The machine
# ---------------------------------------------------------------------------


class HaltFlag:  # pylint: disable=too-many-instance-attributes
    # Nine attributes: four injected sinks/ports (plane1, plane2, marker, and the
    # onset pair), the validated floor map, the clock, the active-cause table and
    # the cached (halted, why) pair branch 0 reads. None is incidental state —
    # each is one thing §12.5, §12.10 or §3:173 names.
    """§12.5's global HALT flag. Satisfies the frozen `gate.HaltFlagPort`.

    Construct once at boot; single-threaded, like everything else the Limiter's
    §5 event loop owns. `is_set()` is the only verb on the hot path and it is one
    attribute load (§11:590).

    Deliberately NOT a subclass of `HaltFlagPort`. A `Protocol`'s method bodies
    are docstrings, so inheriting it means a verb this class forgot to override
    returns `None` — and a HALT flag whose `is_set()` answered `None` reads as
    *not halted* and would look like a working gate while gating nothing.
    Conformance is proven by driving the real `GatePass` against this object.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        plane1: Plane1Port,
        plane2: Plane2Port,
        floors: Mapping[str, float],
        marker: HaltMarker | None = None,
        onset: OnsetSweepPort | None = None,
        pending: PendingEntriesPort | None = None,
        clock: Callable[[], float] = time.time,
        boot_id: str | None = None,
    ) -> None:
        """Both planes are REQUIRED; the marker and the onset sweep are declared.

        §12.10:753 routes `HALT set / cleared + cause` to Plane 1 **and** Plane 2,
        so a machine constructible without either would emit half the inventory
        row with nothing disagreeing. `floors` is validated here rather than read
        lazily: §12A:801 requires an invalid tunable set to be rejected *"before
        any strategy registers"*, and a floor discovered missing at clear time
        would default to zero — an auto-clear with no cooldown at all.
        """
        self._plane1 = plane1
        self._plane2 = plane2
        self._marker = marker
        self._onset = onset
        self._pending = pending
        self._clock = clock
        self._floors = _validated_floors(floors)
        self._active: dict[HaltCause, HaltRecord] = {}
        #: Cached so branch 0 is one read (§11:590). Recomputed on transition only.
        self._flag: tuple[bool, str] = (False, "")
        self._seq = 0
        #: ARC 034 (D3.195). This process's identity in the marker file. `_seq`
        #: alone is a PER-INSTANCE counter starting at 0, and the marker is
        #: append-only across the crash §12.5:634 describes, so `seq` is not an
        #: identity there — `(boot_id, seq)` is. Injectable ONLY so a test can
        #: replay two named boots against one file; production takes the random
        #: default, because a boot id that a second process could guess or
        #: reproduce would rebuild the collision it exists to prevent.
        self._boot_id = boot_id if boot_id is not None else uuid.uuid4().hex
        if (onset is None) != (pending is None):
            raise KnobError(
                "the §3:173 onset sweep needs BOTH the executor and the pending-"
                "entry book, or neither: an executor with nothing to sweep would "
                "report a successful cancellation of zero orders on every onset, "
                "which is indistinguishable from a sweep that works"
            )

    # -- the frozen port ----------------------------------------------------

    def is_set(self) -> tuple[bool, str]:
        """`(halted, why)`. §3:138 branch 0 / §11:590's first atomic read.

        One attribute load. Nothing is computed, nothing is polled, no sink is
        read — in particular Plane 2 is never consulted here (§12.10:740: never
        read by the trading path).
        """
        return self._flag

    # -- the setters (§12.5:631) --------------------------------------------

    def set(
        self, cause: HaltCause, reason: str, *, now: float | None = None
    ) -> HaltTransition:
        """Declare a HALT under one of §12.5's six causes. Audited, both planes.

        Order of operations, and each step is chosen for the failure it survives:

        1. **the marker first** (§12.1:610's *before*), so a process killed at any
           later point still leaves the evidence `replay_markers` needs;
        2. the flag flips — money is gated from this instant, before any I/O the
           log path might block on;
        3. §3:173's onset sweep, on the 0→1 EDGE ONLY: pending ENTRY orders are
           cancelled, exits are untouched;
        4. the Plane-1 row (§9:553, §12.10:753) and the Plane-2 line;
        5. **the marker again** (§12.1's *after*), recording that the row reached
           the log, so the next boot does not book it twice.

        A re-set of an already-active cause updates nothing and books nothing: it
        is not a transition (see `HaltTransition.booked`). A DIFFERENT cause
        arriving while HALT is already set is a real transition, is booked, and
        does not re-sweep — §3:173's onset is the entry into HALT, and there are no
        pending entries to cancel once branch 0 is already denying them.
        """
        stamp = self._clock() if now is None else now
        detail = reason.strip() or (
            f"{cause.value}: HALT declared with no reason — §12.5:633 requires "
            "every set to be an audited event WITH reason"
        )
        if cause in self._active:
            return HaltTransition(
                cause=cause,
                action="reaffirmed",
                reason=detail,
                ts=stamp,
                halted_after=True,
                booked=False,
            )
        was_halted = self._flag[0]
        self._seq += 1
        seq = self._seq
        if self._marker is not None:
            self._marker.record_set(cause, detail, stamp, seq, self._boot_id)
        self._active[cause] = HaltRecord(cause=cause, reason=detail, set_ts=stamp)
        self._refresh()
        swept = False
        if not was_halted:
            swept = self._sweep_pending_entries()
        self._book(EventKind.HALT_SET, cause, detail, stamp, swept=swept)
        if self._marker is not None:
            self._marker.record_booked(cause, stamp, seq, self._boot_id)
        return HaltTransition(
            cause=cause,
            action="set",
            reason=detail,
            ts=stamp,
            halted_after=True,
            booked=True,
            swept=swept,
        )

    # -- the condition's own lifecycle (§12.5:632) --------------------------

    def condition_cleared(self, cause: HaltCause, now: float | None = None) -> float:
        """A producer reports its condition has ENDED. Starts the floor running.

        This does NOT clear the HALT. §12.5:632's rule is a hybrid — condition
        -clear AND a minimum floor — so the condition ending is one of two
        necessary facts and neither alone is sufficient.

        Refused for `OPERATOR`: §12.5:633 gives an operator HALT no condition that
        can clear, and accepting the call would let a producer start a cooldown
        that would eventually clear a HALT only an operator may clear.
        """
        stamp = self._clock() if now is None else now
        record = self._require_active(cause)
        if not cause.auto_clearable:
            raise OperatorHaltPersists(
                "operator HALT has no auto-clearing condition: §12.5:633 / "
                "§12.11:773 — 'Operator HALT clears only by operator'. Refusing "
                "to start a cooldown that would clear it without one"
            )
        self._active[cause] = dataclasses.replace(record, condition_cleared_ts=stamp)
        return self.eligible_at(cause) or stamp

    def condition_returned(self, cause: HaltCause) -> None:
        """The condition RE-ARMED before the floor ran out. Cancels the pending clear.

        Without this the machine would clear on the strength of a gap that had
        already closed and reopened — a feed flapping across the staleness
        threshold would auto-clear a HALT that its own condition had just re-set.
        """
        record = self._require_active(cause)
        self._active[cause] = dataclasses.replace(record, condition_cleared_ts=None)

    def eligible_at(self, cause: HaltCause) -> float | None:
        """The earliest instant `cause` may auto-clear, or `None` if it may not.

        `max(set_ts, condition_cleared_ts) + floor` — the strictest reading of
        §12.5:632, which satisfies both readings of an ambiguous sentence (see the
        module docstring). `None` for an operator HALT and for a cause whose
        condition is still live: in neither case is there an instant at which it
        becomes eligible.
        """
        record = self._active.get(cause)
        if record is None or not cause.auto_clearable:
            return None
        if record.condition_cleared_ts is None:
            return None
        return max(record.set_ts, record.condition_cleared_ts) + self._floors[cause]

    # -- the clears (§12.5:632-633) -----------------------------------------

    def auto_clear(self, now: float | None = None) -> tuple[HaltTransition, ...]:
        """Sweep every AUTO-set cause whose condition cleared and whose floor ran.

        `OPERATOR` is not a candidate and is not skipped by a condition that
        happens to be false — `HaltCause.auto_clearable` excludes it structurally,
        so no rewrite of this loop's predicate can accidentally admit it.

        Returns every transition it made, which may be empty. Clearing the last
        auto cause while an operator HALT stands leaves the flag SET, and the
        returned transitions say so in `halted_after`.
        """
        stamp = self._clock() if now is None else now
        made: list[HaltTransition] = []
        for cause in list(self._active):
            if not cause.auto_clearable:
                continue
            eligible = self.eligible_at(cause)
            if eligible is None or stamp < eligible:
                continue
            made.append(
                self._clear(
                    cause,
                    (
                        f"{cause.value}: auto-cleared — condition cleared at "
                        f"{self._active[cause].condition_cleared_ts!r} and the "
                        f"§12.5:632 minimum floor {self._floors[cause]!r}s elapsed "
                        f"(eligible at {eligible!r}, now {stamp!r})"
                    ),
                    stamp,
                    by_operator=False,
                )
            )
        return tuple(made)

    def clear_by_operator(
        self, cause: HaltCause, reason: str, *, now: float | None = None
    ) -> HaltTransition:
        """§12.11:773's `HALT clear` verb — the ONLY route that clears `OPERATOR`.

        It also clears an auto cause, because an operator override of a machine
        decision is exactly what the verb is for, and §12.8's anti-lockout review
        requires every blocking condition to have a defined exit. What it does NOT
        do is pretend the condition ended: the row records an operator clear, and
        the condition producer is free to set the HALT again on its next poll.
        """
        stamp = self._clock() if now is None else now
        self._require_active(cause)
        detail = reason.strip() or (
            f"{OPERATOR_VERB}: cleared by operator with no reason — §12.5:633 "
            "requires every clear to be an audited event WITH reason"
        )
        return self._clear(cause, detail, stamp, by_operator=True)

    def clear(
        self, cause: HaltCause, reason: str, *, now: float | None = None
    ) -> HaltTransition:
        """Clear ONE auto-set cause, refusing every way it would be premature.

        Three refusals, each naming what is not yet true:
        `OperatorHaltPersists` (§12.5:633 — use `clear_by_operator`),
        `ConditionStillActive` (the condition never reported clear), and
        `CooldownNotElapsed` (the §12.5:632 floor has not run). Directive 4: a
        clear this machine cannot justify is a refusal, never a silent success.
        """
        stamp = self._clock() if now is None else now
        self._require_active(cause)
        if not cause.auto_clearable:
            raise OperatorHaltPersists(
                f"{cause.value}: §12.5:633 / §12.11:773 — 'Operator HALT clears "
                "only by operator'. This route is the auto-clear path; the "
                "operator verb is clear_by_operator()"
            )
        eligible = self.eligible_at(cause)
        if eligible is None:
            raise ConditionStillActive(
                f"{cause.value}: the condition has not reported clear, so the "
                "§12.5:632 hybrid is unsatisfied — condition-clear AND a minimum "
                "floor, and neither alone is sufficient"
            )
        if stamp < eligible:
            raise CooldownNotElapsed(
                f"{cause.value}: the §12.5:632 minimum floor "
                f"{self._floors[cause]!r}s has not elapsed — eligible at "
                f"{eligible!r}, now {stamp!r}"
            )
        return self._clear(cause, reason, stamp, by_operator=False)

    # -- evidence -----------------------------------------------------------

    def active(self) -> tuple[HaltCause, ...]:
        """Every cause currently holding the flag set, in the order it was set."""
        return tuple(self._active)

    def record(self, cause: HaltCause) -> HaltRecord | None:
        """One active cause's record, or `None`."""
        return self._active.get(cause)

    @property
    def floors(self) -> Mapping[HaltCause, float]:
        """The validated §12.5:632 floors, by cause. Read-only."""
        return dict(self._floors)

    @property
    def sweep_wired(self) -> bool:
        """Is §3:173's onset sweep wired? False means an onset cancels NOTHING."""
        return self._onset is not None

    # -- internals ----------------------------------------------------------

    def _require_active(self, cause: HaltCause) -> HaltRecord:
        record = self._active.get(cause)
        if record is None:
            raise NotHalted(
                f"{cause.value} is not set (active: "
                f"{tuple(c.value for c in self._active)!r})"
            )
        return record

    def _clear(
        self, cause: HaltCause, reason: str, stamp: float, *, by_operator: bool
    ) -> HaltTransition:
        """The ONE place a cause leaves the active set. Every clear is audited."""
        detail = reason.strip() or f"{cause.value}: cleared"
        del self._active[cause]
        self._refresh()
        self._book(
            EventKind.HALT_CLEARED,
            cause,
            detail,
            stamp,
            by_operator=by_operator,
        )
        return HaltTransition(
            cause=cause,
            action=OPERATOR_VERB if by_operator else "cleared",
            reason=detail,
            ts=stamp,
            halted_after=self._flag[0],
            booked=True,
        )

    def _refresh(self) -> None:
        """Recompute the cached branch-0 pair. The ONLY writer of `_flag`."""
        if not self._active:
            self._flag = (False, "")
            return
        why = "; ".join(
            f"{record.cause.value}: {record.reason}" for record in self._active.values()
        )
        self._flag = (True, f"global HALT (§3:138 branch 0, §12.5) — {why}")

    def _sweep_pending_entries(self) -> bool:
        """§3:173: HALT onset cancels pending ENTRY orders. Exits are untouched.

        Returns whether a sweep ran. `False` when the sweep is not wired, and that
        distinction rides the Plane-1 row (`onset_sweep`) rather than being
        invisible: an onset that cancelled nothing because nothing was wired must
        not read like an onset that found nothing to cancel.

        **`TerminalPath` is imported at MODULE scope and that is load-bearing.**
        It was written as a deferred import first, and the gate caught it on the
        first run: a check loads this module out of `ctx.nix_home` and then
        RESTORES `sys.path` and purges `sys.modules`, so an import that runs at
        CALL time re-imports `nixrisk.seam` from whichever tree is on the path by
        then. The two `TerminalPath` enums are then different objects, the
        executor's `cause not in _ONSET_CAUSES` membership test fails, and a HALT
        onset raises `NotAnOnsetCause` — a live defect produced entirely by the
        import site. Deferred imports of seam values are banned here for that
        reason, not for style.
        """
        if self._onset is None or self._pending is None:
            return False
        self._onset.cancel_entries_on_onset(
            TerminalPath.HALT_ONSET, tuple(self._pending.pending_entries())
        )
        return True

    def _book(  # pylint: disable=too-many-arguments
        self,
        kind: EventKind,
        cause: HaltCause,
        reason: str,
        stamp: float,
        *,
        swept: bool | None = None,
        by_operator: bool | None = None,
    ) -> None:
        """One §12.10:753 event on BOTH planes. Plane 1 first — it gates money.

        Plane 1 is `enqueue` only: §9:557's split puts the fsync on the shared-pool
        writer and §11.6 keeps group-commit off the hot path. A HALT set that
        blocked on a disk sync would delay the instant money stops flowing, which
        inverts the priority — the flag has ALREADY flipped by the time this runs.
        """
        fields: dict[str, str] = {
            "cause": cause.value,
            "source": SOURCE_LIVE,
            "retroactive": "false",
            "halted_after": repr(self._flag[0]),
            "active": ",".join(c.value for c in self._active),
        }
        if swept is not None:
            fields["onset_sweep"] = "ran" if swept else "not_wired"
        if by_operator is not None:
            fields["by_operator"] = repr(by_operator)
        self._plane1.enqueue(
            EventRow(
                kind=kind,
                ts=stamp,
                strategy_id=SYSTEM_ACTOR,
                reason=reason,
                fields=fields,
            )
        )
        self._plane2.emit(kind.value, reason=reason, **fields)


def _validated_floors(floors: Mapping[str, float]) -> dict[HaltCause, float]:
    """§12A-shaped boot validation for the §12.5:632 cooldown floors.

    Every auto-clearable cause needs a floor and every floor must be > 0. Both
    directions are refusals at construction (§12A:801-802: reject an invalid set
    *before any strategy registers*):

    * a MISSING floor would be read as zero at clear time, which is an auto-clear
      with no cooldown — the flapping condition §12.5:632 names the floor to stop;
    * an EXTRA key names a cause that cannot auto-clear (`operator`) or no cause
      at all, and a floor that nothing consults is a number a reader will believe.

    `operator` is absent from the map ON PURPOSE and its absence is enforced: a
    floor for a cause that clears only by operator would imply an auto-clear that
    does not exist.
    """
    admissible = {cause.value: cause for cause in HaltCause if cause.auto_clearable}
    unknown = sorted(set(floors) - set(admissible))
    if unknown:
        raise KnobError(
            f"halt cooldown floors name {unknown!r}, which is not an auto-clearing "
            f"§12.5:631 cause (admissible: {sorted(admissible)!r}). 'operator' in "
            "particular clears ONLY by operator (§12.5:633), so a floor for it "
            "would imply an auto-clear that does not exist"
        )
    missing = sorted(set(admissible) - set(floors))
    if missing:
        raise KnobError(
            f"halt cooldown floors are missing {missing!r} — §12.5:632 gives every "
            "auto-set condition a minimum floor, and a missing one reads as zero: "
            "an auto-clear with no cooldown at all"
        )
    validated: dict[HaltCause, float] = {}
    for name, cause in admissible.items():
        value = floors[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise KnobError(f"halt cooldown floor {name!r} is {value!r}, not a number")
        if float(value) <= 0.0:
            raise KnobError(
                f"halt cooldown floor {name!r} = {value!r} — §12.5:632's floor is a "
                "MINIMUM dwell in HALT, and a floor of zero or less is no floor"
            )
        validated[cause] = float(value)
    return validated
