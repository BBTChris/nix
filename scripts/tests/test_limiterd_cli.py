"""S4.4 — bringing `limiterd.py` under testmon's coverage fingerprint.

ARC 046 / S4 point 4: `check_limiter_daemon_dispatch.py` drives a real
`limiterd` as a SUBPROCESS (the DRIVEN arm has to be a real process with a
pid — that is the whole point of `limiterd.py` existing, per its own module
docstring). testmon's fingerprinting is coverage-based and only sees the
CURRENT process, so a subprocess-only subject leaves zero fingerprint edges
in the db no matter how many times it is driven. Every arc that touches
`scripts/limiterd.py` therefore reads it as `uncovered`, and the runtime
gate escalates to a full, non-selective pass — the ~44-minute per-arc tax
`msg.txt`'s S4.4 answer measured directly, four times, in this arc's own
commit attempts.

This file closes that gap the honest way: it imports `limiterd` IN-PROCESS
and exercises real, side-effect-free properties of it, so testmon's db gets
a genuine dependency edge on this module's actual lines — not a bare
`import limiterd` with no assertion, which would be exactly the
vacuous-coverage shape Core Directive 1 (prove real properties, not
proxies) refuses. It does NOT replace the out-of-process DRIVEN gate; a
parser accepting the right flags in-process is a different, narrower
property than a real loop consuming a real completion.
"""
# pylint: disable=invalid-name

from __future__ import annotations

import limiterd
import pytest  # pylint: disable=import-error


def test_the_parser_ACCEPTS_the_exact_flags_the_OUT_OF_PROCESS_GATE_passes():
    """`_parser()`'s own docstring calls itself a FIXED CONTRACT the
    out-of-process gate is written against — this proves the contract holds
    from the inside, so a renamed flag breaks fast, in-process."""
    runtime_dir = "/tmp/x"  # nosec B108 - an arg fixture value, never written to
    parser = limiterd._parser()  # pylint: disable=protected-access
    args = parser.parse_args(
        [
            "--runtime-dir",
            runtime_dir,
            "--heartbeat-interval",
            "0.05",
            "--tick-interval",
            "0.01",
            "--max-ticks",
            "5",
        ]
    )
    assert args.runtime_dir == runtime_dir
    assert args.heartbeat_interval == 0.05
    assert args.tick_interval == 0.01
    assert args.max_ticks == 5
    # Flags the gate does NOT pass keep their documented defaults.
    assert args.go_timeout is None
    assert args.plane1_wal is None


def test_the_parser_REFUSES_with_NO_runtime_dir():
    """`--runtime-dir` is `required=True` — there is no directory to default to."""
    parser = limiterd._parser()  # pylint: disable=protected-access
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_PENDING_ACK_TIMEOUT_reads_a_REAL_positive_interval_from_the_shipped_config():
    """§12A:830, no default (directive 4): `OrderOutcomes` refuses construction
    without a finite positive interval, so this must read a real one."""
    timeout = limiterd.pending_ack_timeout_from_config()
    assert isinstance(timeout, float)
    assert timeout > 0.0


def test_VERB_RESERVE_landed_this_ARC_and_is_in_the_SERVED_verbs():
    """§3's *"taken at approval"* — ARC 046: a daemon holding no reservations
    has nothing for a cancel completion to release."""
    assert limiterd.VERB_RESERVE == "reserve"
    assert limiterd.VERB_RESERVE in limiterd.VERBS
