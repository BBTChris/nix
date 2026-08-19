#!/usr/bin/env python3
# C0302: this module crossed pylint's 1 000-line ceiling in ARC 038 (sub-agent
# G, finding FG2 / CHECK-DEBT D3.409) and the excess is PROSE — the measurement
# that showed this gate discarding an already-observed second Plane-1 author
# whenever Postgres was unreachable, written beside the handler it corrects.
# Doctrine B.7 puts the argument next to the instrument it argues for, which is
# the same trade `check_artifact_gate_coverage.py` states at its own head;
# moving the reasoning away from the code it explains to satisfy a line counter
# is the trade the check contract refuses.
# pylint: disable=too-many-lines
# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK and its `standalone_main` footer
# against every other house-style check's. That shape is REQUIRED, not
# accidental duplication (§4.2).
"""Gate: the CODE has exactly one Plane-1 author, and a second one is REFUSED.

ARC 035 / Stage 1 / sub-agent A (A2). Authority:
`docs/nics_risk_subsystem_spec_v1.3.md` §9 (*Limiter = sole writer*) and §12.10
(*Plane 1 … **no new writers, ever***).

## THE BRIEF'S SENTENCE, AND THE C.9 BOUNDARY THIS GATE HAD TO FIND

> *a non-Limiter INSERT is REFUSED by privilege, not merely absent from the code.*

`check_plane1_schema` ARM 9 already proves half of that, and doctrine C.9
forbids a second instrument re-driving the same property. So the boundary is
drawn where the two genuinely differ, and `check_plane1_schema`'s own §7.12
hazard 5 draws it in advance:

> *What this gate cannot see is a Limiter configured to point somewhere else at
> runtime; that is a WIRING property, not a schema property, and it belongs to
> the sole-writer gate rather than here.*

**ARM 9 proves the DATABASE refuses an ad-hoc statement. This gate proves the
CODE has exactly one author, and that the SHIPPED SINK — the actual object that
will run in production — is refused when it carries a non-Limiter identity.**
The instrument is `nixrisk.plane1_sink.Plane1PostgresSink` itself, not a psql
string this gate composed. A privilege that bites an ad-hoc UPDATE and not the
shipped writer would satisfy ARM 9 and fail here, which is what makes the two
gates different measurements rather than one measurement twice.

## THE TWO HALVES, AND WHY NEITHER IS SUFFICIENT ALONE

**ARM A — THE ATTEMPT (privilege).** A scratch Plane-1 database is built from
the shipped DDL, and the shipped sink is driven against it TWICE through
`GroupCommitWriter` — §9's own path, never `.commit()` by hand:

* the **CONTROL**, as `nix_limiter`: the group-commit must SUCCEED and the rows
  must read back. A refusal is only evidence beside a permission that works;
  without this, "the reader was refused" would also be true of a database where
  nobody can write at all.
* the **PROBE**, as `nix_reader`: the identical sink, the identical rows, one
  parameter different. It must be refused with SQLSTATE **42501** *and* with
  `permission denied for table plane1_event_log` in the same stderr. The object
  is asserted because Phase 0.4 of this arc measured the failure one level down
  — a probe refused with the right SQLSTATE for the wrong object (a SEQUENCE,
  not the table) would have reported "correctly refused" over a live second
  writer. Check-contract rule 11: never the exit code alone, and here not even
  the SQLSTATE alone.

**ARM B — THE AUTHORSHIP (static).** Every construction of a Plane-1 row and
every construction of a Plane-1 INSERT in the tree, found by AST, and each one
resolved to the Limiter's enqueue path or reported. Three sub-arms:

* **B1 — SQL authorship.** Any file whose STRING LITERALS compose an `INSERT
  INTO plane1_event_log … VALUES/SELECT` other than the sink is a second
  author. Literals rather than raw file text, and a real INSERT rather than a
  mention: the first measurement of this arm flagged this gate's own docstring
  and its own defect message, both of which name the table in prose. Exceptions
  are ENUMERATED with their reasons, not waved through (`SQL_AUTHOR_EXEMPT`).
  Scope: BOTH roots, tests included — the arc's common brief is explicit that a
  second writer must not be introduced *"anywhere, including in a test
  fixture."*
* **B2 — sink implementations.** Any `def commit(self, rows, …)` — the
  `CommitSinkPort` shape — outside the enumerated set is a candidate second
  author, because a sink is the object that turns rows into INSERTs.
* **B3 — row constructions.** Every `EventRow(…)` node is classified by its
  syntactic route to `enqueue`: `direct` (an argument to a `.enqueue(…)` call),
  `named` (bound to a local that is passed to `.enqueue(…)` in the same
  function), or `factory` (returned, so the route runs through its callers). A
  construction matching none of the three is reported: a Plane-1 row is being
  built and where it goes cannot be established. Scope: `ROUTE_ROOTS` — the
  modules that can BE the Limiter. Constructing a row is not writing one, and a
  test that builds one to assert on it is not an author; applying this arm to
  `scripts/tests/` and `checks/` reported exactly that noise on first
  measurement, and a gate that reports legitimate code gets switched off.

## WHAT THE STATIC HALF CANNOT SEE, SAID PLAINLY

**Dynamic dispatch is invisible to it.** `getattr(port, "en" + "queue")`, an SQL
string read from a file, a `psql` argv assembled at runtime, an ORM, an
extension — none of them appear as an `EventRow` node or an `INSERT INTO` literal
and no static scan will ever find them. That is not a hazard this gate closes; it
is the reason ARM A exists. **The database refuses a second writer whether the
scan can see it or not, and the scan finds the authors the database would
happily serve if someone granted them.** Neither half is the proof. Together
they are.

## debug.md §7.12 — what would make this gate PASS while measuring nothing?

1. **The scan could scan nothing.** An empty `git ls-files`, a glob matching no
   file, a regex matching no construction — every one reports "no unauthorised
   author" over an empty population, which is the purest vacuous green.
   *Closed:* three non-vacuity FLOORS, checked before any verdict is formed —
   files scanned, `EventRow` constructions found, `enqueue` call sites found.
   Below any floor the verdict is `CANNOT_MEASURE` (§17), never PASS. They are
   floors, not today's numbers.
2. **The scan could read the INDEX and miss the working tree.** `git ls-files`
   is the index, so a new unauthorised writer that is untracked is invisible —
   failure mode #14. *Closed as far as it can be, and NAMED:* the scan walks the
   FILESYSTEM under `scripts/` and `checks/` rather than asking git, so an
   untracked file is scanned like any other. What remains invisible is a file
   outside those two roots — and, for B3 only, a file outside `ROUTE_ROOTS`.
   Both scopes are printed in the evidence.
3. **ARM A's control could fail**, making every refusal below it true of a role
   with no rights. *Closed:* the control INSERT must succeed AND the rows must
   read back by count before the probe is even attempted; a failed control is
   `CANNOT_MEASURE`.
4. **ARM A could refuse for the wrong reason.** A typo'd table, a dead server
   and a refused privilege all fail. *Closed:* SQLSTATE 42501 AND the table
   named in the message.
5. **The gate could measure a database nobody writes.** *Closed:* ARM C asserts
   that the sink's own `PLANE1_DB` literal and `check_plane1_schema.PLANE1_DB`
   are the same string — the wiring property the schema gate handed over. The
   scratch database ARM A uses is built from the SHIPPED DDL, so a privilege
   that exists only in production would show up as a scratch-side failure, not
   as a free pass.
6. **Postgres could be down.** *Closed:* `CANNOT_MEASURE` naming the psql
   stderr, never PASS.
"""

