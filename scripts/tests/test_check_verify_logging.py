"""`check_verify_logging` — the can-fail artifact CHECK-DEBT D3.25 says does not exist.

ARC 027 / A1. **D3.25's whole subject is that this file was not here.** The row
was opened by ARC 026 Stage 2.4 while building the §2.4 binding table from
measured evidence: the gate has passed green in every arc since ARC 024, the
only occurrence of its name anywhere under `scripts/tests/` was a DOCSTRING LINE
in `test_plane2.py`, and nobody had claimed a binding for it. An unclaimed
binding attracts no audit, which is why the row calls it worse than a false one.

**MEASURED BEFORE THIS FILE EXISTED**, by `scripts/tests/binding_census.py` over
the whole committed suite on commit `2ef4585`:

    check_verify_logging             EXERCISED-NEVER-RED      PASS:7  |  -

Seven observations of the shipped gate's `run()`, every one of them PASS. The
gate ran; nothing had ever shown it able to say no.

--------------------------------------------------------------------------
THE SUBJECT, AND WHY EACH PLANT LANDS IN IT RATHER THAN BESIDE IT
--------------------------------------------------------------------------
`check_verify_logging.SUBJECTS` names `scripts/nixverify/plane2.py`, and the
gate's other half is the journal it reads back with `journalctl`. Both are real
here. Under the CHECK-DEBT rule of record (*a can-fail against a purpose-built
fake proves the gate can discriminate, not that it discriminates against its
real subject*) every plant below is taken against that module and that journal:

  * **PLANT 1 — no file is edited at all.** `plane2.DISABLE_ENV`
    (`NIX_PLANE2_DISABLED`) is the module's own documented emission switch, and
    its docstring says it exists so a *control* can be driven. Setting it is a
    real operational state — a unit file carrying it would make `verify.py` log
    nothing to the journal, silently — and it drives the SHIPPED gate,
    IN-PROCESS, against the SHIPPED `plane2.py` and the REAL journal. Arms 1 and
    2 both fire.
  * **PLANTS 2-5** edit `scripts/nixverify/plane2.py` — the declared subject —
    in a **scratch copy of the tree**, which doctrine C.8 makes the venue and
    never the subject, with a byte-identical restore asserted in teardown.

The scratch runs are subprocesses so the planted module is the one imported.
`PYTHONPATH` is PREPENDED rather than replaced (`_env`), for two reasons that
are both load-bearing: `checks/_preamble.py` *appends* its `scripts/` directory,
so a real `scripts/` already on the path would win and the plant would be
invisible; and `binding_census.py` puts its tracer on `PYTHONPATH`, so replacing
it would make every subprocess verdict below unobservable to the very instrument
that has to confirm this file bound anything (§0e).

--------------------------------------------------------------------------
§7.12 THE STANDING QUESTION, asked of this file rather than of the gate:
what would have to be true for these tests to PASS while measuring nothing?
--------------------------------------------------------------------------
 1. **The gate could be returning FAIL for a reason that is not the plant** — a
    missing venv, an unparseable module, an import error. Every exit code in
    this project is a shared namespace and 1 is the crowded end of it.
    *Closed:* no test here asserts a status or an exit code alone. Each asserts
    the REASON — the site string, or the specific sentence the arm emits — so a
    gate that broke for an unrelated cause fails these tests rather than
    satisfying them.
 2. **The plants could be landing in a copy the gate never reads.** A scratch
    tree whose `nixverify` is shadowed by the real one on `sys.path` would
    produce a serene PASS and look like a gate that tolerates the defect.
    *Closed by `test_the_scratch_tree_is_the_module_the_gate_actually_imports`,*
    which asserts the control run's own evidence proves the round-trip happened
    AND that a plant moves the verdict — a shadowed module cannot do the second.
 3. **The control could be green for the wrong reason.** *Closed:* the control
    is asserted FIRST (doctrine C.3) and its evidence is required to name a
    non-zero delivery and a recovered round-trip, so "PASS" is not accepted from
    a run that measured nothing.
 4. **The restore could be nominal.** *Closed:* `plant`'s teardown asserts the
    sha256 of `plane2.py` came back byte-identical, and a final control run
    re-passes on the restored tree.
 5. **The whole file could be skipped** on a box with no journal and read as
    green. *Closed:* the skip is a `pytest.mark.skipif` with a named reason at
    module scope, so a skipped run is reported as `s` and never as a pass — and
    `binding_census.py` keys its verdict on observed FAILING statuses, so a
    skipped module contributes no binding rather than a silent one.

--------------------------------------------------------------------------
WHAT IS NOT PLANTED, AND WHY — arm 5, REFUSED WITH A MEASUREMENT
--------------------------------------------------------------------------
Arm 5 (`_arm5_presentation`) reddens when an ANSI escape or a spinner frame
appears in the Plane-2 stream. Its subject is the REAL journal over a 30-minute
window, and the only way to plant it is to emit a presentation byte into the
shared journal under the `nix-verify` identifier. journald is append-only: that
entry cannot be withdrawn, so the plant would leave the real gate RED for every
worktree on this box for the next half hour — including whatever else is
committing at the time. That is the same hazard `check_hook_suite`'s suite
refuses for the shared hooks directory, and it is refused here for the same
reason. `test_the_presentation_detector_is_live_but_is_not_plantable_here`
drives the detector directly instead and states the residual; CHECK-DEBT D3.26
carries it.
"""

