#!/usr/bin/env python3
# C0302: the §7.12 block, the ALLOW-SET argument and the per-finding reason
# strings ARE the deliverable — each is a sentence an operator reads out of a
# red verdict — and check contract §4.2 requires a check be independently
# runnable as ONE file.
# pylint: disable=too-many-lines
"""Gate: the Limiter's HOT PATH does cache reads and arithmetic ONLY — I9.

ARC 050. Subject: `scripts/nixrisk/gate.py`, `scripts/nixrisk/stops.py`,
`scripts/nixrisk/reservations.py`, `scripts/nixrisk/picture.py`,
`scripts/nixrisk/loop.py` and `scripts/nixrisk/wal.py`, imported out of
`ctx.nix_home` and DRIVEN under load.

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md` — the frozen risk spec —
unless another document is named on the same line. Spelled out because a file
under `checks/` is read against the check contract by default and the same
section number means different things in the two documents.

ONE gate, ONE property (`nix_check_contract.md` §5.5, doctrine C.9): *the
transitive operation census of the Limiter's hot path lies inside a MEASURED
allow-set, and the expensive work §11 places off that path still runs.*

------------------------------------------------------------------------------
DOCTRINE C.9 — CHECKED BEFORE BUILDING, NOT AFTER
------------------------------------------------------------------------------
Four gates in this tree touch the words "hot path". None owned this property,
and the census was taken before a line of this file was written:

* `check_plane1_hot_path` owns *§11.6 group-commit LATENCY isolation* — a
  four-arm relation in microseconds between a baseline loop, a loop concurrent
  with a real commit, and a synchronous control. It is a TIMING instrument over
  ONE off-path item. It says nothing about what operations the path performs,
  and `docs/CHECK-DEBT.md` D3.400 records that it times a `GatePass` built with
  `ledger=None`, so the shipped approve path's only I/O is outside every timed
  region it measures.
* `check_limiter_gate.arm_hot_path` owns *§11.3's O(1)-in-|positions| SHAPE* —
  traversal and `len` counts against a counting position table, with the
  microsecond figures explicitly excluded from its verdict (D3.39). Traversal
  counts are not an operation census: a pass that opened a socket without
  touching the table satisfies it completely.
* `check_flatten` ARM 6 owns *wire-freedom of the EXIT path* — a `sys.setprofile`
  allow-set over `nixrisk.flatten`. Different subject, different property; this
  gate borrows its ALLOW-SET IDIOM and none of its scope.
* `check_pollers` owns the OTHER side — that §6.4's pollers exist and own the
  caches. That the caches are maintained is its property; that the hot path only
  READS them is this one.

So this is a new instrument for a new property, not a second opinion.

------------------------------------------------------------------------------
THE HOT PATH, DERIVED — never a transcribed list
------------------------------------------------------------------------------
`ENTRY_POINTS` below is not the claim. The claim is ARM 6: the set of entry
points this gate drove must EQUAL the set derived from the subject's own source
by SHAPE. Two derivations, held against each other:

* **per-GO** — the §3 gate decision. Derived as: the public method of
  `gate.GatePass` that a `RulePort` manifest is dispatched through. Found by AST:
  the method of `class GatePass` that contains an `ast.Call` on `rule.evaluate`
  transitively (`evaluate` -> `_dispatch`), plus the daemon's own shipped per-GO
  decision, `loop.LimiterLoop.take_in_flight`, derived as the method of
  `LimiterLoop` that calls `registry.take_in_flight`.
* **per-tick** — §15's `O(positions <= 5)/tick` stop evaluation. Derived as:
  every public method of `stops.StopBook` that iterates `self._by_symbol`, which
  is the bounded loop §15 permits, plus the O(1) precomputed-aggregate reads the
  tick consumes (`reservations.ReservationLedger.total_reserved`,
  `picture.FinancialPictureBook.current`), derived as the methods whose body is a
  single `ast.Return` of an attribute of `self`.

A NEW hot-path callee added later with a forbidden op inside it is the exact
defect, and ARM 6 is what makes the drive's silence about it a FAIL rather than
a shrug.

------------------------------------------------------------------------------
THREE MECHANISMS, BECAUSE ONE IS PROVABLY VACUOUS
------------------------------------------------------------------------------
ARC 038's sub-agent F ran 2,000 real gate evaluations under a PEP-578 audit hook
across three port configurations and recorded **zero events**. `strace -c` over
the same shipped path counted **4,202 `write(2)` for 4,200 approvals**. Both
numbers are correct. `Plane1Wal` opens its handle `open(..., "ab", buffering=0)`
and appends through `_io.FileIO.write` on an ALREADY-OPEN descriptor, and PEP 578
raises no event for that: it audits `open`, not `write`.

**Re-measured at ARC 050 / S1, at the tip this gate was built against**: 2,000
real APPROVALS, PEP-578 events **0**, `/proc/self/io` `syscw` delta **2,000**.
An audit-hook-only purity gate is therefore vacuous BY CONSTRUCTION, and that is
not a hypothesis about this tree — it is a measurement of it.

So three mechanisms, each catching what the others cannot:

1. **`sys.setprofile`** — catches every Python frame ENTERED, so every module
   root and every per-eval import (`importlib._bootstrap` frames). Blind to
   anything below the Python/C boundary.
2. **`sys.addaudithook` (PEP 578)** — catches `open`, `socket.connect`/`bind`,
   `subprocess.Popen`, `exec` and the `os.*` mutators, inside CPython and
   unbypassable. **Blind to `write`/`read` on an already-open descriptor.**
3. **`/proc/self/io` `syscw`/`syscr`** — RAW syscall counts from the KERNEL,
   including on open descriptors. Blind to which call site made them.

Mechanism 3 supplies the count; mechanism 1 supplies the site. Neither alone is
a finding an operator can act on, which is why both are reported.

------------------------------------------------------------------------------
THE ALLOW-SET, AND WHY IT IS NOT A BAN-LIST
------------------------------------------------------------------------------
`debug.md` §7.12 asks what would make this gate PASS while measuring nothing.
The answer for a ban-list is *an expensive operation nobody thought to ban* —
the hole `check_flatten` ARM 6 closed for the exit path and the one this gate
closes for the hot path. So the hot path may enter ONLY `_ALLOWED_ROOTS`, and a
module root outside it is UNCLASSIFIABLE: **CANNOT_MEASURE naming it, never
PASS**. The allow-set is honest because it was MEASURED against the shipped pure
path (six roots on the gate arm, four on the tick arm) rather than granted.

**`nixrisk.wal` is IN the allow-set, and this is the one entry that needs an
argument rather than a measurement.** §11 item 6 reads, verbatim:

    6. **Group-commit** event-log writes off hot path (WAL-buffered).

The operation §11.6 places OFF the hot path is the GROUP-COMMIT — the durable,
batched write to §9's event log. The mechanism by which it is kept off is that
the hot path is *WAL-buffered*: the hot path appends to the WAL, and the
group-commit drains it elsewhere. §11.6 therefore puts the WAL append ON the hot
path by its own words, and `check_flatten` banked the same reading for the exit
path (`_BANNED_ON_EXIT` deliberately omits `nixrisk.wal`: *"a bounded in-process
buffer append is not a wire"*).

That permission is NOT open-ended, and three separate bounds keep it from
becoming the laundering channel:

* **`MAX_WRITES_PER_APPROVAL = 1`.** The shipped path performs exactly one
  `write(2)` per approval. A SECOND write — a log line, a second sink, a
  duplicated emit — is a FAIL, and the count comes from the kernel.
* **`fsync` on the hot path is a FAIL, unconditionally.** `os.fsync` IS the
  group-commit's blocking verb and §11.6's actual prohibition. Measured: 0
  fsyncs across 2,000 approvals; `sync_to_disk` is the only site and ARM 4
  proves it runs OFF the path.
* **ARM 2, the DISCRIMINATOR.** The same gate pass is driven again with the WAL
  replaced by a pure in-memory sink, and the raw write count must fall to
  ZERO. If it does not, something OTHER than the §11.6 buffer append is writing
  and hiding behind the permission. **ARM 2 is what makes ARM 1's allow-set
  honest**, in the same role `check_plane1_hot_path`'s synchronous control plays
  for its timings. A non-zero count there is a FAIL and not a CANNOT_MEASURE,
  and the distinction was MEASURED rather than reasoned: PLANT A puts an `open`
  inside `GatePass.evaluate`, and the first draft of this gate answered it with
  CANNOT_MEASURE because the discriminator fired first. That was wrong. The
  discriminator had POSITIVELY OBSERVED a writer it could name the count of;
  cannot-measure is for what an instrument could not see, never for what it saw.
  ARM 2 reports CANNOT_MEASURE only when it did not drive the same path as ARM 1
  — a discriminator that ran a different pass discriminates nothing.

**NAMED RESIDUAL, not laundered:** `buffering=0` makes the append one syscall
per row rather than one per buffer-full. D3.400 measured the cost of that
(p99 38.4 us, max 1169.8 us) and it stays OPEN debt, owned by the crash-gap
property `check_plane1_crash_gap` holds — bytes in the page cache survive a
process crash; bytes in a Python buffer do not. This gate does not certify that
tail away. It bounds the count at one and reports the number.

------------------------------------------------------------------------------
debug.md §7.12 — what would make this gate PASS while measuring nothing?
------------------------------------------------------------------------------
1. **The path is never exercised.** A census over a drive that denied at rule
   one, or never ran, is silent about everything after it. *Closed:* ARM 1
   requires `MIN_APPROVALS` real APPROVE decisions and a non-zero
   `ledger.total_reserved()`; ARM 3 requires stop states actually returned. A
   drive that denies is CANNOT_MEASURE naming the denying rule. Measured: the
   first draft of this gate's own drill denied all 2,000 evaluations because a
   port double answered the wrong verb, and every "no forbidden op" it printed
   was true and worthless.
2. **The instrument cannot see the operation.** The PEP-578 hole above. *Closed:*
   mechanism 3, from the kernel.
3. **The allow-set is widened until the defect fits.** *Closed:* every entry is
   justified in `_ALLOWED_ROOTS` beside itself, `nixrisk.wal` carries the three
   bounds above, and ARM 2 isolates it.
4. **A forbidden op is reachable only at runtime** — a lazy import behind a
   config file, a conditional socket. *Closed:* the census is DRIVEN, not static;
   a per-eval import shows as `importlib._bootstrap` frames in mechanism 1.
5. **Purity achieved by dropping the work.** A hot path that skipped the WAL
   append entirely would be serenely pure and would have destroyed §9's audit
   trail. *Closed:* ARM 4 asserts the off-path work still HAPPENS — rows made
   durable by `sync_to_disk`, §11.7's full-scan reconcile running and reporting.
6. **The traced entry points are not the real ones.** *Closed:* ARM 6, the
   derived-set equality.
7. **One clean pass is read as the invariant.** *Closed:* every arm drives
   `N`/`M` in the thousands and the census is a UNION over all of them, so a
   forbidden op on one iteration in a thousand is caught.

------------------------------------------------------------------------------
CORRECTABLE = False
------------------------------------------------------------------------------
The subject is WHICH OPERATIONS THE RISK GATE PERFORMS. A gate empowered to edit
it would be manufacturing its own green over the code that decides whether an
order is admitted. The repair for a forbidden op on the hot path is an
ARCHITECTURAL move — the work goes to a poller or an event handler that updates
a cache the hot path reads (§11) — decided by a human against §11, never a
mechanical edit an instrument makes to its own subject.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK and its `standalone_main` footer
# against every other house-style check's. That shape is REQUIRED, not
# accidental duplication (check contract §4.2).
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

#: Nothing must run first. The subjects are imported from the tree under test
#: and no other check produces them.
DEPENDS_ON: tuple[str, ...] = ()
#: Imports the risk package out of `ctx.nix_home` (mutating `sys.path` and
#: `sys.modules` for the load and restoring both), and writes ONE Plane-1 WAL
#: under `/tmp` so the reservation ledger is the REAL one rather than a double —
#: driving the gate with `ledger=None` is precisely D3.400's vacuity and this
#: gate exists partly to close it. Also READS `/proc/self/io`, which is not a
#: contended claim and is not declared (see `scripts/nixverify/observe.py` on why
#: file reads are outside the observed classes).
RESOURCES: tuple[str, ...] = (
    "interpreter:sys.modules",
    "interpreter:sys.path",
    "file-write:/tmp",
)
#: No timeout, no poll, no sleep, no socket. Every drive is in-process.
TIME_BOUND = False
#: NON-CORRECTABLE — see the module docstring's closing section.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is WHICH OPERATIONS THE RISK GATE PERFORMS on the path that "
    "admits an order. The repair for a forbidden op is an ARCHITECTURAL move — "
    "the work goes to a poller or event handler that updates a cache the hot "
    "path reads (§11) — decided by a human against §11, never a mechanical edit "
    "an instrument makes to its own subject"
)
#: The files whose hot-path code this gate judges. Declared (unlike
#: `check_two_phase_entry`'s deliberate emptiness) because this gate does NOT
#: scan the whole tree: it drives six named modules and derives its entry points
#: from three of them, so a SUBJECTS row here names a real artifact this gate
#: measures rather than moving coverage arithmetic (D3.138's honest half).
SUBJECTS: tuple[str, ...] = (
    "scripts/nixrisk/gate.py",
    "scripts/nixrisk/stops.py",
    "scripts/nixrisk/loop.py",
    # ARC 055 / I1 ARC C1. §5:322's price poll, which is NEW hot-path code: the
    # tick now maintains §4's trails and tests for breach on every pass. I9 is a
    # DISCHARGED invariant and this arc's own poll is exactly the way a
    # discharged invariant gets broken silently, so the poll is declared a
    # subject here and DRIVEN by ARM 3c below. A plant inside `StopWatch.poll`
    # must redden this gate, which it cannot do if the file is not its subject.
    "scripts/nixrisk/stopwatch.py",
)

NAME = "check_hot_path_purity"

PACKAGE = "nixrisk"
SCAN_ROOT = "scripts"

_MODULES = (
    "nixrisk.gate",
    "nixrisk.loop",
    "nixrisk.picture",
    "nixrisk.reservations",
    "nixrisk.seam",
    "nixrisk.stops",
    "nixrisk.stopwatch",
    "nixrisk.wal",
)

#: Real GO evaluations per gate arm. Thousands, not one: §0a — a single clean
#: pass is not proof the next GO stays pure, and a forbidden op on one iteration
#: in a thousand is invisible to a single trace.
N_GATE = 2000
#: Real ticks per stop-eval arm.
M_TICK = 2000
#: Below this many real APPROVALS the gate arm measured a path that stopped
#: early — CANNOT_MEASURE, never PASS.
MIN_APPROVALS = 1000
#: §15's bound. The ONE loop the hot path may run.
MAX_POSITIONS = 5
#: §11.6's WAL buffer append, bounded. A SECOND write per approval is a FAIL.
MAX_WRITES_PER_APPROVAL = 1

#: The ONLY module roots the hot path may enter. Derived by MEASUREMENT against
#: the shipped path (ARC 050 / S1), not by permission. Anything else is
#: UNCLASSIFIABLE -> CANNOT_MEASURE naming it. Each entry says why it is here.
_ALLOWED_ROOTS: dict[str, str] = {
    # -- the subject itself ------------------------------------------------
    "nixrisk.gate": "the §3 pass under judgement",
    "nixrisk.stops": "§15's O(positions<=5)/tick stop evaluation",
    "nixrisk.stopwatch": (
        "§5:322's price poll — the ring READ (one dict lookup) and the breach "
        "ENQUEUE. It is on this list because §5:322 puts the price poll on the "
        "loop by its own words; the FIRE it enqueues for is NOT here, and that "
        "is ARM 3c's whole point"
    ),
    "nixrisk.loop": "the daemon's own per-GO one-in-flight decision (§3:140)",
    "nixrisk.reservations": "§3's reservation take and its O(1) running Σ",
    "nixrisk.picture": "§11.3's precomputed snapshot, read as ONE attribute load",
    "nixrisk.seam": "the frozen vocabulary and record types (dataclass __init__)",
    # -- §11.6's sanctioned buffer append ----------------------------------
    "nixrisk.wal": (
        "§11.6's WAL buffer append — the ONE write §11 places ON this path "
        "('group-commit ... off hot path (WAL-buffered)'). Bounded at "
        "MAX_WRITES_PER_APPROVAL, fsync-free, and ISOLATED by ARM 2"
    ),
    # -- stdlib the frozen record types drag in ----------------------------
    "enum": "member value/name lookup on the frozen Decision/Phase/Side enums",
    "dataclasses": "`replace` on a frozen StopState during the §4 ratchet",
    "json": "the WAL row encoder, inside the §11.6 append and nowhere else",
    "abc": "Protocol/ABC machinery under isinstance on a frozen port",
    "typing": "runtime_checkable Protocol dispatch on a frozen port",
    "threading": "`get_ident()` — the loop's single-thread REFUSAL, never a lock",
    "itertools": "the ledger's monotonic reservation-id counter",
    "math": "isfinite/fsum — arithmetic, which is the permitted half of §11",
    # -- the harness itself ------------------------------------------------
    "__main__": "this gate's own drive closures",
    NAME: "this gate's own drive closures when imported by verify.py",
    "checks": "this gate's own drive closures under the package spelling",
}

#: Module roots whose presence on the hot path IS the defect, named so a FAIL
#: can say WHICH class of expensive work it found (check contract rule 11 — the
#: reason is the assertion). This is a SECOND OPINION on top of the allow-set,
#: never the primary mechanism: anything not in `_ALLOWED_ROOTS` is already a
#: finding, and this list only lets the finding say more than "unclassified".
_KNOWN_EXPENSIVE: dict[str, str] = {
    "socket": "a wire on the hot path (§5: the sender thread owns blocking I/O)",
    "select": "a wire on the hot path",
    "selectors": "a wire on the hot path",
    "ssl": "a wire on the hot path",
    "http": "a wire on the hot path",
    "urllib": "a wire on the hot path",
    "zmq": "a wire on the hot path",
    "psycopg": "a DATABASE round trip on the hot path (§11.6 puts it off-path)",
    "sqlite3": "a database round trip on the hot path",
    "subprocess": "a child process on the hot path",
    "multiprocessing": "a child process on the hot path",
    "asyncio": "an event loop on the §5 single-threaded hot path",
    "queue": "a blocking queue on the hot path (§5: the hot loop never blocks)",
    "concurrent": "a blocking future on the hot path",
    "logging": "a formatted log write on the hot path",
    "nixscore": "§11.9's EMA math — the Scoring process owns it, OFF-hot-path",
    "nixbus": "the state bus wire on the hot path (§12.7 publishes off-path)",
    "nixalloc": "the Allocator on the Limiter's hot path",
    "nixrisk.plane1_sink": "§11.6's GROUP-COMMIT sink on the hot path",
    "nixrisk.drift_audit": "§11.7's full-scan reconcile on the hot path",
    "nixrisk.projection": "a WAL replay fold on the hot path",
    "importlib": "a PER-EVAL IMPORT (§5: 'no per-eval import')",
    "time": "a wall-clock sample per evaluation (D3.402) — neither a cache read "
    "nor arithmetic",
}

#: PEP-578 events that are the INSTRUMENT's own, never the subject's work. An
#: audit hook armed while `sys.setprofile` is installed records
#: `object.__getattr__` for the profiler's own `frame.f_code` read; an
#: instrument that observes itself reports noise as a finding. The two censuses
#: are taken in SEPARATE drives for the same reason, and this is belt and braces.
_INSTRUMENT_EVENTS = frozenset(
    {"object.__getattr__", "sys.setprofile", "sys.settrace", "sys._getframe"}
)

#: PEP-578 events that are a FINDING wherever they appear on the hot path.
_FORBIDDEN_EVENTS = (
    "open",
    "socket.",
    "subprocess.",
    "os.mkdir",
    "os.rename",
    "os.remove",
    "os.rmdir",
    "os.chmod",
    "os.link",
    "os.symlink",
    "os.truncate",
    "exec",
    "compile",
    "import",
    "urllib.",
    "ftplib.",
    "smtplib.",
    "sqlite3.",
    "cpython.run_",
)


# ---------------------------------------------------------------------------
# the three mechanisms
# ---------------------------------------------------------------------------


def _syscall_counts() -> tuple[int, int]:
    """`(syscw, syscr)` for THIS process, from the kernel.

    The only mechanism that sees a `write(2)` on an already-open descriptor,
    which is where D3.400's 4,202 writes lived while a PEP-578 hook reported
    zero events over the same path. `/proc/self/io` needs no privilege and no
    child process.
    """
    text = Path("/proc/self/io").read_text(encoding="ascii")
    syscw = syscr = -1
    for line in text.splitlines():
        if line.startswith("syscw:"):
            syscw = int(line.split()[1])
        elif line.startswith("syscr:"):
            syscr = int(line.split()[1])
    if syscw < 0 or syscr < 0:
        raise OSError("/proc/self/io carries no syscw/syscr — cannot count syscalls")
    return syscw, syscr


@dataclasses.dataclass(frozen=True)
class Census:
    """What ONE drive of the hot path did, by all three mechanisms."""

    frames: frozenset[str]
    roots: frozenset[str]
    events: tuple[str, ...]
    writes: int
    reads: int
    raised: BaseException | None


def _roots_of(frames: set[str]) -> set[str]:
    """`nixrisk.gate.GatePass.evaluate` -> `nixrisk.gate`; `json.dumps` -> `json`.

    Two segments for the first-party packages, one otherwise — the same shape
    the allow-set is written in, so classification never needs the qualname.
    """
    roots: set[str] = set()
    for entry in frames:
        parts = entry.split(".")
        if parts[0] in ("nixrisk", "nixbus", "nixalloc", "nixscore", "nixsentinel"):
            roots.add(".".join(parts[:2]))
        else:
            roots.add(parts[0])
    return roots


def _census(drive: Callable[[], None]) -> Census:
    """Drive the hot path once under ALL THREE mechanisms and report.

    The profile census and the audit census are taken in SEPARATE drives, then
    unioned: an audit hook armed under `sys.setprofile` records the profiler's
    own frame reads, and an instrument that observes itself is noise. The
    syscall delta is taken over the AUDITED drive, which carries no profiler
    overhead — a `sys.setprofile` callback that itself touched a file would
    corrupt the count this gate's whole argument rests on.

    A raise is RETURNED, never propagated: on this path a raise is a finding
    about the subject, and a gate that died measured nothing.
    """
    frames: set[str] = set()

    def profile(frame: Any, event: str, arg: Any) -> None:
        del arg
        if event == "call":
            frames.add(
                f"{frame.f_globals.get('__name__', '?')}.{frame.f_code.co_qualname}"
            )

    raised: BaseException | None = None
    previous = sys.getprofile()
    sys.setprofile(profile)
    try:
        drive()
    except BaseException as exc:  # noqa: BLE001  pylint: disable=broad-except
        raised = exc
    finally:
        sys.setprofile(previous)

    events: list[str] = []
    armed = [False]

    def hook(event: str, args: tuple[Any, ...]) -> None:
        if armed[0] and event not in _INSTRUMENT_EVENTS:
            events.append(f"{event}{args!r}"[:160])

    sys.addaudithook(hook)
    before_w, before_r = _syscall_counts()
    armed[0] = True
    try:
        drive()
    except BaseException as exc:  # noqa: BLE001  pylint: disable=broad-except
        raised = raised or exc
    finally:
        armed[0] = False
    after_w, after_r = _syscall_counts()

    return Census(
        frames=frozenset(frames),
        roots=frozenset(_roots_of(frames)),
        events=tuple(events),
        writes=after_w - before_w,
        reads=after_r - before_r,
        raised=raised,
    )


def _forbidden_events(events: tuple[str, ...]) -> list[str]:
    """The PEP-578 events on this census that are findings, deduplicated."""
    found: list[str] = []
    for event in events:
        name = event.split("(")[0]
        if (
            any(name.startswith(prefix) for prefix in _FORBIDDEN_EVENTS)
            and event not in found
        ):
            found.append(event)
    return found


# ---------------------------------------------------------------------------
# loading the tree under judgement
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Loaded:
    """The subject modules, resolved out of the tree under judgement."""

    mods: dict[str, ModuleType]
    home: Path


def load(home: Path) -> tuple[Loaded | None, str]:
    """Import the risk package out of `home`, or say why not. Restores state."""
    scripts = str(home / SCAN_ROOT)
    if not (home / SCAN_ROOT / PACKAGE / "__init__.py").is_file():
        return None, f"no {PACKAGE} package under {home / SCAN_ROOT}"
    saved_path = list(sys.path)
    saved_mods = {k: v for k, v in sys.modules.items() if k.split(".")[0] == PACKAGE}
    for name in list(sys.modules):
        if name.split(".")[0] == PACKAGE:
            del sys.modules[name]
    sys.path.insert(0, scripts)
    try:
        mods = {name: importlib.import_module(name) for name in _MODULES}
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        sys.path[:] = saved_path
        sys.modules.update(saved_mods)
        return (
            None,
            f"cannot import {PACKAGE} out of {home}: {type(exc).__name__}: {exc}",
        )
    finally:
        sys.path[:] = saved_path
    # D3.124 — provenance. `_preamble` leaves the LIVE scripts/ on sys.path, so
    # a missing tree falls through to this checkout and the gate would report on
    # a tree it never read.
    for name, mod in mods.items():
        origin = getattr(mod, "__file__", None)
        if origin is None or not str(Path(origin).resolve()).startswith(
            str(home.resolve())
        ):
            sys.modules.update(saved_mods)
            return None, (
                f"{name} resolved to {origin!r}, which is OUTSIDE the tree under "
                f"judgement ({home}) — the verdict would be about another tree"
            )
    return Loaded(mods=mods, home=home), ""


def unload(saved: dict[str, ModuleType]) -> None:
    """Put `sys.modules` back the way it was found."""
    for name in list(sys.modules):
        if name.split(".")[0] == PACKAGE:
            del sys.modules[name]
    sys.modules.update(saved)


# ---------------------------------------------------------------------------
# the rig — REAL objects, never doubles for the subject
# ---------------------------------------------------------------------------


class _ClearPorts:
    """Every §3 port, answering CLEAR, so the pass reaches `_settle`.

    These are the CACHES §11.1-11.5 says the hot path reads — a tradability
    lookup, a HALT flag, a net-liq mark. A double here is not a double for the
    subject: the subject is the PASS, and a port that answers from a dict is
    exactly what §11 says the shipped port must be. What a port double must NOT
    do is hide work, which is why every one of these is a constant return and
    why ARM 1 asserts the drive really APPROVED.
    """

    def read(self, symbol: str = "") -> tuple[bool, str]:
        """`SymbolFlagPort`/`GlobalFlagPort`: `(blocked, reason)`. Never blocked."""
        del symbol
        return False, ""

    def is_set(self) -> tuple[bool, str]:
        """`HaltFlagPort`: §11.5's global HALT flag, clear."""
        return False, ""

    def in_flight(self, strategy_id: str) -> tuple[bool, str]:
        """`InFlightPort`: §3's one-in-flight lock, free."""
        del strategy_id
        return False, ""

    def mark(self) -> tuple[float, bool]:
        """`NetLiqMarkPort`: §6.5's net-liq mark, fresh and generous."""
        return 10_000_000.0, True


