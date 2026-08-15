"""ARC 031 Stage 1 / C — the CAN-FAIL suite for `checks/check_allocator_caps.py`.

**THE REQUIREMENT THIS FILE EXISTS TO SATISFY** (§0e): a can-fail must be a
committed, runnable artifact that drives the SHIPPED bytes red. So every control
below builds a throwaway `nix_home` under `tmp_path` holding COPIES of the two
modules, both seams, the config set, the loader and the frozen spec; perturbs a
COPY; and drives `checks/check_allocator_caps.py`'s OWN bytes against it.

**No plant touches a production artifact** (doctrine C.8). Nothing here writes
inside the repository, and `test_no_plant_touched_the_repository` asserts that
the live tree is still green after the whole suite has run.

The plants are chosen to be the wrong implementations that a reader would
plausibly write, not arbitrary corruption:

  * `sum()` replaced by `max()` — the defect the whole C1 mandate is about, and
    the one a single-position-per-bucket test cannot see;
  * the same-bucket filter deleted — a cap that reaches across buckets;
  * size-down replaced by all-or-nothing — safe, and the wrong rule;
  * the FCFS fallback raising — a scoring outage halting order flow;
  * FCFS ordered by SYMBOL instead of arrival — structurally biased;
  * the ranking port never consulted — a decorative read seam;
  * an `award()` verb — the authority split crossed.

Every control asserts the REASON — the site and the named condition — never the
exit code or the status alone (check contract v2 §11).
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code

from __future__ import annotations

import ast
import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_allocator_caps as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

COPIED_FILES = (
    "scripts/nixalloc/__init__.py",
    "scripts/nixalloc/seam.py",
    "scripts/nixalloc/caps.py",
    "scripts/nixalloc/contention.py",
    "scripts/nixrisk/__init__.py",
    "scripts/nixrisk/seam.py",
    "scripts/risk_config.py",
    "docs/nics_risk_subsystem_spec_v1.3.md",
)

CAPS = "scripts/nixalloc/caps.py"
CONTENTION = "scripts/nixalloc/contention.py"
SEAM = "scripts/nixalloc/seam.py"
ALLOCATOR_CONFIG = "risks/allocator.config.json"
CAPS_CONFIG = "risks/allocator_caps.config.json"
SPEC = "docs/nics_risk_subsystem_spec_v1.3.md"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway tree carrying COPIES of every artifact the gate reads."""
    for rel in COPIED_FILES:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, target)
    (tmp_path / "risks").mkdir(parents=True, exist_ok=True)
    for source in sorted((REPO / "risks").glob("*.json")):
        shutil.copy(source, tmp_path / "risks" / source.name)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _plant(home: Path, rel: str, old: str, new: str) -> None:
    """Rewrite a COPIED file. Fails loudly if the anchor moved or is ambiguous."""
    path = home / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, (
        f"{rel}: anchor appears {text.count(old)} times, not once — the plant "
        "would measure something other than what it names"
    )
    path.write_text(text.replace(old, new), encoding="utf-8")


def _append(home: Path, rel: str, addition: str) -> None:
    """Add to a COPIED file."""
    path = home / rel
    path.write_text(path.read_text(encoding="utf-8") + addition, encoding="utf-8")


def _red(result, *, site_contains: str, why_contains: str) -> None:
    assert result.status is Status.FAIL_NEEDS_OPERATOR, (
        f"expected FAIL_NEEDS_OPERATOR, got {result.status!r}: {result.detail}"
    )
    assert site_contains in (result.site or ""), (
        f"site {result.site!r} does not name {site_contains!r}"
    )
    assert why_contains in (result.detail or ""), (
        f"detail does not name {why_contains!r}: {result.detail}"
    )


def _unmeasurable(result, *, why_contains: str) -> None:
    assert result.status is Status.CANNOT_MEASURE, (
        f"expected CANNOT_MEASURE, got {result.status!r}: {result.detail}"
    )
    assert why_contains in (result.detail or ""), (
        f"detail does not name {why_contains!r}: {result.detail}"
    )


# ==========================================================================
# NON-VACUITY FIRST. A gate that cannot pass clean measures nothing dirty.
# ==========================================================================


def test_the_REAL_tree_and_the_COPY_both_pass(home: Path) -> None:
    """The gate is green on the shipped tree and on an untouched copy of it."""
    live = _run(REPO)
    assert live.status is Status.PASS, live.detail
    assert "7 arms driving the SHIPPED" in (live.evidence or ""), live.evidence
    copied = _run(home)
    assert copied.status is Status.PASS, copied.detail


