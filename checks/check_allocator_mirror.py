#!/usr/bin/env python3
# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK — `PRIVILEGE`/`INTERACTIVE`/
# `DISRUPTIVE`, `DEPENDS_ON`/`RESOURCES`/`TIME_BOUND`/`CORRECTABLE`/`SUBJECTS`,
# the `load()` sys.path/sys.modules dance every tree-scoped gate needs, and the
# `standalone_main` `__main__` — against every other check's. That similarity is
# the CONTRACT (`nix_check_contract.md` §4.2, §4.4): every check must declare the
# same symbols and must be independently runnable, so the blocks are identical BY
# REQUIREMENT and factoring them into a shared helper would break the contract to
# satisfy a similarity counter.
"""Gate: the Allocator's private mirror is ATOMIC, STALE-FIRST, MONOTONIC, READ-ONLY.

Subject: `scripts/nixalloc/mirror.py`, DRIVEN — never a mock of it, and for two
of the five arms driven over a real ZeroMQ `ipc://` socket.

Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §2 (authority split — the
Allocator is permissive: it reads and proposes, it never writes canonical
state), §3 (*FULL FINANCIAL-PICTURE PUBLISH* and its **ATOMICITY RULE**).

`docs/nics_risk_subsystem_spec_v1.3.md` §6.4 (one writer, one version stamp
over balance + positions + reservations + per-symbol margin), §6.4b
(**MONOTONIC-BY-SOURCE guard**, *per key*).

`docs/nics_risk_subsystem_spec_v1.3.md` §12.7 (state-table transport, LOCKED
v1.3 — snapshot-on-subscribe mandatory, *"never sizes on a half-built
mirror"*), §16 U3.

Doctrine: `docs/debug.md` §7.12; `docs/VERIFY-AND-CHECKS.md` Part C.

## debug.md §7.12 — THE STANDING QUESTION, asked at the point this gate is built

**What would have to be true for this gate to PASS while measuring nothing?**

Seven answers. Every one is CLOSED by a mechanism in this file, not by a promise.

1. **The subject could fail to import, OR THE WRONG SUBJECT COULD IMPORT.** A
   gate whose import failed and whose arms therefore never ran has an empty
   defect list, which reads exactly like a clean tree. *CLOSED:* `load()`
   returns `CANNOT_MEASURE` naming the exception and the tree it was looking in
   (§17: a property proven while its subject is unavailable is not proven, and
   is **never a PASS**).

   The second half is not hypothetical — **it was MEASURED on this gate's first
   draft.** `checks/_preamble.py` appends the REAL `scripts/` to `sys.path`
   permanently, so pointing the gate at a tree with no `scripts/nixalloc/` made
   the import fall THROUGH to the live repository and the gate returned PASS
   over an empty directory. Its own can-fail suite caught it. *CLOSED:*
   `_provenance_defect` reads each loaded module's `__file__` — the
   interpreter's own record of where the bytes came from — and requires it to
   lie under the tree being judged.

2. **The atomicity arm could publish once and read it back.** That measures a
   round trip and calls it atomicity. Nothing about a single-threaded
   publish/read can distinguish a mirror that swaps one pointer from one that
   assigns nine fields in a loop. *CLOSED:* `_arm_atomicity` races a READER
   THREAD against a mid-publish WRITER for thousands of generations, and every
   observation is checked for internal consistency (every published field is
   linked to ONE generation number, so a mixed observation is arithmetically
   visible).

3. **The race could be unable to catch a torn read** — a harness that never
   observes anything, or a consistency predicate that is vacuously true, would
   report a green over a broken mirror. *CLOSED TWICE:* a non-vacuity floor on
   the reader's observation count (zero observations is a finding, never a
   pass), and a **FALSIFIER** — `_TornMirror`, a deliberately non-atomic mirror
   that stores its fields in separate slots with a real window between them —
   driven through the SAME harness, which is REQUIRED to catch it. A harness
   that stops catching the falsifier fails this gate.

4. **The staleness arm could drive a healthy feed.** A mirror handed nothing but
   complete snapshots reports FRESH forever, and §12.7's whole hazard is that a
   MISSED snapshot looks exactly like a quiet, healthy feed (ARC 027's
   `XPUB_VERBOSE` finding, on the publisher's side of the same wire). *CLOSED:*
   `_arm_staleness` drives four states out of the same object — never-heard
   (EMPTY), heard-but-incomplete (PARTIAL), unstamped (PARTIAL), quiet-and-
   current (FRESH), quiet-too-long (STALE) — and requires EMPTY and PARTIAL to
   be DISTINCT, with two falsifiers (`_HeardBlind`, `_AcceptsUnstamped`) each
   required to lose exactly the property the arm asserts.

5. **The monotonic arm could deliver readings in order.** Readings that arrive
   newest-last prove nothing about a guard: an implementation with no guard at
   all passes that test. *CLOSED:* `_arm_monotonic` delivers an OLDER reading
   and requires it to be DISCARDED — held version unchanged, the regressing
   VALUE unchanged, `discarded_older` incremented, and the reason NAMING the
   key. It then delivers a reading that regresses a DIFFERENT key, so the guard
   is shown to be per-key rather than watching one privileged field, and drives
   `_Unguarded` as the falsifier.

6. **The read-only arm could assert an ABSENCE.** "No mutating verb in the
   source" is a code review, and it passes trivially against a mirror whose
   published objects are mutable in place. *CLOSED:* `_arm_readonly` ATTEMPTS
   four mutations against the live mirrored snapshot and records the exception
   each attempt RAISED — the evidence is the raised `FrozenInstanceError` /
   `TypeError`, not the absence of a change — and drives the same attempt
   harness over a deliberately WRITABLE stand-in, which is required to succeed
   four times. An attempt harness that cannot succeed anywhere is measuring its
   own `try` block.

7. **The whole gate could avoid the wire.** §12.7 LOCKS the transport, and a
   mirror proven only against an injected fake has been proven against the fake.
   *CLOSED:* `_arm_transport` binds a real `ipc://` endpoint, publishes the
   picture BEFORE any subscriber exists and never again (so only
   snapshot-on-subscribe can deliver it), requires non-zero bytes off the
   socket, runs a CONTROL with `service()` withheld that must receive nothing,
   drives a delta-only mirror that must report PARTIAL naming the missing topic,
   and replays the §6.4b per-key regression over that same live socket.

8. **THE WIRE COULD NEVER LEAVE THIS PROCESS.** Two sockets in one process do
   traverse the kernel, but fd inheritance, socket-file permissions and the
   actual §12.7 topology — *Limiter process -> Allocator process*, on separate
   cores (§10) — are all untouched by that, and CHECK-DEBT **D3.122** says so in
   as many words. *CLOSED (ARC 032):* `_arm_cross_process` spawns a REAL child
   interpreter that binds the endpoint, publishes ONE picture **before the
   parent's subscriber exists** and then does nothing but answer subscriptions,
   and requires the parent's `AllocatorMirror` to reach FRESH across that
   boundary carrying the child's `stop_distance`. The arm asserts the announced
   pid is not this process's. Its CONTROL is the same drill with the child
   **killed before the parent subscribes**: the mirror must stay EMPTY on zero
   bytes, so arrival in the measured half is evidence the live child produced it
   and not evidence that something in this process remembered it.

## Boundary against the neighbouring gates (§5.5, doctrine C.9)

`check_state_bus` owns the TRANSPORT (`nixbus/statebus.py`).
`check_picture_atomicity` owns the PUBLISHER (`nixrisk/picture.py`). This gate
owns the CONSUMER (`nixalloc/mirror.py`). Neither re-measures another: this gate
would still fail on a torn consumer over a perfect bus and a perfect publisher.

## What this gate does NOT cover

Sizing arithmetic (§7), correlation caps, contention (§6.6 — the Scoring process
is R5 and does not exist), the tradability cache (§16 U1) and the strategy FSM.
No green here may be read as covering any of them.

**Cross-process delivery, restated for ARC 032 rather than left as it was.** Arm
5's publisher and subscriber are still two sockets in ONE process. Arm 6 crosses
a real boundary: a child interpreter binds, publishes and services while this
process only subscribes. What that narrows of D3.122 is `ipc://` delivery,
socket-file visibility and snapshot-on-subscribe across a `fork`+`exec`; what it
does NOT reach is the rest of the row — the child is a bare publisher rather than
a real Limiter, there is no core pinning (§10), no SELinux/AppArmor labelling is
exercised, and nothing here says anything about behaviour under load. The row is
narrowed, not discharged, and this docstring says which half.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import json
import operator
import os
import secrets
import subprocess  # nosec B404 - argv built in `_spawn_child`, shell=False
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=too-few-public-methods,missing-class-docstring
# pylint: disable=missing-function-docstring,too-many-instance-attributes
# The falsifiers and feeds below are one-verb stand-ins for a frozen port's
# single relevant method; each class's NAME states the property it is built to
# lose, and a docstring restating the name is noise. Where a falsifier's defect
# is not obvious from its name it carries a docstring anyway.
# `_TornMirror` holds ten attributes BY CONSTRUCTION: it is the nine-slot,
# non-atomic implementation §3 forbids, written out so the race harness can be
# shown to catch it, and collapsing its slots into one object would delete the
# very defect it exists to have.
#
# pylint: disable=too-many-lines
# This gate is five arms, each with its own falsifier, plus three socket
# scenarios and a §7.12 section that answers seven conditions with a named
# mechanism apiece. Splitting it across modules would break §4.2's requirement
# that a check be a single independently-runnable artifact, and the honest
# alternative to length here is fewer measurements.

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: `pyzmq` is a `checks/pinned_deps.json` pin, and arm 5 drives a real `ipc://`
#: endpoint, so the venv is what makes this gate's transport arm runnable at all.
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: FOUR claims, declared honestly against what this gate really touches:
#: * `file-write:/tmp` — `tempfile.mkdtemp` for the bus root, plus `_remove_tree`'s
#:   ABSOLUTE-path unlinks. `shutil.rmtree` is deliberately not used: on POSIX it
#:   unlinks with a BARE RELATIVE name through a directory fd, which the audit
#:   hook records as `file-write:<basename>` with no directory attached, and no
#:   path-rooted declaration can ever account for it (measured, ARC 026, see
#:   `check_state_bus._remove_tree`).
#: * `zmq-ipc` — the AF_UNIX sockets libzmq binds and connects. **NOT observable
#:   by `check_observed_resource_claims`**: `socket.bind`/`socket.connect` audit
#:   events fire from CPython's `socket` module and libzmq calls `bind(2)` from
#:   C, so the observer will report this gate as touching no socket and that
#:   report will be wrong in the permissive direction. Declared anyway: the claim
#:   is real and the PLAN is what needs to know.
#: * `interpreter:sys.modules` / `interpreter:sys.path` — `load()` purges and
#:   restores the `nixalloc`/`nixrisk`/`nixbus` package namespaces so the gate
#:   reads the tree it was GIVEN rather than the live repository.
#: * `subprocess:python3` / `subprocess:python` — **ARC 032**: arm 6's publisher
#:   children, spawned through `sys.executable`. BOTH spellings, because the
#:   observer matches a subprocess claim by BASENAME and `sys.executable` is
#:   `python` under the venv and `python3` under the system interpreter — the
#:   split D3.140 measured on `check_extract_sources`, declared away here rather
#:   than reproduced. This declaration REPLACES the line that read *"`subprocess:*`
#:   is deliberately ABSENT: this gate spawns nothing"*, which was true until
#:   arm 6 existed and would now be a false declaration (D2.27).
RESOURCES: tuple[str, ...] = (
    "file-write:/tmp",
    "interpreter:sys.modules",
    "interpreter:sys.path",
    "subprocess:python",
    "subprocess:python3",
    "zmq-ipc",
)
TIME_BOUND = True
#: One bounded race (~1 s), one bounded falsifier race (~0.2 s), three socket
#: round-trips each with a bounded service/drain budget, and TWO child
#: interpreters (the measured cross-process drill and its killed-child control),
#: each bounded by `CHILD_CEILING_S`. MEASURED on this node at 5.9 s, twice, with
#: arm 6 costing ~4.5 s of it; budgeted with headroom because ARRIVAL ends both
#: child waits and only a BROKEN boundary reaches a ceiling.
EXPECTED_S = 15.0
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is the Allocator's live consumer-side behaviour under a real "
    "race and a real socket; there is no on-disk setting to correct, and an "
    "instrument that 'repaired' a mirror by writing into it would be committing "
    "the §2 authority violation it exists to detect"
)
SUBJECTS: tuple[str, ...] = ("scripts/nixalloc/mirror.py",)

NAME = "check_allocator_mirror"

MIRROR_FILE = "scripts/nixalloc/mirror.py"
PACKAGES = ("nixalloc", "nixrisk", "nixbus")

#: Generations the atomicity race applies. Large enough that a torn read would
#: be overwhelmingly likely if the mechanism were wrong — the falsifier below
#: is caught within a few dozen — and bounded so the gate cannot hang.
RACE_GENERATIONS = 4000
#: Generations the FALSIFIER race applies. Small, because it sleeps inside its
#: own non-atomic window on purpose.
FALSIFIER_GENERATIONS = 60
#: A reader that observed fewer than this measured nothing about the race.
MIN_OBSERVATIONS = 200
#: Socket budgets. Generous enough that ipc setup is not a race, bounded enough
#: that exhausting one is a finding rather than a hang.
SERVICE_MS = 1500
DRAIN_MS = 750
#: Freshness ceiling used by the driven mirrors. Explicit everywhere: the class
#: takes no default, deliberately.
MAX_AGE_S = 60.0
#: Arm 6. How long the child keeps answering subscriptions, and how long this
#: process will wait for its mirror to complete. ARRIVAL ends the wait; the
#: ceiling only bounds a boundary that is BROKEN rather than slow (D3.39).
CHILD_SECONDS = 20.0
CHILD_CEILING_S = 10.0
#: The CONTROL's ceiling, and it is shorter on purpose. The child is reaped
#: before the subscriber is opened, so its silence is PERMANENT rather than slow
#: and waiting `CHILD_CEILING_S` would add ten seconds of certainty to a wait
#: already an order of magnitude past the healthy arrival. The PROPERTY is
#: unchanged; only the ceiling moves (the reasoning `check_picture_atomicity`
#: records for its own planted-failure ceilings).
CONTROL_CEILING_S = 1.5
#: The stop distance in TICKS the child publishes. A value nothing else in this
#: gate uses, so a row carrying it CAME FROM THE CHILD — the placeholder 20 that
#: every fixture in the tree carries would have proved nothing.
CHILD_STOP_TICKS = 137


class Finding(NamedTuple):
    site: str
    why: str


class Loaded(NamedTuple):
    mirror: ModuleType
    seam: ModuleType
    picture: ModuleType
    statebus: ModuleType


def _purge(saved: dict[str, ModuleType]) -> None:
    for name in [
        key
        for key in sys.modules
        if key in PACKAGES or key.startswith(tuple(f"{p}." for p in PACKAGES))
    ]:
        del sys.modules[name]
    sys.modules.update(saved)


def _provenance_defect(loaded: Loaded, home: Path) -> str:
    """Did every loaded module really come OUT OF `home`? MEASURED, not assumed.

    **This exists because the naive version PASSED against an EMPTY tree.**
    `checks/_preamble.py` appends the REAL `scripts/` to `sys.path` permanently
    and never removes it (deliberately — see `nixverify/loader.py`). So when the
    tree under judgement has no `scripts/nixalloc/mirror.py`, the `sys.path[0]`
    insert below finds nothing, the import falls THROUGH to the live repository,
    and the gate measures the pristine tree while reporting on the empty one — a
    PASS that measured something other than its subject, which is doctrine C.4's
    moving anchor in its most literal form. Found by this gate's own can-fail
    suite (`test_a_MISSING_subject_is_cannot_measure_never_a_PASS`), ARC 031.

    Checking `__file__` is the fix because it is the interpreter's own record of
    where the bytes came from, not a second guess at what the import should have
    resolved to.
    """
    root = (home / "scripts").resolve()
    for module in loaded:
        origin = getattr(module, "__file__", None)
        if origin is None:
            return f"{module.__name__} has no __file__, so its origin is unknowable"
        resolved = Path(origin).resolve()
        if root != resolved and root not in resolved.parents:
            return (
                f"{module.__name__} was imported from {resolved}, which is NOT under "
                f"{root} — the tree under judgement does not contain the subject and "
                "the import fell through to another tree"
            )
    return ""


def load(home: Path) -> tuple[Loaded | None, str]:
    """Import the subject OUT OF `home`, never by name off the live repo."""
    saved_path = list(sys.path)
    saved_modules = {
        key: value
        for key, value in sys.modules.items()
        if key in PACKAGES or key.startswith(tuple(f"{p}." for p in PACKAGES))
    }
    _purge({})
    sys.path.insert(0, str((home / "scripts").resolve()))
    importlib.invalidate_caches()
    try:
        loaded = Loaded(
            mirror=importlib.import_module("nixalloc.mirror"),
            seam=importlib.import_module("nixalloc.seam"),
            picture=importlib.import_module("nixrisk.picture"),
            statebus=importlib.import_module("nixbus.statebus"),
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        sys.path[:] = saved_path
        _purge(saved_modules)
        return None, (
            f"{MIRROR_FILE}: cannot import the subject from {home} — "
            f"{type(exc).__name__}: {exc}. The subject is unavailable, so nothing "
            "was measured (§17: never a PASS)"
        )
    defect = _provenance_defect(loaded, home)
    if defect:
        sys.path[:] = saved_path
        _purge(saved_modules)
        return None, (
            f"{MIRROR_FILE}: {defect}. Nothing about {home} was measured, so this "
            "is CANNOT_MEASURE and is deliberately never a PASS (§17)"
        )
    sys.path[:] = saved_path
    _purge(saved_modules)
    return loaded, ""


# --------------------------------------------------------------------------
# THE GENERATION LINK — what makes a torn read arithmetically visible
# --------------------------------------------------------------------------


def _expected(generation: int) -> dict[str, float]:
    """Every published number as a function of ONE generation.

    §3's atomicity rule is about what a consumer can OBSERVE, and a consumer can
    only observe a tear if the fields are linked. Independent fields carrying
    independent values are indistinguishable from a torn read and from a correct
    one, which is why a naive race measures nothing.
    """
    balance = 100_000.0 * generation
    open_margin = 1_000.0 * generation
    reservations = 500.0 * generation
    committed = open_margin + reservations
    return {
        "balance": balance,
        "row_margin": open_margin,
        "margin_es": 10.0 * generation,
        "margin_nq": 20.0 * generation,
        "sum_open_margin": open_margin,
        "sum_reservations": reservations,
        "committed": committed,
        "deployable": max(0.0, 0.70 * balance - committed),
    }


def _linked_picture(loaded: Loaded, generation: int, published_ts: float) -> Any:
    """One self-consistent picture at `generation`, built from `_expected`."""
    want = _expected(generation)
    row = loaded.seam.PositionRow(
        trade_id="T-1",
        symbol="ES",
        strategy_id="strat-1",
        size=generation,
        margin=want["row_margin"],
        state=loaded.seam.PositionState.OPEN,
        stop_distance=20,
    )
    return loaded.seam.FinancialPicture(
        version=generation,
        published_ts=published_ts,
        balance=want["balance"],
        positions=(row,),
        margin_per_contract=MappingProxyType(
            {"ES": want["margin_es"], "NQ": want["margin_nq"]}
        ),
        sum_open_margin=want["sum_open_margin"],
        sum_reservations=want["sum_reservations"],
        committed=want["committed"],
        deployable=want["deployable"],
    )


def _inconsistency(picture: Any) -> str:
    """`""` when every field of this ONE picture came from one generation.

    TOTAL: it never raises, whatever shape the picture is in, because the whole
    point is to be run against half-built objects.
    """
    generation = getattr(picture, "version", 0)
    want = _expected(generation)
    diffs: list[str] = []
    rows: tuple[Any, ...] = getattr(picture, "positions", ())
    if len(rows) != 1:
        diffs.append(f"position table has {len(rows)} row(s), expected 1")
    elif rows[0].margin != want["row_margin"] or rows[0].size != generation:
        diffs.append(
            f"row margin={rows[0].margin!r} size={rows[0].size!r}, expected "
            f"{want['row_margin']!r}/{generation!r}"
        )
    margins = getattr(picture, "margin_per_contract", {})
    for symbol, key in (("ES", "margin_es"), ("NQ", "margin_nq")):
        if margins.get(symbol) != want[key]:
            diffs.append(
                f"margin[{symbol}]={margins.get(symbol)!r}, want {want[key]!r}"
            )
    for field in ("balance", "sum_open_margin", "sum_reservations", "committed"):
        if getattr(picture, field, None) != want[field]:
            diffs.append(
                f"{field}={getattr(picture, field, None)!r}, want {want[field]!r}"
            )
    if not diffs:
        return ""
    return f"version {generation}: " + "; ".join(diffs)


# --------------------------------------------------------------------------
# Feeds and falsifiers
# --------------------------------------------------------------------------


class _GenerationFeed:
    """Hands out generation `n` on the nth read. The mid-publish WRITER's source."""

    def __init__(self, loaded: Loaded, update_type: Any, published_ts: float) -> None:
        self._loaded = loaded
        self._update = update_type
        self._ts = published_ts
        self.generation = 0

    def read(self, timeout_ms: int) -> Any:
        del timeout_ms
        self.generation += 1
        return self._update(
            picture=_linked_picture(self._loaded, self.generation, self._ts),
            heard=True,
            complete=True,
            source_stamps={"balance": float(self.generation)},
        )


