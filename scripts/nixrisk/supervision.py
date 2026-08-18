"""§12.2's supervision and the crash-loop breaker — the thing that COUNTS.

ARC 034 / sub-agent C (C1, C3). Authority is the frozen risk spec,
`docs/nics_risk_subsystem_spec_v1.3.md`. Every `§` on any line below cites that
document unless another one is named on the same line.

THE RULE, TRANSCRIBED RATHER THAN PARAPHRASED
---------------------------------------------
§12.2:616-618, whole::

    ### 12.2 Supervision & crash-loop breaker
    Every process systemd-managed with restart policy. **N restarts in M minutes
    ⇒ HALT + operator alert** — never blind restart-into-trading. Boot-flatten
    makes any single restart safe by design.

§4:272-274, the strategy-level cap, locked::

    **Crash-loop cap (locked):** after **3** restarts within a window (window =
    tunable variable), stop relaunching. The strategy is **quarantined — left
    dead and flat, alert raised** — while the rest of the system keeps trading.
    Quarantine is NOT auto-resurrected; return is operator-driven.

`risks/supervision.config.json` shipped in ARC 028 saying outright *"No
supervision unit counts restarts today. These are homes for numbers."* This
module is the counter those numbers were waiting for.

ONE COUNTER, TWO CONSEQUENCES — AND THE SPLIT IS THE SPEC'S, NOT A CHOICE
-------------------------------------------------------------------------
The same two knobs govern two different rules with two different outcomes, and
collapsing them would be wrong in both directions:

* **`BreakerScope.PROCESS`** is §12.2. The subject is a supervised PROCESS. The
  consequence is **HALT + operator alert** — the whole system stops taking new
  risk, because the process that crash-looped may be the one that gates money.
* **`BreakerScope.STRATEGY`** is §4:272-274. The subject is one strategy. The
  consequence is **quarantine + alert and NO HALT**, because §4 is explicit that
  *"the rest of the system keeps trading"*. A HALT here would convert one
  strategy's death into a platform-wide stop, which is the rule inverted.

A `CrashLoopBreaker` therefore REFUSES to be constructed with the wrong
collaborator for its scope: a PROCESS breaker with no HALT flag is a counter
that cannot act, and a STRATEGY breaker holding one is a quarantine that can
stop the whole platform.

THE WINDOW IS THE WHOLE TUNABLE
--------------------------------
A breaker that trips on N restarts EVER has no window, and would quarantine a
strategy that crashed once a month for three months. The window is half-open:
a restart at `t` counts toward a verdict taken at `now` **iff `now - t <
window_s`**. An event exactly `window_s` old has EXPIRED. That boundary instant
is driven from both sides by `scripts/tests/test_supervision.py` and by
`checks/check_supervision.py`, because a boundary nobody drives is a boundary
nobody has measured.

THE COUNTER MUST SURVIVE THE CRASH, WHICH IS WHY IT IS ON DISK
---------------------------------------------------------------
A restart counter held in the memory of the process that is restarting counts to
one, forever. `RestartLedger` is an append-only JSONL file with one `fsync(2)`
per record, the same construction §12.1:610 gives the Sentinel marker and for the
same reason: the writer may be killed immediately after. Two `RestartLedger`
objects over one path are two processes, and the second sees the first's
restarts. `scripts/nix_crash_loop_halt.py` is the systemd-side actuator that
does exactly that.

WHAT THIS MODULE DOES NOT DO, STATED SO A GREEN CANNOT IMPLY IT
----------------------------------------------------------------
* **It installs, enables, starts and reloads nothing.** ARC 034 was not
  authorised to take an outward-facing act on a box that runs a live IB Gateway.
  `scripts/nix-crash-loop-halt@.service` is a unit FILE, gated as a file by
  `checks/check_supervision.py`, and it is not installed. Every unit already on
  this box is unmodified, and adopting the breaker on those units — an
  `OnFailure=` line each — is OWED work, not done work.
* **It books no Plane-1 row itself.** §12.10:756 routes *"crash-loop count / cap
  hit"* to **Plane 2 only**. The HALT it declares is a Plane-1 event, and it is
  booked by `nixrisk.halt` — through the Limiter's sole writer — or, in the case
  §12.5:634-638 describes where the Limiter is the dead process, by a HALT
  MARKER that `halt.replay_markers` books retroactively at next boot.
* **Score handling across death is NOT WIRED here** (re-pointed ARC 037,
  CHECK-DEBT D3.252). §4:275-280 locks it and §6.6:457-461 gives the ranking
  table exactly one writer. Since ARC 036 the mechanism EXISTS —
  `scripts/nixscore/store.py`, `scripts/nixscore/ema.py`,
  `scripts/nixscore/process.py` — and the JOIN does not: this module holds no
  reference to any score store, so quarantining a strategy here removes nothing
  from any ranking table and restoring one returns no archived rows.
  `SCORE_BOUNDARY` states that in the one place it lives, and both gates print
  it. It said the OPPOSITE ("Scoring does not exist in this tree") for one arc
  after it stopped being true, inside a string that ships to the operator.

THE VERDICT MUST SURVIVE THE SUPERVISOR TOO, WHICH IS WHY THERE ARE TWO BOOKS
-----------------------------------------------------------------------------
`RestartLedger` persists the EVIDENCE. `QuarantineLedger` (ARC 037) persists the
VERDICT, and they are not the same durability. ARC 036 measured the gap: three
restarts fsynced, `is_quarantined -> True` on the breaker that counted them, and
a SECOND breaker over the SAME ledger — which is exactly what the next
supervision process constructs at boot — answering `is_quarantined -> False`
while `restarts_in_window` still returned 3 at a cap of 3. §4:274 is *"Quarantine
is NOT auto-resurrected; return is operator-driven"*, and a supervisor restart
was doing the resurrecting, with no operator and no §12.11 verb (CHECK-DEBT
D3.250). The §12.11:779 restore FLOOR had the mirror-image defect: it lived in
`_floors`, so a restart un-did the operator's restore and re-quarantined the
strategy on restarts it had already been forgiven for (D3.251).

Both books are append-only, one `write(2)` + one `fsync(2)` per record, 0600. A
restore SUPERSEDES its quarantine by being appended after it, never by deleting
it (directive 6). `CrashLoopBreaker.__init__` folds the book BEFORE this object
can answer anything, and the §18 refusal text quotes the record's own `seq`,
`reason` and `restarts_in_window`, so the reason cannot contradict the record it
was read from — which is the second half of D3.250 and was measurably false.

`debug.md` §7.12 — THE STANDING QUESTION for `CrashLoopBreaker.record_restart`:
*what would have to be true for this to answer while measuring nothing?*
  1. **No subject ever reaches the cap**, so the tripping branch is dead code.
     CLOSED IN BOTH INSTRUMENTS: the suite and the gate each drive `max` and
     `max + 1` restarts INSIDE the window and require a trip, and each drives the
     falsifier (`_NoWindowBreaker`) to show it loses the property.
  2. **The window is never exercised**, so a breaker with no window passes.
     CLOSED: `max` restarts spread ACROSS the window boundary must NOT trip, and
     the boundary instant itself (`now - t == window_s`, and one epsilon inside)
     is driven from both sides.
  3. **The HALT is asserted by exit code / return value only.** CLOSED: every
     control reads the REASON — the `HaltCause`, the recorded reason string, the
     alert code — never a bare boolean (check contract v2 §11).
  4. **The counter resets on every process start**, so it counts to one forever.
     CLOSED: `RestartLedger` is on disk and `test_supervision.py` drives TWO
     ledger objects over ONE path, which is what a restart looks like.
  4a. **The VERDICT resets on every process start**, so a quarantined strategy
     is auto-resurrected by supervision's own restart. CLOSED ARC 037:
     `QuarantineLedger` is on disk, `__init__` folds it before any read verb
     answers, and `checks/check_quarantine_durability.py` drives the
     reconstruction in a **fresh interpreter process** — not merely a second
     object in this one, which a module-level cache would hide.
  4b. **The restore FLOOR resets on every process start**, so the operator's
     §12.11:779 restore is silently un-done. CLOSED ARC 037 by the same book:
     the floor is a `restore` record, and the fresh-process arm requires the
     POST-restore count.
  4c. **The book is written and never queried**, so durability is proven in a
     table the breaker does not consult. CLOSED: the gate's non-vacuity arm
     proves the SAME book yields NOT-quarantined before the record is written
     and quarantined after, so a constructor that ignored it fails one of the
     two.
  5. **The verdict is read out of the subject.** CLOSED: the gate reads
     `crash_loop_max` / `crash_loop_window_min` from `risks/supervision.config.json`
     — the CONFIG, which is a different artifact from the code being judged — and
     computes the expected trip point from those numbers, so a breaker that
     invented its own cap disagrees with the file.
"""