class _MemorySink:
    """A Plane-1 sink that touches NOTHING. ARM 2's discriminator.

    Same verb as `nixrisk.wal.Plane1Wal`, zero syscalls. If ARM 1's write count
    does not fall to zero when the WAL is swapped for this, something other than
    §11.6's buffer append is writing.
    """

    def __init__(self) -> None:
        self.rows: list[Any] = []

    def enqueue(self, row: Any) -> None:
        """The `Plane1Wal` verb, to memory. No descriptor, so no syscall."""
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        """Nothing to make durable — this sink is the ABSENCE of the WAL."""
        return 0

    def pending(self) -> int:
        """Rows held, so a caller can prove this sink really received them."""
        return len(self.rows)


def _order(seam: Any, n: int, mode: Any = None) -> Any:
    return seam.ProposedOrder(
        client_order_id=f"hpp-{n}",
        strategy_id="probe",
        symbol="ES",
        side=seam.Side.LONG,
        qty=4,
        margin_per_contract=1000.0,
        stop_ticks=40,
        stop_mode=mode or seam.StopMode.FIXED,
        signal_ts=1.0,
    )


def _picture(seam: Any) -> Any:
    """A snapshot with room, so no shipped rule denies on the numbers."""
    return seam.FinancialPicture(
        version=7,
        published_ts=1.0,
        balance=1_000_000.0,
        positions=(),
        margin_per_contract={"ES": 1000.0},
        sum_open_margin=0.0,
        sum_reservations=0.0,
        committed=0.0,
        deployable=700_000.0,
    )


