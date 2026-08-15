"""Observe a check's ACTUAL resource use at runtime (ARC 025, CHECK-DEBT D2.27).

`optimize.py` states the bound it cannot close in its own docstring:

> Disjointness is checked over **declarations**. Two checks that both dial port
> 4002 and both declare `RESOURCES = ()` will pass this check and collide at
> runtime. **No static mechanism can close that gap.**

That sentence is true of STATIC mechanisms and only of static mechanisms. ARC 024
already built the dynamic one and then threw it away: a `socket.connect` spy over
a real run of both Gateway gates recorded each dialling `('127.0.0.1', 4002)`,
which is the measurement that refused Stage 3.1's parallel-block spelling
(D1.41). **That spy was never banked as code** — the repo keeps its *conclusion*
(`test_optimize.py::test_the_two_gateway_gates_share_an_endpoint_and_must_not_go_parallel`,
which re-asserts the registry block is sequential and observes nothing) and lost
its *instrument*. This module is that instrument, promoted from a one-off
measurement to a standing one, and `checks/check_observed_resource_claims.py` is
the gate that runs it every time `verify.py` runs.

## Doctrine C.9 — checked before building, not after

No instrument in this tree owned "what a check actually touches". The two `spy`
callables in `scripts/tests/test_check_ibgateway_*.py` are monkeypatched stubs
that replace the handshake so the *gate's* logic can be driven; they observe
nothing about resource use. `optimize._disjointness` owns "do the DECLARATIONS
collide", and that property is left entirely to it — this module never re-derives
disjointness. The split: **`optimize.py` compares declaration to declaration;
this compares declaration to REALITY.**

## The mechanism: CPython audit hooks (PEP 578), not monkeypatching

`sys.addaudithook` is used rather than patching `socket`/`subprocess`/`open`,
for the same structural reason `declarations.py` chose AST over import: the
guarantee has to hold for a check nobody has written yet.

* An audit hook **cannot be removed** once installed and **cannot be bypassed**
  by re-importing the module, by holding a reference captured before the patch,
  or by reaching through to `_socket`. A monkeypatch is defeated by any of the
  three, silently, and a defeated spy reports *no claims* — which is exactly the
  false green this gate exists to prevent.
* The events fire **inside CPython**, at the call, so a claim is recorded whether
  or not the call succeeds. That is load-bearing for the masked-hazard rule
  below: a `connect` to a refused port still emits `socket.connect`.

## What is observed, and what is NOT — stated, never implied

| class | how | token |
|---|---|---|
| TCP/UDP endpoints | audit `socket.connect`, `socket.bind` | `socket:HOST:PORT` |
| unix sockets (the journal) | same events, `AF_UNIX` address | `unix-socket:PATH` |
| file WRITES | audit `open` (write mode/flags), plus the `os.*` mutators | `file-write:PATH` |
| child processes / services | audit `subprocess.Popen` | `subprocess:PROGRAM` |

**NOT observed, and a caller must not read a clean result as covering these:**

1. **File READS.** A read is not a contended claim and including it would drown
   every real finding in `importlib` noise.
2. **Anything the CHILD process does.** Audit hooks are per-interpreter. A check
   that shells out to `systemctl` is recorded as `subprocess:/usr/bin/systemctl`
   and NOT as whatever sockets `systemctl` opens.
3. **Code paths this run did not take.** This is a dynamic instrument: it reports
   what one execution did, not what the check is capable of. A check that dials
   4002 only when a config file exists is unobserved on a box without that file.
   This is the residual, it is *narrower* than D2.27's residual, and it is named
   rather than papered over.
4. **A `dir_fd` whose descriptor has already closed.** CHECK-DEBT D3.118 is
   discharged by resolving `dir_fd`-relative `os.*` targets through
   `/proc/self/fd/<n>` (see `resolve_fd`), which is what makes a
   `TemporaryDirectory` teardown record `file-write:/tmp/<dir>/<name>` instead
   of the bare `file-write:<name>` no honest `file-write:<root>` declaration
   could ever cover. The residual is narrow and named: if the descriptor is
   gone by the time the hook reads it, or `/proc` is not mounted, the claim
   falls back to the unresolved basename. It is never DROPPED — a lost claim
   is indistinguishable from one never made, which is the whole defect.

5. **Module-level side effects.** Observation is armed AFTER the check module is
   imported and disarmed before the record is written, so import machinery does
   not appear as the check's claims. `--optimize` never imports a check at all,
   so a module-level socket is a hazard for the ENGINE, not for planning.

## THE MASKED-HAZARD RULE — the reason this file records outcomes at all

**A safety property proven while its subject is unavailable is not proven.**

The IB Gateway on this box is down. Both Gateway gates get `ECONNREFUSED`, and a
naive observer would see two gates that touched nothing and report a serene
green over the exact collision D1.41 measured. So two facts are recorded, not
one:

* the **claim** — from the unbypassable audit hook. *The attempt IS the claim*: a
  connect to a dead port is a claim on that endpoint, because the port being dead
  today says nothing about tomorrow.
* the **outcome** — from a thin wrapper around `socket.connect`/`connect_ex`,
  which the audit hook cannot supply because it fires BEFORE the call. An
  `ECONNREFUSED`/`ETIMEDOUT`/`EHOSTUNREACH` marks the endpoint UNREACHABLE, and
  the consumer must return `CANNOT_MEASURE` for that check — **never PASS** —
  because everything downstream of that connect did not execute.

Two mechanisms, two distinct facts, one property each — not two instruments for
one property. The wrapper is *defeatable* and that is acceptable precisely
because it is not the one carrying the safety claim; if it is bypassed, the
audit hook still records the claim and the check is compared as if reachable,
which is the strict direction.
"""

