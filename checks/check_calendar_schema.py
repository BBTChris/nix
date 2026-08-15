#!/usr/bin/env python3
"""check_calendar_schema -- verify.py gate: the calendar DATA is UTC-canonical,
its provenance chains to the artifact it was derived from, its per-symbol
keying is the one §7:498 locks, and NO DECISION PATH READS A STORED
LOCAL-TIME FIELD.

---

## WHY THE RULE IS PHRASED THAT WAY ROUND, AND NOT THE OTHER WAY

The obvious rule is *"no stored local-time timestamp exists"*. **It is the
wrong rule, and shipping it would have reddened a correct tree on day one.**

Measured on the shipped artifact: `cme_calendar_sessions.csv` stores
`eth_open_ct` and `eth_close_ct` alongside its UTC columns. They are generated
through `ZoneInfo("America/Chicago")` and are DST-correct (-0600 in January,
-0500 in July, verified on 2025 rows), and **no runtime code reads them** --
`crucible.calendar.Session` does not carry them and the only references
anywhere are inside `calendar_gen.py`, which WRITES them. They are write-only
audit/eyeball columns.

A gate that banned their existence would therefore have exactly two futures:
someone deletes useful audit columns to make an instrument happy, or the
instrument gets suppressed. Neither protects anything.

The invariant that IS true of the shipped tree, IS mechanically checkable on
it, and DOES close the hazard is §12.3's own sentence:

  > **All internal time is UTC**; the calendar poller converts exchange-local
  > (incl. DST) exactly once at window generation.

So the rule enforced here is: **no decision path may READ a stored local-time
field.** Exchange-local is a generation-time input, never a decision-time one.

**A stored local-time column that nothing reads is still a loaded gun.** The
next arc that needs "exchange local" will find `eth_open_ct` sitting there and
read it -- at which point the conversion has happened twice, at two different
times, potentially against two different tzdb states, and §12.3's "exactly
once" is gone with no error anywhere. This gate exists precisely to keep those
columns unread, which is a stronger and more useful thing to guarantee than
their absence.

---

## PROPERTIES PROVEN (real, effective, on THIS host)

  ARM A  UTC-CANONICAL. Every column named `*_utc` in every artifact this
         gate owns parses as `%Y-%m-%dT%H:%M:%SZ` and is timezone-aware UTC,
         and no column in them carries a local UTC offset.
  ARM B  NO DECISION PATH READS A STORED LOCAL-TIME FIELD. The local field
         names are DISCOVERED from the artifacts' own headers and sample
         values (never listed here), and every tracked Python file under
         `scripts/` and `checks/` is AST-scanned for a read of one.
  ARM C  PROVENANCE CHAIN. The three extension artifacts hash to the value
         `nix_calendar_ext_provenance.json` stamps, AND that stamp's record
         of the UPSTREAM artifact's hash still matches the upstream bytes.
  ARM D  PER-SYMBOL KEYING. The symbol map and the roll schedule cover
         exactly the symbols `nixalloc.seam.BUCKET_OF` carries -- read
         statically out of that file, never typed here.
  ARM E  THE READ PORTS DECLARE NO MUTATING VERB. §6.4: "Allocator/Limiter
         read caches only", made structural on `calendar_seam.py`'s bytes.

## EXIT / STATUS CONTRACT (nix_check_contract.md §4.2)
  PASS (0)            every arm clean and every non-vacuity floor met
  FAIL (1)            a measured violation, sited and named
  CANNOT_MEASURE (2)  a subject is absent, unparseable, or below a
                      non-vacuity floor -- never PASS (§17)

---

## debug.md §7.12 -- THE STANDING QUESTION: how could this gate be GREEN
## while the property is FALSE?
##
## (This block is required of every gate at the point it is built. It is
## deliberately NOT labelled with the arc-brief section number that asked for
## it: check contract v2 rule 13 -- arc-brief labels are per-arc, collide
## across arcs, and are not identifiers. `check_spec_citations` enforces
## that mechanically and reddened on the first spelling of this heading.)

1. **The artifact could be missing or unparseable, and a `try/except` could
   turn that into silence.** *Closed:* `_subject_defects` returns
   CANNOT_MEASURE naming every absent path, and every CSV/JSON parse failure
   is CANNOT_MEASURE naming the file and the parser's own message (§17: a
   property proven while its subject is unavailable is not proven). The
   catch-all at the bottom of `run` is CANNOT_MEASURE, never PASS.

2. **The row population could be so small the UTC arm is vacuous.** A gate
   that scans an empty CSV finds no non-UTC value and reports PASS. *Closed:*
   `FLOORS` sets a per-artifact minimum row count and a minimum count of
   `*_utc` columns actually parsed. **The floors are FLOORS, not today's
   numbers** (doctrine C.4): today's break-window count is 35,478 and the
   floor is 20,000, because a legitimate regeneration moves the exact count
   (a new early-close, a re-run over a shifted span) while nothing legitimate
   halves the population. A floor set at today's value is a moving anchor
   that reddens on correct work; a floor set at zero measures nothing.

3. **The "no decision path reads local time" arm could scan a file list a
   person maintains, and silently miss a new reader.** This is the failure
   mode that would make ARM B decorative. *Closed three ways:*
   * the LOCAL FIELD NAMES are not listed here -- they are DISCOVERED by
     reading every CSV header under `calendar_data/` and sniffing the first
     data row for a `+HHMM`/`-HHMM` offset, so a local column added tomorrow
     is in scope the moment it is generated;
   * the FILE SET is not listed here either -- it is `git ls-files` over
     `scripts/` and `checks/`, so a new reader is in scope the moment it is
     tracked;
   * the EXEMPTIONS are three, enumerated, justified, and *checked*: each
     must still exist (a rename cannot silently widen the exemption into a
     hole), and the generator's exemption is additionally guarded by proving
     it is not reachable in the import closure of the runtime query module.

   **WHAT ARM B CANNOT SEE, stated rather than implied:** a read built at
   runtime (`row["eth_open" + "_ct"]`, `getattr`, an f-string key, a
   `csv.DictReader` row passed wholesale into something that indexes it
   dynamically); a non-Python reader (SQL, shell, a dashboard template); a
   reader outside this repository; and an UNTRACKED file -- deliberately, an
   untracked reader is not shipped, and `check_untracked_attribution` is the
   instrument for that. ARM B is a static-read detector, and its scan floor
   (`FLOORS["scanned_files"]`) is what stops it going quietly blind.

4. **The provenance arm could hash the file it read the expected hash from.**
   A self-referential hash is always satisfiable and proves nothing. *Closed
   structurally, not by convention:* `_arm_provenance` asserts the provenance
   file's own path is NOT among the paths hashed, and asserts that the
   stamp's `content_hash_covers` list names exactly the files that were
   hashed -- so a future generator that folded the stamp into its own digest
   reddens here rather than passing vacuously.

5. **The provenance arm could pass on a re-stamped edit.** Editing the
   upstream calendar and re-running its generator produces a fresh, internally
   consistent upstream stamp -- and `check_crucible_calendar`, which compares
   upstream bytes to the upstream stamp, would stay green. *Closed by the
   CHAIN:* this gate compares upstream BYTES against the copy of the upstream
   hash recorded in the EXTENSION's stamp, which the upstream generator does
   not write. That is the property `check_crucible_calendar` structurally
   cannot make, and it is why this arm is not a duplicate of it (C.9).

6. **ARM D could be typed as a literal.** A gate that hardcodes
   `{"ES","NQ","CL","GC","ZN"}` agrees with itself forever. *Closed:* the
   expected set is read out of `scripts/nixalloc/seam.py`'s `BUCKET_OF` dict
   literal by AST -- statically, never by importing it (check contract v2
   rule 6's own reasoning) -- and a `BUCKET_OF` that cannot be found or that
   yields fewer than the floor is CANNOT_MEASURE, not PASS.

---

## C.9 -- WHAT THIS GATE DELIBERATELY DOES NOT MEASURE

`check_crucible_calendar` already owns: the upstream artifact's hash against
its own stamp, the six locked product groups, and the runtime module's
forbidden-import scan. None of those is repeated here. This gate's subjects
are the ARC 033 extension artifacts, the calendar seam, and the one property
no existing gate holds -- the local-time read ban.

## NON-CORRECTABLE

The subjects are generated artifacts and declared source. "Correcting" a hash
mismatch here would mean regenerating the artifact from an unattended
boot-time gate so its own verdict became true by construction -- the same
refusal `check_crucible_calendar` and `check_monitor` both record. Drift is
FAIL-and-report; regeneration is a reviewed
`scripts/crucible/calendar_ext_gen.py` run.
"""

