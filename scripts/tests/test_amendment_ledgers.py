"""ARC 028 / 0.4 — the amendment ledgers cannot collide with each other again.

**The defect this closes was real and it was caught by a human reading two files.**
`SPEC-AMENDMENTS.md` issued ARC 022's `AMENDMENT 5 (D1.38)` and per-channel
freshness both as *AMENDMENT 5*, inside one document. Separately, a bare
"AMENDMENT 6" named two different rulings, because this project keeps **two**
ledgers that each number from 1 and each hold six entries. Nothing on disk could
tell any of them apart.

The architect's ruling was two mechanisms, and this module is the mechanism half:

  * **A LEDGER PREFIX.** `SPEC-A<n>` and `CHECK-A<n>`. The number is unchanged and
    nothing was renumbered — the prefix disambiguates the citation, it does not
    restate the entry.
  * **A UNIQUENESS GATE INSIDE EACH LEDGER.** A number may appear once as an
    amendment heading in its own ledger. This is the arm that would have caught
    the original defect on the commit that introduced it.

WHY A TEST AND NOT A `checks/check_*.py`. The subject is two markdown records,
read statically, with no runtime state and no node dependency — there is nothing
for `verify.py` to actuate, correct, or install, and a check that can only ever
read two files duplicates what the suite already does more cheaply. The coverage
ratchet's question ("does any check declare this artifact") is answered for both
ledgers by `check_derived_claims` and `check_spec_citations`, which read them.

WHAT THIS CANNOT PROVE, stated rather than implied: that an amendment is CORRECT,
that its number is the RIGHT one, or that its content does not contradict another
ledger's entry. It proves the identifiers are unambiguous. A wrong ruling with a
unique, well-formed identifier passes here, and should.
"""
# pylint: disable=invalid-name
# Test names SHOUT the property, as everywhere else in this suite.

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent

#: ledger path -> its prefix. The mapping IS the ruling.
LEDGERS: dict[str, str] = {
    "docs/SPEC-AMENDMENTS.md": "SPEC",
    "docs/CHECK-CONTRACT-AMENDMENTS.md": "CHECK",
}

#: Non-vacuity floor. Both ledgers held six when this was written; the floor is
#: deliberately BELOW that and is a floor rather than today's count (doctrine
#: C.4) — a ledger that grows must not have to edit this file, but a parser that
#: stopped matching must not read as a clean sheet.
MIN_AMENDMENTS = 4

#: A prefixed amendment heading. `-REFINEMENT` is a suffix on an existing number
#: and is deliberately NOT a new amendment (SPEC-A3-REFINEMENT narrows SPEC-A3;
#: a separate entry would let the two be cited against each other).
_HEADING = re.compile(
    r"^## (?P<prefix>[A-Z]+)-A(?P<num>\d+)(?P<refinement>-REFINEMENT)?\b", re.MULTILINE
)

#: The parametrize argvalues, mirrored here so the INLINE LITERALS in the
#: decorators below can be held against `LEDGERS`.
#:
#: `sorted(LEDGERS)` would be the obvious spelling and `check_derived_claims`
#: REFUSED it, by name and on the first run: *"parametrize argvalues is not a
#: literal sequence — the AST count cannot be trusted; register a different
#: source"*. Its `source_ast` probe counts test functions statically and a
#: computed argvalues list makes that count unknowable, so the gate declines to
#: measure rather than guessing — which is the behaviour this suite is written to
#: honour, not an obstacle to route around. The literal is therefore written out,
#: The literal is written INLINE in each decorator — a module-level name is not a
#: literal either, and the probe refuses that too (measured). This constant is the
#: mirror `test_the_LITERAL_ARGVALUES_STILL_MATCH_THE_LEDGER_MAP` holds the inline
#: literals against, which is the one thing a literal costs.
_EACH_LEDGER = ("docs/CHECK-CONTRACT-AMENDMENTS.md", "docs/SPEC-AMENDMENTS.md")

#: The unprefixed form. Its presence as a HEADING is the defect: it is the
#: citation shape that named two rulings at once.
_BARE_HEADING = re.compile(r"^## AMENDMENT\s+\d+", re.MULTILINE)


def _text(relative: str) -> str:
    path = REPO / relative
    if not path.is_file():
        pytest.fail(
            f"{relative} is in LEDGERS and is not on disk — a scope that "
            "silently shrinks reports a clean sheet over what it stopped reading"
        )
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the parser reaches real headings in both ledgers
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "relative",
    ("docs/CHECK-CONTRACT-AMENDMENTS.md", "docs/SPEC-AMENDMENTS.md"),
)
def test_the_PARSER_REACHES_REAL_HEADINGS_in_this_ledger(relative: str) -> None:
    """A clean sheet over zero headings is the failure this floor prevents."""
    found = _HEADING.findall(_text(relative))

    assert len(found) >= MIN_AMENDMENTS, (
        f"{relative}: parsed only {len(found)} amendment heading(s), below the "
        f"floor of {MIN_AMENDMENTS} — every assertion below would then be true "
        "of an empty set"
    )


