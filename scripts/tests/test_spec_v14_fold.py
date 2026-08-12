"""ARC 027 (B4) — the v1.4 fold, and the two halves of it that were REFUSED.

`docs/nics_risk_subsystem_spec_v1.4.md` is v1.3 with each entry of
`docs/SPEC-AMENDMENTS.md` inserted at the section that entry names, wrapped in
`<!-- BEGIN FOLDED ... -->` / `<!-- END FOLDED ... -->` markers. Mechanical only:
nothing reworded, nothing renumbered, nothing improved.

## The gate, and why it diffs against GIT rather than against the file on disk

*"No non-amendment text changed"* is only a claim if the reference is out of the
editing hand's reach. `docs/nics_risk_subsystem_spec_v1.3.md` is a working-tree
file; diffing v1.4 against it would compare the fold to whatever v1.3 happens to
say today, and an edit to v1.3 would make a wrong fold look right.

The reference is therefore the COMMITTED BLOB at
`aaa6a28f06f071d99411fec925a3d678cfbe66c6`. That commit is the initial import,
it is the ONLY commit that has ever touched the risk spec, and the working copy
is still byte-identical to it — measured, and asserted below, so the "frozen —
never edit" prohibition is verified rather than assumed.

## WHAT WAS REFUSED, per amendment, and why

The brief permits a per-amendment refusal where the spec has no section saying
the thing the amendment amends. Two refusals were needed and neither is that one,
so both are stated here in full rather than filed under a rule they do not fit.

**1. The §2A list GROWTH implied by AMENDMENT 4 and AMENDMENT 5 (D1.38).** Both
supply verbatim RULING text and both were folded. Both ALSO imply that §2A's
broker-datafeed declarations must grow — `on_bar` / `on_bar_revision` events for
AMENDMENT 4, `poll_history` / `granted_mode` and a sync/async split for
AMENDMENT 5 — and **neither supplies verbatim text for the new bullets.**
Authoring an event signature is composing spec text, which is editorial, which
"mechanical fold only" forbids. The rules are folded; the list growth is not, and
it is an architect action. Recorded as CHECK-DEBT D3.32.

**2. v1.4 IS NOT THE CITED AUTHORITY, and the reason is measured, not stylistic.**
The tree carries dozens of LINE-COORDINATE citations into the risk spec
(`§2A:105-106`, `§6.4:373-374`, `§12A:830`, `§13:919-920` …) inside
`GOVERNED_ROOTS`, where `check_spec_citations` range-checks them. A fold inserts
lines, so **every coordinate below the first insertion moves** —
`test_the_fold_MOVES_line_coordinates_and_here_is_how_many` measures exactly how
many governed citations that is. Re-pointing them is not a fold; it is a
re-coordination of the whole tree, it is Stage-2-serial work, and doing it inside
a fold would make the fold unreviewable. So v1.3 stays on disk, unmodified, and
stays the cited document. Recorded as CHECK-DEBT D3.33.

**This is B4's §0a answer, and it is uncomfortable.** *What would have to be true
for B4 to complete while measuring nothing?* Exactly this: write a perfectly
folded v1.4, leave every citation pointing at v1.3, register it with no gate, and
report "v1.4 delivered". The file would be real, correct, and read by nothing.
That is why v1.4 is a SUBJECT of this module and why the fold's fidelity is
re-proven on every pytest run — the document is inert as an authority and is NOT
inert as a measured artifact.

## debug.md §7.12 — the standing question

**What would have to be true for these tests to pass while measuring nothing?**

1. **The stripped text and the reference could both be empty** — a bad marker
   regex that eats the whole file, compared against a `git show` that returned
   nothing. *Closed:* both are asserted longer than `MIN_SPEC_LINES`, and the
   folded-block count is asserted equal to the number of entries in the ledger.
2. **The ledger could be read from v1.4 itself**, so every amendment would
   trivially be "traceable". *Closed:* the verbatim text is read from
   `docs/SPEC-AMENDMENTS.md` and required to appear in v1.4, which is the
   direction that can fail.
3. **The reference could be the working-tree v1.3**, comparing the fold to a file
   the same hand can edit. *Closed:* `git show <sha>:<path>`, and the sha is a
   literal in this file.
4. **The marker strip could be doing the work** — a regex that removes any line
   it dislikes would reconcile any fold. *Closed:* the strip is anchored to the
   BEGIN/END markers only, and `test_PLANT_...` shows that a single character
   changed OUTSIDE a folded block breaks the identity.
"""
# pylint: disable=invalid-name,duplicate-code

