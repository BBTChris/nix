#!/usr/bin/env python3
# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK — `PRIVILEGE`/`INTERACTIVE`/
# `DISRUPTIVE`, `DEPENDS_ON`/`RESOURCES`/`TIME_BOUND`/`CORRECTABLE`/`SUBJECTS`,
# and the `standalone_main` `__main__` — against every other check's. That
# similarity is the CONTRACT (`nix_check_contract.md` §4.2, §4.4): every check
# must declare the same symbols and must be independently runnable, so the
# blocks are identical BY REQUIREMENT and factoring them into a shared helper
# would break the contract to satisfy a similarity counter. Same pragma, same
# reason, as `scripts/nixverify/actuation.py` line 1.
"""Gate: §12.7's state-table transport carries REAL TRAFFIC, snapshot included.

Subject: `scripts/nixbus/statebus.py` and a live `ipc://` ZeroMQ endpoint.
Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §12.7 (state-table transport,
**LOCKED v1.3** — ZeroMQ PUB/SUB + snapshot-on-subscribe, mirror model), §12.9;
`docs/nix_check_contract.md` §4-§5; `docs/VERIFY-AND-CHECKS.md` Part C.

## debug.md §7.12 — the standing question, asked at the point this gate is built

**What would have to be true for this gate to PASS while measuring nothing?**

The arc brief names this gate's failure mode by name: *"a transport gate that
passes because nothing was ever published. A subscriber that receives zero
messages and reports 'no errors' measures nothing."* Six answers, six arms:

1. **Nobody published, nobody received, nothing raised.** The purest form of the
   named defect. *Closed by the NON-VACUITY PRECONDITION:* the verdict reads
   `StateSubscriber.bytes_received`, and **zero bytes is CANNOT_MEASURE, never
   PASS**. The transport is not asked whether it is well; it is asked what it
   carried.
2. **Something arrived and the content was never checked.** A message of the
   right shape carrying the wrong table is a transport that works and a mirror
   that lies. *Closed by the NONCE:* every arm mints a fresh token, puts it
   inside the published table, and requires it back out of the *payload* — not
   out of the topic, not out of a header.
3. **The snapshot was actually an organic delta.** This is the subtle one. A
   subscriber that connects and then receives the next ordinary publication
   looks exactly like snapshot-on-subscribe from the receiving end. *Closed by
   arm 1's shape and by arm 3, the CONTROL:* the table is published **before the
   subscriber exists** and is never published again, so the only thing that can
   deliver it is the subscribe-triggered snapshot; and the control repeats that
   setup with `service()` never called, requiring that the subscriber then
   receives **nothing**. A control that receives the table proves the arrival in
   arm 1 was not caused by the mechanism under test.
4. **A mirror assembled from fragments passes as complete.** §12.7: *"mirror
   incomplete => treated as stale => fast-drop/deny until snapshot lands"*.
   *Closed by arm 4*, which requires a delta-only mirror to report `stale` and
   to name the missing table.
5. **Freshness stamps are documented and absent.** §12.7: *"freshness stamps
   ride each update"*. *Closed by arm 5*, which reads `_stamp` off a received
   message and requires it to be a plausible clock, not a zero.
6. **It never touches `ipc://` at all** — an in-process `inproc://` round-trip
   would exercise none of the socket path the spec locks. *Closed by arm 6*,
   which requires the endpoint to be `ipc://` and requires the socket **file**
   to exist on disk while the publisher is bound. That is the kernel's record of
   the endpoint, not the library's.

## Scope: this gate does NOT prove cross-process delivery

Publisher and subscriber are two sockets in one process. `ipc://` is a real
AF_UNIX socket either way — the bytes traverse the kernel — but a second process
is not spawned, so process-boundary concerns (fd inheritance, permissions,
SELinux) are unproven here and `docs/CHECK-DEBT.md` carries the row rather than
this docstring carrying a reassurance.
"""

from __future__ import annotations

