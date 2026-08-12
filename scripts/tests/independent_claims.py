"""A SECOND, EXTERNALLY-IMPLEMENTED SOURCE for `check_derived_claims`' claims.

ARC 026 / A1. Not a test module — plant material and instrument, imported by
`scripts/tests/test_check_derived_claims.py`.

WHY IT EXISTS. `check_derived_claims` compares two sources per claim, and for
ten of its thirteen claims BOTH sources are probes inside the gate itself,
re-entered as `{self} --probe`. The two sides then share the gate's parsing
helpers, so **a defect in a shared helper moves both numbers together and the
comparison stays green.** That is not a hypothesis; ARC 026 planted it three
times and measured it (see the plants in the companion test module).

WHAT "INDEPENDENT" MEANS HERE, precisely, because the word is cheap:

  * **Different mechanism.** The gate reads code by `ast.parse` and reads the
    ledger with one regex per rule. Everything below is REGEX ONLY — over the
    same documents, never over the gate's output — so an AST-side defect cannot
    reach it and a shared-helper defect cannot move it.
  * **Different file, no import of the subject.** Nothing here imports
    `check_derived_claims`, so no helper is shared with it at all. The only
    thing the two have in common is the tree they read.
  * **Different implementations of the same STATED rule**, which is the only
    kind of independence available when the rule itself is the thing under
    measurement. Two spellings of one rule can disagree, and on their first run
    together they did — see `bold_spans` below.

WHAT IT IS NOT. It is not a re-derivation of the gate's *code*; a transcription
would inherit the defects it is supposed to be independent of, and would be
worse than nothing because it would look like a second opinion. Where the rule
was too intricate to re-implement honestly, the companion module marks the
claim NOT INDEPENDENT rather than shipping a copy — four honest UNBOUND rows
beat four green rows resting on prose.
"""

from __future__ import annotations

import re
from pathlib import Path

LEDGER = "docs/CHECK-DEBT.md"
SPEC = "docs/nics_risk_subsystem_spec_v1.3.md"
SEAM = "scripts/broker/broker_seam.py"
MAPPING = "scripts/broker/ibkr_mapping.py"
BANS = "checks/check_order_path_bans.py"

_ROW = re.compile(r"^\|\s*(D[123]\.\d+)\s*\|")
_DISCHARGED = re.compile(r"discharged ARC \d+", re.IGNORECASE)


