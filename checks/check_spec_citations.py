#!/usr/bin/env python3
"""Every attributed `§`-citation resolves to a real heading in the cited document.

ONE gate, ONE property (`nix_check_contract.md` §5.5, doctrine C.9): *a section
citation names a section that exists.* No instrument in this tree owned that
property before ARC 019 — `check_order_path_bans` owns the retry ban and
`check_derived_claims` owns derive-never-restate — so this is an extension of
nothing and a new instrument is the correct shape, not a second opinion.

WHY A GATE AND NOT A CLAIM. `checks/derived_claims.json` was the obvious home and
is the wrong one, for three reasons measured rather than assumed:
  * that registry's own scope line reads "numeric claims only. Prose facts are
    out of scope and must not be smuggled in as a count of words that happen to
    match." A citation is a set-membership fact, not a number;
  * a claim compares integers from >= 2 sources. The only integer available here
    is "how many citations do not resolve", and the assertion would be that it
    equals zero — `debug.md` §7.4 names `assert count(*) == 0` as a bad anchor by
    name, and two probes both counting the same non-resolutions are the same
    computation twice, which `check_derived_claims` rejects as §7.12 condition 3;
  * a claim can say "the numbers disagree". It cannot say *which file, which
    line, which citation* — and doctrine C.2 requires the instrument name the
    site. That naming is the whole value here, because the defect being closed
    propagated by nobody being able to see where it came from.

------------------------------------------------------------------------------
THE FAILURE THIS CLOSES — measured, ARC 018
------------------------------------------------------------------------------
`§2.1` was written in the ARC 017 *task brief* as its own prohibition 1. The
ARC 017 gate docstring cited it honestly as "ARC 017 §2.1" — a brief, named as a
brief. The CHECK-DEBT D2.14 row then wrote "banned by §2.1" with **no document**,
and from there it read as the frozen spec, which has no §2.1. Nothing in the tree
could tell the two apart, because nothing checked citations at all.

Separately, "invariant N per §14" pointed at the wrong section across at least
three briefs: `§14` exists, is titled "Locked Invariants", and holds unnumbered
bullets, while the numbered seam invariants 1-5 are at `§2A:103-107`. Both
defects are mechanically checkable and neither was caught.

Note what the first one teaches about mechanism, because it drove this design:
**the defect was the missing document, not the wrong number.** An unattributed
`§X` acquires whatever authority the reader assumes.

------------------------------------------------------------------------------
BOTH SIDES ARE DERIVED. NEITHER IS A HAND-MAINTAINED LIST.
------------------------------------------------------------------------------
  HEADINGS — parsed at run time from every `*.md` in `docs/`. A heading
      contributes a label when its text opens with a section number
      (`## 2A. Broker Abstraction Contract` -> `2A`); its SPAN runs to the line
      before the next labelled heading. Nothing is typed out here: adding a
      document to `docs/` indexes it, and renaming one is caught by
      `REQUIRED_DOCS` below rather than by silence.

  ALIASES — each indexed document's own filename and its stem. Derived from the
      same directory listing, so a new document is citable the moment it lands.

  CITATIONS — a regex scan of the working tree under `SCAN_ROOTS`, minus
      `SKIP_DIRS`. The tree, not `git ls-files`: `debug.md` §8 failure mode #14
      and CHECK-DEBT D1.16 are both the observation that a git-tracked file set
      is something a person can shrink without touching the gate.

------------------------------------------------------------------------------
ATTRIBUTION — how the gate decides WHICH document a `§X` means
------------------------------------------------------------------------------
This is the hard half and it is where a naive version produces false positives,
which doctrine B.4 says makes a gate broken rather than strict. Three rules were
measured against this tree before one was adopted:

  (a) whole enclosing paragraph, any document named in it wins. MEASURED: 902
      citations, 404 attributed, and among them `debug.md` §7.12 attributed to
      `CHECK-DEBT.md` because the paragraph mentions the ledger; `broker_seam.py`
      §2A attributed to `nix_check_contract.md`; and `elements_v2.md`'s own
      "v1.3" references to spec section 12A attributed to `elements_v2.md`
      itself. Rejected: it reddens correct prose.

  (b) same line, or one line either side. MEASURED: precision no better, because
      a markdown TABLE ROW is one very long line naming several documents, and
      `docs/CHECK-DEBT.md` is mostly table rows. It also scored the ARC 017
      series row's "banned by §2.1" as RESOLVED — against `debug.md`, which does
      have a §2.1. A rule that resolves the arc's own subject to the wrong
      document is worse than one that declines to resolve it.

  (c) ADOPTED — nearest document alias inside the enclosing STRUCTURAL BLOCK and
      within `ATTRIBUTION_CHARS` characters, preferring a mention that PRECEDES
      the citation. A block is a blank-line-separated paragraph, except that a
      markdown table row is its own block, because a table row is a record and
      the row above it is a different record. MEASURED on this tree: 114
      attributed, and every governed non-resolution inspected by hand was real.

`ATTRIBUTION_CHARS` is a calibration, and `nix_check_contract.md` §5.2 permits
calibrating a new instrument as it comes online provided the calibration is
MEASURED. It was: at an unbounded block window the gate reported
`check_order_path_bans.py:226` — its standing-question banner, which is correct
prose about `debug.md` §7.12 — as a citation of `nix_check_contract.md`, because
that file's previous paragraph mentions that document. Bounding the search
removed that hit and removed no real one.

**A citation this gate cannot attribute is an ADVISORY, never a violation, and
it is COUNTED AND PRINTED on every run.** That is the honest reading: the gate
does not know which document is meant, so it declines to judge, out loud. It is
also the largest thing this gate does not do — see §7.12 condition 6 — and the
repair is to write the document name beside the citation, at which point this
gate starts checking it with no edit to this file.

A document with ZERO numbered headings is UNINDEXABLE. `VERIFY-AND-CHECKS.md`
numbers by Part letter (`A.4`, `B.7`, `C.2`), `docs/CHECK-DEBT.md` by debt id,
`docs/directory_structure.md` not at all. Without this guard every citation
attributed to one of them would be a false violation, which is the same B.4
error one level down.

------------------------------------------------------------------------------
LINE-NUMBER CITATIONS (the `2A:71` spelling) — the choice, and the argument
------------------------------------------------------------------------------
A line number is `debug.md` §8 failure mode #4 — a stale literal anchor — and it
WILL drift. Three options, and the rejected two are the argument:

  (i) verify the section and IGNORE the coordinate. Cheapest. It makes the
      coordinate decorative: it may drift arbitrarily and nothing ever says so,
      which is a literal anchor with a gate standing next to it saying nothing.
      Rejected.

  (iii) verify the section PLUS a content anchor — a quoted phrase written beside
      the citation must appear at that line. Strongest on paper, worse in
      practice. The anchor is prose a person types beside each citation, which is
      a hand-maintained list one level down (#14) and *a specific spelling*,
      which §7.4 names as a bad anchor in its own right. It also cannot be
      applied to the citations already in the tree without editing files this arc
      does not own. Rejected — and rejected explicitly rather than deferred,
      because a half-built version of it would make the residual look addressed.

  (ii) ADOPTED — verify the coordinate falls inside the cited section's own line
      SPAN, where the span is derived from the document being cited. Nothing is
      written down: both the coordinate and the span come from the two artifacts
      already in play. It catches the failure that actually happened — "invariant
      N per §14" is exactly a coordinate that does not lie in the span of the
      section it was attached to — and it costs one comparison.

      It has extra force on the document the defect occurred in:
      `nics_risk_subsystem_spec_v1.3.md` is **frozen — never edit**, so a
      coordinate correct today can only go wrong by an edit that is itself
      forbidden. Span containment is therefore near-exact there, and a genuine
      approximation only for the mutable documents.

      WHAT IT DOES NOT CATCH, stated rather than discovered later: drift WITHIN a
      section. `§2A:71` moving to `§2A:75` still lands in the span. §7.12
      condition 5 carries this.

------------------------------------------------------------------------------
SUPPRESSION — per-site, justified, self-expiring. Never file-level.
------------------------------------------------------------------------------
`checks/citation_reviewed.json`, one entry per reviewed site, keyed by
`(file, section, document)` and DELIBERATELY NOT by line number, because a line
number is failure mode #4 and this gate exists to argue that. It has exactly one
legitimate use: prose whose subject IS a non-existent citation. ARC 018's own
correction note in `check_order_path_bans.py` says "There is no §2.1 in that
document" three lines after naming the document, and a gate that reddens the
record of a fix is reddening the fix.

Same three honesty properties as `order_path_retry_reviewed.json`: an entry with
no `justification` or no `reviewed_in` is REJECTED and the rejection is a
VIOLATION; an entry matching NOTHING is a VIOLATION (the site moved and the
review no longer applies to code that exists); every entry is printed in
`evidence` on every run.

------------------------------------------------------------------------------
SCOPE — GOVERNED versus SURVEYED, and why the line is where it is
------------------------------------------------------------------------------
The whole tree is SCANNED. Only `GOVERNED_ROOTS` can produce a VIOLATION;
everything else is SURVEYED — its non-resolutions are named and counted in
`evidence` on every run, and are never a failure.

That is not a convenience. Doctrine B.3: *an owner that cannot pay is no owner
wearing a name.* The surveyed set at ARC 019 holds seven real non-resolutions in
`scripts/verify.py`, `scripts/nixverify/__init__.py`, `scripts/tests/` and
`install.sh` — all of them citing `nix_check_contract.md` sections 9.1 through
9.5, which are numbers carried over from the ARC 008 self-authored
reconstruction that ARC 010 renamed into that file. Its section 9 is "Engine
invariants" and its subsections are unnumbered, so none of the five exists.
They are the SAME defect class as the phantom 2.1 above, and they are recorded
as CHECK-DEBT **D1.21** rather than reddened here, because
this arc's sub-agent C cannot write those files and a gate that reddens on
somebody else's behalf converts a finding into a blocked branch.

**Widening `GOVERNED_ROOTS` is the discharge of D1.21 and is a one-tuple edit.**

------------------------------------------------------------------------------
§7.12 THE STANDING QUESTION — what would have to be true for this gate to PASS
while measuring nothing?
------------------------------------------------------------------------------
Seven conditions, each stated so it could be planted.

 1. `docs/` is renamed, empty, or holds no `.md`, so the heading index is empty
    and every citation is "unattributable" — a scan of zero headings reports no
    unresolved citations.
    GUARDED: `REQUIRED_DOCS` must each be present AND contribute at least one
    numbered heading, or the gate is CANNOT_MEASURE. Note the required names are
    VERSION-BEARING (`nics_risk_subsystem_spec_v1.3.md`): a v1.4 that lands
    without this constant moving makes the gate go CANNOT_MEASURE loudly rather
    than green quietly, which is the correct direction for a fail-closed gate.

 2. The tree walk returns nothing — a bad suffix set, a `SKIP_DIRS` that grew, a
    `SCAN_ROOTS` pointing at an empty directory — and zero citations resolve
    cleanly.
    GUARDED: the gate requires a non-empty ATTRIBUTED set, and additionally
    requires at least one citation to have RESOLVED into each of
    `REQUIRED_DOCS`. Resolving zero citations into the frozen spec means the
    gate is not looking at its subject whatever else it counted.

 3. Every citation becomes an ADVISORY — attribution stops working (an alias
    regex that matches nothing, an `ATTRIBUTION_CHARS` of 0) — and a gate with no
    attributed citations has no violations to report.
    GUARDED by condition 2's floor, and made visible besides: `evidence` prints
    attributed / unattributed / ambiguous / unindexable / suppressed counts on
    every run, so a collapse in the attributed count is readable rather than
    inferred.

 4. `GOVERNED_ROOTS` is narrowed — to `()`, or to a path that does not exist —
    so every non-resolution demotes to a survey advisory and the gate is green
    over a tree full of bad citations.
    GUARDED, PARTIALLY: the governed file count is asserted non-zero and printed
    on every run, and `REQUIRED_GOVERNED` names two files that must be inside it.
    NOT GUARDED: narrowing from three roots to two. That is failure mode #14 and
    it is inherent to any gate whose severity is scoped; the mitigation is that
    the roots are printed and the survey count is printed beside them, so a
    narrowing shows up as violations falling and survey advisories rising.

 5. A line-coordinate citation is checked but the span is wrong-but-containing.
    `§2A:71` drifting to `§2A:75` stays inside §2A's span and passes. This is the
    residual of design choice (ii) above and it is not repaired here.
    PARTIALLY VISIBLE: the count of coordinates actually range-checked is printed
    on every run, so an arm that has silently lost its subject — zero coordinates
    checked — is readable. It is NOT a failure, because zero line-coordinate
    citations is a legitimate state for this tree.

 6. UNGUARDED, AND THE REAL LIMIT — an UNATTRIBUTED citation is exactly the
    defect that produced §2.1, and this gate treats it as an advisory. A tree in
    which every `§X` names no document passes this gate completely while being
    maximally vulnerable to the failure it was built for. That is not an
    oversight, it is a staged repair: at ARC 019 the tree carries far more
    unattributed citations than attributed ones, and promoting them to violations
    in one step would redden files across four owners at once. The count is
    printed on every run so the trend is visible, and promoting unattributed to a
    violation — starting inside `GOVERNED_ROOTS` — is recorded as CHECK-DEBT
    **D2.17**. Plantable in the direction that matters: delete the document name
    beside any governed citation and this gate stops checking it, silently, which
    is why the advisory count is printed and not merely tallied.

 7. UNGUARDED — a citation that resolves to a heading that EXISTS but is not the
    heading the author meant. `§13` resolves in four of the indexed documents.
    Attribution decides which one, and attribution is a proximity heuristic, not
    a proof. This gate proves a citation is not DANGLING; it cannot prove it is
    APT. No mechanical instrument can, and a version that tried would be reading
    intent out of prose.
"""