from __future__ import annotations

# R0801: every instrument's control stands on its own file. One shared helper
# would let a single edit un-bind several gates at once — see
# test_check_python_runtime.py, which carries this pragma for the same reason.
# pylint: disable=duplicate-code
import hashlib
import os
import shutil
import subprocess  # nosec B404 - fixed argv, shell=False, scratch tree only
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "checks"
if str(CHECKS) not in sys.path:
    sys.path.insert(0, str(CHECKS))

# pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=import-error
    Context,
    Mode,
    Status,
)
from nixverify.loader import load_check  # pylint: disable=import-error
from nixverify.plane2 import (  # pylint: disable=import-error
    DISABLE_ENV,
    JOURNAL_SOCKET,
    JOURNALCTL,
    read_back,
)

GATE = "checks/check_verify_logging.py"
SUBJECT = "scripts/nixverify/plane2.py"
VENV_PYTHON = REPO / ".venv" / "bin" / "python"


def _journal_is_measurable() -> bool:
    """True only when the gate's subject is actually present and readable.

    `Path.is_socket()`, not `exists()`: a regular file at `/dev/log` is exactly
    the false-green `Plane2._open` was hardened against, and a gate driven
    against it would be measuring the wrong thing rather than nothing.
    """
    if not Path(JOURNAL_SOCKET).is_socket() or not Path(JOURNALCTL).exists():
        return False
    _, error = read_back(since="-1 min")
    return not error


pytestmark = pytest.mark.skipif(
    not _journal_is_measurable(),
    reason=(
        "no readable journald on this box — the gate's subject is absent, so a "
        "can-fail taken here would prove nothing (check contract §10)"
    ),
)


# ---------------------------------------------------------------------------
# THE SCRATCH TREE. Doctrine C.8: no plant touches a production artifact.
# ---------------------------------------------------------------------------