from __future__ import annotations

import dataclasses
import errno
import json
import os
import socket
import subprocess  # nosec B404 - re-executes this file, fixed argv, no shell
import sys
import tempfile
from pathlib import Path
from typing import Any

#: Audit events this module cares about. Membership is tested first in the hook
#: because the hook runs on EVERY audited event in the interpreter.
_WATCHED = frozenset(
    {
        "socket.connect",
        "socket.bind",
        "open",
        "subprocess.Popen",
        "os.remove",
        "os.rename",
        "os.mkdir",
        "os.rmdir",
        "os.truncate",
    }
)

#: Writes that are interpreter bookkeeping, not the check's claim.
_WRITE_NOISE = ("__pycache__", ".pyc", "/dev/null")

#: A runaway check must not be able to make the record unboundedly large; a gate
#: that OOMs its own runner has measured nothing. Well above any real check.
_MAX_CLAIMS = 500

#: errnos that mean "the subject was not there to be observed" rather than "the
#: check chose not to talk to it". EPIPE/ECONNRESET are deliberately absent: they
#: mean the peer WAS there.
_UNREACHABLE_ERRNOS = frozenset(
    {
        errno.ECONNREFUSED,
        errno.ETIMEDOUT,
        errno.EHOSTUNREACH,
        errno.ENETUNREACH,
        errno.ENETDOWN,
        errno.EHOSTDOWN,
        errno.ENOENT,  # AF_UNIX: the socket path does not exist
    }
)

#: Ceiling on ONE observed check. Exhausting it is CANNOT_MEASURE, never PASS.
PER_CHECK_TIMEOUT_S = 60.0

#: `dir_fd` values that mean "there is no directory descriptor". CPython passes
#: -1 for an omitted argument and `AT_FDCWD` (-100) for an explicit
#: cwd-relative call; neither names a directory this module could resolve.
_NO_DIR_FD = frozenset({-1, -100})

#: CHECK-DEBT D3.118. Per audited `os.*` mutator: (path arg index, dir_fd arg
#: index). `shutil.rmtree` — which `tempfile.TemporaryDirectory.__exit__` uses —
#: takes CPython's TOCTOU-safe fd-relative path when the platform supports
#: `os.open(..., dir_fd=...)`, and unlinks each entry as
#: `os.unlink(entry.name, dir_fd=parent_fd)`. The PEP 578 event then fires with
#: that literal `(basename, dir_fd)` pair, so decoding `args[0]` alone records
#: `file-write:sample.py` — a bare fixture basename no honest
#: `file-write:<root>` declaration can cover, and which doctrine C.4 forbids
#: papering over with a literal per-filename token. The index is per EVENT
#: because the signatures differ: `os.remove(path, dir_fd)`,
#: `os.mkdir(path, mode, dir_fd)`, `os.rename(src, dst, src_dir_fd, dst_dir_fd)`.
#: `os.truncate(fd, length)` carries no dir_fd at all — its first argument may
#: itself BE a descriptor, which is the `None` case below.
_DIR_FD_ARG: dict[str, int | None] = {
    "os.remove": 1,
    "os.rmdir": 1,
    "os.mkdir": 2,
    "os.rename": 2,
    "os.truncate": None,
}


