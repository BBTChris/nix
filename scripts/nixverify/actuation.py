# pylint: disable=duplicate-code
# R0801 pairs this module's `systemctl show` call with check_ibgateway_service's
# Gateway probe over six lines of subprocess.run KEYWORD BOILERPLATE
# (capture_output/text/timeout/check). That is argument shape, not shared logic:
# the two calls run different programs, for different subjects, with different
# failure meanings. Factoring them into a common helper to satisfy a similarity
# counter would couple a session-interlock query to a broker-session probe, which
# is a worse object than the duplication. On its own line because the Similarities
# checker does not honour a same-line pragma (see check_venv.py's note).
"""Actuation: verify / correct / install, and the guards around the last two.

ARC 024 Stage 2. Operator ruling 1: *every check must be able to verify, correct
and install, selected by passed-in flags.* Ruling 3: *when a check corrects or
installs, it runs a verify afterwards to confirm the change actually happened.*

## What was already true, measured before anything was built

`verify.py` has carried `--mode verify|correct|install` since ARC 009, and the
mode is already handed to every check as `run(mode, ctx)`. The default is already
`Mode.VERIFY`. So the **[ARCHITECT RULING]** that a flagless invocation never
mutates is not a change of policy — it is the policy already on disk, now
written down and enforced rather than merely observed.

What was missing is that a check's *own* CLI had no way to ask for correction:
all 13 hardcoded `Mode.VERIFY` in `__main__`. A check was an actuator the runner
could drive and an operator could not. `parse_actuation` closes that.

## §2.2 — the re-verify is an INDEPENDENT re-measurement

**[ARCHITECT RULING — revocable, implemented as written.]** After a correction,
`reverify()` re-executes the check **as a fresh subprocess in verify-only mode**
and reads its exit code. It does not call `run()` again in-process, and it does
not believe a return value from the correcting path.

This is the project's signature defect and it is worth being explicit about: an
instrument reporting on a state it just wrote. `correct()` returning `True` and
the check reporting PASS on that basis is a vacuous pass **by construction** —
the correcting code and the confirming code share every assumption, every cached
value, and every module-level import. A fresh process shares none of them: it
re-reads the file, re-opens the socket, re-asks systemd. **The re-verify must be
able to fail after a successful-looking correction, and that is demonstrated by
a control** in `scripts/tests/test_actuation.py`.

## §2.3 — the non-correctable class

**[ARCHITECT RULING — revocable, implemented as written; operator to ratify or
narrow.]** A check may declare `CORRECTABLE = False` with a
`NON_CORRECTABLE_REASON`, and it then refuses `--correct`/`--install` loudly
rather than silently ignoring them. Proposed members: anything on the order
path; anything touching credentials or `state/` (0600); anything that would
mutate broker session state, clientId assignments, or open positions.

The reasoning is §4's: auto-resend on the order path is prohibited for exactly
this reason — automatic remediation there converts one intended action into two.

## §2.4 — the safety interlock

**[ARCHITECT RULING — revocable, implemented as written.]** `--correct` and
`--install` refuse to run while a trading session may be active, and say why.
Fail-closed: Nix's whole risk posture is that uncertainty resolves toward flat,
and a remediation pass that mutates the box mid-session resolves uncertainty
toward change.

**The interlock has three states, not two, and the third is the honest one.**
ACTIVE refuses; INACTIVE permits; UNKNOWN refuses **and names what it could not
determine**. A two-state interlock would have to guess, and a guess in this
position is either a refusal that never lifts or a permission that was never
earned. Today the interlock reaches INACTIVE by a real measurement — no unit is
active inside `nix-trading.slice` — rather than by the absence of evidence.
"""

from __future__ import annotations

import argparse
import dataclasses
import subprocess  # nosec B404 - systemctl query and the re-verify re-exec
import sys
from collections.abc import Callable
from pathlib import Path

from nixverify.contract import (
    CheckResult,
    Context,
    Mode,
    exit_code_for,
    validate_result,
)
from nixverify.declarations import read_declaration
from nixverify.plane2 import Plane2

SYSTEMCTL = "/usr/bin/systemctl"

#: The cgroup slice the risk spec's core map pins trading processes into. A unit
#: active inside it is the observable that stands in for "a session is running".
TRADING_SLICE = "nix-trading.slice"


class ActuationRefused(Exception):
    """A mutation was asked for and refused. Always carries the reason."""