from __future__ import annotations

import enum
import json
import os
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

from nixrisk.halt import HaltCause

# pylint: disable=too-few-public-methods,too-many-lines
# too-few-public-methods: every Protocol below is a one-verb sink — the operator
# alert and the Plane-2 line. A second method invented to clear a class-shape
# heuristic would be surface this module does not own.
# too-many-lines (C0302): this module is over the 1000-line default and the
# excess is PROSE — the transcribed §12.2 and §4:272-274 rules, the two books'
# rationale, and `debug.md` §7.12's standing question answered inline. Splitting
# the quarantine book into its own module was considered and refused: the book
# and the breaker are one invariant (§4:274's verdict and the object that
# answers it), and a two-file seam would be a place for the fold to be skipped.
# The precedent is checks/check_fill_seam.py and scripts/feed_kill_drill.py.

__all__ = [
    "KNOB_KEYS",
    "QUARANTINE_KIND",
    "QUARANTINE_LEDGER_SUFFIX",
    "RESTORE_KIND",
    "RESTORE_VERB",
    "SCORE_BOUNDARY",
    "AlertSink",
    "BreakerScope",
    "BreakerVerdict",
    "CrashLoopBreaker",
    "Plane2Port",
    "QuarantineLedger",
    "QuarantineRecord",
    "QuarantineState",
    "RestartLedger",
    "RestartRecord",
    "SupervisionKnobError",
    "SupervisionKnobs",
    "SupervisionUsageError",
    "UnitPolicy",
    "read_unit_policy",
]

#: The §12A knob names `risks/supervision.config.json` is the physical home of.
KNOB_KEYS: Final[tuple[str, ...]] = ("crash_loop_max", "crash_loop_window_min")

#: THE SCORE BOUNDARY, stated once and printed by both gates (directive 3).
#:
#: RE-POINTED ARC 037 (sub-agent C, CHECK-DEBT D3.252, first half). The previous
#: text asserted *"Scoring does not exist in this tree, so there is no table to
#: archive from and no EMA to persist"*. That was true when ARC 034 wrote it and
#: is FALSE on disk now — `scripts/nixscore/store.py`, `scripts/nixscore/ema.py`
#: and `scripts/nixscore/process.py` all exist — and it was false in a string
#: that SHIPS TO THE OPERATOR inside the quarantine and restore alerts, which is
#: directive 3's restatement failure in its most expensive location. The absence
#: is re-pointed at what is actually still absent, and NOT widened past it: the
#: mechanism exists, the JOIN does not.
SCORE_BOUNDARY: Final[str] = (
    "score handling across death (§4:275-280: a normal crash-restart PERSISTS "
    "the strategy×symbol realized-P&L history and books no phantom zero; "
    "quarantine ARCHIVES it rather than destroying it, and removes the strategy "
    "from the LIVE ranking table) has a MECHANISM in this tree and NO JOIN. "
    "WHAT EXISTS (measured on disk, ARC 037): scripts/nixscore/store.py's "
    "ScoreStore — durable pair rows keyed (strategy_id, symbol), "
    "archive_strategy / restore_strategy, and a three-valued presence() that "
    "keeps ARCHIVED distinct from ABSENT; scripts/nixscore/ema.py's realized-P&L "
    "EMA; and scripts/nixscore/process.py, §6.6:457-461's sole writer of the "
    "ranking table. WHAT IS ABSENT is the WIRING BETWEEN THE TWO HALVES: this "
    "module holds no reference to any score store, no shipped call site of "
    "ScoreStore.archive_strategy exists at the §4:273 quarantine transition and "
    "none of ScoreStore.restore_strategy at the §12.11:779 restore, so a "
    "strategy quarantined here is NOT removed from any live ranking table and a "
    "strategy restored here does NOT get its archived rows back. CHECK-DEBT "
    "D3.252 owns that missing join. This module WIRES THE LIFECYCLE TRANSITIONS "
    "ONLY — quarantined / not-quarantined and the operator-driven return, both "
    "DURABLE across supervision's own death since ARC 037 (QuarantineLedger) — "
    "and a green over it must never be read as score archival happening"
)

_SITE: Final[str] = "scripts/nixrisk/supervision.py"

#: §12.11:779's `quarantine-restore` — the ONLY way out of quarantine (§4:274:
#: *"Quarantine is NOT auto-resurrected; return is operator-driven"*).
RESTORE_VERB: Final[str] = "quarantine-restore"

#: The quarantine book's default path is the restart ledger's path plus this
#: suffix (ARC 037 seam freeze (c)). Derived rather than configured so that no
#: existing `CrashLoopBreaker` construction site had to change, and so that the
#: two books that describe one subject can never be pointed at two different
#: directories by two different callers.
QUARANTINE_LEDGER_SUFFIX: Final[str] = ".quarantine"

#: The two — and only two — record kinds the quarantine book holds.
QUARANTINE_KIND: Final[str] = "quarantine"
RESTORE_KIND: Final[str] = "restore"


class SupervisionKnobError(ValueError):
    """A tunable set the breaker refuses to run on. Never defaulted."""


class SupervisionUsageError(RuntimeError):
    """A breaker wired in a way its own scope forbids. Loud, never a no-op."""