from __future__ import annotations

import ast
import os
import re
import subprocess  # nosec B404 - git show, fixed argv, no shell
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixverify.gitenv import scrubbed_env  # pylint: disable=wrong-import-position

#: The initial import — the ONLY commit that has ever touched the risk spec.
FROZEN_SHA = "aaa6a28f06f071d99411fec925a3d678cfbe66c6"
V13 = "docs/nics_risk_subsystem_spec_v1.3.md"
V14 = "docs/nics_risk_subsystem_spec_v1.4.md"
LEDGER = "docs/SPEC-AMENDMENTS.md"
GIT = "/usr/bin/git"

#: A floor, so an empty-vs-empty comparison cannot read as a clean fold.
MIN_SPEC_LINES = 1000

#: The seven entries as they stand ON DISK. The numbering is the ledger's, not a
#: tidied one: two rulings were both ISSUED as "AMENDMENT 5" and the ledger
#: records the ARC 023 one as AMENDMENT 6 while keeping the ruling's own
#: self-reference intact. **RENUMBER NOTHING** — the architect rules on that.
FOLDED_IDS: tuple[str, ...] = (
    "AMENDMENT 1",
    "AMENDMENT 2",
    "AMENDMENT 3",
    "AMENDMENT 3, REFINEMENT (ARC 022)",
    "AMENDMENT 4",
    "AMENDMENT 5 (D1.38)",
    "AMENDMENT 6",
)

_BLOCK = re.compile(r"\n<!-- BEGIN FOLDED .*?<!-- END FOLDED [^>]*-->\n\n", re.DOTALL)


