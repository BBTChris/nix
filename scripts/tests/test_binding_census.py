"""The binding census's own can-fail — including the defect it was caught having.

ARC 027 / 0.2. `binding_census.py` decides, every arc, which gates are BOUND.
An instrument in that position is exactly the thing §0f was written about: if it
is wrong, it is wrong about *everything*, quietly, and the table it publishes
looks the same either way.

**The property this file is really about is non-perturbation**, and it is here
because the instrument failed it on its first run rather than because it was
anticipated. The first cut opened its record file with `open()` once per
observation; `nixverify.observe` hooks the `open` AUDIT EVENT; so the tracer's
own bookkeeping landed inside the observation window as a `file-write:` claim
charged to whichever gate was being observed, and five controls went red. The
measurement changed the measurement. Two tests below hold that closed — one
proving the tracer is invisible, and one CONTROL proving the invisibility is a
property of the mechanism rather than of the day, by putting `open()` back and
watching the claim reappear.
"""

# pylint: disable=invalid-name,duplicate-code
# `invalid-name`: the test names SHOUT the property under test — the project's
# standing convention across every control file.
# `duplicate-code`: the sys.path bootstrap and the synthetic-check text are
# shared shapes across every control file by design (see
# test_check_python_runtime.py) — one helper module would let a single edit
# un-bind several instruments at once.

from __future__ import annotations

import collections
import json
import os
import sys
import textwrap
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))
if str(REPO / "scripts" / "tests") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "tests"))

# pylint: disable=wrong-import-position
import binding_census as census  # pylint: disable=import-error
import binding_tracer as tracer  # pylint: disable=import-error
from nixverify.observe import observe_check  # pylint: disable=import-error

#: A check that returns a FAIL, so the tracer has something to see. It is a real
#: `run(mode, ctx) -> CheckResult`, because that return is the observation point.
SYNTHETIC = textwrap.dedent(
    '''
    """A synthetic check. Never registered — census plant material only."""
    from nixverify.contract import CheckResult, Status

    DEPENDS_ON = ()
    RESOURCES = ()


    def run(mode, ctx):
        return CheckResult(
            name="check_plantling",
            status=Status.FAIL_NEEDS_OPERATOR,
            site="synthetic",
            detail="planted",
        )
    '''
).strip()

#: The honest sitecustomize the driver generates: import the tracer, nothing else.
SITE_QUIET = "import sys\nsys.path.insert(0, {tests!r})\nimport binding_tracer\n"

#: THE PLANT. The same record, written with `open()` — the spelling that was
#: measured perturbing the observer — and written AT THE SAME MOMENT: from inside
#: the monitoring callback, which fires as the check's `run` returns, which is
#: inside the observation window. Planting the `open()` at import instead would
#: prove nothing, because import is outside the window BY DESIGN; that is the
#: whole content of `_open_sink`.
SITE_LOUD = (
    "import sys\n"
    "sys.path.insert(0, {tests!r})\n"
    "import json, os\n"
    "import binding_tracer\n"
    "def _loud(check, status, module):\n"
    "    row = dict(check=check, status=status, module=module, canonical=True,\n"
    "               sha='', test='control', pid=os.getpid())\n"
    "    with open(os.environ['NIX_BINDING_CENSUS_OUT'], 'a', encoding='utf-8') as h:\n"
    "        h.write(json.dumps(row) + '\\n')\n"
    "binding_tracer._record = _loud\n"
)


def _counters(**kwargs: dict[str, int]) -> dict:
    """One census row, built from raw counters — the shape `verdict` reads."""
    entry: dict[str, object] = {
        "shipped": collections.Counter(),
        "modified": collections.Counter(),
        "unknown": collections.Counter(),
        "tests": set(),
        "modified_paths": set(),
    }
    for where, counts in kwargs.items():
        entry[where] = collections.Counter(counts)
    return entry


# ===========================================================================
# NON-VACUITY FIRST (doctrine C.3) — the ladder, before any plant.
# ===========================================================================


