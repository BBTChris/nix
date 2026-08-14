"""Pin conformance per nix_check_contract.md §7.

--------------------------------------------------------------------------
ARC 027 / A4 — THE REAL-SUBJECT PLANT THIS FILE DID NOT HAVE
--------------------------------------------------------------------------
Everything above the PLANT section below drives `evaluate()` on hand-built
dictionaries, or drives `run()` against a `tmp_path` home holding a fake
interpreter. Those are good tests of a pure function and of one CANNOT_MEASURE
path, and they are not a can-fail of the gate: **not one of them ever changed
`checks/pinned_deps.json`, the artifact `SUBJECTS` names.** `binding_census.py`
measured the consequence over the whole committed suite on commit `2ef4585`:

    check_python_deps                EXERCISED-NEVER-RED      CANNOT_MEASURE:1,PASS:8  |  -

Eight PASSes and one CANNOT_MEASURE, and no red at all. The single
CANNOT_MEASURE is `test_query_failure_is_cannot_measure_not_absent`, which
proves the gate notices an ABSENT subject — check contract §10 is explicit that
a property proven while its subject is unavailable is not proven, so that is not
a can-fail either.

CHECK-DEBT's ARC 022 census records this gate BOUND on a plant into the real
pins file. That plant was taken **by hand** and banked in a results document;
§0e requires a committed, runnable artifact and D2.30 is the row for the class.
The PLANT section below is that artifact.

**The venue is a scratch copy of the tree (doctrine C.8); the measured side is
the REAL venv**, reached through a symlink, so the comparison the gate performs
is between a planted declaration and this machine's actual installed set.

RESIDUAL, stated rather than implied and unchanged since ARC 022: the plant
moves the DECLARED half. The INSTALLED half has never been perturbed and cannot
be here — `.venv` is shared with the canonical tree and with every sibling
worktree, so uninstalling a package to prove a point would break whatever else
is running. That is the same ownership problem CHECK-DEBT D3.12 records for
`check_venv`. **CHECK-DEBT D3.28.**
"""

# pylint: disable=invalid-name,duplicate-code
# Test names SHOUT the property under test, as in every other suite here
# (ARC 030 / Stage 2 A2's lock-awareness tests are the ones long enough to
# trip pylint's default naming-style check). duplicate-code: the fake-
# interpreter fixture setup here necessarily pairs with the near-identical
# one in test_check_python_transitive_deps.py.

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest  # pylint: disable=import-error
from nixverify.contract import Context, Mode, Status
from nixverify.loader import load_check

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"


def _run(mode: Mode, home: Path):
    loaded = load_check(CHECKS, "check_python_deps")
    assert loaded.run is not None, loaded.load_error
    return loaded.run(mode, Context(nix_home=home, mode=mode))


def test_real_venv_satisfies_the_real_pins() -> None:
    """PASS against this repo's own real venv, with evidence recorded."""
    result = _run(Mode.VERIFY, REPO)
    assert result.status is Status.PASS
    assert "ib_async" in result.evidence


def test_pins_file_lists_ib_async_at_the_arc_008_version() -> None:
    """The pins file, not this test, is the single source of truth (§7)."""
    pins = json.loads((CHECKS / "pinned_deps.json").read_text(encoding="utf-8"))
    assert pins["packages"]["ib_async"] == "2.1.0"


def test_wrong_version_fails_and_names_the_package(  # pylint: disable=unused-argument
    tmp_path: Path,
) -> None:
    """§7: drift from the pin is a defect the check must name specifically.

    `tmp_path` is unused: `evaluate()` is pure and needs no filesystem, but
    the signature is kept as specified by task-9-brief.md rather than
    silently trimmed.
    """
    loaded = load_check(CHECKS, "check_python_deps")
    assert loaded.run is not None, loaded.load_error
    import check_python_deps as mod  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel

    result = mod.evaluate({"ib_async": "2.1.0"}, {"ib_async": "2.0.1"})
    assert result.status is Status.FAIL_REPAIRABLE
    assert "ib_async" in result.site
    assert "2.0.1" in result.detail


def test_absent_package_fails_and_names_it() -> None:
    """A missing package is drift too, not a silent pass."""
    loaded = load_check(CHECKS, "check_python_deps")
    assert loaded.run is not None, loaded.load_error
    import check_python_deps as mod  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel

    result = mod.evaluate({"ib_async": "2.1.0"}, {})
    assert result.status is Status.FAIL_REPAIRABLE
    assert "ib_async" in result.site