def test_the_gate_DECLARES_its_three_subjects() -> None:
    """Coverage is what SUBJECTS names; the ratchet can see nothing else."""
    assert set(gate.SUBJECTS) == {CAPS, CONTENTION, CAPS_CONFIG}


def test_the_gate_is_NON_CORRECTABLE_with_a_stated_reason() -> None:
    """Rule 1/2: a gate that could edit either side manufactures its own green."""
    assert gate.CORRECTABLE is False
    assert "manufacturing its own green" in gate.NON_CORRECTABLE_REASON


def test_the_gate_spells_NO_bucket_name_in_its_EXECUTABLE_code() -> None:
    """ARM 1's reference side is parsed from the spec, never transcribed here.

    Measured over the AST — every string constant that is not a docstring, and
    every identifier — rather than over the raw bytes: the gate's PROSE names
    the buckets while explaining what it does, and a check that reddened on its
    own explanation would be unusable (the same carve-out
    `check_risks_data_only` makes for its `_WATCH_LITERAL_MAX`).
    """
    tree = ast.parse(Path(gate.__file__).read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    executable = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ] + [node.id for node in ast.walk(tree) if isinstance(node, ast.Name)]
    haystack = " ".join(executable).lower()
    for spelled in ("equities", "energy", "metals", "rates"):
        assert spelled not in haystack, (
            f"{spelled!r} appears in the gate's executable code — a gate that "
            "spells its own expected side is a gate agreeing with itself"
        )


# ==========================================================================
# C1 — the SUMMATION plant, and it is the one that matters
# ==========================================================================


def test_a_MAX_shaped_cap_reddens_the_gate(home: Path) -> None:
    """THE FALSIFIER for C1. `sum()` becomes `max()` inside the real module."""
    _plant(
        home,
        CAPS,
        "        total += dollar_risk(exposure, config)",
        "        total = max(total, dollar_risk(exposure, config))",
    )
    _red(
        _run(home),
        site_contains="caps.py:admit",
        why_contains="§7:511 sums the bucket",
    )


def test_the_MAX_plant_removed_leaves_the_same_tree_GREEN(home: Path) -> None:
    """The plant, then its removal. A red that never goes green is not a control."""
    original = (home / CAPS).read_text(encoding="utf-8")
    _plant(
        home,
        CAPS,
        "        total += dollar_risk(exposure, config)",
        "        total = max(total, dollar_risk(exposure, config))",
    )
    assert _run(home).status is Status.FAIL_NEEDS_OPERATOR
    (home / CAPS).write_text(original, encoding="utf-8")
    restored = _run(home)
    assert restored.status is Status.PASS, restored.detail


def test_a_cap_that_counts_only_the_FIRST_exposure_reddens(home: Path) -> None:
    """A second summation defect: the loop stops after one same-bucket position."""
    _plant(
        home,
        CAPS,
        "        total += dollar_risk(exposure, config)\n        contributors += 1",
        "        total += dollar_risk(exposure, config)\n        contributors += 1\n        break",
    )
    _red(
        _run(home),
        site_contains="caps.py:admit",
        why_contains="below the discriminator floor",
    )


def test_a_cap_that_reaches_ACROSS_buckets_reddens(home: Path) -> None:
    """§7:505-510 is SAME-BUCKET ONLY. Delete the filter and the control fires."""
    _plant(
        home,
        CAPS,
        "        if bucket_for(exposure.symbol) is not bucket:\n            continue\n",
        "",
    )
    _red(
        _run(home),
        site_contains="caps.py",
        why_contains="SAME-BUCKET ONLY",
    )


def test_an_ALL_OR_NOTHING_cap_reddens(home: Path) -> None:
    """§7:514 sizes DOWN before it denies. Safe is not the same as correct."""
    _plant(
        home,
        CAPS,
        "    admitted = max(0, min(contracts, fits))",
        "    admitted = contracts if fits >= contracts else 0",
    )
    _red(
        _run(home),
        site_contains="caps.py:admit",
        why_contains="sizes DOWN toward the ceiling",
    )


def test_a_cap_that_ROUNDS_UP_to_one_contract_reddens(home: Path) -> None:
    """The other half of §7:514: deny at zero, never round up to a tradeable lot."""
    _plant(
        home,
        CAPS,
        "    admitted = max(0, min(contracts, fits))",
        "    admitted = max(1, min(contracts, fits))",
    )
    _red(
        _run(home),
        site_contains="caps.py:admit",
        why_contains="denies at zero rather than rounding up",
    )