from __future__ import annotations

# C0302 (too-many-lines) disabled, matching check_artifact_gate_coverage,
# check_execution_ledger, check_limiter_gate and four others. The module is
# over pylint's 1000-line default and the overflow is DOCUMENTATION, not
# logic: the standing-question block, the C.9 boundary against
# check_crucible_calendar, and the argument for why the local-time rule is
# phrased as a READ ban rather than an existence ban are the things a later
# reader needs most, and moving them out of the gate is how a gate ends up
# measuring something nobody can explain. Splitting the file instead would
# put five arms over one subject in two modules -- the duplicate-instrument
# shape C.9 forbids, arrived at by a line count.
# pylint: disable=too-many-lines
import ast
import csv
import hashlib
import json
import re
import subprocess  # nosec B404 - git ls-files, fixed argv, no shell
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status
from nixverify.gitenv import scrubbed_env

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported; §4.4) ---
#: Nothing produces these artifacts at runtime and no other check gates them.
DEPENDS_ON: tuple[str, ...] = ()
#: ARM B derives its scan set from `git ls-files`, so the subprocess is
#: DECLARED. Check contract v2 rule 12: declared claims are checked against
#: OBSERVED ones, and a check declaring `RESOURCES = ()` while shelling out is
#: measurable, not trusted. No port, no service, no interpreter mutation, no
#: write of any kind.
RESOURCES: tuple[str, ...] = ("subprocess:git",)
TIME_BOUND = False
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subjects are a build-time-generated data artifact and declared "
    "source; a repair that regenerated the artifact here would make this "
    "gate's own verdict true by construction, which is the refusal "
    "check_crucible_calendar and check_monitor both record"
)
#: The `.py`/`.json` artifacts this gate covers for
#: `check_artifact_gate_coverage`. The `.csv` data files are not in that
#: gate's artifact set (it includes only `.py` and `.json`) but they are the
#: measured subject of ARMS A, C and D regardless.
#: `scripts/crucible/calendar.py` is NOT claimed here: it is
#: `check_crucible_calendar`'s subject and stays there (C.9), even though ARM
#: B scans it like every other tracked file.
SUBJECTS: tuple[str, ...] = (
    "scripts/nixrisk/calendar_seam.py",
    "scripts/crucible/calendar_ext_gen.py",
    "scripts/crucible/calendar_data/nix_calendar_ext_provenance.json",
)