from __future__ import annotations

import bisect
import json
import re
from pathlib import Path
from typing import NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# R0801 (duplicate-code) is disabled at module scope for the same reason every
# other gate carries it: `nix_check_contract.md` §4.2 requires each
# checks/check_*.py be independently runnable and map status -> exit code
# identically, and doctrine B.2 requires the crash path return CANNOT_MEASURE in
# both. Those blocks are MANDATED to be the same text; the only way to
# deduplicate them is a shared helper, which §4.2 forbids. Hoisted to module
# scope because R0801 is reported at line 1.
# pylint: disable=duplicate-code
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

NAME = "check_spec_citations"

# --------------------------------------------------------------------------
# SCOPE — the tree, not the git index (failure mode #14 / CHECK-DEBT D1.16).
# --------------------------------------------------------------------------
SCAN_ROOTS: tuple[str, ...] = (".",)
SKIP_DIRS: frozenset[str] = frozenset(
    {".git", ".venv", "__pycache__", ".mypy_cache", ".ruff_cache", "graphify-out"}
)
SCAN_SUFFIXES: frozenset[str] = frozenset(
    {".py", ".md", ".yaml", ".yml", ".toml", ".sh", ".cfg", ".txt"}
)

# Where the citable documents live. The index is every `*.md` in here.
DOC_DIR = "docs"