def _manifest(gate: Any, ports: Any) -> tuple[Any, ...]:
    return gate.default_manifest(
        blackout=ports,
        tradability=ports,
        staleness=ports,
        clock_skew=ports,
        in_flight=ports,
        net_liq=ports,
        deployable_fraction=0.70,
        survival_safety_pad=0.10,
        coherence_tolerance=1e-6,
    )


# ---------------------------------------------------------------------------
# ARM 6 — the DERIVED entry-point set
# ---------------------------------------------------------------------------


def _methods_of(tree: ast.Module, klass: str, public_only: bool = False) -> list[Any]:
    """Every (Async)FunctionDef defined directly on `class <klass>`.

    Shared by both derivations below so the class walk is written ONCE — two
    copies of it would be two places for the shape to drift, and the shape is
    what ARM 6 compares against.
    """
    out: list[Any] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != klass:
            continue
        for item in ast.iter_child_nodes(node):
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if public_only and item.name.startswith("_"):
                continue
            out.append(item)
    return out


def _calls_attr(node: ast.AST, attr: str) -> bool:
    """True if `node` contains a call `<anything>.<attr>(...)`."""
    return any(
        isinstance(inner, ast.Call)
        and isinstance(inner.func, ast.Attribute)
        and inner.func.attr == attr
        for inner in ast.walk(node)
    )


