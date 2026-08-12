#!/usr/bin/env python3
"""Find figures RESTATED across documents and DERIVED by none of them.

ARC 027 / D2. The defect class, named by ARC 026: the "10 of 13" reflexivity
figure appeared in `sessions/SESSION.md`, `docs/CHECK-DEBT.md` and the arc
brief, and was derived by none of them. **The true figure was 9.** Three
documents agreeing is not evidence; it is one unchecked assertion, copied.

## Why this does NOT start from `checks/derived_claims.json`

`check_derived_claims` compares two or three sources per REGISTERED claim, and
`scripts/tests/independent_claims.py` is the external second source for those.
Both are excellent and both are blind to this class by construction: **the
defect is precisely a number nobody registered.** A sweep that iterates the
registry finds every registered claim in good order and reports a clean sheet
over the numbers that were never entered.

So the enumerator starts from the DOCUMENTS. `figures()` reads prose, extracts
count-shaped tokens, and reports the ones that occur in two or more distinct
files. The registry is then used only to say which of those already have a
home — never to decide what is in scope.

## HISTORY versus CONTROL SURFACE — the line, drawn explicitly

CLAUDE.md directive 6: *append history; never rewrite banked evidence.* A stale
figure in a closed arc's record is not a defect, it is what was measured then.

  * **HISTORY, never edited.** Every `downloads/arc_0*.md`. And, inside any
    document, a figure carried by ARC-qualified narration — *"Audited, ARC 025,
    by AST over the whole suite — 512 test functions"* is a dated record of a
    measurement, and it stays true forever.
  * **CONTROL SURFACE, where a stale figure IS a defect.** A figure a reader
    would act on today, carrying no arc or date qualifier: `CLAUDE.md`,
    `docs/CHECK-DEBT.md` open rows, `docs/nix_check_contract.md` normative
    sections, `docs/CHECK-CONTRACT-AMENDMENTS.md` amendment bodies.

`classify_occurrence` implements exactly that and nothing more. It never edits
anything; the line only decides how a finding is REPORTED.

## What this module adds that prose cannot

`ADJUDICATED` is the answer sheet: every cross-document figure this arc swept,
each with either a **derivation** — a callable that recomputes it from the tree,
right now — or an explicit **debt row id**. `--verify` re-runs every derivation
and reports agreement or disagreement. A figure with neither is a loud error, so
the table cannot quietly acquire an unadjudicated row.

## debug.md §7.12 — what would have to be true for this to report clean while
## measuring nothing?

1. **The extractor could match nothing**, and every document would look
   figure-free. *Closed:* `MIN_CREDIBLE_FIGURES` — a run finding fewer
   cross-document figures than the floor is a refusal, not a clean sheet.
2. **The scope could be empty.** A glob that resolves to no files reports no
   restatements. *Closed:* every path in `SCOPE` is required to exist and a
   missing one is a refusal naming it.
3. **`ADJUDICATED` could be full of derivations that are re-statements.** A
   "derivation" that returns a literal is a restatement wearing a function's
   clothes. *Closed:* every derivation reads the tree, and
   `test_restated_figures.py` asserts the two known-defective figures — the
   ARC 026 census and the ARC 025 test-function count — come back as
   `AGREES` and `DISAGREES` respectively. A table where nothing can disagree is
   not an answer sheet.
4. **The verifier could pass by finding nothing to verify.** *Closed:*
   `verify_all` refuses an empty derivation set.

## The residual, named

The extractor is a regex over prose and it is NOT complete: a figure spelled in
words ("thirteen claims"), split across a line break, or embedded in a table
cell this pattern does not reach is invisible. This narrows the class; it does
not close it. The honest bound is *"these are the cross-document figures this
pattern can see"*, and that is what the report says.
"""

from __future__ import annotations

import argparse
import ast
import collections
import dataclasses
import json
import re
import subprocess  # nosec B404 - fixed argv, shell=False, this repo's own history
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
# The `sys.path` bootstrap above must run BEFORE these imports; that is the
# whole point of it, and it is the shape `checks/_preamble.py` uses for every
# check in this tree.
from nixverify.gitenv import scrubbed_env