#: The POSIX shared-memory mount. A vocabulary constant this module COMPARES
#: claims against; nothing here ever opens it.
_SHM_ROOT = "/dev/shm"  # nosec B108


def resolve_fd(fd: int) -> str:
    """The path an open descriptor names, via `/proc/self/fd/<n>`, or ''.

    Linux-specific and deliberately so: this project's architecture invariant
    is Ubuntu-only, and the alternative (threading a per-process fd table
    through an audit hook that must not itself perform audited operations) is
    strictly worse. `os.readlink` emits no audit event — MEASURED, not
    assumed — so this cannot re-enter the hook that calls it.

    Total by construction. A descriptor closed between the event firing and
    this call, a `/proc` that is not mounted, or a non-Linux kernel all yield
    '' and the caller falls back to the unresolved name: a claim recorded
    under a bare basename is a weaker record, an exception raised inside the
    hook is a LOST claim, and D3.118's whole point is that a lost claim is
    indistinguishable from one never made.
    """
    try:
        return os.readlink(f"/proc/self/fd/{int(fd)}")
    except OSError, ValueError, TypeError:
        return ""


@dataclasses.dataclass(frozen=True)
class ObservedRun:
    """What one check was measured doing. `error` non-empty means UNMEASURED."""

    check: str
    claims: tuple[str, ...] = ()
    #: (endpoint, errno-name) for every connect that could not reach its subject.
    unreachable: tuple[tuple[str, str], ...] = ()
    #: The observed check's own verdict, carried for context only — never a
    #: verdict input here. This gate reports on resource CLAIMS, not on whether
    #: the observed check passed; conflating them would make one gate's red
    #: another gate's red, which is how a suite loses attribution.
    status: str = ""
    #: Why nothing could be observed. Empty on a completed observation.
    error: str = ""

    @property
    def measured(self) -> bool:
        """True when the check ran to completion under an armed observer."""
        return not self.error


# ---------------------------------------------------------------------------
# CHILD SIDE — armed inside the observed check's own process.
# ---------------------------------------------------------------------------


