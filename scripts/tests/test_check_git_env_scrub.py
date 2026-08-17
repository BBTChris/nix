"""`check_git_env_scrub` must REDDEN on the calls D3.205 was made of.

A gate over a rule everybody already follows is indistinguishable from a gate
that measures nothing. Every arm here therefore drives the gate against a tree
or a source that CONTAINS the defect, and asserts the gate says so **by
reason** — the file, the line, the resolved `env=` expression — never by exit
code (check contract §11/§18).

The three shapes that mattered are each driven, because each is a real call in
this tree and each is a different AST:

  * `subprocess.run(["git", ...])`                — the plain list
  * `subprocess.run(base + args)`                 — `scripts/monitor.py`
  * `subprocess.run(("git",) + args)`             — `scripts/runtime_gate.py`

And the two ways a green here could be a lie are driven as their own arms:

  * **the analyser going blind** — it flags nothing because it can no longer
    tell a scrubbed call from an inherited one, and
  * **the control going silent** — the unscrubbed half stops corrupting,
    which is exactly what an inherited `GIT_WORK_TREE` in the harness does and
    is where the defect masked itself twice in ARC 035.

Every fixture git call runs under `scrubbed_env` (doctrine C.8): the fixture
that builds the isolation must not be the thing that breaks it, which is how
ARC 025 lost an index.
"""

# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring
# Test names spell the OUTCOME they assert. The sys.path bootstrap and the
# scrubbed fixture-git helper are repeated per module DELIBERATELY — a scrub
# nobody sees at the call site is how private spellings of it drifted apart.
from __future__ import annotations