# pylint: enable=wrong-import-position

#: The documents swept. Globs are expanded; a literal path that does not exist
#: is a REFUSAL, because a scope that silently shrinks is this project's
#: recurring defect (bandit scanning nothing, pre-commit skipping untracked).
SCOPE: tuple[str, ...] = (
    "sessions/SESSION.md",
    "docs/CHECK-DEBT.md",
    "docs/CHECK-CONTRACT-AMENDMENTS.md",
    "docs/SPEC-AMENDMENTS.md",
    "docs/nix_check_contract.md",
    "downloads/RESULTS.md",
    "downloads/arc_0*.md",
    "CLAUDE.md",
)

#: Documents that are banked history in their entirety. Never a defect; always
#: reported, because a figure's history is how you tell restatement from origin.
HISTORICAL_GLOBS: tuple[str, ...] = ("downloads/arc_0*.md",)

#: Below this the extractor is not credible — these documents are thick with
#: counts, and a handful means the pattern stopped matching. A floor, not
#: today's count (doctrine C.4).
MIN_CREDIBLE_FIGURES = 20

#: A figure is a COUNT or a RATIO of things in this project.
_RATIO = re.compile(r"\b(\d{1,4})\s*(?:/|of|out of)\s*(\d{1,4})\b")
_COUNT = re.compile(
    r"\b(\d{1,5}(?:,\d{3})*)\s+"
    r"(checks?|gates?|rows?|claims?|sources?|bindings?|amendments?|tests?|"
    r"test functions?|findings?|paths?|modules?|files?|objectives?|insertions?|"
    r"hooks?|controls?|elements?|probes?)\b"
)

#: Token shapes that are never a project count: a version, a section reference,
#: a line reference, an ARC number, a debt-row id, an exit code, a port.
#: Every alternative here is exercised by a case in
#: `test_tokens_that_only_look_like_figures_are_excluded`. A date alternative was
#: dropped when no case could be found that it actually suppressed — the same
#: standard D1's normalisation table is held to: a rule nobody can show firing is
#: decoration, and decoration in an exclusion list is where over-matching hides.
_NOISE = re.compile(
    r"(?:v?\d+\.\d+\.\d+)|(?:§\s*\d)|(?:\.md:\d+)|"
    r"(?:\bARC\s*0?\d+\b)|(?:\bD[123]\.\d+\b)|(?:\bexit\s*\d)|(?:\b400\d\b)"
)

#: Narration that dates a figure to a past measurement. An occurrence carrying
#: one of these is HISTORY even inside a live document — see the module
#: docstring. Deliberately narrow: "ARC 025 audited ..." dates a figure;
#: "ARC 025" merely appearing elsewhere on a 400-character ledger row does not.
_DATED = re.compile(
    r"(?:ARC\s*0?\d+[^.]{0,40}?(?:audit|measur|found|report|ran|opened|closed))|"
    r"(?:(?:audit|measur|found|report|ran)[^.]{0,40}?ARC\s*0?\d+)|"
    r"(?:\bas of\b)|(?:\bat the time\b)|(?:MEASURED\s+20\d\d-\d\d-\d\d)",
    re.IGNORECASE,
)


class RefusedError(Exception):
    """The sweep could not be made informative. Always names why."""


@dataclasses.dataclass(frozen=True)
class Occurrence:
    """One figure, at one place, with the class of the surface carrying it."""

    figure: str
    noun: str
    path: str
    line: int
    context: str
    historical: bool

    @property
    def surface(self) -> str:
        """HISTORY or CONTROL-SURFACE. Decides reporting, never editing."""
        return "HISTORY" if self.historical else "CONTROL-SURFACE"