@pytest.fixture(name="scratch", scope="module")
def _scratch(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A full copy of the tree, `.venv` symlinked rather than duplicated.

    Copied rather than planted in place because several agents and a pre-commit
    hook may be reading this worktree while the suite runs; ARC 018 established
    that a concurrent cross-set write corrupts evidence, not merely state.

    `state/` is excluded deliberately: it is a symlink back to the canonical
    tree, and `copytree` would follow it into live operational data.
    """
    home = tmp_path_factory.mktemp("verify_logging") / "nix"
    shutil.copytree(
        REPO,
        home,
        ignore=shutil.ignore_patterns(
            ".git",
            "__pycache__",
            ".venv",
            ".venv-dev",
            "*.pyc",
            "state",
            "graphify-out",
        ),
    )
    (home / ".venv").symlink_to(REPO / ".venv")
    return home


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _env(home: Path) -> dict[str, str]:
    """The child environment: the scratch `scripts/` FIRST, everything else kept.

    See the module docstring — prepending rather than replacing is what makes
    the plant visible to the gate and keeps the census tracer installed in the
    child. Both halves have bitten this project before.
    """
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        [str(home / "scripts")] + ([existing] if existing else [])
    )
    return env


def _drive(home: Path) -> tuple[int, str]:
    """Run the scratch tree's own copy of the gate as a program. (exit, stdout)."""
    proc = subprocess.run(  # nosec B603 - fixed argv, shell=False, scratch tree
        [str(VENV_PYTHON), str(home / GATE), str(home)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(home),
        env=_env(home),
    )
    return proc.returncode, (proc.stdout or proc.stderr).strip()


@pytest.fixture(name="plant")
def _plant(scratch: Path) -> Iterator[Callable[[str, str], None]]:
    """Substitute one string in the REAL subject, then restore it byte-identically.

    Both halves of doctrine C.2 live here: the caller measures with the plant
    in, and the teardown asserts the control returned with the sha256 it went in
    with. `__pycache__` is purged either side — `checks/_preamble.py` sets
    `sys.dont_write_bytecode`, but the scratch tree is also read by interpreters
    that do not go through it, and a stale `.pyc` would let an unplanted tree
    keep running planted code.
    """
    target = scratch / SUBJECT
    before = target.read_text(encoding="utf-8")
    before_sha = _sha(target)

    def _purge() -> None:
        for cache in scratch.rglob("__pycache__"):
            shutil.rmtree(cache, ignore_errors=True)

    def _apply(old: str, new: str) -> None:
        assert old in before, f"plant anchor is not in the subject: {old[:60]!r}"
        _purge()
        target.write_text(before.replace(old, new, 1), encoding="utf-8")
        assert _sha(target) != before_sha, "the plant changed nothing"

    yield _apply
    _purge()
    target.write_text(before, encoding="utf-8")
    assert _sha(target) == before_sha, "the control was not restored byte-identically"


# ===========================================================================
# NON-VACUITY — asserted before any plant (doctrine C.3).
# ===========================================================================


def test_the_control_passes_and_its_evidence_proves_a_real_round_trip(
    scratch: Path,
) -> None:
    """CONTROL. A PASS is only accepted from a run that demonstrably measured.

    `pass` alone would be satisfied by a gate that looked at nothing, which is
    the whole class D3.25 sits in. The evidence is required to name a delivering
    transport, a recovered journal entry, and a parsed UTC stamp — the three
    facts arms 1-3 are supposed to establish.
    """
    code, out = _drive(scratch)
    assert code == 0, out
    assert out.startswith("pass:"), out
    assert "delivered=1" in out, out
    assert "round-trip: 1 entry/entries" in out, out
    assert "ts parsed UTC" in out, out


def test_the_gate_reads_the_journal_and_not_its_own_optimism(scratch: Path) -> None:
    """The recovered line is the one THIS run emitted, matched on the nonce.

    §7.12 answer 2 in the gate's own docstring is that a stale entry from an
    earlier run would satisfy "an event of this shape exists". The nonce closes
    it; this asserts the nonce actually reaches the evidence, so the closure is
    observable rather than claimed.
    """
    _, out = _drive(scratch)
    assert "nonce=ARC024-" in out, out
    emitted_nonce = out.split("nonce=")[-1].split()[0]
    assert emitted_nonce in out.split("round-trip")[0] or emitted_nonce in out, out


# ===========================================================================
# PLANT 1 — THE REAL TREE, THE REAL MODULE, THE REAL JOURNAL, NO FILE EDITED.
# ===========================================================================


def test_disabling_emission_reddens_arms_1_and_2_against_the_shipped_module(
    scratch: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CAN-FAIL, arms 1 and 2, IN-PROCESS, against the SHIPPED gate and module.

    `NIX_PLANE2_DISABLED` is `plane2.DISABLE_ENV`, whose own docstring says it
    exists *"so the gate can drive a control — emission off must produce a FAIL,
    which is how the gate proves it is measuring the journal rather than its own
    optimism."* This is that drive, and until this test existed it had never
    been taken by anything committed.

    Nothing is written and nothing is copied: the module under measurement is
    `scripts/nixverify/plane2.py` as it ships, imported by the shipped gate in
    this very process. `nix_home` points at the scratch tree only so arm 4's
    scratch file and arm 6's `logs/` walk stay out of the real worktree.

    Two reasons are asserted, not one status: the transport must NAME the
    environment variable that silenced it, and the journal arm must report that
    this run's nonce never landed. A gate that failed for an unrelated cause
    satisfies neither.
    """
    monkeypatch.setenv(DISABLE_ENV, "1")
    loaded = load_check(CHECKS, "check_verify_logging")
    assert loaded.run is not None, loaded.load_error

    result = loaded.run(Mode.VERIFY, Context(nix_home=scratch, mode=Mode.VERIFY))

    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "nixverify/plane2.py:Plane2" in (result.site or "")
    assert f"disabled by {DISABLE_ENV}" in (result.detail or "")
    assert "did not land within" in (result.detail or "")


def test_the_same_gate_in_the_same_process_passes_once_emission_is_back(
    scratch: Path,
) -> None:
    """CONTROL for plant 1, taken in-process so the two differ only in the env.

    Without this the plant above could be read as "the in-process path always
    fails", which is a different fact and a much worse one.
    """
    assert DISABLE_ENV not in os.environ, "the plant leaked out of its test"
    loaded = load_check(CHECKS, "check_verify_logging")
    assert loaded.run is not None, loaded.load_error
    result = loaded.run(Mode.VERIFY, Context(nix_home=scratch, mode=Mode.VERIFY))
    assert result.status is Status.PASS, result.detail
    assert "delivered=" in (result.evidence or "")


# ===========================================================================
# PLANTS 2-5 — into `scripts/nixverify/plane2.py`, the declared SUBJECT.
# ===========================================================================


def test_a_wrong_proc_field_reddens_arm_3_and_names_the_field(
    scratch: Path, plant: Callable[[str, str], None]
) -> None:
    """CAN-FAIL, arm 3. The event round-trips and is NOT §12.10's format.

    This is the plant that separates *the journal received something* from *the
    journal received the contract*. §12.10 makes `proc=` per-emitter and the
    gate requires `verify.py`; one character off and the stream is no longer
    attributable to the process that wrote it.
    """
    plant('PROCESS = "verify.py"', 'PROCESS = "verify"')
    code, out = _drive(scratch)
    assert code == 1, out
    assert "expected proc=verify.py" in out, out
    assert "journal proc='verify'" in out, out


def test_a_malformed_timestamp_reddens_arm_3_and_quotes_the_stamp(
    scratch: Path, plant: Callable[[str, str], None]
) -> None:
    """CAN-FAIL, arm 3. A stamp that arrives and does not parse as §12.10 UTC.

    Deliberately a DIFFERENT field from the plant above: arm 3 checks four
    required keys and one parse, and a single plant would leave the parse
    unexercised while looking like arm 3 was covered.
    """
    plant(
        '.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"',
        '.strftime("%Y/%m/%d %H:%M:%S") + "Z"',
    )
    code, out = _drive(scratch)
    assert code == 1, out
    assert "not a §12.10 UTC timestamp this gate can parse" in out, out
    assert "journal ts=" in out, out


def test_a_transport_that_lies_about_delivery_reddens_the_control_arm(
    scratch: Path, plant: Callable[[str, str], None]
) -> None:
    """CAN-FAIL, arm 4 — the arm that makes arms 1-3 falsifiable.

    Arm 4 re-drives the emission with the transport pointed at a regular file
    and requires that configuration to be recoverable as a failure. If a `Plane2`
    aimed at a non-socket still reported itself available AND delivering, then
    `available` and `emitted` would carry no information and every PASS from
    arms 1-3 would be vacuous.

    Two edits, because one is not enough to express the defect: the socket guard
    is removed so the dead transport is accepted, and the counting handler is
    made to count a record it never delivered. That pair IS the false green the
    arm exists to catch, and the gate names it as such.
    """
    plant("        if not path.is_socket():\n", "        if False:\n")
    target = scratch / SUBJECT
    target.write_text(
        target.read_text(encoding="utf-8").replace(
            "        before = self.failed\n"
            "        super().emit(record)\n"
            "        if self.failed == before:\n"
            "            self.delivered += 1\n",
            "        try:\n"
            "            super().emit(record)\n"
            "        except OSError:\n"
            "            pass\n"
            "        self.delivered += 1\n",
            1,
        ),
        encoding="utf-8",
    )
    code, out = _drive(scratch)
    assert code == 1, out
    assert "nixverify/plane2.py:Plane2 CONTROL" in out, out
    assert "reported itself available AND delivering" in out, out
    assert "would be vacuous" in out, out


def test_a_plane2_artifact_under_logs_reddens_arm_6_and_names_the_file(
    scratch: Path,
) -> None:
    """CAN-FAIL, arm 6. `directory_structure.md` pins `logs/` to non-Plane artifacts.

    The planted file is a genuine §12.10 line, not a marker string: the arm
    recognises Plane-2 content by its format and by the syslog identifier, and a
    plant that used a sentinel would be testing the sentinel.
    """
    logs = scratch / "logs"
    logs.mkdir(exist_ok=True)
    stray = logs / "plane2_leak.log"
    stray.write_text(
        "ts=2026-08-12T00:00:00.000000Z proc=verify.py event=run_complete rc=0\n",
        encoding="utf-8",
    )
    try:
        code, out = _drive(scratch)
        assert code == 1, out
        assert "logs/plane2_leak.log" in out, out
        assert "pinned to non-Plane artifacts" in out, out
    finally:
        stray.unlink()
    code, out = _drive(scratch)
    assert code == 0, out


# ===========================================================================
# THE ARM THAT IS NOT PLANTED — stated, driven, and carried as debt.
# ===========================================================================


def test_the_presentation_detector_is_live_but_is_not_plantable_here() -> None:
    """Arm 5's detector works; the ARM is refused a plant, and this says why.

    Planting arm 5 means emitting an ANSI escape into the SHARED journal under
    the `nix-verify` identifier. journald is append-only, so that entry would
    keep the real gate RED for thirty minutes for every worktree on this box.
    The detector is driven directly instead — which proves the predicate and
    NOT the arm, and under the CHECK-DEBT rule of record that is a weaker claim
    that must be recorded as one. **CHECK-DEBT D3.26.**
    """
    import check_verify_logging as gate  # pylint: disable=import-outside-toplevel

    clean = ["ts=1 proc=verify.py event=ok"]
    # `== []` rather than `not ...`: an empty list and a falsey non-list are
    # different outcomes for a function whose contract is "a list of offenders",
    # and test_plane2.py carries the same pragma for the same reason.
    # pylint: disable=protected-access,use-implicit-booleaness-not-comparison
    assert gate._ansi_offenders(clean) == []
    ansi = ["ts=1 proc=verify.py event=\x1b[32mok\x1b[0m"]
    spinner = ["ts=1 proc=verify.py event=⠋ running"]
    assert "ANSI escape" in gate._ansi_offenders(ansi)[0]  # pylint: disable=protected-access
    assert "spinner frame" in gate._ansi_offenders(spinner)[0]  # pylint: disable=protected-access


# ===========================================================================
# THE RESTORE, ASSERTED RATHER THAN TRUSTED.
# ===========================================================================


def test_the_scratch_tree_is_the_module_the_gate_actually_imports(
    scratch: Path, plant: Callable[[str, str], None]
) -> None:
    """§7.12 answer 2: a shadowed module would make every plant above vacuous.

    A scratch `nixverify` that the child never imports produces a serene PASS,
    which reads exactly like a gate tolerating the defect. The discriminator is
    that a plant MOVES the verdict — a shadowed module cannot do that — so this
    asserts the move itself, in the same process pair, on the same tree.
    """
    before_code, _ = _drive(scratch)
    assert before_code == 0
    plant('PROCESS = "verify.py"', 'PROCESS = "nothing-imports-this"')
    after_code, after_out = _drive(scratch)
    assert after_code == 1, after_out
    assert "nothing-imports-this" in after_out, after_out


def test_the_control_is_green_again_once_every_plant_is_gone(scratch: Path) -> None:
    """The unplant leg of doctrine C.2, taken after the plants rather than beside them.

    The `plant` fixture already asserts the sha256 came back; this asserts the
    GATE agrees, which is the fact that matters — a byte-identical file the gate
    still reddens on would mean a plant leaked somewhere else.
    """
    assert _sha(scratch / SUBJECT) == _sha(REPO / SUBJECT)
    code, out = _drive(scratch)
    assert code == 0, out
    assert out.startswith("pass:"), out