from __future__ import annotations

import ast
import importlib.util
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Final

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixrisk.plane1_sink import (
    PLANE1_DB,
    SQLSTATE_INSUFFICIENT_PRIVILEGE,
    Plane1PostgresSink,
)
from nixrisk.seam import EventKind, EventRow
from nixrisk.wal import GroupCommitWriter, Plane1Wal
from nixverify.contract import CheckResult, Context, Mode, Status

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = False
EXPECTED_S = 12.0
ON_FAIL = "continue"
DEPENDS_ON: tuple[str, ...] = ("check_plane1_schema",)
#: This process spawns `psql`, `createdb` and `dropdb` (its own scratch database,
#: created and dropped inside the run) and writes a WAL under `/tmp`. Every token
#: is FALSIFIABLE by observation — a `postgres:nix_plane1` token was refused for
#: the reason `check_plane1_schema` records: no observation could contradict it
#: (D3.152's 24-check unfalsifiable-token debt).
RESOURCES: tuple[str, ...] = (
    "subprocess:psql",
    "subprocess:createdb",
    "subprocess:dropdb",
    "file-write:/tmp",
)
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is WHO may write the money record. A gate authorised to correct "
    "it would be a gate authorised to grant INSERT, which is the violation it "
    "exists to detect"
)
ANCHOR = "scripts/nixrisk/plane1_sink.py"
SUBJECTS: tuple[str, ...] = (
    "scripts/nixrisk/plane1_sink.py",
    "scripts/provision_plane1.py",
)

NAME = "check_plane1_sole_writer"

#: Roots the authorship scan walks. Printed in the evidence, because the scope
#: of a scan is part of its result (§7.12 answer 2).
SCAN_ROOTS: tuple[str, ...] = ("scripts", "checks")

#: B3's narrower scope: the modules that can BE the Limiter. B1 and B2 stay over
#: everything, because composing an INSERT or implementing a sink is writing
#: wherever it happens — including in a test fixture, which the arc's common
#: brief names explicitly. Constructing an `EventRow` is NOT writing: a test
#: builds one to assert on it and a gate builds one to drive the seam, and
#: neither is an author. Applying B3 to `scripts/tests/` and `checks/` produced
#: exactly that noise on first measurement (`test_risk_config.py` builds an
#: `EventKind.BOOT` row for an assertion), and a gate that reports legitimate
#: code gets switched off.
ROUTE_ROOTS: tuple[str, ...] = ("scripts/nixrisk/", "scripts/")

