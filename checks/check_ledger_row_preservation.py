#!/usr/bin/env python3
# R0801 pairs this file's DECLARATION BLOCK and its `standalone_main` footer
# against every other house-style check's. That shape is REQUIRED, not
# accidental duplication (§4.2).
# R0914/R0911: `historical_ids` carries the git plumbing's intermediate names
# (commits, oids, per-commit, per-blob, union, last_seen) and `analyse` returns
# one CANNOT_MEASURE per §7.12 door it closes. Collapsing either would merge
# doors that must stay separately named — the whole point of the docstring below.
# C0116: `run` is the check contract's entry point and its behaviour is the
# module docstring; a docstring here would restate it (directive 3).
# pylint: disable=duplicate-code,too-many-locals,too-many-return-statements
# pylint: disable=missing-function-docstring
"""D3.272 — a `docs/CHECK-DEBT.md` row that has EVER existed is still there.

ARC 037 / sub-agent F.

## THE DEFECT THIS EXISTS FOR, MEASURED TWICE BEFORE THIS FILE WAS WRITTEN

**Instance one, ARC 036 Stage 2.** The integrator resolved `docs/CHECK-DEBT.md`
across five branches with a resolver that took OURS for any hunk containing the
arc's series row. On three of the five merges that row and that branch's NEW
rows were inside one hunk, so `D3.240`-`D3.245`, `D3.250`-`D3.253` and
`D3.260`-`D3.264` were discarded with it — **fifteen findings, gone, and every
gate green.** `check_derived_claims` compares `derived:ledger_rows` against the
figure the series table states, and BOTH moved together: deleting rows and
re-deriving the count produces a perfectly consistent smaller ledger. That gate
can only catch a stale FIGURE. It is structurally blind to a lost ROW.

Reproduced on trunk before this gate was written, so this is built against a
measurement and not against the story: deleting `D3.260`, `D3.261` and `D3.262`
from the ledger and resyncing the series row gives `derived ledger_rows = 247`,
`stated series = 247`, **AGREE = True**, `check_derived_claims` PASS.

**Instance two, found BY THIS GATE on its first run over the real history.**
`D1.8` (Xvfb `:99` display persistence) and `D1.9` (IB Gateway process
persistence) were **deleted outright** from the ledger by ARC 011 when
`check_ibgateway_service` discharged them, rather than being marked discharged
in place. They were last present at commit `da28f4c` and absent from `67c8ad9`
onward — a silent two-row loss that stood for twenty-six arcs and that nothing
in this tree could see. `CLAUDE.md` directive 6 is *append history; never
rewrite banked evidence*, and a discharged row is banked evidence. Both rows
were recovered from `git show da28f4c:docs/CHECK-DEBT.md` and re-appended in
their numeric position, marked `**discharged ARC 011**` so the open count is
unchanged. That recovery is ARC 037's, and the finding is this gate's.

## THE PROPERTY, AND WHY IT IS A SET AND NOT A COUNT

The ledger is append-only by directive 6. So the property is a **one-way ratchet
over the SET OF IDS**, never over their number:

> every `D<n>.<m>` id that appears in ANY committed revision of
> `docs/CHECK-DEBT.md` reachable from `HEAD` must appear in the working ledger.

A count cannot express it. Fifteen deletions plus fifteen additions is a count
that never moved; fifteen deletions plus a resynced figure is two numbers that
agree about a ledger that lost its findings.

## THE COMPARISON SET IS THE REPOSITORY'S OWN HISTORY. THERE IS NO BASELINE FILE

Deliberate, and it is the single most important decision in this file. A
baseline JSON listing "the ids that must exist" would be regenerated from the
current ledger by the first arc that hit a red — which is the defect wearing the
instrument's clothes. The comparison set here is **committed git objects**:
every commit reachable from `HEAD`, its blob for the ledger path, and the union
of the ids in every one of them. **The working-tree edit under judgement cannot
reach any of it.** That is the same reasoning `check_artifact_gate_coverage`
uses for its ratchet's high-water mark, applied to a document instead of to a
gate roster.

`git rev-list HEAD` is used rather than `git log -- <path>` **because history
simplification is exactly the enemy here**: `git log -- <path>` prunes side
branches whose changes did not survive a merge, which is a precise description
of the fifteen rows D3.272 records. Every reachable commit is asked, the blob
oids are de-duplicated (335 commits collapse to 99 distinct ledger blobs on this
tree), and the union is taken over the distinct blobs.

## debug.md §7.12 — WHAT WOULD HAVE TO BE TRUE FOR THIS GATE TO BE **GREEN WHILE
## A ROW IS MISSING**?

This is the nasty version of the standing question, because the gate's subject
is an absence. Each door is named and then driven shut.

 1. **A BASELINE REGENERATED FROM THE CURRENT FILE.** The classic. If the "must
    exist" set is rebuilt from the ledger as it stands, a deletion updates the
    evidence and the finding, together, and the gate agrees with the loss the
    way `check_derived_claims` did.
    *CLOSED BY CONSTRUCTION:* there is no baseline file, `CORRECTABLE = False`,
    `INSTALLABLE = False`, and this module contains no write path of any kind.
    The evidence set is committed git objects only.

 2. **COMPARING AGAINST `HEAD` WHEN THE LOSS IS ALREADY COMMITTED.** A
    working-tree-vs-`HEAD` diff sees nothing the moment the deletion is
    committed — and in the D3.272 case the deletion WAS committed, by the merge
    itself.
    *CLOSED:* the union spans every commit reachable from `HEAD`, not `HEAD`.
    A committed deletion still reddens, because the ids survive in an ancestor
    blob. Verified by plant: deleting a row, `git add -A`, `git commit`, and
    re-running still names the id.

 3. **A `git` CALL THAT FAILS AND IS READ AS "NOTHING TO COMPARE".** An empty
    `rev-list`, a `cat-file` that dies, `git` absent, not a repository, a
    detached or corrupt object store — every one of them yields an empty
    historical set, and an empty historical set has nothing missing from it.
    *CLOSED:* every git invocation's exit status is checked and any failure is
    `CANNOT_MEASURE` (exit 2) naming the argv and the stderr — **never PASS**.
    On top of that, `MIN_REVISIONS` and `MIN_UNION_IDS` floors make a
    suspiciously small history or union `CANNOT_MEASURE` as well. The floors are
    anchored an order below the observed figures (99 blobs, 301 ids) and are NOT
    set to today's numbers, which would be a moving anchor (`debug.md` §7.4).

 4. **ONE REGEX ON BOTH SIDES.** The deep one. Both the historical ids and the
    working ids come from the same row grammar, so a grammar that stops matching
    — a column added, the pipe style changed, an id renumbered `D4.x` — drops
    ids from BOTH sides equally and the difference stays empty. The gate would
    be green having compared nothing to nothing.
    *CLOSED THREE WAYS:*
      a. **A PLANTED DELETION IS DRIVEN ON EVERY RUN, IN MEMORY, AGAINST THE
         REAL LEDGER TEXT.** `_self_control` removes one real row from a copy of
         the live text, re-extracts, and REQUIRES the comparison to report
         exactly that id and to name it in the message. An extractor that has
         stopped matching produces no ids and therefore no named finding, and
         the self-control fails — `CANNOT_MEASURE`, never PASS. The instrument
         proves it can still fail, on this tree, on this run, before its verdict
         is read (doctrine C.6 / check contract §18: assert the REASON).
      b. **A NO-DEFECT CONTROL** runs beside it: an unmodified copy must report
         NOTHING missing. Without it, an extractor that returned a constant
         non-empty set would pass (a) and be equally broken.
      c. **A SECOND, LOOSER EXTRACTOR** reads the working ledger with a
         deliberately different rule (any `D<digits>.<digits>` in a leading table
         cell, no major-number restriction) and any id it finds that the strict
         rule missed is a FAIL naming it. That is grammar drift caught at the
         moment it happens rather than one arc later.

 5. **A DELETION THAT NEVER REACHED A COMMIT AT ALL.** Rows written and lost
    inside one uncommitted working session are invisible to every mechanism
    here, because git never saw them.
    *NOT CLOSED, AND NOT CLOSABLE FROM HERE.* Stated rather than papered over.
    The mitigation is procedural and it is `CLAUDE.md`'s own: `git add -A`
    before every gate measurement, and an arc is not durable until `HEAD`
    advanced. This gate is strictly stronger the more often the tree is
    committed, which is the right direction for a ratchet to lean.

 6. **A HISTORY REWRITE.** `rebase`, `filter-branch`, an amended merge, a
    shallow clone — any of them can make an ancestor blob unreachable, and an id
    that is unreachable was never in the union.
    *NARROWED, NOT CLOSED.* The `MIN_REVISIONS` floor catches the gross case (a
    shallow or truncated history is `CANNOT_MEASURE`), and the evidence prints
    the number of distinct ledger revisions unioned on every run, so a history
    that collapses from 99 revisions to 4 is READABLE rather than inferred. A
    rewrite that removes exactly one ancestor and leaves the rest is beyond
    this instrument and is named here instead of being claimed.

 7. **A ROW KEPT BY ID AND EMPTIED OF CONTENT.** The ratchet is over ids; an id
    whose row body was gutted still satisfies it.
    *NARROWED:* every preserved row is required to carry at least
    `MIN_ROW_CHARS` characters, which is far below any real row on this tree
    (the shortest is over 90) and far above an id-only stub. A row hollowed to
    half its prose still passes, and that is stated rather than claimed.

 8. **SIBLING BRANCHES.** Only history reachable from `HEAD` is judged, so a row
    living on an unmerged branch is not required to be present.
    *DELIBERATE, AND IT IS THE ONLY CORRECT CHOICE.* Six sub-agent worktrees
    share one object store; requiring every branch's rows in every branch would
    redden all six on day one and the gate would be turned off. The obligation
    lands at the merge instead, which is precisely where D3.272's loss happened:
    the moment the merge commit exists, both parents are reachable and every one
    of their ids is required. Named here because a reader must not mistake this
    gate for one that can police an in-flight branch.

 9. **THE GATE COULD JUDGE A DIFFERENT REPOSITORY.** `git` honours `GIT_DIR`,
    `GIT_WORK_TREE` and `GIT_INDEX_FILE` ahead of `-C` (D3.22/D3.205), and this
    gate runs under `pre-commit`, which exports them.
    *CLOSED:* every subprocess here goes through `nixverify.gitenv.scrubbed_env`,
    and the gate resolves `git rev-parse --show-toplevel` and REPORTS the
    repository it actually measured in its evidence. A toplevel that is not the
    `nix_home` under measurement is `CANNOT_MEASURE`.

10. **A LEGITIMATE REMOVAL COULD BE NEEDED AND THERE IS NO ESCAPE HATCH.**
    Correct: there is none, on purpose. An exemption list is a suppression list
    with better manners, and this gate exists because a suppression happened by
    accident. If an authorised removal is ever genuinely required it takes an
    architect ruling recorded as a `CHECK-A<n>` amendment, the same bar
    `check_artifact_gate_coverage`'s exclusions carry — and it is a change to
    THIS file, in review, not a row added to a JSON nobody reads.

NON-CORRECTABLE. The only mechanical "correction" would be to write rows back
into the ledger from history — an instrument editing the evidence ledger to make
itself green, which is the worst artifact this arc could produce. The repair is
a human restoring the row WITH the account of how it was lost, which is what
ARC 037 did for `D1.8`/`D1.9` and ARC 036 did for the fifteen.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404 - fixed argv, shell=False, scrubbed environment
import sys
from pathlib import Path
from typing import NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status
from nixverify.gitenv import scrubbed_env

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: Nothing must run first. This gate reads one tracked document and the git
#: object store, and produces no artifact any other check consumes.
DEPENDS_ON: tuple[str, ...] = ()
#: `git` is SPAWNED three times (`rev-parse`, `rev-list`, `cat-file` twice).
#: Nothing is written anywhere: there is no temporary directory, no baseline,
#: and no write path in this module at all — see §7.12 door 1.
RESOURCES: tuple[str, ...] = ("subprocess:git",)
#: FALSE on the facts: three git invocations over an object store, measured at
#: 0.32 s wall for 335 commits / 99 distinct ledger blobs on this node.
TIME_BOUND = False
EXPECTED_S = 20.0
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the only mechanical correction is for this instrument to write rows back "
    "into `docs/CHECK-DEBT.md` out of git history — an instrument editing the "
    "evidence ledger to make itself green. A lost row is lost WITH a reason "
    "(a merge resolution, a discharge that deleted instead of marking), and "
    "the repair is a human restoring the row together with the account of how "
    "it went missing, which is what ARC 036 did for fifteen rows and ARC 037 "
    "did for D1.8/D1.9. An automated restore would erase exactly that account."
)
INSTALLABLE = False
#: CONTINUE. A lost ledger row is a serious finding and it stops nothing else
#: from being measured; halting the run would cost the operator every other
#: verdict to report a document defect.
ON_FAIL = "continue"
#: The artifact this gate MEASURES, for `check_artifact_gate_coverage`.
SUBJECTS: tuple[str, ...] = ("docs/CHECK-DEBT.md",)

NAME = "check_ledger_row_preservation"

#: The ledger, one spelling, used identically for the git query and the disk
#: read so the two sides cannot end up looking at different documents.
LEDGER = "docs/CHECK-DEBT.md"

#: THE ROW GRAMMAR. A debt row is a markdown table row whose FIRST cell is the
#: id and nothing else. Deliberately anchored to the leading pipe: the ledger
#: cites other rows in prose constantly ("see D3.2", "the same class as D3.213")
#: and a loose scan would manufacture ids that were never rows.
_ROW = re.compile(r"^\|\s*(D[123]\.\d+)\s*\|", re.MULTILINE)

#: THE SECOND, LOOSER GRAMMAR — §7.12 door 4c. Same anchor, no restriction on
#: the major number and a tolerant separator. Anything it finds that `_ROW`
#: missed is grammar drift, and grammar drift is what makes one regex on both
#: sides a silent no-op.
_ROW_LOOSE = re.compile(r"^\|\s*(D\d+\.\d+)\s*[|:]", re.MULTILINE)

#: The whole row line, for the hollowed-row control (§7.12 door 7).
_ROW_LINE = re.compile(r"^\|\s*(D[123]\.\d+)\s*\|.*$", re.MULTILINE)

#: FLOORS. Observed on this tree when the gate was written: 335 reachable
#: commits, 99 distinct ledger blobs, 301 ids in the union, shortest row 90+
#: characters. Every floor is an order of magnitude below its observation and
#: NONE is set to today's figure — a threshold equal to the current number is a
#: moving anchor (`debug.md` §7.4) and would redden on the next commit.
MIN_REVISIONS = 20
MIN_UNION_IDS = 120
MIN_ROW_CHARS = 40

#: The floor the SELF-CONTROL uses, and it is deliberately much lower than
#: `MIN_UNION_IDS`. The self-control asks *can this extractor still see rows at
#: all* — a question about the INSTRUMENT. `MIN_UNION_IDS` asks whether the
#: HISTORY is credible, which is a question about the evidence and can never
#: legitimately shrink. Tying the two together was the first spelling and it was
#: wrong in the direction that matters: a ledger gutted from 301 rows to 100
#: would have been CANNOT_MEASURE ("the extractor lost the document") when the
#: honest answer is FAIL naming two hundred missing ids. Never a PASS either
#: way, but the weaker verdict is the wrong one to report about a real loss.
MIN_SELF_CONTROL_IDS = 5


class Finding(NamedTuple):
    """One defect, with the site and the REASON (check contract §18)."""

    site: str
    why: str


class GitError(RuntimeError):
    """A git invocation could not answer. NEVER read as 'nothing to compare'."""


def _git(home: Path, *args: str, stdin: bytes | None = None) -> bytes:
    """One git invocation on a SCRUBBED environment (D3.22 / D3.205).

    Any failure raises. The caller turns that into CANNOT_MEASURE — §7.12 door
    3 is the whole reason this helper has no "return empty on error" path.
    """
    argv = ["git", "-C", str(home), *args]
    try:
        proc = subprocess.run(  # nosec B603 - literal argv, no shell, scrubbed env
            argv,
            input=stdin,
            capture_output=True,
            check=False,
            timeout=EXPECTED_S,
            env=scrubbed_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitError(f"{' '.join(argv)}: did not run: {exc!r}") from exc
    if proc.returncode != 0:
        raise GitError(
            f"{' '.join(argv)}: exit {proc.returncode}: "
            f"{proc.stderr.decode('utf-8', 'replace').strip()[:300]}"
        )
    return proc.stdout


def strict_ids(text: str) -> set[str]:
    """Ids that are the first cell of a ledger table row."""
    return set(_ROW.findall(text))


def loose_ids(text: str) -> set[str]:
    """Ids under the second, independent grammar (§7.12 door 4c)."""
    return set(_ROW_LOOSE.findall(text))


def missing_ids(historical: set[str], working: set[str]) -> list[str]:
    """Ids that history holds and the working ledger does not. Sorted, stable."""
    return sorted(
        historical - working,
        key=lambda name: (name.split(".")[0], int(name.split(".")[1])),
    )


def _self_control(text: str) -> str:
    """Drive a PLANTED DELETION through the real comparison. Returns an error.

    §7.12 door 4a and 4b, executed on EVERY run against the LIVE ledger text —
    not against a fixture, because a fixture proves the extractor still parses
    the fixture. Two arms:

      * **the plant** — one real row removed from a copy; the comparison must
        report EXACTLY that id, and the id must appear in the rendered reason.
      * **the control** — an untouched copy; the comparison must report NOTHING.

    An extractor that has stopped matching the ledger's grammar yields no ids,
    so the plant reports nothing missing and this returns an error. An extractor
    that returns a constant non-empty set passes the plant and fails the control.
    Both arms must hold or the gate is CANNOT_MEASURE.
    """
    baseline = strict_ids(text)
    if len(baseline) < MIN_SELF_CONTROL_IDS:
        return (
            f"self-control: the row grammar extracted only {len(baseline)} id(s) "
            f"from the live ledger, below the {MIN_SELF_CONTROL_IDS} floor — the "
            "extractor has lost the document and every comparison below would "
            "be empty-against-empty"
        )
    victim = max(baseline, key=lambda n: (n.split(".")[0], int(n.split(".")[1])))
    doctored = _ROW_LINE.sub(
        lambda m: "" if m.group(1) == victim else m.group(0), text, count=0
    )
    planted = missing_ids(baseline, strict_ids(doctored))
    if planted != [victim]:
        return (
            f"self-control: a planted deletion of {victim} produced "
            f"{planted!r} instead of ['{victim}'] — the comparison cannot name "
            "a row it has lost, so a green from it would mean nothing"
        )
    rendered = _refusal(planted, {victim: "PLANT"})
    if victim not in rendered:
        return (
            f"self-control: the refusal text for a deleted {victim} does not "
            f"contain the id ({rendered[:160]!r}) — check contract §18 requires "
            "the REASON, and 'a row is missing' is not one"
        )
    clean = missing_ids(baseline, strict_ids(text))
    if clean:
        return (
            f"self-control: an UNMODIFIED copy of the ledger reported "
            f"{clean[:6]!r} missing — the comparison manufactures findings and "
            "its reds are worth as little as its greens"
        )
    return ""


def _refusal(missing: list[str], last_seen: dict[str, str]) -> str:
    """THE REFUSAL, and it NAMES THE D-NUMBER. Never 'a row is missing'."""
    parts = [
        f"{name} (last present at {last_seen.get(name, 'unknown')})" for name in missing
    ]
    return (
        f"{len(missing)} ledger row(s) present in committed history and ABSENT "
        f"from the working {LEDGER}: " + "; ".join(parts) + ". `CLAUDE.md` "
        "directive 6 makes the ledger append-only: a discharged row is marked "
        "in place with a bold `discharged ARC <n>` span, never deleted. Restore "
        "each row from the revision named beside it (`git show "
        f"<rev>:{LEDGER}`) together with the account of how it was lost — "
        "D3.272 is the record of fifteen rows going this way inside one merge "
        "resolution while every gate stayed green"
    )


class History(NamedTuple):
    """The union over committed history, with what it took to build it."""

    ids: set[str]
    last_seen: dict[str, str]
    revisions: int
    commits: int
    toplevel: str


def historical_ids(home: Path) -> History:
    """Every id in every reachable committed revision of the ledger.

    `git rev-list HEAD` and NOT `git log -- <path>`: log applies history
    simplification and prunes side branches whose changes did not survive a
    merge, which is a precise description of the fifteen rows D3.272 records.
    Blob oids are de-duplicated before they are read, so 335 commits cost 99
    blob reads on this tree and the whole sweep is one `cat-file --batch`.
    """
    toplevel = _git(home, "rev-parse", "--show-toplevel").decode().strip()
    commits = _git(home, "rev-list", "HEAD").decode().split()
    if not commits:
        raise GitError("`git rev-list HEAD` named no commit — there is no history")
    spec = "".join(f"{sha}:{LEDGER}\n" for sha in commits).encode()
    checked = _git(home, "cat-file", "--batch-check", stdin=spec).decode().splitlines()
    if len(checked) != len(commits):
        raise GitError(
            f"`cat-file --batch-check` answered {len(checked)} of "
            f"{len(commits)} requests — the object store did not answer in full"
        )
    #: commit -> blob oid, in rev-list order (newest first), skipping revisions
    #: predating the ledger (git answers `<spec> missing` for those).
    per_commit: list[tuple[str, str]] = []
    for sha, line in zip(commits, checked, strict=True):
        fields = line.split()
        if len(fields) == 3 and fields[1] == "blob":
            per_commit.append((sha, fields[0]))
    oids = sorted({oid for _sha, oid in per_commit})
    if not oids:
        raise GitError(
            f"no commit reachable from HEAD holds {LEDGER} — the path is wrong, "
            "or this is not the repository the ledger lives in"
        )
    blobs = _read_blobs(home, oids)
    per_blob = {oid: strict_ids(text) for oid, text in blobs.items()}
    union: set[str] = set()
    last_seen: dict[str, str] = {}
    for sha, oid in per_commit:  # newest first
        for name in per_blob.get(oid, ()):
            union.add(name)
            last_seen.setdefault(name, sha[:12])
    return History(union, last_seen, len(oids), len(commits), toplevel)


def _read_blobs(home: Path, oids: list[str]) -> dict[str, str]:
    """`cat-file --batch` over de-duplicated oids. Bytes, because sizes are bytes.

    The header is `<oid> blob <size>\\n`, then exactly `<size>` BYTES, then a
    newline. Decoding before slicing would be wrong the moment the ledger holds
    a `§` or an em dash, which it does on nearly every row — the first draft of
    this parser did exactly that and desynchronised on the first blob.
    """
    raw = _git(
        home, "cat-file", "--batch", stdin="".join(o + "\n" for o in oids).encode()
    )
    out: dict[str, str] = {}
    pos = 0
    while pos < len(raw):
        end = raw.find(b"\n", pos)
        if end < 0:
            raise GitError("`cat-file --batch` output ended mid-header")
        fields = raw[pos:end].split()
        if len(fields) != 3 or fields[1] != b"blob":
            raise GitError(
                f"`cat-file --batch` header is not a blob: {raw[pos:end][:120]!r}"
            )
        size = int(fields[2])
        out[fields[0].decode()] = raw[end + 1 : end + 1 + size].decode(
            "utf-8", "replace"
        )
        pos = end + 1 + size + 1
    if len(out) != len(oids):
        raise GitError(f"`cat-file --batch` returned {len(out)} of {len(oids)} blobs")
    return out


def grammar_defects(text: str) -> list[Finding]:
    """§7.12 door 4c — an id the strict grammar cannot see, and hollow rows."""
    out: list[Finding] = []
    strict = strict_ids(text)
    for name in sorted(loose_ids(text) - strict):
        out.append(
            Finding(
                f"{LEDGER}:{name}",
                (
                    f"{name} sits in a leading table cell that the ROW GRAMMAR "
                    "does not match. Both sides of this gate's comparison use "
                    "that grammar, so an id it cannot see is invisible in "
                    "history AND in the working file — the two agree about "
                    "nothing and the gate goes green. Widen `_ROW` or fix the row"
                ),
            )
        )
    for match in _ROW_LINE.finditer(text):
        if len(match.group(0)) < MIN_ROW_CHARS:
            out.append(
                Finding(
                    f"{LEDGER}:{match.group(1)}",
                    (
                        f"the row is {len(match.group(0))} characters, under the "
                        f"{MIN_ROW_CHARS} floor — the id survives and the finding "
                        "does not, which satisfies an id ratchet while losing "
                        "exactly what the ledger is for"
                    ),
                )
            )
    return out


def analyse(home: Path) -> tuple[list[Finding], History, str]:
    """(findings, history, blocker). A non-empty blocker is CANNOT_MEASURE."""
    ledger = home / LEDGER
    if not ledger.is_file():
        return [], History(set(), {}, 0, 0, ""), f"{LEDGER} is absent (§17)"
    text = ledger.read_text(encoding="utf-8")

    blocker = _self_control(text)
    if blocker:
        return [], History(set(), {}, 0, 0, ""), blocker

    try:
        history = historical_ids(home)
    except GitError as exc:
        return [], History(set(), {}, 0, 0, ""), f"git could not answer: {exc}"

    if Path(history.toplevel).resolve() != home.resolve():
        return (
            [],
            history,
            (
                f"git answered for {history.toplevel!r}, not {str(home)!r} — the "
                "history unioned is not this ledger's history (D3.22)"
            ),
        )
    if history.revisions < MIN_REVISIONS:
        return (
            [],
            history,
            (
                f"only {history.revisions} distinct committed revision(s) of "
                f"{LEDGER} are reachable, below the {MIN_REVISIONS} floor — a "
                "truncated or rewritten history has nothing to ratchet against"
            ),
        )
    if len(history.ids) < MIN_UNION_IDS:
        return (
            [],
            history,
            (
                f"the historical union holds {len(history.ids)} id(s), below the "
                f"{MIN_UNION_IDS} floor — the extraction has lost the document"
            ),
        )

    working = strict_ids(text)
    findings: list[Finding] = []
    lost = missing_ids(history.ids, working)
    if lost:
        findings.append(
            Finding(f"{LEDGER}:{','.join(lost)}", _refusal(lost, history.last_seen))
        )
    findings += grammar_defects(text)
    return findings, history, ""


def _evidence(history: History, working: int) -> str:
    return (
        f"{LEDGER}: {working} row id(s) in the working file against a union of "
        f"{len(history.ids)} id(s) taken from {history.revisions} distinct "
        f"committed revision(s) across {history.commits} commit(s) reachable "
        f"from HEAD in {history.toplevel} (git env scrubbed, D3.205). The "
        "comparison set is committed git objects and there is NO baseline file, "
        "so the edit under judgement cannot reach it. A planted deletion and a "
        "no-defect control were driven through the real comparison this run and "
        "both held. LIMITS: a loss that never reached a commit is invisible "
        "here, and only history reachable from HEAD is judged — a sibling "
        "branch's rows become obligatory at the merge, not before."
    )


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    try:
        findings, history, blocker = analyse(ctx.nix_home)
        if blocker:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site=LEDGER,
                detail=blocker,
            )
        working = len(strict_ids((ctx.nix_home / LEDGER).read_text(encoding="utf-8")))
        evidence = _evidence(history, working)
        if findings:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(f.site for f in findings),
                evidence=evidence,
                detail="; ".join(f"{f.site}: {f.why}" for f in findings),
            )
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