import secrets
import sys
import tempfile
from pathlib import Path
from typing import Any

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import (
    CheckResult,
    Context,
    Mode,
    Status,
    result_from_defects,
)

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: `pyzmq` is a `checks/pinned_deps.json` pin, so the venv is what makes this
#: gate's subject importable at all.
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: THREE claims, and the second and third are the ones ARC 025's seven false
#: declarations warn about:
#: * `file-write:/tmp` — `tempfile.mkdtemp` plus `_remove_tree`'s absolute-path
#:   unlinks. OBSERVABLE, and OBSERVED: the audit hook records `os.mkdir` /
#:   `os.remove` / `os.rmdir` as `file-write:` claims, and this declaration was
#:   caught FALSE once already — see `_remove_tree` for what the observer said
#:   and why the repair was to change the deletion rather than the declaration.
#: * `zmq-ipc` — the AF_UNIX sockets libzmq binds and connects. **NOT observable
#:   by `check_observed_resource_claims`**: `socket.bind`/`socket.connect` audit
#:   events fire from CPython's `socket` module, and libzmq calls `bind(2)`
#:   directly from C. So the observer will report this gate as touching no
#:   socket, and that report will be WRONG in the permissive direction. Declared
#:   anyway, because the claim is real and the plan is what needs to know.
#: * `subprocess:python3` is deliberately ABSENT: this gate spawns nothing.
RESOURCES: tuple[str, ...] = ("file-write:/tmp", "zmq-ipc")
TIME_BOUND = True
#: Four socket round-trips, each with a bounded service/drain budget.
EXPECTED_S = 8.0
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is a transport's live behaviour; there is no on-disk setting to "
    "correct, and a gate that 'repaired' a bus by publishing into it would be "
    "manufacturing the traffic it exists to measure"
)
SUBJECTS: tuple[str, ...] = ("scripts/nixbus/statebus.py",)

NAME = "check_state_bus"

TOPIC = "tbl.gate"
#: Budgets. Generous enough that ipc setup is not a race, bounded enough that
#: exhausting one is a finding rather than a hang.
SERVICE_MS = 1000
DRAIN_MS = 500


def _import_statebus() -> tuple[Any, str]:
    """Import the subject lazily. `verify.py` may be running under a python
    without pyzmq (`nix-verify.service` uses `/usr/bin/python3`), and a
    module-level import would make that a LOAD ERROR for the whole check rather
    than an honest CANNOT_MEASURE."""
    try:
        from nixbus import statebus  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        return None, f"cannot import nixbus.statebus under {sys.executable}: {exc!r}"
    return statebus, ""


def _endpoint(bus: Any, root: Path, name: str) -> str:
    return str(bus.endpoint_for(name, root=root))


def _late_subscriber_snapshot(
    bus: Any, root: Path, nonce: str, *, service: bool
) -> dict[str, Any]:
    """Publish, THEN subscribe. Returns what the late subscriber actually got.

    `service=False` is the CONTROL: identical in every other respect, so the only
    difference between the two runs is whether the snapshot-on-subscribe
    mechanism was allowed to run.
    """
    endpoint = _endpoint(bus, root, "svc" if service else "ctl")
    publisher = bus.StatePublisher(endpoint)
    subscriber = None
    try:
        publisher.publish(TOPIC, {"nonce": nonce, "tradable": True})
        socket_file = Path(endpoint.removeprefix("ipc://"))
        subscriber = bus.StateSubscriber(endpoint, [TOPIC])
        served = publisher.service(SERVICE_MS) if service else 0
        messages = subscriber.drain(DRAIN_MS)
        return {
            "endpoint": endpoint,
            "socket_file_exists": socket_file.exists(),
            "served": served,
            "messages": messages,
            "received": subscriber.received,
            "bytes": subscriber.bytes_received,
            "mirror_complete": subscriber.mirror.complete,
            "mirror_missing": subscriber.mirror.missing,
        }
    finally:
        if subscriber is not None:
            subscriber.close()
        publisher.close()


def _delta_only_mirror(bus: Any, root: Path, nonce: str) -> dict[str, Any]:
    """Subscribe FIRST, then publish once. The mirror sees a delta and no snapshot."""
    endpoint = _endpoint(bus, root, "dlt")
    publisher = bus.StatePublisher(endpoint)
    subscriber = None
    try:
        subscriber = bus.StateSubscriber(endpoint, [TOPIC])
        # Let the subscription reach the publisher, and swallow the snapshot it
        # triggers, so the mirror under test has genuinely seen only a delta.
        publisher.service(SERVICE_MS)
        subscriber.drain(200)
        publisher.publish(TOPIC, {"nonce": nonce, "tradable": False})
        messages = subscriber.drain(DRAIN_MS)
        deltas = [m for m in messages if not m.snapshot]
        return {
            "deltas": deltas,
            "bytes": subscriber.bytes_received,
            "mirror": bus.Mirror([TOPIC]),
            "delta_mirror_stale": _delta_mirror_stale(bus, deltas),
        }
    finally:
        if subscriber is not None:
            subscriber.close()
        publisher.close()