def test_the_verdict_ladder_is_derived_from_counters_never_from_a_table() -> None:
    """All four rungs, so a future edit cannot collapse two of them unnoticed."""
    assert census.verdict(_counters(shipped={"FAIL_NEEDS_OPERATOR": 1})) == "BOUND"
    assert (
        census.verdict(_counters(modified={"FAIL_NEEDS_OPERATOR": 1}))
        == "BOUND-BY-MODIFIED-GATE"
    )
    only_green = {"PASS": 9}  # nosec B105 - a status tally, not a credential
    assert census.verdict(_counters(shipped=only_green)) == "EXERCISED-NEVER-RED"
    assert census.verdict(_counters()) == "UNBOUND"


def test_CANNOT_MEASURE_and_GUARDED_are_not_counted_as_a_can_fail() -> None:
    """§10: a property proven while its subject is unavailable is not proven.

    A control that only ever drove a gate to CANNOT_MEASURE showed that the gate
    notices an ABSENT subject, which is not the same claim as noticing a broken
    one. Merging them would have called `check_python_deps` bound on the strength
    of one unreachable-`pip` control.
    """
    assert (
        census.verdict(_counters(shipped={"CANNOT_MEASURE": 5, "GUARDED": 5}))
        == "EXERCISED-NEVER-RED"
    )


def test_every_check_ON_DISK_is_a_row_even_with_zero_observations() -> None:
    """D3.25's shape: a gate nobody touched must be a LOUD row, not an absent one.

    Rows come from the `checks/` glob, never from the observations, because a
    table built from what was seen cannot contain what was never seen — which is
    precisely how `check_verify_logging` stayed invisible for two arcs.
    """
    names = census.registered_checks()
    assert len(names) >= 20, names
    table = census.census([], names)
    assert set(table) == set(names)
    assert {census.verdict(entry) for entry in table.values()} == {"UNBOUND"}


def test_a_red_in_a_MODIFIED_gate_does_not_bind_the_shipped_one() -> None:
    """Location is not identity; SOURCE is. Both halves, on one real check.

    The same observation, differing only in `sha`, must land in different buckets
    — otherwise a control that plants INTO the gate (mutation-testing its own
    derivation) would read as a can-fail of the program this repo installs.
    """
    name = census.registered_checks()[0]
    shipped_sha = census.shipped_digests([name])[name]
    assert shipped_sha, name
    red = {"status": "FAIL_NEEDS_OPERATOR", "test": "t"}
    observed = [
        {"check": name, "sha": shipped_sha, **red},
        {"check": name, "sha": "0" * 64, **red},
    ]
    table = census.census(observed, [name])
    assert table[name]["shipped"]["FAIL_NEEDS_OPERATOR"] == 1
    assert table[name]["modified"]["FAIL_NEEDS_OPERATOR"] == 1
    assert census.verdict(census.census(observed[1:], [name])[name]) == (
        "BOUND-BY-MODIFIED-GATE"
    )


def test_a_suite_that_COLLECTED_NOTHING_is_REFUSED_by_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Refusal arm one, asserted by REASON rather than by exit code (§18).

    Exit 2 is a shared namespace here — the floor arm below reaches the same
    integer — so the code alone would not tell an operator which of the two
    happened, and the two need opposite responses.
    """
    out = tmp_path / "empty.jsonl"
    out.write_text("", encoding="utf-8")
    assert not census.read_observations(out)
    code = census.main(
        ["--observations", str(out), "--", "-k", "a_name_that_matches_no_test_at_all"]
    )
    assert code == 2
    assert "collected no tests" in capsys.readouterr().err


def test_a_RUN_THAT_SAW_TOO_LITTLE_is_REFUSED_and_never_an_empty_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The purest vacuous pass this instrument has: a monitor that never fired.

    Zero observations and "no gate in this system can fail" are the same file.
    This arm runs tests — so it is past the collection guard — and still sees
    nothing, because the tests it runs drive no gate. That must refuse by NAME.
    """
    out = tmp_path / "thin.jsonl"
    code = census.main(
        [
            "--observations",
            str(out),
            "--",
            "-k",
            "test_the_verdict_ladder_is_derived_from_counters_never_from_a_table",
        ]
    )
    assert code == 2
    assert "below the credibility floor" in capsys.readouterr().err


