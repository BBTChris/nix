#!/usr/bin/env python3
# C0302: this module is over pylint's line ceiling and the excess is PROSE —
# the §7.12 standing question answered condition by condition, and a rationale
# beside every arm. Doctrine B.7 puts the argument next to the instrument it
# argues for; splitting the gate to satisfy a line counter would move half the
# reasoning away from the code it explains, which is the trade the check
# contract explicitly refuses.
# pylint: disable=too-many-lines
"""Gate: every tracked module and config artifact is NAMED by some check.

ARC 024 §2.7. AMENDMENT 3 broadens the coverage trigger from *every environment
change owes a check* to *any module or setting written to disk or changed owes a
check*. A doctrine that broad is unenforceable as prose and would rot into a
slogan, so it gets an instrument.

## READ THIS BEFORE TRUSTING A GREEN FROM THIS GATE

**This gate ships UNBOUND per D3.10 and says so in its own verdict.**

It proves that **some check NAMES the artifact**. That is strictly weaker than
**some check MEASURES the artifact**, and the gap between those two sentences is
D3.16 exactly — a gate that reported PASS across two arcs over a method it never
executed. A check can add a path to its `SUBJECTS` tuple and never open the file.
This gate cannot see that class of defect and must not be read as if it could.

Binding it — proving the named subject is actually driven — is a named future
arc. Until then its green means *declared*, never *covered*.

## debug.md §7.12 — the standing question

**What would have to be true for this gate to PASS while measuring nothing?**

1. **The artifact set could be empty.** A `git ls-files` that returns nothing —
   wrong cwd, git absent, a tree with no tracked files — yields "zero artifacts,
   zero uncovered, PASS", which is the purest possible vacuous green. *Closed:*
   an empty artifact set is CANNOT_MEASURE, and a set smaller than
   `MIN_CREDIBLE_ARTIFACTS` is CANNOT_MEASURE, because this repo cannot honestly
   have three source files.
2. **The declared-subject set could be empty and the artifact set could also be
   empty**, for the same reason. Same closure.
3. **The baseline could absorb everything forever.** A ratchet whose baseline
   only ever grows is a suppression list wearing a ratchet's name. *Closed by the
   STALE-BASELINE rule:* an entry in the baseline that is now covered is a FAIL,
   not a shrug. The baseline can only tighten.
4. **ARC 025 — the baseline could GROW, silently, and rule 3 would not see it.**
   Rule 3 only reddens entries that became covered; nothing stopped a hand adding
   a fresh path to `uncovered` and turning a regression into an accepted one in
   the same motion. *Closed by `_high_water_mark`:* the prior mark is derived from
   the baseline's own **git history** — the tightest revision ever committed —
   and any addition relative to it must name the single arc that admitted it, in
   the file's `admitted` map, validated by the same grammar `guard_owner` uses.
   The mark is deliberately not stored anywhere the addition's author can edit.
5. **ARC 025 — the ratchet itself could go blind.** If git is absent, or the
   baseline has no commit history, or one historical revision will not parse,
   there is no mark. *Closed:* every one of those is `CANNOT_MEASURE` naming the
   reason, and a revision that cannot be read is an ERROR rather than a skip —
   the skipped revision could be exactly the tightest one.
6. **ARC 027 — the GUARD could be walked forward forever, and rules 1-5 would
   all stay green.** Every rule above judges the accepted SET; the owner rules
   judge the owner VALUE standing today. A marker re-pointed at the next arc at
   every arc boundary satisfies all of them permanently, and the debt is never
   paid. *Closed by `_row_lineage` + `contract.reowning_defect`:* the sequence
   of committed owner values is derived from the SAME git walk the ratchet uses,
   and more than `GUARD_REOWN_CEILING` re-ownings escalates GUARDED to FAIL.
   Its own sub-vacuities: a lineage read from the working tree is length 1 by
   construction (closed — committed blobs only); an unreadable revision could
   hide an owner change (closed — ERROR, never skip); a TRUNCATED history drops
   the OLDEST revisions and so under-counts (closed — a lower bound may FAIL but
   may never PASS, so truncation under the ceiling is CANNOT_MEASURE).
   **NOT closed, and named rather than implied:** `git log` here does not follow
   RENAMES, so moving `checks/gate_coverage_baseline.json` restarts the lineage
   at zero. `--follow` is not the repair — it makes `git show <sha>:<path>` fail
   for pre-rename revisions, which this gate correctly treats as an ERROR, so it
   would trade a silent reset for a permanent CANNOT_MEASURE. Recorded as
   CHECK-DEBT D2.35 rather than half-fixed.
7. **ARC 028 — THE DECOMPOSITION COULD LAUNDER THE CEILING.** Splitting one
   sixteen-artifact guard into sixteen rows hands each row a lineage, and a
   lineage read only from the NEW schema starts at length 1 — nought re-ownings
   — so a file format change would reset a ceiling ARC 027 spent an arc
   building. *Closed by `_parse_v1`:* every historical revision is projected
   onto per-path rows, so each of the sixteen inherits the aggregate's owner
   sequence and is AT the ceiling on the day of the split, not below it.
8. **ARC 028 — an owner could be assigned to the ARC IN FLIGHT**, which every
   read-time rule accepts (that arc has not closed yet) and which is guaranteed
   dead at that arc's own close-out. That is CHECK-DEBT D3.40, measured on this
   very file. *Closed by `_assignment_defects` + `contract.
   guard_owner_assignment_defect` (STANDING RULE §0g):* a row whose owner
   differs from the value committed at `HEAD` is an assignment happening NOW and
   is judged against the arc in flight, not merely against the completed set.
9. **ARC 028 — `measured_by` could be a claim nobody checks**, which would make
   the per-row honesty decorative. *Closed by `_coverage_defects`:* every row's
   claim is compared against every module under `scripts/tests/`, in BOTH
   directions, and what that comparison can and cannot prove is stated in
   `_named_by_tests` and printed in the verdict.

## Why GUARDED rather than FAIL today

The uncovered set is large and known: most checks predate the declaration
mechanism and name nothing. That is a measured deferral with an owner — now one
owner PER ARTIFACT — which is precisely AMENDMENT 1's GUARDED (exit 3), not a
failure. A *new* uncovered artifact is a regression and is a FAIL. So the
instrument is a ratchet: existing debt is guarded and visible; new debt is red.

**AND TODAY IT IS NOT GUARDED, IT IS CANNOT_MEASURE, PER ROW.** All sixteen rows
name `ARC 027`, which has completed. The decomposition deliberately did NOT
re-point them at a live arc: that is the third re-owning D2.31's ceiling forbids,
and it is forbidden per artifact now rather than in aggregate. Nothing was forced
green and nothing was discharged by being named (D3.19). CHECK-DEBT D3.40 stays
open and is now stated per artifact.
"""