def _delta_mirror_stale(bus: Any, deltas: list[Any]) -> bool | None:
    """A fresh mirror fed ONLY these deltas — is it still stale? `None` = no data."""
    if not deltas:
        return None
    mirror = bus.Mirror([TOPIC])
    for message in deltas:
        mirror.apply(message)
    return bool(mirror.stale)


def _arm_snapshot(
    live: dict[str, Any], nonce: str, defects: list[tuple[str, str]], ev: list[str]
) -> None:
    """A LATE subscriber receives the CURRENT table, content and all."""
    site = "scripts/nixbus/statebus.py:StatePublisher.service"
    snapshots = [m for m in live["messages"] if m.snapshot]
    if not snapshots:
        defects.append(
            (
                site,
                (
                    f"a subscriber that joined AFTER the only publication received "
                    f"{live['received']} message(s) and no snapshot — §12.7's "
                    "snapshot-on-subscribe is mandatory, not polish"
                ),
            )
        )
        return
    payload = snapshots[0].payload
    if payload.get("nonce") != nonce:
        defects.append(
            (
                site,
                (
                    f"snapshot arrived carrying nonce {payload.get('nonce')!r}, "
                    f"expected {nonce!r} — the transport delivered something that "
                    "is not the table under test"
                ),
            )
        )
        return
    ev.append(
        f"late subscriber got snapshot topic={snapshots[0].topic} "
        f"nonce={nonce} tradable={payload.get('tradable')!r} "
        f"served={live['served']} bytes={live['bytes']}"
    )


def _arm_control(
    control: dict[str, Any], defects: list[tuple[str, str]], ev: list[str]
) -> None:
    """CONTROL — with the mechanism disabled, the late subscriber gets nothing."""
    site = "scripts/nixbus/statebus.py CONTROL (service() never called)"
    # ARC 027 (B3), D3.21's class. The test was on `received` (a MESSAGE count)
    # and the narration claimed "0 bytes". They can diverge: statebus increments
    # `bytes_received` BEFORE `_decode` and `received` only after it, so a frame
    # taken off the socket that fails to decode leaves bytes > 0 and messages 0 —
    # the control would then report "received 0 bytes" over a socket that had in
    # fact delivered some. Both counters are now tested, and both are narrated
    # from the dict rather than asserted.
    if control["received"] or control["bytes"]:
        defects.append(
            (
                site,
                (
                    f"a late subscriber received {control['received']} message(s) "
                    f"({control['bytes']} bytes) with snapshot-on-subscribe never "
                    "run — so arrival in the measured arm is not evidence that the "
                    "mechanism works, and that arm's PASS would be vacuous"
                ),
            )
        )
        return
    ev.append(
        f"CONTROL: service() withheld -> late subscriber received "
        f"{control['received']} message(s) / {control['bytes']} bytes"
    )


def _arm_ipc(
    live: dict[str, Any], defects: list[tuple[str, str]], ev: list[str]
) -> None:
    """The endpoint is `ipc://` and the kernel has the socket file to prove it."""
    endpoint = str(live["endpoint"])
    if not endpoint.startswith("ipc://"):
        defects.append((endpoint, "endpoint is not ipc:// — §12.7's transport"))
        return
    if not live["socket_file_exists"]:
        defects.append(
            (
                endpoint,
                (
                    "no socket file on disk while the publisher was bound — the "
                    "endpoint was never materialised by the kernel"
                ),
            )
        )
        return
    ev.append(f"ipc endpoint materialised: {endpoint}")


def _arm_mirror(
    delta: dict[str, Any], nonce: str, defects: list[tuple[str, str]], ev: list[str]
) -> None:
    """§12.7: a mirror with no snapshot is STALE, and says which table is missing."""
    site = "scripts/nixbus/statebus.py:Mirror.complete"
    deltas = delta["deltas"]
    if not deltas:
        defects.append((site, "no delta was delivered, so the mirror rule is untested"))
        return
    if deltas[0].payload.get("nonce") != nonce:
        defects.append((site, f"delta carried {deltas[0].payload.get('nonce')!r}"))
        return
    if delta["delta_mirror_stale"] is not True:
        defects.append(
            (
                site,
                (
                    "a mirror fed only deltas reports itself COMPLETE — §12.7 "
                    "requires an incomplete mirror to be treated as stale until a "
                    "snapshot lands"
                ),
            )
        )
        return
    ev.append(f"delta delivered (nonce={nonce}); delta-only mirror reports stale")