def _methods_calling(tree: ast.Module, klass: str, attr: str) -> set[str]:
    """Methods of `klass` whose body contains a call to `<anything>.<attr>(...)`.

    BY SHAPE, never by spelling of the collaborator (the D3.426 lesson):
    the receiver's attribute name is not matched, only that the call is
    `.<attr>(...)`. Renaming `self.registry` does not hide the site.

    `ast.iter_child_nodes`/`ast.walk` is used throughout rather than reading a
    dict's `.keys` — the ARC 049 cross-gate hazard: a `_HANDLERS`-style mapping
    read by a bare `.keys` sees only literal keys and erodes another gate's
    ratchet when a key is computed.
    """
    return {
        f"{klass}.{item.name}"
        for item in _methods_of(tree, klass)
        if _calls_attr(item, attr)
    }


def _loops_over_self_attr(node: ast.AST, attr: str) -> bool:
    """True if any `for` in `node` ITERATES something reaching `self.<attr>`."""
    for inner in ast.walk(node):
        if not isinstance(inner, (ast.For, ast.AsyncFor)):
            continue
        for target in ast.walk(inner.iter):
            if (
                isinstance(target, ast.Attribute)
                and target.attr == attr
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
            ):
                return True
    return False


def _methods_iterating_self_attr(tree: ast.Module, klass: str, attr: str) -> set[str]:
    """Public methods of `klass` that LOOP over `self.<attr>`.

    §15's bounded loop, derived — and the criterion is the LOOP, not mere
    contact with the attribute. Measured, at the tip this gate was built
    against: `StopBook` has four public methods that name `self._by_symbol`.
    Two of them — `maintain` and `breached` — run
    `for coid in tuple(self._by_symbol.get(symbol, ()))`, which IS §15's
    `O(positions <= 5)/tick` traversal. The other two mutate it on an EVENT and
    never traverse it: `arm` does `.setdefault(...).add(...)` at a confirmed
    fill, `forget` does a `.get` and a `del` at a close. Deriving by contact
    alone put both event handlers on the per-tick list, which is how this gate's
    own first run reddened; the loop is the shape that separates them, and it is
    the shape §15 itself names.

    A method that stops looping has left the per-tick path; a new one that
    starts has joined it. ARM 6 catches both.
    """
    return {
        f"{klass}.{item.name}"
        for item in _methods_of(tree, klass, public_only=True)
        if _loops_over_self_attr(item, attr)
    }


