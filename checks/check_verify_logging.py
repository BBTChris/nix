#!/usr/bin/env python3
"""Gate: `verify.py`'s Plane-2 stream actually reaches the journal.

Subject: `scripts/nixverify/plane2.py` and the journal it claims to write to.
Authority: `nics_risk_subsystem_spec_v1.3.md` §12.10 (two-plane model, locked);
`nix_check_contract.md` §4-§5; `VERIFY-AND-CHECKS.md` Part C.

## debug.md §7.12 — the standing question, asked at the point this gate is built

**What would have to be true for this gate to PASS while measuring nothing?**

Five answers, and each one is an arm below rather than a paragraph:

1. **It asks the emitter whether it emitted, and believes it.** `Plane2.emitted`
   is a counter incremented by the same object under test. A `Plane2` writing
   into a dead socket with a broken error path could report any number it liked.
   *Closed by arm 2:* the verdict comes from `journalctl` reading the journal
   back, not from the emitter's self-report. The counter is corroboration.
2. **It looks for the identifier and finds a stale entry from an earlier run.**
   The journal holds every previous `nix-verify` event, so "an event with this
   shape exists" is satisfied by history alone and would pass with the socket
   unplugged. *Closed by the NONCE:* every run mints a fresh random token, and
   only an entry carrying *this run's* nonce counts.
3. **It proves a round-trip and never checks the FORMAT.** A one-line event that
   arrived but does not carry §12.10's fields is not the contract. *Closed by
   arm 3*, which parses the recovered line and requires `ts=`, `proc=`, `event=`
   and the nonce field, with the timestamp actually parsing as UTC.
4. **It never demonstrates it can say no.** *Closed by arm 4*, the CONTROL: the
   same emission is re-driven with the transport pointed at a path that is not a
   socket, and the gate requires that configuration to be recoverable-as-FAIL.
   An arm 4 that passes means arms 1-3 cannot distinguish anything.
5. **It proves Plane 2 works and ignores what else got in.** *Closed by arms 5
   and 6:* no ANSI escape or spinner frame may appear in the Plane-2 stream
   (§1.3 — a journal full of spinner frames is a corrupted diagnostic plane),
   and no Plane-2 artifact may appear under `logs/`, which
   `directory_structure.md` pins to non-Plane artifacts.

**GUARDED:** an empty recovered-entry set is CANNOT_MEASURE, never PASS. If
`journalctl` is absent, unreadable by this user, or the syslog socket does not
exist, this gate cannot see its subject and says so with exit 2 — it does not
report that logging is fine because it failed to look.

## Why this gate does not simply run `verify.py`

It drives `Plane2` directly instead. Running the whole of `verify.py` to test its
logging would make this gate's runtime the suite's runtime and would couple a
logging verdict to twelve unrelated checks' behaviour. The subject is the
transport, and the transport is what is driven.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import secrets
import sys
import time
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import (
    CheckResult,
    Context,
    Mode,
    Status,
    exit_code_for,
    validate_result,
)
from nixverify.plane2 import (
    IDENTIFIER,
    JOURNAL_SOCKET,
    JOURNALCTL,
    Plane2,
    read_back,
)

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

#: ARC 024 orchestration declarations. See `nixverify/declarations.py` for the
#: contract these satisfy and why they are read without importing this module.
DEPENDS_ON: tuple[str, ...] = ()
#: `file-write:checks` added ARC 025: `_arm4_control` writes a scratch
#: `.plane2_control_<nonce>` file into `checks/` to build the dead transport its
#: control needs. OBSERVED by `check_observed_resource_claims`; the declaration
#: said `journal` alone and was false about the directory every other check is
#: enumerated from.
RESOURCES: tuple[str, ...] = ("journal", "file-write:checks")
TIME_BOUND = True
#: Derived from READBACK_TIMEOUT_S below, not from an observed duration.
EXPECTED_S = 6.0
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is the journal transport; 'correcting' it would mean writing to "
    "the journal, which is the thing under measurement"
)
SUBJECTS: tuple[str, ...] = ("scripts/nixverify/plane2.py",)

NAME = "check_verify_logging"
#: How long to wait for an emitted event to become visible to `journalctl`.
#: journald ingests asynchronously, so a readback immediately after emit is a
#: race. Bounded, and exhausting it is CANNOT_MEASURE, never PASS.
READBACK_TIMEOUT_S = 5.0
READBACK_POLL_S = 0.2


def _last_error(plane: Plane2) -> str:
    """The transport's own account of its last failure, without reaching inside.

    `Plane2` deliberately keeps its handler private; a gate poking at
    `plane._handler` would couple this file to that internal and would break the
    moment the transport changed shape.
    """
    return plane.last_error or "-"


def _journal_since(nonce: str, window: str = "-2 min") -> tuple[list[str], str]:
    """Lines carrying `nonce`, via the one reader that lives beside the emitter."""
    return read_back(identifier=IDENTIFIER, since=window, grep=nonce)


def _await_readback(nonce: str) -> tuple[list[str], str]:
    """Poll the journal until the nonce lands or the budget is spent."""
    deadline = time.perf_counter() + READBACK_TIMEOUT_S
    while time.perf_counter() < deadline:
        lines, error = _journal_since(nonce)
        if lines:
            return lines, ""
        if error:
            return [], error
        time.sleep(READBACK_POLL_S)
    return [], ""


def _parse_fields(line: str) -> dict[str, str]:
    """Split a §12.10 one-line event into its key=value fields."""
    fields: dict[str, str] = {}
    for token in line.split(" "):
        if "=" in token:
            key, _, value = token.partition("=")
            fields.setdefault(key, value)
    return fields


def _drive_live(nonce: str) -> tuple[Plane2, str]:
    """Emit one nonce-bearing event through the real transport."""
    plane = Plane2()
    line = plane.emit("gate_probe", nonce=nonce, gate="check_verify_logging")
    return plane, line


def _drive_control(nonce: str, tmp_socket: Path) -> Plane2:
    """CONTROL: the same emission with the transport pointed somewhere dead.

    `tmp_socket` is a regular file, not a socket. `SysLogHandler` will either
    refuse to open it or accept it and fail on every send; both outcomes must
    leave the gate able to tell that nothing was logged.
    """
    plane = Plane2(socket_path=str(tmp_socket), identifier=IDENTIFIER)
    plane.emit("gate_probe_control", nonce=nonce, gate="check_verify_logging")
    return plane


def _scan_logs_dir(nix_home: Path) -> list[str]:
    """`logs/` must hold no Plane-2 artifact (directory_structure.md)."""
    logs = nix_home / "logs"
    if not logs.is_dir():
        return []
    offenders = []
    for path in logs.rglob("*"):
        if not path.is_file():
            continue
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:20000]
        except OSError:
            continue
        if "proc=verify.py event=" in head or IDENTIFIER in head:
            offenders.append(str(path.relative_to(nix_home)))
    return offenders


def _ansi_offenders(lines: list[str]) -> list[str]:
    """Presentation bytes that must never appear in Plane 2 (§1.3)."""
    spinner_frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    offenders = []
    for line in lines:
        if "\x1b" in line:
            offenders.append(f"ANSI escape in {line[:80]!r}")
        elif any(frame in line for frame in spinner_frames):
            offenders.append(f"spinner frame in {line[:80]!r}")
    return offenders


@dataclasses.dataclass
class _Findings:
    """Accumulator the arms write into. Keeps each arm a small, testable unit."""

    defects: list[tuple[str, str]] = dataclasses.field(default_factory=list)
    evidence: list[str] = dataclasses.field(default_factory=list)


def _precondition() -> CheckResult | None:
    """CANNOT_MEASURE when the subject is absent. Never PASS by failing to look."""
    if not Path(JOURNAL_SOCKET).exists():
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=(
                f"no syslog socket at {JOURNAL_SOCKET} — this node has no journal "
                "ingress, so Plane 2 has no subject to measure here (§12.10)"
            ),
        )
    if not Path(JOURNALCTL).exists():
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"{JOURNALCTL} not present — cannot read the journal back",
        )
    return None


def _arm1_transport(plane: Plane2, found: _Findings) -> None:
    """The transport opens and reports itself as having delivered."""
    if not plane.available:
        found.defects.append(
            ("nixverify/plane2.py:Plane2", f"transport unavailable: {plane.transport}")
        )
    elif plane.emitted == 0:
        found.defects.append(
            (
                "nixverify/plane2.py:_CountingSysLogHandler",
                (
                    f"handler attached but delivered nothing "
                    f"(failed={plane.failed}, last_error={_last_error(plane)})"
                ),
            )
        )
    else:
        found.evidence.append(f"transport={plane.transport} delivered={plane.emitted}")


def _arm2_roundtrip(nonce: str, recovered: list[str], found: _Findings) -> None:
    """The journal holds THIS run's event, identified by nonce."""
    if not recovered:
        found.defects.append(
            (
                f"journal(-t {IDENTIFIER})",
                (
                    f"emitted event carrying nonce {nonce} did not land within "
                    f"{READBACK_TIMEOUT_S}s — the handler is attached to a "
                    "stream nothing can read back"
                ),
            )
        )
    else:
        found.evidence.append(f"round-trip: {len(recovered)} entry/entries for {nonce}")