def test_matching_pin_passes_with_evidence() -> None:
    """§5: PASS carries non-empty evidence naming what was measured."""
    loaded = load_check(CHECKS, "check_python_deps")
    assert loaded.run is not None, loaded.load_error
    import check_python_deps as mod  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel

    result = mod.evaluate({"ib_async": "2.1.0"}, {"ib_async": "2.1.0"})
    assert result.status is Status.PASS
    assert "2.1.0" in result.evidence


def test_query_failure_is_cannot_measure_not_absent(tmp_path: Path) -> None:
    """Task 9 review, Finding 2 (§4.1): a subprocess that cannot answer must
    never collapse into 'nothing is installed' — that would send --correct
    into an unattended reinstall against a defect that may not exist.

    The fake interpreter is a real, executable file that always exits
    nonzero, so `installed_versions()` genuinely cannot parse a version
    list out of it — this is not a mock standing in for the failure, it is
    the failure.
    """
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    fake_python = venv_bin / "python3"
    fake_python.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    fake_python.chmod(0o755)

    result = _run(Mode.VERIFY, tmp_path)

    assert result.status is Status.CANNOT_MEASURE


def test_drift_UNDER_a_HELD_venv_mutation_lock_is_CANNOT_MEASURE_not_FAIL(
    tmp_path: Path,
) -> None:
    """ARC 030 / Stage 2 A2 — the hazard this arc's brief names directly.

    A venv reporting "nothing installed" (every pin absent) is exactly the
    transient shape a concurrent `rm -rf .venv && python -m venv` produces
    mid-rebuild — not evidence the pins are actually violated. Without lock
    awareness this fixture would drive `FAIL_REPAIRABLE` (proven by the
    sibling test right above, which hits the identical "package absent"
    branch via a different subject — a broken interpreter rather than an
    empty package set — through the same `evaluate()` path). With the lock
    held by this process (modelling a concurrent mutator), the SAME
    drift-shaped state must report CANNOT_MEASURE, naming the lock.
    """
    # pylint: disable-next=import-outside-toplevel
    from nixverify.venv_lock import venv_mutation_lock

    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    fake_python = venv_bin / "python3"
    fake_python.write_text("#!/usr/bin/env python3\nprint('{}')\n", encoding="utf-8")
    fake_python.chmod(0o755)

    with venv_mutation_lock(tmp_path):
        result = _run(Mode.VERIFY, tmp_path)

    assert result.status is Status.CANNOT_MEASURE
    assert "venv-mutation lock is held" in result.detail

    # Released, the identical tree is measured as real drift again — proving
    # the CANNOT_MEASURE above was about the lock, not about the packages.
    released = _run(Mode.VERIFY, tmp_path)
    assert released.status is Status.FAIL_REPAIRABLE