# Only these produce a VIOLATION. Everything else under SCAN_ROOTS is SURVEYED:
# counted and named, never a failure. See the scope block in the docstring, and
# CHECK-DEBT D1.21 for what widening this tuple discharges.
GOVERNED_ROOTS: tuple[str, ...] = ("checks", "scripts/broker", "docs/CHECK-DEBT.md")

# Non-vacuity floors. Each must be indexed AND must receive at least one
# resolved citation, or the gate is CANNOT_MEASURE — `debug.md` §7.12
# conditions 1 and 2 below.
REQUIRED_DOCS: tuple[str, ...] = ("nics_risk_subsystem_spec_v1.3.md", "debug.md")

# The governed scan is only believable if it reached these (§7.12 condition 4).
REQUIRED_GOVERNED: tuple[str, ...] = (
    "checks/check_order_path_bans.py",
    "docs/CHECK-DEBT.md",
)

# Calibration, measured — see the ATTRIBUTION block in the docstring.
ATTRIBUTION_CHARS = 160

SUPPRESSIONS_FILE = "citation_reviewed.json"
SUPPRESSION_KEYS = ("file", "section", "document")
SUPPRESSION_REQUIRED = ("justification", "reviewed_in")

# A markdown heading, and the section label it opens with. `## 2A. Broker
# Abstraction Contract` -> "2A"; `# NICS — Risk Subsystem Specification` -> none.
_HEADING = re.compile(r"^#{1,6}\s+(.*)$")
_LABEL = re.compile(r"^(\d+[A-Za-z]?(?:\.\d+[a-z]?)*)[.)]?\s")