from __future__ import annotations

import dataclasses
import json
import re
import subprocess  # nosec B404 - git ls-files/log/show, fixed argv, no shell
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import (
    GUARD_REOWN_CEILING,
    CheckResult,
    Context,
    Mode,
    Status,
    completed_arcs,
    guard_owner_assignment_defect,
    guard_owner_defect,
    in_flight_arc,
    reowning_defect,
)
from nixverify.declarations import read_all
from nixverify.gitenv import SELECTORS, scrubbed_env

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

DEPENDS_ON: tuple[str, ...] = ()
#: `()` until ARC 025, when `check_observed_resource_claims` OBSERVED this gate
#: spawning `/usr/bin/git` and reported the empty declaration as false — D2.27's
#: residual caught on the gate that opened it.
RESOURCES: tuple[str, ...] = ("subprocess:git",)
TIME_BOUND = False
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "coverage is closed by writing checks, not by an instrument editing "
    "declarations to satisfy itself — a gate that could add its own SUBJECTS "
    "entries would be manufacturing its own green"
)
SUBJECTS: tuple[str, ...] = (
    "checks/gate_coverage_baseline.json",
    "scripts/nixverify/declarations.py",
)

NAME = "check_artifact_gate_coverage"
GIT = "/usr/bin/git"
BASELINE = "checks/gate_coverage_baseline.json"

#: Below this, the enumeration is not credible and the gate refuses to report.
#: Anchored to a floor, not to the current count — a threshold equal to today's
#: number would be a moving anchor that reddens the moment a file is added.
MIN_CREDIBLE_ARTIFACTS = 20

#: What counts as a "module or setting written to disk". Test modules are
#: excluded: a test is not a settable artifact, it IS the measurement.
_INCLUDE_SUFFIXES = (".py", ".json")
_EXCLUDE_PREFIXES = ("scripts/tests/", "checks/check_", "downloads/", "docs/")

#: How far back the ratchet reads. Bounded so the gate's own runtime cannot be
#: set by the length of the repository's history.
_HISTORY_LIMIT = 200


def _tracked_artifacts(home: Path) -> tuple[list[str], str]:
    """Enumerate tracked module/config artifacts. Returns (paths, error)."""
    listing, error = _git(home, "ls-files")
    if error:
        return [], error
    found = [
        line
        for line in listing.splitlines()
        if line.endswith(_INCLUDE_SUFFIXES) and not line.startswith(_EXCLUDE_PREFIXES)
    ]
    return sorted(found), ""


def _declared_subjects(home: Path) -> set[str]:
    """Union of every SUBJECTS entry across the check population."""
    return {
        subject
        for decl in read_all(home / "checks").values()
        for subject in decl.subjects
    }


#: The values `measured_by` may take. See `_coverage_defects` for what each one
#: CLAIMS and — the part that matters — what the gate can actually check.
MEASURED_BY_TESTS = "tests"
MEASURED_BY_NOTHING = "none"
MEASURED_BY_VALUES = (MEASURED_BY_TESTS, MEASURED_BY_NOTHING)


@dataclasses.dataclass(frozen=True)
class Row:
    """ONE accepted-uncovered artifact. ARC 028 (C2), ARCHITECT RULING D3.40.

    Until ARC 028 this file held a flat `uncovered` LIST under a single
    top-level `owner`: sixteen unrelated debts, one promise, one ceiling. The
    ceiling was blunt by construction — it could only ever say "somebody has
    deferred this pile three times", never which artifact, and the two entries
    nothing measures at all hid inside the aggregate exactly as well as the
    thirteen the test suite drives hard.
    """

    #: The single arc that will discharge THIS artifact. Its lineage, and so its
    #: re-owning ceiling, is derived per path from the same git walk.
    owner: str = ""
    #: The single arc that admitted this path to the accepted set. A RECEIPT
    #: (backward-looking), never a promise — see `guard_owner_defect`.
    admitted: str = ""
    #: What DOES measure it, if anything: `tests` or `none`. Checked, not taken.
    measured_by: str = ""
    #: Why it is uncovered, in this file, per artifact. Required and non-empty.
    reason: str = ""