def test_the_inlined_PARAMETRIZE_ids_agree_with_FOLDED_IDS() -> None:
    """`check_derived_claims`' AST counter cannot read a NAME as argvalues.

    So the seven ids are inlined below, and this test is what stops the two
    copies drifting — the same trade `test_check_order_path_bans_drive.py` makes.
    """
    inlined: set[str] = set()
    for node in ast.walk(ast.parse(Path(__file__).read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "parametrize"):
            continue
        values = node.args[1] if len(node.args) > 1 else None
        if isinstance(values, ast.List):
            inlined |= {
                e.value
                for e in values.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            }
    assert inlined == set(FOLDED_IDS), (inlined, set(FOLDED_IDS))


def _frozen_v13() -> str:
    """The committed blob. NOT the working tree — that is the whole point."""
    proc = subprocess.run(  # nosec B603 - fixed absolute path, no shell
        [GIT, "-C", str(REPO), "show", f"{FROZEN_SHA}:{V13}"],
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_env(),
    )
    return proc.stdout


def _v14() -> str:
    return (REPO / V14).read_text(encoding="utf-8")


def _stripped(text: str) -> str:
    """v1.4 with the header comment and every folded block removed."""
    return _BLOCK.sub("", text.split("-->\n\n", 1)[1])


def _ledger_blocks() -> list[str]:
    """Every `> `-quoted run in the amendment ledger, as raw text."""
    lines = (REPO / LEDGER).read_text(encoding="utf-8").splitlines()
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.startswith(">"):
            current.append(line)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return ["\n".join(block) for block in blocks]


# --- NON-VACUITY FIRST (doctrine C.3, §5.1 step 2) --------------------------


def test_NONVACUITY_both_sides_of_the_comparison_are_real_documents() -> None:
    """An empty-vs-empty diff is clean, and means nothing."""
    frozen = _frozen_v13()
    v14 = _v14()
    assert len(frozen.splitlines()) >= MIN_SPEC_LINES, len(frozen.splitlines())
    assert len(v14.splitlines()) > len(frozen.splitlines()), (
        "the fold must be strictly longer than the document it folds into"
    )
    assert len(_stripped(v14).splitlines()) >= MIN_SPEC_LINES


def test_the_frozen_prohibition_HELD_the_working_v13_equals_its_only_commit() -> None:
    """`frozen — never edit`, verified rather than believed.

    If this ever fails, every claim in this module is void: the reference the
    fold was taken against is not the document anyone has been reading.
    """
    assert (REPO / V13).read_text(encoding="utf-8") == _frozen_v13()

    log = subprocess.run(  # nosec B603 - fixed absolute path, no shell
        [GIT, "-C", str(REPO), "log", "--format=%H", "--", V13],
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_env(),
    ).stdout.split()
    assert log == [FROZEN_SHA], (
        f"the risk spec has been touched by {len(log)} commit(s); the fold's "
        f"reference is no longer unambiguous: {log}"
    )


# --- THE GATE: no non-amendment text changed --------------------------------


def test_v14_MINUS_the_folded_blocks_is_BYTE_IDENTICAL_to_the_committed_v13() -> None:
    """The whole of *mechanical fold only*, in one assertion, against git."""
    assert _stripped(_v14()) == _frozen_v13(), (
        "text OUTSIDE a folded block differs from frozen v1.3 — the fold has "
        "reworded, reflowed or 'improved' something it was not permitted to touch"
    )


def test_PLANT_one_character_changed_OUTSIDE_a_folded_block_BREAKS_the_identity() -> (
    None
):
    """*A strip that removes whatever it dislikes reconciles any fold.*

    The can-fail for the gate itself. Without it, `_stripped` could be returning
    the reference text by construction and the test above would be a tautology.
    """
    tampered = _v14().replace("**Restart = flat, always.**", "**Restart = flat.**", 1)
    assert tampered != _v14(), "the plant did not land — the anchor text moved"
    assert _stripped(tampered) != _frozen_v13()


def test_PLANT_a_folded_block_whose_text_is_ALTERED_is_no_longer_traceable() -> None:
    """The other direction: the amendment text must be the ledger's, verbatim."""
    tampered = _v14().replace("value the quantity could", "value it could", 1)
    assert tampered != _v14()
    missing = [b for b in _ledger_blocks() if b in _v14() and b not in tampered]
    assert missing, "altering folded amendment text must break traceability"


@pytest.mark.parametrize(
    "amendment_id",
    [
        "AMENDMENT 1",
        "AMENDMENT 2",
        "AMENDMENT 3",
        "AMENDMENT 3, REFINEMENT (ARC 022)",
        "AMENDMENT 4",
        "AMENDMENT 5 (D1.38)",
        "AMENDMENT 6",
    ],
    ids=[
        "AMENDMENT 1",
        "AMENDMENT 2",
        "AMENDMENT 3",
        "AMENDMENT 3 REFINEMENT",
        "AMENDMENT 4",
        "AMENDMENT 5 D1.38",
        "AMENDMENT 6",
    ],
)
def test_every_amendment_is_TRACEABLE_to_its_landed_text(amendment_id: str) -> None:
    """Each entry has a marked block, and the block names its ledger source."""
    v14 = _v14()
    assert f"<!-- BEGIN FOLDED {amendment_id} -->" in v14, amendment_id
    assert f"<!-- END FOLDED {amendment_id} -->" in v14, amendment_id
    start = v14.index(f"<!-- BEGIN FOLDED {amendment_id} -->")
    end = v14.index(f"<!-- END FOLDED {amendment_id} -->")
    body = v14[start:end]
    assert f"source: {LEDGER} lines" in body, body[:400]
    assert "target:" in body, body[:400]
    quoted = [line for line in body.splitlines() if line.startswith(">")]
    assert len(quoted) >= 5, (amendment_id, len(quoted))


def test_the_folded_block_count_equals_the_LEDGER_entry_count() -> None:
    """A fold that quietly dropped one would still pass every test above."""
    v14 = _v14()
    assert v14.count("<!-- BEGIN FOLDED ") == len(FOLDED_IDS)
    assert v14.count("<!-- END FOLDED ") == len(FOLDED_IDS)


def test_the_NUMBERING_is_the_LEDGERS_and_AMENDMENT_6_keeps_its_self_reference() -> (
    None
):
    """RENUMBER NOTHING. The collision is the architect's to rule on.

    Two rulings were issued titled "AMENDMENT 5": ARC 022's async port (D1.38)
    and ARC 023's per-channel freshness. The ledger records the second as
    AMENDMENT 6 and preserves its text verbatim, self-reference included. A fold
    that "helpfully" corrected that would destroy the evidence of the collision.
    """
    v14 = _v14()
    block = v14[
        v14.index("<!-- BEGIN FOLDED AMENDMENT 6 -->") : v14.index(
            "<!-- END FOLDED AMENDMENT 6 -->"
        )
    ]
    assert "**AMENDMENT 5 — freshness is per-channel.**" in block, (
        "the ruling's own self-reference was silently corrected"
    )
    assert "AMENDMENT 5 (D1.38)" in v14, "the OTHER amendment 5 must still be there"


# --- THE REFUSALS, ASSERTED SO THEY CANNOT BE FORGOTTEN ---------------------


def test_REFUSED_the_2A_list_growth_was_NOT_authored(  # pylint: disable=invalid-name,duplicate-code
) -> None:
    """AMENDMENT 4 and 5 imply new §2A bullets and supply no text for them.

    Composing an event signature is editorial. The assertion is that the fold did
    NOT invent one — a fold that had would be indistinguishable, on the diff,
    from a fold that was handed the text.
    """
    v14 = _v14()
    for invented in ("on_bar(", "on_bar_revision(", "poll_history(", "granted_mode("):
        outside = _stripped(v14)
        assert invented not in outside, (
            f"{invented!r} appears in v1.4 outside a folded block — the fold "
            "authored spec text it was not given (CHECK-DEBT D3.32)"
        )


def test_REFUSED_v13_is_UNTOUCHED_and_remains_the_cited_document() -> None:
    """The fold adds a file; it does not re-coordinate the tree (D3.33)."""
    assert (REPO / V13).is_file(), "v1.3 must remain on disk"
    assert (REPO / V13).read_text(encoding="utf-8") == _frozen_v13()


def test_the_fold_MOVES_line_coordinates_and_here_is_how_many() -> None:
    """The MEASUREMENT behind refusal 2, taken rather than asserted.

    Every governed citation carrying a line span into the risk spec resolves
    against v1.3's line numbers. The fold inserts lines, so a coordinate below the
    first insertion point names DIFFERENT text in v1.4. This counts them, and the
    count is the reason re-pointing the tree is a separate, serial job.
    """
    spans: list[tuple[str, int]] = []
    pattern = re.compile(r"§[0-9A-Za-z.]+:(\d+)(?:-\d+)?")
    for root in ("checks", "scripts/broker", "docs/CHECK-DEBT.md"):
        base = REPO / root
        files = [base] if base.is_file() else sorted(base.rglob("*"))
        for path in files:
            if not path.is_file() or path.suffix not in (".py", ".md", ".json"):
                continue
            for match in pattern.finditer(
                path.read_text(encoding="utf-8", errors="ignore")
            ):
                spans.append((str(path.relative_to(REPO)), int(match.group(1))))

    first_insertion = _v14().index("<!-- BEGIN FOLDED AMENDMENT 5 (D1.38) -->")
    shifted_from = _v14()[:first_insertion].count("\n")
    moved = [s for s in spans if s[1] > shifted_from]
    assert spans, "the citation sweep found nothing — the roots moved"
    assert moved, (
        "no governed line coordinate sits below the first insertion point, which "
        "would mean the fold is coordinate-safe and refusal 2 should be re-opened"
    )
    # Banked as an assertion so the figure cannot quietly stop being a reason.
    assert len(moved) >= 20, (
        f"only {len(moved)} governed coordinate(s) move; re-open D3.33 if the "
        "tree has been re-pointed"
    )


def test_the_environment_this_module_shells_git_in_is_SCRUBBED() -> None:
    """`GIT_DIR` ahead of `-C` bared the canonical repository once already."""
    assert not any(key.startswith("GIT_") for key in scrubbed_env(dict(os.environ)))
