#!/usr/bin/env python3
# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK — `PRIVILEGE`/`INTERACTIVE`/
# `DISRUPTIVE`, `DEPENDS_ON`/`RESOURCES`/`TIME_BOUND`/`CORRECTABLE`/`SUBJECTS`,
# and the `standalone_main` `__main__` — against every other check's. That
# similarity is the CONTRACT (`nix_check_contract.md` §4.2, §4.4): every check
# must declare the same symbols and must be independently runnable, so the
# blocks are identical BY REQUIREMENT and factoring them into a shared helper
# would break the contract to satisfy a similarity counter. Same pragma, same
# reason, as `scripts/nixverify/actuation.py` line 1.
"""Gate: the price firehose ring works, AND it is the ONLY shared memory in Nix.

Subject: `scripts/nixbus/price_ring.py`, a live `/dev/shm` segment, and every
`.py` file in the tree.
Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §12.7 (*"Sole exception — the
price firehose ... shared-memory single-writer ring buffer ... **Strictly one
writer by construction; prices only, never financial state**"*), §10, §11;
`docs/nix_check_contract.md` §4-§5.

## TWO CLAIMS, AND THE SECOND IS THE ONE THAT DECAYS

1. **The ring works** — a reader gets the writer's ticks, byte for byte, and is
   told exactly how many it missed.
2. **Nothing else uses shared memory** — §12.7 calls this the *sole* exception,
   and an exception is a claim about everything *outside* it. Claim 1 is proven
   by driving the ring. Claim 2 cannot be proven by driving anything: it is a
   property of the whole tree, and it is the one that silently stops being true
   the first time somebody reaches for `mmap` because it was convenient. So this
   gate sweeps every `.py` file in the tree by AST and FAILS naming any file
   outside a four-entry allow-list.

## debug.md §7.12 — the standing question, asked at the point this gate is built

**What would have to be true for this gate to PASS while measuring nothing?**

1. **The ring is created and never written to.** Zero ticks read, no exception,
   green. *Closed by the NON-VACUITY PRECONDITION:* fewer ticks recovered than
   were published is a defect, and **zero recovered is CANNOT_MEASURE, never
   PASS**.
2. **Ticks are counted and their CONTENT never checked.** *Closed by arm 1*,
   which asserts the exact `price`, `size`, `venue_ts_ns` and `symbol_id` of
   every recovered tick against what was published, in order.
3. **Overrun is silently absorbed.** A ring that drops without saying so is worse
   on the hot path than one that fails. *Closed by arm 2*, which deliberately
   overflows a small ring and requires the drop count to be **exactly** the
   arithmetic answer — not merely non-zero.
4. **"Single writer by construction" is a comment.** *Closed by arm 3*, the
   CONTROL: a second writer is attempted against the live segment and must be
   REFUSED with the incumbent PID named. A refusal that named nothing would be
   indistinguishable from any other failure to open a segment.
5. **The segment is a Python object and never a kernel one.** *Closed by arm 4*,
   which requires `/dev/shm/<name>` to exist while the writer is alive and to be
   GONE after `close()` — kernel state, before and after.
6. **THE SWEEP FINDS NOTHING BECAUSE THE SWEEP IS BROKEN.** This is the vacuity
   that matters, because a detector that matches nothing reports a clean tree
   forever. *Closed by the sweep's own control:* the sweep must find the KNOWN
   shared-memory uses inside `price_ring.py` itself. Zero hits anywhere in the
   tree is CANNOT_MEASURE — the detector proved itself broken, not the tree
   proved itself clean. The enumeration is also floored: too few files scanned
   is CANNOT_MEASURE, for the same reason `check_artifact_gate_coverage` floors
   its artifact set.

## Why the sweep walks the filesystem instead of asking git

`check_artifact_gate_coverage`'s own docstring names *"a tracking state silently
sets a gate's scope"* as this project's recurring defect class. An UNTRACKED file
that maps shared memory is still a second user of shared memory, so the scope
here is the filesystem. `.venv` is excluded and that exclusion is stated: it is
third-party code, it is full of legitimate `mmap`, and §12.7 constrains Nix.
"""