def _derive_entry_points(home: Path) -> tuple[set[str], str]:
    """`(derived, complaint)` — the hot-path entry points, from the SOURCE.

    Three derivations, each by shape:

    * per-GO, spec side: the `GatePass` method that dispatches a rule —
      the method containing a `.evaluate(...)` call. `_dispatch` is where the
      call lives and `evaluate` is its only caller, so the PUBLIC entry is the
      one this returns.
    * per-GO, daemon side: the `LimiterLoop` method that calls
      `.take_in_flight(...)` on a collaborator.
    * per-tick: the public `StopBook` methods that LOOP over `self._by_symbol`
      — §15's one permitted bounded traversal. Contact is not the criterion; see
      `_methods_iterating_self_attr` on why, and on the run that proved it.
    """
    derived: set[str] = set()
    for module, klass, attr, kind in (
        ("gate.py", "GatePass", "evaluate", "call"),
        ("loop.py", "LimiterLoop", "take_in_flight", "call"),
        ("stops.py", "StopBook", "_by_symbol", "loop"),
        # ARC 055. The DRIVER of the two above, derived by the same shape rule
        # the daemon-side per-GO entry is derived by: the `StopWatch` method
        # that calls `breached` on its collaborator. Deriving it rather than
        # transcribing `stopwatch.poll` is what makes a LATER method that also
        # breaches — a second poll, a batch sweep — appear in `derived` and fail
        # ARM 6 until it is driven, instead of slipping past uncensused.
        ("stopwatch.py", "StopWatch", "breached", "call"),
    ):
        path = home / SCAN_ROOT / PACKAGE / module
        if not path.is_file():
            return set(), f"{path} is missing — the entry points cannot be derived"
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            return set(), f"{path} does not parse: {exc}"
        if kind == "call":
            found = _methods_calling(tree, klass, attr)
        else:
            found = _methods_iterating_self_attr(tree, klass, attr)
        if not found:
            return set(), (
                f"{module}: no method of {klass} {kind}s {attr!r} — the shape "
                "this gate derives its entry points by has changed, so the "
                "traced set cannot be compared against anything"
            )
        derived |= {f"{module.removesuffix('.py')}.{name}" for name in found}
    return derived, ""


# ---------------------------------------------------------------------------
# verdict helpers
# ---------------------------------------------------------------------------


def _cannot(detail: str, site: str = "") -> CheckResult:
    return CheckResult(
        name=NAME, status=Status.CANNOT_MEASURE, site=site, detail=detail
    )


def _fail(site: str, detail: str, evidence: str) -> CheckResult:
    return CheckResult(
        name=NAME,
        status=Status.FAIL_NEEDS_OPERATOR,
        site=site,
        detail=detail,
        evidence=evidence,
        action=(
            "move the operation OFF the hot path — to a poller or event handler "
            "that updates a cache the hot path READS (§11's architecture). The "
            "hot path reads what pollers precomputed; it does not compute or "
            "block. This gate never edits its subject (CORRECTABLE=False)"
        ),
    )


def _classify(roots: frozenset[str], arm: str) -> tuple[list[str], list[str]]:
    """`(expensive, unclassifiable)` — the allow-set applied to one census.

    The ORDER matters and is the ARM-6/I3 lesson: a root outside the allow-set
    is already a finding whether or not anyone thought to ban it. The
    `_KNOWN_EXPENSIVE` lookup only decides how much the finding can SAY.
    """
    expensive: list[str] = []
    unclassifiable: list[str] = []
    for root in sorted(roots):
        if root in _ALLOWED_ROOTS:
            continue
        if root in _KNOWN_EXPENSIVE:
            expensive.append(f"{arm}: {root} — {_KNOWN_EXPENSIVE[root]}")
        else:
            unclassifiable.append(
                f"{arm}: {root} — entered the hot path and is in NEITHER the "
                "measured allow-set nor the known-expensive list. An operation "
                "nobody thought to ban is exactly what §7.12 asks about, so "
                "this is CANNOT_MEASURE and never a PASS"
            )
    return expensive, unclassifiable


# ---------------------------------------------------------------------------
# the arms
# ---------------------------------------------------------------------------


def _arm_gate(  # pylint: disable=too-many-locals
    mods: dict[str, ModuleType], tmp: Path
) -> tuple[Census, Census, dict[str, int], Any, int, str]:
    """ARMS 1+2. `(shipped, discriminator, outcomes, wal, fsyncs_on_path, complaint)`.

    `fsyncs_on_path` is snapshotted HERE, at the close of the gate arms, and
    never re-read later. ARM 4 deliberately calls `sync_to_disk()` to prove the
    group-commit still happens off-path, so a fsync assertion that read the
    counter afterwards would be reading its own sibling arm's work and reporting
    it as a hot-path violation. Measured: this gate's own first green run
    reddened on exactly that, and the finding was about the instrument.

    ARM 1 drives the §3 pass with the REAL `ReservationLedger` and the REAL
    `Plane1Wal` — D3.400's vacuity is a gate that drives it with `ledger=None`.
    ARM 2 drives the identical pass with `_MemorySink` in the WAL's place, and
    the write count must fall to ZERO.
    """
    gate = mods["nixrisk.gate"]
    seam = mods["nixrisk.seam"]
    wal_mod = mods["nixrisk.wal"]
    res = mods["nixrisk.reservations"]

    ports = _ClearPorts()
    pic = _picture(seam)

    wal = wal_mod.Plane1Wal(tmp / "plane1.wal")
    ledger = res.ReservationLedger(plane1=wal)
    passer = gate.GatePass(ports, list(_manifest(gate, ports)), ledger=ledger)

    outcomes: dict[str, int] = {}
    counter = [0]

    def drive_shipped() -> None:
        for _ in range(N_GATE):
            counter[0] += 1
            out = passer.evaluate(_order(seam, counter[0]), pic, float(counter[0]))
            outcomes[out.decision.name] = outcomes.get(out.decision.name, 0) + 1

    shipped = _census(drive_shipped)

    sink = _MemorySink()
    ledger_b = res.ReservationLedger(plane1=sink)
    passer_b = gate.GatePass(ports, list(_manifest(gate, ports)), ledger=ledger_b)
    counter_b = [0]
    outcomes_b: dict[str, int] = {}

    def drive_detached() -> None:
        for _ in range(N_GATE):
            counter_b[0] += 1
            out = passer_b.evaluate(
                _order(seam, 500_000 + counter_b[0]), pic, float(counter_b[0])
            )
            outcomes_b[out.decision.name] = outcomes_b.get(out.decision.name, 0) + 1

    detached = _census(drive_detached)

    complaint = ""
    approvals = outcomes.get("APPROVE", 0)
    if approvals < MIN_APPROVALS:
        complaint = (
            f"the gate arm produced {approvals} APPROVE decision(s) out of "
            f"{sum(outcomes.values())} across two drives of {N_GATE} — below the "
            f"floor of {MIN_APPROVALS}. Outcomes: {outcomes}. A census over a "
            "pass that denied before `_settle` says nothing about the reservation "
            "take, the WAL append, or anything else after the denying rule"
        )
    elif ledger.total_reserved() <= 0.0:
        complaint = (
            "the gate arm APPROVED but `ledger.total_reserved()` is "
            f"{ledger.total_reserved()!r} — the §3 reservation take did not "
            "happen, so the path this gate claims to have measured was not the "
            "one that commits margin"
        )
    elif outcomes_b.get("APPROVE", 0) < MIN_APPROVALS:
        complaint = (
            "ARM 2 (the discriminator) produced "
            f"{outcomes_b.get('APPROVE', 0)} APPROVE decision(s) — it did not "
            "drive the same path as ARM 1, so the isolation of §11.6's WAL "
            "append is unproven and the allow-set entry for `nixrisk.wal` is "
            "unbounded. CANNOT_MEASURE, never PASS"
        )
    return shipped, detached, outcomes, wal, int(wal.fsyncs), complaint