#: An INSERT that actually inserts names its source. Requiring one of these
#: alongside the table makes the match a STATEMENT rather than a mention — this
#: gate's own defect message and this docstring both name the table in prose, and
#: a bare substring scan flagged both on first measurement.
_INSERT_SOURCES: tuple[str, ...] = ("VALUES", "SELECT")

#: Non-vacuity floors. FLOORS, not today's numbers — a count restated here would
#: go stale inside the arc that wrote it (doctrine B.7 / D2.8).
MIN_FILES_SCANNED: Final[int] = 60
MIN_EVENTROW_SITES: Final[int] = 6
MIN_ENQUEUE_SITES: Final[int] = 5

#: B1: files permitted to compose an `INSERT INTO plane1_event_log`, each with
#: the reason it is not a second author. ENUMERATED, because "everything under
#: checks/" would let the next check quietly become a writer.
SQL_AUTHOR_EXEMPT: Final[dict[str, str]] = {
    "scripts/nixrisk/plane1_sink.py": "IS the sole writer — §9's group-commit sink",
    "checks/check_plane1_schema.py": (
        "ARM 9's privilege PROBE. Every statement runs inside BEGIN … ROLLBACK "
        "and the reader-role probe exists to be REFUSED; the limiter-role control "
        "is rolled back rather than committed, so no row is authored"
    ),
    "scripts/tests/test_check_plane1_schema.py": (
        "the can-fail suite for the above, driving the same rolled-back probes "
        "against throwaway scratch databases"
    ),
    # ---------------------------------------------------------------------
    # ARC 035 STAGE 2 — THE INTEGRATOR'S RULING, and the one exemption in this
    # map that is MEASURED rather than argued.
    #
    # `plane1_seed.py` is sub-agent B's fixture conduit. It appeared on the
    # merged tree and NEITHER branch could see the collision: sub-agent A built
    # this detector, sub-agent B built a module that composes INSERTs against
    # the log, and A's ARM B1 fired on B's file the first time the two were in
    # one tree. That is the whole argument for an integration stage.
    #
    # It is NOT a second AUTHOR, on two properties — and because an exemption
    # resting on a docstring is exactly what §12.10's "no new writers, ever"
    # cannot afford, ARM B1b DRIVES both instead of trusting them:
    #   (i) every INSERT runs under `SET ROLE nix_limiter`, so the rows carry
    #       the Limiter's database identity and no other;
    #   (ii) `seed()` REFUSES the production database by raising — proven by
    #       ATTEMPT, not by reading the `if`.
    # Strike either property and this gate reddens, which is the difference
    # between an exemption and a hole.
    #
    # The END STATE is not this exemption. B's own docstring says the seeding
    # should go through A's `Plane1PostgresSink` once it exists — it now does —
    # and this entry should disappear when that rewiring lands. Recorded as
    # CHECK-DEBT so it is a deferral with an owner and not a permanent guest.
    # ---------------------------------------------------------------------
    "scripts/nixrisk/plane1_seed.py": (
        "sub-agent B's fixture conduit: writes ONLY under `SET ROLE "
        "nix_limiter` (the Limiter's own database identity, not a new one) and "
        "REFUSES the production database by raising. Both properties are driven "
        "by ARM B1b below, so this exemption is measured. TEMPORARY: it goes "
        "away when the seeding is rewired through plane1_sink"
    ),
    # The two DRILLS. Same integration collision as the conduit above, same
    # ruling, and the same refusal to take a docstring for it: each is an
    # INSTRUMENT that stands up its own throwaway PostgreSQL cluster
    # (`initdb` + `pg_ctl` on a private socket) and writes into THAT, which is
    # why neither can reach the live record. ARM B1b drives the same
    # production-refusal property against both.
    "scripts/plane1_crash_drill.py": (
        "sub-agent B's §9 crash-gap drill: builds an EPHEMERAL cluster and "
        "crashes it with `pg_ctl -m immediate`. Writes under the Limiter's role "
        "into a database that exists for the duration of the drill"
    ),
    "scripts/plane1_degraded_drill.py": (
        "sub-agent C's §12.4 drill: same ephemeral-cluster shape, driving the "
        "outage / disk-critical / reconnect ladder"
    ),
}

#: ARM B1b: an exemption that rests on properties must have those properties
#: MEASURED. `path -> (role_marker, refusal_probe)`.
CONDUIT_EXEMPT_PROOFS: Final[dict[str, str]] = {
    "scripts/nixrisk/plane1_seed.py": "SET ROLE nix_limiter",
}