class _Recorder:
    """Collects claims. Deliberately does nothing that could itself be audited.

    The hook must not open files, log, or format lazily: every one of those is an
    audited event and would re-enter this hook. `_armed` is flipped around the
    observed call so import machinery and the record write are outside the window.
    """

    def __init__(self) -> None:
        self.armed = False
        self.claims: set[str] = set()
        self.unreachable: set[tuple[str, str]] = set()
        #: Times the hook could not classify an event. NEVER silently zero: a
        #: hook that swallowed an exception has LOST a claim, and a lost claim is
        #: indistinguishable from a claim that was never made. Non-zero makes the
        #: whole observation unmeasured rather than clean.
        self.lost = 0

    def add(self, kind: str, target: str) -> None:
        """Record one claim, bounded."""
        if len(self.claims) < _MAX_CLAIMS:
            self.claims.add(f"{kind}:{target}")

    def hook(self, event: str, args: tuple) -> None:
        """The audit hook. Never raises — an exception here would abort the check.

        A hook that propagated would turn an observation into a defect in the
        thing observed, so it cannot raise; but it must not swallow silently
        either, so every failure increments `lost` and the caller degrades the
        run to UNMEASURED.
        """
        if not self.armed or event not in _WATCHED:
            return
        try:
            self._dispatch(event, args)
        except Exception:  # noqa: BLE001 pylint: disable=broad-exception-caught
            self.lost += 1

    def _dispatch(self, event: str, args: tuple) -> None:
        """Map one audit event onto zero or one claim."""
        if event in ("socket.connect", "socket.bind"):
            self._on_socket(args)
        elif event == "open":
            self._on_open(args)
        elif event == "subprocess.Popen":
            self._on_popen(args)
        else:  # os.remove / rename / mkdir / rmdir / truncate
            self._on_path(event, args)

    def _on_socket(self, args: tuple) -> None:
        kind, target = format_address(args[1] if len(args) > 1 else None)
        self.add(kind, target)

    def _on_open(self, args: tuple) -> None:
        path = args[0] if args else None
        if path is None or isinstance(path, int):
            return
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else None
        if not _is_write(mode, flags):
            return
        text = os.fsdecode(path)
        if text and not any(noise in text for noise in _WRITE_NOISE):
            self.add("file-write", text)

    def _on_popen(self, args: tuple) -> None:
        program = args[0] if args else None
        if program is not None and not isinstance(program, int):
            self.add("subprocess", os.fsdecode(program))

    def _on_path(self, event: str, args: tuple) -> None:
        """`os.*` mutators, with D3.118's `dir_fd` resolution applied.

        Three shapes, all real and all previously collapsed into one:

        * an absolute (or cwd-relative) path with no descriptor — decoded as
          before;
        * a basename relative to a `dir_fd`, which `shutil.rmtree` produces on
          every `TemporaryDirectory` teardown — joined to the directory the
          descriptor names;
        * `os.truncate(fd, length)`, whose first argument may itself BE a
          descriptor rather than a path. The old code returned silently here,
          so a truncate-by-fd — the one `os.*` mutator that destroys content
          rather than a directory entry — was invisible.
        """
        target = args[0] if args else None
        if target is None:
            return
        if isinstance(target, int):
            # os.truncate(fd, length): the descriptor IS the subject.
            resolved = resolve_fd(target)
            if resolved:
                self.add("file-write", resolved)
            return
        self._add_path(args, 0, _DIR_FD_ARG.get(event))
        if event == "os.rename":
            # `os.rename(src, dst, src_dir_fd, dst_dir_fd)`. The DESTINATION
            # is the write — a rename over an existing file destroys it — and
            # only `args[0]` was ever recorded, so the atomic-write idiom
            # (write to a temp name, rename into place) claimed the temp name
            # and never the file it actually replaced.
            self._add_path(args, 1, 3)

    def _add_path(self, args: tuple, index: int, dir_fd_index: int | None) -> None:
        """One path argument of an `os.*` mutator, `dir_fd`-resolved."""
        target = args[index] if len(args) > index else None
        if target is None or isinstance(target, int):
            return
        text = os.fsdecode(target)
        if not text:
            return
        if dir_fd_index is not None and not text.startswith("/"):
            raw = args[dir_fd_index] if len(args) > dir_fd_index else None
            if isinstance(raw, int) and raw not in _NO_DIR_FD:
                directory = resolve_fd(raw)
                if directory:
                    text = f"{directory.rstrip('/')}/{text}"
        self.add("file-write", text)


def format_address(address: object) -> tuple[str, str]:
    """Canonicalise a socket address into (kind, target). Total, never raises."""
    if isinstance(address, (bytes, bytearray)):
        decoded = os.fsdecode(bytes(address)).strip("\x00")
        return "unix-socket", decoded or "<abstract>"
    if isinstance(address, str):
        return "unix-socket", address
    if isinstance(address, tuple) and len(address) >= 2:
        return "socket", f"{address[0]}:{address[1]}"
    return "socket", repr(address)


def _is_write(mode: object, flags: object) -> bool:
    """True when this `open` is capable of mutating the file.

    `io.open` supplies the mode string; `os.open` supplies `None` and an int flag
    set. Both spellings are handled because a check using `os.open` to write must
    not be invisible.
    """
    if isinstance(mode, str):
        return any(char in mode for char in "wxa+")
    if isinstance(flags, int):
        writable = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
        return bool(flags & writable)
    return False