def _arm_ticks(
    mods: dict[str, ModuleType],
) -> tuple[Census, int, int, str]:
    """ARM 3. `(census, stops_armed, states_seen, complaint)` — §15's bounded loop."""
    seam = mods["nixrisk.seam"]
    stops = mods["nixrisk.stops"]
    book = stops.StopBook({"ES": 0.25})
    for i in range(MAX_POSITIONS):
        book.arm(
            5000.0, _order(seam, 900_000 + i, seam.StopMode.TRAILING), trail_ticks=20
        )
    armed = len(book.stops())
    seen = [0]

    def drive() -> None:
        for i in range(M_TICK):
            price = 5000.0 + (i % 40) * 0.25
            seen[0] += len(book.maintain("ES", price))
            seen[0] += len(book.breached("ES", price))

    census = _census(drive)
    complaint = ""
    if armed > MAX_POSITIONS:
        complaint = (
            f"{armed} stops armed, above §15's bound of {MAX_POSITIONS} — the "
            "one loop the hot path may run is O(positions <= 5)/tick and this "
            "drive exceeded it, so a clean census would be about the wrong shape"
        )
    elif seen[0] <= 0:
        complaint = (
            f"{M_TICK} ticks over {armed} armed stop(s) returned NO stop states "
            "across two drives — the per-tick evaluation did not run, and a "
            "census over an unexercised path is vacuous"
        )
    return census, armed, seen[0], complaint


def _arm_poll(
    mods: dict[str, ModuleType],
) -> tuple[Census, int, int, str]:
    """ARM 3c. `(census, armed, enqueued, complaint)` — ARC 055's NEW hot path.

    §5:322's price poll, DRIVEN. This is the arm that re-proves I9 over code I9
    was discharged before: the tick now reads the price ring, ratchets §4's
    trails and tests every armed stop for breach, and every one of those steps
    is new since ARC 050.

    The drive is shaped so BOTH branches of the poll are exercised — the
    maintain-only path and the breach path — because a census over a poll that
    never breached would say nothing about the enqueue, which is the branch that
    produces work for another thread and therefore the branch most likely to
    acquire something expensive. It is also the arm that proves the FIRE is not
    here: if `StopWatch.poll` ever reached `ProtectiveFlatten.fire`, this census
    would show `nixrisk.flatten` and `threading`-lock frames and the allow-set
    would refuse them.
    """
    seam = mods["nixrisk.seam"]
    stops = mods["nixrisk.stops"]
    stopwatch = mods["nixrisk.stopwatch"]
    book = stops.StopBook({"ES": 0.25})
    for i in range(MAX_POSITIONS):
        book.arm(
            5000.0, _order(seam, 800_000 + i, seam.StopMode.TRAILING), trail_ticks=20
        )
    armed = len(book.stops())
    ring = stopwatch.PriceRing()
    watch = stopwatch.StopWatch(ring, book)
    enqueued = [0]

    def drive() -> None:
        for i in range(M_TICK):
            # A sawtooth that spends most of its time ABOVE every stop (the
            # maintain branch) and dips THROUGH them periodically (the breach
            # branch). `drain` is called so the pending list cannot grow without
            # bound across 2 x M_TICK ticks and turn this census into a memory
            # measurement instead of a purity one.
            price = 5000.0 + (i % 40) * 0.25 - (60.0 if i % 400 == 399 else 0.0)
            ring.publish("ES", price)
            enqueued[0] += watch.poll(i)
            watch.drain()

    census = _census(drive)
    complaint = ""
    if armed > MAX_POSITIONS:
        complaint = (
            f"{armed} stops armed, above §15's bound of {MAX_POSITIONS} — the "
            "poll's one loop is O(positions <= 5)/tick and this drive exceeded "
            "it, so a clean census would be about the wrong shape"
        )
    elif watch.polls <= 0:
        complaint = (
            f"the poll ran {watch.polls} time(s) across two drives of {M_TICK} — "
            "a census over an unexercised path is vacuous"
        )
    elif watch.maintained <= 0:
        complaint = (
            f"{M_TICK} polls ratcheted NOTHING ({watch.maintained} maintained) "
            "over "
            f"{armed} armed trailing stop(s) — the MAINTAIN branch never ran, so "
            "this census says nothing about §4's ratchet on the tick"
        )
    elif enqueued[0] <= 0:
        complaint = (
            f"{M_TICK} polls enqueued NOTHING across two drives — the BREACH "
            "branch never ran, so the branch that produces work for the sender "
            "thread was never censused and is the one a forbidden op would hide in"
        )
    return census, armed, enqueued[0], complaint


def _arm_reads(mods: dict[str, ModuleType], tmp: Path) -> tuple[Census, float, str]:
    """ARM 3b. §11.3's precomputed aggregates, read O(1) — no I/O, no recompute."""
    res = mods["nixrisk.reservations"]
    picture = mods["nixrisk.picture"]
    wal_mod = mods["nixrisk.wal"]
    ledger = res.ReservationLedger(plane1=wal_mod.Plane1Wal(tmp / "reads.wal"))
    book = picture.FinancialPictureBook(balance=1_000_000.0, deployable_fraction=0.70)
    acc = [0.0]

    def drive() -> None:
        for _ in range(M_TICK):
            acc[0] += ledger.total_reserved()
            acc[0] += book.current().balance

    census = _census(drive)
    complaint = ""
    if acc[0] <= 0.0:
        complaint = (
            f"the aggregate-read arm accumulated {acc[0]!r} over {M_TICK} reads "
            "— the reads returned nothing, so the census is vacuous"
        )
    return census, acc[0], complaint