def scope_paths(home: Path) -> list[Path]:
    """Expand `SCOPE`. A literal path that does not exist is a refusal."""
    out: list[Path] = []
    for entry in SCOPE:
        if "*" in entry:
            out.extend(sorted(home.glob(entry)))
            continue
        path = home / entry
        if not path.is_file():
            raise RefusedError(
                f"{entry} is in SCOPE and is not on disk — a sweep whose scope "
                "silently shrinks reports a clean sheet over what it stopped reading"
            )
        out.append(path)
    return out


def _is_historical(home: Path, path: Path) -> bool:
    """True for documents that are banked history in their entirety."""
    relative = path.relative_to(home).as_posix()
    return any(
        path in set(home.glob(g)) for g in HISTORICAL_GLOBS
    ) or relative.startswith("downloads/arc_0")


def classify_occurrence(text: str, whole_file_is_history: bool) -> bool:
    """Is THIS occurrence history? The line the brief asked to be drawn.

    A whole-file historical document is history throughout. Inside a live
    document, an occurrence is history when its own sentence dates the figure to
    a past measurement — and only then. Everything else is a control surface a
    reader would act on today.
    """
    return whole_file_is_history or bool(_DATED.search(text))


def figures(home: Path) -> list[Occurrence]:
    """Every count-shaped token in scope, with its surface class. Never edits."""
    found: list[Occurrence] = []
    for path in scope_paths(home):
        whole = _is_historical(home, path)
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            found.extend(_line_figures(home, path, number, line, whole))
    return found


def _line_figures(
    home: Path, path: Path, number: int, line: str, whole: bool
) -> Iterator[Occurrence]:
    """Figures on one line. Split out so the noise rule is applied in one place."""
    relative = path.relative_to(home).as_posix()
    for match in _RATIO.finditer(line):
        if _noisy(line, match):
            continue
        yield Occurrence(
            figure=f"{match.group(1)}/{match.group(2)}",
            noun="ratio",
            path=relative,
            line=number,
            context=_window(line, match.start()),
            historical=classify_occurrence(line, whole),
        )
    for match in _COUNT.finditer(line):
        if _noisy(line, match):
            continue
        yield Occurrence(
            figure=match.group(1).replace(",", ""),
            noun=_singular(match.group(2)),
            path=relative,
            line=number,
            context=_window(line, match.start()),
            historical=classify_occurrence(line, whole),
        )


#: How far either side of a match the noise rules may look. TIGHT on purpose:
#: the shapes being excluded — `D3.10 binding`, `§13 objective`, `ARC 010/011`,
#: `v1.3.0` — all sit immediately against the number. A wide window would let an
#: `ARC 025` mentioned anywhere on a 400-character ledger row suppress a real
#: figure on the same row, which is a gate quietly narrowing its own scope.
_NOISE_BEFORE, _NOISE_AFTER = 14, 4


def _noisy(line: str, match: re.Match[str]) -> bool:
    """True when a token only LOOKS like a figure: a version, ARC number, §ref."""
    window = line[max(0, match.start() - _NOISE_BEFORE) : match.end() + _NOISE_AFTER]
    return bool(_NOISE.search(match.group(0)) or _NOISE.search(window))


def _singular(noun: str) -> str:
    """Crude but closed: the plural forms this pattern can produce."""
    lowered = noun.lower()
    return (
        lowered[:-1]
        if lowered.endswith("s") and not lowered.endswith("ss")
        else lowered
    )


def _window(line: str, at: int) -> str:
    """120 characters around a match, for a human to adjudicate."""
    return line[max(0, at - 55) : at + 65].strip()


def cross_document(
    occurrences: list[Occurrence],
) -> dict[tuple[str, str], list[Occurrence]]:
    """Group by (figure, noun), keeping only groups spanning 2+ distinct files."""
    grouped: dict[tuple[str, str], list[Occurrence]] = collections.defaultdict(list)
    for one in occurrences:
        grouped[(one.figure, one.noun)].append(one)
    return {
        key: rows
        for key, rows in sorted(grouped.items())
        if len({row.path for row in rows}) >= 2
    }


# ---------------------------------------------------------------------------
# THE ANSWER SHEET — a derivation or a debt row, never neither.
# ---------------------------------------------------------------------------