def _arm3_fields(recovered: list[str], found: _Findings) -> None:
    """The recovered line carries §12.10's fields and a parseable UTC stamp."""
    if not recovered:
        return
    fields = _parse_fields(recovered[0])
    for required in ("ts", "proc", "event", "nonce"):
        if required not in fields:
            found.defects.append(
                (
                    f"journal entry {recovered[0][:60]!r}",
                    f"§12.10 field {required!r} missing from the recovered event",
                )
            )
    stamp = fields.get("ts", "")
    try:
        # The format's trailing `Z` is a literal, not `%z`, so strptime yields a
        # NAIVE datetime that merely looks UTC. Attaching UTC makes the parsed
        # value mean what the wire format asserts — and the parse itself is
        # still what falsifies a malformed stamp.
        parsed = _dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=_dt.UTC
        )
    except ValueError:
        found.defects.append(
            (f"journal ts={stamp!r}", "not a §12.10 UTC timestamp this gate can parse")
        )
    else:
        found.evidence.append(f"ts parsed UTC {parsed.isoformat()}")
    if fields.get("proc") != "verify.py":
        found.defects.append(
            (f"journal proc={fields.get('proc')!r}", "expected proc=verify.py")
        )


def _arm4_control(nix_home: Path, found: _Findings) -> None:
    """CONTROL — a dead transport must be recoverable as a failure.

    This is the arm that makes arms 1-3 falsifiable. If a `Plane2` pointed at a
    non-socket still reported itself available and delivering, `available` and
    `emitted` would carry no information and every PASS above would be vacuous.
    """
    control_nonce = f"ARC024CTL-{secrets.token_hex(8)}"
    dead = nix_home / "checks" / f".plane2_control_{control_nonce}"
    try:
        dead.write_text("not a socket\n", encoding="utf-8")
        control = _drive_control(control_nonce, dead)
        delivered, available = control.emitted, control.available
        control.close()
        if available and delivered > 0:
            found.defects.append(
                (
                    "nixverify/plane2.py:Plane2 CONTROL",
                    (
                        "a transport pointed at a regular file reported itself "
                        "available AND delivering — `available`/`emitted` cannot "
                        "distinguish a live journal from a dead one, so this "
                        "gate's PASS would be vacuous"
                    ),
                )
            )
        else:
            found.evidence.append(
                f"control(dead socket): available={available} delivered={delivered}"
            )
        leaked, _ = _journal_since(control_nonce)
        if leaked:
            found.defects.append(
                (
                    f"journal(-t {IDENTIFIER})",
                    (
                        f"CONTROL event {control_nonce} reached the journal "
                        "through a transport pointed at a regular file"
                    ),
                )
            )
    finally:
        dead.unlink(missing_ok=True)