def test_load_pins_rejects_malformed_entries(tmp_path: Path) -> None:
    """Minor finding: pinned_deps.json feeds this check's `pip install` argv
    directly and install.sh's deliberately-unquoted `$PINS` shell expansion
    (§7). A package name starting with `-` or a version with a space/glob
    character would corrupt one side's argv and word-split/glob the other.
    """
    loaded = load_check(CHECKS, "check_python_deps")
    assert loaded.run is not None, loaded.load_error
    import check_python_deps as mod  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel

    (tmp_path / "pinned_deps.json").write_text(
        json.dumps({"packages": {"-evil": "1.0.0"}}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="-evil"):
        mod.load_pins(tmp_path)


def _expected_print_pins() -> str:
    """What `--print-pins` must emit, DERIVED from the pins file.

    ARC 015: these two tests previously hardcoded "ib_async==2.1.0", which restated a
    mutable fact the pins file owns (CLAUDE.md directive 3) — so adding the
    pytest-asyncio pin broke two tests that were not measuring anything about
    pytest-asyncio. Deriving keeps them honest: the assertion is about the FORMAT and
    ORDERING install.sh's `$PINS` expansion depends on, and about the output covering
    every declared pin, neither of which weakens when a pin is added.

    Non-vacuity: `test_pins_file_lists_ib_async_at_the_arc_008_version` above is the test
    that pins the actual version, and it still hardcodes on purpose. Deriving here does
    not leave the version unasserted anywhere.
    """
    pins = json.loads((CHECKS / "pinned_deps.json").read_text(encoding="utf-8"))
    return "\n".join(
        f"{name.lower()}=={version}"
        for name, version in sorted(pins["packages"].items())
    )


def test_print_pins_emits_validated_specs_one_per_line() -> None:
    """Task 9 review round 2, Finding A: install.sh must consume this
    output rather than re-parsing pinned_deps.json itself, so the pins
    guard actually reaches the shell-side `$PINS` expansion it was written
    to protect (§7). One implementation, one validator, one source.
    """
    proc = subprocess.run(
        [sys.executable, str(CHECKS / "check_python_deps.py"), "--print-pins"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    expected = _expected_print_pins()
    assert proc.stdout.strip() == expected
    # The shape install.sh relies on, asserted independently of the contents: one
    # `name==version` spec per line, no blanks, no stray whitespace to word-split on.
    lines = proc.stdout.strip().splitlines()
    assert lines == sorted(lines)
    assert all(line.count("==") == 1 and " " not in line for line in lines), lines
    assert len(lines) >= 2, "pins collapsed to fewer than the two declared packages"


def test_print_pins_works_under_system_python_with_no_venv() -> None:
    """install.sh runs before .venv exists (§9.1-adjacent): this mode must
    not need anything beyond stdlib, or install.sh could never call it."""
    proc = subprocess.run(
        ["/usr/bin/python3", str(CHECKS / "check_python_deps.py"), "--print-pins"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == _expected_print_pins()


def test_pins_file_lists_pytest_asyncio() -> None:
    """ARC 015 Part 3: the query verbs became coroutines, so the suite that drives them
    needs pytest-asyncio — and anything the venv must contain is pinned here or
    check_python_deps cannot see it drift (§7)."""
    pins = json.loads((CHECKS / "pinned_deps.json").read_text(encoding="utf-8"))
    assert pins["packages"]["pytest-asyncio"] == "1.4.0"


def test_declares_disruptive_because_repair_swaps_the_order_placing_client() -> None:
    """Task 9 review, Finding 1: repair() reinstalls ib_async — a package
    swap is exactly §4's definition of disruptive. The engine (not this
    check) is what keeps it inspectable at boot despite this (§8)."""
    loaded = load_check(CHECKS, "check_python_deps")
    assert loaded.disruptive is True


# ===========================================================================
# THE PLANT — ARC 027 / A4. See the module docstring for why it is here.
#
# §7.12, asked of this section: what would have to be true for it to pass while
# measuring nothing?
#
#   1. The gate could be reading THIS worktree's pins file while wearing the
#      scratch tree's name. `run()` resolves `checks_dir` from its own
#      `__file__` and ignores `ctx.nix_home` — the trap CHECK-DEBT D2.23 records
#      for `check_derived_claims`. CLOSED by driving the SCRATCH TREE'S OWN copy
#      of the gate as a program, and by
#      `test_the_real_pins_file_is_untouched_by_every_plant_here`.
#   2. The gate could be failing for an unrelated reason and reaching exit 1
#      through the same shared namespace. CLOSED: every plant asserts the
#      package name and the version arithmetic in the message, never the code.
#   3. A plant could silently trigger a repair, which would make the test a
#      `pip install` rather than a measurement. CLOSED by
#      `test_verify_mode_never_mutates_the_shared_venv`, which reads the real
#      venv's installed set either side of the whole plant sequence.
# ===========================================================================

VENV_PYTHON = REPO / ".venv" / "bin" / "python"
PINS = "checks/pinned_deps.json"


@pytest.fixture(name="scratch", scope="module")
def _scratch(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A copy of the tree with `.venv` SYMLINKED, so the measured side is real.

    `state/` is excluded deliberately: it is a symlink back to the canonical
    tree and `copytree` would follow it into live operational data.
    """
    home = tmp_path_factory.mktemp("python_deps") / "nix"
    shutil.copytree(
        REPO,
        home,
        ignore=shutil.ignore_patterns(
            ".git", "__pycache__", ".venv", "*.pyc", "state", "graphify-out"
        ),
    )
    (home / ".venv").symlink_to(REPO / ".venv")
    return home


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _drive(home: Path) -> tuple[int, str]:
    """Run the scratch tree's own copy of the gate, in VERIFY mode (flagless).

    Flagless is measure-only by the check contract's first rule, and it is the
    only mode this file ever uses: `--correct` would `pip install` into a venv
    three agents share.

    `PYTHONPATH` is PREPENDED rather than replaced — `checks/_preamble.py`
    APPENDS its `scripts/`, so a real one already on the path would shadow the
    scratch tree, and `binding_census.py` installs its tracer through
    `PYTHONPATH`, so replacing it would hide this verdict from the instrument
    that has to confirm the binding.
    """
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        [str(home / "scripts")] + ([existing] if existing else [])
    )
    proc = subprocess.run(  # nosec B603 - fixed argv, shell=False, scratch tree
        [str(VENV_PYTHON), str(home / "checks" / "check_python_deps.py")],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(home),
        env=env,
    )
    return proc.returncode, (proc.stdout or proc.stderr).strip()


@pytest.fixture(name="plant")
def _plant(scratch: Path) -> Iterator[Callable[[Callable[[dict], None]], None]]:
    """Mutate the scratch pins file, then restore it byte-identically.

    Both halves of doctrine C.2 in one fixture: the caller measures with the
    plant in, and the teardown asserts the sha256 came back unchanged.
    """
    target = scratch / PINS
    before = target.read_text(encoding="utf-8")
    before_sha = _sha(target)

    def _apply(mutate: Callable[[dict], None]) -> None:
        payload = json.loads(before)
        mutate(payload)
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        assert _sha(target) != before_sha, "the plant changed nothing"

    yield _apply
    target.write_text(before, encoding="utf-8")
    assert _sha(target) == before_sha, "the control was not restored byte-identically"


def _installed_now() -> dict:
    """What the REAL venv holds, asked of the real venv, not of the pins file."""
    import check_python_deps as mod  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel

    present = mod.installed_versions(REPO / ".venv" / "bin" / "python3")
    assert present is not None, "the real venv could not answer"
    return present


def test_the_scratch_control_passes_against_the_real_venv(scratch: Path) -> None:
    """CONTROL (doctrine C.3), asserted before any plant.

    The evidence must name the pins that were satisfied — a bare `pass` would be
    satisfied by a run that compared an empty pin set against anything.
    """
    code, out = _drive(scratch)
    assert code == 0, out
    assert out.startswith("pass: pins satisfied:"), out
    for package in json.loads((CHECKS / "pinned_deps.json").read_text())["packages"]:
        assert package.lower() in out, out


def test_a_drifted_pin_reddens_the_gate_and_names_both_versions(
    scratch: Path, plant: Callable[[Callable[[dict], None]], None]
) -> None:
    """CAN-FAIL against the REAL subject — `checks/pinned_deps.json`.

    ARC 022's hand-taken cycle, made reproducible. The installed version is the
    real venv's; only the declaration moves. Both numbers are asserted, so a
    gate that merely noticed *something* differed would not satisfy this.
    """
    plant(lambda p: p["packages"].update({"ib_async": "2.0.1"}))
    code, out = _drive(scratch)
    assert code == 1, out
    assert out.startswith("fail_repairable:"), out
    assert "ib_async" in out, out
    assert "2.1.0 (want 2.0.1)" in out, out


def test_a_pin_with_no_installed_package_is_named_absent_not_drifted(
    scratch: Path, plant: Callable[[Callable[[dict], None]], None]
) -> None:
    """CAN-FAIL, the OTHER branch of `evaluate` — and the distinction matters.

    `absent` and `wrong version` take different repairs and the gate must not
    collapse them. Driven end-to-end here rather than on a hand-built dict,
    because the dict form was already present above and never touched the
    subject.
    """
    plant(lambda p: p["packages"].update({"nix_absent_probe_pkg": "9.9.9"}))
    code, out = _drive(scratch)
    assert code == 1, out
    assert "nix_absent_probe_pkg: absent (want 9.9.9)" in out, out


def test_the_real_pins_file_is_untouched_by_every_plant_here(scratch: Path) -> None:
    """The plant landed in the scratch tree and nowhere else.

    Doctrine C.8 is that the scratch copy is the venue and never the subject; a
    plant that reached `~/nix/checks/pinned_deps.json` would have made this
    suite an environment change rather than a measurement.
    """
    assert _sha(scratch / PINS) == _sha(REPO / PINS)
    code, out = _drive(scratch)
    assert code == 0, out


def test_verify_mode_never_mutates_the_shared_venv(scratch: Path) -> None:
    """§1 of the check contract: a flagless check never mutates.

    Asserted over the REAL venv's installed set, not over the gate's return
    value — the plants above drive a `FAIL_REPAIRABLE`, and a `repair()` reached
    by accident would `pip install` into a venv that the canonical tree and every
    sibling worktree share.
    """
    before = _installed_now()
    _drive(scratch)
    assert _installed_now() == before