def _git(home: Path, *args: str) -> str:
    """`git` with every `GIT_*` variable scrubbed (D3.22, gitenv.scrubbed_env)."""
    # nosec B603 B607 - fixed argv, shell=False, no user input. `git` by name and
    # not by absolute path, matching check_canonical_tree/_name_coherence/_hook_suite:
    # pinning a path would report on a binary nothing else in this project uses.
    return subprocess.run(  # nosec B603 B607
        ["git", "-C", str(home), *args],
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_env(),
    ).stdout


#: ARC 024's work landed as one commit. `git diff --shortstat` against its parent
#: is the derivation the ARC 025 brief asked for and nobody wrote back.
ARC024_COMMIT = "45a37fa"


def arc024_paths(home: Path) -> int:
    """`30 paths` — ARC 024's staged-never-committed set, counted from history."""
    return len(
        _git(home, "diff", "--name-only", f"{ARC024_COMMIT}^", ARC024_COMMIT).split()
    )


def arc024_insertions(home: Path) -> int:
    """`5,019 insertions` — from the same commit's shortstat."""
    stat = _git(home, "diff", "--shortstat", f"{ARC024_COMMIT}^", ARC024_COMMIT)
    match = re.search(r"(\d+) insertions?\(\+\)", stat)
    if match is None:
        raise RefusedError(f"could not read insertions from shortstat: {stat!r}")
    return int(match.group(1))


def reflexive_claims(home: Path) -> int:
    """`9 of 13` — claims of `check_derived_claims` whose sources are ALL in-gate.

    Structural, over `derived_claims.json` alone: a source carrying a `probe`
    key is implemented inside the gate and re-entered as `{self} --probe`. This
    never imports the gate, so a defect in the gate cannot move this number —
    which is the whole property the "10 of 13" figure was asserting about.
    """
    payload = json.loads((home / "checks" / "derived_claims.json").read_text("utf-8"))
    return sum(
        1
        for claim in payload["claims"]
        if all("probe" in source for source in claim["sources"])
    )


def registered_claims(home: Path) -> int:
    """`13` — the denominator of the reflexivity census."""
    payload = json.loads((home / "checks" / "derived_claims.json").read_text("utf-8"))
    return len(payload["claims"])


def test_functions(home: Path) -> int:
    """`512 test functions` — ARC 025's AST audit, re-implemented and re-run.

    D2.29 records that the original auditor lived in a scratch directory and was
    deleted at close-out, so the figure has had no source since the day it was
    taken. It is a MOVING figure — it grows with the suite — restated as though
    it were fixed. This is that auditor, committed.
    """
    total = 0
    for path in sorted((home / "scripts" / "tests").glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        total += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        )
    return total