def _arm_stamp(
    live: dict[str, Any], defects: list[tuple[str, str]], ev: list[str]
) -> None:
    """§12.7: *freshness stamps ride each update*."""
    message = live["messages"][0]
    if message.stamp <= 0:
        defects.append(
            (
                "scripts/nixbus/statebus.py:StatePublisher._send",
                (
                    f"update carries _stamp={message.stamp!r} — §12.7 requires a "
                    "freshness stamp on every update"
                ),
            )
        )
        return
    ev.append(
        f"freshness stamp rides updates: age={message.age_s:.3f}s seq={message.seq}"
    )


def _remove_tree(root: Path) -> None:
    """Delete the scratch bus directory by ABSOLUTE path, never `shutil.rmtree`.

    MEASURED, ARC 026: `check_observed_resource_claims` FAILED this gate with
    *"OBSERVED using file-write:svc.ipc … and its declaration
    RESOURCES=['file-write:/tmp', 'zmq-ipc'] does not account for it"*, three
    times over. The claim really was made and the declaration really did not
    cover it — but the cause was not the socket. On POSIX `shutil.rmtree`
    recurses on **directory file descriptors** and calls `os.unlink(name,
    dir_fd=…)` with a BARE RELATIVE name, so the audit hook records
    `file-write:svc.ipc` with no directory attached, and no path-rooted
    declaration can ever account for it.

    Two repairs were available and only one is honest. Declaring
    `file-write:svc.ipc` would have matched — `observe.covers` compares unknown
    tokens by exact string equality first — and would have been a declaration of
    a **stdlib implementation detail**, true only until CPython changed how
    `rmtree` walks. Unlinking by absolute path instead makes the OBSERVED claim
    say what is actually true: a file under `/tmp`. The declaration was right;
    the instrument was right; the *deletion* was making an unattributable claim.
    """
    if not root.is_dir():
        return
    for child in sorted(root.iterdir()):
        try:
            child.unlink()
        except OSError:
            continue
    try:
        root.rmdir()
    except OSError:
        pass


def _cannot(detail: str, evidence: list[str]) -> CheckResult:
    """CANNOT_MEASURE with whatever was learned before the wall."""
    return CheckResult(
        name=NAME,
        status=Status.CANNOT_MEASURE,
        detail=detail,
        evidence="; ".join(evidence),
    )


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Drive real traffic over a real `ipc://` socket and check what arrived."""
    bus, import_error = _import_statebus()
    if bus is None:
        return _cannot(import_error, [])

    root = Path(tempfile.mkdtemp(prefix="nixbus-gate-"))
    nonce = f"ARC026-{secrets.token_hex(8)}"
    evidence: list[str] = []
    defects: list[tuple[str, str]] = []
    try:
        live = _late_subscriber_snapshot(bus, root, nonce, service=True)
        control = _late_subscriber_snapshot(bus, root, f"CTL-{nonce}", service=False)
        delta = _delta_only_mirror(bus, root, f"DLT-{nonce}")
    except Exception as exc:  # noqa: BLE001 pylint: disable=broad-exception-caught
        return _cannot(f"the bus could not be driven: {exc!r}", evidence)
    finally:
        _remove_tree(root)

    # THE NON-VACUITY PRECONDITION. Not an arm: nothing below is meaningful
    # without it, so it is checked before any arm gets to contribute a verdict.
    carried = int(live["bytes"]) + int(delta["bytes"])
    if carried == 0:
        return _cannot(
            "the transport carried ZERO bytes across every arm — a subscriber "
            "that received nothing cannot report that the bus is well (§12.7). "
            "This is CANNOT_MEASURE and is deliberately never PASS",
            evidence,
        )
    evidence.append(f"transport carried {carried} bytes of real traffic")

    _arm_ipc(live, defects, evidence)
    _arm_snapshot(live, nonce, defects, evidence)
    _arm_control(control, defects, evidence)
    _arm_mirror(delta, f"DLT-{nonce}", defects, evidence)
    if live["messages"]:
        _arm_stamp(live, defects, evidence)
    return result_from_defects(NAME, defects, "; ".join(evidence))


if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