def _install_outcome_wrapper(recorder: _Recorder) -> None:
    """Wrap `socket.connect`/`connect_ex` to learn WHY a connect failed.

    The audit hook fires before the syscall and so cannot know the outcome. This
    supplies the second fact the masked-hazard rule needs. It is bypassable (a
    check reaching straight into `_socket` defeats it) and that is tolerable
    because the CLAIM — the part carrying the safety verdict — comes from the
    hook, which is not.
    """
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def _note(address: object, err: int) -> None:
        if err in _UNREACHABLE_ERRNOS and len(recorder.unreachable) < _MAX_CLAIMS:
            _, target = format_address(address)
            recorder.unreachable.add((target, errno.errorcode.get(err, str(err))))

    def connect(self: Any, address: Any) -> None:
        try:
            real_connect(self, address)
        except OSError as exc:
            if recorder.armed and exc.errno is not None:
                _note(address, exc.errno)
            raise

    def connect_ex(self: Any, address: Any) -> int:
        code = real_connect_ex(self, address)
        if recorder.armed and code:
            _note(address, code)
        return code

    # `Any` above and the ignores here: the stubs type the address parameter as
    # the union of every address family, and this wrapper is deliberately
    # family-agnostic — it forwards whatever it was handed, unexamined, so that a
    # future address family it has never heard of still reaches the real call.
    socket.socket.connect = connect  # type: ignore[method-assign,assignment]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign,assignment]


def _child(checks_dir: Path, name: str, nix_home: Path, record: Path) -> int:
    """Import one check, arm the observer, run it, and write the record.

    Verify-only, always. `Mode.VERIFY` is not a parameter of this function on
    purpose: an observation pass that could be asked to CORRECT would be an
    instrument with a mutation flag, and `--optimize`/observation are planning
    activities. Ruling 1's "a flagless check never mutates" is what makes running
    the whole population safe.
    """
    from nixverify.contract import Context, Mode  # pylint: disable=C0415
    from nixverify.loader import load_check  # pylint: disable=C0415

    loaded = load_check(checks_dir, name)
    recorder = _Recorder()
    payload: dict[str, object] = {"check": name}
    if loaded.load_error or loaded.run is None:
        # The loader's message does not carry the check's name (it is supplied by
        # the engine downstream), and an observation record that cannot say WHICH
        # check failed to load is a finding nobody can act on.
        payload["error"] = f"{name}: {loaded.load_error or 'no run() callable'}"
        record.write_text(json.dumps(payload), encoding="utf-8")
        return 0

    _install_outcome_wrapper(recorder)
    sys.addaudithook(recorder.hook)
    recorder.armed = True
    try:
        result = loaded.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))
        status = getattr(getattr(result, "status", ""), "value", "")
    except BaseException as exc:  # noqa: BLE001 pylint: disable=broad-exception-caught
        # The claims observed BEFORE the raise are kept: a check that dialled a
        # port and then blew up still claimed the port. But the run is marked
        # unmeasured, because everything after the raise is unobserved — the same
        # reasoning as the unreachable case.
        status = ""
        payload["error"] = f"{name} raised under observation: {exc!r}"
    else:
        payload["status"] = status
    finally:
        recorder.armed = False

    if recorder.lost and "error" not in payload:
        payload["error"] = (
            f"{name}: the audit hook failed to classify {recorder.lost} event(s) — "
            "claims may be MISSING, so this observation is not clean"
        )
    payload["claims"] = sorted(recorder.claims)
    payload["unreachable"] = sorted(recorder.unreachable)
    record.write_text(json.dumps(payload), encoding="utf-8")
    return 0


# ---------------------------------------------------------------------------
# PARENT SIDE — drives one observation per subprocess.
# ---------------------------------------------------------------------------