# ---------------------------------------------------------------------------
# The knobs (§12A, physical home `risks/supervision.config.json`)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SupervisionKnobs:
    """§12A's two supervision tunables as one immutable, validated value.

    Both are §12A knobs BY NAME (`CRASH_LOOP_MAX` = 3 stated outright;
    `CRASH_LOOP_WINDOW`, CC-calibrate), so unlike several of the blackout knobs
    next door neither is a declared Nix addition. The boot validation is the one
    rule the config file declares — `positive.scalars` — restated as executable
    code here rather than trusted: a zero cap quarantines a strategy on its first
    crash and a zero window means no two restarts ever fall in one window, so the
    breaker never trips.
    """

    crash_loop_max: int
    crash_loop_window_min: float

    def __post_init__(self) -> None:
        """§12A:801-802's boot validation, at the object that reads the knobs."""
        if isinstance(self.crash_loop_max, bool) or not isinstance(
            self.crash_loop_max, int
        ):
            raise SupervisionKnobError(
                f"crash_loop_max must be a whole number of restarts, got "
                f"{self.crash_loop_max!r} ({type(self.crash_loop_max).__name__}) "
                "— a fractional cap has no restart it names"
            )
        if self.crash_loop_max <= 0:
            raise SupervisionKnobError(
                f"crash_loop_max must be > 0, got {self.crash_loop_max!r} — a "
                "cap of zero quarantines a strategy on its FIRST crash, before "
                "any loop exists to break (risks/supervision.config.json, "
                "positive.scalars)"
            )
        if not isinstance(self.crash_loop_window_min, (int, float)) or isinstance(
            self.crash_loop_window_min, bool
        ):
            raise SupervisionKnobError(
                f"crash_loop_window_min must be a number of minutes, got "
                f"{self.crash_loop_window_min!r}"
            )
        if self.crash_loop_window_min <= 0:
            raise SupervisionKnobError(
                f"crash_loop_window_min must be > 0, got "
                f"{self.crash_loop_window_min!r} — a window of zero width means "
                "no two restarts ever fall inside one window, so the breaker "
                "never trips and §12.2's 'N restarts in M minutes' becomes a "
                "rule with no M (risks/supervision.config.json, positive.scalars)"
            )

    @property
    def window_s(self) -> float:
        """The window in SECONDS. §12.2:617 spells the rule 'N restarts in M
        minutes', so minutes is the unit on disk and seconds is the unit of every
        clock this module reads; the conversion lives here and nowhere else."""
        return float(self.crash_loop_window_min) * 60.0

    @classmethod
    def from_config(cls, values: Mapping[str, object]) -> SupervisionKnobs:
        """Build from `risks/supervision.config.json`'s VALUE keys. No defaults.

        Takes the plain mapping rather than a `RiskConfigSet` for the reason
        `nixrisk/freshness.py` states: the breaker must be constructible at boot,
        in a test and inside a check, and only one of those three has a validated
        config set in hand. An absent knob is a REFUSAL, never a substituted
        number nobody chose (directive 4).
        """
        missing = [key for key in KNOB_KEYS if key not in values]
        if missing:
            raise SupervisionKnobError(
                f"supervision knobs absent from the loaded config: {missing} — "
                "§12A owns these values and this module holds no default for "
                "either of them"
            )
        raw_max = values["crash_loop_max"]
        raw_window = values["crash_loop_window_min"]
        if isinstance(raw_max, bool) or not isinstance(raw_max, int):
            raise SupervisionKnobError(
                f"crash_loop_max={raw_max!r} is {type(raw_max).__name__}, "
                "expected a whole number of restarts"
            )
        if isinstance(raw_window, bool) or not isinstance(raw_window, (int, float)):
            raise SupervisionKnobError(
                f"crash_loop_window_min={raw_window!r} is "
                f"{type(raw_window).__name__}, expected a number of minutes"
            )
        return cls(crash_loop_max=raw_max, crash_loop_window_min=float(raw_window))


# ---------------------------------------------------------------------------
# The sinks
# ---------------------------------------------------------------------------


@runtime_checkable
class AlertSink(Protocol):
    """§12.2:617's *operator alert*. One verb; the transport is not ours."""

    def alert(self, code: str, message: str) -> None:
        """Raise one operator-visible alert."""


@runtime_checkable
class Plane2Port(Protocol):
    """§12.10:739's ops plane. Diagnostic only — never read by the trading path."""

    def emit(self, event: str, **fields: Any) -> str:
        """Write one structured operational line. Returns the line."""


@runtime_checkable
class HaltPort(Protocol):
    """The §12.5 setter half this module reaches. Satisfied by `halt.HaltFlag`."""

    def set(self, cause: Any, reason: str, *, now: float | None = None) -> Any:
        """Declare a HALT under one of §12.5:631's six causes."""


# ---------------------------------------------------------------------------
# The on-disk restart ledger — it must survive the crash it counts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RestartRecord:
    """One restart of one subject. `seq` is the file's own line ordinal."""

    subject: str
    ts: float
    seq: int
    detail: str = ""


def _append_durable(path: Path, line: str, noun: str) -> None:
    """ONE `write(2)` + ONE `fsync(2)`, 0600, durable before this returns.

    Shared by both books on purpose. §12.1:610's construction is a property of
    the RECORD, not of which book it lands in, and two copies of it would be two
    places for the `fsync` to be dropped from. `noun` is the book's own name so
    the refusal still says which file could not be written.
    """
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    except OSError as exc:
        raise SupervisionUsageError(f"cannot open {noun} {path}: {exc!r}") from exc
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    except OSError as exc:
        raise SupervisionUsageError(f"cannot append to {noun} {path}: {exc!r}") from exc
    finally:
        os.close(fd)


class RestartLedger:
    """An append-only, fsync-per-record restart log. §12.1:610's construction.

    THE POINT OF THE DISK. §12.2's subject is a process that is CRASHING; a
    counter that lives in that process's memory is reset by the very event it
    exists to count, so it reaches one and stays there forever. Every record here
    is one `write(2)` plus one `fsync(2)`, durable before the call returns,
    because a restart still in the page cache when the box loses power was never
    counted. The cost is paid on a rare event and never on the hot path.

    Append-only and never rewritten (directive 6). Pruning is a READ-TIME window
    over the records, not a deletion: the ledger keeps the history and the
    breaker keeps the window.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise SupervisionUsageError(
                f"cannot create restart-ledger directory for {self.path}: {exc!r}"
            ) from exc

    def record(self, subject: str, ts: float, detail: str = "") -> RestartRecord:
        """Append one restart. Durable before this returns."""
        seq = len(self.records()) + 1
        record = RestartRecord(subject=subject, ts=float(ts), seq=seq, detail=detail)
        line = (
            json.dumps(
                {
                    "subject": record.subject,
                    "ts": record.ts,
                    "seq": record.seq,
                    "detail": record.detail,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        _append_durable(self.path, line, "restart ledger")
        return record

    def records(self) -> tuple[RestartRecord, ...]:
        """Every parsable record in file order. A damaged line is REPORTED.

        Never repaired and never skipped: a restart that was written and cannot
        be parsed is exactly the evidence the cap stands on, and discarding it
        would move a strategy back below the cap by losing the count.
        """
        if not self.path.exists():
            return ()
        try:
            blob = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SupervisionUsageError(
                f"cannot read restart ledger {self.path}: {exc!r}"
            ) from exc
        found: list[RestartRecord] = []
        for index, line in enumerate(blob.splitlines()):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                found.append(
                    RestartRecord(
                        subject=str(raw["subject"]),
                        ts=float(raw["ts"]),
                        seq=int(raw["seq"]),
                        detail=str(raw.get("detail", "")),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise SupervisionUsageError(
                    f"{self.path}:{index + 1} is not a restart record ({exc!r}) "
                    "— refusing to skip it: a restart that was counted and "
                    "cannot be read is a crash loop the cap will not see"
                ) from exc
        return tuple(found)

    def since(self, subject: str, floor_ts: float) -> tuple[RestartRecord, ...]:
        """This subject's restarts STRICTLY LATER than `floor_ts`. Half-open."""
        return tuple(
            rec
            for rec in self.records()
            if rec.subject == subject and rec.ts > floor_ts
        )


