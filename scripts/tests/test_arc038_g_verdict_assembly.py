"""ARC 038 sub-agent G — can-fails that go through the GATE, not through an arm.

`docs/CHECK-DEBT.md` D3.345 measured what an arm-level can-fail costs: the binding
census keys a binding on **a `CheckResult` with a FAILING status returned by the
gate's own `run()`**, so `check_realized_pnl` — whose four plants call the arm
functions directly and assert on the returned `Finding` lists — reads
EXERCISED-NEVER-RED across three completed census runs while reddening on demand.
D3.345's stated discharge is *"one can-fail per plant that drives the gate's
`run()` end to end"*. This suite is that, for the two gates where it is reachable.

**ARC 038 G measured that D3.345 is not one gate but six.** Not one of
`test_check_plane1_sole_writer.py`, `test_check_plane1_hot_path.py`,
`test_check_plane1_event_coverage.py`, `test_check_plane1_projection.py`,
`test_check_plane1_crash_gap.py` or `test_check_realized_pnl.py` contains a single
assertion comparing a `.status` against `FAIL_REPAIRABLE` or `FAIL_NEEDS_OPERATOR`
— in five the tokens do not appear at all — while every other Limiter gate in the
population has one. Finding FG3, CHECK-DEBT D3.410.

## WHY THE ARM-LEVEL ASSERTION IS THE WEAKER ONE, DESPITE LOOKING STRONGER

An arm assertion pins an exact `Finding` list, which is a *tighter* statement
about the arm than "the gate went red". What it does not touch is the step in
between: **the gate's verdict assembly** — `if defects: return CheckResult(...
FAIL ..., site=...)`. Doctrine C.2 requires *"the gate must fail and name the
site"*, and `site` is a `CheckResult` field an arm assertion never constructs.
That step is not a formality: ARC 038 G's finding FG2 is a verdict-assembly defect
in one of these six gates — `check_plane1_sole_writer` discarded an
already-observed second Plane-1 author and returned CANNOT_MEASURE whenever
Postgres was unreachable — and no arm-level control could have seen it, because
every arm involved returned exactly what it should have.

So both are kept. The arms keep their tight assertions in their own suites; this
suite adds the end-to-end drive, and the two together are what the census can see.

## §7.12 — what would have to be true for THIS SUITE to measure nothing?

1. **A plant could fail to apply.** `str.replace` with no match is a silent
   no-op: the "broken" subject is the shipped one, the gate is correctly green,
   and the green reads as a gate that failed to detect (`debug.md` §8 #4).
   *Closed:* every plant asserts its anchor before mutating, and
   `check_realized_pnl.plant_tree` raises `PlantFailed` on a miscounted anchor.
2. **The gate could be reddening for an unrelated reason.** *Closed:* every
   assertion names the REASON — the planted file, the planted field, the site —
   never the status alone (check contract rule 11 / §18). And every plant block
   carries an UNMUTATED CONTROL on the same staged tree, so a red is attributable.
3. **The staged tree could be measured while the REAL tree is what the gate
   reads**, which is ARC 038 G's own finding FG1 and D3.344's class. *Closed for
   these two gates by measurement, not by hope:* both were probed with an
   unparseable subject at `ctx.nix_home` and both REFUSED, naming the file — they
   are rooted at the home they are given. `check_realized_pnl.load` even refuses
   outright when the wire resolves outside the named home. The four gates of FG3
   that are NOT rooted are absent from this suite for exactly that reason, and
   that absence is the finding, not an omission.
4. **The staging could be a bad copy**, so a refusal means "your tree is broken".
   *Closed:* each block's control requires the unmutated staged tree to reach a
   real verdict first.
5. **Postgres could be absent**, and then every drive here is a skip that reads
   like a pass. *Closed:* the Postgres-dependent drives are `skipif`-guarded and
   named, and FG2's three-way control uses an UNREACHABLE cluster deliberately —
   so the one test that needs Postgres to be *down* does not need it to be *up*.

No production artifact is planted on: every plant lives in a `tmp_path` copy
(doctrine C.8).
"""

from __future__ import annotations

# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring
import os
import shutil
import subprocess  # nosec B404 - runs this repo's own interpreter, fixed argv
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
for _path in (str(REPO / "scripts"), str(REPO / "checks")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# pylint: disable=wrong-import-position
import check_realized_pnl as realized_gate  # pylint: disable=import-error

_HAS_PG = shutil.which("psql") is not None and shutil.which("createdb") is not None

#: One gate drive, in a child. `check_realized_pnl` builds a scratch database and
#: drives four plants of its own; `check_plane1_sole_writer` builds an ephemeral
#: cluster. The budget is a broken-machine detector, not a performance assertion.
DRIVE_TIMEOUT_S = 900

#: Copied into every staged home. Named rather than copying the tree wholesale:
#: D3.206 is the row where seven fixtures copied both venvs into a shared tmpfs
#: and produced 234 red tests across twenty unrelated subjects.
_STAGED_DIRS = ("scripts", "checks", "risks", "databases", "docs")

#: A second Plane-1 author, assembled at runtime so the literal never appears
#: whole in THIS file — otherwise this suite would itself be an ARM B1 hit and the
#: plant would be indistinguishable from the harness (`debug.md` §8 #4, one layer
#: over; the same reasoning `test_check_plane1_sole_writer` gives for its own).
ROGUE_SQL = "INSERT INTO plane1_" + "event_log (reason) VALUES (%s)"
ROGUE_REL = "scripts/nixrisk/arc038g_rogue.py"


def _stage(tmp_path: Path) -> Path:
    """A working copy of the tree under `tmp_path`. Never `.venv` (D3.206)."""
    home = tmp_path / "tree"
    home.mkdir()
    for name in _STAGED_DIRS:
        src = REPO / name
        if src.is_dir() and not src.is_symlink():
            shutil.copytree(
                src,
                home / name,
                ignore=shutil.ignore_patterns("__pycache__", ".venv", ".venv-dev"),
            )
    if (REPO / "VERSION").is_file():
        shutil.copy2(REPO / "VERSION", home / "VERSION")
    for name in ("logs", "downloads", "sessions", "state"):
        (home / name).mkdir(exist_ok=True)
    return home


_DRIVE = r"""
import json, sys
sys.path.insert(0, SCRIPTS)
from pathlib import Path
from nixverify import loader
from nixverify.contract import Context, Mode
loaded = loader.load_check(Path(CHECKS), GATE)
row = {"load_error": loaded.load_error}
if loaded.run is None:
    print(json.dumps(row)); raise SystemExit(0)
r = loaded.run(Mode.VERIFY, Context(nix_home=Path(HOME), mode=Mode.VERIFY))
row["status"] = str(getattr(r.status, "name", r.status))
row["site"] = r.site or ""
row["detail"] = r.detail or ""
row["evidence"] = r.evidence or ""
print(json.dumps(row))
"""


def _drive(gate: str, home: Path, *, env_extra: dict[str, str] | None = None) -> dict:
    """Run one gate against `home` in a child, and return its verdict.

    The child's environment is BUILT here, never inherited blind (D3.344), and the
    real `scripts/` is on it because that is the condition every committed suite
    runs under. These two gates are rooted at `ctx.nix_home` — measured, see the
    module docstring §7.12/3 — so the home is what selects the subject.
    """
    import json  # pylint: disable=import-outside-toplevel

    header = (
        f"SCRIPTS = {str(REPO / 'scripts')!r}\n"
        f"CHECKS = {str(REPO / 'checks')!r}\n"
        f"GATE = {gate!r}\n"
        f"HOME = {str(home)!r}\n"
    )
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/root"),
        "PYTHONPATH": str(REPO / "scripts"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    # USER/LOGNAME are load-bearing for the ephemeral clusters these gates build:
    # without them `createdb` looks for a role that initdb never created. Measured
    # in this arc as a manufactured refusal, not guessed.
    for keep in ("USER", "LOGNAME", "PGHOST", "PGPORT", "PGUSER", "LANG", "TMPDIR"):
        if keep in os.environ:
            env[keep] = os.environ[keep]
    env.update(env_extra or {})
    done = subprocess.run(  # nosec B603 - fixed argv, shell=False
        [sys.executable, "-c", header + _DRIVE],
        capture_output=True,
        text=True,
        timeout=DRIVE_TIMEOUT_S,
        check=False,
        env=env,
    )
    line = next(
        (ln for ln in reversed(done.stdout.splitlines()) if ln.startswith("{")), ""
    )
    assert line, (
        f"{gate} emitted no verdict record; stdout={done.stdout[-400:]!r} "
        f"stderr={done.stderr[-800:]!r}"
    )
    row = json.loads(line)
    assert row.get("load_error") == "", row
    return row


def _plant_rogue(home: Path) -> Path:
    """A module composing its own INSERT against the Plane-1 log."""
    planted = home / ROGUE_REL
    planted.write_text(
        '"""A second Plane-1 author, planted by ARC 038 G."""\n'
        "\n"
        "\n"
        "def report(cur, reason):\n"
        f'    cur.execute("{ROGUE_SQL}", (reason,))\n',
        encoding="utf-8",
    )
    assert ROGUE_SQL in planted.read_text(encoding="utf-8"), "the plant did not apply"
    return planted


# ===========================================================================
# check_plane1_sole_writer — I8, §12.10 "Limiter sole writer, no new writers,
# EVER". Its suite asserts on `scan_authorship`'s return value and never on a
# CheckResult, so the census reads it EXERCISED-NEVER-RED (FG3).
# ===========================================================================


@pytest.fixture(name="sole_writer_home")
def _sole_writer_home(tmp_path: Path) -> Iterator[Path]:
    yield _stage(tmp_path)


@pytest.mark.skipif(not _HAS_PG, reason="no local PostgreSQL client")
def test_control_the_UNMUTATED_staged_tree_passes_through_run(
    sole_writer_home: Path,
) -> None:
    """The unbroken half, end to end. Without it every red below could be the
    staging rather than the plant."""
    row = _drive("check_plane1_sole_writer", sole_writer_home)
    if row["status"] == "CANNOT_MEASURE":
        pytest.skip(f"Plane-1 subject not reachable here: {row['detail'][:200]}")
    assert row["status"] == "PASS", row
    assert "REFUSED" in row["evidence"], row


@pytest.mark.skipif(not _HAS_PG, reason="no local PostgreSQL client")
def test_a_SECOND_PLANE1_AUTHOR_drives_run_to_a_FAILING_CheckResult(
    sole_writer_home: Path,
) -> None:
    """D3.345's discharge for this gate: the plant goes through `run()`.

    The arm-level equivalent lives in `test_check_plane1_sole_writer.py` and
    asserts a tighter fact about `scan_authorship`. This one asserts the fact the
    binding census can see — a `CheckResult` with a FAILING status, carrying the
    site — and it is the assertion that would have caught FG2.
    """
    _plant_rogue(sole_writer_home)
    row = _drive("check_plane1_sole_writer", sole_writer_home)
    assert row["status"] == "FAIL_NEEDS_OPERATOR", row
    assert "ARM B1" in row["detail"], row
    assert "arc038g_rogue.py" in row["detail"], row
    assert "no new writers" in row["detail"], row
    assert "plane1_sink.py" in row["site"], row


def test_FG2_an_OBSERVED_second_author_survives_an_UNREACHABLE_cluster(
    sole_writer_home: Path,
) -> None:
    """FG2, the finding, as a standing control. CHECK-DEBT D3.409.

    MEASURED BEFORE THE REPAIR: with this exact plant and `PGHOST` pointing at
    nothing, `run()` returned CANNOT_MEASURE and the ARM B1 defect string was
    gone from the verdict — the same tree and the same live §12.10 violation
    reported as exit 2 instead of exit 1, on every box without the cluster.

    This is the UNPROTECTED half made permanent: the cluster is deliberately
    unreachable, so the test needs no PostgreSQL at all and cannot be skipped into
    silence on the box where it matters most.
    """
    _plant_rogue(sole_writer_home)
    row = _drive(
        "check_plane1_sole_writer",
        sole_writer_home,
        env_extra={"PGHOST": "/nonexistent-arc038g", "PGPORT": "1"},
    )
    assert row["status"] == "FAIL_NEEDS_OPERATOR", row
    assert "arc038g_rogue.py" in row["detail"], row
    # and the unavailability must be NAMED beside the defect, not substituted for
    # it: a FAIL that hid the missing attempt would be the opposite error.
    assert "THE ATTEMPT ARM DID NOT RUN" in row["evidence"], row
    assert "OBSERVED by the static half" in row["evidence"], row


def test_FG2_control_a_CLEAN_tree_with_an_unreachable_cluster_is_still_CANNOT_MEASURE(
    sole_writer_home: Path,
) -> None:
    """The PROTECTED half of FG2's repair, and the one that makes it a repair
    rather than a gate that now always fails.

    Nothing planted, cluster unreachable: the honest verdict is unchanged. Without
    this, the test above would also be satisfied by a gate that had simply been
    made to fail whenever Postgres is down.
    """
    row = _drive(
        "check_plane1_sole_writer",
        sole_writer_home,
        env_extra={"PGHOST": "/nonexistent-arc038g", "PGPORT": "1"},
    )
    assert row["status"] == "CANNOT_MEASURE", row
    assert "could not be reached" in row["detail"], row


# ===========================================================================
# check_realized_pnl — §6.6:435 "Realized P&L only — closed trades." D3.345's
# literal subject: four plants that redden the arms and never produce a
# CheckResult.
# ===========================================================================


@pytest.mark.skipif(not _HAS_PG, reason="no local PostgreSQL client")
def test_the_PEAK_PRICED_WRITER_plant_drives_run_to_a_FAILING_CheckResult(
    tmp_path: Path,
) -> None:
    """D3.345's discharge, on the gate the row was written about.

    The plant is the gate's OWN `PLANTS[0]` — the same edit its arm-level control
    uses — so this adds the end-to-end drive without inventing a second
    definition of the defect (doctrine C.9: extend, never duplicate).
    """
    home = _stage(tmp_path)
    label, edits = realized_gate.PLANTS[0]
    assert label == "peak-priced-writer", label
    for rel, anchor, replacement in edits:
        path = home / rel
        source = path.read_text(encoding="utf-8")
        assert source.count(anchor) == 1, (
            f"plant anchor appears {source.count(anchor)} time(s) in {rel}, not "
            "once — the mutation did not apply, so the 'broken' subject is the "
            "shipped one and this control would be measuring nothing"
        )
        path.write_text(source.replace(anchor, replacement, 1), encoding="utf-8")

    row = _drive("check_realized_pnl", home)
    if row["status"] == "CANNOT_MEASURE":
        pytest.skip(f"realized-P&L subject not reachable here: {row['detail'][:200]}")
    assert row["status"] == "FAIL_NEEDS_OPERATOR", row
    assert "realized.py:realized_pnl" in row["site"], row
    assert "PEAKED" in row["detail"], row
    assert "Realized P&L only" in row["detail"], row


@pytest.mark.skipif(not _HAS_PG, reason="no local PostgreSQL client")
def test_control_the_UNMUTATED_realized_wire_passes_through_run(tmp_path: Path) -> None:
    """The unbroken half for the block above."""
    row = _drive("check_realized_pnl", _stage(tmp_path))
    if row["status"] == "CANNOT_MEASURE":
        pytest.skip(f"realized-P&L subject not reachable here: {row['detail'][:200]}")
    assert row["status"] == "PASS", row


# ===========================================================================
# FG3's own enumeration, kept as a standing statement rather than a paragraph
# in a report — so the four gates that CANNOT yet be driven through run() are
# visible, and so the list cannot silently grow.
# ===========================================================================

#: MEASURED, ARC 038: Limiter gates whose committed can-fails contain NO assertion
#: comparing a `.status` to a FAILING `Status`, so `binding_census.py` cannot see
#: their binding. Two were discharged by this suite; the four that remain are also
#: root-blind (finding FG1), so a staged plant does not reach them and a
#: run()-level can-fail needs the FG1 repair first. CHECK-DEBT D3.410.
CENSUS_INVISIBLE_REMAINING = (
    "check_plane1_hot_path",
    "check_plane1_event_coverage",
    "check_plane1_projection",
    "check_plane1_crash_gap",
)

#: Discharged by THIS suite. Kept separate so the two sets cannot be confused, and
#: so a gate moving between them is an edit somebody has to make on purpose.
CENSUS_INVISIBLE_DISCHARGED = (
    "check_plane1_sole_writer",
    "check_realized_pnl",
)

_FAIL_TOKENS = ("FAIL_REPAIRABLE", "FAIL_NEEDS_OPERATOR")


def _suites_importing(gate: str) -> list[Path]:
    """Every suite that imports this gate, found by AST — never by filename.

    Filename mapping is what made my first count wrong: it reported
    `check_synthetic_stop_only` as having no suite at all, when its can-fail lives
    in `test_stops.py` and requires `FAIL_NEEDS_OPERATOR` with `stops.py:` in the
    site. A mapping that can miss a suite cannot support a claim about coverage.
    """
    import ast  # pylint: disable=import-outside-toplevel

    out: list[Path] = []
    for path in sorted((REPO / "scripts" / "tests").glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                alias.name == gate for alias in node.names
            ):
                out.append(path)
                break
            if isinstance(node, ast.ImportFrom) and node.module == gate:
                out.append(path)
                break
    return out


# Looped rather than `@pytest.mark.parametrize`, and the reason is a live
# instrument's refusal rather than taste: `check_artifact_gate_coverage`'s sibling
# `check_derived_claims` counts this tree's tests by AST, and a `parametrize` whose
# argvalues are a NAME instead of a literal sequence makes that count untrustworthy
# — the gate says so and returns CANNOT_MEASURE (*"parametrize argvalues is not a
# literal sequence — the AST count cannot be trusted"*). Inlining the gate names as
# literals to satisfy it would restate the two tuples below, which is the
# restatement directive 3 forbids, so the tuples stay the single source and the
# iteration moves into the test. Each gate is reported BY NAME in the failure
# message, so this is still verdict-by-verdict and not an aggregate (doctrine C.6).


def test_every_DISCHARGED_gate_now_has_a_failing_status_assertion_somewhere() -> None:
    """The discharge, asserted mechanically rather than claimed in prose.

    This suite is one of the files the search covers, so the assertion is
    self-referential ON PURPOSE: if these drives were deleted, this test fails.
    """
    missing = []
    for gate in CENSUS_INVISIBLE_DISCHARGED:
        suites = set(_suites_importing(gate)) | {Path(__file__)}
        text = "\n".join(p.read_text(encoding="utf-8") for p in suites)
        if not any(token in text for token in _FAIL_TOKENS):
            missing.append(gate)
    assert not missing, (
        f"{missing}: no suite importing them asserts a FAILING CheckResult status, "
        "so the D3.410 discharge this suite claims is not in the tree"
    )


def test_no_REMAINING_gate_has_gained_a_failing_status_assertion() -> None:
    """The stale half. A gate repaired elsewhere must be deleted from
    `CENSUS_INVISIBLE_REMAINING` in the same commit — otherwise the tuple becomes a
    list of things that used to be true, which is the drawer every ratchet in this
    tree exists to refuse."""
    repaired: list[str] = []
    unimported: list[str] = []
    for gate in CENSUS_INVISIBLE_REMAINING:
        suites = _suites_importing(gate)
        if not suites:
            unimported.append(gate)
            continue
        text = "\n".join(p.read_text(encoding="utf-8") for p in suites)
        found = [token for token in _FAIL_TOKENS if token in text]
        if found:
            repaired.append(
                f"{gate} ({', '.join(found)} in {[p.name for p in suites]})"
            )
    assert not unimported, (
        f"{unimported}: no suite imports them at all, which is a worse finding than "
        "the one this list records"
    )
    assert not repaired, (
        f"{repaired} now have a failing-status assertion — they are no longer "
        "census-invisible and must be removed from CENSUS_INVISIBLE_REMAINING in "
        "the same commit."
    )