class _ScriptedFeed:
    """Returns each scripted update in turn, then repeats the last one forever."""

    def __init__(self, updates: list[Any]) -> None:
        self._updates = updates
        self.reads = 0

    def read(self, timeout_ms: int) -> Any:
        del timeout_ms
        index = min(self.reads, len(self._updates) - 1)
        self.reads += 1
        return self._updates[index]


class _TornMirror:
    """FALSIFIER for arm 1: nine fields in nine slots, with a real window.

    This is the implementation §3's atomicity rule forbids, written out so the
    race harness can be shown to catch it. If this class stops being caught, the
    harness has stopped measuring and arm 1's PASS is worthless.
    """

    def __init__(self, loaded: Loaded) -> None:
        self._loaded = loaded
        self.generation = 0
        self._version = 0
        self._balance = 0.0
        self._rows: tuple[Any, ...] = ()
        self._margins: Any = MappingProxyType({})
        self._open = 0.0
        self._reserved = 0.0
        self._committed = 0.0
        self._deployable = 0.0

    def refresh(self, timeout_ms: int = 0) -> Any:
        del timeout_ms
        self.generation += 1
        source = _linked_picture(self._loaded, self.generation, 0.0)
        self._version = source.version
        self._balance = source.balance
        time.sleep(0.0005)  # the window a single pointer swap does not have
        self._rows = source.positions
        self._margins = source.margin_per_contract
        self._open = source.sum_open_margin
        self._reserved = source.sum_reservations
        self._committed = source.committed
        self._deployable = source.deployable
        return self.snapshot()

    def snapshot(self) -> Any:
        assembled = self._loaded.seam.FinancialPicture(
            version=self._version,
            published_ts=0.0,
            balance=self._balance,
            positions=self._rows,
            margin_per_contract=self._margins,
            sum_open_margin=self._open,
            sum_reservations=self._reserved,
            committed=self._committed,
            deployable=self._deployable,
        )
        return self._loaded.seam.MirrorSnapshot(
            state=self._loaded.seam.MirrorState.FRESH,
            picture=assembled,
            reason="falsifier",
        )