from __future__ import annotations

import ast
import dataclasses
import os
import secrets
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixbus.price_ring import (
    SHM_DIR,
    PriceRingError,
    PriceRingReader,
    PriceRingWriter,
)
from nixverify.contract import (
    CheckResult,
    Context,
    Mode,
    Status,
    result_from_defects,
)

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: `price_ring` is stdlib-only, and the sweep reads files. Nothing must run first.
DEPENDS_ON: tuple[str, ...] = ()
#: ONE claim, and it is one this project's observer CANNOT see — stated because
#: ARC 025's finding was seven declarations that were false in the permissive
#: direction:
#: * `shm` — a POSIX shared-memory segment under `/dev/shm`.
#:   `multiprocessing.shared_memory` reaches the kernel through
#:   `_posixshmem.shm_open` and `mmap`, and **neither raises a CPython audit
#:   event**, so `check_observed_resource_claims` will observe this gate touching
#:   no shared memory whatsoever. The declaration is therefore the ONLY record
#:   that the claim exists, which is exactly why it is here and not omitted.
#:   Any future check that opens a segment must collide with this one.
#: File reads are deliberately not declared: the observer does not record reads,
#: and a read is not a contended claim.
RESOURCES: tuple[str, ...] = ("shm",)
TIME_BOUND = True
#: An in-memory round-trip plus an AST parse of a few dozen small files.
EXPECTED_S = 5.0
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the exception's narrowness is closed by deleting a second shared-memory "
    "user, which is a code change; an instrument that edited source to satisfy "
    "its own sweep would be manufacturing its own green"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/nixbus/price_ring.py",
    #: The package docstring is where §12.7's three-way split is written down —
    #: state tables over ZMQ, prices over shared memory, nothing else. That claim
    #: is this gate's subject as much as the ring itself is.
    "scripts/nixbus/__init__.py",
)

NAME = "check_price_ring"

#: Small on purpose: the overrun arm has to be able to overflow it cheaply.
GATE_CAPACITY = 8
#: Published in the round-trip arm. Below `GATE_CAPACITY` so nothing is dropped.
ROUND_TRIP_TICKS = 5
#: Published in the overrun arm. The drop count is then exactly this minus the
#: capacity, and "exactly" is what the arm asserts.
OVERRUN_TICKS = 20

#: The ONLY files permitted to touch shared memory. Repo-relative. FOUR entries,
#: and each earns its place: the implementation, this gate, the implementation's
#: own test, and this gate's own test — which necessarily plants the constructs
#: the detector looks for in order to prove the detector matches them.
#:
#: Docstrings are NOT counted as uses (see `_ShmVisitor.visit_Constant`), so a
#: file that merely explains the exception never lands here. Every entry below is
#: a file that genuinely executes or plants shared-memory code.
ALLOWED = frozenset(
    {
        "scripts/nixbus/price_ring.py",
        "checks/check_price_ring.py",
        "scripts/tests/test_price_ring.py",
        "scripts/tests/test_check_price_ring.py",
    }
)

#: Directories the sweep does not enter, each for a stated reason.
_SKIP_DIRS = frozenset(
    # `.claude` holds agent WORKTREES — full copies of this repo the harness
    # checks out for sub-agents. A filesystem sweep that walked into them would
    # scan (and flag) the price ring's OWN legitimate `shared_memory` use in every
    # live worktree copy, which is the tree scanning itself. ARC 029: measured, a
    # sub-agent worktree drove this gate to FAIL on `.claude/worktrees/*/price_ring`.
    # `.venv-dev` (ARC CRUCIBLE-DEPSPLIT): the same reasoning as `.venv` above,
    # one line down — third-party code (numpy/pandas/pip's own vendored mmap
    # use), never Nix's. Same exclusion, same stated reason, second venv.
    {
        ".venv",
        ".venv-dev",
        ".git",
        ".claude",
        "__pycache__",
        "graphify-out",
        "node_modules",
    }
)