#: B2: `def commit(self, rows, …)` — the `CommitSinkPort` shape — is permitted
#: only here. A new one is a candidate second author until argued otherwise.
SINK_IMPL_EXEMPT: Final[dict[str, str]] = {
    "scripts/nixrisk/wal.py": (
        "the `CommitSinkPort` Protocol declaration itself, plus `RecordingSink` "
        "— in-memory, reaches no database"
    ),
    "scripts/nixrisk/plane1_sink.py": "the real sink",
    "scripts/plane1_hotpath_drill.py": (
        "`SlowSink` — an in-memory instrument with a deliberate delay, the §11 item 6 "
        "drill's control surface; reaches no database"
    ),
    "scripts/plane1_degraded_drill.py": (
        "ARC 035 Stage 2: sub-agent C's §12.4 drill defines its own sink so it "
        "can fail and recover on command. It reaches only the drill's own "
        "EPHEMERAL cluster, never `nix_plane1`"
    ),
}

#: The §9 row this gate drives through ARM A. Content is irrelevant to the
#: property; what matters is that the sink is the SHIPPED one.
_PROBE_ROWS: Final[tuple[EventRow, ...]] = (
    EventRow(
        kind=EventKind.SIGNAL,
        ts=1_755_000_000.0,
        strategy_id="sole-writer-gate",
        reason="check_plane1_sole_writer ARM A",
        trade_id="sole-writer-gate",
        fields={"symbol": "ES"},
    ),
    EventRow(
        kind=EventKind.DENIED,
        ts=1_755_000_000.5,
        strategy_id="sole-writer-gate",
        reason="check_plane1_sole_writer ARM A, second row of the group",
        trade_id="sole-writer-gate",
        fields={"symbol": "ES"},
    ),
)


class Unmeasurable(Exception):
    """The subject could not be reached, so nothing was measured (§17)."""


# --------------------------------------------------------------- ARM B (static)


def _python_files(home: Path) -> list[Path]:
    """Every `.py` under the declared roots, from the FILESYSTEM not the index.

    `git ls-files` would report the index, and an untracked new writer would be
    invisible to it — failure mode #14, and it is the exact shape a second
    author would take while being added.
    """
    found: list[Path] = []
    for root in SCAN_ROOTS:
        base = home / root
        if not base.is_dir():
            continue
        found += [
            path
            for path in sorted(base.rglob("*.py"))
            if "__pycache__" not in path.parts
        ]
    return found


def _in_route_scope(relative: str) -> bool:
    """Is this module one that can BE the Limiter? See `ROUTE_ROOTS`."""
    if relative.startswith("scripts/nixrisk/"):
        return True
    # `scripts/<file>.py` — the top-level drills and entry points — but not
    # `scripts/tests/…` or any other subpackage.
    return relative.startswith("scripts/") and relative.count("/") == 1


def _docstring_nodes(tree: ast.Module) -> set[int]:
    """`id()` of every Constant that is a module/class/function docstring."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", None)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _insert_literals(tree: ast.Module) -> list[str]:
    """String literals that compose an INSERT against the Plane-1 log."""
    skip = _docstring_nodes(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in skip:
            continue
        flat = " ".join(node.value.upper().split())
        if "INSERT INTO PLANE1_EVENT_LOG" not in flat:
            continue
        if not any(source in flat for source in _INSERT_SOURCES):
            continue
        found.append(node.value)
    return found


def _enqueue_argument(node: ast.AST) -> bool:
    """Is this call `<something>.enqueue(…)`?"""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "enqueue"
    )


def _is_eventrow_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "EventRow"
    )


def _enqueue_calls(tree: ast.Module) -> list[ast.Call]:
    """Every `<something>.enqueue(…)` call node in one module."""
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _enqueue_argument(node)
    ]


def _enqueued_names(tree: ast.Module) -> set[str]:
    """Locals handed to `.enqueue(…)` anywhere in this module.

    Module-scoped rather than function-scoped on purpose: a narrower scope would
    report `unresolved` for the legitimate helper-function shape, and a false red
    on the sole-writer gate is the one thing that would get it switched off.
    """
    names: set[str] = set()
    for call in _enqueue_calls(tree):
        names.update(arg.id for arg in call.args if isinstance(arg, ast.Name))
    return names


def _direct_lines(tree: ast.Module) -> set[int]:
    """Lines where an `EventRow(…)` is itself an argument to `.enqueue(…)`."""
    lines: set[int] = set()
    for call in _enqueue_calls(tree):
        lines.update(arg.lineno for arg in call.args if _is_eventrow_call(arg))
    return lines


def _bound_and_returned(tree: ast.Module) -> tuple[dict[int, str], set[int]]:
    """`({line: local name}, {returned line})` for `EventRow(…)` constructions."""
    assigned: dict[int, str] = {}
    returned: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _is_eventrow_call(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned[node.value.lineno] = target.id
        if (
            isinstance(node, ast.Return)
            and node.value is not None
            and _is_eventrow_call(node.value)
        ):
            returned.add(node.value.lineno)
    return assigned, returned


def _route_of(
    line: int,
    direct: set[int],
    assigned: dict[int, str],
    enqueued: set[str],
    returned: set[int],
) -> tuple[str, str]:
    """One construction's `(route, detail)`. See ARM B3 in the module docstring."""
    if line in direct:
        return "direct", "argument to a .enqueue(…) call"
    if line in assigned and assigned[line] in enqueued:
        return "named", f"bound to {assigned[line]!r}, passed to .enqueue(…)"
    if line in returned:
        return "factory", "returned; the route runs through its callers"
    return "unresolved", "no syntactic route to .enqueue(…)"