def _arm5_presentation(found: _Findings) -> None:
    """§1.3 — no presentation byte may appear in Plane 2."""
    window, window_err = _journal_since("proc=verify.py", window="-30 min")
    if window_err:
        return
    offenders = _ansi_offenders(window)
    for offender in offenders[:5]:
        found.defects.append((f"journal(-t {IDENTIFIER})", offender))
    if not offenders:
        found.evidence.append(
            f"presentation-clean: {len(window)} Plane-2 entries, 0 ANSI, "
            "0 spinner frames"
        )


def _arm6_logs_dir(nix_home: Path, found: _Findings) -> None:
    """Plane 2 never lands in `logs/` (directory_structure.md)."""
    strays = _scan_logs_dir(nix_home)
    for stray in strays:
        found.defects.append(
            (
                stray,
                (
                    "Plane-2 artifact found under logs/, which is pinned to "
                    "non-Plane artifacts"
                ),
            )
        )
    if not strays:
        found.evidence.append("logs/ holds no Plane-2 artifact")


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Prove the Plane-2 stream round-trips to the journal and stays clean."""
    blocked = _precondition()
    if blocked is not None:
        return blocked

    found = _Findings()
    nonce = f"ARC024-{secrets.token_hex(8)}"
    plane, emitted_line = _drive_live(nonce)
    _arm1_transport(plane, found)

    recovered, read_error = _await_readback(nonce)
    plane.close()
    if read_error:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"journal unreadable: {read_error}",
            evidence="; ".join(found.evidence),
        )
    _arm2_roundtrip(nonce, recovered, found)
    _arm3_fields(recovered, found)
    _arm4_control(Path(ctx.nix_home), found)
    _arm5_presentation(found)
    _arm6_logs_dir(Path(ctx.nix_home), found)

    found.evidence.append(f"emitted line: {emitted_line[:120]}")
    joined = "; ".join(found.evidence)
    if found.defects:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site="; ".join(site for site, _ in found.defects),
            evidence=joined,
            detail="; ".join(f"{site}: {why}" for site, why in found.defects),
        )
    return CheckResult(name=NAME, status=Status.PASS, evidence=joined)


if __name__ == "__main__":
    HOME = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().parent.parent
    )
    # validate_result, not the raw return: standalone invocation must be held to
    # the same §5 rules the engine applies, including AMENDMENT 1's GUARDED
    # requirements. Without it a standalone run could exit on a verdict the
    # engine would have downgraded — the check reporting better news about
    # itself than the runner would. Enforced by
    # scripts/tests/test_check_standalone_nonvacuity.py, which caught this file
    # omitting it.
    OUTCOME = validate_result(
        run(Mode.VERIFY, Context(nix_home=HOME, mode=Mode.VERIFY))
    )
    print(f"{OUTCOME.status.value}: {OUTCOME.detail or OUTCOME.evidence}")
    sys.exit(exit_code_for(OUTCOME.status))