# A citation, with an optional line coordinate: `§2A`, `§2A:71`, `§2A:103-108`.
_CITATION = re.compile(r"§\s*(\d+[A-Za-z]?(?:\.\d+[a-z]?)*)(?::(\d+)(?:-(\d+))?)?")

# A markdown table row. Its own attribution block: a row is a record and the row
# above it is a different record.
_TABLE_ROW = re.compile(r"^\s*\|")


# ===========================================================================
# THE HEADING INDEX — derived from the documents, never typed out.
# ===========================================================================


class Section(NamedTuple):
    """One labelled heading and the line span it owns."""

    first: int
    last: int


def index_document(text: str) -> dict[str, Section]:
    """Label -> line span, for every numbered heading in one markdown document.

    A label's span ends at the line before the next labelled heading, so an
    unnumbered `### broker-order` inside `## 2A.` stays part of §2A rather than
    truncating it. A repeated label widens the existing span rather than
    replacing it: two headings with one number is a defect in the document, not
    a reason for this index to pick one.
    """
    lines = text.splitlines()
    opened: list[tuple[str, int]] = []
    for number, line in enumerate(lines, 1):
        head = _HEADING.match(line)
        if not head:
            continue
        matched = _LABEL.match(head.group(1).strip())
        if matched:
            opened.append((matched.group(1), number))
    sections: dict[str, Section] = {}
    for position, (label, first) in enumerate(opened):
        last = opened[position + 1][1] - 1 if position + 1 < len(opened) else len(lines)
        known = sections.get(label)
        sections[label] = (
            Section(known.first, max(known.last, last))
            if known
            else Section(first, last)
        )
    return sections