# ---------------------------------------------------------------------------
# The on-disk QUARANTINE book — the VERDICT must survive the supervisor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QuarantineRecord:  # pylint: disable=too-many-instance-attributes
    # Nine fields because the seam freeze fixes two record shapes over one file
    # and every field is one fact the refusal text has to be able to quote. A
    # frozen value with no behaviour; dropping one would make the reason unable
    # to name the record it came from, which is the D3.250 defect restated.
    """One line of the quarantine book. Two kinds and no more.

    `kind` is `"quarantine"` or `"restore"`. The quarantine kind carries the
    verdict's own `reason`, `restarts_in_window`, `cap` and `window_s`; the
    restore kind carries the `operator` and the `counter_floor` §12.11:779's
    reset is expressed as. `seq` is the file's own line ordinal, so a refusal can
    name WHICH record it read and a reader can tell two identical verdicts apart.
    """

    kind: str
    subject: str
    ts: float
    seq: int
    reason: str = ""
    restarts_in_window: int = 0
    cap: int = 0
    window_s: float = 0.0
    operator: str = ""
    counter_floor: float | None = None


@dataclass(frozen=True)
class QuarantineState:
    """The fold of the whole book: who is quarantined NOW, and every floor.

    `live` maps subject -> the quarantine record that is currently in force.
    `floors` maps subject -> the §12.11:779 counter floor its last restore
    raised. `records_read` is the total line count, carried so that a "not
    quarantined" answer can say how much book it read — an empty book and a book
    with a restore in it are different facts and a verdict must be able to say
    which one it is standing on.
    """

    live: Mapping[str, QuarantineRecord]
    floors: Mapping[str, float]
    records_read: int


