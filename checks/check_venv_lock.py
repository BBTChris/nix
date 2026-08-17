#!/usr/bin/env python3
# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK and its `standalone_main` footer
# against every other house-style check's. That shape is REQUIRED, not
# accidental duplication (§4.2: every check is independently runnable and
# self-contained).
"""Gate: `scripts/nixverify/venv_lock.py` really serializes venv mutation.

ARC 035 / Phase 0.2. This artifact sat in `checks/gate_coverage_baseline.json`'s
`artifacts` ratchet with its owner walked `ARC 031 -> 032 -> 033 -> 035` — four
arcs, three re-ownings, one over the operator ceiling (D2.31). The brief's
instruction is explicit: **discharge by REAL COVERAGE, not another walk and not
an exclusion.** So this gate does not name the file; it DRIVES it, with two real
OS processes contending for one real `flock`.

## What is actually proven, and by what

Every arm below is a real process pair, never a mock:

* **ARM 1 — a never-locked home reports FREE, and says so by naming absence.**
  `probe_lock` on a scratch `nix_home` with no lock file must return
  `(False, "... absent (never locked)")`. A gate that accepted any `False` here
  would accept an observer that reports "free" because it crashed.
* **ARM 2 — a lock held by ANOTHER PROCESS is observed as HELD, and the holder
  is named.** A real child interpreter acquires `venv_mutation_lock` and blocks
  on a rendezvous file; this process's `probe_lock` must report `held=True` and
  the detail must contain the CHILD's pid. The pid is the load-bearing part: a
  probe that reported HELD by seeing its own hold would be indistinguishable
  from a correct one without it.
* **ARM 3 — a non-blocking acquire under contention RAISES `VenvLockHeld`, and
  the message names the lock path.** Check-contract rule 11: the reason is
  asserted, never the bare fact that something was raised. `RuntimeError` here
  is a FAIL even though "an exception happened" either way — that exact plant is
  in the can-fail suite.
* **ARM 4 — `blocking=True, timeout=T` under a held lock WAITS and then raises.**
  Two halves, because either alone is vacuous: it must raise `VenvLockHeld`
  (so it does not silently proceed into a venv someone else is rebuilding) AND
  the elapsed wall time must be at least `T` (so a timeout that is ignored and
  raises instantly is caught rather than mistaken for correct behaviour).
* **ARM 5 — the lock is released by the holder's DEATH, not by good manners.**
  The child is killed, never asked to clean up. `probe_lock` must then report
  free and this process must acquire successfully. This is the arm that
  distinguishes a real `flock` from a hand-rolled lockfile that leaks forever
  when its owner dies — the failure mode that would wedge every venv-mutating
  check on this box permanently.
* **ARM 6 — the lock file lives under `state/`, never under `.venv`.** The
  module's own docstring makes this a load-bearing claim: the lock must survive
  a `rm -rf .venv` mid-rebuild. Asserted against the resolved path, so moving it
  into the directory it guards reddens here.

## debug.md §7.12 — what would make this gate PASS while measuring nothing?

1. **The child could never actually acquire.** Then ARM 2 would see a free lock
   and the whole contention story would be a fiction agreeing with itself.
   *Closed:* the child writes `HELD` to a rendezvous file only AFTER the
   `with venv_mutation_lock(...)` block is entered, and this gate waits for that
   token with a deadline. No token, no measurement: `CANNOT_MEASURE`, naming the
   timeout — never a PASS.
2. **The child could be this process.** A single-process `flock` re-acquire
   SUCCEEDS on Linux (same fd table semantics differ, and same-process locks are
   a different subject entirely), so an in-process "contention" test would
   measure the opposite of what it claims. *Closed:* the holder is a real
   `subprocess.Popen` of a real interpreter, and ARM 2 asserts the recorded
   holder pid equals `child.pid`, which is by construction not `os.getpid()`.
3. **The subject could be the INSTALLED module rather than the file on disk.**
   `import nixverify.venv_lock` would measure whatever is already in
   `sys.modules` — including a copy from another tree. *Closed:* the module is
   loaded by explicit path from `ctx.nix_home` every run, under a private module
   name, and the child is given that same explicit path.
4. **The scratch home could be the real one.** Driving contention against
   `/home/bbt/nix/state/.venv-mutation.lock` would make this gate fight the very
   repair paths it exists to protect, and a concurrent real repair would make it
   flap. *Closed:* every arm runs against a fresh `mkdtemp` home. The gate
   touches `/tmp` and nothing else, which is what it declares.
5. **Timing could carry the verdict.** ARM 4 asserts an elapsed floor, and a
   loaded box makes wall time a poor instrument in the OTHER direction (too
   long). *Named, not guarded:* only a LOWER bound is asserted, because a
   scheduler can only ever make the wait longer than the timeout, never shorter.
   There is no upper-bound assertion anywhere in this gate.

NON-CORRECTABLE: the subject is the lock every venv-mutating repair path takes.
A gate that rewrote it to satisfy itself would be repairing the instrument that
protects repairs.
"""