def build_index(nix_home: Path) -> dict[str, dict[str, Section]]:
    """Every `*.md` in `docs/`, indexed. A document with no labels stays, empty.

    An unindexable document is kept in the map on purpose: it is what lets the
    gate say "this citation names `VERIFY-AND-CHECKS.md`, which numbers by Part
    letter" instead of "this citation names nothing".
    """
    docs: dict[str, dict[str, Section]] = {}
    for path in sorted((nix_home / DOC_DIR).glob("*.md")):
        # AppleDouble sidecars (`._name.md`) are macOS resource forks, not documents.
        # They match `*.md`, are not UTF-8, and are absent from a fresh worktree — which
        # is why ARC 019 sub-agent C never saw them and this gate raised
        # UnicodeDecodeError on its first run in the real tree. Skipping them by NAME
        # rather than by decode failure is deliberate: a genuinely undecodable document
        # in docs/ must still raise, because that is a real finding and this gate fails
        # closed. Indexing one would also be worse than crashing — a sidecar carries no
        # headings, and an un-indexable document is the map entry that EXEMPTS citations
        # attributed to it, so `._debug.md` would silently become an escape hatch.
        if path.name.startswith("._"):
            continue
        docs[path.name] = index_document(path.read_text(encoding="utf-8"))
    return docs


def build_aliases(docs: dict[str, dict[str, Section]]) -> dict[str, str]:
    """Each document's filename and stem, lower-cased, mapped back to the file."""
    aliases: dict[str, str] = {}
    for name in docs:
        aliases[name.lower()] = name
        aliases[Path(name).stem.lower()] = name
    return aliases


# ===========================================================================
# BLOCKS — the attribution unit. Structural, not a character count.
# ===========================================================================


class Block(NamedTuple):
    """A run of text within which a document mention may attribute a citation."""

    first_line: int
    text: str


def blocks(text: str) -> list[Block]:
    """Blank-line paragraphs, except that a markdown table row is its own block."""
    found: list[Block] = []
    buffered: list[str] = []
    start = 1
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip() and not _TABLE_ROW.match(line):
            if not buffered:
                start = number
            buffered.append(line)
            continue
        if buffered:
            found.append(Block(start, "\n".join(buffered)))
            buffered = []
        if _TABLE_ROW.match(line):
            found.append(Block(number, line))
    if buffered:
        found.append(Block(start, "\n".join(buffered)))
    return found