class QuarantineLedger:
    """§4:274's verdict, on disk. Append-only, fsync-per-record, 0600.

    THE POINT OF THE DISK, and it is NOT the same point `RestartLedger` makes.
    `RestartLedger` persists the EVIDENCE (how many restarts). This persists the
    VERDICT (that the cap was reached and the subject was quarantined). ARC 036
    measured why both are needed: three restarts fsynced into the restart ledger,
    `is_quarantined` True on the breaker that counted them, and a SECOND breaker
    over the SAME ledger — which is exactly what the next supervision process
    constructs at boot — answering `is_quarantined -> False` while
    `restarts_in_window` still returned 3 at a cap of 3. §4:274 is *"Quarantine
    is NOT auto-resurrected; return is operator-driven"*, and a supervisor
    restart was resurrecting it with no operator and no §12.11 verb
    (CHECK-DEBT D3.250).

    NEVER REWRITTEN. A restore is an APPEND that supersedes, not a deletion
    (directive 6, and the argument `RestartLedger` already makes for restarts):
    the operator's return is itself banked evidence, and a file that erased the
    quarantine to express the restore would leave the operator's act with no
    record anywhere on disk. The fold in `state()` is a READ-TIME replay in file
    order, so the last record for a subject decides.

    A DAMAGED LINE IS REPORTED, NEVER SKIPPED. A quarantine record that was
    written and cannot be read is a resurrection the cap will not see — the same
    failure `RestartLedger.records` refuses, one layer up and worse, because
    losing it re-enables a strategy the operator never asked back.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise SupervisionUsageError(
                f"cannot create quarantine-ledger directory for {self.path}: {exc!r}"
            ) from exc

    @classmethod
    def beside(cls, restart_ledger: RestartLedger) -> QuarantineLedger:
        """The default book for a breaker: `<restart-ledger>.quarantine`.

        Derived from the restart ledger rather than defaulted to a constant path,
        so every existing `CrashLoopBreaker` construction site keeps working and
        two books describing one subject cannot be pointed at two directories.
        """
        return cls(Path(str(restart_ledger.path) + QUARANTINE_LEDGER_SUFFIX))

    # -- writes --------------------------------------------------------------

    # too-many-arguments: six, and every one is a field the seam freeze fixes for
    # the `quarantine` record. Collapsing them into the verdict object would make
    # the ledger depend on the breaker's type, which is the direction that must
    # not exist — the book has to be readable by a process that never built one.
    def record_quarantine(  # pylint: disable=too-many-arguments
        self,
        subject: str,
        ts: float,
        *,
        reason: str,
        restarts_in_window: int,
        cap: int,
        window_s: float,
    ) -> QuarantineRecord:
        """Append the §4:273 quarantine verdict. Durable before this returns."""
        record = QuarantineRecord(
            kind=QUARANTINE_KIND,
            subject=subject,
            ts=float(ts),
            seq=len(self.records()) + 1,
            reason=reason,
            restarts_in_window=int(restarts_in_window),
            cap=int(cap),
            window_s=float(window_s),
        )
        _append_durable(
            self.path,
            json.dumps(
                {
                    "kind": record.kind,
                    "subject": record.subject,
                    "ts": record.ts,
                    "seq": record.seq,
                    "reason": record.reason,
                    "restarts_in_window": record.restarts_in_window,
                    "cap": record.cap,
                    "window_s": record.window_s,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            "quarantine ledger",
        )
        return record

    def record_restore(
        self, subject: str, ts: float, *, operator: str, counter_floor: float
    ) -> QuarantineRecord:
        """Append the §12.11:779 restore. An APPEND, never a deletion."""
        record = QuarantineRecord(
            kind=RESTORE_KIND,
            subject=subject,
            ts=float(ts),
            seq=len(self.records()) + 1,
            operator=operator,
            counter_floor=float(counter_floor),
        )
        _append_durable(
            self.path,
            json.dumps(
                {
                    "kind": record.kind,
                    "subject": record.subject,
                    "ts": record.ts,
                    "seq": record.seq,
                    "operator": record.operator,
                    "counter_floor": record.counter_floor,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            "quarantine ledger",
        )
        return record

    # -- reads ---------------------------------------------------------------

    def records(self) -> tuple[QuarantineRecord, ...]:
        """Every record in FILE ORDER. A damaged line is REPORTED, never skipped."""
        if not self.path.exists():
            return ()
        try:
            blob = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SupervisionUsageError(
                f"cannot read quarantine ledger {self.path}: {exc!r}"
            ) from exc
        found: list[QuarantineRecord] = []
        for index, line in enumerate(blob.splitlines()):
            if not line.strip():
                continue
            found.append(self._parse(line, index + 1))
        return tuple(found)

    def _parse(self, line: str, lineno: int) -> QuarantineRecord:
        try:
            raw = json.loads(line)
            kind = str(raw["kind"])
            if kind not in (QUARANTINE_KIND, RESTORE_KIND):
                raise ValueError(
                    f"kind={kind!r} is neither {QUARANTINE_KIND!r} nor {RESTORE_KIND!r}"
                )
            floor = raw.get("counter_floor")
            return QuarantineRecord(
                kind=kind,
                subject=str(raw["subject"]),
                ts=float(raw["ts"]),
                seq=int(raw["seq"]),
                reason=str(raw.get("reason", "")),
                restarts_in_window=int(raw.get("restarts_in_window", 0)),
                cap=int(raw.get("cap", 0)),
                window_s=float(raw.get("window_s", 0.0)),
                operator=str(raw.get("operator", "")),
                counter_floor=None if floor is None else float(floor),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SupervisionUsageError(
                f"{self.path}:{lineno} is not a quarantine record ({exc!r}) — "
                "refusing to skip it: a quarantine that was written and cannot "
                "be read is a resurrection the cap will not see, and §4:274 "
                "makes the return operator-driven"
            ) from exc

    def state(self) -> QuarantineState:
        """Replay the whole book in file order and return what holds NOW.

        A `quarantine` record puts its subject in force; a `restore` record takes
        it out and raises that subject's counter floor. Last record wins, which
        is what makes an append able to supersede without a rewrite.
        """
        live: dict[str, QuarantineRecord] = {}
        floors: dict[str, float] = {}
        records = self.records()
        for record in records:
            if record.kind == QUARANTINE_KIND:
                live[record.subject] = record
            else:
                live.pop(record.subject, None)
                if record.counter_floor is not None:
                    floors[record.subject] = record.counter_floor
        return QuarantineState(live=live, floors=floors, records_read=len(records))


# ---------------------------------------------------------------------------
# The breaker
# ---------------------------------------------------------------------------


class BreakerScope(enum.Enum):
    """WHAT the cap is counting, which fixes WHAT happens when it is reached.

    Not an implementation convenience: §12.2:616-618 and §4:272-274 are two
    different rules over the same two knobs, and their consequences are opposite
    in the one respect that matters — whether the rest of the platform keeps
    trading.
    """

    #: §12.2:617 — a supervised PROCESS crash-looped. Consequence: HALT + alert.
    PROCESS = "process"
    #: §4:272-274 — one STRATEGY crash-looped. Consequence: quarantine + alert,
    #: and explicitly NO HALT: *"while the rest of the system keeps trading"*.
    STRATEGY = "strategy"


@dataclass(frozen=True)
class BreakerVerdict:  # pylint: disable=too-many-instance-attributes
    # Eleven fields, and every one is a distinct FACT the operator or the
    # sequencer needs: who, which rule, how many, the cap, the window and where
    # it opened, whether it tripped, which of the two consequences was taken,
    # the reason, and the stamps counted. The threshold is about behavioural
    # classes accreting state; this is a frozen value with no behaviour, and a
    # verdict that dropped a field would be a verdict that cannot be checked.
    """What one restart did to the breaker. Every field is a fact, not a code.

    `reason` is present on BOTH answers and not only on the trip (check contract
    v2 §11): a verdict that cannot say what it counted is indistinguishable from
    one that counted nothing.
    """

    subject: str
    scope: BreakerScope
    restarts_in_window: int
    cap: int
    window_s: float
    window_opens_after: float
    tripped: bool
    halted: bool
    quarantined: bool
    reason: str
    #: The timestamps that were INSIDE the window when the verdict was taken.
    counted_ts: tuple[float, ...] = ()


class CrashLoopBreaker:  # pylint: disable=too-many-instance-attributes
    # Eleven attributes: the validated knobs, the scope, the two on-disk books
    # (restarts, and the §4:274 quarantine verdict), the two sinks §12.2:617
    # names (HALT and operator alert), the clock, and the three folded reads of
    # the quarantine book (who is quarantined, the record that says so, and each
    # subject's restore floor). None is incidental — each is one thing §12.2 or
    # §4:272-274 names, and the folded three are one book read three ways.
    """§12.2's N-restarts-in-M-minutes breaker, and §4:272's strategy cap.

    Constructed once at boot per scope. Single-threaded, like everything else
    the Limiter's §5 loop owns; the systemd-side actuator
    (`scripts/nix_crash_loop_halt.py`) is a separate short-lived process and
    shares state ONLY through the on-disk `RestartLedger`, which is why that
    ledger and not an attribute is the counter of record.
    """

    # too-many-arguments: six injected collaborators, keyword-only, and only the
    # clock has a default. A breaker that silently defaulted its HALT flag or
    # its alert sink would count correctly into a black hole.
    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        knobs: SupervisionKnobs,
        scope: BreakerScope,
        ledger: RestartLedger,
        alert: AlertSink,
        plane2: Plane2Port,
        halt: HaltPort | None = None,
        clock: Callable[[], float] = time.time,
        quarantine_ledger: QuarantineLedger | None = None,
    ) -> None:
        """The scope decides which collaborators are REQUIRED, and it refuses.

        A `PROCESS` breaker with no HALT flag is §12.2 with its verb removed: it
        would count to N and write a log line, which is indistinguishable from a
        breaker that works right up until the moment it matters. A `STRATEGY`
        breaker holding one is §4:273 inverted — one strategy's death would stop
        the whole platform, and §4 says in the same sentence that the rest of the
        system keeps trading. Both are refused at construction rather than
        checked at trip time, because §12A:801-802 wants an invalid wiring
        rejected *before any strategy registers*.

        THE QUARANTINE BOOK IS FOLDED IN HERE, BEFORE THIS OBJECT ANSWERS
        ANYTHING. §4:274 — *"Quarantine is NOT auto-resurrected; return is
        operator-driven"* — and a supervision restart is exactly a new breaker
        over the same on-disk state, which is the event the book exists to
        survive (CHECK-DEBT D3.250 / D3.251). `quarantine_ledger` defaults to
        `<restart-ledger>.quarantine` so no existing construction site changes.
        """
        if scope is BreakerScope.PROCESS and halt is None:
            raise SupervisionUsageError(
                f"{_SITE}: a PROCESS-scope breaker needs the §12.5 HALT flag. "
                "§12.2:617 is 'N restarts in M minutes ⇒ HALT + operator alert'; "
                "a breaker that can only alert counts correctly and never stops "
                "the money, which is 'blind restart-into-trading' with a log line"
            )
        if scope is BreakerScope.STRATEGY and halt is not None:
            raise SupervisionUsageError(
                f"{_SITE}: a STRATEGY-scope breaker must NOT hold a HALT flag. "
                "§4:273 quarantines the dead strategy 'while the rest of the "
                "system keeps trading', so declaring a platform-wide HALT for "
                "one strategy's crash loop is that rule inverted"
            )
        self._knobs = knobs
        self._scope = scope
        self._ledger = ledger
        self._alert = alert
        self._plane2 = plane2
        self._halt = halt
        self._clock = clock
        # The annotation is load-bearing to an INSTRUMENT, not only to a reader:
        # `check_uncalled_entry_points` resolves a call's receiver by type, and a
        # conditional expression has none it can read, so `record_quarantine` and
        # `record_restore` classified UNCALLED while being called right here.
        self._quarantine_ledger: QuarantineLedger = (
            QuarantineLedger.beside(ledger)
            if quarantine_ledger is None
            else quarantine_ledger
        )
        #: THE FOLD. Read from disk at construction, before any read verb can
        #: answer. A damaged line raises here rather than being skipped, so a
        #: breaker that cannot read its own book refuses to exist instead of
        #: booting into "nobody is quarantined" (directive 4, fail closed).
        folded = self._quarantine_ledger.state()
        self._quarantined: dict[str, BreakerVerdict] = {
            subject: self._verdict_from_record(record)
            for subject, record in folded.live.items()
        }
        #: subject -> the quarantine RECORD in force, kept beside the verdict so
        #: `may_relaunch`'s §18 reason can quote the book's own `seq`, `reason`
        #: and `restarts_in_window` instead of restating them (D3.250's second
        #: half: the refusal text was measurably false on the same object).
        self._quarantine_records: dict[str, QuarantineRecord] = dict(folded.live)
        #: subject -> a counter floor raised by `restore`. §12.11:779's
        #: *"crash-loop counter resets"*, expressed as a floor rather than a
        #: deletion so the append-only ledger is never rewritten (directive 6)
        #: — and read back off the quarantine book at construction, because a
        #: floor that lived only here UN-DID the operator's restore at the next
        #: supervision restart (CHECK-DEBT D3.251).
        self._floors: dict[str, float] = dict(folded.floors)

    # -- reads ---------------------------------------------------------------

    @property
    def knobs(self) -> SupervisionKnobs:
        """The validated tunables this breaker runs on."""
        return self._knobs

    @property
    def scope(self) -> BreakerScope:
        """Which of the two rules this breaker is."""
        return self._scope

    @property
    def quarantine_book(self) -> QuarantineLedger:
        """The on-disk book §4:274's verdict survives in."""
        return self._quarantine_ledger

    def _verdict_from_record(self, record: QuarantineRecord) -> BreakerVerdict:
        """Rebuild the §4:273 verdict FROM THE BOOK, never from memory.

        Every field is the record's own, so a rebuilt verdict cannot say a
        different number than the line it was read from. `counted_ts` is empty
        and deliberately so: the individual stamps are the RestartLedger's to
        hold, and inventing them here would be this object asserting evidence it
        did not read. `halted` is False because only a STRATEGY-scope breaker
        ever writes this book (§4:273 — the rest of the system keeps trading).
        """
        return BreakerVerdict(
            subject=record.subject,
            scope=self._scope,
            restarts_in_window=record.restarts_in_window,
            cap=record.cap,
            window_s=record.window_s,
            window_opens_after=record.ts - record.window_s,
            tripped=True,
            halted=False,
            quarantined=True,
            reason=record.reason,
        )

    def restarts_in_window(self, subject: str, now: float) -> tuple[RestartRecord, ...]:
        """This subject's restarts inside the window ending at `now`. HALF-OPEN.

        `now - ts < window_s` counts; `now - ts == window_s` has EXPIRED. The
        boundary is stated here because it is the entire tunable: a breaker that
        counted every restart ever would trip on three crashes three months
        apart, and one that dropped the boundary instant would let a crash loop
        walk out of its own window one second at a time.

        A `restore` floor (§12.11:779) is applied here too, so a restored
        subject starts from zero without any record being deleted.
        """
        floor = max(
            now - self._knobs.window_s, self._floors.get(subject, float("-inf"))
        )
        return self._ledger.since(subject, floor)

    def is_quarantined(self, subject: str) -> bool:
        """§4:273 — is this subject left dead and flat, awaiting the operator?"""
        return subject in self._quarantined

    def quarantine_verdict(self, subject: str) -> BreakerVerdict | None:
        """The verdict that quarantined this subject, or None."""
        return self._quarantined.get(subject)

    def may_relaunch(self, subject: str) -> tuple[bool, str]:
        """§4:272 — may the recovery sequencer relaunch this subject?

        `(allowed, reason)` rather than a bare bool: a refusal that cannot say it
        is the crash-loop cap is indistinguishable from a supervisor that simply
        did nothing, and §4:273 requires the operator to be told which it was.
        """
        record = self._quarantine_records.get(subject)
        book = self.quarantine_book.path
        if record is None:
            #: The OLD text here asserted "the cap has not been reached", which
            #: ARC 036 measured returning while the ledger it had just read held
            #: three restarts at a cap of three (D3.250). The claim is replaced
            #: by the fact it is derived from: a quarantine record is written at
            #: exactly the moment the cap is reached, so "no live record in the
            #: book" and "the cap has not been reached, as recorded" are ONE
            #: fact read once, and the reason cannot contradict the record.
            return True, (
                f"{_SITE}: {subject!r} is not quarantined — the quarantine book "
                f"{book} holds NO live '{QUARANTINE_KIND}' record for it "
                f"({len(self._quarantined)} subject(s) quarantined). That record "
                f"is written at the instant the §4:272 cap of "
                f"{self._knobs.crash_loop_max} restart(s) per "
                f"{self._knobs.crash_loop_window_min} min is reached, so its "
                f"absence IS the cap-not-reached fact and not a second claim "
                f"about it"
            )
        return False, (
            f"{_SITE}: {subject!r} is QUARANTINED by quarantine-book record "
            f"seq={record.seq} in {book} (ts={record.ts!r}), which holds "
            f"restarts_in_window={record.restarts_in_window} against cap="
            f"{record.cap} over {record.window_s}s — {record.reason}. §4:274 "
            f"makes quarantine operator-driven and NOT auto-resurrected, so the "
            f"only way back is the §12.11:779 '{RESTORE_VERB}' verb"
        )

    # -- the write path ------------------------------------------------------

    def record_restart(
        self, subject: str, *, now: float | None = None, detail: str = ""
    ) -> BreakerVerdict:
        """Count one restart and decide. THE §12.2 / §4:272 rule, executed.

        Order of operations, each chosen for the failure it survives:

        1. **the ledger first**, fsynced — a process killed at any later point
           still leaves the restart counted, which is the whole reason the
           counter is on disk;
        2. the window is recomputed by READING the ledger back, never from an
           in-memory tally, so a second process's restarts are counted too;
        3. on a trip: the consequence for this scope (HALT for `PROCESS`,
           quarantine for `STRATEGY`), then the operator alert;
        4. the Plane-2 line last, carrying the count either way. §12.10:756 puts
           *"crash-loop count / cap hit"* on Plane 2 ONLY, so every restart is
           observable and not merely the ones that tripped.
        """
        stamp = self._clock() if now is None else float(now)
        self._ledger.record(subject, stamp, detail)
        counted = self.restarts_in_window(subject, stamp)
        tripped = len(counted) >= self._knobs.crash_loop_max
        verdict = self._verdict(subject, stamp, counted, tripped)
        if tripped:
            verdict = self._act(verdict, stamp)
        self._plane2.emit(
            "crash-loop-count",
            subject=subject,
            scope=self._scope.value,
            restarts_in_window=verdict.restarts_in_window,
            cap=verdict.cap,
            window_s=verdict.window_s,
            cap_hit=verdict.tripped,
            halted=verdict.halted,
            quarantined=verdict.quarantined,
        )
        return verdict

    def restore(
        self, subject: str, operator: str, *, now: float | None = None
    ) -> BreakerVerdict | None:
        """§12.11:779's `quarantine-restore`. THE ONLY EXIT FROM QUARANTINE.

        *"relaunch via supervision, re-register, boots to flat like any start;
        archived score rows return to the live ranking table (§6.6); crash-loop
        counter resets."* Two of those three are here — the quarantine is lifted
        and the counter resets, both DURABLY. The third is not wired: a score
        store exists in this tree and nothing joins it to this transition, and
        `SCORE_BOUNDARY` says exactly that (CHECK-DEBT D3.252).

        The counter reset is a NEW FLOOR, not a deletion (directive 6): the
        ledger keeps every record it ever wrote, and this raises the timestamp
        below which they no longer count. Returns the verdict that was lifted, or
        None when the subject was not quarantined.
        """
        floor = self._clock() if now is None else float(now)
        #: THE BOOK FIRST, durable before this returns. ARC 036 measured the
        #: floor living only in this process's memory: the SAME breaker reported
        #: 2 restarts after a restore and a NEW breaker over the same ledger
        #: reported 3 — the pre-restore count, so the operator's restore left no
        #: trace on disk and the strategy was re-quarantined at its next crash by
        #: restarts it had already been forgiven for (CHECK-DEBT D3.251).
        record = self._quarantine_ledger.record_restore(
            subject, floor, operator=operator, counter_floor=floor
        )
        lifted = self._quarantined.pop(subject, None)
        self._quarantine_records.pop(subject, None)
        self._floors[subject] = floor
        self._plane2.emit(
            RESTORE_VERB,
            subject=subject,
            scope=self._scope.value,
            operator=operator,
            was_quarantined=lifted is not None,
            counter_floor=floor,
            quarantine_book=str(self.quarantine_book.path),
            quarantine_book_seq=record.seq,
        )
        self._alert.alert(
            "supervision.quarantine-restore",
            f"{_SITE}: operator {operator!r} restored {subject!r}; §12.11:779 "
            f"resets the crash-loop counter to a floor of {floor!r}, recorded "
            f"DURABLY as {RESTORE_KIND!r} seq={record.seq} in "
            f"{self.quarantine_book.path} — an APPEND that supersedes the "
            f"quarantine record, never a deletion of it (directive 6). "
            f"NOTE — {SCORE_BOUNDARY}",
        )
        return lifted

    # -- internals -----------------------------------------------------------

    def _verdict(
        self,
        subject: str,
        stamp: float,
        counted: Sequence[RestartRecord],
        tripped: bool,
    ) -> BreakerVerdict:
        floor = stamp - self._knobs.window_s
        inside = tuple(rec.ts for rec in counted)
        count = len(inside)
        if tripped:
            reason = (
                f"{_SITE}: CRASH-LOOP CAP HIT — {subject!r} restarted {count} "
                f"time(s) within {self._knobs.crash_loop_window_min} min "
                f"(cap {self._knobs.crash_loop_max}, §12A CRASH_LOOP_MAX / "
                f"CRASH_LOOP_WINDOW, physical home "
                f"risks/supervision.config.json). Restart stamps counted: "
                f"{list(inside)}; the window opens after {floor!r}"
            )
        else:
            reason = (
                f"{_SITE}: {subject!r} has {count} restart(s) inside the "
                f"{self._knobs.crash_loop_window_min} min window (cap "
                f"{self._knobs.crash_loop_max}) — under the cap, so supervision "
                f"relaunches. Stamps counted: {list(inside)}; the window opens "
                f"after {floor!r}"
            )
        return BreakerVerdict(
            subject=subject,
            scope=self._scope,
            restarts_in_window=count,
            cap=self._knobs.crash_loop_max,
            window_s=self._knobs.window_s,
            window_opens_after=floor,
            tripped=tripped,
            halted=False,
            quarantined=False,
            reason=reason,
            counted_ts=inside,
        )

    def _act(self, verdict: BreakerVerdict, stamp: float) -> BreakerVerdict:
        """The consequence for this scope. §12.2:617 or §4:273 — never both."""
        halted = False
        quarantined = False
        if self._scope is BreakerScope.PROCESS and self._halt is not None:
            self._halt.set(HaltCause.CRASH_LOOP, verdict.reason, now=stamp)
            halted = True
            self._alert.alert(
                "supervision.crash-loop-halt",
                f"§12.2:617 — HALT declared under cause "
                f"{HaltCause.CRASH_LOOP.value!r}. {verdict.reason}. Never blind "
                "restart-into-trading",
            )
        else:
            quarantined = True
            #: THE BOOK BEFORE THE ALERT, and durable before either returns. A
            #: supervisor killed between the alert and the book would leave a
            #: quarantine an operator has been told about and no on-disk record
            #: of it, which is §4:274's auto-resurrection with a notification.
            record = self._quarantine_ledger.record_quarantine(
                verdict.subject,
                stamp,
                reason=verdict.reason,
                restarts_in_window=verdict.restarts_in_window,
                cap=verdict.cap,
                window_s=verdict.window_s,
            )
            self._quarantine_records[verdict.subject] = record
            self._alert.alert(
                "supervision.quarantine",
                f"§4:273 — strategy {verdict.subject!r} QUARANTINED: left dead "
                f"and flat, the rest of the system keeps trading. "
                f"{verdict.reason}. Recorded DURABLY as {QUARANTINE_KIND!r} "
                f"seq={record.seq} in {self.quarantine_book.path}, so a "
                f"supervision restart cannot resurrect it. Return is "
                f"operator-driven via the §12.11:779 '{RESTORE_VERB}' verb. "
                f"NOTE — {SCORE_BOUNDARY}",
            )
        acted = BreakerVerdict(
            subject=verdict.subject,
            scope=verdict.scope,
            restarts_in_window=verdict.restarts_in_window,
            cap=verdict.cap,
            window_s=verdict.window_s,
            window_opens_after=verdict.window_opens_after,
            tripped=True,
            halted=halted,
            quarantined=quarantined,
            reason=verdict.reason,
            counted_ts=verdict.counted_ts,
        )
        if quarantined:
            self._quarantined[verdict.subject] = acted
        return acted