# ===========================================================================
# THE PROPERTY THAT WAS MEASURED FAILING — non-perturbation, and its control.
# ===========================================================================


def _observe_with_tracer(tmp_path: Path, sitecustomize: str) -> tuple[list[str], list]:
    """Observe a synthetic check in a child carrying `sitecustomize`.

    Returns `(claims the observer recorded, rows the tracer wrote)`. The child is
    spawned by `observe_check` with NO custom env, so it inherits what is set
    here — which is exactly how the real census reaches spawned checks.
    """
    checks = tmp_path / "checks"
    checks.mkdir()
    (checks / "check_plantling.py").write_text(SYNTHETIC, encoding="utf-8")
    site = tmp_path / "site"
    site.mkdir()
    (site / "sitecustomize.py").write_text(
        sitecustomize.format(tests=str(REPO / "scripts" / "tests")), encoding="utf-8"
    )
    out = tmp_path / "observations.jsonl"

    previous = {key: os.environ.get(key) for key in ("PYTHONPATH", *_TRACER_VARS)}
    os.environ["PYTHONPATH"] = os.pathsep.join(
        [str(site), str(REPO / "scripts"), str(REPO / "scripts" / "tests")]
    )
    os.environ[tracer.OUT_VAR] = str(out)
    os.environ[tracer.CHECKS_VAR] = str(checks)
    os.environ[tracer.TEST_VAR] = "control"
    try:
        run = observe_check(checks, "check_plantling", tmp_path)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    rows = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
    return list(run.claims), rows


_TRACER_VARS = (tracer.OUT_VAR, tracer.CHECKS_VAR, tracer.TEST_VAR)


def test_NONVACUITY_the_tracer_actually_records_from_a_SPAWNED_process(
    tmp_path: Path,
) -> None:
    """Before the invisibility claim means anything, the tracer must be WORKING.

    An instrument that records nothing is trivially invisible. This is the arm
    that makes the next test a property rather than a tautology.
    """
    _, rows = _observe_with_tracer(tmp_path, SITE_QUIET)
    assert [row["status"] for row in rows] == ["FAIL_NEEDS_OPERATOR"], rows
    assert rows[0]["check"] == "check_plantling"
    assert rows[0]["canonical"] is True


def test_the_tracer_is_INVISIBLE_to_the_resource_observer(tmp_path: Path) -> None:
    """The measurement must not change the measurement. Named site, not a count."""
    claims, rows = _observe_with_tracer(tmp_path, SITE_QUIET)
    assert rows, "the tracer did not fire; invisibility would be meaningless"
    sink = str(tmp_path / "observations.jsonl")
    assert not [claim for claim in claims if sink in claim], claims


def test_CONTROL_a_tracer_that_uses_open_IS_visible_to_the_observer(
    tmp_path: Path,
) -> None:
    """The plant: put `open()` back, and the claim the last test forbids returns.

    This is what actually happened — five controls in `test_check_observed_
    resource_claims.py` and `test_observe.py` went red because the census was
    writing its record with `open()`. Without this arm the previous test proves
    only that nothing wrote a file today.
    """
    claims, _ = _observe_with_tracer(tmp_path, SITE_LOUD)
    sink = str(tmp_path / "observations.jsonl")
    offending = [claim for claim in claims if sink in claim]
    assert offending, (
        "the observer did not see an `open()` on the sink — either the audit "
        "hook stopped covering `open`, or this control is no longer planting "
        "anything, and in both cases the invisibility test above is vacuous"
    )
    assert offending[0].startswith("file-write:"), offending


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