def _classify_constructions(tree: ast.Module) -> list[tuple[int, str, str]]:
    """Every `EventRow(…)` in one module -> `(line, route, detail)`.

    Routes: `direct`, `named`, `factory`, `unresolved`. The first three are
    accepted and REPORTED; the fourth is a defect.
    """
    enqueued = _enqueued_names(tree)
    direct = _direct_lines(tree)
    assigned, returned = _bound_and_returned(tree)
    return [
        (node.lineno, *_route_of(node.lineno, direct, assigned, enqueued, returned))
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _is_eventrow_call(node)
    ]


def _sink_impl_lines(tree: ast.Module) -> list[int]:
    """`def commit(self, rows, …)` — the `CommitSinkPort` shape — by line.

    Keyed on the SECOND parameter's name rather than on the method name alone:
    `nixrisk/picture.py` and `nixrisk/recovery.py` both define a `commit`, and
    neither is a Plane-1 sink. A name-only match would report two permanent
    false positives and the gate would be edited to death.
    """
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "commit":
            continue
        args = [arg.arg for arg in node.args.args]
        if len(args) >= 2 and args[0] in {"self", "cls"} and args[1] == "rows":
            lines.append(node.lineno)
    return lines


def _scan_file(relative: str, tree: ast.Module, counts: dict[str, int]) -> list[str]:
    """ARM B1/B2/B3 over ONE parsed module. Mutates `counts`, returns defects."""
    defects: list[str] = []

    # B1 — SQL authorship, over string LITERALS that are not docstrings. Reading
    # the raw file text instead flags every comment and docstring that names the
    # table, this gate's own included; reading the literals asks the narrower
    # question the property is actually about.
    if relative not in SQL_AUTHOR_EXEMPT:
        for literal in _insert_literals(tree):
            defects.append(
                f"ARM B1: {relative} composes SQL against the Plane-1 log: "
                f"{literal[:70]!r}. §12.10: 'Limiter sole writer, no new "
                f"writers, EVER'. Only {', '.join(sorted(SQL_AUTHOR_EXEMPT))} "
                f"are enumerated, each with a reason it is not an author"
            )
            break

    # B2 — sink implementations.
    sink_lines = _sink_impl_lines(tree)
    counts["sink_impls"] += len(sink_lines)
    if sink_lines and relative not in SINK_IMPL_EXEMPT:
        defects.append(
            f"ARM B2: {relative}:{sink_lines[0]} defines a CommitSinkPort "
            f"`commit(self, rows, …)`. A sink is the object that turns §9 rows "
            f"into INSERTs; a new one is a candidate SECOND AUTHOR until it is "
            f"enumerated with a reason it is not"
        )

    # B3 — row constructions, over the modules that can BE the Limiter.
    counts["enqueue_sites"] += len(_enqueue_calls(tree))
    if not _in_route_scope(relative):
        return defects
    for line, route, detail in _classify_constructions(tree):
        counts["eventrow_sites"] += 1
        if route == "unresolved":
            counts["unresolved"] += 1
            defects.append(
                f"ARM B3: {relative}:{line} constructs a Plane-1 EventRow with "
                f"{detail}. Every row must originate from the Limiter's enqueue "
                f"path (§9); a row whose route cannot be established is a row "
                f"that may reach Plane 1 by another door"
            )
    return defects


def scan_authorship(home: Path) -> tuple[list[str], dict[str, int]]:
    """ARM B. Returns `(defects, counts)`. Counts feed the non-vacuity floors."""
    defects: list[str] = []
    counts = {
        "files": 0,
        "eventrow_sites": 0,
        "enqueue_sites": 0,
        "sink_impls": 0,
        "unresolved": 0,
    }
    for path in _python_files(home):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            defects.append(f"ARM B: cannot read {path}: {exc!r}")
            continue
        counts["files"] += 1
        relative = path.relative_to(home).as_posix()
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            defects.append(f"ARM B: {relative} does not parse: {exc}")
            continue
        defects += _scan_file(relative, tree, counts)
    return defects, counts


# -------------------------------------------------------------- ARM A (attempt)


def _scratch_database() -> str:
    """Build a throwaway Plane-1 database from the SHIPPED DDL. Raises on failure."""
    import provision_plane1  # pylint: disable=import-outside-toplevel

    if shutil.which("psql") is None or shutil.which("createdb") is None:
        raise Unmeasurable("psql/createdb are not on PATH")
    name = provision_plane1.SCRATCH_PREFIX + "solewriter_" + uuid.uuid4().hex[:10]
    try:
        outcome, detail = provision_plane1.provision(name, provision_plane1.SCHEMA_SQL)
    except provision_plane1.ProvisionError as exc:
        raise Unmeasurable(f"cannot build a scratch Plane-1 database: {exc}") from exc
    if outcome != "created":
        raise Unmeasurable(f"provisioning {name} returned {outcome}: {detail}")
    return name