# --------------------------------------------------------------------------
# THE TWO PROPERTIES THE RULING NAMES
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "relative",
    ("docs/CHECK-CONTRACT-AMENDMENTS.md", "docs/SPEC-AMENDMENTS.md"),
)
def test_EVERY_AMENDMENT_HEADING_CARRIES_ITS_OWN_LEDGERS_PREFIX(relative: str) -> None:
    """`CHECK-A3` in `SPEC-AMENDMENTS.md` would be a citation nobody can resolve."""
    expected = LEDGERS[relative]
    text = _text(relative)

    bare = _BARE_HEADING.findall(text)
    assert bare == [], (
        f"{relative}: {len(bare)} heading(s) still spelled `## AMENDMENT <n>` "
        f"({bare}) — that is the ambiguous form, and it named two different "
        "rulings across two ledgers that each number from 1"
    )
    wrong = [
        match.group(0)
        for match in _HEADING.finditer(text)
        if match.group("prefix") != expected
    ]
    assert wrong == [], (
        f"{relative}: heading(s) carrying the wrong ledger prefix {wrong} — "
        f"every amendment heading in this file must begin `## {expected}-A<n>`"
    )


@pytest.mark.parametrize(
    "relative",
    ("docs/CHECK-CONTRACT-AMENDMENTS.md", "docs/SPEC-AMENDMENTS.md"),
)
def test_A_NUMBER_IS_ISSUED_ONCE_INSIDE_ITS_OWN_LEDGER(relative: str) -> None:
    """The arm that would have caught `AMENDMENT 5` being issued twice."""
    numbers = [
        match.group("num")
        for match in _HEADING.finditer(_text(relative))
        if not match.group("refinement")
    ]

    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    assert duplicates == [], (
        f"{relative}: amendment number(s) {duplicates} issued more than once in "
        "one ledger. This is the ARC 022 defect verbatim -- two rulings wearing "
        "one identifier, in the document that exists to keep them apart"
    )


def test_THE_TWO_LEDGERS_PREFIXES_ARE_DISJOINT() -> None:
    """Two ledgers sharing a prefix would reintroduce the ambiguity exactly."""
    prefixes = list(LEDGERS.values())

    assert len(set(prefixes)) == len(prefixes), (
        f"ledger prefixes {prefixes} are not distinct — the prefix exists ONLY "
        "to tell the ledgers apart, so a shared one is worse than none"
    )


def test_A_REFINEMENT_IS_NOT_COUNTED_AS_A_NEW_AMENDMENT() -> None:
    """`SPEC-A3-REFINEMENT` narrows SPEC-A3; it must not occupy a number.

    Non-vacuity for the rule above: if no refinement heading existed anywhere,
    the `refinement` branch of the uniqueness test would never execute and the
    exclusion would be untested decoration.
    """
    text = _text("docs/SPEC-AMENDMENTS.md")
    refinements = [
        match.group(0) for match in _HEADING.finditer(text) if match.group("refinement")
    ]

    assert refinements, (
        "no `-REFINEMENT` heading is on disk, so the uniqueness rule's exclusion "
        "for refinements has never been exercised by a real case"
    )
    for heading in refinements:
        base = heading.split("-REFINEMENT")[0]
        assert f"{base} " in text or f"{base} (" in text, (
            f"{heading} refines {base}, which is not in this ledger — a "
            "refinement of nothing is a new amendment wearing a suffix"
        )


def test_the_INLINE_ARGVALUES_STILL_MATCH_THE_LEDGER_MAP() -> None:
    """The price of the inline literals, paid rather than left as a comment.

    A ledger added to `LEDGERS` and not to a decorator would be silently
    unparametrised — swept by nothing, while this suite still reported green over
    the ledgers it does reach. That is the scope-shrinks-silently class this
    project sweeps for, and here it would be living inside the sweeper.

    So the guard reads THIS MODULE'S OWN SOURCE by AST and compares every
    `parametrize` argvalues tuple to the map, rather than comparing a mirror
    constant to the map and leaving the decorators unchecked — a guard that
    checks a copy of the thing is the defect it is supposed to catch.
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    found: list[tuple[str, ...]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if not (isinstance(target, ast.Attribute) and target.attr == "parametrize"):
            continue
        argvalues = node.args[1]
        assert isinstance(argvalues, (ast.Tuple, ast.List)), (
            "a parametrize argvalues that is not a literal sequence makes "
            "check_derived_claims' source_ast probe unmeasurable — it refused "
            "exactly this on the first run, by name"
        )
        values: list[str] = []
        for element in argvalues.elts:
            assert isinstance(element, ast.Constant), (
                f"a non-literal element {ast.dump(element)} in parametrize "
                "argvalues — the same unmeasurable shape one level down"
            )
            values.append(str(element.value))
        found.append(tuple(values))

    assert found, "no parametrize decorator was parsed — this guard read nothing"
    expected = tuple(sorted(LEDGERS))
    assert _EACH_LEDGER == expected, (
        f"_EACH_LEDGER {_EACH_LEDGER} has drifted from LEDGERS {expected}"
    )
    for parsed in found:
        assert parsed == expected, (
            f"an inline parametrize argvalues {parsed} disagrees with LEDGERS "
            f"{expected} — a ledger in the map and not in a decorator is a "
            "ledger no test in this file ever reads"
        )