@dataclasses.dataclass(frozen=True)
class Baseline:
    """The ratchet file, parsed. `error` non-empty means it could not be read."""

    rows: dict[str, Row] = dataclasses.field(default_factory=dict)
    #: 1 = the flat pre-ARC-028 shape, 2 = per-artifact. Recorded because the
    #: ratchet reads HISTORICAL revisions and most of them are schema 1.
    schema: int = 0
    error: str = ""

    @property
    def uncovered(self) -> frozenset[str]:
        """The accepted set — the quantity the ratchet has always judged."""
        return frozenset(self.rows)

    def owner_of(self, path: str) -> str:
        """This revision's owner for one artifact, or `''` if it held none."""
        return self.rows[path].owner if path in self.rows else ""


def _parse_v1(payload: dict, where: str) -> Baseline:
    """The FLAT pre-ARC-028 shape, projected onto per-artifact rows.

    **THIS IS WHAT STOPS THE DECOMPOSITION LAUNDERING THE CEILING**, and it is
    the whole reason the historical reader exists rather than the old shape
    being deleted. Every committed revision before ARC 028 carries ONE owner
    covering ALL of its accepted paths, so projecting that owner onto each path
    reconstructs a per-path lineage that INCLUDES the aggregate's history. The
    sixteen artifacts inherit
    `'the bulk check retrofit arc (ARC 025+)…' -> 'ARC 025' -> 'ARC 027'`
    rather than starting at zero.

    A decomposition that read only the new shape would hand every row a fresh
    lineage of length 1 — nought re-ownings — and the ceiling ARC 027 spent an
    arc building would be reset by a file format change. That is the §0a defect
    for this step, and this function is the answer to it.
    """
    del where
    admitted = payload.get("admitted", {})
    admitted = admitted if isinstance(admitted, dict) else {}
    owner = str(payload.get("owner", ""))
    return Baseline(
        rows={
            str(item): Row(owner=owner, admitted=str(admitted.get(str(item), "")))
            for item in payload.get("uncovered", [])
        },
        schema=1,
    )


def _parse_v2(payload: dict, where: str) -> Baseline:
    """The per-artifact shape. One row per artifact, each with its own owner."""
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        return Baseline(error=f"{where}: `artifacts` is not a JSON object")
    rows: dict[str, Row] = {}
    for path, entry in artifacts.items():
        if not isinstance(entry, dict):
            return Baseline(error=f"{where}:{path} is not a JSON object")
        rows[str(path)] = Row(
            owner=str(entry.get("owner", "")),
            admitted=str(entry.get("admitted", "")),
            measured_by=str(entry.get("measured_by", "")),
            reason=str(entry.get("reason", "")),
        )
    return Baseline(rows=rows, schema=2)


def _parse_baseline(text: str, where: str) -> Baseline:
    """Parse baseline JSON. Shared by the working tree and by `git show`.

    Both schemas are read, and which one was read is RECORDED rather than
    smoothed over: the ratchet's whole job is to compare today's file against
    revisions committed under the older shape.
    """
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return Baseline(error=f"{where} unreadable: {exc!r}")
    if not isinstance(payload, dict):
        return Baseline(error=f"{where} is not a JSON object")
    if "artifacts" in payload:
        return _parse_v2(payload, where)
    return _parse_v1(payload, where)


def _load_baseline(home: Path) -> Baseline:
    """Read the baseline as it stands in the WORKING TREE."""
    path = home / BASELINE
    if not path.is_file():
        return Baseline(error=f"{BASELINE} absent")
    try:
        return _parse_baseline(path.read_text(encoding="utf-8"), BASELINE)
    except OSError as exc:
        return Baseline(error=f"{BASELINE} unreadable: {exc!r}")


#: Git honours every one of these AHEAD of `-C`. A caller invoked from inside
#: another git operation — a pre-commit hook, a rebase, a filter-branch — has them
#: exported, and this gate would then enumerate a DIFFERENT repository and a
#: DIFFERENT index from the directory it was handed, silently.
#:
#: **MEASURED IN THIS ARC, NOT ANTICIPATED.** ARC 025 C's own test suite ran
#: `git add` inside a throwaway repo under `tmp_path` while pre-commit had
#: `GIT_INDEX_FILE` exported, and git wrote the throwaway tree into THIS
#: worktree's real index — every tracked file staged as deleted. The tests were
#: the visible casualty; the gate has the same exposure and is the reason this
#: constant lives here rather than in the test harness. It is the project's
#: recurring defect class (an ambient tracking state silently setting a gate's
#: scope) arriving through the environment instead of through a config file.
#:
#: **ARC 026 (B4): this is now an ALIAS of `nixverify.gitenv.SELECTORS`.** The
#: names above are the ones that were measured doing damage; the rule applied is
#: the broader `GIT_*` prefix. Kept as a name because the committed suite asserts
#: on it, and two spellings of one list is the defect this arc is purging.
_GIT_ENV_BLOCKED = SELECTORS