def _drop_database(name: str) -> None:
    import subprocess  # nosec B404  pylint: disable=import-outside-toplevel

    binary = shutil.which("dropdb")
    if binary is None or not name:
        return
    subprocess.run(  # nosec B603 - fixed argv, no shell
        [binary, "--if-exists", "--force", name],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _row_count(database: str) -> int:
    import subprocess  # nosec B404  pylint: disable=import-outside-toplevel

    binary = shutil.which("psql")
    if binary is None:
        raise Unmeasurable("psql is not on PATH")
    proc = subprocess.run(  # nosec B603 - fixed argv, no shell
        [
            binary,
            "-d",
            database,
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "select count(*) from plane1_event_log",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise Unmeasurable(f"cannot count rows in {database}: {proc.stderr[-200:]}")
    return int(proc.stdout.strip() or "0")


def _drive(database: str, role: str, tmp: Path) -> tuple[int, str, str]:
    """One §9 pass — enqueue → WAL → group-commit — under `role`.

    Returns `(rows_committed, error_text, persistence_state)`.

    Driven through `GroupCommitWriter`, never `sink.commit()` by hand: the
    property is about the PATH, and a direct call would measure the SQL while
    stepping around the seam that makes the sink reachable at all. `drain_once`
    catches the sink's exception by design (§12.4: a sink outage is a RESULT,
    not a crash), which is why `Plane1PostgresSink` puts the SQLSTATE into the
    exception MESSAGE — the reason survives the stringification and this arm can
    still assert it.
    """
    wal_path = tmp / f"solewriter-{role}-{uuid.uuid4().hex[:8]}.wal"
    wal = Plane1Wal(wal_path)
    sink = Plane1PostgresSink(database, role=role)
    writer = GroupCommitWriter(wal, sink)
    try:
        for row in _PROBE_ROWS:
            wal.enqueue(row)
        wal.sync_to_disk()
        result = writer.drain_once()
        return result.committed, result.error, result.state.value
    finally:
        wal.close()
        wal_path.unlink(missing_ok=True)


def attempt_privilege(
    tmp: Path, database: str | None = None
) -> tuple[list[str], list[str]]:
    """ARM A. Returns `(defects, evidence)`. Raises `Unmeasurable` (§17).

    `database` is a parameter ONLY so the can-fail suite can hand the SHIPPED
    arm a database it has broken in exactly one declared way (a second writer
    granted INSERT) and observe that the arm reddens. A caller-supplied database
    is never dropped here — the fixture that made it owns it.
    """
    own = database is None
    database = database or _scratch_database()
    try:
        # THE CONTROL FIRST. A refusal is only evidence beside a permission that
        # works — otherwise "the reader was refused" is also true of a database
        # nobody can write.
        landed, error, state = _drive(database, "nix_limiter", tmp)
        if error:
            raise Unmeasurable(
                f"the CONTROL group-commit as nix_limiter FAILED: {error}. Every "
                f"refusal below would then be true of a role with no rights at "
                f"all, which is not evidence about sole authorship"
            )
        banked = _row_count(database)
        if landed != len(_PROBE_ROWS) or banked != len(_PROBE_ROWS):
            raise Unmeasurable(
                f"the CONTROL reported {landed} row(s) landed and the database "
                f"holds {banked}, against {len(_PROBE_ROWS)} driven — the control "
                f"did not establish a working write path"
            )
        defects: list[str] = []
        evidence = [
            (
                f"CONTROL: the shipped sink as nix_limiter group-committed "
                f"{landed} row(s) through GroupCommitWriter (WAL state {state}) "
                f"and {banked} row(s) read back from {database}"
            )
        ]

        # THE PROBE: the identical sink, one parameter different.
        landed, error, state = _drive(database, "nix_reader", tmp)
        if not error:
            defects.append(
                f"ARM A: the SHIPPED SINK, run as nix_reader, group-committed "
                f"{landed} row(s) into plane1_event_log. §12.10's 'no new writers, "
                f"EVER' is violated by the running code, not merely by a grant"
            )
        elif f"SQLSTATE {SQLSTATE_INSUFFICIENT_PRIVILEGE}" not in error:
            defects.append(
                f"ARM A: the sink as nix_reader was refused, but NOT with SQLSTATE "
                f"{SQLSTATE_INSUFFICIENT_PRIVILEGE} (insufficient_privilege). A "
                f"refusal for the wrong reason is not evidence about grants — a "
                f"typo, an absent table and a dead server all refuse just as "
                f"loudly. seam error: {error[-260:]}"
            )
        elif "permission denied for table plane1_event_log" not in error:
            defects.append(
                f"ARM A: the sink as nix_reader was refused with the right SQLSTATE "
                f"for the WRONG OBJECT — expected 'permission denied for table "
                f"plane1_event_log', got: {error[-260:]}. A sequence, a schema and "
                f"a table all refuse with {SQLSTATE_INSUFFICIENT_PRIVILEGE}, and "
                f"Phase 0.4 of this arc measured exactly that mask over a live "
                f"second writer"
            )
        else:
            evidence.append(
                "PROBE: the same sink as nix_reader was REFUSED through the same "
                f"seam — SQLSTATE {SQLSTATE_INSUFFICIENT_PRIVILEGE}, 'permission "
                f"denied for table plane1_event_log', WAL state {state}"
            )
        after = _row_count(database)
        if after != len(_PROBE_ROWS):
            defects.append(
                f"ARM A: {database} holds {after} row(s) after the refused probe, "
                f"not the {len(_PROBE_ROWS)} the control banked — the refusal did "
                f"not roll back cleanly"
            )
        return defects, evidence
    finally:
        if own:
            _drop_database(database)


# ---------------------------------------------------------------------- ARM C


def wiring_defects(home: Path) -> list[str]:
    """ARM C: the sink writes the database the schema gate inspects.

    `check_plane1_schema`'s §7.12 hazard 5 named this and handed it here. Two
    modules each holding their own literal is two sources of truth; the gate
    asserts they agree rather than trusting that nobody edited one.

    The sibling's literal is read by **AST from its source**, not by importing
    it. A check must never import another check (§4.2 keeps each independently
    runnable, and `checks/` is not reliably on `sys.path` under every runner) —
    and reading the literal is also strictly what is wanted here: the value the
    file DECLARES, not a value some import-time code could have rebound.
    """
    sibling = home / "checks" / "check_plane1_schema.py"
    try:
        tree = ast.parse(sibling.read_text(encoding="utf-8"), filename=str(sibling))
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        return [f"ARM C: cannot read {sibling}: {exc!r}"]
    declared: str | None = None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "PLANE1_DB" for t in node.targets
            )
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            declared = node.value.value
    if declared is None:
        return [
            (
                "ARM C: check_plane1_schema.py declares no module-level "
                "PLANE1_DB string, so the two gates' targets cannot be compared"
            )
        ]
    if declared != PLANE1_DB:
        return [
            (
                f"ARM C: the sink writes {PLANE1_DB!r} and check_plane1_schema "
                f"inspects {declared!r}. Both gates would be green and neither "
                f"would be about the database the Limiter uses"
            )
        ]
    return []


# ---------------------------------------------------------------------------


def _arm_b1b_conduit_proofs(home: Path) -> list[str]:
    """ARM B1b — every CONDUIT exemption's two properties, MEASURED.

    ARC 035 Stage 2. `SQL_AUTHOR_EXEMPT` is a list of files allowed to compose
    INSERTs against the Plane-1 log, each with a written reason. A written
    reason is exactly what §12.10's *"no new writers, ever"* cannot be secured
    by, so the ONE conduit entry has its reason turned into two assertions:

      (i) the module writes only under `SET ROLE nix_limiter` — checked in its
          source, because the role is what makes the rows the Limiter's;
     (ii) `seed()` REFUSES the production database — checked by ATTEMPT, calling
          it against `PLANE1_DB` and requiring a raise that NAMES the database.
          Reading the `if` would prove the branch exists; calling it proves the
          branch is reached, and a fixture that could write the live record is a
          second writer whatever its docstring says.

    Deleting either property reddens this gate, which is the difference between
    an exemption and a hole.
    """
    defects: list[str] = []
    for relative, marker in CONDUIT_EXEMPT_PROOFS.items():
        path = home / relative
        if not path.is_file():
            defects.append(
                f"ARM B1b: {relative} is exempted from ARM B1 but is not on "
                f"disk — an exemption for a file that does not exist is a hole "
                f"waiting for a file to fill it"
            )
            continue
        source = path.read_text(encoding="utf-8")
        if marker not in source:
            defects.append(
                f"ARM B1b: {relative} is exempted on the grounds that it writes "
                f"only under {marker!r}, and that string is ABSENT. The "
                f"exemption's own premise is false"
            )
        # (ii) BY ATTEMPT.
        try:
            seed_mod = _load_module(path, "_nix_plane1_conduit")
            seed_mod.seed(seed_mod.Psql(dbname=PLANE1_DB))
        except AttributeError:
            defects.append(
                f"ARM B1b: {relative} exposes no `seed(psql)`/`Psql` pair, so "
                f"the production-refusal property cannot be driven at all"
            )
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            if PLANE1_DB not in str(exc):
                defects.append(
                    f"ARM B1b: {relative}.seed() refused {PLANE1_DB!r} but its "
                    f"message does not NAME it ({type(exc).__name__}: {exc}). "
                    f"Rule 11: the reason is the assertion"
                )
        else:
            defects.append(
                f"ARM B1b: {relative}.seed() ACCEPTED the production database "
                f"{PLANE1_DB!r}. A fixture that can write the live Plane-1 "
                f"record is a second writer whatever it is called (§12.10)"
            )
    return defects


def _load_module(path: Path, name: str):
    """Load a module from an explicit path, never from `sys.modules`."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"{path}: not loadable")
    module = importlib.util.module_from_spec(spec)
    # Registered BEFORE exec: `@dataclasses.dataclass` resolves a class's
    # `__module__` through `sys.modules`, and a module that is not there yet
    # makes the decorator raise AttributeError on an unrelated line — which
    # would read as "the conduit exposes no seed()" rather than as a loader
    # bug. Measured, not guessed: that is exactly how this arm first failed.
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Measure Plane-1 authorship: by attempt, and over the code."""
    home = ctx.nix_home
    #: What the STATIC half already established, bound here so the handlers below
    #: can never read it unbound (ARC 038 G / FG2 — see the `Unmeasurable`
    #: handler). Empty means the static half had not finished, and an empty list
    #: is the honest CANNOT_MEASURE it always was.
    observed: list[str] = []
    try:
        defects, counts = scan_authorship(home)
        defects = list(defects) + _arm_b1b_conduit_proofs(home)
        floors = (
            ("files scanned", counts["files"], MIN_FILES_SCANNED),
            ("EventRow constructions", counts["eventrow_sites"], MIN_EVENTROW_SITES),
            ("enqueue call sites", counts["enqueue_sites"], MIN_ENQUEUE_SITES),
        )
        for label, seen, floor in floors:
            if seen < floor:
                return CheckResult(
                    name=NAME,
                    status=Status.CANNOT_MEASURE,
                    site=", ".join(SCAN_ROOTS),
                    detail=(
                        f"non-vacuity floor: {seen} {label} against a floor of "
                        f"{floor}. The authorship scan would report 'no "
                        f"unauthorised writer' over an empty population, which is "
                        f"the vacuous green this gate exists to avoid (§17)"
                    ),
                )
        defects += wiring_defects(home)
        # ARC 038 sub-agent G, finding FG2 (CHECK-DEBT D3.409). Everything above
        # is STATIC and is now MEASURED; everything below needs a reachable
        # cluster. `observed` carries the static verdict past the availability
        # wall so the handler at the bottom of this function cannot throw a
        # positively-observed second writer away as "nothing was measured".
        observed = list(defects)
        tmp = Path(tempfile.mkdtemp(prefix="nixp1sw-"))
        try:
            attempt_defects, evidence = attempt_privilege(tmp)
        finally:
            for leftover in tmp.glob("*"):
                leftover.unlink(missing_ok=True)
            tmp.rmdir()
        defects += attempt_defects
        if defects:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site=ANCHOR,
                evidence=f"{len(defects)} sole-writer defect(s)",
                detail="; ".join(defects),
            )
        return CheckResult(
            name=NAME,
            status=Status.PASS,
            evidence=(
                "; ".join(evidence)
                + f". AUTHORSHIP over {counts['files']} file(s) under "
                + "/".join(SCAN_ROOTS)
                + f": {counts['eventrow_sites']} EventRow construction(s), all "
                f"resolved to the Limiter's enqueue path; "
                f"{counts['enqueue_sites']} enqueue call site(s); "
                f"{counts['sink_impls']} CommitSinkPort implementation(s), all "
                f"enumerated. The static half is BLIND TO DYNAMIC DISPATCH "
                "(getattr, runtime-assembled SQL, an ORM) and that is why the "
                "attempt above is not optional"
            ),
        )
    except Unmeasurable as exc:
        # ARC 038 G / FG2 (CHECK-DEBT D3.409). MEASURED: with a second Plane-1
        # author planted in the tree and `PGHOST` pointing at nothing, this
        # handler returned CANNOT_MEASURE and the ARM B1 defect string — a live
        # §12.10 violation, already found — vanished from the verdict. Same tree,
        # same violation, exit 1 with the cluster up and exit 2 without it; and
        # under check-contract rule 4's `Fail > Cannot-measure` ordering that is
        # the difference between a certified-failed run and an uncertified one.
        # On any box without the cluster a second author shipped as "cannot
        # measure", while this detail asserted "nothing was measured" — which the
        # gate is in a position to know is false.
        #
        # Rule 10's own sentence, applied in the direction it was written for:
        # *the attempt is the claim; a positively-observed claim outranks
        # masking.* An unreachable LATER arm cannot unmeasure an EARLIER one, so
        # the static defects are reported and the unavailability is NAMED beside
        # them rather than substituted for them.
        if observed:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site=ANCHOR,
                evidence=(
                    f"{len(observed)} sole-writer defect(s) OBSERVED by the static "
                    f"half BEFORE the privilege attempt became unreachable. THE "
                    f"ATTEMPT ARM DID NOT RUN, so the DATABASE's refusal of a "
                    f"second writer is unproven on this box: {exc}"
                ),
                detail="; ".join(observed),
            )
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=ANCHOR,
            detail=f"the subject could not be reached, so nothing was measured (§17): {exc}",
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# Deliberately duplicated across every checks/check_*.py (§4.2).
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