def text(home: Path, rel: str) -> str:
    """One repo-relative file, as text."""
    return (home / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# THE LEDGER'S BOLD-SPAN RULE, implemented by DELIMITER FLANKING.
# ---------------------------------------------------------------------------


def bold_spans(line: str) -> list[str]:
    """Every `**bold**` span, by CommonMark's left/right-flanking delimiter rule.

    THE GATE SPELLS THIS RULE AS ONE REGEX — `\\*\\*[^*]*\\bdischarged ARC \\d+`
    — which asks whether some `**` is followed, without an intervening `*`, by
    the phrase. It never checks the span CLOSES.

    THE TWO SPELLINGS DISAGREED ON THEIR FIRST RUN TOGETHER, and finding that
    is the entire justification for this file existing. A naive left-to-right
    pairing (`\\*\\*(.+?)\\*\\*`) reports **69** open rows against the gate's 68,
    the extra row being **D2.16** — whose body carries a perfectly ordinary
    `**DISCHARGED ARC 018 Phase 4, ...**` span, but which has an ODD number of
    `**` markers (15) earlier in the row, so pairing from the left makes that
    opener land in a closer's position and the phrase falls outside bold.
    Flanking resolves it the way a renderer would: a `**` followed by non-space
    opens, a `**` preceded by non-space closes. That implementation agrees with
    the gate on all 69 rows, VERDICT BY VERDICT and not merely in total
    (doctrine C.6).

    The residual is real and is named rather than papered over: a ledger row
    with unbalanced emphasis is ambiguous under any implementation of a rule
    stated in prose, and the two instruments now agree by construction on
    today's text rather than by proof for all text.
    """
    spans: list[str] = []
    opened: int | None = None
    for match in re.finditer(r"\*\*", line):
        start, end = match.span()
        left_flanking = start > 0 and not line[start - 1].isspace()
        right_flanking = end < len(line) and not line[end].isspace()
        if opened is None:
            if right_flanking:
                opened = end
        elif left_flanking:
            spans.append(line[opened:start])
            opened = None
    return spans


def open_rows(home: Path) -> list[tuple[str, str]]:
    """(id, row) for every ledger row no bold span declares discharged."""
    rows = [ln for ln in text(home, LEDGER).splitlines() if _ROW.match(ln)]
    if not rows:
        raise AssertionError(f"{LEDGER}: no D1./D2./D3. rows matched")
    return [
        (_ROW.match(line).group(1), line)  # type: ignore[union-attr]
        for line in rows
        if not any(_DISCHARGED.search(span) for span in bold_spans(line))
    ]


# ---------------------------------------------------------------------------
# THE TWO §2A ROSTERS, by regex over the frozen spec and over the seam.
# ---------------------------------------------------------------------------


def spec_roster(home: Path, library: str) -> list[str]:
    """§2A identifiers for one library. `re.split` on headings, not index/find."""
    for part in re.split(r"(?m)^###\s+", text(home, SPEC))[1:]:
        if not part.startswith(library):
            continue
        block = re.split(r"(?m)^(?:##\s|---)", part)[0]
        names: list[str] = []
        for span in re.findall(r"(?m)^-\s+`([^`]+)`", block):
            names.extend(re.findall(r"([A-Za-z_]\w*)\s*\(", span))
        if not names:
            raise AssertionError(f"§2A {library}: no identifiers")
        return names
    raise AssertionError(f"{SPEC}: no '### {library}' section")


def seam_tuple(home: Path, name: str, source: str | None = None) -> list[str]:
    """A module-level str tuple, by regex. The gate reads the same by AST."""
    body = source if source is not None else text(home, SEAM)
    match = re.search(rf"(?m)^{name}\b[^=]*=\s*\((.*?)\)\n", body, re.DOTALL)
    if not match:
        raise AssertionError(f"{name} not found")
    return re.findall(r'"([^"]+)"', match.group(1))


def flagged_additions(home: Path, candidates: list[str], spec: list[str]) -> list[str]:
    """Seam elements outside §2A whose own docstring calls them a Nix addition."""
    body = text(home, SEAM)
    flagged: list[str] = []
    for name in candidates:
        if name in spec:
            continue
        match = re.search(
            rf"(?m)^\s*(?:async\s+)?def\s+{re.escape(name)}\s*\(.*?"
            r'"""(.*?)"""',
            body,
            re.DOTALL,
        )
        if match and "nix addition" in match.group(1).lower():
            flagged.append(name)
    return flagged


# ---------------------------------------------------------------------------
# ARC 014's grades, by regex over the Finding(...) literals.
# ---------------------------------------------------------------------------


def grades(home: Path, roster: list[str]) -> dict[str, str]:
    """ARC 014's grade for each roster identifier it names."""
    pairs = re.findall(r'Finding\(\s*"([^"]+)"\s*,\s*"([^"]+)"', text(home, MAPPING))
    if not pairs:
        raise AssertionError(f"{MAPPING}: no Finding(...) literals")
    out: dict[str, str] = {}
    for verb, grade in pairs:
        for name in (p.strip() for p in verb.split("(", 1)[0].split("/")):
            if name in roster:
                out[name] = grade
    return out


def element_coverage(home: Path, roster: list[str]) -> int:
    """`sec2a-element-v1`: integer percent of the roster graded CLEAN."""
    if not roster:
        raise AssertionError("a percent over an empty roster is not a percent")
    found = grades(home, roster)
    clean = sum(1 for name in roster if found.get(name) == "CLEAN")
    return 100 * clean // len(roster)


# ---------------------------------------------------------------------------
# THE OWNING-MODULE COLUMN — ARC 026 / B3 replaced the prose rule with an
# AUTHORED column, and this section was rewritten to follow it.
#
# WHAT WAS HERE BEFORE, AND WHY IT IS GONE. Until B3 the two debt claims
# selected rows by scanning prose for order-path basenames and roster verbs,
# and this file carried an independent regex re-implementation of that ~300-line
# rule. The rule no longer exists: `_roster_hit`, `_broker_order_scoped` and
# `_order_path_basenames` are not in the gate any more. Re-implementing a rule
# that was deleted would be a second opinion about nothing, so the code was
# removed rather than kept passing.
#
# THE NEW RULE, and the mechanisms below are deliberately not the gate's:
#   * vocabulary — the gate anchors `^\|\s*`token`\s*\|` with one MULTILINE
#     regex over the whole file. This locates the vocabulary SECTION by heading
#     and splits its rows into cells.
#   * owning module — the gate does `stripped[:-1].rsplit("|", 1)[-1]`. This
#     splits the whole row and indexes `[-2]`.
#   * stated tally — the gate anchors `^\|\s*token\s*\|\s*(\d+)\s*\|$`.
#     This locates the tally SECTION by heading and reads its cells.
# Same stated rules, different readers, so a defect in one cannot move the other.
# ---------------------------------------------------------------------------

VOCAB_HEADING = "### The controlled vocabulary"
TALLY_HEADING = "### Stated per-module tally"


def _section(home: Path, heading: str) -> str:
    """The markdown block under `heading`, up to the next `###`/`##` divider."""
    body = text(home, LEDGER)
    start = body.index(heading) + len(heading)
    rest = re.split(r"(?m)^(?:###?\s|---\s*$)", body[start:])[0]
    return rest


def _cells(line: str) -> list[str]:
    """A markdown row's cells, outer pipes discarded."""
    parts = [cell.strip() for cell in line.split("|")]
    return parts[1:-1] if len(parts) > 2 else []


def owning_vocabulary(home: Path) -> set[str]:
    """The legal `owning module` tokens, from the vocabulary table's first cell."""
    tokens = set()
    for line in _section(home, VOCAB_HEADING).splitlines():
        cells = _cells(line)
        if not cells:
            continue
        match = re.fullmatch(r"`([a-z][a-z-]*)`", cells[0])
        if match:
            tokens.add(match.group(1))
    if not tokens:
        raise AssertionError("the owning-module vocabulary table parsed to nothing")
    return tokens


def owning_module(line: str) -> str:
    """The row's LAST cell — the authored column. `''` when the row has none."""
    parts = line.rstrip().split("|")
    return parts[-2].strip() if len(parts) >= 3 and parts[-1].strip() == "" else ""


def rows_by_module(home: Path) -> dict[str, list[str]]:
    """Open row ids grouped by their authored column. Fails closed, like the gate.

    An unattributed open row raises rather than being dropped: the failure this
    column replaces was a row leaving a count with nobody noticing, and a lenient
    second source would agree with a lenient gate for the wrong reason.
    """
    vocabulary = owning_vocabulary(home)
    grouped: dict[str, list[str]] = {token: [] for token in vocabulary}
    stray = []
    for rid, line in open_rows(home):
        token = owning_module(line)
        if token not in vocabulary:
            stray.append(f"{rid}={token or '<absent>'}")
            continue
        grouped[token].append(rid)
    if stray:
        raise AssertionError(f"open row(s) with no valid owning module: {stray}")
    return grouped


def stated_tally(home: Path) -> dict[str, int]:
    """The ledger's hand-written per-module tally, read from the tally SECTION."""
    tally: dict[str, int] = {}
    for line in _section(home, TALLY_HEADING).splitlines():
        cells = _cells(line)
        if (
            len(cells) == 2
            and re.fullmatch(r"[a-z][a-z-]*", cells[0])
            and cells[1].isdigit()
        ):
            tally[cells[0]] = int(cells[1])
    if not tally:
        raise AssertionError("the stated per-module tally parsed to nothing")
    return tally


# ---------------------------------------------------------------------------
# THE CLAIMS THIS FILE CAN ANSWER, by the gate's own claim id.
# ---------------------------------------------------------------------------


def registered_check_count(home: Path) -> int:
    """Claim `registered_check_count`, from the registry's block lists."""
    import json  # pylint: disable=import-outside-toplevel

    registry = json.loads(text(home, "checks/registry.json"))
    return len({name for block in registry["blocks"] for name in block["checks"]})


def check_debt_open_items(home: Path) -> int:
    """Claim `check_debt_open_items`."""
    return len(open_rows(home))


def spec_2a_broker_order_elements(home: Path) -> int:
    """Claim `spec_2a_broker_order_elements`."""
    return len(spec_roster(home, "broker-order"))


def arc014_broker_order_classification(home: Path) -> int:
    """Claim `arc014_broker_order_classification`.

    ADDED ARC 026 / A1 SECOND PASS. All THREE of this claim's sources call the
    gate's `_spec_identifiers`, and truncating it moves 16 -> 15 -> 15 -> 15 with
    the gate reporting agreement. Measured, not reasoned.
    """
    return len(grades(home, spec_roster(home, "broker-order")))


def spec_2a_broker_datafeed_elements(home: Path) -> int:
    """Claim `spec_2a_broker_datafeed_elements`.

    ADDED ARC 026 / A1 SECOND PASS. Both sources call the gate's `_module_tuples`,
    and truncating it moves 11 -> 9 on both sides in silence.
    """
    spec_feed = spec_roster(home, "broker-datafeed")
    seam_feed = seam_tuple(home, "DATAFEED_PORT_VERBS") + seam_tuple(
        home, "DATAFEED_EVENTS"
    )
    return len(spec_feed) + len(flagged_additions(home, seam_feed, spec_feed))


def broker_order_element_coverage_v1(home: Path) -> int:
    """Claim `broker_order_element_coverage_v1`, scheme `sec2a-element-v1`."""
    return element_coverage(home, spec_roster(home, "broker-order"))


def broker_order_open_debt_rows(home: Path) -> int:
    """Claim `broker_order_open_debt_rows`, by the authored column."""
    return len(rows_by_module(home)["broker-order"])


def broker_datafeed_open_debt_rows(home: Path) -> int:
    """Claim `broker_datafeed_open_debt_rows`, by the authored column."""
    return len(rows_by_module(home)["broker-datafeed"])


#: Claim id -> independent re-derivation. The companion module iterates this
#: rather than naming the claims twice.
SOURCES = {
    "registered_check_count": registered_check_count,
    "check_debt_open_items": check_debt_open_items,
    "spec_2a_broker_order_elements": spec_2a_broker_order_elements,
    "arc014_broker_order_classification": arc014_broker_order_classification,
    "spec_2a_broker_datafeed_elements": spec_2a_broker_datafeed_elements,
    "broker_order_element_coverage_v1": broker_order_element_coverage_v1,
    "broker_order_open_debt_rows": broker_order_open_debt_rows,
    "broker_datafeed_open_debt_rows": broker_datafeed_open_debt_rows,
}