def precommit_hook_invocations(home: Path) -> int:
    """`8` in `8/8` — hook ENTRIES in `.pre-commit-config.yaml`, which is what runs."""
    text = (home / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    return len(re.findall(r"^\s+-\s+id:\s*\S+", text, re.MULTILINE))


def precommit_hook_ids(home: Path) -> int:
    """`7` — DISTINCT hook ids. `bandit` appears twice, aliased `bandit-tests`.

    This is the whole of the `7` versus `8` disagreement across the documents:
    both numbers are true of different denominators and no document says which
    it means. Neither figure was wrong; the noun was.
    """
    text = (home / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    return len(set(re.findall(r"^\s+-\s+id:\s*(\S+)", text, re.MULTILINE)))


@dataclasses.dataclass(frozen=True)
class Adjudication:
    """One swept figure's disposition: a derivation, or a debt row. Never neither."""

    figure: str
    what: str
    #: Recomputes the figure from the tree, right now. `None` only with `debt`.
    derivation: Callable[[Path], int] | None = None
    #: The value the documents state. Compared against the derivation.
    stated: int | None = None
    #: The debt row id owning this figure when no derivation exists.
    debt: str = ""
    #: Why the figure is what it is, for a reader who finds it in a document.
    note: str = ""

    def __post_init__(self) -> None:
        if self.derivation is None and not self.debt:
            raise RefusedError(
                f"{self.figure}: adjudicated with neither a derivation nor a debt "
                "row — that is the defect this module exists to find, in this "
                "module's own table"
            )


ADJUDICATED: tuple[Adjudication, ...] = (
    Adjudication(
        figure="30 paths",
        what="ARC 024's staged-never-committed set (CLAUDE.md, CCA, contract x2)",
        derivation=arc024_paths,
        stated=30,
        note=(
            "The ARC 025 brief asked to 'confirm the number and the membership' and "
            "nothing wrote back. Confirmed here: git diff --name-only 45a37fa^ "
            "45a37fa. The figure is TRUE and was, until now, restated by four "
            "surfaces and derived by none."
        ),
    ),
    Adjudication(
        figure="5,019 insertions",
        what="the same commit's insertion count",
        derivation=arc024_insertions,
        stated=5019,
        note="git diff --shortstat 45a37fa^ 45a37fa.",
    ),
    Adjudication(
        figure="9 of 13",
        what="check_derived_claims claims with BOTH sources inside the gate",
        derivation=reflexive_claims,
        stated=9,
        note=(
            "ARC 026's correction to the restated '10 of 13' had itself never been "
            "derived — it was stated in RESULTS.md and SESSION.md and computed by "
            "nothing, which is the same epistemic status the 10 had. Derived here "
            "structurally, without importing the gate."
        ),
    ),
    Adjudication(
        figure="13 claims",
        what="the reflexivity census denominator",
        derivation=registered_claims,
        stated=13,
        note="len(derived_claims.json['claims']).",
    ),
    Adjudication(
        figure="512 test functions",
        what="ARC 025's §18 AST audit population (contract §18 x2, D2.29 x2, SESSION)",
        derivation=test_functions,
        stated=512,
        debt="D2.39",
        note=(
            "EXPECTED TO DISAGREE. 512 was true when ARC 025 measured it; the "
            "suite has grown since and the auditor was deleted at close-out "
            "(D2.29). The figure is banked history where it is narrated as ARC "
            "025's measurement, and a moving anchor wherever it is restated "
            "without that qualifier. This is the auditor, committed."
        ),
    ),
    Adjudication(
        figure="8 hooks",
        what="pre-commit hook ENTRIES — the denominator of the '8/8' banner",
        derivation=precommit_hook_invocations,
        stated=8,
        note="Hook entries in .pre-commit-config.yaml; this is what pre-commit runs.",
    ),
    Adjudication(
        figure="7 hooks",
        what="DISTINCT pre-commit hook ids",
        derivation=precommit_hook_ids,
        stated=7,
        debt="D2.40",
        note=(
            "Both 7 and 8 are true and the documents disagree because they mean "
            "different nouns: bandit is entered twice (production, and tests via "
            "alias bandit-tests). No surface says which it means."
        ),
    ),
    Adjudication(
        figure="76 modules",
        what="modules permanently added to sys.modules by a check import (D2.32, SESSION)",
        stated=76,
        debt="D2.41",
        note=(
            "Stated in a live ledger row and a session summary, computed by "
            "nothing. It is a property of ONE interpreter's import graph at one "
            "moment; no committed instrument recomputes it."
        ),
    ),
    Adjudication(
        figure="27 of 27",
        what="files bandit skipped while exiting 0 (contract, CHECK-DEBT, SESSION)",
        stated=27,
        debt="D2.41",
        note=(
            "ARC 010's measurement of a defect that was REPAIRED in the same arc. "
            "Banked history everywhere it appears; recomputing it today would "
            "measure the repaired hook, not the historical one. Recorded, not owed."
        ),
    ),
    Adjudication(
        figure="7 of 10",
        what="hostile-GIT_DIR decoy tests naming the scrub (D3.22 row, RESULTS)",
        stated=7,
        debt="D2.41",
        note=(
            "Live debt row plus results, derived by neither. "
            "scripts/tests/test_gitenv_hostile.py is the subject and no committed "
            "instrument counts it."
        ),
    ),
)


@dataclasses.dataclass(frozen=True)
class Verification:
    """One adjudicated figure, re-derived."""

    figure: str
    stated: int | None
    derived: int | None
    error: str = ""

    @property
    def verdict(self) -> str:
        """AGREES / DISAGREES / DEBT-ONLY / ERROR — never a bare boolean."""
        if self.error:
            return "ERROR"
        if self.derived is None:
            return "DEBT-ONLY"
        return "AGREES" if self.derived == self.stated else "DISAGREES"


def verify_all(home: Path) -> list[Verification]:
    """Re-derive every adjudicated figure that has a derivation."""
    derivable = [row for row in ADJUDICATED if row.derivation is not None]
    if not derivable:
        raise RefusedError(
            "no adjudicated figure carries a derivation — a verifier with nothing "
            "to verify passes by measuring nothing"
        )
    out: list[Verification] = []
    for row in ADJUDICATED:
        if row.derivation is None:
            out.append(Verification(row.figure, row.stated, None))
            continue
        try:
            out.append(Verification(row.figure, row.stated, row.derivation(home)))
        except Exception as exc:  # noqa: BLE001 pylint: disable=broad-exception-caught
            out.append(Verification(row.figure, row.stated, None, error=repr(exc)))
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Sweep the documents, then re-derive the answer sheet."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--home", default=str(REPO))
    parser.add_argument(
        "--sweep", action="store_true", help="list cross-document figures"
    )
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args(argv)
    home = Path(args.home).resolve()

    try:
        occurrences = figures(home)
        groups = cross_document(occurrences)
        if len(groups) < MIN_CREDIBLE_FIGURES:
            raise RefusedError(
                f"{len(groups)} cross-document figure(s) found, below the floor of "
                f"{MIN_CREDIBLE_FIGURES} — these documents are thick with counts, so "
                "that is the signature of an extractor that stopped matching"
            )
        verifications = verify_all(home)
    except RefusedError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    if args.sweep:
        render_sweep(groups, len(occurrences), args.limit)
    return render_adjudication(verifications)


def render_sweep(
    groups: dict[tuple[str, str], list[Occurrence]], total: int, limit: int
) -> None:
    """List the cross-document figures, most-restated first."""
    print(f"\nCROSS-DOCUMENT FIGURES ({len(groups)} groups, {total} occurrences)")
    ranked = sorted(groups.items(), key=lambda kv: -len({r.path for r in kv[1]}))
    for (figure, noun), rows in ranked[:limit]:
        surfaces = sorted({row.surface for row in rows})
        files = len({row.path for row in rows})
        print(f"\n  {figure} {noun}  — {files} files, {surfaces}")
        for row in rows[:6]:
            print(f"      {row.path}:{row.line} [{row.surface}] {row.context[:96]}")


def render_adjudication(verifications: list[Verification]) -> int:
    """Print the answer sheet and return the exit code.

    An ADJUDICATED disagreement is a finding a debt row already owns, and
    reddening on it forever would make the honest disposition the noisy one. An
    UNADJUDICATED disagreement is exactly this module's subject, and is red.
    """
    print("\nADJUDICATION — every swept figure has a derivation or a debt row")
    print(f"  {'figure':<22} {'verdict':<11} {'stated':>8} {'derived':>8}  disposition")
    print("  " + "-" * 96)
    by_figure = {row.figure: row for row in ADJUDICATED}
    worst = 0
    for check in verifications:
        owner = by_figure[check.figure]
        derived = "-" if check.derived is None else str(check.derived)
        print(
            f"  {check.figure:<22} {check.verdict:<11} {check.stated!s:>8} "
            f"{derived:>8}  {owner.debt or 'derived'}"
        )
        if check.verdict == "ERROR":
            worst = max(worst, 2)
            print(f"      ERROR {check.error}")
        elif check.verdict == "DISAGREES":
            worst = max(worst, 0 if owner.debt else 1)
            print(f"      {owner.note}")
    return worst


if __name__ == "__main__":
    sys.exit(main())