def _arm_off_path(
    mods: dict[str, ModuleType], tmp: Path, wal: Any
) -> tuple[list[str], str]:
    """ARM 4. `(evidence, complaint)` — the expensive work §11 moves off STILL RUNS.

    Purity achieved by dropping the work is a different and worse bug: a hot
    path that skipped the WAL append entirely would be serenely clean and would
    have destroyed §9's audit trail. So this arm asserts the OTHER direction.
    """
    res = mods["nixrisk.reservations"]
    picture = mods["nixrisk.picture"]
    seam = mods["nixrisk.seam"]
    evidence: list[str] = []

    fsyncs_before = wal.fsyncs
    pending_before = wal.pending()
    made = wal.sync_to_disk()
    if made <= 0 or wal.fsyncs <= fsyncs_before:
        return [], (
            f"§11.6's group-commit did NOT run off-path: `sync_to_disk()` made "
            f"{made} row(s) durable and fsyncs went {fsyncs_before} -> "
            f"{wal.fsyncs} with {pending_before} row(s) pending. A pure hot path "
            "whose off-path commit never happens has dropped §9's audit trail, "
            "not achieved §11's discipline"
        )
    evidence.append(
        f"group-commit OFF-path: sync_to_disk() made {made} row(s) durable, "
        f"fsyncs {fsyncs_before} -> {wal.fsyncs} (and ZERO fsync on the hot path)"
    )

    ledger = res.ReservationLedger(plane1=wal)
    taken = ledger.take(_order(seam, 700_001), 1.0)
    audit = ledger.audit()
    if audit.taken <= 0 or audit.scanned <= 0.0:
        return [], (
            f"§11.7's full-scan reconcile reported {audit!r} after a real take — "
            "the off-path audit is not seeing the ledger it reconciles"
        )
    evidence.append(
        f"§11.7 full-scan reconcile OFF-path: aggregate={audit.aggregate} "
        f"scanned={audit.scanned} taken={audit.taken} outstanding={audit.outstanding} "
        f"(reservation {taken.reservation_id} visible to it)"
    )

    sink_book = picture.FinancialPictureBook(
        balance=1_000_000.0, deployable_fraction=0.70
    )
    before = sink_book.commits
    sink_book.commit(balance=999_000.0)
    if sink_book.commits <= before:
        return [], (
            "§11.3's aggregate MAINTENANCE did not run off-path: "
            f"`FinancialPictureBook.commit` left commits at {sink_book.commits}. "
            "The hot path reads a precomputed snapshot; if nothing recomputes it, "
            "the O(1) read is O(1) over a value that never changes"
        )
    evidence.append(
        f"§11.3 aggregate maintenance OFF-path: commit() raised commits "
        f"{before} -> {sink_book.commits}, version now "
        f"{sink_book.current().version} (the hot path READS this, never builds it)"
    )
    del tmp
    return evidence, ""


# ---------------------------------------------------------------------------
# the verdict
# ---------------------------------------------------------------------------


def _measure(home: Path) -> CheckResult:  # pylint: disable=too-many-return-statements
    """Every arm, then the verdict. Returns; never raises past `run`."""
    derived, complaint = _derive_entry_points(home)
    if complaint:
        return _cannot(f"ARM 6 (derivation): {complaint}", site=str(home))

    saved = {k: v for k, v in sys.modules.items() if k.split(".")[0] == PACKAGE}
    loaded, why = load(home)
    if loaded is None:
        unload(saved)
        return _cannot(why, site=str(home))

    tmp = Path(tempfile.mkdtemp(prefix="hot_path_purity_"))
    try:
        return _judge(loaded.mods, tmp, derived)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        unload(saved)


# R0911/R0914 (ARC 055): the returns ARE the ladder this function exists to
# keep separate — one CANNOT_MEASURE per arm that did not run, each naming its
# own site. ARC 055's ARM 3c (§5:322's price poll) added a fourth arm and with it
# a fourth pair of refusals; collapsing them would put "the gate did not run" and
# "which part of the gate did not run" behind one sentence.
def _drive_arms(  # pylint: disable=too-many-return-statements,too-many-locals
    mods: dict[str, ModuleType], tmp: Path
) -> tuple[dict[str, Any] | None, CheckResult | None]:
    """`(readings, refusal)` — run every arm, or say why nothing was measured.

    Split from `_judge` so the DRIVING and the JUDGING are two functions: the
    first can only fail with CANNOT_MEASURE (an arm that did not run measured
    nothing), the second only ever reads numbers that exist. Keeping them in one
    body mixed "the instrument did not run" with "the subject is wrong", which
    are the two verdicts this contract is most careful to separate.
    """
    shipped, detached, outcomes, wal, fsyncs_on_path, complaint = _arm_gate(mods, tmp)
    if complaint:
        return None, _cannot(f"ARM 1/2 (gate pass): {complaint}", site="nixrisk.gate")
    if shipped.raised is not None:
        return None, _cannot(
            "ARM 1 (gate pass): the drive raised "
            f"{type(shipped.raised).__name__}: {shipped.raised} — a gate pass "
            "that could not complete measured nothing",
            site="nixrisk.gate",
        )

    ticks, armed, states, complaint = _arm_ticks(mods)
    if complaint:
        return None, _cannot(f"ARM 3 (stop-eval): {complaint}", site="nixrisk.stops")
    if ticks.raised is not None:
        return None, _cannot(
            f"ARM 3 (stop-eval): the drive raised {type(ticks.raised).__name__}: "
            f"{ticks.raised}",
            site="nixrisk.stops",
        )

    poll, poll_armed, enqueued, complaint = _arm_poll(mods)
    if complaint:
        return None, _cannot(
            f"ARM 3c (price poll): {complaint}", site="nixrisk.stopwatch"
        )
    if poll.raised is not None:
        return None, _cannot(
            f"ARM 3c (price poll): the drive raised {type(poll.raised).__name__}: "
            f"{poll.raised}",
            site="nixrisk.stopwatch",
        )

    reads, acc, complaint = _arm_reads(mods, tmp)
    if complaint:
        return None, _cannot(
            f"ARM 3b (aggregate reads): {complaint}", site="nixrisk.picture"
        )
    return {
        "shipped": shipped,
        "detached": detached,
        "outcomes": outcomes,
        "wal": wal,
        "fsyncs_on_path": fsyncs_on_path,
        "ticks": ticks,
        "armed": armed,
        "states": states,
        "poll": poll,
        "poll_armed": poll_armed,
        "enqueued": enqueued,
        "reads": reads,
        "acc": acc,
    }, None


#: ARM 6's TRACED set — every hot-path entry point this gate's arms actually
#: drive. It is compared against the set DERIVED from the subject's own source,
#: and a derived entry point missing from here is CANNOT_MEASURE. ARC 055 added
#: `stopwatch.StopWatch.poll` when §5:322's price poll became real hot-path code.
_TRACED: frozenset[str] = frozenset(
    {
        "gate.GatePass.evaluate",
        "gate.GatePass._dispatch",
        "loop.LimiterLoop.take_in_flight",
        "stops.StopBook.maintain",
        "stops.StopBook.breached",
        "stopwatch.StopWatch.poll",
    }
)


def _judge_per_tick_io(
    ticks: Census, poll: Census, reads: Census, evidence: str
) -> CheckResult | None:
    """The per-tick I/O rung. `None` when all three per-tick arms wrote nothing.

    Split out of `_judge` when ARC 055's ARM 3c made it a three-way test: §15's
    per-tick budget is O(positions <= 5) of ARITHMETIC, and the site named is
    whichever arm actually wrote, because "the per-tick path wrote" is not a
    finding an operator can act on until it says WHICH per-tick path.
    """
    if ticks.writes == 0 and poll.writes == 0 and reads.writes == 0:
        return None
    site = "nixrisk.stopwatch" if poll.writes else "nixrisk.stops"
    return _fail(
        site,
        f"THE PER-TICK PATH PERFORMED I/O: {ticks.writes} raw write(2) in "
        f"stop-eval, {poll.writes} in §5:322's price poll, {reads.writes} in the "
        "aggregate reads. §15's per-tick budget is O(positions <= 5) of "
        "ARITHMETIC; §11.3 has the aggregates maintained as running values and "
        "READ, never written, by the tick",
        evidence,
    )