@dataclasses.dataclass
class _WritablePicture:
    """FALSIFIER for arm 4: a picture whose containers really do admit writes."""

    version: int
    published_ts: float
    balance: float
    positions: list[Any]
    margin_per_contract: dict[str, float]


class _Observations:
    """Reader-thread bookkeeping. Plain lists: `append` is atomic under the GIL."""

    def __init__(self) -> None:
        self.seen: list[int] = []
        self.torn: list[str] = []


def _read_until(mirror: Any, stop: threading.Event, out: _Observations) -> None:
    """Spin on `snapshot()` and check EVERY observation for internal consistency."""
    while not stop.is_set():
        snap = mirror.snapshot()
        picture = snap.picture
        if picture is None or picture.version < 1:
            continue
        out.seen.append(picture.version)
        why = _inconsistency(picture)
        if why:
            out.torn.append(why)


def _race(mirror: Any, generations: int) -> _Observations:
    """Race a reader thread against a mid-publish writer. Returns what it saw."""
    out = _Observations()
    stop = threading.Event()
    reader = threading.Thread(target=_read_until, args=(mirror, stop, out), daemon=True)
    reader.start()
    try:
        for _ in range(generations):
            mirror.refresh(0)
    finally:
        stop.set()
        reader.join(timeout=5.0)
    return out