NAME = "check_calendar_schema"

REL_DATA_DIR = "scripts/crucible/calendar_data"
REL_SEAM = "scripts/nixrisk/calendar_seam.py"
REL_ALLOC_SEAM = "scripts/nixalloc/seam.py"
REL_RUNTIME_MODULE = "scripts/crucible/calendar.py"

EXT_ARTIFACTS = (
    "nix_symbol_map.csv",
    "nix_break_windows.csv",
    "nix_roll_schedule.csv",
)
EXT_PROVENANCE = "nix_calendar_ext_provenance.json"
#: The extension artifacts that MUST carry at least one `*_utc` column. The
#: symbol map is a pure keying table and carries no instant at all, so
#: demanding one of it would be a false requirement rather than a stricter one.
TIMESTAMPED_EXT = ("nix_break_windows.csv", "nix_roll_schedule.csv")
UPSTREAM_ARTIFACTS = ("cme_calendar_sessions.csv", "cme_calendar_reconciliation.csv")
UPSTREAM_PROVENANCE = "cme_calendar_provenance.json"

#: Files ARM B does not scan, each with the reason it cannot be a decision
#: path. Enumerated, small, and CHECKED: `_arm_local_time_reads` fails if any
#: of these paths has stopped existing, so a rename cannot quietly widen the
#: exemption set into a hole.
SCAN_EXEMPTIONS: dict[str, str] = {
    "scripts/crucible/calendar_gen.py": (
        "the GENERATOR -- it WRITES the local-time columns; it runs only "
        "under .venv-dev, imports a calendar library, and is not reachable "
        "from the runtime query module (proved below)"
    ),
    "checks/check_calendar_schema.py": (
        "this gate -- it must name the discovered field names to search for "
        "them, and a detector that trips on itself detects nothing"
    ),
    "scripts/tests/test_check_calendar_schema.py": (
        "this gate's can-fail suite -- it must name the field names to plant "
        "the SUBJECT defect ARM B exists to catch"
    ),
}

#: A stored value carrying an explicit non-Zulu UTC offset, e.g.
#: `2008-01-01T19:00:00-0600`. This is how a local-time COLUMN is recognised;
#: the column NAMES are never listed in this file.
_LOCAL_OFFSET = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:?\d{2}$")
_ZULU = "%Y-%m-%dT%H:%M:%SZ"

#: Verb stems that mutate. ARM E's own vocabulary, deliberately NOT imported
#: from the seam: the seam declares WHICH ports are read-only, this gate
#: decides what "mutating" means, so a bug in one is not automatically a bug
#: in the other (the reasoning `check_crucible_calendar` gives for duplicating
#: its locked-groups tuple in its test).
MUTATING_STEMS = (
    "publish",
    "set",
    "put",
    "write",
    "update",
    "apply",
    "poll",
    "refresh",
    "clear",
    "invalidate",
    "delete",
    "remove",
    "add",
    "insert",
    "reset",
    "commit",
    "store",
)

#: NON-VACUITY FLOORS (doctrine C.4). Every one is a FLOOR chosen well below
#: the measured value, never the measured value: today's figures move on any
#: legitimate regeneration or file addition, and a gate anchored to them
#: reddens on correct work (`debug.md` §8 failure mode #4, the moving anchor).
#: A floor catches the failure that matters -- a population collapsing to
#: nothing, which is how a scan goes quietly vacuous.
FLOORS = {
    #: measured 35,478 break rows / 684 roll rows / 5 symbol rows
    "nix_break_windows.csv": 20_000,
    "nix_roll_schedule.csv": 200,
    "nix_symbol_map.csv": 2,
    "cme_calendar_sessions.csv": 20_000,
    #: `*_utc` cell values actually parsed across all artifacts. Measured
    #: ~178k; a floor of 50k still cannot be met by a truncated artifact.
    "utc_cells": 50_000,
    #: tracked `.py` files ARM B walked. Measured 225 under scripts/+checks/;
    #: a floor of 100 catches a `git ls-files` that returned a fragment.
    "scanned_files": 100,
    #: read Protocols and their verbs, for ARM E.
    "read_ports": 3,
    "read_verbs": 6,
    #: symbols found in `BUCKET_OF`. §7:498 locks five; the floor is 4 so a
    #: partial AST parse cannot pass, while a sixth symbol being provisioned
    #: is not this gate's business to veto.
    "bucket_symbols": 4,
}


class Finding(NamedTuple):
    """One divergence. `site` names WHERE, `why` names the reason (§18)."""

    site: str
    why: str


def _fail(findings: list[Finding]) -> CheckResult:
    return CheckResult(
        name=NAME,
        status=Status.FAIL_NEEDS_OPERATOR,
        site="; ".join(f.site for f in findings),
        evidence=f"{len(findings)} violation(s): " + "; ".join(f.why for f in findings),
        detail=" | ".join(f"{f.site}: {f.why}" for f in findings),
    )


