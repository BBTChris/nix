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
# THE MODULE-SCOPING RULE — the intricate one, re-implemented by regex.
# ---------------------------------------------------------------------------


def order_path_dirs(home: Path) -> list[str]:
    """The order path, read out of the bans gate's own anchor — never typed."""
    return seam_tuple(home, "ORDER_PATH_DIRS", text(home, BANS))


def _class_bodies(source: str) -> list[str]:
    """The indented body of every top-level class, by indentation.

    The gate does this with `ast.walk` + `isinstance(node, ast.ClassDef)`. This
    reads columns, which is why it can disagree with the gate rather than merely
    echo it — and it did, on the first run: an earlier spelling here returned
    NO class bodies at all, which emptied the datafeed subtraction and selected
    D1.13 that the gate correctly excludes. A silent empty set is this project's
    vacuity class, so the caller asserts a non-empty implementor set.
    """
    bodies: list[str] = []
    for chunk in re.split(r"(?m)^class ", source)[1:]:
        body: list[str] = []
        for line in chunk.split("\n")[1:]:
            if line and not line[0].isspace():
                break
            body.append(line)
        bodies.append("\n".join(body))
    return bodies


def port_implementors(home: Path, verbs: list[str], quorum: int) -> set[str]:
    """Modules under `scripts/` whose class defines `quorum` of `verbs`."""
    out: set[str] = set()
    for path in sorted((home / "scripts").rglob("*.py")):
        if any(part in {".venv", "__pycache__"} for part in path.parts):
            continue
        for body in _class_bodies(path.read_text(encoding="utf-8")):
            methods = set(re.findall(r"(?m)^    (?:async )?def (\w+)", body))
            if len(methods & set(verbs)) >= quorum:
                out.add(path.name)
    return out


def order_path_owners(home: Path) -> set[str]:
    """Receiver names a roster verb may legitimately hang off."""
    owners: set[str] = set()
    for directory in order_path_dirs(home):
        for path in (home / directory).rglob("*.py"):
            if "__pycache__" in path.parts or not path.is_file():
                continue
            owners.add(path.stem)
            owners |= set(
                re.findall(r"(?m)^\s*class\s+(\w+)", path.read_text(encoding="utf-8"))
            )
    return owners


def roster_hit(body: str, roster: list[str], owners: set[str]) -> bool:
    """A roster identifier used as a verb, not as somebody else's attribute."""
    for name in roster:
        for match in re.finditer(r"\b" + re.escape(name) + r"\b", body):
            qualifier = re.search(r"([A-Za-z_]\w*)\.$", body[: match.start()])
            if qualifier is None or qualifier.group(1) in owners:
                return True
    return False


def _d3_owned(
    rid: str, line: str, on_path: list[str], roster: list[str], owners: set[str]
) -> bool:
    if not rid.startswith("D3"):
        return True
    cells = [cell.strip() for cell in line.split("|")][1:]
    subject = cells[1] if len(cells) > 1 else ""
    return any(name in subject for name in on_path) or roster_hit(
        subject, roster, owners
    )


def order_debt_rows(home: Path, roster: list[str]) -> list[str]:
    """Open ledger rows owned by an order-path artefact. Returns the IDS.

    IDS, NOT A COUNT, and that is the point: the companion test compares the
    SELECTED SET against the gate's own printed selection, verdict by verdict.
    Two counts agreeing while two different rows were selected is doctrine C.6's
    measured failure, and a count-only comparison cannot see it.
    """
    dirs = order_path_dirs(home)
    on_path = sorted(
        {p.name for d in dirs for p in (home / d).rglob("*.py") if p.is_file()}
    )
    feed = port_implementors(home, seam_tuple(home, "DATAFEED_PORT_VERBS"), 3)
    if not feed:
        raise AssertionError(
            "no module implements the datafeed port — the D2.19 subtraction "
            "would be vacuous and every datafeed module would count as order "
            "depth (this exact emptiness selected D1.13 while it was live)"
        )
    distinctive = [name for name in on_path if name not in feed]
    owners = order_path_owners(home)
    return [
        rid
        for rid, line in open_rows(home)
        if (
            any(name in line for name in distinctive)
            or roster_hit(line, roster, owners)
        )
        and _d3_owned(rid, line, on_path, roster, owners)
    ]


def datafeed_debt_rows(home: Path, feed: list[str], order: list[str]) -> list[str]:
    """Open ledger rows naming a DISTINCTIVE broker-datafeed artefact."""
    distinctive = [name for name in feed if name not in order]
    if not distinctive:
        raise AssertionError("the datafeed roster is a subset of the order roster")
    feed_only = sorted(
        port_implementors(home, seam_tuple(home, "DATAFEED_PORT_VERBS"), 3)
        - port_implementors(home, seam_tuple(home, "ORDER_PORT_VERBS"), 4)
    )
    patterns = [re.compile(r"\b" + re.escape(name) + r"\b") for name in distinctive]
    return [
        rid
        for rid, line in open_rows(home)
        if any(name in line for name in feed_only)
        or any(pattern.search(line) for pattern in patterns)
    ]


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


def broker_order_element_coverage_v1(home: Path) -> int:
    """Claim `broker_order_element_coverage_v1`, scheme `sec2a-element-v1`."""
    return element_coverage(home, spec_roster(home, "broker-order"))


def broker_order_open_debt_rows(home: Path) -> int:
    """Claim `broker_order_open_debt_rows`."""
    return len(order_debt_rows(home, spec_roster(home, "broker-order")))


def broker_datafeed_open_debt_rows(home: Path) -> int:
    """Claim `broker_datafeed_open_debt_rows`."""
    feed = spec_roster(home, "broker-datafeed")
    seam_feed = seam_tuple(home, "DATAFEED_PORT_VERBS") + seam_tuple(
        home, "DATAFEED_EVENTS"
    )
    return len(
        datafeed_debt_rows(
            home,
            feed + flagged_additions(home, seam_feed, feed),
            spec_roster(home, "broker-order"),
        )
    )


#: Claim id -> independent re-derivation. The companion module iterates this
#: rather than naming the claims twice.
SOURCES = {
    "registered_check_count": registered_check_count,
    "check_debt_open_items": check_debt_open_items,
    "spec_2a_broker_order_elements": spec_2a_broker_order_elements,
    "broker_order_element_coverage_v1": broker_order_element_coverage_v1,
    "broker_order_open_debt_rows": broker_order_open_debt_rows,
    "broker_datafeed_open_debt_rows": broker_datafeed_open_debt_rows,
}