# ---------------------------------------------------------------------------
# The systemd side — unit FILES, read as files. Nothing is installed.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UnitPolicy:  # pylint: disable=too-many-instance-attributes
    # Eight fields, each one systemd directive §12.2 constrains plus the file's
    # own path and the raw directive map. A frozen parse result with no
    # behaviour; dropping one would make that directive uncheckable.
    """The §12.2 restart-policy facts of ONE systemd unit FILE.

    A parsed READING of a file on disk, never an assertion about a running
    system: this arc installed, enabled, started and reloaded nothing. Whether
    the unit is loaded by the live manager is a different fact that this object
    deliberately cannot express.
    """

    path: str
    restart: str
    start_limit_interval_s: float | None
    start_limit_burst: int | None
    start_limit_action: str
    on_failure: tuple[str, ...]
    exec_start: tuple[str, ...]
    directives: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def restarts(self) -> bool:
        """Does this unit declare a restart policy at all? §12.2:616."""
        return self.restart not in ("", "no")


_DIRECTIVE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9]*)\s*=\s*(.*?)\s*$")

#: systemd time suffixes this reader understands, in seconds. Deliberately
#: small: the units a `StartLimitIntervalSec=` in this tree may legally use.
_TIME_SUFFIXES: Final[Mapping[str, float]] = {
    "us": 1e-6,
    "ms": 1e-3,
    "s": 1.0,
    "sec": 1.0,
    "m": 60.0,
    "min": 60.0,
    "h": 3600.0,
}