def _cannot(detail: str) -> CheckResult:
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


# ---------------------------------------------------------------------------
# Subjects
# ---------------------------------------------------------------------------


def _subject_defects(home: Path) -> CheckResult | None:
    """CANNOT_MEASURE naming every absent subject (§17). None if all present."""
    data = home / REL_DATA_DIR
    required = [
        home / REL_SEAM,
        home / REL_ALLOC_SEAM,
        home / REL_RUNTIME_MODULE,
        data / EXT_PROVENANCE,
        data / UPSTREAM_PROVENANCE,
        *[data / n for n in EXT_ARTIFACTS],
        *[data / n for n in UPSTREAM_ARTIFACTS],
    ]
    missing = [str(p.relative_to(home)) for p in required if not p.is_file()]
    if not missing:
        return None
    return _cannot(
        f"calendar-schema subject(s) absent: {', '.join(missing)} -- the "
        "subject cannot be observed, so its property was not measured (§17); "
        "never a PASS"
    )


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]], str]:
    """(header, rows, error). `error` non-empty means it could not be parsed."""
    try:
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            header = list(reader.fieldnames or ())
            rows = list(reader)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return [], [], f"{path.name}: unreadable -- {type(exc).__name__}: {exc}"
    if not header:
        return [], [], f"{path.name}: no header row -- nothing to measure"
    return header, rows, ""


# ---------------------------------------------------------------------------
# ARM A -- UTC canonicity (§12.3)
# ---------------------------------------------------------------------------


#: How many ARM A findings are reported before the scan stops. A malformed
#: artifact produces one finding per cell; five is enough for an operator to
#: see the shape without a megabyte of identical rows.
_UTC_FINDING_CAP = 5


def _is_zulu_utc(value: str) -> bool:
    """True where `value` is a `...Z` instant `datetime` accepts as UTC."""
    try:
        datetime.strptime(value, _ZULU).replace(tzinfo=UTC)
    except ValueError:
        return False
    return True


def _utc_cell_findings(
    name: str, header: list[str], rows: list[dict[str, str]]
) -> tuple[list[Finding], int]:
    """Every `*_utc` cell in ONE artifact. Returns (findings, cells_parsed)."""
    findings: list[Finding] = []
    cells = 0
    utc_cols = [c for c in header if c.endswith("_utc")]
    for idx, row in enumerate(rows, start=2):
        for col in utc_cols:
            value = row.get(col) or ""
            cells += 1
            if _is_zulu_utc(value):
                continue
            findings.append(
                Finding(
                    f"{REL_DATA_DIR}/{name}:{idx}:{col}",
                    f"value {value!r} is not a Zulu UTC instant "
                    f"(§12.3: all internal time is UTC)",
                )
            )
            if len(findings) >= _UTC_FINDING_CAP:
                return findings, cells
    return findings, cells


def _local_column_findings(
    name: str, header: list[str], rows: list[dict[str, str]]
) -> list[Finding]:
    """An artifact THIS arc owns must carry no exchange-local column at all."""
    if not rows:
        return []
    return [
        Finding(
            f"{REL_DATA_DIR}/{name}:{col}",
            f"column carries a local UTC offset ({rows[0].get(col)!r}); the "
            "extension artifacts are UTC-canonical -- exchange-local is "
            "converted exactly once at window generation and never stored "
            "here (§12.3)",
        )
        for col in header
        if _LOCAL_OFFSET.match(rows[0].get(col) or "")
    ]


def _arm_utc(
    tables: dict[str, tuple[list[str], list[dict[str, str]]]],
) -> tuple[list[Finding], int]:
    """ARM A over every artifact. Returns (findings, cells_parsed)."""
    findings: list[Finding] = []
    cells = 0
    for name in (*EXT_ARTIFACTS, *UPSTREAM_ARTIFACTS):
        header, rows = tables[name]
        if not any(c.endswith("_utc") for c in header) and name in TIMESTAMPED_EXT:
            findings.append(
                Finding(
                    f"{REL_DATA_DIR}/{name}:header",
                    "carries no `*_utc` column, so ARM A would scan nothing "
                    f"in it -- header is {header}",
                )
            )
            continue
        cell_findings, counted = _utc_cell_findings(name, header, rows)
        findings += cell_findings
        cells += counted
        if name in EXT_ARTIFACTS:
            findings += _local_column_findings(name, header, rows)
    return findings, cells


# ---------------------------------------------------------------------------
# ARM B -- no decision path reads a stored local-time field
# ---------------------------------------------------------------------------


def _discover_local_fields(
    tables: dict[str, tuple[list[str], list[dict[str, str]]]],
) -> dict[str, str]:
    """Column name -> the artifact it lives in, for every column whose first
    data row carries an explicit UTC offset. DISCOVERED, never listed."""
    found: dict[str, str] = {}
    for name, (header, rows) in tables.items():
        if not rows:
            continue
        for col in header:
            if _LOCAL_OFFSET.match(rows[0].get(col) or ""):
                found[col] = name
    return found