def test_a_cap_that_names_the_WRONG_binding_constraint_reddens(home: Path) -> None:
    """§16 U5: a rationale that does not name the cap makes the audit wrong."""
    _plant(
        home,
        CAPS,
        "        BindingConstraint.BUCKET_CAP if admitted < contracts else BindingConstraint.NONE",
        "        BindingConstraint.NONE if admitted < contracts else BindingConstraint.NONE",
    )
    _red(
        _run(home),
        site_contains="caps.py:admit",
        why_contains="requires the sizing rationale to name WHICH term bound",
    )


def test_a_RENAMED_bucket_key_in_the_config_reddens(home: Path) -> None:
    """ARM 1: the ceiling table's buckets must be the spec's, and are compared."""
    _plant(home, ALLOCATOR_CONFIG, '"equities": 0.01', '"equity": 0.01')
    result = _run(home)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "disagree with §7:498's locked sentence" in (result.detail or ""), (
        result.detail
    )


# ==========================================================================
# C2 — the FCFS fallback plants
# ==========================================================================


def test_a_fallback_that_RAISES_reddens(home: Path) -> None:
    """§6.6:467-468: a scoring outage must NEVER halt order flow."""
    _plant(
        home,
        CONTENTION,
        "    ordered = fcfs_order(contenders)\n",
        '    raise RuntimeError("scoring outage halted order flow")\n',
    )
    _red(
        _run(home),
        site_contains="contention.py:rank",
        why_contains="must NEVER halt order flow",
    )


def test_an_FCFS_ordered_by_SYMBOL_instead_of_ARRIVAL_reddens(home: Path) -> None:
    """§6.6:466: 'structurally neutral (favors no symbol)', made mechanical."""
    _plant(
        home,
        CONTENTION,
        "key=lambda contender: contender.arrival_seq",
        "key=lambda contender: contender.symbol",
    )
    _red(
        _run(home),
        site_contains="contention.py:rank",
        why_contains="first-come-first-served",
    )


def test_a_fallback_that_names_NO_REASON_reddens(home: Path) -> None:
    """§18: three different outages reaching one ordering differ only by reason."""
    _plant(home, CONTENTION, "        reason=reason,\n", '        reason="",\n')
    _red(
        _run(home),
        site_contains="contention.py:rank",
        why_contains="named no reason",
    )


def test_a_fallback_that_reports_the_WRONG_POLICY_reddens(home: Path) -> None:
    """§6.6:465's fallback is LOCKED; a fallback that calls itself weighted lies."""
    _plant(
        home,
        CONTENTION,
        "        policy=ContentionPolicy.FCFS,\n        ordering=ordered,",
        "        policy=ContentionPolicy.PERFORMANCE_WEIGHTED,\n        ordering=ordered,",
    )
    _red(
        _run(home),
        site_contains="contention.py:rank",
        why_contains="fallback is LOCKED",
    )


def test_a_DECORATIVE_read_seam_reddens(home: Path) -> None:
    """The port is never consulted. In the live state that looks identical."""
    _plant(
        home,
        CONTENTION,
        "    return _weighted(contenders, scores)",
        '    return _fallback(contenders, "the port was never consulted")',
    )
    _red(
        _run(home),
        site_contains="contention.py:rank",
        why_contains="the READ seam is",
    )


def test_a_module_that_ignores_EQUAL_scores_reddens(home: Path) -> None:
    """§6.6:455: equal scores are an FCFS case, and cold start is exactly that."""
    _plant(
        home,
        CONTENTION,
        "    if len(set(scores.values())) <= 1:",
        "    if False:  # equal scores no longer fall back",
    )
    _red(
        _run(home),
        site_contains="contention.py:rank",
        why_contains="EQUAL scores an FCFS",
    )


# ==========================================================================
# C3 — the authority boundary plants
# ==========================================================================


def test_an_AWARD_verb_on_the_contention_module_reddens(home: Path) -> None:
    """§6.6:459-460 gives arbitration to the LIMITER, not to the Allocator."""
    _append(
        home,
        CONTENTION,
        "\n\ndef award(contenders):\n"
        '    """Hands a shared resource to one contender."""\n'
        "    return contenders[0]\n",
    )
    _red(
        _run(home),
        site_contains="contention.py:award",
        why_contains="the authority split crossed",
    )


