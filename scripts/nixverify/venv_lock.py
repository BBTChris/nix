"""One lock guarding every MUTATION of `.venv` / `.venv-dev` (ARC 030 / Stage 2 A2).

## The hazard this closes

CRUCIBLE-DEPSPLIT rebuilt `.venv` from scratch while other arcs could run.
Worktree/index isolation (Stage 2 A1) gives every concurrent arc its own git
index and HEAD, but every arc still resolves through the SAME `.venv` /
`.venv-dev` on disk — there is one Python environment on this box, not one
per arc. A check reading `.venv`'s installed-package state (`check_venv`,
`check_python_deps`, `check_python_transitive_deps`) while another process is
mid-`pip install` — or mid-`rm -rf && python -m venv` — is not reading a
stable subject: it is reading a state that will not exist by the time the
verdict is printed. Reporting PASS or FAIL against that is reporting on
nothing (`nix_check_contract.md` §17, CLAUDE.md directive 5: verified
on-disk state outranks memory — a moving target is not verified state).

Concrete, already-measured instance of the CLASS of hazard this generalizes:
reconciling `main` through arc-026..arc-029 during this arc's Phase 1 showed
`check_price_ring` FAILING against `.venv-dev/lib/python3.14/site-packages/
numpy/...` at every pre-CRUCIBLE-DEPSPLIT commit, purely because `.venv-dev`
(untracked, persists across `git checkout`) existed on disk before the code
excluding it from the scan did. That was a code/environment skew across TIME
(checkout vs. build). This lock closes the same skew across CONCURRENT
PROCESSES on the same checkout.

## Why a lock and not a per-arc venv

Building a real per-worktree `.venv` (a full `ib_async`/`numpy`/etc install,
hundreds of MB, several minutes) for every one of N concurrent arc worktrees
was rejected as disproportionate to what Stage 2 A2 needs to PROVE: that a
concurrent mutation cannot silently corrupt another arc's gate results. A
lock gives every gate an OBSERVABLE fact ("is `.venv` mid-mutation right
now?") that turns a spurious FAIL into an honest CANNOT_MEASURE. It does not,
by itself, stop two arcs from wanting to run `--correct` at the same time —
it makes the second one find out immediately, rather than racing.

## Mechanics

`flock(2)` on one file under `state/`, `LOCK_EX | LOCK_NB` — never blocking:
a check performing a repair must find out AT ONCE that someone else holds it
and report CANNOT_MEASURE, never hang the runner waiting. `state/` is
gitignored wholesale (`docs/directory_structure.md`) and per-worktree (it is
not a tracked path), so the lock file itself does not collide across
worktrees the way `.venv` does — each worktree's OWN attempt to mutate ITS
OWN on-disk venv is what this guards, and in this repo's current single-
shared-venv-on-the-box topology (`.venv` lives at a fixed absolute path
relative to whichever `nix_home` a check was given) two worktrees pointed at
the SAME physical `.venv` (e.g. via a symlink, or both invoked with
`nix_home=/home/bbt/nix`) are correctly serialized by it; two worktrees each
with their OWN separate `.venv` are correctly NOT serialized against each
other, because they are not contending for the same subject.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import os
import time
from collections.abc import Iterator
from pathlib import Path

#: Under `state/`, never under `.venv` itself — the lock must survive a
#: `rm -rf .venv` mid-rebuild so a probe running concurrently can still find
#: and honour it instead of racing past an absent lock file into an absent
#: venv and calling that CANNOT_MEASURE for the wrong reason.
LOCK_FILENAME = ".venv-mutation.lock"


class VenvLockHeld(Exception):
    """Raised by `venv_mutation_lock` when the lock is held by someone else."""


def lock_path(nix_home: Path) -> Path:
    """Where the lock file lives for a given `nix_home`. Named, not hidden."""
    return nix_home / "state" / LOCK_FILENAME


@contextlib.contextmanager
def venv_mutation_lock(
    nix_home: Path, *, blocking: bool = False, timeout: float = 0.0
) -> Iterator[None]:
    """Hold the venv-mutation lock for the body of the `with` block.

    Non-blocking by default: a repair path (`check_venv._create`,
    `check_python_deps.repair`) must discover contention immediately and
    report CANNOT_MEASURE rather than block the whole runner on someone
    else's rebuild. Raises `VenvLockHeld` when the lock cannot be acquired.
    The PID is written into the file so a concurrent OBSERVER
    (`probe_lock`) can name who holds it — best-effort diagnostic only,
    never load-bearing: the flock state, not the PID text, is the fact.
    """
    lock_dir = nix_home / "state"
    lock_dir.mkdir(parents=True, exist_ok=True)
    path = lock_path(nix_home)
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                if not blocking or time.monotonic() >= deadline:
                    raise VenvLockHeld(f"{path}: held by another process") from exc
                time.sleep(0.05)
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        os.fsync(fd)
        try:
            yield
        finally:
            try:
                os.ftruncate(fd, 0)
            except OSError:
                pass
    finally:
        os.close(fd)  # closing the fd releases the flock (POSIX semantics)


def probe_lock(nix_home: Path) -> tuple[bool, str]:
    """Is the lock held RIGHT NOW? `(held, detail)` — never raises.

    Non-blocking: attempts to acquire and immediately releases. `held=True`
    means some OTHER process holds it at this instant (this probe's own
    attempt failed, and it never acquired, so it cannot be seeing its own
    hold) — a caller observing that must treat `.venv`'s package state as a
    moving target, not a stable subject (§17). Absence of the lock FILE is
    reported as free, not as an error: a venv that has never been mutated
    under this mechanism has no lock file yet, and that is a legitimate,
    common state, not a defect.
    """
    path = lock_path(nix_home)
    if not path.is_file():
        return False, f"{path}: absent (never locked)"
    try:
        fd = os.open(str(path), os.O_RDWR)
    except OSError as exc:
        return False, f"{path}: unreadable ({exc!r}) — treated as free"
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            try:
                holder = os.read(fd, 64).decode("utf-8", "replace").strip()
            except OSError:
                holder = ""
            return True, f"{path}: HELD ({holder or 'unknown holder'})"
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False, f"{path}: free"
    finally:
        os.close(fd)