def git_env() -> dict[str, str]:
    """`os.environ` with every repository-selecting `GIT_*` variable removed.

    Exported so the test harness runs git the same way the gate does — a harness
    that could redirect itself while the gate could not would be measuring a
    different program from the one that ships.

    **ARC 026 (B4): the rule moved to `nixverify.gitenv` and got STRICTER.** This
    used to strip a nine-name list; it now strips every `GIT_`-prefixed variable,
    because a list does not inherit the repository-selecting variables future git
    releases add and a prefix rule does. `_GIT_ENV_BLOCKED` is kept as an alias of
    the shared `SELECTORS` tuple so the committed assertions that name it keep
    naming one thing.
    """
    return scrubbed_env()


def _git(home: Path, *args: str) -> tuple[str, str]:
    """Run one git command against `home` and NOTHING else. Returns (stdout, error)."""
    if not Path(GIT).exists():
        return "", f"{GIT} not present"
    try:
        proc = subprocess.run(  # nosec B603 - fixed absolute path, no shell
            [GIT, "-C", str(home), *args],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=git_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return "", f"git {args[0]} failed: {exc!r}"
    if proc.returncode != 0:
        return "", f"git {' '.join(args)} exit {proc.returncode}"
    return proc.stdout, ""


@dataclasses.dataclass(frozen=True)
class History:
    """Every COMMITTED revision of the baseline, oldest first.

    ARC 027 (B2). One git walk, two derived facts — the tightest accepted set
    (`_high_water_mark`, ARC 025) and the owner lineage (`_row_lineage`, D2.31's
    ceiling). Doctrine C.9: the property *"a fact about this file that the hand
    editing it cannot reach"* was already owned by the ratchet's walk, so the
    ceiling extends that walk instead of opening a second one. Two walks would be
    two chances to disagree about which revisions exist.

    `truncated` is `True` when the log came back at `_HISTORY_LIMIT` and the
    OLDEST revisions may therefore be missing. It is not a nicety: the limit
    truncates from the old end, which is exactly where a lineage's early owners
    live, so every consumer must say what a lower bound does to its verdict.
    """

    revisions: tuple[tuple[str, Baseline], ...] = ()
    truncated: bool = False
    error: str = ""


def _committed_history(home: Path) -> History:
    """Read every committed revision of the baseline, oldest first.

    **A revision that cannot be read is an ERROR, never a skip.** A silently
    skipped revision might be exactly the tightest one, or exactly the one that
    changed the owner, and a mark or a lineage that quietly improves is the
    vacuous pass this gate exists to refuse.
    """
    listing, error = _git(
        home, "log", f"-{_HISTORY_LIMIT}", "--format=%H", "--", BASELINE
    )
    if error:
        return History(error=error)
    shas = [line.strip() for line in listing.splitlines() if line.strip()]
    if not shas:
        return History(
            error=(
                f"{BASELINE} has no commit history — the ratchet has nothing to "
                "ratchet against, so the accepted set cannot be shown not to have "
                "grown"
            )
        )
    revisions: list[tuple[str, Baseline]] = []
    for sha in reversed(shas):  # oldest first, so ties keep the earliest mark
        blob, blob_error = _git(home, "show", f"{sha}:{BASELINE}")
        if blob_error:
            # Suffixes preserved verbatim from ARC 025 (CLAUDE.md directive 6:
            # never rewrite banked evidence — the committed suite asserts them).
            return History(error=f"{blob_error} — cannot establish the high-water mark")
        revision = _parse_baseline(blob, f"{BASELINE}@{sha[:12]}")
        if revision.error:
            return History(error=f"{revision.error} — cannot establish the mark")
        revisions.append((sha, revision))
    return History(revisions=tuple(revisions), truncated=len(shas) >= _HISTORY_LIMIT)


def _row_lineage(history: History, path: str) -> tuple[str, ...]:
    """ONE artifact's committed `owner` values, oldest first, dupes collapsed.

    ARC 027 (B2) built this over the file's single top-level owner; ARC 028 (C2)
    reads it PER PATH, which is the whole of the decomposition — `len(lineage)
    - 1` is now the number of times THIS artifact's deferral was handed on, and
    `contract.reowning_defect` bounds that per artifact instead of bounding one
    number for sixteen unrelated debts.

    Revisions in which the path was NOT in the accepted set are skipped: a guard
    that did not exist yet cannot have been re-owned. Revisions committed under
    the flat schema contribute the file-wide owner, because under that schema it
    genuinely was this artifact's owner (see `_parse_v1`).

    Consecutive duplicates are collapsed rather than de-duplicated globally: an
    owner re-appearing after a different one is a second deferral onto that arc,
    not a repeat of the first, and a global `set` would let a guard be cycled
    between two arc numbers at a constant apparent cost forever.

    **Derived from committed blobs, never from the working tree.** The working
    tree holds exactly one owner value per row at any moment, so a lineage read
    from it is length 1 and the ceiling is unreachable by construction — the
    same reason the high-water mark is not a `previous_count` field.
    """
    lineage: list[str] = []
    for _sha, revision in history.revisions:
        if path not in revision.rows:
            continue
        owner = revision.owner_of(path).strip()
        if not lineage or lineage[-1] != owner:
            lineage.append(owner)
    return tuple(lineage)


def _head_owners(history: History) -> dict[str, str]:
    """Each artifact's owner as most recently COMMITTED. `{}` with no history.

    The reference the §0g assignment arm diffs the working tree against: an
    owner value that differs from this IS an assignment happening now, in this
    tree, and has not yet been committed anywhere.
    """
    if not history.revisions:
        return {}
    _sha, newest = history.revisions[-1]
    return {path: row.owner.strip() for path, row in newest.rows.items()}


def _high_water_mark(home: Path) -> tuple[frozenset[str], str, str]:
    """The TIGHTEST accepted set this baseline has ever been COMMITTED with.

    Returns `(set, sha, error)`. Kept as a named function with this signature
    because the committed suite drives it directly; ARC 027 moved the git walk
    beneath it into `_committed_history` so the owner lineage reads the same
    revisions rather than re-deriving them.

    ## Where the high-water mark lives, and why it lives there

    A ratchet needs a prior mark to ratchet against, and the tempting place to put
    it is a `previous_count` field in this same file — which the same hand edits
    in the same motion as the addition it excuses, making the ratchet decorative.
    A second config file is the same object with an extra filename.

    **So the mark is not stored at all. It is DERIVED from git history**, which is
    the one record on this box that the edit being judged provably cannot reach:
    `git show <sha>:<path>` reads the committed tree, not the working tree, and
    moving a committed revision means rewriting history — which `CLAUDE.md`
    directive 6 forbids outright and which changes every downstream sha, so it
    cannot be done quietly. Doctrine B.7's self-enforcing pattern, pointed at
    time instead of at a document.

    **The mark is the minimum over the WHOLE history, not `HEAD`.** `HEAD` alone
    would let an addition be laundered by committing it: one commit later the
    addition IS the prior mark. The minimum-over-history has no such laundry
    cycle — the tightest revision stays the tightest forever.

    **A revision that cannot be read is an ERROR, never a skip.** A silently
    skipped revision might be exactly the tightest one, and a high-water mark that
    quietly rises is the vacuous pass this gate exists to refuse.
    """
    return _mark_from(_committed_history(home))


def _mark_from(history: History) -> tuple[frozenset[str], str, str]:
    """The minimum-over-history accepted set. Pure, so the walk is measured once."""
    if history.error:
        return frozenset(), "", history.error
    best: frozenset[str] | None = None
    best_sha = ""
    for sha, revision in history.revisions:
        if best is None or len(revision.uncovered) < len(best):
            best, best_sha = revision.uncovered, sha
    return (best or frozenset()), best_sha, ""


def _ratchet_defects(
    baseline: Baseline, mark: frozenset[str], sha: str
) -> list[tuple[str, str]]:
    """Every accepted entry added since the tightest committed revision, unadmitted.

    The set may SHRINK freely — that is the whole point of a ratchet. An ADDITION
    is permitted only when the baseline names the single arc that admitted it, in
    `admitted`, under the SAME grammar `validate_result` enforces on `guard_owner`
    (one function, two consumers). An addition with no arc, or with a range, is a
    LOUD FAIL naming the path and the reason.
    """
    defects: list[tuple[str, str]] = []
    for path in sorted(baseline.uncovered - mark):
        # SHAPE ONLY — no `completed` argument, deliberately (ARC 026 B2).
        # `admitted` records the arc that ALREADY admitted this path. That arc
        # completes, and the record stays true; passing the completion set here
        # would redden every honest `admitted` entry at the next arc boundary.
        # A guard owner is a promise, an admitting arc is a receipt.
        defect = guard_owner_defect(baseline.rows[path].admitted)
        if defect:
            defects.append(
                (
                    f"{BASELINE}:admitted:{path}",
                    (
                        f"{path!r} was ADDED to the accepted-uncovered set since the "
                        f"tightest committed revision {sha[:12]} ({len(mark)} "
                        f"entries); a ratchet may only shrink, and an addition "
                        f"requires a named arc in `admitted` — {defect}"
                    ),
                )
            )
    return defects


# ===========================================================================
# PER-ROW ARMS. ARC 028 (C2). Each returns `[(site, why)]` so `run` stays a
# linear sequence of named arms rather than a nest of conditionals inside the
# instrument that decides whether this repo's coverage debt may grow.
# ===========================================================================

#: Where a `measured_by: tests` claim is checked. Test modules are excluded from
#: the ARTIFACT set (a test is not a settable artifact, it IS the measurement) —
#: which is exactly why they are the population searched here.
_TEST_DIR = "scripts/tests"


def _importable_name(path: str) -> str:
    """The dotted name a test would import this artifact by, or `''`.

    `scripts/nixverify/gitenv.py` -> `nixverify.gitenv`, because `scripts/` is on
    the path and no test writes the file path. Without this the classifier would
    call ten thoroughly-tested modules uncovered-by-everything, which is a
    FALSE RED and would make the honest distinction below worthless.

    `__init__.py` gets NO dotted name, deliberately. Its package name appears in
    every `from nixverify... import` line in the tree, so a dotted match would
    mark it covered on the strength of imports of its SIBLINGS. It therefore
    matches only by literal path — and comes back named by nothing, which is the
    true answer: it is EXECUTED constantly and ASSERTED ABOUT nowhere.
    """
    if not path.endswith(".py") or path.endswith("__init__.py"):
        return ""
    parts = path[: -len(".py")].split("/")
    if parts and parts[0] in ("scripts", "checks", "databases"):
        parts = parts[1:]
    return ".".join(parts)


def _named_by_tests(home: Path, paths: list[str]) -> dict[str, list[str]]:
    """Which test modules NAME each artifact, by path or by importable name.

    **READ THE LIMIT BEFORE READING THE ANSWER.** This proves a test module
    MENTIONS the artifact. It does not prove the test EXECUTES it, and it
    certainly does not prove it ASSERTS anything about it — the same gap D3.16
    named for `SUBJECTS`, one layer over. It is kept because it separates two
    states this gate could not previously tell apart at all: an artifact the
    suite at least reaches, and an artifact NOTHING in this repository names.
    """
    sources: dict[str, str] = {}
    for module in sorted((home / _TEST_DIR).glob("*.py")):
        try:
            sources[f"{_TEST_DIR}/{module.name}"] = module.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover - a file that vanished mid-run
            continue
    found: dict[str, list[str]] = {}
    for path in paths:
        dotted = _importable_name(path)
        pattern = re.compile(
            re.escape(path)
            if not dotted
            else rf"{re.escape(path)}|\b{re.escape(dotted)}\b"
        )
        found[path] = sorted(
            name for name, text in sources.items() if pattern.search(text)
        )
    return found


def _shape_defects(baseline: Baseline) -> list[tuple[str, str]]:
    """Every row must classify itself and say why. A blank row is not a row."""
    defects: list[tuple[str, str]] = []
    for path, row in sorted(baseline.rows.items()):
        if row.measured_by not in MEASURED_BY_VALUES:
            defects.append(
                (
                    f"{BASELINE}:artifacts:{path}",
                    (
                        f"`measured_by` is {row.measured_by!r}; expected one of "
                        f"{list(MEASURED_BY_VALUES)}. An unclassified row is the "
                        "aggregate wearing a per-artifact shape"
                    ),
                )
            )
        if not row.reason.strip():
            defects.append(
                (
                    f"{BASELINE}:artifacts:{path}",
                    (
                        "no `reason` — the decomposition exists so each debt "
                        "states its own case; a row that cannot say why it is "
                        "uncovered is a suppression entry"
                    ),
                )
            )
    return defects


def _coverage_defects(
    baseline: Baseline, named: dict[str, list[str]]
) -> list[tuple[str, str]]:
    """Each row's `measured_by` claim, checked against the test tree.

    Both directions, because both are lies of the same family: a row claiming
    the suite measures it when nothing names it, and a row claiming nothing
    measures it when something does. The second matters as much as the first —
    it is how an artifact that HAS acquired coverage keeps hiding in the
    accepted set.
    """
    defects: list[tuple[str, str]] = []
    for path, row in sorted(baseline.rows.items()):
        hits = named.get(path, [])
        site = f"{BASELINE}:artifacts:{path}:measured_by"
        if row.measured_by == MEASURED_BY_TESTS and not hits:
            defects.append(
                (
                    site,
                    (
                        f"claims {MEASURED_BY_TESTS!r} but NO module under "
                        f"{_TEST_DIR}/ names {path} or its importable name "
                        f"{_importable_name(path)!r} — the claim is false"
                    ),
                )
            )
        elif row.measured_by == MEASURED_BY_NOTHING and hits:
            defects.append(
                (
                    site,
                    (
                        f"claims {MEASURED_BY_NOTHING!r} but {len(hits)} test "
                        f"module(s) name it ({', '.join(hits[:4])}) — the row is "
                        "stale and understates what already exists"
                    ),
                )
            )
    return defects


def _assignment_defects(
    baseline: Baseline,
    head: dict[str, str],
    completed: frozenset[int],
    live: int | None,
) -> list[tuple[str, str]]:
    """STANDING RULE §0g — an owner being ASSIGNED right now, judged now.

    A row whose owner differs from the value committed at `HEAD` is an
    assignment in progress: it exists only in this working tree and has not been
    committed anywhere. That is the one moment at which "can this arc still
    discharge it?" has a different answer from the read rule's, and CHECK-DEBT
    D3.40 is the measured proof that the difference is a whole arc wide.

    Rows whose owner is UNCHANGED are not assignments and are left to the read
    rule; re-judging them here would redden an owner that was legitimate when it
    was written, which is a different (and much louder) rule than the one §0g
    asks for.
    """
    defects: list[tuple[str, str]] = []
    for path, row in sorted(baseline.rows.items()):
        if path in head and head[path] == row.owner.strip():
            continue
        defect = guard_owner_assignment_defect(row.owner, completed, live)
        if defect:
            defects.append((f"{BASELINE}:artifacts:{path}:owner", defect))
    return defects


def _ceiling_defects(
    baseline: Baseline, history: History
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """The re-owning ceiling, PER ARTIFACT. Returns (defects, deferrals).

    ARC 027 (B2), CHECK-DEBT D2.31, decomposed by ARC 028 (C2). Every rule
    before this one judges an owner VALUE standing today, and a marker walked
    forward one honest arc at a time passes all of them forever. This is the
    only arm that judges the SEQUENCE — and now it judges sixteen sequences
    rather than one, so an artifact that has been handed on three times is named
    instead of being averaged into a pile.
    """
    defects: list[tuple[str, str]] = []
    deferrals: list[tuple[str, str]] = []
    for path in sorted(baseline.rows):
        lineage = _row_lineage(history, path)
        site = f"{BASELINE}:artifacts:{path}:owner"
        if not lineage:
            # A row with NO committed lineage has never been committed at all.
            # For the single aggregate guard that meant a missing record and
            # `reowning_defect` calls it a defect — correctly, because that file
            # always had history. Per artifact it means something else and much
            # more ordinary: a row added in THIS working tree. That case is
            # already owned by `_ratchet_defects`, which FAILs it unless the
            # baseline names the arc that admitted it, so judging it here as
            # well would make every legitimate admission red. A path present in
            # the high-water mark always has a lineage, so nothing that the
            # ceiling should see reaches this branch.
            continue
        defect = reowning_defect(lineage)
        if defect:
            # Conclusive even on a TRUNCATED history: truncation drops the
            # OLDEST revisions, so the lineage is a lower bound, and a lower
            # bound already over the ceiling is over it. Checked BEFORE the
            # truncation arm for exactly that reason.
            defects.append((site, defect))
        elif history.truncated:
            deferrals.append(
                (
                    site,
                    (
                        f"the committed history came back at the {_HISTORY_LIMIT}-"
                        "revision limit, so this artifact's owner lineage is a "
                        "LOWER BOUND and its ceiling cannot be shown to be "
                        "unexhausted. Raise the limit or discharge the guard"
                    ),
                )
            )
    return defects, deferrals


def _owner_deferrals(
    baseline: Baseline, completed: frozenset[int]
) -> list[tuple[str, str]]:
    """The READ rule, per artifact. ARC 025's arm, decomposed.

    Validated HERE as well as in `validate_result` so an operator is told WHICH
    row's `owner` field is the offender rather than being handed the engine's
    generic downgrade.
    """
    return [
        (f"{BASELINE}:artifacts:{path}:owner", defect)
        for path, row in sorted(baseline.rows.items())
        if (defect := guard_owner_defect(row.owner, completed))
    ]


def _render(pairs: list[tuple[str, str]]) -> str:
    """`[(site, why)]` -> one detail line, IDENTICAL reasons grouped by site.

    Sixteen rows failing for one reason used to print that reason sixteen times,
    which buries the row that fails for a DIFFERENT one — the decomposition's
    own §0a hazard, since more rows means more repetition. Grouping keeps every
    site named (doctrine C.2) while making a single odd row visible.
    """
    grouped: dict[str, list[str]] = {}
    for site, why in pairs:
        grouped.setdefault(why, []).append(site)
    return "; ".join(
        (sites[0] if len(sites) == 1 else f"{len(sites)} rows [{', '.join(sites)}]")
        + f": {why}"
        for why, sites in grouped.items()
    )


def _guard_of_record(baseline: Baseline) -> str:
    """The single arc `CheckResult.guard_owner` can hold, out of many.

    **A STATED LIMITATION, NOT A DESIGN.** `CheckResult` carries ONE
    `guard_owner`, and `validate_result` requires it to be exactly one arc. A
    decomposed guard has one owner PER ARTIFACT, so when several live owners
    disagree the field cannot represent the truth and the lowest-numbered — the
    arc that owes soonest — is what it holds. The full per-row map is in
    `detail` on every run, so nothing is hidden; what is lost is the ability to
    read the owner off the summary line. CHECK-DEBT D3.63.
    """
    owners = {row.owner.strip() for row in baseline.rows.values() if row.owner.strip()}
    return min(owners, default="")


def _prepare(home: Path) -> tuple[list[str], Baseline, History, str]:
    """Everything `run` needs before it can judge anything. `str` = a refusal."""
    artifacts, error = _tracked_artifacts(home)
    if error:
        return [], Baseline(), History(), error
    if len(artifacts) < MIN_CREDIBLE_ARTIFACTS:
        return (
            [],
            Baseline(),
            History(),
            (
                f"only {len(artifacts)} tracked artifact(s) enumerated, below the "
                f"credibility floor of {MIN_CREDIBLE_ARTIFACTS} — an empty or tiny "
                "enumeration would make every artifact trivially covered"
            ),
        )
    baseline = _load_baseline(home)
    if baseline.error:
        return [], baseline, History(), baseline.error
    # ONE walk of the baseline's committed history; three facts derived from it
    # (ARC 027 B2, extended ARC 028 C2). See `History`.
    history = _committed_history(home)
    if history.error:
        # The ratchet's prior mark is what makes a green mean anything. Without
        # it the gate can still see regressions but cannot see the baseline
        # growing, which is the whole of ARC 025's C3 — so it reports what it
        # could not measure rather than passing on the half it could.
        return artifacts, baseline, history, history.error
    return artifacts, baseline, history, ""


def _ratchet_arms(
    baseline: Baseline, uncovered: set[str], mark: frozenset[str], mark_sha: str
) -> list[tuple[str, str]]:
    """Regression, rot, and unadmitted growth — the three set-level arms."""
    defects: list[tuple[str, str]] = [
        (path, "no check declares this artifact as a SUBJECT")
        for path in sorted(uncovered - baseline.uncovered)[:20]
    ]
    defects.extend(
        (
            f"{BASELINE}:{path}",
            (
                "baseline still accepts this artifact as uncovered, but a check "
                "now declares it — tighten the baseline (a ratchet may only "
                "shrink)"
            ),
        )
        for path in sorted(baseline.uncovered - uncovered)[:20]
    )
    defects.extend(_ratchet_defects(baseline, mark, mark_sha)[:20])
    return defects


@dataclasses.dataclass(frozen=True)
class Measured:
    """One run's raw counts, so the evidence renderer takes one argument.

    Grouped rather than passed as seven positionals because they are one thing —
    what this run saw — and because a seven-argument renderer is where a caller
    eventually swaps two same-typed arguments and the evidence quietly describes
    a different measurement.
    """

    artifacts: list[str]
    declared: set[str]
    uncovered: set[str]
    baseline: Baseline
    mark: tuple[frozenset[str], str]
    history: History
    named: dict[str, list[str]]


def _evidence_for(state: Measured) -> str:
    """What was measured, on every run, including what it does NOT prove."""
    artifacts, declared, uncovered = state.artifacts, state.declared, state.uncovered
    baseline, mark, history, named = (
        state.baseline,
        state.mark,
        state.history,
        state.named,
    )
    unnamed = sorted(path for path in baseline.rows if not named.get(path))
    return (
        f"{len(artifacts)} tracked artifact(s); {len(declared)} declared subject(s); "
        f"{len(uncovered)} uncovered; baseline schema v{baseline.schema} accepts "
        f"{len(baseline.uncovered)} in {len(baseline.rows)} per-artifact row(s); "
        f"ratchet high-water mark {len(mark[0])} at committed revision "
        f"{mark[1][:12]}; ceiling {GUARD_REOWN_CEILING} applied PER ARTIFACT over "
        f"{len(history.revisions)} committed revision(s)"
        f"{' (history TRUNCATED — a lower bound)' if history.truncated else ''}; "
        f"{len(unnamed)} row(s) named by NOTHING under {_TEST_DIR}/ "
        f"({', '.join(unnamed) or 'none'}). "
        "UNBOUND (D3.10): proves an artifact is NAMED by a check — and, per row, "
        "MENTIONED by a test — never that it is MEASURED by either. Do not read "
        "this verdict as coverage."
    )


def run(  # pylint: disable=unused-argument,too-many-locals,too-many-return-statements
    mode: Mode, ctx: Context
) -> CheckResult:
    """Compare tracked artifacts against declared subjects, and ratchet.

    ARC 028 (C2) decomposed the single sixteen-artifact guard into one row per
    artifact. The arms below are unchanged in what they forbid; what changed is
    that every one of them now names an ARTIFACT, and the owner and the ceiling
    are per artifact rather than per file.

    Five returns is five distinct named outcomes: the refusal, the failure, the
    deferral, the guarded deferral and the pass. The arms are computed as lists
    so that ALL of them are evaluated on every run — an early return per arm
    would report the first defect and hide the other fifteen, which is precisely
    what the aggregate did.
    """
    home = Path(ctx.nix_home)
    artifacts, baseline, history, refusal = _prepare(home)
    if refusal:
        return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=refusal)

    declared = _declared_subjects(home)
    uncovered = {path for path in artifacts if path not in declared}
    mark, mark_sha, _ = _mark_from(history)
    named = _named_by_tests(home, sorted(baseline.rows))
    evidence = _evidence_for(
        Measured(
            artifacts, declared, uncovered, baseline, (mark, mark_sha), history, named
        )
    )

    completed, completion_error = completed_arcs(home)
    if completion_error:
        # ARC 026 (B2). FAIL CLOSED. Without the completion record this gate
        # cannot tell a live owner from a dead one, and "probably still open" is
        # the assumption that let `ARC 025` stand as an owner through a whole arc.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            evidence=evidence,
            detail=f"{BASELINE} owners cannot be judged — {completion_error}",
        )
    live, live_error = in_flight_arc(home)

    defects = _ratchet_arms(baseline, uncovered, mark, mark_sha)
    defects.extend(_shape_defects(baseline))
    defects.extend(_coverage_defects(baseline, named))
    defects.extend(
        _assignment_defects(baseline, _head_owners(history), completed, live)
    )
    ceiling_defects, deferrals = _ceiling_defects(baseline, history)
    defects.extend(ceiling_defects)
    if defects:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site="; ".join(site for site, _ in defects),
            evidence=evidence,
            detail=_render(defects),
        )

    deferrals.extend(_owner_deferrals(baseline, completed))
    if live_error and baseline.rows:
        deferrals.append((f"{BASELINE}:artifacts", live_error))
    if deferrals:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            evidence=evidence,
            detail=_render(deferrals),
        )

    if baseline.rows:
        # AMENDMENT 1: measured subject, known-red marker, named owner — now one
        # marker per artifact, with `guard_owner` holding the arc that owes
        # soonest because the field can hold only one (see `_guard_of_record`).
        return CheckResult(
            name=NAME,
            status=Status.GUARDED,
            evidence=evidence,
            guard_owner=_guard_of_record(baseline),
            detail="; ".join(
                f"{path} -> {row.owner.strip()} "
                f"({len(_row_lineage(history, path)) - 1} of "
                f"{GUARD_REOWN_CEILING} re-owning(s) used, measured_by="
                f"{row.measured_by})"
                for path, row in sorted(baseline.rows.items())
            ),
        )
    return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)


if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