def observe_check(
    checks_dir: Path,
    name: str,
    nix_home: Path,
    timeout: float = PER_CHECK_TIMEOUT_S,
) -> ObservedRun:
    """Run one check under the observer, in a FRESH process, and read the record.

    A fresh process per check for three reasons, all of which have bitten this
    project: audit hooks are permanent and would leak into the runner; `loader`
    permanently appends to `sys.path`; and a check that calls `sys.exit`, hangs,
    or segfaults must cost one observation rather than the whole gate. It is also
    the same shape as `actuation.reverify` — the process doing the measuring is
    not the process being measured.
    """
    with tempfile.TemporaryDirectory(prefix="nix-observe-") as tmp:
        record = Path(tmp) / "record.json"
        argv = [
            sys.executable,
            str(Path(__file__).resolve()),
            str(checks_dir),
            name,
            str(nix_home),
            str(record),
        ]
        try:
            proc = subprocess.run(  # nosec B603 - argv built here, no shell
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ObservedRun(
                check=name,
                error=(
                    f"observation timed out after {timeout}s — the check did not "
                    "finish, so its resource use is UNOBSERVED"
                ),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return ObservedRun(check=name, error=f"observer could not run: {exc!r}")
        if not record.is_file():
            tail = (proc.stderr or proc.stdout or "").strip()[-400:]
            return ObservedRun(
                check=name,
                error=(
                    f"observer wrote no record (exit {proc.returncode}); "
                    f"stderr: {tail or '-'}"
                ),
            )
        return _read_record(name, record)


def _read_record(name: str, record: Path) -> ObservedRun:
    """Parse the child's record, loudly."""
    try:
        payload = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ObservedRun(check=name, error=f"observer record unreadable: {exc!r}")
    return ObservedRun(
        check=name,
        claims=tuple(str(claim) for claim in payload.get("claims", ())),
        unreachable=tuple(
            (str(pair[0]), str(pair[1]))
            for pair in payload.get("unreachable", ())
            if isinstance(pair, (list, tuple)) and len(pair) == 2
        ),
        status=str(payload.get("status", "")),
        error=str(payload.get("error", "")),
    )


# ---------------------------------------------------------------------------
# THE VOCABULARY — how a DECLARED token is matched against an OBSERVED claim.
# ---------------------------------------------------------------------------
#
# The declaration side is prose written by check authors ("venv", "journal",
# "network:pypi", "port:4002"); the observed side is canonical
# (`socket:127.0.0.1:4002`). Something has to translate, and the translation is
# the one place this gate could be quietly weakened — a permissive rule turns
# every FAIL into a PASS. So the table is small, closed, and every rule is stated
# here rather than spread through the gate:
#
#   venv            -> any claim whose path lies under <nix_home>/.venv
#   shm             -> any file-write under /dev/shm (POSIX shared memory)
#   state/ | state  -> any file-write under <nix_home>/state
#   journal         -> /dev/log, /run/systemd/journal/*, journalctl, systemd-cat
#   service:<n>     -> systemctl / journalctl subprocesses
#   network:<n>     -> any socket: claim to a NON-loopback host
#   port:<n>        -> any socket: claim on port <n>, any host
#   <kind>:<target> -> the canonical spellings, matched exactly
#                      (file-write and subprocess additionally match by prefix
#                       and by basename respectively)
#
# An unknown declared token matches ONLY by exact string equality. Unknown means
# unknown; guessing what a novel token was meant to cover is how a vocabulary
# becomes a rubber stamp.


def _under(path: str, root: Path) -> bool:
    """True when `path` lies under `root`, tolerant of symlinked roots."""
    candidate = Path(path)
    for base in (root, root.resolve()):
        try:
            if candidate == base or base in candidate.parents:
                return True
            if base in candidate.resolve().parents:
                return True
        except OSError:
            continue
    return False


def _claim_path(claim: str) -> str:
    """The filesystem path a `file-write:`/`subprocess:` claim names, else ''."""
    for prefix in ("file-write:", "subprocess:"):
        if claim.startswith(prefix):
            return claim[len(prefix) :]
    return ""


def _covers_journal(claim: str) -> bool:
    """`journal` covers the syslog socket and the journal's own CLI tools."""
    if claim.startswith("unix-socket:"):
        target = claim[len("unix-socket:") :]
        return target == "/dev/log" or target.startswith("/run/systemd/journal")
    return Path(_claim_path(claim)).name in ("journalctl", "systemd-cat")


def _covers_shm(claim: str) -> bool:
    """`shm` covers POSIX shared memory — any write under `/dev/shm`.

    Added with D3.118's `os.truncate(fd, length)` arm, which made these claims
    visible for the first time: `multiprocessing.shared_memory` sizes a fresh
    segment with `os.ftruncate(fd, size)`, and before the repair that
    fd-relative event carried no path at all. Three checks
    (`check_price_ring`, `check_feed_kill_drill`, `check_plane2_across_kill`)
    have declared `shm` since ARC 021; the token was simply unknown to this
    table and matched by exact string equality only. A DIRECTORY rule, not a
    per-segment literal — segment names carry a pid and a random suffix, so an
    exact token would be the C.4 anchor this gate refuses.
    """
    path = _claim_path(claim)
    return bool(path) and (path == _SHM_ROOT or path.startswith(f"{_SHM_ROOT}/"))


#: The two EXACT-MATCH vocabulary tokens whose rule is a whole predicate.
#: A dict here and not in `covers` at large: `covers` reads top to bottom and
#: the ORDER of its prefix rules is load-bearing (the fall-through to `False`
#: is what makes an unrecognised token match by exact equality only). These two
#: are exact, disjoint token names, so no order between THEM exists to hide.
_EXACT_TOKEN_RULES = {"journal": _covers_journal, "shm": _covers_shm}


def _covers_socket_token(declared: str, claim: str) -> bool:
    """`port:N`, `network:*` and the canonical `socket:`/`unix-socket:` forms."""
    if declared.startswith("port:"):
        return claim.startswith("socket:") and claim.rsplit(":", 1)[-1] == declared[5:]
    if declared.startswith("network:"):
        if not claim.startswith("socket:"):
            return False
        host = claim[len("socket:") :].rsplit(":", 1)[0]
        return host not in ("127.0.0.1", "::1", "localhost")
    return False


def covers(  # pylint: disable=too-many-return-statements
    declared: str, claim: str, nix_home: Path
) -> bool:
    """Does one DECLARED resource token account for one OBSERVED claim?

    Nine returns is nine independent vocabulary rules read top to bottom, which is
    exactly the shape the table above documents. Collapsing them into a dispatch
    dict would hide the ORDER — and the order is load-bearing, because the final
    fall-through to `False` is what makes an unrecognised token match by exact
    equality only.

    The whole gate turns on this predicate, so it is total, side-effect free, and
    directly unit-tested rather than only exercised through the gate.
    """
    if declared == claim:
        return True
    if declared == "venv":
        path = _claim_path(claim)
        return bool(path) and _under(path, nix_home / ".venv")
    if declared in ("state/", "state"):
        path = _claim_path(claim)
        return claim.startswith("file-write:") and _under(path, nix_home / "state")
    exact = _EXACT_TOKEN_RULES.get(declared)
    if exact is not None:
        return exact(claim)
    if declared.startswith("service:"):
        return Path(_claim_path(claim)).name in ("systemctl", "journalctl")
    if _covers_socket_token(declared, claim):
        return True
    if declared.startswith("file-write:") and claim.startswith("file-write:"):
        # A declared path may be repo-relative (the spelling SUBJECTS uses) or
        # absolute. Relative resolves against nix_home, so a declaration reads the
        # same on this box and on the next one — doctrine C.4, never anchor to
        # something that moves, applied to the declaration rather than the gate.
        target = Path(declared[len("file-write:") :])
        root = target if target.is_absolute() else nix_home / target
        return _under(_claim_path(claim), root)
    if declared.startswith("subprocess:") and claim.startswith("subprocess:"):
        return Path(_claim_path(claim)).name == Path(declared[11:]).name
    return False


def undeclared(
    claims: tuple[str, ...], resources: tuple[str, ...], nix_home: Path
) -> tuple[str, ...]:
    """The observed claims no declared token accounts for. The finding, in one line."""
    return tuple(
        claim
        for claim in claims
        if not any(covers(token, claim, nix_home) for token in resources)
    )


def _main(argv: list[str]) -> int:
    """Child entry point: `observe.py <checks_dir> <name> <nix_home> <record>`."""
    if len(argv) != 4:
        print(
            "usage: observe.py <checks_dir> <check_name> <nix_home> <record.json>",
            file=sys.stderr,
        )
        return 2
    checks_dir, name, nix_home, record = argv
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    return _child(Path(checks_dir), name, Path(nix_home), Path(record))


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