#: Module names whose import IS a shared-memory claim.
_SHM_MODULES = frozenset(
    {
        "mmap",
        "multiprocessing.shared_memory",
        "posix_ipc",
        "sysv_ipc",
        "_posixshmem",
    }
)
#: Names whose use is a shared-memory claim regardless of how they were imported.
_SHM_NAMES = frozenset(
    {"SharedMemory", "ShareableList", "shared_memory", "RawArray", "RawValue"}
)
#: A literal naming the shm filesystem is a claim on it however it is used.
# nosec B108 - this is a DETECTOR PATTERN, not a path this gate opens. It is the
# string the sweep looks for in other people's source; bandit's heuristic cannot
# tell a literal being searched for from a literal being used.
_SHM_LITERAL = "/dev/shm"  # nosec B108

#: Below this the enumeration is not credible. Anchored to a floor, never to
#: today's count — a threshold equal to the current number reddens on the next
#: file added (`check_artifact_gate_coverage`'s reasoning, reused deliberately).
MIN_CREDIBLE_FILES = 20


class _ShmVisitor(ast.NodeVisitor):
    # pylint: disable=invalid-name
    # `visit_<NodeType>` is `ast.NodeVisitor`'s dispatch contract, and the node
    # types are CamelCase. Renaming to snake_case would silently stop the
    # dispatcher finding these methods — a detector that matches nothing, which
    # is the exact vacuity this gate's §7.12 answer 6 exists to prevent.
    """Collect shared-memory constructs in one module. AST, never regex.

    Regex over source would match the word `mmap` inside this very docstring and
    inside every comment explaining why a file does NOT use shared memory — a
    detector whose false positives are concentrated in the files that discuss it
    is worse than no detector.
    """

    def __init__(self, docstrings: frozenset[int]) -> None:
        self.hits: list[str] = []
        #: `id()`s of the Constant nodes that are DOCSTRINGS. Excluded from the
        #: literal rule, and the exclusion is the whole reason this detector is
        #: usable: every file that explains why it does NOT use shared memory
        #: contains the words, and a detector whose false positives cluster on
        #: the files discussing it is worse than no detector. An import or an
        #: attribute is unaffected — those are uses, not prose.
        self._docstrings = docstrings

    def visit_Import(self, node: ast.Import) -> None:
        """`import mmap`, `import posix_ipc`."""
        for alias in node.names:
            if alias.name in _SHM_MODULES or alias.name.split(".")[0] in _SHM_MODULES:
                self.hits.append(f"line {node.lineno}: import {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """`from multiprocessing import shared_memory`, `from mmap import mmap`."""
        module = node.module or ""
        for alias in node.names:
            full = f"{module}.{alias.name}" if module else alias.name
            if (
                module in _SHM_MODULES
                or full in _SHM_MODULES
                or alias.name in _SHM_NAMES
            ):
                self.hits.append(
                    f"line {node.lineno}: from {module} import {alias.name}"
                )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """`multiprocessing.shared_memory.SharedMemory`, `mp.RawArray`."""
        if node.attr in _SHM_NAMES:
            self.hits.append(f"line {node.lineno}: attribute .{node.attr}")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        """A bare `SharedMemory(...)` after a `from ... import`."""
        if node.id in _SHM_NAMES:
            self.hits.append(f"line {node.lineno}: name {node.id}")
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        """A literal `/dev/shm` path — in CODE, never in a docstring."""
        if (
            isinstance(node.value, str)
            and _SHM_LITERAL in node.value
            and id(node) not in self._docstrings
        ):
            self.hits.append(f"line {node.lineno}: literal {_SHM_LITERAL!r}")
        self.generic_visit(node)


def _docstring_ids(tree: ast.Module) -> frozenset[int]:
    """`id()` of every module/class/function docstring Constant in `tree`."""
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    return frozenset(
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, holders)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    )


def _python_files(home: Path) -> list[Path]:
    """Every `.py` under `home`, minus the stated exclusions.

    ARC 026 Stage 2. AppleDouble sidecars (`._name`) are excluded, and the
    exclusion is a FILENAME CLASS rather than a tracking state — which is the
    distinction that matters here, because "git tracking state silently sets
    gate scope" is this project's most-repeated defect and the canonical path
    is now the live Samba share, so macOS metadata lands in the tree as a
    matter of course. Filtering on `git check-ignore` would have been that
    defect; filtering on a name pattern stated in the source is not.

    These files are not Python and cannot be: an AppleDouble sidecar is the
    resource fork and extended attributes of its sibling, raw bytes with NUL
    at offset 0 (this tree's carry `com.apple.quarantine`). PEP 263 requires
    source be decodable text, so a sidecar cannot contain an `import mmap` for
    the sweep to miss. They were reaching `ast.parse`, raising
    UnicodeDecodeError, and correctly driving the whole gate to CANNOT_MEASURE
    — fail-closed working exactly as designed, on 37 files that are not code.

    Over-exclusion cannot hide here: `MIN_CREDIBLE_FILES` runs on the result of
    this function, so a filter that ate the tree fails the credibility floor
    instead of returning a clean sweep.
    """
    found: list[Path] = []
    for path in home.rglob("*.py"):
        if _SKIP_DIRS.intersection(path.parts):
            continue
        if path.name.startswith("._"):
            continue
        found.append(path)
    return sorted(found)


def sweep(home: Path) -> tuple[dict[str, list[str]], list[str], int]:
    """`({relpath: hits}, unparseable, files_scanned)` over the whole tree."""
    hits: dict[str, list[str]] = {}
    unparseable: list[str] = []
    files = _python_files(home)
    for path in files:
        rel = str(path.relative_to(home))
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, ValueError) as exc:
            unparseable.append(f"{rel}: {exc!r}")
            continue
        visitor = _ShmVisitor(_docstring_ids(tree))
        visitor.visit(tree)
        if visitor.hits:
            hits[rel] = visitor.hits
    return hits, unparseable, len(files)


@dataclasses.dataclass
class _RoundTrip:
    """Everything one drive of the ring learned, so no arm has to re-drive it."""

    ticks: list = dataclasses.field(default_factory=list)
    dropped: int = 0
    pid: int = 0
    refusal: str = ""
    #: `/dev/shm/<name>` observed WHILE the writer was alive. Captured inside the
    #: drive because after `close(unlink=True)` there is nothing left to observe,
    #: and an arm that checked afterwards could only ever see the absence.
    alive_in_shm: bool = False


def _round_trip(name: str) -> _RoundTrip:
    """Publish `ROUND_TRIP_TICKS`, read them back, and run the writer CONTROL."""
    writer = PriceRingWriter(name, capacity=GATE_CAPACITY)
    try:
        reader = PriceRingReader(name)
        for index in range(ROUND_TRIP_TICKS):
            writer.publish(
                symbol_id=100 + index,
                price=4_512.25 + index,
                size=float(index + 1),
                venue_ts_ns=1_700_000_000_000_000_000 + index,
            )
        ticks, dropped = reader.poll()
        outcome = _RoundTrip(
            ticks=ticks,
            dropped=dropped,
            pid=os.getpid(),
            refusal=_second_writer_refusal(name),
            alive_in_shm=(SHM_DIR / name).exists(),
        )
        reader.close()
        return outcome
    finally:
        writer.close()


def _second_writer_refusal(name: str) -> str:
    """CONTROL — attempt a second writer. Returns the refusal message, or ''."""
    try:
        rogue = PriceRingWriter(name, capacity=GATE_CAPACITY)
    except PriceRingError as exc:
        return str(exc)
    rogue.close(unlink=False)
    return ""


def _overrun(name: str) -> tuple[int, int]:
    """Overflow a small ring. `(ticks_recovered, dropped)`."""
    writer = PriceRingWriter(name, capacity=GATE_CAPACITY)
    try:
        reader = PriceRingReader(name)
        for index in range(OVERRUN_TICKS):
            writer.publish(1, float(index), 1.0, index)
        ticks, dropped = reader.poll()
        reader.close()
        return len(ticks), dropped
    finally:
        writer.close()


def _arm1_content(ticks: list, dropped: int, defects: list, ev: list) -> None:
    """Every recovered tick equals what was published, in order."""
    site = "scripts/nixbus/price_ring.py:PriceRingReader.poll"
    if dropped:
        defects.append((site, f"{dropped} tick(s) dropped with the ring not full"))
        return
    if len(ticks) != ROUND_TRIP_TICKS:
        defects.append(
            (site, f"published {ROUND_TRIP_TICKS} ticks, recovered {len(ticks)}")
        )
        return
    for index, tick in enumerate(ticks):
        expected = (100 + index, 4_512.25 + index, float(index + 1))
        actual = (tick.symbol_id, tick.price, tick.size)
        if actual != expected or tick.venue_ts_ns != 1_700_000_000_000_000_000 + index:
            defects.append(
                (
                    site,
                    (
                        f"tick {index} came back as {actual}/{tick.venue_ts_ns}, "
                        f"published {expected}/"
                        f"{1_700_000_000_000_000_000 + index}"
                    ),
                )
            )
            return
    ev.append(
        f"round-trip: {len(ticks)} ticks byte-exact, last price={ticks[-1].price} "
        f"venue_ts_ns={ticks[-1].venue_ts_ns}"
    )


def _arm2_overrun(recovered: int, dropped: int, defects: list, ev: list) -> None:
    """Overrun is counted EXACTLY, not merely noticed."""
    site = "scripts/nixbus/price_ring.py:PriceRingReader._resync"
    expected_drop = OVERRUN_TICKS - GATE_CAPACITY
    if dropped != expected_drop or recovered != GATE_CAPACITY:
        defects.append(
            (
                site,
                (
                    f"published {OVERRUN_TICKS} into a {GATE_CAPACITY}-slot ring and "
                    f"the reader reported {recovered} recovered / {dropped} dropped; "
                    f"exactly {GATE_CAPACITY} / {expected_drop} is the arithmetic "
                    "answer, and a ring that miscounts its own gap is worse on the "
                    "hot path than one that fails"
                ),
            )
        )
        return
    ev.append(f"overrun counted exactly: {recovered} recovered, {dropped} dropped")


def _arm3_single_writer(control: str, pid: int, defects: list, ev: list) -> None:
    """CONTROL — a second writer is refused, and the refusal names the incumbent."""
    site = "scripts/nixbus/price_ring.py:PriceRingWriter._claim_segment"
    if not control:
        defects.append(
            (
                site,
                (
                    "a SECOND writer attached to the live segment — §12.7's "
                    "'strictly one writer by construction' is then a convention, "
                    "not a construction"
                ),
            )
        )
        return
    if f"pid={pid}" not in control:
        defects.append(
            (
                site,
                f"the refusal does not name the incumbent PID {pid}: {control[:160]}",
            )
        )
        return
    ev.append(f"CONTROL: second writer refused naming incumbent pid={pid}")


def _arm4_kernel(name: str, alive: bool, defects: list, ev: list) -> None:
    """The segment is real to the kernel while alive, and gone afterwards."""
    site = str(SHM_DIR / name)
    after = (SHM_DIR / name).exists()
    if not alive:
        defects.append((site, "no segment in /dev/shm while the writer was alive"))
        return
    if after:
        defects.append((site, "the segment survived close(unlink=True)"))
        return
    ev.append(f"kernel state: {site} present while alive, absent after close")


def _arm5_narrowness(
    hits: dict[str, list[str]], scanned: int, defects: list, ev: list
) -> None:
    """§12.7's exception is SOLE. Any file outside the allow-list is a defect."""
    strays = {rel: found for rel, found in hits.items() if rel not in ALLOWED}
    for rel, found in sorted(strays.items()):
        defects.append(
            (
                rel,
                (
                    f"shared memory outside §12.7's sole exception ({found[0]}) — "
                    "the price firehose is the ONE permitted user; everything else "
                    "goes over ZeroMQ"
                ),
            )
        )
    if not strays:
        ev.append(
            f"narrowness: {scanned} .py files swept, shared memory confined to "
            f"{sorted(hits)}"
        )


def _cannot(detail: str, evidence: list[str]) -> CheckResult:
    """CANNOT_MEASURE with whatever was learned before the wall."""
    return CheckResult(
        name=NAME,
        status=Status.CANNOT_MEASURE,
        detail=detail,
        evidence="; ".join(evidence),
    )


def _sweep_or_cannot(
    home: Path, evidence: list[str]
) -> tuple[dict[str, list[str]], int, CheckResult | None]:
    """Run the sweep and apply its two non-vacuity floors."""
    hits, unparseable, scanned = sweep(home)
    if scanned < MIN_CREDIBLE_FILES:
        return (
            hits,
            scanned,
            _cannot(
                f"the sweep found only {scanned} .py files under {home} — this "
                f"repository cannot honestly have fewer than {MIN_CREDIBLE_FILES}, "
                "so the enumeration is wrong and its clean result means nothing",
                evidence,
            ),
        )
    if unparseable:
        return (
            hits,
            scanned,
            _cannot(
                f"{len(unparseable)} file(s) would not parse, so the sweep did not "
                f"cover the tree: {unparseable[:3]}",
                evidence,
            ),
        )
    covered = set(hits) & ALLOWED
    if not covered:
        return (
            hits,
            scanned,
            _cannot(
                "the sweep found NO shared-memory construct anywhere, including "
                "inside scripts/nixbus/price_ring.py, which certainly has them — "
                "the detector is broken and its clean tree is an artefact of the "
                "instrument, not a property of the code",
                evidence,
            ),
        )
    return hits, scanned, None


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Drive the ring, then prove nothing else in the tree reaches for shm."""
    home = Path(ctx.nix_home)
    evidence: list[str] = []
    defects: list[tuple[str, str]] = []

    hits, scanned, blocked = _sweep_or_cannot(home, evidence)
    if blocked is not None:
        return blocked

    name = f"nix_ring_gate_{os.getpid()}_{secrets.token_hex(4)}"
    try:
        drive = _round_trip(name)
        recovered, over_dropped = _overrun(f"{name}_o")
    except (PriceRingError, OSError) as exc:
        return _cannot(f"the ring could not be driven: {exc!r}", evidence)

    # THE NON-VACUITY PRECONDITION. Zero ticks recovered is never a PASS.
    if not drive.ticks:
        return _cannot(
            f"{ROUND_TRIP_TICKS} ticks were published and ZERO were recovered — a "
            "ring that carried nothing cannot report that the firehose is well",
            evidence,
        )
    evidence.append(f"ring carried {len(drive.ticks)} real ticks")

    _arm1_content(drive.ticks, drive.dropped, defects, evidence)
    _arm2_overrun(recovered, over_dropped, defects, evidence)
    _arm3_single_writer(drive.refusal, drive.pid, defects, evidence)
    _arm4_kernel(name, drive.alive_in_shm, defects, evidence)
    _arm5_narrowness(hits, scanned, defects, evidence)
    return result_from_defects(NAME, defects, "; ".join(evidence))


if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
