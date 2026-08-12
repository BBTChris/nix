"""First real check: the floor, which cannot repair itself (§3).

ARC 025 Wave A. This check was RETROFITTED (declarations + the full actuation
CLI), and a retrofitted check is a NEW check whose can-fail binding does not
survive the retrofit. Everything below `RE-BINDING` re-establishes it against
the real subject: non-vacuity first, then plant, then the control that removes
the plant. Every control asserts the REASON — the message, the site, or the
field — never the exit code alone.
"""

# R0801 pairs this file's declaration assertions and refusal assertions with the
# matching blocks in test_check_node_identity.py and test_check_spec_citations.py.
# The similarity is deliberate and must stay: each gate's binding has to stand on
# its own, and folding these into one shared helper would make a single edit
# silently un-bind three independent instruments at once (doctrine C.10 — one
# owner per shared measurement, applied to the measurement OF the gates). The
# assertions differ in exactly the fields that matter — the declared values and
# the reason text — which is the part that carries the evidence.
# pylint: disable=duplicate-code
import ast
import subprocess
import sys
from pathlib import Path

from nixverify.contract import Context, Mode, Status
from nixverify.declarations import read_declaration
from nixverify.loader import load_check

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"
SCRIPTS = REPO / "scripts"
CHECK_FILE = CHECKS / "check_python_runtime.py"


def _ctx(mode: Mode = Mode.VERIFY) -> Context:
    """Build a Context rooted at the real repo, for the given mode."""
    return Context(nix_home=REPO, mode=mode)


def test_passes_on_this_interpreter_with_evidence() -> None:
    """PASS on the interpreter running the test, with evidence recorded."""
    loaded = load_check(CHECKS, "check_python_runtime")
    assert loaded.run is not None, loaded.load_error
    result = loaded.run(Mode.VERIFY, _ctx())
    assert result.status is Status.PASS
    assert str(sys.version_info.major) in result.evidence


def test_reports_needs_operator_when_below_floor(monkeypatch) -> None:
    """§4.1: verify.py cannot apt-install its own interpreter."""
    loaded = load_check(CHECKS, "check_python_runtime")
    assert loaded.run is not None
    import check_python_runtime as mod  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel

    monkeypatch.setattr(mod, "MINIMUM", (99, 0))
    result = mod.run(Mode.CORRECT, _ctx(Mode.CORRECT))
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert result.site