def _parse_seconds(raw: str) -> float | None:
    text = raw.strip()
    if not text:
        return None
    match = re.fullmatch(r"([0-9]*\.?[0-9]+)\s*([A-Za-z]*)", text)
    if match is None:
        return None
    value = float(match.group(1))
    suffix = match.group(2).lower()
    if not suffix:
        return value
    factor = _TIME_SUFFIXES.get(suffix)
    return None if factor is None else value * factor


def _collect(text: str) -> dict[str, list[str]]:
    directives: dict[str, list[str]] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";", "[")):
            continue
        match = _DIRECTIVE.match(stripped)
        if match is None:
            continue
        directives.setdefault(match.group(1), []).append(match.group(2))
    return directives


def _last(directives: Mapping[str, Sequence[str]], key: str, default: str = "") -> str:
    values = directives.get(key)
    return values[-1] if values else default


def read_unit_policy(path: str | os.PathLike[str]) -> UnitPolicy:
    """Parse one unit FILE's §12.2 restart-policy facts. Reads, never installs.

    A deliberately small INI reader rather than `systemd-analyze`: shelling to
    the live manager to learn what a file says would make the reading depend on
    a daemon this arc must not touch, and would answer about the INSTALLED unit
    rather than the file in the tree.
    """
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise SupervisionUsageError(f"cannot read unit file {target}: {exc!r}") from exc
    directives = _collect(text)
    burst_raw = _last(directives, "StartLimitBurst")
    try:
        burst = int(burst_raw) if burst_raw else None
    except ValueError:
        burst = None
    return UnitPolicy(
        path=str(target),
        restart=_last(directives, "Restart"),
        start_limit_interval_s=_parse_seconds(
            _last(directives, "StartLimitIntervalSec")
        ),
        start_limit_burst=burst,
        start_limit_action=_last(directives, "StartLimitAction"),
        on_failure=tuple(directives.get("OnFailure", ())),
        exec_start=tuple(directives.get("ExecStart", ())),
        directives={key: tuple(value) for key, value in directives.items()},
    )