@pytest.mark.parametrize(
    "verb", ["award", "winner", "grant", "allocate", "assign", "arbitrate"]
)
def test_EVERY_award_verb_is_caught_in_turn(home: Path, verb: str) -> None:
    """The forbidden list is driven member by member, never as a whole."""
    _append(home, CONTENTION, f"\n\ndef {verb}(contenders):\n    return contenders\n")
    _red(
        _run(home),
        site_contains=f"contention.py:{verb}",
        why_contains=f"{verb!r}",
    )


def test_a_COROUTINE_on_the_contention_path_reddens(home: Path) -> None:
    """§6.6:468: an `async def` here is a place order flow can stall."""
    _append(
        home,
        CONTENTION,
        "\n\nasync def rank_later(contenders):\n    return contenders\n",
    )
    _red(
        _run(home),
        site_contains="contention.py:rank_later",
        why_contains="declared `async def`",
    )


# ==========================================================================
# THE MEASURE-NOTHING ROUTES (§7.12), each driven rather than argued
# ==========================================================================


def test_a_MISSING_module_is_CANNOT_MEASURE_and_never_a_PASS(home: Path) -> None:
    """§17: a property proven while its subject is unavailable is not proven."""
    (home / CAPS).unlink()
    _unmeasurable(_run(home), why_contains="no such file")


def test_an_UNIMPORTABLE_module_is_CANNOT_MEASURE(home: Path) -> None:
    """A syntax error is not a finding about §7; it is an unread subject."""
    _append(home, CONTENTION, "\nthis is not python\n")
    _unmeasurable(_run(home), why_contains="cannot load out of")


def test_a_MOVED_spec_sentence_is_CANNOT_MEASURE_not_a_quiet_agreement(
    home: Path,
) -> None:
    """§7.12/2: an unmatched anchor yields an empty expected set."""
    _plant(home, SPEC, "  - **Buckets:** equities", "  - **Groups:** equities")
    _unmeasurable(_run(home), why_contains="did not match its anchor")


def test_an_EMPTY_tick_table_is_CANNOT_MEASURE(home: Path) -> None:
    """The loader refuses a config that cannot cover the spec's own buckets."""
    _plant(
        home,
        CAPS_CONFIG,
        '"tick_value_usd": {\n    "ES": 12.5,',
        '"tick_value_usd": {\n    "XX": 12.5,',
    )
    _unmeasurable(_run(home), why_contains="cannot load out of")


def test_a_SHRUNKEN_symbol_table_trips_the_non_vacuity_floor(home: Path) -> None:
    """§7.12/7: `MIN_CAP_SYMBOLS` is a live floor, not a decorative one.

    Both sides are shrunk together — the seam's bucket map and the tick table —
    because the loader's own boot rule refuses a tick table that does not cover
    the buckets, and that refusal would otherwise mask the floor.
    """
    _plant(home, SEAM, '    "GC": CorrelationBucket.METALS,\n', "")
    _plant(home, SEAM, '    "ZN": CorrelationBucket.RATES,\n', "")
    _plant(home, CAPS_CONFIG, '    "GC": 10.0,\n', "")
    _plant(home, CAPS_CONFIG, '    "ZN": 15.625\n', '    "CL": 10.0\n')
    _plant(home, CAPS_CONFIG, '    "CL": 10.0,\n    "CL": 10.0\n', '    "CL": 10.0\n')
    _unmeasurable(_run(home), why_contains="below the floor of")


def test_the_gate_ANSWERS_the_standing_question_in_its_docstring() -> None:
    """§7.12 is required of every gate at the point it is built."""
    doc = gate.__doc__ or ""
    assert "WHAT WOULD HAVE TO BE TRUE FOR THIS GATE TO PASS" in doc
    assert doc.count("CLOSED:") >= 6, "a route with no mechanism is not closed"


def test_the_gate_states_what_it_CANNOT_prove() -> None:
    """A green here must not read as coverage of §6.6's unbuilt half."""
    doc = gate.__doc__ or ""
    assert "WHAT THIS GATE CANNOT PROVE" in doc
    assert "Scoring process" in doc
    assert "R5" in doc


def test_no_plant_touched_the_repository() -> None:
    """Doctrine C.8, asserted rather than promised: the live tree is still green."""
    live = _run(REPO)
    assert live.status is Status.PASS, live.detail