def _tracked_python(home: Path) -> tuple[list[str], str]:
    """Tracked `.py` files under scripts/ and checks/. Returns (paths, error)."""
    try:
        proc = subprocess.run(  # nosec B603 B607 - fixed argv, no shell
            ["git", "ls-files", "--", "scripts", "checks"],
            cwd=home,
            capture_output=True,
            text=True,
            check=False,
            env=scrubbed_env(),
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [], f"git ls-files failed: {type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        return [], f"git ls-files exited {proc.returncode}: {proc.stderr.strip()}"
    return [p for p in proc.stdout.splitlines() if p.endswith(".py")], ""


def _reads_of(tree: ast.Module, fields: set[str]) -> list[tuple[int, str]]:
    """(line, field) for every static mention of a discovered local field."""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in fields:
                hits.append((node.lineno, node.value))
        elif isinstance(node, ast.Attribute) and node.attr in fields:
            hits.append((node.lineno, node.attr))
        elif isinstance(node, ast.Name) and node.id in fields:
            hits.append((node.lineno, node.id))
    return hits


def _parse(path: Path) -> ast.Module | None:
    """`ast.parse` a file, or None where it cannot be read or parsed."""
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except OSError, SyntaxError, UnicodeDecodeError:
        return None


def _dotted_imports(tree: ast.Module) -> set[str]:
    """Every dotted name this module imports, statically."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            names.add(base)
            names.update(f"{base}.{a.name}" if base else a.name for a in node.names)
    return {n for n in names if n}


def _import_closure(home: Path, start_rel: str) -> set[str]:
    """In-repo modules reachable from `start_rel` by static import, as paths."""
    scripts = home / "scripts"
    seen: set[str] = set()
    queue = [start_rel]
    while queue:
        rel = queue.pop()
        if rel in seen:
            continue
        seen.add(rel)
        tree = _parse(home / rel)
        if tree is None:
            continue
        for dotted in _dotted_imports(tree):
            candidate = scripts / (dotted.replace(".", "/") + ".py")
            if candidate.is_file():
                queue.append(str(candidate.relative_to(home)))
    return seen


def _scan_guard_findings(home: Path) -> list[Finding]:
    """The two guards on ARM B's own exemption set.

    Without these the arm is only as honest as its exemption list, and an
    exemption list is exactly the person-maintained thing the standing
    question warns about.
    """
    findings: list[Finding] = [
        Finding(
            f"{NAME}:SCAN_EXEMPTIONS:{rel}",
            f"exempted path no longer exists (reason on record: {why}) -- an "
            "exemption naming a path that moved silently widens the set of "
            "files nobody scans",
        )
        for rel, why in SCAN_EXEMPTIONS.items()
        if not (home / rel).is_file()
    ]
    # The generator's exemption is only safe while it is unreachable from the
    # runtime query module. Prove it rather than assume it.
    generator = "scripts/crucible/calendar_gen.py"
    if generator in _import_closure(home, REL_RUNTIME_MODULE):
        findings.append(
            Finding(
                f"{NAME}:import-closure:{REL_RUNTIME_MODULE}",
                f"{generator} is reachable by static import from the runtime "
                "query module, so exempting it from the local-time scan would "
                "exempt a decision path",
            )
        )
    return findings


def _arm_local_time_reads(
    home: Path, tables: dict[str, tuple[list[str], list[dict[str, str]]]]
) -> tuple[list[Finding], int, dict[str, str], str]:
    """Returns (findings, files_scanned, discovered_fields, cannot_measure)."""
    fields = _discover_local_fields(tables)
    if not fields:
        return (
            [],
            0,
            {},
            (
                "ARM B: no stored local-time column was discovered anywhere "
                f"under {REL_DATA_DIR} -- the subject of the read-ban is "
                "absent, so the ban was not measured (§17). If the audit "
                "columns were removed deliberately this arm has nothing left "
                "to guard; it is reported as unmeasured rather than as a PASS"
            ),
        )

    findings = _scan_guard_findings(home)
    paths, error = _tracked_python(home)
    if error:
        return [], 0, fields, f"ARM B: cannot enumerate the scan set -- {error} (§17)"

    field_names = set(fields)
    scanned = 0
    for rel in paths:
        if rel in SCAN_EXEMPTIONS:
            continue
        if not (home / rel).is_file():
            continue
        tree = _parse(home / rel)
        if tree is None:
            return (
                [],
                scanned,
                fields,
                (
                    f"ARM B: {rel} could not be read or parsed; the scan is "
                    "incomplete, so nothing was proven (§17)"
                ),
            )
        scanned += 1
        for line, field in _reads_of(tree, field_names):
            findings.append(
                Finding(
                    f"{rel}:{line}",
                    f"reads stored local-time field {field!r} (column of "
                    f"{fields[field]}). §12.3: all internal time is UTC and "
                    "exchange-local is converted exactly once at window "
                    "generation -- a decision path that reads a stored local "
                    "instant converts it a second time",
                )
            )
    return findings, scanned, fields, ""


# ---------------------------------------------------------------------------
# ARM C -- provenance chain
# ---------------------------------------------------------------------------


def _sha256(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(p.read_bytes())
    return h.hexdigest()


def _arm_provenance(home: Path) -> tuple[list[Finding], str, str]:
    """Returns (findings, ext_hash, cannot_measure)."""
    data = home / REL_DATA_DIR
    ext_stamp_path = data / EXT_PROVENANCE
    try:
        stamp = json.loads(ext_stamp_path.read_text(encoding="utf-8"))
        upstream_stamp = json.loads(
            (data / UPSTREAM_PROVENANCE).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        return (
            [],
            "",
            (
                f"provenance stamp unparseable -- {type(exc).__name__}: {exc}; "
                "the subject could not be read, so the chain was not measured (§17)"
            ),
        )

    findings: list[Finding] = []
    hashed_paths = [data / n for n in EXT_ARTIFACTS]

    # debug.md §7.12 hazard 4, closed STRUCTURALLY: the stamp must not be inside its own
    # digest, and the stamp must agree about what the digest covers.
    if ext_stamp_path in hashed_paths:
        findings.append(
            Finding(
                f"{REL_DATA_DIR}/{EXT_PROVENANCE}",
                "the provenance stamp is inside the digest it publishes -- a "
                "self-referential hash is always satisfiable and proves nothing",
            )
        )
    covers = list(stamp.get("content_hash_covers") or ())
    if covers != [p.name for p in hashed_paths]:
        findings.append(
            Finding(
                f"{REL_DATA_DIR}/{EXT_PROVENANCE}:content_hash_covers",
                f"stamp says the digest covers {covers}, this gate hashed "
                f"{[p.name for p in hashed_paths]} -- the two must name the "
                "same files or the digest is over an unknown set",
            )
        )

    ext_hash = _sha256(hashed_paths)
    if stamp.get("content_hash_sha256") != ext_hash:
        findings.append(
            Finding(
                f"{REL_DATA_DIR}/{EXT_PROVENANCE}:content_hash_sha256",
                f"HASH MISMATCH: stamp says "
                f"{stamp.get('content_hash_sha256')!r}, independently "
                f"recomputed {ext_hash!r} -- an extension artifact was edited "
                "without regenerating its stamp "
                "(scripts/crucible/calendar_ext_gen.py)",
            )
        )

    # THE CHAIN. This is the property `check_crucible_calendar` cannot make.
    upstream_bytes_hash = _sha256([data / n for n in UPSTREAM_ARTIFACTS])
    chained = stamp.get("upstream_content_hash_sha256")
    if chained != upstream_bytes_hash:
        findings.append(
            Finding(
                f"{REL_DATA_DIR}/{EXT_PROVENANCE}:upstream_content_hash_sha256",
                f"CHAIN BROKEN: the extension was derived from upstream bytes "
                f"hashing {chained!r}, the upstream artifact on disk now "
                f"hashes {upstream_bytes_hash!r}. The upstream calendar "
                "changed under the extension -- re-run "
                "scripts/crucible/calendar_ext_gen.py so the derived data and "
                "its source are the same generation",
            )
        )
    if stamp.get("upstream_stamped_hash_sha256") != upstream_stamp.get(
        "content_hash_sha256"
    ):
        findings.append(
            Finding(
                f"{REL_DATA_DIR}/{EXT_PROVENANCE}:upstream_stamped_hash_sha256",
                f"the extension recorded the upstream STAMP as "
                f"{stamp.get('upstream_stamped_hash_sha256')!r}; the upstream "
                f"stamp now reads "
                f"{upstream_stamp.get('content_hash_sha256')!r} -- the "
                "upstream artifact was regenerated and re-stamped after the "
                "extension was derived",
            )
        )
    return findings, ext_hash, ""


# ---------------------------------------------------------------------------
# ARM D -- per-symbol keying, derived from BUCKET_OF (never typed here)
# ---------------------------------------------------------------------------


def _assign_target(node: ast.AST) -> tuple[str | None, ast.expr | None]:
    """(module-level assigned name, value) for an assignment node, else (None, None)."""
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id, node.value
    if (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    ):
        return node.targets[0].id, node.value
    return None, None


def _assigned_value(tree: ast.Module, name: str) -> ast.expr | None:
    """The value assigned to module-level `name`, read STATICALLY.

    Check contract v2 rule 6's own reasoning, applied to a declaration rather
    than to a check's metadata: reading a value by AST cannot execute the
    module it is read from, so the gate cannot be influenced by its subject.
    """
    for node in ast.walk(tree):
        target, value = _assign_target(node)
        if target == name:
            return value
    return None


def _string_keys(node: ast.expr | None) -> set[str]:
    """The string keys of a dict literal, or an empty set for anything else."""
    if not isinstance(node, ast.Dict):
        return set()
    return {
        k.value
        for k in node.keys
        if isinstance(k, ast.Constant) and isinstance(k.value, str)
    }


def _string_elements(node: ast.expr | None) -> tuple[str, ...]:
    """The string elements of a tuple literal, or `()` for anything else."""
    if not isinstance(node, ast.Tuple):
        return ()
    return tuple(
        e.value
        for e in node.elts
        if isinstance(e, ast.Constant) and isinstance(e.value, str)
    )


def _bucket_of_symbols(home: Path) -> tuple[set[str], str]:
    """`BUCKET_OF`'s keys, read STATICALLY out of the Allocator seam."""
    tree = _parse(home / REL_ALLOC_SEAM)
    if tree is None:
        return set(), (
            f"{REL_ALLOC_SEAM} could not be read or parsed -- the expected "
            "symbol set has no source"
        )
    keys = _string_keys(_assigned_value(tree, "BUCKET_OF"))
    if not keys:
        return set(), (
            f"{REL_ALLOC_SEAM}: no `BUCKET_OF` dict literal found -- the "
            "expected symbol set has no source, so nothing was compared against"
        )
    return keys, ""


def _arm_symbols(
    home: Path, tables: dict[str, tuple[list[str], list[dict[str, str]]]]
) -> tuple[list[Finding], set[str], str]:
    expected, error = _bucket_of_symbols(home)
    if error:
        return [], set(), f"ARM D: {error} (§17)"
    if len(expected) < FLOORS["bucket_symbols"]:
        return (
            [],
            expected,
            (
                f"ARM D: BUCKET_OF yielded {len(expected)} symbol(s), below the "
                f"non-vacuity floor of {FLOORS['bucket_symbols']} -- a partial "
                "parse cannot certify a symbol set (§17)"
            ),
        )

    findings: list[Finding] = []
    _, map_rows = tables["nix_symbol_map.csv"]
    mapped = {r["symbol"] for r in map_rows}
    if mapped != expected:
        findings.append(
            Finding(
                f"{REL_DATA_DIR}/nix_symbol_map.csv:symbol",
                f"symbol map covers {sorted(mapped)}, "
                f"{REL_ALLOC_SEAM}:BUCKET_OF locks {sorted(expected)} "
                f"(missing {sorted(expected - mapped)}, "
                f"extra {sorted(mapped - expected)})",
            )
        )
    _, roll_rows = tables["nix_roll_schedule.csv"]
    rolled = {r["symbol"] for r in roll_rows}
    if rolled != expected:
        findings.append(
            Finding(
                f"{REL_DATA_DIR}/nix_roll_schedule.csv:symbol",
                f"roll schedule covers {sorted(rolled)}, "
                f"{REL_ALLOC_SEAM}:BUCKET_OF locks {sorted(expected)} "
                f"(missing {sorted(expected - rolled)}, "
                f"extra {sorted(rolled - expected)}) -- §7.5 gives every live "
                "symbol a front-month identity and a roll instant",
            )
        )
    _, session_rows = tables["cme_calendar_sessions.csv"]
    known_groups = {r["product_group"] for r in session_rows}
    for row in map_rows:
        if row["product_group"] not in known_groups:
            findings.append(
                Finding(
                    f"{REL_DATA_DIR}/nix_symbol_map.csv:{row['symbol']}",
                    f"maps to product group {row['product_group']!r}, which "
                    f"the session artifact does not carry (has "
                    f"{sorted(known_groups)}) -- the symbol has no session "
                    "calendar, so §6.1's per-symbol window cannot be built",
                )
            )
    return findings, expected, ""


# ---------------------------------------------------------------------------
# ARM E -- the read ports declare no mutating verb (§6.4)
# ---------------------------------------------------------------------------


def _port_verb_findings(port: str, node: ast.ClassDef) -> tuple[list[Finding], int]:
    """Every verb declared on ONE read port. Returns (findings, verbs)."""
    findings: list[Finding] = []
    verbs = 0
    for item in node.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        verbs += 1
        if isinstance(item, ast.AsyncFunctionDef):
            findings.append(
                Finding(
                    f"{REL_SEAM}:{port}.{item.name}",
                    "a READ port verb is declared `async def`; §6.4 makes "
                    "these caches read-only and the module declares every "
                    "read synchronous, because a suspension point inside a "
                    "pre-size gate has a third outcome the gate cannot act on",
                )
            )
        stem = item.name.lstrip("_").split("_")[0]
        if stem in MUTATING_STEMS:
            findings.append(
                Finding(
                    f"{REL_SEAM}:{port}.{item.name}",
                    f"a READ port declares the mutating verb {item.name!r} "
                    f"(stem {stem!r}). §6.4: Allocator/Limiter READ CACHES "
                    "ONLY -- a mutating verb on a read port is authority "
                    "the spec withheld, granted at the boundary",
                )
            )
    return findings, verbs


def _arm_read_only(home: Path) -> tuple[list[Finding], int, int, str]:
    """Returns (findings, ports_checked, verbs_checked, cannot_measure)."""
    tree = _parse(home / REL_SEAM)
    if tree is None:
        return [], 0, 0, f"ARM E: {REL_SEAM} could not be read or parsed (§17)"

    declared = _string_elements(_assigned_value(tree, "READ_ONLY_PORTS"))
    if len(declared) < FLOORS["read_ports"]:
        return (
            [],
            len(declared),
            0,
            (
                f"ARM E: {REL_SEAM} declares {len(declared)} read-only port(s), "
                f"below the non-vacuity floor of {FLOORS['read_ports']} -- a "
                "vocabulary that names nothing certifies nothing (§17)"
            ),
        )

    classes = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    findings: list[Finding] = []
    verbs = 0
    for port in declared:
        node = classes.get(port)
        if node is None:
            findings.append(
                Finding(
                    f"{REL_SEAM}:READ_ONLY_PORTS",
                    f"declares {port!r} read-only, but no such class exists in "
                    "the module -- a declaration over an absent subject",
                )
            )
            continue
        port_findings, counted = _port_verb_findings(port, node)
        findings += port_findings
        verbs += counted
    if verbs < FLOORS["read_verbs"]:
        return (
            findings,
            len(declared),
            verbs,
            (
                f"ARM E: only {verbs} verb(s) found across {len(declared)} read "
                f"port(s), below the non-vacuity floor of {FLOORS['read_verbs']} "
                "-- ports with no verbs cannot violate a verb ban (§17)"
            ),
        )
    return findings, len(declared), verbs, ""


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


Tables = dict[str, tuple[list[str], list[dict[str, str]]]]


def _load_tables(home: Path) -> tuple[Tables, str]:
    """Every artifact parsed and floored. `error` non-empty ⇒ CANNOT_MEASURE."""
    data = home / REL_DATA_DIR
    tables: Tables = {}
    for name in (*EXT_ARTIFACTS, *UPSTREAM_ARTIFACTS):
        header, rows, error = _read_csv(data / name)
        if error:
            return {}, (
                f"{REL_DATA_DIR}/{error} -- the artifact could not be parsed, "
                "so nothing in it was measured (§17)"
            )
        floor = FLOORS.get(name)
        if floor is not None and len(rows) < floor:
            return {}, (
                f"{REL_DATA_DIR}/{name} holds {len(rows)} row(s), below the "
                f"non-vacuity floor of {floor}. A scan over a collapsed "
                "population finds no violation and would report PASS; that is "
                "unmeasured, not proven (doctrine C.4, §17)"
            )
        tables[name] = (header, rows)
    return tables, ""


def _all_arms(home: Path, tables: Tables) -> tuple[list[Finding], dict, str]:
    """Run all five arms. Returns (findings, stats, cannot_measure)."""
    findings: list[Finding] = []
    stats: dict = {"artifacts": len(tables)}

    utc_findings, stats["cells"] = _arm_utc(tables)
    findings += utc_findings
    if stats["cells"] < FLOORS["utc_cells"]:
        return (
            findings,
            stats,
            (
                f"ARM A parsed {stats['cells']} `*_utc` cell(s), below the "
                f"non-vacuity floor of {FLOORS['utc_cells']} -- too few to certify "
                "that the artifact is UTC-canonical (doctrine C.4, §17)"
            ),
        )

    local, stats["scanned"], stats["fields"], cannot = _arm_local_time_reads(
        home, tables
    )
    if cannot:
        return findings, stats, cannot
    findings += local
    if stats["scanned"] < FLOORS["scanned_files"]:
        return (
            findings,
            stats,
            (
                f"ARM B scanned {stats['scanned']} tracked Python file(s), below "
                f"the non-vacuity floor of {FLOORS['scanned_files']} -- a scan "
                "over a fragment of the tree cannot certify that no decision path "
                "reads a local-time field (doctrine C.4, §17)"
            ),
        )

    prov, stats["ext_hash"], cannot = _arm_provenance(home)
    if cannot:
        return findings, stats, cannot
    findings += prov

    symbols, stats["expected"], cannot = _arm_symbols(home, tables)
    if cannot:
        return findings, stats, cannot
    findings += symbols

    ports, stats["ports"], stats["verbs"], cannot = _arm_read_only(home)
    findings += ports
    return findings, stats, cannot


def _pass(stats: dict) -> CheckResult:
    return CheckResult(
        name=NAME,
        status=Status.PASS,
        evidence=(
            f"ARM A {stats['cells']} `*_utc` cells all Zulu UTC across "
            f"{stats['artifacts']} artifacts; ARM B {stats['scanned']} tracked "
            f".py files scanned, zero reads of the {len(stats['fields'])} "
            f"discovered local-time field(s) {sorted(stats['fields'])} "
            f"({len(SCAN_EXEMPTIONS)} exemptions, all present, generator "
            f"unreachable from {REL_RUNTIME_MODULE}); ARM C extension hash "
            f"{stats['ext_hash'][:12]}... matches its stamp and the upstream "
            "chain holds; ARM D symbol map and roll schedule both cover "
            f"exactly BUCKET_OF's {len(stats['expected'])} symbols; ARM E "
            f"{stats['verbs']} verbs across {stats['ports']} read ports, none "
            "mutating, none async. ARM B is a STATIC read detector: it cannot "
            "see a dynamically built key, a non-Python reader, or an "
            "untracked file"
        ),
    )


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Five arms over the calendar data, its provenance chain, and the seam."""
    try:
        home = Path(ctx.nix_home)
        absent = _subject_defects(home)
        if absent is not None:
            return absent
        tables, error = _load_tables(home)
        if error:
            return _cannot(error)
        findings, stats, cannot = _all_arms(home, tables)
        # FAIL outranks CANNOT_MEASURE, per the check contract's aggregate
        # ordering (`Fail > Cannot-measure > Guarded > Pass`) applied WITHIN a
        # check. A violation an earlier arm MEASURED stays measured when a
        # later arm loses its subject; reporting CANNOT_MEASURE here would
        # let an unparseable seam hide a non-UTC instant that was seen.
        if findings:
            return _fail(findings)
        return _cannot(cannot) if cannot else _pass(stats)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1.
        return _cannot(f"gate raised {type(exc).__name__}: {exc}")


# Deliberately duplicated across every checks/check_*.py: the check contract
# (§4.2) requires each module be independently runnable.
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