from __future__ import annotations

import importlib.util
import shutil
import signal
import subprocess  # nosec B404 - a real child interpreter IS the subject
import sys
import tempfile
import time
from pathlib import Path
from types import ModuleType

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = True
#: Wall time is dominated by ARM 4's deliberate timeout wait, not by work.
EXPECTED_S = 6.0
DEPENDS_ON: tuple[str, ...] = ()
#: A scratch `mkdtemp` home under /tmp, and one real child interpreter. The
#: REAL `.venv` and the real `state/` are never touched — declaring `venv`
#: here would be a false claim in the safe direction, which §4.4 still calls
#: a false claim.
# ARC 035 Stage 2: BOTH interpreter spellings, and the second one is not
# belt-and-braces. `nixverify.observe.covers` matches a `subprocess:` token by
# BASENAME, and this gate spawns `sys.executable` — which is
# `/home/bbt/nix/.venv/bin/python` under the venv interpreter and
# `/usr/bin/python3` under the system one. One spelling is a declaration that is
# TRUE under one documented launch mode and FALSE under the other: D3.140
# exactly. `check_observed_resource_claims` measured it on the merged tree
# rather than taking the branch's word for it.
RESOURCES: tuple[str, ...] = (
    "file-write:/tmp",
    "subprocess:python",
    "subprocess:python3",
)
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is the mutual-exclusion lock every venv-mutating repair path "
    "acquires; a gate that rewrote it to satisfy its own arms would be "
    "repairing the instrument that protects repairs"
)
ANCHOR = "scripts/nixverify/venv_lock.py"
SUBJECTS: tuple[str, ...] = ("scripts/nixverify/venv_lock.py",)

NAME = "check_venv_lock"

#: How long ARM 4 asks `blocking=True` to wait before giving up.
BLOCKING_TIMEOUT_S = 0.5
#: How long ARM 1..5 will wait for the child to announce it holds the lock.
CHILD_READY_TIMEOUT_S = 20.0

#: The holder. Written into the scratch home, run by a real interpreter. It
#: imports the SUBJECT BY PATH (never `import nixverify.venv_lock`), takes the
#: lock, announces, and then sleeps until it is killed — it is never asked to
#: release politely, because ARM 5's whole subject is release-by-death.
_HOLDER_SRC = """\
import importlib.util, os, sys, time
from pathlib import Path

subject, home, ready = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
spec = importlib.util.spec_from_file_location("_nix_venv_lock_holder", subject)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

with mod.venv_mutation_lock(home):
    ready.write_text("HELD %d\\n" % os.getpid())
    while True:
        time.sleep(0.05)
"""