@dataclasses.dataclass(frozen=True)
class SessionState:
    """What the interlock could determine about trading activity."""

    verdict: str  # "active" | "inactive" | "unknown"
    detail: str

    @property
    def permits_mutation(self) -> bool:
        """Only a positively-measured INACTIVE permits a mutation."""
        return self.verdict == "inactive"


def session_state() -> SessionState:
    """Measure whether a trading session may be running.

    Enumerates units whose `Slice=` is the trading slice and reports whether any
    is active. The slice itself is always `active` (it is a cgroup, not a
    process) so the slice's own ActiveState is deliberately NOT the signal —
    reading it would produce a permanent, meaningless refusal.
    """
    if not Path(SYSTEMCTL).exists():
        return SessionState("unknown", f"{SYSTEMCTL} absent — cannot ask systemd")
    try:
        proc = subprocess.run(  # nosec B603 - fixed absolute path, no shell
            [
                SYSTEMCTL,
                "list-units",
                "--all",
                "--no-legend",
                "--plain",
                "--type=service",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return SessionState("unknown", f"systemctl failed: {exc!r}")
    if proc.returncode != 0:
        return SessionState("unknown", f"systemctl exit {proc.returncode}")

    running: list[str] = []
    for line in proc.stdout.splitlines():
        unit = line.split()[0] if line.split() else ""
        if not unit.endswith(".service"):
            continue
        try:
            show = subprocess.run(  # nosec B603 - fixed absolute path, no shell
                [SYSTEMCTL, "show", unit, "-p", "Slice", "-p", "ActiveState"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except OSError, subprocess.SubprocessError:
            continue
        fields = dict(
            line.split("=", 1) for line in show.stdout.splitlines() if "=" in line
        )
        if (
            fields.get("Slice") == TRADING_SLICE
            and fields.get("ActiveState") == "active"
        ):
            running.append(unit)
    if running:
        return SessionState(
            "active", f"units active in {TRADING_SLICE}: {', '.join(sorted(running))}"
        )
    return SessionState(
        "inactive", f"no unit active in {TRADING_SLICE} (measured, not assumed)"
    )


def guard_mutation(
    mode: Mode,
    correctable: bool,
    non_correctable_reason: str,
    check_name: str,
    force: bool = False,
) -> None:
    """Raise `ActuationRefused` if this mutation must not proceed.

    Order matters: the per-check refusal is checked BEFORE the session interlock.
    A non-correctable check must refuse for its own reason even on a quiet box —
    otherwise the operator learns "no session is running" and infers, wrongly,
    that correction would have been available.
    """
    if mode.rank <= Mode.VERIFY.rank:
        return
    if not correctable:
        raise ActuationRefused(
            f"{check_name} is declared NON-CORRECTABLE and refuses --{mode.value}: "
            f"{non_correctable_reason}"
        )
    state = session_state()
    if state.permits_mutation:
        return
    if force:
        raise ActuationRefused(
            f"{check_name}: --force is not an override for the session interlock; "
            f"session state is {state.verdict!r} ({state.detail})"
        )
    raise ActuationRefused(
        f"{check_name} refuses --{mode.value}: trading session state is "
        f"{state.verdict!r} — {state.detail}. Mutation is permitted only on a "
        "positively-measured inactive session (fail-closed, §2.4)."
    )


@dataclasses.dataclass(frozen=True)
class Reverification:
    """The outcome of an independent post-actuation re-measurement."""

    exit_code: int
    stdout: str
    stderr: str

    @property
    def confirmed(self) -> bool:
        """True only when the fresh process reported PASS."""
        return self.exit_code == 0


def reverify(
    check_path: Path, nix_home: Path, timeout: float = 300.0
) -> Reverification:
    """Re-execute the check in a FRESH PROCESS, verify-only, and read its verdict.

    §2.2. This deliberately does not import the check, does not reuse the current
    interpreter's state, and does not accept any value from the correcting code
    path. `sys.executable` re-runs the same interpreter the correction ran under
    so the re-verify is not accidentally measuring a different environment — the
    process is new, the environment is the same one that was corrected.
    """
    try:
        proc = subprocess.run(  # nosec B603 - argv built here, no shell
            [sys.executable, str(check_path), str(nix_home)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Reverification(2, "", f"re-verify timed out after {timeout}s")
    except (OSError, subprocess.SubprocessError) as exc:
        return Reverification(2, "", f"re-verify could not run: {exc!r}")
    return Reverification(proc.returncode, proc.stdout, proc.stderr)


def parse_actuation(argv: list[str], prog: str) -> argparse.Namespace:
    """The flag surface every check exposes on its own CLI.

    Default is measure-only. `--correct` and `--install` are explicit, per
    invocation, and there is no environment variable or config key that turns
    them on — a mutation on a trading platform should require someone to have
    typed it.
    """
    parser = argparse.ArgumentParser(prog=prog, add_help=True)
    parser.add_argument("home", nargs="?", default=None, help="NIX_HOME override")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--correct", action="store_true", help="repair what can be repaired"
    )
    group.add_argument(
        "--install", action="store_true", help="install what is missing, then repair"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="reserved; does NOT override the session interlock",
    )
    args = parser.parse_args(argv)
    if args.install:
        args.mode = Mode.INSTALL
    elif args.correct:
        args.mode = Mode.CORRECT
    else:
        args.mode = Mode.VERIFY
    return args


def standalone_main(
    check_file: Path,
    run_fn: Callable[[Mode, Context], CheckResult],
    name: str,
    argv: list[str] | None = None,
) -> int:
    """The full actuation surface for a check's own `__main__`.

    One implementation, shared by every retrofitted check, so the pilots cannot
    drift apart in how they refuse, re-verify, or report — the same reasoning
    that made both Gateway gates share one handshake instead of owning a copy
    (doctrine C.9).

    **Correctability is READ from the check's own declarations, never passed in.**
    An earlier draft took `correctable` and `non_correctable_reason` as
    arguments, which meant the same fact was stated twice per check — once as a
    module constant for `--optimize` to read, once in the `__main__` call — with
    nothing keeping them equal. That is `CLAUDE.md` directive 3 exactly, and the
    two spellings would have disagreed the first time one was edited. The
    declaration is the single source; this reads it with the same AST mechanism
    `--optimize` uses, so a check cannot refuse on its CLI while advertising
    itself as correctable to the planner.

    **The returned verdict after a mutation is the RE-VERIFY's, not the
    correction's.** That is the whole of §2.2 in one line: the process that did
    the writing does not get to report on the result.
    """
    declaration = read_declaration(check_file)
    args = parse_actuation(
        list(sys.argv[1:]) if argv is None else argv, prog=check_file.name
    )
    home = Path(args.home) if args.home else check_file.resolve().parent.parent
    plane2 = Plane2()

    try:
        guard_mutation(
            args.mode,
            declaration.correctable,
            declaration.non_correctable_reason,
            name,
            force=args.force,
        )
    except ActuationRefused as refusal:
        plane2.emit(
            "actuation_refused", check=name, verb=args.mode.value, reason=str(refusal)
        )
        print(f"REFUSED: {refusal}", file=sys.stderr)
        # Exit 1: a refused mutation is a real answer about a real subject, not
        # an inability to measure. The operator asked for something the contract
        # forbids and must be told so distinctly from "I could not look".
        return 1

    if args.mode.rank > Mode.VERIFY.rank:
        plane2.emit(
            "actuation_attempted", check=name, verb=args.mode.value, target=str(home)
        )

    outcome = validate_result(run_fn(args.mode, Context(nix_home=home, mode=args.mode)))
    print(f"{outcome.status.value}: {outcome.evidence or outcome.detail}")
    if outcome.detail and outcome.evidence:
        print(f"  detail: {outcome.detail}")

    if args.mode.rank <= Mode.VERIFY.rank:
        return exit_code_for(outcome.status)

    # -- §2.2: independent re-measurement in a fresh process. ---------------
    again = reverify(check_file, home)
    plane2.emit(
        "actuation_reverify",
        check=name,
        verb=args.mode.value,
        exit=again.exit_code,
        confirmed=again.confirmed,
    )
    print(f"  re-verify (fresh process, verify-only): exit {again.exit_code}")
    if not again.confirmed:
        print(
            "  RE-VERIFY DID NOT CONFIRM — the correction reported success and an "
            "independent re-measurement disagrees; trust the re-measurement",
            file=sys.stderr,
        )
        if again.stderr.strip():
            print(f"  re-verify stderr: {again.stderr.strip()[:400]}", file=sys.stderr)
    return again.exit_code