def attribute(block_text: str, position: int, aliases: dict[str, str]) -> str | None:
    """The document a citation at `position` names, or None if undecidable.

    Nearest alias within `ATTRIBUTION_CHARS`, preferring one that PRECEDES the
    citation, because prose names the document and then cites into it. A rival
    document at the same or a smaller distance makes the citation ambiguous and
    the gate declines rather than guessing.
    """
    low = block_text.lower()
    marks: list[tuple[int, int, str]] = []
    for alias, document in aliases.items():
        start = low.find(alias)
        while start >= 0:
            marks.append((start, start + len(alias), document))
            start = low.find(alias, start + 1)
    before = sorted(
        (position - end, doc)
        for start, end, doc in marks
        if end <= position and position - end <= ATTRIBUTION_CHARS
    )
    after = sorted(
        (start - position, doc)
        for start, end, doc in marks
        if start > position and start - position <= ATTRIBUTION_CHARS
    )
    candidates = before or after
    if not candidates:
        return None
    nearest_distance, nearest = candidates[0]
    rivals = [distance for distance, doc in candidates if doc != nearest]
    if rivals and min(rivals) <= nearest_distance:
        return None
    return nearest


# ===========================================================================
# CITATIONS
# ===========================================================================


class Citation(NamedTuple):
    """One `§`-citation, located and (maybe) attributed."""

    file: str
    line: int
    section: str
    coordinates: tuple[int, ...]
    document: str | None
    ambiguous: bool

    def key(self) -> tuple[str, str, str]:
        """The suppression key. NO LINE NUMBER — failure mode #4."""
        return (self.file, self.section, self.document or "")

    def site(self) -> str:
        """The site string doctrine C.2 requires the gate to name."""
        coordinate = (
            f":{'-'.join(str(c) for c in self.coordinates)}" if self.coordinates else ""
        )
        return f"{self.file}:{self.line} §{self.section}{coordinate}"


def _line_of(newlines: list[int], position: int) -> int:
    return bisect.bisect_right(newlines, position)


def citations_in(relative: str, text: str, aliases: dict[str, str]) -> list[Citation]:
    """Every citation in one file, with its attribution decided per block."""
    found: list[Citation] = []
    for block in blocks(text):
        newlines = [index for index, char in enumerate(block.text) if char == "\n"]
        for match in _CITATION.finditer(block.text):
            document = attribute(block.text, match.start(), aliases)
            coordinates = tuple(
                int(group) for group in (match.group(2), match.group(3)) if group
            )
            found.append(
                Citation(
                    file=relative,
                    line=block.first_line + _line_of(newlines, match.start()),
                    section=match.group(1),
                    coordinates=coordinates,
                    document=document,
                    ambiguous=False,
                )
            )
    return found