import shutil
import subprocess  # nosec B404 - fixed argv, shell=False, tmp_path only
import sys
import textwrap
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
for _extra in (str(REPO / "checks"), str(REPO / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

# pylint: disable=wrong-import-position
import check_git_env_scrub as gate  # pylint: disable=import-error
from nixverify.contract import Context, Mode, Status  # pylint: disable=import-error
from nixverify.gitenv import scrubbed_env  # pylint: disable=import-error

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git is the instrument here"
)

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def _git(cwd: Path, *args: str) -> None:
    """One git command in a throwaway repository, environment scrubbed.

    `env=scrubbed_env(...)` IS THE POINT, not boilerplate: this suite runs
    inside `pre-commit`, which git invokes with `GIT_DIR` and `GIT_INDEX_FILE`
    exported, and those outrank `cwd`. The identity rides `extra`, AFTER the
    scrub, where it is visible.
    """
    proc = subprocess.run(  # nosec B603 B607 - fixed argv, shell=False, tmp_path only
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env=scrubbed_env(extra=_IDENTITY),
    )
    assert proc.returncode == 0, f"git {args}: {proc.stderr}"


# ---------------------------------------------------------------------------
# The analyser, driven over sources whose answer is known by construction
# ---------------------------------------------------------------------------

SCRUBBED_CALL = """
import subprocess
from nixverify.gitenv import scrubbed_env
def f():
    subprocess.run(["git", "status"], env=scrubbed_env())
"""

INHERITED_CALL = """
import subprocess
def f():
    subprocess.run(["git", "status"])
"""


def _sites(source: str, path: str = "scripts/probe.py", modules=None):
    found, error = gate.scan_source(path, textwrap.dedent(source), modules)
    assert not error, error
    return found


def test_a_bare_git_call_with_no_env_is_reported_as_inherited() -> None:
    bad = gate.offenders(_sites(INHERITED_CALL))
    assert [s.where for s in bad] == ["scripts/probe.py:4"]
    assert bad[0].env_expr == "<absent>", (
        "the finding must name the resolved env expression — an exit code "
        "cannot distinguish a missing env from a wrong one (§18)"
    )


def test_a_call_through_scrubbed_env_is_not_reported() -> None:
    assert not gate.offenders(_sites(SCRUBBED_CALL))


@pytest.mark.parametrize(
    ("expr", "why"),
    [
        ("os.environ", "the ambient environment IS the hazard"),
        ("None", "env=None means inherit, which is the defect spelled out"),
        ("dict(os.environ)", "a copy of the ambient environment is still ambient"),
        (
            '{k: v for k, v in os.environ.items() if not k.startswith("GIT_")}',
            (
                "a private re-spelling of the scrub is the drift gitenv.py "
                "exists to stop — five of them were on this tree"
            ),
        ),
    ],
)
def test_an_env_that_is_not_the_scrub_is_reported(expr: str, why: str) -> None:
    source = f"""
    import os
    import subprocess
    def f():
        subprocess.run(["git", "status"], env={expr})
    """
    bad = gate.offenders(_sites(source))
    assert len(bad) == 1, why

    # `ast.unparse` normalises quoting, so the comparison is quote-insensitive.
    # It is still a comparison against the WRITTEN expression: the finding has
    # to name what it saw, not merely that it failed (§18).
    def _canon(text: str) -> str:
        return text.replace(" ", "").replace("'", '"')

    assert _canon(bad[0].env_expr) == _canon(expr)


def test_the_monitor_shape_of_a_concatenated_argv_is_detected() -> None:
    """`scripts/monitor.py`: `base = ["git", ...]` then `run(base + args)`."""
    source = """
    import subprocess
    def f(args):
        base = ["git", "-C", "/somewhere"]
        subprocess.run(base + args)
    """
    assert [s.where for s in gate.offenders(_sites(source))] == ["scripts/probe.py:5"]


def test_the_runtime_gate_shape_of_a_tuple_argv_is_detected() -> None:
    """`scripts/runtime_gate.py`: `run(("git",) + args)`."""
    source = """
    import subprocess
    def f(args):
        subprocess.run(("git",) + args)
    """
    assert [s.where for s in gate.offenders(_sites(source))] == ["scripts/probe.py:4"]


def test_an_absolute_git_path_is_still_a_git_call() -> None:
    source = """
    import subprocess
    GIT = "/usr/bin/git"
    def f():
        subprocess.run([GIT, "status"])
    """
    assert len(gate.offenders(_sites(source))) == 1


def test_a_non_git_subprocess_is_not_reported() -> None:
    source = """
    import subprocess
    def f():
        subprocess.run(["ruff", "check"])
    """
    assert not _sites(source)


def test_a_same_file_helper_returning_the_scrub_is_followed() -> None:
    source = """
    import subprocess
    from nixverify.gitenv import scrubbed_env
    def _env():
        return scrubbed_env()
    def f():
        subprocess.run(["git", "status"], env=_env())
    """
    assert not gate.offenders(_sites(source))


def test_a_LOCAL_function_merely_NAMED_scrubbed_env_buys_nothing() -> None:
    """The spelling is not the mechanism.

    `scripts/harness.py` and `scripts/monitor.py` legitimately define a local
    `scrubbed_env` fallback — they are copied into throwaway trees with no
    `nixverify` package — and both IMPORT the real one above it inside a
    `try:`. That import is what the gate keys on, so the documented exception
    resolves and a module that only invents the name does not.
    """
    source = """
    import os
    import subprocess
    def scrubbed_env():
        return dict(os.environ)
    def f():
        subprocess.run(["git", "status"], env=scrubbed_env())
    """
    assert len(gate.offenders(_sites(source))) == 1

    imported = """
    import os
    import subprocess
    try:
        from nixverify.gitenv import scrubbed_env
    except ImportError:
        def scrubbed_env(env=None):
            src = os.environ if env is None else env
            return {k: v for k, v in src.items() if not k.startswith("GIT_")}
    def f():
        subprocess.run(["git", "status"], env=scrubbed_env())
    """
    assert not gate.offenders(_sites(imported))


def test_a_same_file_helper_that_does_not_scrub_is_reported() -> None:
    source = """
    import os
    import subprocess
    def _env():
        return dict(os.environ)
    def f():
        subprocess.run(["git", "status"], env=_env())
    """
    assert len(gate.offenders(_sites(source))) == 1


def test_one_cross_module_hop_into_a_gate_helper_is_followed() -> None:
    """`env=gate._clean_git_env()` — the shape three suites use on purpose."""
    other = """
    from nixverify.gitenv import scrubbed_env
    def _clean_git_env():
        return scrubbed_env()
    """
    source = """
    import subprocess
    import check_hook_suite as gate
    def f():
        subprocess.run(["git", "status"], env=gate._clean_git_env())
    """
    modules = {"check_hook_suite": textwrap.dedent(other)}
    assert not gate.offenders(_sites(source, modules=modules))


def test_a_cross_module_helper_that_does_not_scrub_is_reported() -> None:
    other = """
    import os
    def _clean_git_env():
        return dict(os.environ)
    """
    source = """
    import subprocess
    import check_hook_suite as gate
    def f():
        subprocess.run(["git", "status"], env=gate._clean_git_env())
    """
    modules = {"check_hook_suite": textwrap.dedent(other)}
    assert len(gate.offenders(_sites(source, modules=modules))) == 1


def test_a_SECOND_cross_module_hop_is_refused_rather_than_followed() -> None:
    """Two hops and the reader of the call site can no longer see the env.

    The scrub is provably there in this source, and the gate still reports it.
    That is deliberate and is the same judgement `gitenv.py` makes: an
    environment that takes two files to establish is an ambient environment
    wearing a function call.
    """
    middle = """
    import deepest
    def _clean_git_env():
        return deepest.real_scrub()
    """
    deepest = """
    from nixverify.gitenv import scrubbed_env
    def real_scrub():
        return scrubbed_env()
    """
    source = """
    import subprocess
    import middle as gate
    def f():
        subprocess.run(["git", "status"], env=gate._clean_git_env())
    """
    modules = {
        "middle": textwrap.dedent(middle),
        "deepest": textwrap.dedent(deepest),
    }
    assert len(gate.offenders(_sites(source, modules=modules))) == 1


# ---------------------------------------------------------------------------
# The declared-exception marker cannot be used to buy silence
# ---------------------------------------------------------------------------


def test_the_marker_excuses_an_unscrubbed_control_under_scripts_tests() -> None:
    source = f"""
    import subprocess
    def f():
        subprocess.run(["git", "status"])  # {gate.MARKER}
    """
    sites = _sites(source, path="scripts/tests/test_thing.py")
    assert sites[0].marked
    assert not gate.offenders(sites)


def test_the_marker_does_NOT_excuse_an_unscrubbed_call_in_shipped_code() -> None:
    """A control lives with its test. In `checks/` the marker buys nothing."""
    source = f"""
    import subprocess
    def f():
        subprocess.run(["git", "status"])  # {gate.MARKER}
    """
    sites = _sites(source, path="checks/check_thing.py")
    assert sites[0].marked
    assert len(gate.offenders(sites)) == 1, (
        "the marker is scoped to scripts/tests/; honouring it in shipped code "
        "would make it the way to add the sixth unscrubbed call quietly"
    )


# ---------------------------------------------------------------------------
# The gate's own non-vacuity: it must be able to say NO
# ---------------------------------------------------------------------------


def test_the_analyser_can_fail_control_passes_on_the_shipped_analyser() -> None:
    can_fail, why = gate.analyser_can_fail()
    assert can_fail, why


def test_the_analyser_can_fail_control_REPORTS_a_blinded_analyser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blind the analyser and the control must call it blind, not green."""
    monkeypatch.setattr(gate, "offenders", lambda sites: [])
    can_fail, why = gate.analyser_can_fail()
    assert not can_fail
    assert "blind" in why, why


# ---------------------------------------------------------------------------
# The both-halves control, driven for real
# ---------------------------------------------------------------------------


def test_the_control_corrupts_a_victim_unscrubbed_and_is_inert_scrubbed(
    tmp_path: Path,
) -> None:
    result = gate.drive_control(tmp_path / "run", scrubbed_env())
    assert not result.error, result.error
    assert result.corrupted_unscrubbed, (
        "the unscrubbed half left the victim index at "
        f"{result.before} — the subject was not reproduced, so the scrubbed "
        "half proves nothing"
    )
    assert result.inert_scrubbed, (
        f"scrubbed_env did not neutralise the hostile environment: "
        f"{result.before} -> {result.after_scrubbed}"
    )
    assert result.after_unscrubbed != result.before


def test_the_control_still_corrupts_under_a_hostile_AMBIENT_environment(
    tmp_path: Path,
) -> None:
    """The D3.205 plant: the harness itself inherits the damaging variables.

    This is where the defect masked itself twice. A fixture that builds its
    victim under an inherited `GIT_WORK_TREE` builds it elsewhere, and the
    corruption half then quietly stops corrupting — the control goes silent and
    reads as safe. Every fixture call in `drive_control` is scrubbed precisely
    so this cannot happen, and this arm is what proves it rather than asserting
    it.
    """
    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    hostile = scrubbed_env(
        extra={var: str(nowhere) for var in gate.DAMAGING},
    )
    result = gate.drive_control(tmp_path / "run", hostile)
    assert not result.error, result.error
    assert result.corrupted_unscrubbed, (
        "THE CONTROL WENT SILENT under a hostile ambient environment — this is "
        "the masking D3.205 measured, not a pass"
    )
    assert result.inert_scrubbed


# ---------------------------------------------------------------------------
# End to end: the gate over a real repository, both halves
# ---------------------------------------------------------------------------


def _populate(home: Path, unscrubbed: int) -> None:
    """A repository with enough git calls to clear the non-vacuity floor."""
    for root in ("scripts", "checks"):
        (home / root).mkdir(parents=True, exist_ok=True)
    calls = "\n".join(
        f'    subprocess.run(["git", "log", "-{n}"], env=scrubbed_env())'
        for n in range(gate.MIN_CALL_SITES + 2)
    )
    (home / "scripts" / "clean.py").write_text(
        "import subprocess\nfrom nixverify.gitenv import scrubbed_env\n"
        f"def f():\n{calls}\n",
        encoding="utf-8",
    )
    if unscrubbed:
        bad = "\n".join(
            f'    subprocess.run(["git", "log", "-{n}"])' for n in range(unscrubbed)
        )
        (home / "checks" / "dirty.py").write_text(
            f"import subprocess\ndef f():\n{bad}\n", encoding="utf-8"
        )
    _git(home, "add", "-A")
    _git(home, "commit", "-qm", "population")


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    home = tmp_path / "nix"
    home.mkdir()
    _git(home, "init", "-q", ".")
    return home


def test_the_gate_PASSES_a_tree_whose_every_git_call_is_scrubbed(repo: Path) -> None:
    _populate(repo, unscrubbed=0)
    result = gate.run(Mode.VERIFY, Context(nix_home=repo, mode=Mode.VERIFY))
    assert result.status is Status.PASS, result.detail
    assert "route through nixverify.gitenv.scrubbed_env" in (result.evidence or "")


def test_the_gate_FAILS_the_same_tree_with_one_unscrubbed_call_added(
    repo: Path,
) -> None:
    """The both-halves pair: the ONLY difference is one call losing its env."""
    _populate(repo, unscrubbed=1)
    result = gate.run(Mode.VERIFY, Context(nix_home=repo, mode=Mode.VERIFY))
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.evidence
    assert "checks/dirty.py:3" in (result.detail or ""), result.detail
    assert "env=<absent>" in (result.detail or ""), (
        "the finding must name WHAT it saw, not merely that it failed (§18)"
    )


def test_the_gate_CANNOT_MEASURE_a_scope_with_too_few_git_calls(repo: Path) -> None:
    """A green over an empty scope is an artefact of the instrument.

    This is the failure ARC 035 measured one layer out: seven gates went red on
    their non-vacuity floors because the tree they measured had been emptied
    under them. The right verdict for a lost subject is CANNOT_MEASURE with the
    count named — never PASS.
    """
    (repo / "scripts").mkdir()
    (repo / "scripts" / "thin.py").write_text(
        'import subprocess\ndef f():\n    subprocess.run(["ruff"])\n', encoding="utf-8"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "thin")
    result = gate.run(Mode.VERIFY, Context(nix_home=repo, mode=Mode.VERIFY))
    assert result.status is Status.CANNOT_MEASURE
    assert "below the floor" in (result.detail or ""), result.detail


def test_the_gate_FAILS_LOUDLY_when_its_own_control_goes_blind(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE ARM THIS GATE EXISTS FOR.

    Silence in the control half is the failure mode that let D3.205 recur twice
    inside the instrument built to police it. A control that cannot demonstrate
    the defect must be reported as blind, never absorbed into a green.
    """
    _populate(repo, unscrubbed=0)
    blind = gate.ControlResult(
        corrupted_unscrubbed=False,
        inert_scrubbed=True,
        before="a" * 64,
        after_unscrubbed="a" * 64,
        after_scrubbed="a" * 64,
    )
    monkeypatch.setattr(gate, "drive_control", lambda root, ambient: blind)
    result = gate.run(Mode.VERIFY, Context(nix_home=repo, mode=Mode.VERIFY))
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "THE CONTROL IS BLIND" in (result.detail or ""), result.detail


def test_the_gate_FAILS_when_the_scrub_stops_neutralising(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _populate(repo, unscrubbed=0)
    broken = gate.ControlResult(
        corrupted_unscrubbed=True,
        inert_scrubbed=False,
        before="a" * 64,
        after_unscrubbed="b" * 64,
        after_scrubbed="c" * 64,
    )
    monkeypatch.setattr(gate, "drive_control", lambda root, ambient: broken)
    result = gate.run(Mode.VERIFY, Context(nix_home=repo, mode=Mode.VERIFY))
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "DID NOT NEUTRALISE" in (result.detail or ""), result.detail


# ---------------------------------------------------------------------------
# The live tree
# ---------------------------------------------------------------------------


def test_the_live_tree_has_no_unscrubbed_git_call() -> None:
    """The property itself, over `/home/bbt/nix`, derived not remembered."""
    result = gate.run(Mode.VERIFY, Context(nix_home=REPO, mode=Mode.VERIFY))
    assert result.status is Status.PASS, result.detail


def test_the_live_scan_is_not_vacuous() -> None:
    paths, error = gate.tracked_python(REPO)
    assert not error, error
    sources = {rel: (REPO / rel).read_text(encoding="utf-8") for rel in paths}
    modules: dict[str, str] = {}
    for rel, text in sources.items():
        modules.setdefault(Path(rel).stem, text)
    total = 0
    for rel, text in sources.items():
        found, err = gate.scan_source(rel, text, modules)
        assert not err, err
        total += len(found)
    assert total >= gate.MIN_CALL_SITES, (
        f"the live scan found {total} git invocation(s); below "
        f"{gate.MIN_CALL_SITES} the green means the scope was lost"
    )