def _arm_completeness(derived: set[str]) -> CheckResult | None:
    """ARM 6. `None` when every derived entry point was driven, else the refusal."""
    missing = sorted(derived - _TRACED)
    if not missing:
        return None
    return _cannot(
        "ARM 6 (completeness): the subject's source derives hot-path entry "
        f"point(s) this gate does not drive: {missing}. A hot-path callee this "
        "census never entered is one the verdict says nothing about, and a "
        "forbidden op inside it is exactly the defect. Extend the drive, or the "
        "allow-set is being applied to the wrong path",
        site="nixrisk",
    )


def _judge(  # pylint: disable=too-many-return-statements,too-many-locals,too-many-branches,too-many-statements
    mods: dict[str, ModuleType], tmp: Path, derived: set[str]
) -> CheckResult:
    """The arms, in order, and what each one's failure means."""
    readings, refusal = _drive_arms(mods, tmp)
    if refusal is not None:
        return refusal
    if readings is None:
        # Fail closed, and NOT via `assert`: an assertion is stripped under
        # `-O`, and the one place this gate must never fall through silently is
        # the one where it has neither readings nor a refusal to report.
        return _cannot(
            "the arms returned neither readings nor a refusal — this gate "
            "cannot say what it measured, so it certifies nothing"
        )
    shipped = readings["shipped"]
    detached = readings["detached"]
    outcomes = readings["outcomes"]
    wal = readings["wal"]
    fsyncs_on_path = readings["fsyncs_on_path"]
    ticks = readings["ticks"]
    armed = readings["armed"]
    states = readings["states"]
    poll = readings["poll"]
    poll_armed = readings["poll_armed"]
    enqueued = readings["enqueued"]
    reads = readings["reads"]
    acc = readings["acc"]

    refusal = _arm_completeness(derived)
    if refusal is not None:
        return refusal

    # -- the allow-set, over the UNION of every arm --------------------------
    expensive: list[str] = []
    unclassifiable: list[str] = []
    for census, arm in (
        (shipped, "ARM 1 per-GO gate"),
        (detached, "ARM 2 discriminator"),
        (ticks, "ARM 3 per-tick stop-eval"),
        (poll, "ARM 3c per-tick price poll"),
        (reads, "ARM 3b aggregate reads"),
    ):
        found_e, found_u = _classify(census.roots, arm)
        expensive.extend(found_e)
        unclassifiable.extend(found_u)

    events = _forbidden_events(
        shipped.events + ticks.events + poll.events + reads.events
    )

    off_path, complaint = _arm_off_path(mods, tmp, wal)

    evidence = (
        f"ARM 1 per-GO gate (2 x {N_GATE} evaluations, outcomes {outcomes}, "
        f"Σ reserved > 0): raw write(2)={shipped.writes} over the AUDITED drive "
        f"of {N_GATE} approvals = {shipped.writes / N_GATE:.3f}/approval "
        f"(bound {MAX_WRITES_PER_APPROVAL}; the syscall delta is taken over the "
        f"audited drive alone, never over both, because only one of the two is "
        f"inside the counter's region), fsyncs={fsyncs_on_path} on-path, "
        f"PEP-578 events={len(shipped.events)}, roots={sorted(shipped.roots)} | "
        f"ARM 2 discriminator (WAL -> in-memory sink): raw write(2)="
        f"{detached.writes} (must be 0 — this is what bounds the wal permission) | "
        f"ARM 3 per-tick stop-eval (2 x {M_TICK} ticks, |stops|={armed} <= "
        f"{MAX_POSITIONS}, {states} states returned): raw write(2)={ticks.writes}, "
        f"roots={sorted(ticks.roots)} | "
        f"ARM 3c per-tick price poll (2 x {M_TICK} ticks, |stops|={poll_armed} "
        f"<= {MAX_POSITIONS}, {enqueued} breach(es) enqueued): raw write(2)="
        f"{poll.writes}, roots={sorted(poll.roots)} | "
        f"ARM 3b aggregate reads (2 x {M_TICK}, Σ={acc}): raw write(2)="
        f"{reads.writes}, roots={sorted(reads.roots)} | "
        f"ARM 6 derived entry points: {sorted(derived)} | "
        f"ARM 4 off-path: {'; '.join(off_path) if off_path else 'NOT PROVEN'}"
    )

    # THE ORDER OF THIS LADDER IS THE VERDICT RULE, and it is check contract
    # rule 10's principle one layer down: *a positively-observed claim outranks
    # masking.* An `open` the audit hook SAW is a finding an operator can act
    # on; a module root the census could not CLASSIFY is a finding about this
    # gate's own knowledge. So every positive observation is judged first, and
    # UNCLASSIFIABLE is reached only when nothing was positively seen.
    #
    # Measured, not reasoned: PLANT A puts `open(..., encoding="utf-8")` inside
    # `GatePass.evaluate`. Text mode drags in `codecs`, which is in neither
    # list, and an earlier draft answered the plant with "codecs is
    # unclassifiable" — true, useless, and exit 2 where the operator needed
    # exit 1 and the word `open`.
    if expensive:
        return _fail(
            "nixrisk",
            "FORBIDDEN OPERATION ON THE HOT PATH: "
            + "; ".join(expensive)
            + ". §11 makes the entry pathway CACHE READS AND ARITHMETIC ONLY and "
            "puts everything expensive on pollers and event handlers",
            evidence,
        )
    if events:
        return _fail(
            "nixrisk",
            f"FORBIDDEN SYSCALL ON THE HOT PATH: {len(events)} PEP-578 event(s) "
            f"the hot path may not raise: {events[:6]}. §11 permits cache reads "
            "and arithmetic; §5 makes each rule side-effect-free and non-blocking",
            evidence,
        )
    if shipped.writes > N_GATE * MAX_WRITES_PER_APPROVAL:
        return _fail(
            "nixrisk.wal",
            f"THE HOT PATH WROTE {shipped.writes} TIMES for {N_GATE} approval(s) "
            f"— above the bound of {MAX_WRITES_PER_APPROVAL} per approval. §11.6 "
            "sanctions ONE buffered WAL append and nothing more; a second write "
            "per evaluation is a second I/O on the path, whatever it is spelled",
            evidence,
        )
    if fsyncs_on_path != 0:
        return _fail(
            "nixrisk.wal",
            f"THE HOT PATH FSYNCED {fsyncs_on_path} time(s). `os.fsync` IS the "
            "group-commit's blocking verb and §11.6's actual prohibition — "
            "'group-commit event-log writes off hot path'. Durability belongs to "
            "`sync_to_disk` on the off-path drain",
            evidence,
        )
    if detached.writes != 0:
        return _fail(
            "nixrisk.gate",
            f"I/O ON THE HOT PATH THAT IS NOT §11.6's WAL APPEND: ARM 2 recorded "
            f"{detached.writes} raw write(2) over {N_GATE} approvals with the WAL "
            "replaced by a pure in-memory sink. The allow-set permits ONE writer "
            "on this path and it was removed for this drive, so every one of "
            "those writes belongs to something else. §11 makes the entry pathway "
            "cache reads and arithmetic only",
            evidence,
        )
    per_tick = _judge_per_tick_io(ticks, poll, reads, evidence)
    if per_tick is not None:
        return per_tick
    if complaint:
        return _fail(
            "nixrisk", f"OFF-PATH WORK STOPPED HAPPENING: {complaint}", evidence
        )
    # LAST, for the reason the ladder comment gives: nothing above was
    # positively observed, so an unclassified root is all that is left and it
    # is a limit of this gate's census rather than a violation it witnessed.
    if unclassifiable:
        return _cannot(
            "ALLOW-SET: " + "; ".join(unclassifiable) + f" || {evidence}",
            site="nixrisk",
        )

    return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Prove the hot path reads caches and does arithmetic. Never repairs."""
    try:
        return _measure(Path(ctx.nix_home))
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1 —
        # exit 1 would report a violation this gate never observed.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# Deliberately duplicated across every checks/check_*.py: the check contract
# (§4.2) requires each module be independently runnable, so this block cannot be
# factored into a shared helper without breaking that.
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