# --------------------------------------------------------------------------
# ARM 1 — A1: atomicity, and the harness proven able to catch a tear
# --------------------------------------------------------------------------


def _arm_atomicity(loaded: Loaded, evidence: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{MIRROR_FILE}:AllocatorMirror.snapshot[atomicity]"
    feed = _GenerationFeed(loaded, loaded.mirror.MirrorUpdate, time.time())
    subject = loaded.mirror.AllocatorMirror(feed, max_age_s=MAX_AGE_S)

    observed = _race(subject, RACE_GENERATIONS)
    if observed.torn:
        findings.append(
            Finding(
                site,
                f"a reader observed {len(observed.torn)} TORN snapshot(s) during a "
                f"{RACE_GENERATIONS}-generation race — §3's atomicity rule says the "
                f"balance and the position table publish as ONE snapshot; first: "
                f"{observed.torn[0]}",
            )
        )
    if len(observed.seen) < MIN_OBSERVATIONS:
        findings.append(
            Finding(
                site,
                f"the reader made only {len(observed.seen)} observation(s), under the "
                f"{MIN_OBSERVATIONS} floor — a race nobody watched proves nothing "
                "about atomicity and is NEVER a pass",
            )
        )
    if subject.applied < RACE_GENERATIONS:
        findings.append(
            Finding(
                site,
                f"the writer applied {subject.applied} of {RACE_GENERATIONS} "
                "generations — the mirror was not actually being republished under "
                "the reader",
            )
        )

    torn = _race(_TornMirror(loaded), FALSIFIER_GENERATIONS)
    if not torn.torn:
        findings.append(
            Finding(
                f"{site}:falsifier",
                "the DELIBERATELY non-atomic _TornMirror was raced through the SAME "
                f"harness for {FALSIFIER_GENERATIONS} generations and NO torn read "
                "was detected — the harness cannot catch a broken implementation, so "
                "the clean result above is not evidence of anything",
            )
        )
    else:
        evidence.append(
            f"A1: {len(observed.seen)} concurrent observations over "
            f"{RACE_GENERATIONS} generations, 0 torn; falsifier caught "
            f"{len(torn.torn)} tear(s) through the same harness"
        )
    return findings


# --------------------------------------------------------------------------
# ARM 2 — A2: a half-built mirror is STALE, and EMPTY is not PARTIAL
# --------------------------------------------------------------------------


def _staleness_updates(loaded: Loaded, now: float) -> list[Any]:
    """EMPTY -> PARTIAL(incomplete) -> PARTIAL(unstamped) -> FRESH -> quiet."""
    update = loaded.mirror.MirrorUpdate
    unstamped = _linked_picture(loaded, 1, now)
    unstamped = dataclasses.replace(unstamped, version=0)
    return [
        update(heard=False, note="nothing has ever arrived"),
        update(heard=True, complete=False, note="no snapshot yet for ('tbl.x',)"),
        update(picture=unstamped, heard=True, complete=True),
        update(picture=_linked_picture(loaded, 7, now), heard=True, complete=True),
        update(heard=True, complete=False, note="publisher is quiet"),
    ]


def _expect_state(
    snap: Any, states: Any, site: str, what: str, sizeable: bool
) -> list[Finding]:
    """One state assertion, reported with the REASON the mirror gave."""
    if snap.state is not states:
        return [
            Finding(
                site,
                f"{what}: state is {snap.state!r}, expected {states!r} "
                f"(mirror said: {snap.reason!r})",
            )
        ]
    if snap.sizeable is not sizeable:
        return [
            Finding(
                site,
                f"{what}: sizeable is {snap.sizeable!r}, expected {sizeable!r} "
                f"(mirror said: {snap.reason!r})",
            )
        ]
    return []


def _arm_staleness(loaded: Loaded, evidence: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{MIRROR_FILE}:AllocatorMirror.snapshot[staleness]"
    state = loaded.seam.MirrorState
    now = 1_000.0
    clock = [now]
    feed = _ScriptedFeed(_staleness_updates(loaded, now))
    subject = loaded.mirror.AllocatorMirror(feed, max_age_s=2.0, clock=lambda: clock[0])

    findings += _expect_state(
        subject.refresh(), state.EMPTY, site, "never heard from the publisher", False
    )
    partial = subject.refresh()
    findings += _expect_state(
        partial, state.PARTIAL, site, "heard but no snapshot yet", False
    )
    if "no snapshot yet" not in partial.reason:
        findings.append(
            Finding(site, f"the PARTIAL refusal does not say why: {partial.reason!r}")
        )
    unstamped = subject.refresh()
    findings += _expect_state(
        unstamped, state.PARTIAL, site, "unstamped snapshot", False
    )
    if "UNSTAMPED" not in unstamped.reason:
        findings.append(
            Finding(
                site,
                "an unstamped snapshot was refused without naming the stamp: "
                f"{unstamped.reason!r}",
            )
        )
    findings += _expect_state(
        subject.refresh(), state.FRESH, site, "complete stamped snapshot", True
    )
    clock[0] = now + 0.5
    findings += _expect_state(
        subject.refresh(), state.FRESH, site, "publisher quiet and I am current", True
    )
    clock[0] = now + 30.0
    aged = subject.snapshot()
    findings += _expect_state(aged, state.STALE, site, "quiet past the ceiling", False)
    if "ceiling" not in aged.reason:
        findings.append(
            Finding(site, f"the STALE refusal does not name the age: {aged.reason!r}")
        )
    findings += _staleness_falsifiers(loaded, now, site, evidence)
    return findings


class _HeardBlind:
    """FALSIFIER: a mirror that cannot tell never-heard from heard-but-incomplete."""


class _AcceptsUnstamped:
    """FALSIFIER: a mirror that holds a snapshot carrying no version stamp."""


def _staleness_falsifiers(
    loaded: Loaded, now: float, site: str, evidence: list[str]
) -> list[Finding]:
    """Both falsifiers must LOSE exactly the property the arm above asserts."""
    findings: list[Finding] = []
    base = loaded.mirror.AllocatorMirror
    state = loaded.seam.MirrorState

    class _Blind(base):  # type: ignore[misc,valid-type]
        def _absent(self, update: Any) -> None:
            self._refuse(f"{update.note}", heard=False)  # WRONG: drops `heard`

    blind = _Blind(_ScriptedFeed(_staleness_updates(loaded, now)), max_age_s=2.0)
    blind.refresh()
    if blind.refresh().state is not state.EMPTY:
        findings.append(
            Finding(
                f"{site}:falsifier[{_HeardBlind.__name__}]",
                "the heard-blind falsifier reported PARTIAL anyway — it no longer "
                "falsifies, so 'EMPTY is distinct from PARTIAL' above is untested",
            )
        )

    class _Lax(base):  # type: ignore[misc,valid-type]
        def _incoherent(self, picture: Any) -> str:
            del picture
            return ""  # WRONG: §12.7's half-built rule deleted

    lax = _Lax(
        _ScriptedFeed(_staleness_updates(loaded, now)),
        max_age_s=1e9,
        clock=lambda: now,
    )
    for _ in range(3):
        lax.refresh()
    if lax.snapshot().state is not state.FRESH:
        findings.append(
            Finding(
                f"{site}:falsifier[{_AcceptsUnstamped.__name__}]",
                "the accepts-unstamped falsifier still refused the unstamped "
                "snapshot — it no longer falsifies, so the unstamped assertion "
                "above is untested",
            )
        )
    evidence.append(
        "A2: EMPTY / PARTIAL(incomplete) / PARTIAL(unstamped) / FRESH(quiet and "
        "current) / STALE all driven out of ONE mirror, with two falsifiers each "
        "proven to lose its property"
    )
    return findings


# --------------------------------------------------------------------------
# ARM 3 — A3: §6.4b's monotonic-by-source guard, PER KEY
# --------------------------------------------------------------------------


def _keyed_picture(
    loaded: Loaded, version: int, es: float, nq: float, published_ts: float = 1_000.0
) -> Any:
    """A picture whose per-symbol margins are independently settable."""
    row = loaded.seam.PositionRow(
        trade_id="T-1",
        symbol="ES",
        strategy_id="strat-1",
        size=1,
        margin=1_000.0,
        state=loaded.seam.PositionState.OPEN,
        stop_distance=20,
    )
    return loaded.seam.FinancialPicture(
        version=version,
        published_ts=published_ts,
        balance=100_000.0,
        positions=(row,),
        margin_per_contract=MappingProxyType({"ES": es, "NQ": nq}),
        sum_open_margin=1_000.0,
        sum_reservations=0.0,
        committed=1_000.0,
        deployable=max(0.0, 0.70 * 100_000.0 - 1_000.0),
    )


def _stamped(loaded: Loaded, picture: Any, **stamps: float) -> Any:
    return loaded.mirror.MirrorUpdate(
        picture=picture, heard=True, complete=True, source_stamps=dict(stamps)
    )


def _monotonic_script(loaded: Loaded) -> list[Any]:
    """Held, then ES regresses, then NQ regresses, then version regresses, then OK."""
    keys = {"balance": 100.0, "margin:ES": 100.0, "margin:NQ": 100.0}
    return [
        _stamped(loaded, _keyed_picture(loaded, 5, 5_000.0, 7_000.0), **keys),
        _stamped(
            loaded,
            _keyed_picture(loaded, 6, 4_000.0, 7_500.0),
            **{"balance": 110.0, "margin:ES": 90.0, "margin:NQ": 110.0},
        ),
        _stamped(
            loaded,
            _keyed_picture(loaded, 7, 5_500.0, 6_000.0),
            **{"balance": 120.0, "margin:ES": 120.0, "margin:NQ": 90.0},
        ),
        _stamped(
            loaded,
            _keyed_picture(loaded, 4, 1.0, 1.0),
            **{"balance": 900.0, "margin:ES": 900.0, "margin:NQ": 900.0},
        ),
        _stamped(
            loaded,
            _keyed_picture(loaded, 8, 5_500.0, 7_500.0),
            **{"balance": 130.0, "margin:ES": 130.0, "margin:NQ": 130.0},
        ),
    ]


def _held_margin(subject: Any, symbol: str) -> Any:
    snap = subject.snapshot()
    if snap.picture is None:
        return None
    return snap.picture.margin_per_contract.get(symbol)


def _arm_monotonic(  # pylint: disable=too-many-branches
    loaded: Loaded, evidence: list[str]
) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{MIRROR_FILE}:AllocatorMirror._regression[monotonic-by-source]"
    subject = loaded.mirror.AllocatorMirror(
        _ScriptedFeed(_monotonic_script(loaded)), max_age_s=1e9, clock=lambda: 1_000.0
    )
    subject.refresh()
    if subject.version() != 5:
        findings.append(
            Finding(site, f"the held version is {subject.version()}, not 5")
        )

    for step, (key, other, held_value) in enumerate(
        (("margin:ES", "NQ", 5_000.0), ("margin:NQ", "ES", 5_000.0)), start=1
    ):
        before = subject.discarded_older
        subject.refresh()
        if subject.version() != 5:
            findings.append(
                Finding(
                    site,
                    f"step {step}: a reading whose {key} stamp is OLDER than the held "
                    f"one was APPLIED — version moved to {subject.version()}; §6.4b "
                    "says anything older is discarded, not applied",
                )
            )
        if subject.discarded_older != before + 1:
            findings.append(
                Finding(
                    site,
                    f"step {step}: discarded_older did not increment "
                    f"({before} -> {subject.discarded_older}) — the discard is "
                    "invisible, so nothing can prove the guard fired",
                )
            )
        if key not in subject.last_refusal:
            findings.append(
                Finding(
                    site,
                    f"step {step}: the refusal does not name the regressing key "
                    f"{key!r}: {subject.last_refusal!r}",
                )
            )
        if _held_margin(subject, "ES") != held_value:
            findings.append(
                Finding(
                    site,
                    f"step {step}: the held ES margin moved to "
                    f"{_held_margin(subject, 'ES')!r}, expected {held_value!r} — a "
                    f"late update on {key} regressed a held value",
                )
            )
        del other

    before = subject.discarded_older
    subject.refresh()
    if subject.version() != 5 or subject.discarded_older != before + 1:
        findings.append(
            Finding(
                site,
                f"a reading carrying an OLDER picture version was not discarded — "
                f"version {subject.version()}, discarded_older {subject.discarded_older}",
            )
        )
    subject.refresh()
    if subject.version() != 8 or _held_margin(subject, "NQ") != 7_500.0:
        findings.append(
            Finding(
                site,
                "a reading newer on EVERY key was not applied — version "
                f"{subject.version()}, NQ margin {_held_margin(subject, 'NQ')!r}; a "
                "guard that discards everything is not a guard",
            )
        )
    findings += _monotonic_falsifier(loaded, site, evidence)
    return findings


def _monotonic_falsifier(
    loaded: Loaded, site: str, evidence: list[str]
) -> list[Finding]:
    """A mirror with NO guard must lose exactly the property arm 3 asserts."""
    base = loaded.mirror.AllocatorMirror

    class _Unguarded(base):  # type: ignore[misc,valid-type]
        def _regression(self, picture: Any, stamps: Any) -> str:
            del picture, stamps
            return ""  # WRONG: §6.4b's guard deleted

    fake = _Unguarded(
        _ScriptedFeed(_monotonic_script(loaded)), max_age_s=1e9, clock=lambda: 1_000.0
    )
    fake.refresh()
    fake.refresh()
    if _held_margin(fake, "ES") != 4_000.0:
        return [
            Finding(
                f"{site}:falsifier",
                "the UNGUARDED falsifier did not regress the ES margin to 4000.0 "
                f"(it holds {_held_margin(fake, 'ES')!r}) — it no longer falsifies, "
                "so arm 3's clean result is not evidence of a guard",
            )
        ]
    evidence.append(
        "A3: an out-of-order reading was DISCARDED on ES and again on NQ (per key), "
        "an older picture version was discarded, a newer-on-every-key reading was "
        "applied; the unguarded falsifier regressed ES to 4000.0 through the same "
        "assertions"
    )
    return []


# --------------------------------------------------------------------------
# ARM 4 — A4: read-only PROVEN BY ATTEMPT
# --------------------------------------------------------------------------


def _attempt_mutations(snap: Any) -> tuple[list[str], list[str]]:
    """`(mutations that SUCCEEDED, exceptions the attempts RAISED)`.

    The raised list is the evidence: an absence of change proves nothing about
    whether the write was refused or merely never attempted.
    """
    succeeded: list[str] = []
    raised: list[str] = []
    picture = snap.picture
    attempts = (
        ("FinancialPicture.balance", lambda: setattr(picture, "balance", 1.0)),
        (
            "FinancialPicture.positions[0]",
            lambda: operator.setitem(picture.positions, 0, None),
        ),
        (
            "FinancialPicture.margin_per_contract['ES']",
            lambda: operator.setitem(picture.margin_per_contract, "ES", 1.0),
        ),
        ("MirrorSnapshot.state", lambda: setattr(snap, "state", None)),
    )
    for label, attempt in attempts:
        try:
            attempt()
        except (dataclasses.FrozenInstanceError, TypeError, AttributeError) as exc:
            raised.append(f"{label} -> {type(exc).__name__}")
            continue
        succeeded.append(label)
    return succeeded, raised


def _picture_taking_verbs(subject: Any) -> list[str]:
    """Public verbs whose signature would accept a financial picture (§2)."""
    offenders: list[str] = []
    for name in dir(type(subject)):
        if name.startswith("_"):
            continue
        member = getattr(type(subject), name, None)
        if not callable(member):
            continue
        try:
            signature = inspect.signature(member)
        except TypeError, ValueError:
            continue
        for parameter in signature.parameters.values():
            annotation = str(parameter.annotation)
            if "FinancialPicture" in annotation or parameter.name == "picture":
                offenders.append(f"{name}({parameter.name})")
    return offenders


def _arm_readonly(loaded: Loaded, evidence: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{MIRROR_FILE}:AllocatorMirror[read-only]"
    now = 1_000.0
    feed = _ScriptedFeed(
        [
            loaded.mirror.MirrorUpdate(
                picture=_linked_picture(loaded, 3, now), heard=True, complete=True
            )
        ]
    )
    subject = loaded.mirror.AllocatorMirror(feed, max_age_s=1e9, clock=lambda: now)
    snap = subject.refresh()
    if not isinstance(subject, loaded.seam.MirrorPort):
        findings.append(Finding(site, "the subject does not satisfy MirrorPort"))

    succeeded, raised = _attempt_mutations(snap)
    if succeeded:
        findings.append(
            Finding(
                site,
                f"{len(succeeded)} mutation(s) against the mirrored snapshot SUCCEEDED "
                f"({', '.join(succeeded)}) — a consumer that can edit a published field "
                "in place has written canonical state with no event (§2, §9)",
            )
        )
    if len(raised) != 4:
        findings.append(
            Finding(
                site,
                f"only {len(raised)} of 4 mutation attempts raised ({raised}) — the "
                "attempt is the evidence, and an attempt that neither raised nor "
                "succeeded was never made",
            )
        )
    if subject.snapshot() != snap:
        findings.append(
            Finding(site, "the held snapshot CHANGED across the mutation attempts")
        )
    offenders = _picture_taking_verbs(subject)
    if offenders:
        findings.append(
            Finding(
                site,
                f"public verb(s) accept a financial picture: {offenders} — §2 gives "
                "the Allocator no way to install a picture the Limiter never sent",
            )
        )
    findings += _readonly_writable_refusal(loaded, site)
    findings += _readonly_falsifier(loaded, site, raised, evidence)
    return findings


def _readonly_writable_refusal(loaded: Loaded, site: str) -> list[Finding]:
    """A picture whose containers admit writes must never be HELD."""
    writable = loaded.seam.FinancialPicture(
        version=9,
        published_ts=1_000.0,
        balance=1_000.0,
        positions=(),
        margin_per_contract={"ES": 5.0},  # a real dict: item assignment works
        sum_open_margin=0.0,
        sum_reservations=0.0,
        committed=0.0,
        deployable=700.0,
    )
    subject = loaded.mirror.AllocatorMirror(
        _ScriptedFeed(
            [loaded.mirror.MirrorUpdate(picture=writable, heard=True, complete=True)]
        ),
        max_age_s=1e9,
        clock=lambda: 1_000.0,
    )
    snap = subject.refresh()
    if snap.state is not loaded.seam.MirrorState.PARTIAL or snap.sizeable:
        return [
            Finding(
                site,
                "a picture carrying a WRITABLE margin mapping was held as "
                f"{snap.state!r} (sizeable={snap.sizeable!r}) — the mirror would be "
                "writable by the process that must never write it",
            )
        ]
    if "item assignment" not in snap.reason:
        return [
            Finding(site, f"the writable-container refusal is unnamed: {snap.reason!r}")
        ]
    return []


def _readonly_falsifier(
    loaded: Loaded, site: str, raised: list[str], evidence: list[str]
) -> list[Finding]:
    """The SAME attempt harness must SUCCEED against a genuinely writable object."""
    fake = loaded.seam.MirrorSnapshot(
        state=loaded.seam.MirrorState.FRESH,
        picture=_WritablePicture(
            version=1,
            published_ts=0.0,
            balance=1.0,
            positions=[None],
            margin_per_contract={"ES": 1.0},
        ),
        reason="falsifier",
    )
    succeeded, _ = _attempt_mutations(fake)
    if len(succeeded) != 3:
        return [
            Finding(
                f"{site}:falsifier",
                f"the WRITABLE stand-in absorbed only {len(succeeded)} of 3 picture "
                f"mutations ({succeeded}) — the attempt harness cannot succeed "
                "anywhere, so it is measuring its own try block",
            )
        ]
    evidence.append(
        f"A4: 4 mutation attempts against the live mirrored snapshot, all REFUSED "
        f"({'; '.join(raised)}); a writable stand-in absorbed 3 of them through the "
        "same harness; no public verb accepts a picture; a writable margin mapping "
        "is refused rather than held"
    )
    return []


# --------------------------------------------------------------------------
# ARM 5 — the REAL §12.7 transport
# --------------------------------------------------------------------------


def _wire_body(
    loaded: Loaded, picture: Any, stamps: dict[str, float]
) -> dict[str, Any]:
    body = dict(loaded.picture.encode_picture(picture))
    body[loaded.mirror.SOURCE_STAMPS_FIELD] = stamps
    return body


def _transport_live(loaded: Loaded, root: Path, nonce: float) -> dict[str, Any]:
    """Publish BEFORE any subscriber exists; only snapshot-on-subscribe can deliver."""
    statebus, module = loaded.statebus, loaded.mirror
    endpoint = statebus.endpoint_for("alloc-mirror", root=root)
    publisher = statebus.StatePublisher(endpoint)
    subscriber = None
    try:
        first = _keyed_picture(loaded, 11, nonce, nonce * 2.0, time.time())
        publisher.publish(
            loaded.picture.TOPIC,
            _wire_body(loaded, first, {"balance": 100.0, "margin:ES": 100.0}),
        )
        subscriber = statebus.StateSubscriber(endpoint, [loaded.picture.TOPIC])
        mirror = module.AllocatorMirror(
            module.StateBusFeed(subscriber), max_age_s=MAX_AGE_S
        )
        publisher.service(SERVICE_MS)
        fresh = mirror.refresh(DRAIN_MS)
        publisher.publish(
            loaded.picture.TOPIC,
            _wire_body(
                loaded,
                _keyed_picture(loaded, 12, 1.0, 1.0, time.time()),
                {"balance": 110.0, "margin:ES": 90.0},
            ),
        )
        regressed = mirror.refresh(DRAIN_MS)
        return {
            "endpoint": endpoint,
            "socket_file": Path(endpoint.removeprefix("ipc://")).exists(),
            "bytes": subscriber.bytes_received,
            "fresh": fresh,
            "regressed": regressed,
            "version": mirror.version(),
            "discarded": mirror.discarded_older,
            "refusal": mirror.last_refusal,
        }
    finally:
        if subscriber is not None:
            subscriber.close()
        publisher.close()


def _transport_control(loaded: Loaded, root: Path, nonce: float) -> dict[str, Any]:
    """CONTROL: identical, with `service()` never called. Must receive NOTHING."""
    statebus, module = loaded.statebus, loaded.mirror
    endpoint = statebus.endpoint_for("alloc-ctl", root=root)
    publisher = statebus.StatePublisher(endpoint)
    subscriber = None
    try:
        publisher.publish(
            loaded.picture.TOPIC,
            _wire_body(
                loaded, _keyed_picture(loaded, 11, nonce, nonce, time.time()), {}
            ),
        )
        subscriber = statebus.StateSubscriber(endpoint, [loaded.picture.TOPIC])
        mirror = module.AllocatorMirror(
            module.StateBusFeed(subscriber), max_age_s=MAX_AGE_S
        )
        snap = mirror.refresh(DRAIN_MS)
        return {"snap": snap, "bytes": subscriber.bytes_received}
    finally:
        if subscriber is not None:
            subscriber.close()
        publisher.close()


def _transport_delta_only(loaded: Loaded, root: Path, nonce: float) -> dict[str, Any]:
    """Subscribe first, publish deltas, NEVER service. §12.7: that mirror is stale."""
    statebus, module = loaded.statebus, loaded.mirror
    endpoint = statebus.endpoint_for("alloc-dlt", root=root)
    publisher = statebus.StatePublisher(endpoint)
    subscriber = None
    try:
        subscriber = statebus.StateSubscriber(endpoint, [loaded.picture.TOPIC])
        mirror = module.AllocatorMirror(
            module.StateBusFeed(subscriber), max_age_s=MAX_AGE_S
        )
        body = _wire_body(
            loaded, _keyed_picture(loaded, 11, nonce, nonce, time.time()), {}
        )
        snap = mirror.snapshot()
        for _ in range(60):
            publisher.publish(loaded.picture.TOPIC, body)
            snap = mirror.refresh(25)
            if subscriber.bytes_received:
                break
        return {"snap": snap, "bytes": subscriber.bytes_received}
    finally:
        if subscriber is not None:
            subscriber.close()
        publisher.close()


def _arm_transport(  # pylint: disable=too-many-branches
    loaded: Loaded, root: Path, nonce: float, evidence: list[str]
) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{MIRROR_FILE}:StateBusFeed[ipc]"
    live = _transport_live(loaded, root, nonce)
    control = _transport_control(loaded, root, nonce)
    delta = _transport_delta_only(loaded, root, nonce)

    if not live["bytes"]:
        findings.append(
            Finding(
                site,
                "the subscriber took ZERO bytes off a real ipc:// socket — a mirror "
                "that received nothing cannot report that the transport works "
                "(§12.7), and this is deliberately never a PASS",
            )
        )
        return findings
    if not live["socket_file"]:
        findings.append(
            Finding(
                live["endpoint"],
                "no socket file on disk while the publisher was bound — the endpoint "
                "was never materialised by the kernel",
            )
        )
    fresh = live["fresh"]
    if fresh.state is not loaded.seam.MirrorState.FRESH or not fresh.sizeable:
        findings.append(
            Finding(
                site,
                f"a LATE subscriber's mirror is {fresh.state!r} after "
                f"snapshot-on-subscribe (sizeable={fresh.sizeable!r}); §12.7 makes "
                f"the snapshot mandatory, not polish. Mirror said: {fresh.reason!r}",
            )
        )
    elif fresh.picture.margin_per_contract.get("ES") != nonce:
        findings.append(
            Finding(
                site,
                f"the snapshot carried ES margin "
                f"{fresh.picture.margin_per_contract.get('ES')!r}, expected the nonce "
                f"{nonce!r} — the transport delivered something that is not the table "
                "under test",
            )
        )
    if live["version"] != 11 or live["discarded"] != 1:
        findings.append(
            Finding(
                site,
                "a §6.4b key regression delivered over the REAL socket was not "
                f"discarded — held version {live['version']}, discarded_older "
                f"{live['discarded']}, refusal {live['refusal']!r}",
            )
        )
    if control["bytes"] or control["snap"].sizeable:
        findings.append(
            Finding(
                f"{site} CONTROL (service() never called)",
                f"a late subscriber received {control['bytes']} byte(s) and reported "
                f"{control['snap'].state!r} with snapshot-on-subscribe never run — so "
                "arrival in the measured arm is not evidence the mechanism works",
            )
        )
    findings += _delta_only_finding(loaded, site, delta)
    if not findings:
        evidence.append(
            f"A1/A2 over the REAL wire: {live['bytes']} bytes on {live['endpoint']}; "
            f"late subscriber reached FRESH by snapshot-on-subscribe carrying nonce "
            f"{nonce}; control with service() withheld got {control['bytes']} bytes; "
            f"a delta-only mirror reported {delta['snap'].state.value}; a per-key "
            "regression over the same socket was discarded"
        )
    return findings


def _delta_only_finding(
    loaded: Loaded, site: str, delta: dict[str, Any]
) -> list[Finding]:
    if not delta["bytes"]:
        return [
            Finding(
                f"{site} delta-only",
                "no delta was ever delivered, so §12.7's half-built-mirror rule is "
                "untested here",
            )
        ]
    snap = delta["snap"]
    if snap.state is not loaded.seam.MirrorState.PARTIAL or snap.sizeable:
        return [
            Finding(
                f"{site} delta-only",
                f"a mirror fed ONLY deltas reports {snap.state!r} "
                f"(sizeable={snap.sizeable!r}) — §12.7 requires an incomplete mirror "
                f"to be treated as stale until a snapshot lands. Mirror said: "
                f"{snap.reason!r}",
            )
        ]
    if "no snapshot yet" not in snap.reason:
        return [
            Finding(
                f"{site} delta-only",
                f"the delta-only refusal does not name the missing table: {snap.reason!r}",
            )
        ]
    return []


# --------------------------------------------------------------------------
# ARM 6 — a REAL process boundary (CHECK-DEBT D3.122, narrowed by measurement)
# --------------------------------------------------------------------------

#: The child publisher, written into the gate's OWN tempdir and unlinked with it.
#: Doctrine C.8: it is not a production artifact and it never lands in the tree.
#: It is a bare §3 publisher — one commit, then nothing but `service()` — because
#: the property under measurement is the BOUNDARY, and a child that did more
#: would make a failure ambiguous between the boundary and the child.
_CHILD_SOURCE = '''\
"""ARC 032 arm 6: a real second process publishing §3's financial picture."""
import json
import os
import sys
import time

root, endpoint, stop_ticks, seconds = (
    sys.argv[1], sys.argv[2], int(sys.argv[3]), float(sys.argv[4])
)
sys.path.insert(0, root)

from nixbus import statebus  # noqa: E402
from nixrisk import picture as pic  # noqa: E402
from nixrisk import seam  # noqa: E402

publisher = statebus.StatePublisher(endpoint)
sink = pic.StateBusPictureSink(publisher)
book = pic.FinancialPictureBook(
    balance=250_000.0, deployable_fraction=0.70, sink=sink
)
row = seam.PositionRow(
    trade_id="T-XP",
    symbol="ES",
    strategy_id="cross-process",
    size=3,
    margin=1_000.0,
    state=seam.PositionState.OPEN,
    stop_distance=stop_ticks,
)
snapshot = book.commit(balance=250_000.0, positions=(row,))
print(
    json.dumps(
        {
            "pid": os.getpid(),
            "version": snapshot.version,
            "stop_distance": row.stop_distance,
            "balance": snapshot.balance,
            "executable": sys.executable,
        }
    ),
    flush=True,
)
# From here on the child ONLY answers subscriptions. The picture above was
# published before this process's parent had a subscriber at all, so nothing but
# §12.7's snapshot-on-subscribe can put it on the parent's mirror.
deadline = time.monotonic() + seconds
while time.monotonic() < deadline:
    publisher.service(50)
publisher.close()
'''


def _spawn_child(home: Path, root: Path, endpoint: str) -> tuple[Any, dict[str, Any]]:
    """Start the publisher child and read its self-announcement. Raises on either."""
    script = root / "arc032_picture_publisher.py"
    script.write_text(_CHILD_SOURCE, encoding="utf-8")
    argv = [
        sys.executable,
        str(script),
        str((home / "scripts").resolve()),
        endpoint,
        str(CHILD_STOP_TICKS),
        str(CHILD_SECONDS),
    ]
    # pylint: disable=consider-using-with
    # The child outlives this call by design: the whole drill happens while it
    # runs, and `_cross_process` owns the terminate and the reap on every path.
    proc = subprocess.Popen(  # nosec B603 - argv built here, no shell
        argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    line = proc.stdout.readline() if proc.stdout else ""
    if not line.strip():
        proc.kill()
        proc.wait(timeout=20)
        stderr = (proc.stderr.read() if proc.stderr else "")[:400]
        raise MirrorChildError(
            f"the publisher child printed no announcement; stderr={stderr!r}"
        )
    return proc, json.loads(line)


class MirrorChildError(RuntimeError):
    """The arm-6 child could not be started or would not announce itself."""


def _cross_process(
    loaded: Loaded, home: Path, root: Path, *, kill_before_subscribe: bool
) -> dict[str, Any]:
    """Publish from a REAL child; mirror in THIS process. The boundary, driven.

    `kill_before_subscribe` is the CONTROL: with the child dead before this
    process ever connects, nothing may arrive. Without it, arrival in the
    measured half would be evidence only that something delivered a picture.
    """
    name = "alloc-xpc" if kill_before_subscribe else "alloc-xp"
    endpoint = loaded.statebus.endpoint_for(name, root=root)
    proc, announced = _spawn_child(home, root, endpoint)
    subscriber = None
    try:
        if kill_before_subscribe:
            proc.kill()
            proc.wait(timeout=20)
        subscriber = loaded.statebus.StateSubscriber(endpoint, [loaded.picture.TOPIC])
        mirror = loaded.mirror.AllocatorMirror(
            loaded.mirror.StateBusFeed(subscriber), max_age_s=MAX_AGE_S
        )
        ceiling = CONTROL_CEILING_S if kill_before_subscribe else CHILD_CEILING_S
        started = time.monotonic()
        deadline = started + ceiling
        snap = mirror.snapshot()
        while time.monotonic() < deadline:
            snap = mirror.refresh(DRAIN_MS)
            if snap.sizeable:
                break
        return {
            "announced": announced,
            "child_pid": proc.pid,
            "own_pid": os.getpid(),
            "endpoint": endpoint,
            "socket_file": Path(endpoint.removeprefix("ipc://")).exists(),
            "bytes": subscriber.bytes_received,
            "snap": snap,
            "waited_s": time.monotonic() - started,
        }
    finally:
        if subscriber is not None:
            subscriber.close()
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=20)


def _arm_cross_process(  # pylint: disable=too-many-return-statements
    loaded: Loaded, home: Path, root: Path, evidence: list[str]
) -> list[Finding]:
    """§12.7's topology, across a real `fork`+`exec`. D3.122's measured half."""
    site = f"{MIRROR_FILE}:StateBusFeed[cross-process]"
    try:
        live = _cross_process(loaded, home, root, kill_before_subscribe=False)
        control = _cross_process(loaded, home, root, kill_before_subscribe=True)
    except (MirrorChildError, OSError, ValueError) as exc:
        return [
            Finding(
                site,
                f"the publisher child could not be driven: {type(exc).__name__}: "
                f"{exc} — a boundary that was never crossed proves nothing about "
                "cross-process delivery, and D3.122 stands exactly where it was",
            )
        ]
    if live["announced"]["pid"] == live["own_pid"]:
        return [
            Finding(
                site,
                f"the publisher announced pid {live['announced']['pid']}, which is "
                "THIS process — no boundary was crossed and the arm is measuring "
                "itself",
            )
        ]
    if not live["bytes"]:
        return [
            Finding(
                site,
                f"the subscriber took ZERO bytes from a publisher in pid "
                f"{live['child_pid']} over {live['endpoint']} after "
                f"{live['waited_s']:.2f}s — §12.7's snapshot-on-subscribe did not "
                "cross the process boundary, and this is deliberately never a PASS",
            )
        ]
    snap = live["snap"]
    if snap.state is not loaded.seam.MirrorState.FRESH or not snap.sizeable:
        return [
            Finding(
                site,
                f"the mirror is {snap.state!r} (sizeable={snap.sizeable!r}) after "
                f"{live['bytes']} byte(s) from pid {live['child_pid']}. Mirror said: "
                f"{snap.reason!r}",
            )
        ]
    rows = snap.picture.positions
    got = [row.stop_distance for row in rows]
    if got != [CHILD_STOP_TICKS]:
        return [
            Finding(
                site,
                f"the row that crossed the boundary carries stop_distance {got}, not "
                f"[{CHILD_STOP_TICKS}] — the field §7:501 prices a held position "
                "from did not survive a real process boundary, or arrived defaulted, "
                "which is D3.136's fail-open one transport further out",
            )
        ]
    if control["bytes"] or control["snap"].sizeable:
        return [
            Finding(
                f"{site} CONTROL (child killed before subscribe)",
                f"a subscriber received {control['bytes']} byte(s) and reported "
                f"{control['snap'].state!r} with the publisher already dead — so "
                "arrival in the measured half is not evidence that a live second "
                "process produced it",
            )
        ]
    evidence.append(
        f"A6 ACROSS A REAL PROCESS BOUNDARY: child pid {live['child_pid']} "
        f"(this process is {live['own_pid']}) bound {live['endpoint']}, published "
        f"picture version {live['announced']['version']} BEFORE any subscriber "
        f"existed, and this process's mirror reached "
        f"{snap.state.value}/sizeable on {live['bytes']} byte(s) in "
        f"{live['waited_s']:.2f}s carrying stop_distance {CHILD_STOP_TICKS}; the "
        f"killed-child CONTROL took {control['bytes']} byte(s) and reported "
        f"{control['snap'].state.value}"
    )
    return []


def _remove_tree(root: Path) -> None:
    """Delete the scratch bus directory by ABSOLUTE path, never `shutil.rmtree`.

    ARC 026 measured why: on POSIX `rmtree` recurses on directory file
    descriptors and unlinks with a BARE RELATIVE name, which the audit hook
    records as `file-write:<basename>` — a claim no honest `file-write:/tmp`
    declaration can ever cover.
    """
    if not root.is_dir():
        return
    for child in sorted(root.iterdir()):
        try:
            child.unlink()
        except OSError:
            continue
    try:
        root.rmdir()
    except OSError:
        pass


def _cannot(detail: str) -> CheckResult:
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Drive the real mirror: a race, a half-built feed, an older reading, a socket."""
    loaded, error = load(ctx.nix_home)
    if loaded is None:
        return _cannot(error)
    evidence: list[str] = []
    findings: list[Finding] = []
    root = Path(tempfile.mkdtemp(prefix="nixalloc-mirror-gate-"))
    try:
        findings += _arm_atomicity(loaded, evidence)
        findings += _arm_staleness(loaded, evidence)
        findings += _arm_monotonic(loaded, evidence)
        findings += _arm_readonly(loaded, evidence)
        findings += _arm_transport(
            loaded, root, float(secrets.randbelow(9000) + 1000), evidence
        )
        findings += _arm_cross_process(loaded, ctx.nix_home, root, evidence)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return _cannot(
            f"the mirror could not be driven: {type(exc).__name__}: {exc}; "
            f"measured so far: {'; '.join(evidence)}"
        )
    finally:
        _remove_tree(root)
    if findings:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site="; ".join(site for site, _ in findings),
            evidence="; ".join(evidence),
            detail="; ".join(f"{site}: {why}" for site, why in findings),
        )
    return CheckResult(name=NAME, status=Status.PASS, evidence="; ".join(evidence))


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