def test_standalone_invocation_honours_the_exit_contract() -> None:
    """§4.2: the module is independently runnable."""
    proc = subprocess.run(
        [sys.executable, str(CHECKS / "check_python_runtime.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_declares_user_privilege_and_is_not_disruptive() -> None:
    """Metadata reflects §4/§8: this check is user-privileged, non-disruptive."""
    loaded = load_check(CHECKS, "check_python_runtime")
    assert loaded.privilege == "user"
    assert loaded.disruptive is False
    assert loaded.interactive is False


# ===========================================================================
# ARC 025 — ORCHESTRATION DECLARATIONS (read statically, never by import)
# ===========================================================================


def test_every_declaration_is_present_and_statically_readable() -> None:
    """§4.4: the AST reader must get all seven symbols with no named error.

    A computed declaration (`RESOURCES = _BASE + ("x",)`) is not a default, it
    is a named error — so `errors` being empty is the assertion, not a bonus.
    """
    declaration = read_declaration(CHECK_FILE)
    assert not declaration.errors, declaration.errors
    for symbol in (
        "DEPENDS_ON",
        "RESOURCES",
        "TIME_BOUND",
        "CORRECTABLE",
        "NON_CORRECTABLE_REASON",
        "SUBJECTS",
    ):
        assert symbol in declaration.declared, f"{symbol} not declared"
    assert not declaration.depends_on
    # `()` is a positive claim ("claims nothing"), which is different from not
    # having declared — `declares_resources` is what makes the check eligible
    # for a parallel block at all.
    assert not declaration.resources
    assert declaration.declares_resources is True
    assert declaration.time_bound is False
    assert declaration.expected_s is None
    assert declaration.correctable is False
    assert declaration.non_correctable_reason.strip()
    assert not declaration.subjects


def test_the_empty_resource_claim_is_true_this_check_touches_nothing() -> None:
    """`RESOURCES = ()` is a positive claim, so it is proven, not trusted.

    Proof by absence over the AST (doctrine C.5): this check must reach neither
    the filesystem, a subprocess, nor a socket. `sys` and `pathlib` are the only
    things it may import, and `Path` is used solely to hand `__file__` to
    `standalone_main`.
    """
    tree = ast.parse(CHECK_FILE.read_text(encoding="utf-8"), filename=str(CHECK_FILE))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert imported, "the AST scan found no imports — it measured nothing"
    for module in ("socket", "subprocess", "shutil", "os", "tempfile", "json"):
        assert module not in imported, (
            f"the check imports {module!r} — RESOURCES=() is not a true claim"
        )


# ===========================================================================
# RE-BINDING — §0c. NON-VACUITY FIRST (doctrine C.3), then plant, then control.
# ===========================================================================


def test_non_vacuity_the_gate_reads_the_live_interpreter() -> None:
    """Doctrine C.3, asserted BEFORE any plant: the scope contains the subject.

    The subject is the interpreter this process is running on. A gate that
    compared a constant against another constant would pass forever, so what is
    asserted is that BOTH halves of the reported measurement come out of the
    live process: the exact running micro version and the exact executable path.
    """
    loaded = load_check(CHECKS, "check_python_runtime")
    assert loaded.run is not None, loaded.load_error
    result = loaded.run(Mode.VERIFY, _ctx())
    running = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    assert f"sys.version_info={running}" in result.evidence, result.evidence
    assert sys.executable in result.evidence, result.evidence


def test_plant_and_control_the_floor_comparison(monkeypatch) -> None:
    """PLANT then CONTROL, in one test so neither half can be read alone.

    The subject — the running interpreter — cannot be swapped in-process, so the
    plant is on the comparison threshold. What proves the gate still READ its
    subject is that the FAIL is described entirely in terms of the live process:
    `site` names the real executable and the real version. A gate that ignored
    the interpreter could not produce those strings.
    """
    loaded = load_check(CHECKS, "check_python_runtime")
    assert loaded.run is not None, loaded.load_error
    import check_python_runtime as mod  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel

    running = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )

    # -- PLANT -------------------------------------------------------------
    monkeypatch.setattr(mod, "MINIMUM", (99, 0))
    planted = mod.run(Mode.VERIFY, _ctx())
    assert planted.status is Status.FAIL_NEEDS_OPERATOR
    # THE REASON, not the status: the site names the real subject, and the
    # detail names the floor it was measured against and the owner of the fix.
    assert sys.executable in planted.site, planted.site
    assert running in planted.site, planted.site
    assert "need >= 99.0" in planted.detail, planted.detail
    assert "install.sh" in planted.detail, planted.detail

    # -- REMOVE THE PLANT — the control half. ------------------------------
    monkeypatch.setattr(mod, "MINIMUM", (3, 14))
    restored = mod.run(Mode.VERIFY, _ctx())
    assert restored.status is Status.PASS, restored.detail
    assert running in restored.evidence


def _standalone_copy(tmp_path: Path, minimum: str | None) -> Path:
    """A runnable COPY of the check, optionally with a planted floor.

    Doctrine C.8: a plant never touches a production artifact. The copy carries
    its own `_preamble` shim pointing back at the real `scripts/`, so the copy
    exercises the real `nixverify.actuation.standalone_main`, not a stub.
    """
    checks = tmp_path / "checks"
    checks.mkdir(parents=True)
    (checks / "_preamble.py").write_text(
        f"import sys\nsys.path.append({str(SCRIPTS)!r})\n", encoding="utf-8"
    )
    target = checks / "check_python_runtime.py"
    source = CHECK_FILE.read_text(encoding="utf-8")
    if minimum is not None:
        planted = source.replace("MINIMUM = (3, 14)", f"MINIMUM = {minimum}")
        assert planted != source, "the plant did not apply — MINIMUM was respelled"
        source = planted
    target.write_text(source, encoding="utf-8")
    return target


def _run_copy(target: Path, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(target), *flags],
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_retrofitted_cli_carries_the_verdict_and_names_the_reason(
    tmp_path: Path,
) -> None:
    """The retrofit's NEW surface, bound: plant -> exit 1 with the reason
    printed; remove the plant -> exit 0. Both halves, on the real CLI.
    """
    running = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )

    planted = _run_copy(_standalone_copy(tmp_path / "planted", "(99, 0)"))
    assert planted.returncode == 1, planted.stdout + planted.stderr
    # THE REASON: the live version measured, the floor demanded, and the owner.
    assert f"sys.version_info={running}" in planted.stdout, planted.stdout
    assert "need >= 99.0" in planted.stdout, planted.stdout
    assert "install.sh" in planted.stdout, planted.stdout

    control = _run_copy(_standalone_copy(tmp_path / "control", None))
    assert control.returncode == 0, control.stdout + control.stderr
    assert control.stdout.startswith("pass:"), control.stdout
    assert "need >=" not in control.stdout, control.stdout


# ===========================================================================
# ACTUATION — the flag surface, and the refusal that must name its reason.
# ===========================================================================


def test_a_flagless_invocation_is_measure_only() -> None:
    """§4.3: the default is verify. A flagless check never mutates."""
    proc = subprocess.run(
        [sys.executable, str(CHECK_FILE)], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.startswith("pass:"), proc.stdout
    assert "REFUSED" not in proc.stderr


def test_correct_refuses_and_names_the_declared_reason() -> None:
    """§2.3: a refusal with no reason is indistinguishable from a check that
    forgot to implement one. The assertion is on the REASON TEXT, and the text
    is read from the declaration so the two can never drift apart.
    """
    reason = read_declaration(CHECK_FILE).non_correctable_reason
    assert reason.strip()
    for verb in ("--correct", "--install"):
        proc = subprocess.run(
            [sys.executable, str(CHECK_FILE), verb],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "NON-CORRECTABLE" in proc.stderr, proc.stderr
        assert reason in proc.stderr, proc.stderr
        assert "install.sh" in proc.stderr


def test_the_refusal_control_can_tell_a_wrong_reason_from_the_right_one(
    tmp_path: Path,
) -> None:
    """CONTROL for the assertion above. A test that asserted only `exit 1`
    would pass against a check that refused for the WRONG reason — or crashed.
    This plants a different reason into a copy and shows the assertion fails.
    """
    target = _standalone_copy(tmp_path, None)
    source = target.read_text(encoding="utf-8")
    real = read_declaration(CHECK_FILE).non_correctable_reason
    # A later module-level assignment wins in the AST reader, which is what
    # `standalone_main` consults — so this overrides the declaration without
    # having to rewrite a multi-line parenthesised string.
    planted = source.replace(
        'NAME = "check_python_runtime"',
        'NON_CORRECTABLE_REASON = "a different reason"\nNAME = "check_python_runtime"',
        1,
    )
    assert planted != source
    target.write_text(planted, encoding="utf-8")

    proc = _run_copy(target, "--correct")
    # Exit code alone is IDENTICAL to the correct case — which is the point.
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "a different reason" in proc.stderr
    assert real not in proc.stderr, (
        "the copy still carries the real reason, so this control proves nothing"
    )