def unit_policy_defects(policy: UnitPolicy, knobs: SupervisionKnobs) -> list[str]:
    """§12.2's requirements over ONE unit file, checked against the KNOBS.

    Both sides are derived: the expected figures come from
    `risks/supervision.config.json` through `SupervisionKnobs`, and the observed
    ones from the unit file. Neither is a literal typed into a gate, so a unit
    whose burst was hand-edited away from the tunable disagrees with the config
    rather than with a number somebody remembered.

    The rules, each with the failure it names:

    * a unit with **no restart policy** is not supervised at all (§12.2:616);
    * `StartLimitBurst` / `StartLimitIntervalSec` must MATCH the two knobs.
      Otherwise systemd's own limiter and this module's breaker count to
      different numbers, and the one that fires first decides — which makes the
      tunable a fiction;
    * `StartLimitAction` must be `none`. Any other value lets systemd take the
      consequence (reboot, poweroff, or a silent `failed` state), and §12.2:617's
      consequence is **HALT + operator alert**, which systemd cannot declare;
    * the unit must route `OnFailure=` at the breaker's actuator, or the cap is
      counted by nobody at the moment the process actually dies.
    """
    defects: list[str] = []
    if not policy.restarts:
        defects.append(
            f"{policy.path}: Restart={policy.restart!r} — §12.2:616 requires "
            "every process to be systemd-managed WITH a restart policy; a unit "
            "that never restarts has no crash loop to break and no boot-flatten "
            "to make the restart safe"
        )
    if policy.start_limit_burst != knobs.crash_loop_max:
        defects.append(
            f"{policy.path}: StartLimitBurst={policy.start_limit_burst!r} but "
            f"risks/supervision.config.json crash_loop_max={knobs.crash_loop_max}"
            " — systemd's limiter and the §12.2 breaker would count to different "
            "numbers and whichever fired first would decide"
        )
    if policy.start_limit_interval_s != knobs.window_s:
        defects.append(
            f"{policy.path}: StartLimitIntervalSec="
            f"{policy.start_limit_interval_s!r}s but "
            f"crash_loop_window_min={knobs.crash_loop_window_min} "
            f"({knobs.window_s}s) — the unit's window and the breaker's window "
            "must be the same window"
        )
    if policy.start_limit_action != "none":
        defects.append(
            f"{policy.path}: StartLimitAction={policy.start_limit_action!r}, "
            "expected 'none' — §12.2:617's consequence is HALT + operator alert, "
            "and systemd can declare neither. Any other action lets the "
            "supervisor take a consequence the risk spec did not choose"
        )
    if not policy.on_failure:
        defects.append(
            f"{policy.path}: no OnFailure= — nothing counts this unit's restarts "
            "at the moment it dies, so the breaker is a counter with no input"
        )
    return defects


def not_installed(units: Iterable[str], system_dir: str = "/etc/systemd/system") -> str:
    """A STATEMENT OF WHAT WAS NOT DONE, measured rather than promised.

    Returns a sentence naming, for each unit file this module ships, whether a
    file of that name is present under the live manager's directory. ARC 034 was
    not authorised to install, enable, start or reload anything on this box —
    it runs a live IB Gateway — so the honest thing is to MEASURE the absence
    and print it, rather than to assert in prose that nothing was touched.

    A read of a directory, and nothing else: no `systemctl`, no `daemon-reload`.
    """
    root = Path(system_dir)
    seen = [name for name in sorted(units) if (root / name).exists()]
    if not seen:
        return (
            f"none of the shipped unit files is present under {system_dir} — "
            "this arc installed, enabled, started and reloaded nothing"
        )
    return (
        f"{seen} IS present under {system_dir}. This arc did not put it there; "
        "re-measure before reading the unit files below as uninstalled"
    )