def scan_tree(nix_home: Path, aliases: dict[str, str]) -> list[Citation]:
    """Every citation under `SCAN_ROOTS`. The tree, not the git index."""
    found: list[Citation] = []
    for root in SCAN_ROOTS:
        base = (nix_home / root).resolve()
        for path in sorted(base.rglob("*")):
            if path.suffix not in SCAN_SUFFIXES or not path.is_file():
                continue
            relative = path.relative_to(base)
            if not SKIP_DIRS.isdisjoint(relative.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError, UnicodeDecodeError:
                continue
            found.extend(citations_in(str(relative), text, aliases))
    return found


def is_governed(relative: str) -> bool:
    """True when a non-resolution in this file is a VIOLATION, not a survey note."""
    return any(
        relative == root or relative.startswith(root + "/") for root in GOVERNED_ROOTS
    )


# ===========================================================================
# RESOLUTION
# ===========================================================================


def resolve(citation: Citation, docs: dict[str, dict[str, Section]]) -> str | None:
    """None when the citation resolves; otherwise why it does not."""
    sections = docs[citation.document or ""]
    span = sections.get(citation.section)
    if span is None:
        available = ", ".join(sorted(sections)[:12])
        return (
            f"§{citation.section} is not a heading in {citation.document} "
            f"(that document's labels include: {available}…)"
        )
    outside = [c for c in citation.coordinates if not span.first <= c <= span.last]
    if outside:
        return (
            f"line coordinate {outside} falls outside §{citation.section}'s span "
            f"{span.first}-{span.last} in {citation.document}"
        )
    return None


# ===========================================================================
# SUPPRESSIONS — per-site, justified, self-expiring. Never file-level.
# ===========================================================================


SuppressionKey = tuple[str, str, str]


class Suppressions(NamedTuple):
    """Loaded review registry: usable keys and rejected entries."""

    keys: dict[SuppressionKey, dict]
    defects: list[tuple[str, str]]


def load_suppressions(path: Path) -> Suppressions:
    """Read and VALIDATE the review registry. A malformed entry is a defect."""
    if not path.is_file():
        return Suppressions({}, [])
    payload = json.loads(path.read_text(encoding="utf-8"))
    keys: dict[SuppressionKey, dict] = {}
    defects: list[tuple[str, str]] = []
    for index, entry in enumerate(payload.get("reviewed", [])):
        where = f"{path.name}[{index}]"
        missing = [k for k in SUPPRESSION_KEYS if not entry.get(k)]
        unsigned = [
            k for k in SUPPRESSION_REQUIRED if not str(entry.get(k, "")).strip()
        ]
        if missing:
            defects.append((where, f"suppression missing key(s): {', '.join(missing)}"))
            continue
        if unsigned:
            defects.append(
                (
                    where,
                    (
                        f"suppression for {entry['file']} §{entry['section']} is "
                        f"unsigned — missing {', '.join(unsigned)}; an unsigned "
                        f"suppression is not a review"
                    ),
                )
            )
            continue
        keys[tuple(entry[k] for k in SUPPRESSION_KEYS)] = entry  # type: ignore[index]
    return Suppressions(keys, defects)


# ===========================================================================
# VERDICT
# ===========================================================================


class Tally(NamedTuple):
    """What the scan looked at, bucketed. Printed in `evidence` on every run."""

    total: int
    attributed: int
    unattributed: int
    unindexable: int
    coordinates_checked: int
    governed_files: int
    resolved_docs: set[str]


def _cannot_measure(detail: str) -> CheckResult:
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


def _index_complaint(docs: dict[str, dict[str, Section]]) -> str:
    """§7.12 condition 1: the heading index must contain its subject."""
    missing = [name for name in REQUIRED_DOCS if name not in docs]
    if missing:
        return f"docs/ does not hold required document(s): {', '.join(missing)}"
    empty = [name for name in REQUIRED_DOCS if not docs[name]]
    if empty:
        return (
            f"required document(s) contributed no numbered heading: {', '.join(empty)}"
        )
    return ""


def _floor_complaint(tally: Tally) -> str:
    """§7.12 conditions 2 and 4: an empty measurement is never a PASS."""
    if not tally.attributed:
        return "no citation in the tree could be attributed to a document"
    unreached = [name for name in REQUIRED_DOCS if name not in tally.resolved_docs]
    if unreached:
        return (
            f"no citation resolved into {', '.join(unreached)} — the gate did not "
            f"look at its subject whatever else it counted"
        )
    if not tally.governed_files:
        return f"no file under {', '.join(GOVERNED_ROOTS)} holds a citation"
    return ""


def _classify(
    found: list[Citation],
    docs: dict[str, dict[str, Section]],
    suppressions: Suppressions,
) -> tuple[list[tuple[str, str]], list[str], Tally, set[SuppressionKey]]:
    """Split every citation into violation / survey note / advisory, and tally."""
    defects: list[tuple[str, str]] = []
    survey: list[str] = []
    used: set[SuppressionKey] = set()
    counts: dict[str, int] = dict.fromkeys(
        ("attributed", "unattributed", "unindexable", "coordinates"), 0
    )
    resolved_docs: set[str] = set()
    governed_files: set[str] = set()

    for citation in found:
        if is_governed(citation.file):
            governed_files.add(citation.file)
        if citation.document is None:
            counts["unattributed"] += 1
            continue
        if not docs[citation.document]:
            counts["unindexable"] += 1
            continue
        counts["attributed"] += 1
        complaint = resolve(citation, docs)
        if complaint is None:
            resolved_docs.add(citation.document)
            counts["coordinates"] += len(citation.coordinates)
            continue
        key = citation.key()
        if key in suppressions.keys:
            used.add(key)
            survey.append(
                f"REVIEWED SUPPRESSION {citation.site()} — "
                f"{suppressions.keys[key]['justification']}"
            )
        elif is_governed(citation.file):
            defects.append((citation.site(), complaint))
        else:
            survey.append(f"SURVEY {citation.site()} -> {complaint}")

    tally = Tally(
        total=len(found),
        attributed=counts["attributed"],
        unattributed=counts["unattributed"],
        unindexable=counts["unindexable"],
        coordinates_checked=counts["coordinates"],
        governed_files=len(governed_files),
        resolved_docs=resolved_docs,
    )
    return defects, survey, tally, used


def _evidence(
    tally: Tally, docs: dict[str, dict[str, Section]], survey: list[str]
) -> str:
    """What was measured, how it was decided, and what was declined. Every run."""
    indexed = sum(1 for sections in docs.values() if sections)
    return (
        f"scanned {tally.total} §-citation(s) across the tree against {indexed} "
        f"indexed document(s) of {len(docs)} in {DOC_DIR}/; "
        f"attributed {tally.attributed}, unattributed {tally.unattributed}, "
        f"cited-but-unindexable {tally.unindexable}; "
        f"{tally.coordinates_checked} line coordinate(s) range-checked; "
        f"governed roots {list(GOVERNED_ROOTS)} over {tally.governed_files} citing "
        f"file(s); resolved into {sorted(tally.resolved_docs)}; "
        + ("; ".join(survey) if survey else "0 survey/suppression notes")
    )


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Resolve every attributed citation against the real document. Never repairs.

    Rewriting a citation is an editorial act on prose whose meaning this gate
    cannot read (§7.12 condition 7), so it reports and stops.
    """
    try:
        docs = build_index(ctx.nix_home)
        complaint = _index_complaint(docs)
        if complaint:
            return _cannot_measure(
                f"{complaint} (§5.3: an empty scope is never a PASS)"
            )

        suppressions = load_suppressions(
            Path(__file__).resolve().parent / SUPPRESSIONS_FILE
        )
        found = scan_tree(ctx.nix_home, build_aliases(docs))
        defects, survey, tally, used = _classify(found, docs, suppressions)

        complaint = _floor_complaint(tally)
        if complaint:
            return _cannot_measure(
                f"{complaint} (§5.3: an empty scope is never a PASS)"
            )

        missing = [
            name for name in REQUIRED_GOVERNED if not (ctx.nix_home / name).is_file()
        ]
        if missing:
            return _cannot_measure(
                f"governed scope missing required member(s): {', '.join(missing)}"
            )

        defects.extend(suppressions.defects)
        for key in sorted(set(suppressions.keys) - used):
            defects.append(
                (
                    f"{SUPPRESSIONS_FILE}:{'/'.join(key)}",
                    (
                        "STALE SUPPRESSION — matches no citation in the current tree; "
                        "the text moved or was corrected and the review no longer applies"
                    ),
                )
            )

        evidence = _evidence(tally, docs, survey)
        if defects:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in defects),
                evidence=evidence,
                detail="; ".join(f"{site}: {why}" for site, why in defects),
            )
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1 —
        # exit 1 would report a violation the gate never observed.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# Deliberately duplicated across every checks/check_*.py: the check
# contract (§4.2) requires each module be independently runnable, so this
# block cannot be factored into a shared helper without breaking that.
# The disable pragma must be on its own line, not trailing on the `if` —
# pylint's Similarities checker (R0801) does not honour a same-line
# trailing disable comment here (verified empirically, pylint v4.0.6).
# pylint: disable=duplicate-code
if __name__ == "__main__":
    import sys

    from nixverify.contract import exit_code_for, validate_result

    HOME = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().parent.parent
    )
    OUTCOME = validate_result(
        run(Mode.VERIFY, Context(nix_home=HOME, mode=Mode.VERIFY))
    )
    print(f"{OUTCOME.status.value}: {OUTCOME.evidence or OUTCOME.detail}")
    if OUTCOME.detail and OUTCOME.evidence:
        print(f"  detail: {OUTCOME.detail}")
    sys.exit(exit_code_for(OUTCOME.status))