def load_subject(path: Path) -> ModuleType:
    """Load `venv_lock.py` from an explicit path, never from `sys.modules`.

    Named so the can-fail suite can hand this gate a PLANTED copy without
    touching the live module the running process depends on.
    """
    spec = importlib.util.spec_from_file_location("_nix_venv_lock_subject", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"{path}: not loadable as a module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _await_ready(ready: Path, child: subprocess.Popen) -> str:
    """Block until the child says it holds the lock. Raise if it never does."""
    deadline = time.monotonic() + CHILD_READY_TIMEOUT_S
    while time.monotonic() < deadline:
        if ready.is_file():
            text = ready.read_text().strip()
            if text.startswith("HELD"):
                return text
        if child.poll() is not None:
            raise TimeoutError(
                f"holder exited early with rc={child.returncode} before taking "
                f"the lock; nothing was contended, so nothing was measured"
            )
        time.sleep(0.02)
    raise TimeoutError(
        f"holder did not announce the lock within {CHILD_READY_TIMEOUT_S}s; "
        f"no contention was established, so nothing was measured"
    )


def _arm1_absent(subject: ModuleType, home: Path) -> list[str]:
    """A never-locked home is FREE, and the detail names the absence."""
    held, detail = subject.probe_lock(home)
    if held:
        return [f"ARM1: probe_lock reports HELD on a home with no lock file ({detail})"]
    if "absent" not in detail:
        return [
            (
                f"ARM1: probe_lock reports free but does not name the absent lock "
                f"file; detail was {detail!r} — a free verdict with no stated basis "
                f"is indistinguishable from an observer that failed to look"
            )
        ]
    return []


def _arm2_held_names_holder(
    subject: ModuleType, home: Path, child_pid: int
) -> list[str]:
    """A lock held by ANOTHER process reads HELD, and the holder is named."""
    defects: list[str] = []
    held, detail = subject.probe_lock(home)
    if not held:
        defects.append(
            f"ARM2: probe_lock reports FREE while pid {child_pid} holds the "
            f"lock ({detail}) — the observer cannot see a real hold"
        )
        return defects
    if str(child_pid) not in detail:
        defects.append(
            f"ARM2: probe_lock reports HELD but does not name holder pid "
            f"{child_pid}; detail was {detail!r}. Without the holder, a probe "
            f"seeing its OWN hold is indistinguishable from a correct one"
        )
    return defects


def _arm3_nonblocking_reason(subject: ModuleType, home: Path) -> list[str]:
    """A non-blocking acquire under contention raises VenvLockHeld, BY NAME."""
    try:
        with subject.venv_mutation_lock(home):
            pass
    except subject.VenvLockHeld as exc:
        if str(subject.lock_path(home)) not in str(exc):
            return [
                (
                    f"ARM3: VenvLockHeld raised but its message does not name the "
                    f"lock path {subject.lock_path(home)}; message was {str(exc)!r} "
                    f"(check-contract rule 11: the REASON is the assertion)"
                )
            ]
        return []
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return [
            (
                f"ARM3: non-blocking acquire under contention raised "
                f"{type(exc).__name__}, not VenvLockHeld — a caller cannot "
                f"distinguish contention from a broken lock, so it cannot report "
                f"CANNOT_MEASURE for the right reason ({exc})"
            )
        ]
    return [
        (
            "ARM3: non-blocking acquire SUCCEEDED while another process holds the "
            "lock — the lock does not exclude"
        )
    ]


def _arm4_blocking_waits_then_raises(subject: ModuleType, home: Path) -> list[str]:
    """`blocking=True, timeout=T` waits at least T, then raises."""
    started = time.monotonic()
    try:
        with subject.venv_mutation_lock(
            home, blocking=True, timeout=BLOCKING_TIMEOUT_S
        ):
            pass
    except subject.VenvLockHeld:
        elapsed = time.monotonic() - started
        if elapsed < BLOCKING_TIMEOUT_S:
            return [
                (
                    f"ARM4: blocking acquire gave up after {elapsed:.3f}s with a "
                    f"timeout of {BLOCKING_TIMEOUT_S}s — it raised for the right "
                    f"reason at the wrong time, so the timeout is not honoured. "
                    f"Only a LOWER bound is asserted: a loaded box can lengthen "
                    f"this wait, never shorten it"
                )
            ]
        return []
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return [
            (
                f"ARM4: blocking acquire raised {type(exc).__name__}, not "
                f"VenvLockHeld ({exc})"
            )
        ]
    return ["ARM4: blocking acquire SUCCEEDED while another process holds the lock"]


def _arm5_released_by_death(subject: ModuleType, home: Path) -> list[str]:
    """Killing the holder frees the lock. Never asked politely."""
    defects: list[str] = []
    held, detail = subject.probe_lock(home)
    if held:
        defects.append(
            f"ARM5: the holder is dead and the lock is still HELD ({detail}) — "
            f"a lock that outlives its owner wedges every venv-mutating check "
            f"on this box permanently"
        )
        return defects
    try:
        with subject.venv_mutation_lock(home):
            pass
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        defects.append(
            f"ARM5: probe_lock says free after the holder died, but a real "
            f"acquire still raised {type(exc).__name__}: {exc} — the observer "
            f"and the acquirer disagree"
        )
    return defects


def _arm6_lock_lives_outside_venv(subject: ModuleType, home: Path) -> list[str]:
    """The lock must survive `rm -rf .venv`, so it may not live inside it."""
    path = Path(subject.lock_path(home))
    defects: list[str] = []
    venvs = (home / ".venv", home / ".venv-dev")
    if any(venv in path.parents for venv in venvs):
        defects.append(
            f"ARM6: the lock file {path} lives INSIDE the venv it guards; a "
            f"`rm -rf .venv` mid-rebuild would delete the lock and let a "
            f"concurrent probe race past an absent lock into an absent venv"
        )
    if (home / "state") not in path.parents:
        defects.append(
            f"ARM6: the lock file {path} is not under {home / 'state'}; "
            f"docs/directory_structure.md makes state/ the per-worktree, "
            f"gitignored home this mechanism is documented to use"
        )
    return defects


def drive_contention(subject_path: Path, python: str) -> list[str]:
    """Run every arm against the subject at `subject_path`. Returns defects.

    Split out and named so the can-fail suite can drive the SHIPPED arms
    against PLANTED copies of the subject.
    """
    subject = load_subject(subject_path)
    with tempfile.TemporaryDirectory(prefix="nix-venvlock-") as tmp:
        home = Path(tmp)
        # The parent of the lock path the SUBJECT declares, not a hard-coded
        # `state/`: ARM 6 judges WHERE the lock lives, so the setup must not
        # quietly assume the answer. A subject that relocates its lock is then
        # still driven through every contention arm and reddens on ARM 6 alone,
        # rather than dying in setup and reporting CANNOT_MEASURE — which would
        # hide a real defect behind an instrument failure.
        Path(subject.lock_path(home)).parent.mkdir(parents=True, exist_ok=True)
        holder = home / "_holder.py"
        holder.write_text(_HOLDER_SRC)
        ready = home / "_ready"

        defects = _arm1_absent(subject, home)
        defects += _arm6_lock_lives_outside_venv(subject, home)

        # pylint: disable=consider-using-with
        # A `with` block would close the child's pipes at the end of the block,
        # and ARM 5's whole subject is what happens AFTER the holder dies: the
        # kill, the reap, and then a probe and an acquire from THIS process.
        # The lifetime deliberately spans the try/finally below, which kills and
        # reaps unconditionally.
        child = subprocess.Popen(  # nosec B603 - fixed argv, no shell
            [python, str(holder), str(subject_path), str(home), str(ready)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            token = _await_ready(ready, child)
            announced = int(token.split()[1])
            defects += _arm2_held_names_holder(subject, home, announced)
            defects += _arm3_nonblocking_reason(subject, home)
            defects += _arm4_blocking_waits_then_raises(subject, home)
        finally:
            if child.poll() is None:
                child.send_signal(signal.SIGKILL)
            child.wait(timeout=10)
        defects += _arm5_released_by_death(subject, home)
    return defects


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Drive the real lock with two real processes."""
    try:
        subject_path = ctx.nix_home / ANCHOR
        if not subject_path.is_file():
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site=str(subject_path),
                detail=f"{ANCHOR}: absent under {ctx.nix_home} — nothing to drive",
            )
        python = sys.executable or shutil.which("python3") or "python3"
        if ctx.mode is Mode.CORRECT and not CORRECTABLE:
            pass  # measure-only; the correcting arm does not exist by design
        defects = drive_contention(subject_path, python)
        if defects:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site=ANCHOR,
                evidence=f"{ANCHOR}: {len(defects)} of 6 arms failed",
                detail="; ".join(defects),
            )
        return CheckResult(
            name=NAME,
            status=Status.PASS,
            evidence=(
                f"{ANCHOR}: 6/6 arms driven against a real second process — "
                f"absent-reads-free(named), held-reads-HELD(holder pid named), "
                f"non-blocking raises VenvLockHeld naming the path, "
                f"blocking waits >={BLOCKING_TIMEOUT_S}s then raises, "
                f"SIGKILL of the holder releases it, lock file under state/ "
                f"not under .venv. Interpreter: {python}"
            ),
        )
    except TimeoutError as exc:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=ANCHOR,
            detail=(
                f"no contention could be established, so nothing was measured "
                f"(§17): {exc}"
            ),
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# Deliberately duplicated across every checks/check_*.py (§4.2).
# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
