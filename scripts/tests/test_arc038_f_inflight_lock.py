"""ARC 038 / sub-agent F — §14's one-in-flight lock, and the wedge it can reach.

The can-fail suite for the FROZEN spec invariant
*"One in-flight action per strategy — and it can never wedge (GO-timeout)"*
(`docs/nics_risk_subsystem_spec_v1.3.md` §14:965, C6 at §15:994, the state model
at §4:210-212). Every `§` cites v1.3 unless another document is named on the
same line.

## WHY THIS SUITE EXISTS — a MEASURED hole, not an anticipated one

`gate.InFlightLockRule` is the rule that enforces the invariant. ARC 038 (F)
measured its reference count in the whole tree at **two**: its own `class`
statement and the one line of `default_manifest` that constructs it. Nothing —
no test, no gate — ever constructed it directly or drove it to a DENY, because
every instrument in the tree hands `default_manifest` an always-clear
`in_flight` port. Deleting the rule's entire blocking branch
(`if locked: return _blocked(...)`) left `check_limiter_gate`,
`check_orphan_recovery`, `check_allocator_sizing` and 116 collected tests
GREEN. The rule that makes §14's lock real had no can-fail control anywhere.

## §7.12 — THE STANDING QUESTION, ANSWERED CONDITION BY CONDITION

*What would have to be true for this suite to pass while the invariant is
FALSE in reality?*

1. **The lock could be driven only through a DOUBLE.** Then the suite would
   measure a stub agreeing with itself. So `_locked_registry` is the SHIPPED
   `recovery.StrategyRegistry` satisfying the SHIPPED `gate.InFlightPort`, and
   the pass runs through the SHIPPED `default_manifest` and `GatePass`.
2. **The assertion set could be satisfiable by a rule that never blocks.**
   Then the control would be green over the very deletion that motivated it.
   So `test_the_DENY_assertions_REJECT_a_lock_rule_that_never_blocks` runs the
   UNPROTECTED half first — the same manifest with the lock rule replaced by
   one that always clears — and requires the bad outcome (APPROVE) to appear.
3. **The lock could be enforced only by the rule and not by the LOCK.** It was:
   `take_in_flight` accepted a second, third and eighth take for one strategy,
   silently overwriting the `client_order_id` the lock names. That is finding
   FF2 and its guard is driven here in both halves.
4. **The wedge could be asserted as a property of a stub timer.** There is no
   timer: ARC 038 (F) censused every shipped site that clears an `in_flight`
   field and found exactly ONE — `force_deregister`, which destroys the
   registration — and every shipped occurrence of the `go_timeout` token is an
   event-type NAME, a docstring, or the boot validator in
   `scripts/risk_config.py`. `test_the_GO_TIMEOUT_CENSUS...` is that census,
   frozen as a RATCHET: it fails the day a release verb or a firing site
   appears, which is the day CHECK-DEBT D3.398 is discharged and this baseline
   must be updated rather than rediscovered.
5. **The wedge could be an artefact of an in-process fake death.** So
   `test_a_REAL_SIGKILL...` kills a REAL child process holding the GO with a
   real `SIGKILL`, reaps the `-9`, proves `/proc/<pid>` is gone, and only then
   re-reads the lock. Its can-fail half releases the lock through a simulated
   GO-timeout and requires the same assertions to flip.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=too-few-public-methods,missing-function-docstring
# Every helper is a PORT DOUBLE with the port's own single verb; a second
# method would make the double a worse stand-in for the thing it doubles.

from __future__ import annotations

import ast
import dataclasses
import os
import signal
import subprocess  # nosec B404 - argv built here, no shell, own child only
import sys
import threading
import time
from pathlib import Path

import pytest  # pylint: disable=import-error
from nixbus.statebus import StateSubscriber, endpoint_for
from nixrisk.gate import GatePass, InFlightLockRule, default_manifest
from nixrisk.recovery import RecoveryError, StrategyRegistry
from nixrisk.seam import (
    Decision,
    FinancialPicture,
    Phase,
    ProposedOrder,
    RuleVerdict,
    Side,
    StopMode,
)
from nixverify.gitenv import scrubbed_env

REPO = Path(__file__).resolve().parents[2]
FRACTION = 0.70
SAFETY_PAD = 0.10
TOLERANCE = 1e-6
STRATEGY = "s1"
HELD_CID = "c-held"

#: The ONLY shipped sites that clear an `in_flight` field, as MEASURED by ARC
#: 038 (F) over `git ls-files scripts` minus `scripts/tests/`. A RATCHET, not a
#: description: growth here means a release path was added, which is the
#: discharge of CHECK-DEBT D3.398 and must be read, not absorbed.
SHIPPED_INFLIGHT_RELEASE_SITES: tuple[str, ...] = (
    "scripts/nixrisk/recovery.py:StrategyRegistry.force_deregister",
)
#: Shipped modules that so much as MENTION the `go_timeout` token, and what
#: each one does with it. Not one of them measures elapsed time against
#: `limiter.go_timeout_s`; §14's *"it can never wedge (GO-timeout)"* has no
#: implementation. CHECK-DEBT D3.398.
SHIPPED_GO_TIMEOUT_MENTIONS: tuple[str, ...] = (
    "scripts/nixrisk/plane1_seed.py",
    "scripts/nixrisk/plane1_sink.py",
    "scripts/nixrisk/projection.py",
    "scripts/nixrisk/seam.py",
    "scripts/nixscore/ema.py",
    "scripts/risk_config.py",
)


class _Clear:
    """Every §11.1-shaped port in one object, all clear. In-memory BY SPEC (§11)."""

    def read(self, symbol: str | None = None) -> tuple[bool, str]:
        del symbol
        return False, ""

    def is_set(self) -> tuple[bool, str]:
        return False, ""

    def in_flight(self, strategy_id: str) -> tuple[bool, str]:
        del strategy_id
        return False, ""

    def mark(self) -> tuple[float, bool]:
        return 10_000_000.0, True


class _NeverBlocks:
    """A lock rule that always clears — the UNPROTECTED half of the control.

    Satisfies `RulePort` and stands exactly where `InFlightLockRule` stands, so
    the assertion set is exercised against the deletion it exists to catch.
    """

    name = "in_flight_lock"
    phase = Phase.SIZE_INDEPENDENT

    def evaluate(self, order: ProposedOrder, picture: FinancialPicture) -> RuleVerdict:
        del order, picture
        return RuleVerdict(rule=self.name, decision=Decision.APPROVE, reason="")


def _order(cid: str) -> ProposedOrder:
    return ProposedOrder(
        client_order_id=cid,
        strategy_id=STRATEGY,
        symbol="ES",
        side=Side.LONG,
        qty=1,
        margin_per_contract=1000.0,
        stop_ticks=40,
        stop_mode=StopMode.FIXED,
        signal_ts=1.0,
    )


def _picture() -> FinancialPicture:
    return FinancialPicture(
        version=1,
        published_ts=1.0,
        balance=1_000_000.0,
        positions=(),
        margin_per_contract={"ES": 1000.0},
        sum_open_margin=0.0,
        sum_reservations=0.0,
        committed=0.0,
        deployable=500_000.0,
    )


def _locked_registry() -> StrategyRegistry:
    """The SHIPPED registry, holding the SHIPPED lock. Not a double."""
    registry = StrategyRegistry()
    registry.register(STRATEGY, slot=0, now=0.0)
    registry.take_in_flight(STRATEGY, HELD_CID)
    assert registry.in_flight(STRATEGY)[0] is True
    return registry


def _manifest(in_flight_port) -> list:
    return list(
        default_manifest(
            blackout=_Clear(),
            tradability=_Clear(),
            staleness=_Clear(),
            clock_skew=_Clear(),
            in_flight=in_flight_port,
            net_liq=_Clear(),
            deployable_fraction=FRACTION,
            survival_safety_pad=SAFETY_PAD,
            coherence_tolerance=TOLERANCE,
        )
    )


# ---------------------------------------------------------------------------
# 1 — THE MISSING CONTROL: the lock rule's DENY branch, driven
# ---------------------------------------------------------------------------


def test_the_INFLIGHT_LOCK_RULE_DENIES_through_the_shipped_manifest() -> None:
    """§4:210-212 — *'While an order is pending, the strategy's next signal is
    rejected-with-reason until resolution.'* The REAL registry behind the REAL
    manifest, and the denial read for its rule name AND its reason (§18)."""
    registry = _locked_registry()
    gate = GatePass(_Clear(), _manifest(registry))

    outcome = gate.evaluate(_order("c-next"), _picture(), now=2.0)

    assert outcome.decision is Decision.DENY, outcome
    assert outcome.rule == "in_flight_lock", outcome
    assert HELD_CID in outcome.reason, outcome.reason
    assert "§4:210" in outcome.reason, outcome.reason
    assert "in_flight_lock" in outcome.evaluated, outcome.evaluated
    # FAIL-FAST (§5): the rules AFTER the lock never ran.
    assert "picture_coherence" not in outcome.evaluated, outcome.evaluated


def test_the_DENY_assertions_REJECT_a_lock_rule_that_never_blocks() -> None:
    """THE CAN-FAIL HALF. The same manifest with `InFlightLockRule` replaced by
    a rule that always clears — the exact deletion ARC 038 (F) planted — must
    produce the outcome the control above rejects."""
    registry = _locked_registry()
    rules = _manifest(registry)
    lock_index = [i for i, r in enumerate(rules) if r.name == "in_flight_lock"]
    assert lock_index, [r.name for r in rules]
    assert isinstance(rules[lock_index[0]], InFlightLockRule)
    rules[lock_index[0]] = _NeverBlocks()

    outcome = GatePass(_Clear(), rules).evaluate(_order("c-next"), _picture(), now=2.0)

    assert outcome.decision is Decision.APPROVE, (
        "the falsifier did not falsify: a lock rule that never blocks still "
        "produced a denial, so the control above cannot fail and measures nothing"
    )
    assert outcome.rule != "in_flight_lock", outcome


# ---------------------------------------------------------------------------
# 2 — FF2: the LOCK ITSELF must refuse a second take
# ---------------------------------------------------------------------------


def test_the_UNGUARDED_SHAPE_produces_the_orphan_FF2_measured() -> None:
    """THE UNPROTECTED HALF, driven first. Writing the field directly is byte
    for byte what `take_in_flight` did before ARC 038 (F): the lock names only
    the newest `client_order_id` and the teardown reports ONE release for TWO
    takes."""
    registry = StrategyRegistry()
    registry.register(STRATEGY, slot=0, now=0.0)
    row = registry.get(STRATEGY)
    assert row is not None, "the registration this control needs is absent"
    row.in_flight = "c-1"
    row.pending["c-1"] = "pending"
    row.in_flight = "c-2"  # the unguarded overwrite
    row.pending["c-2"] = "pending"

    locked, reason = registry.in_flight(STRATEGY)
    assert locked is True
    assert "c-2" in reason and "c-1" not in reason, (
        "the bad outcome did not appear, so the guard below has nothing to "
        "protect against"
    )
    dereg = registry.force_deregister(STRATEGY)
    assert dereg.released_in_flight == "c-2", dereg.reason
    assert dereg.dropped_pending == ("c-1", "c-2"), dereg.reason


def test_a_SECOND_TAKE_of_the_inflight_lock_is_REFUSED_and_says_why() -> None:
    """THE PROTECTED HALF. §4:210's *one* in-flight action is a property of the
    LOCK, not only of the rule that reads it (ARC 038 (F) finding FF2)."""
    registry = _locked_registry()

    with pytest.raises(RecoveryError) as caught:
        registry.take_in_flight(STRATEGY, "c-second")

    message = str(caught.value)
    assert HELD_CID in message, message
    assert "c-second" in message, message
    assert "§4:210" in message, message
    # The refusal changed NOTHING: the first take still holds the lock.
    locked, reason = registry.in_flight(STRATEGY)
    assert locked is True and HELD_CID in reason, reason
    row = registry.get(STRATEGY)
    assert row is not None, "the refusal removed the registration"
    assert sorted(row.pending) == [HELD_CID], row.pending


def test_CONCURRENT_takes_cannot_BOTH_hold_the_lock() -> None:
    """Eight real threads at one strategy. §5's loop is single-threaded, so this
    is a guard against the day it is not — and against the shape ARC 038 (F)
    measured, where all eight takes were accepted."""
    registry = StrategyRegistry()
    registry.register(STRATEGY, slot=0, now=0.0)
    accepted: list[str] = []
    refused: list[str] = []
    barrier = threading.Barrier(8)

    def take(cid: str) -> None:
        barrier.wait()
        try:
            registry.take_in_flight(STRATEGY, cid)
            accepted.append(cid)
        except RecoveryError as exc:
            refused.append(str(exc))

    threads = [threading.Thread(target=take, args=(f"c-{i}",)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10.0)

    assert len(accepted) == 1, (accepted, len(refused))
    assert len(refused) == 7, refused
    assert all("§4:210" in why for why in refused), refused
    row = registry.get(STRATEGY)
    assert row is not None, "the concurrent takes removed the registration"
    assert sorted(row.pending) == accepted, row.pending


# ---------------------------------------------------------------------------
# 3 — THE CENSUS RATCHET: §14's GO-timeout has no implementation
# ---------------------------------------------------------------------------


def _shipped_modules() -> list[Path]:
    listed = subprocess.run(  # nosec B603 B607 - fixed argv, no shell
        ["git", "-C", str(REPO), "ls-files", "scripts"],
        capture_output=True,
        text=True,
        check=True,
        # D3.205 / D3.22, and `check_git_env_scrub` FOUND my first spelling of
        # this: a hand-rolled pop of four GIT_* names is not the house scrub, and
        # under a hook `-C` does NOT override an exported GIT_DIR.
        env=scrubbed_env(),
    ).stdout.split()
    return [
        REPO / rel
        for rel in listed
        if rel.endswith(".py") and not rel.startswith("scripts/tests/")
    ]


@dataclasses.dataclass(frozen=True)
class _Census:
    """What the shipped population says about §14's deadlock breaker."""

    release_sites: tuple[str, ...]
    go_timeout_mentions: tuple[str, ...]
    knob_readers: tuple[str, ...]


def _clears_in_flight(rel: str, source: str) -> list[str]:
    """Every `<something>.in_flight = None` in one module, as `rel:lineno`."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source, filename=rel)):
        if not isinstance(node, ast.Assign) or ast.unparse(node.value) != "None":
            continue
        for target in node.targets:
            if isinstance(target, ast.Attribute) and target.attr == "in_flight":
                found.append(f"{rel}:{node.lineno}")
    return found


def _census() -> _Census:
    """The AST census, over `git ls-files scripts` minus `scripts/tests/`."""
    releases: list[str] = []
    mentions: list[str] = []
    readers: list[str] = []
    for path in _shipped_modules():
        rel = str(path.relative_to(REPO))
        source = path.read_text()
        releases.extend(_clears_in_flight(rel, source))
        if "go_timeout" in source or "GO-timeout" in source:
            mentions.append(rel)
        if rel != "scripts/risk_config.py" and "go_timeout_s" in source:
            readers.append(rel)
    return _Census(tuple(releases), tuple(sorted(mentions)), tuple(sorted(readers)))


def test_the_ONLY_shipped_release_of_the_inflight_lock_is_a_DEREGISTRATION() -> None:
    """§14:965 / C6 §15:994 — *'it can never wedge (GO-timeout)'*.

    A one-way RATCHET. Growth here means a normal-resolution release verb was
    added, which is the discharge of CHECK-DEBT D3.398 — update this baseline
    deliberately rather than rediscovering the census."""
    sites = _census().release_sites

    assert len(sites) == len(SHIPPED_INFLIGHT_RELEASE_SITES), (
        f"the set of shipped sites that RELEASE the one-in-flight lock moved: "
        f"{list(sites)} against the ARC 038 (F) baseline "
        f"{list(SHIPPED_INFLIGHT_RELEASE_SITES)}. CHECK-DEBT D3.398"
    )
    assert all(site.startswith("scripts/nixrisk/recovery.py:") for site in sites), sites


def test_NO_shipped_module_MEASURES_the_go_timeout_knob() -> None:
    """`limiter.go_timeout_s` is read by the BOOT VALIDATOR and by nothing else,
    so §4:212's *'no sized/denied feedback within T'* has no T. D3.398."""
    readers = _census().knob_readers

    assert not readers, (
        f"{list(readers)} now reads `go_timeout_s` outside "
        f"scripts/risk_config.py's cross-knob validator. §14's deadlock breaker "
        f"may finally exist — CHECK-DEBT D3.398 is being discharged"
    )


def test_every_shipped_GO_TIMEOUT_MENTION_is_a_NAME_and_not_a_MECHANISM() -> None:
    """The six modules that spell the token are a Plane-1 event-type name, a
    docstring, or the boot validator. Pinned so a seventh is READ, not absorbed."""
    mentions = _census().go_timeout_mentions

    assert list(mentions) == list(SHIPPED_GO_TIMEOUT_MENTIONS), (
        f"the shipped `go_timeout` surface moved: {list(mentions)} against "
        f"{list(SHIPPED_GO_TIMEOUT_MENTIONS)}. CHECK-DEBT D3.398"
    )


# ---------------------------------------------------------------------------
# 4 — THE WEDGE, with a REAL process and a REAL death
# ---------------------------------------------------------------------------

_CHILD = """
import os, sys, time
sys.path.insert(0, %r)
from nixbus.statebus import StatePublisher
pub = StatePublisher(sys.argv[1])
deadline = time.time() + 20.0
while pub.subscribes_seen == 0 and time.time() < deadline:
    pub.service(timeout_ms=50)
pub.publish("go", {"strategy_id": %r, "client_order_id": %r, "pid": os.getpid()})
print(os.getpid(), flush=True)
while True:
    pub.service(timeout_ms=200)
"""


def _spawn_go_holder(endpoint: str) -> subprocess.Popen:
    # pylint: disable=consider-using-with
    return subprocess.Popen(  # nosec B603 - argv built here, no shell
        [
            sys.executable,
            "-c",
            _CHILD % (str(REPO / "scripts"), STRATEGY, HELD_CID),
            endpoint,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "PYTHONPATH": str(REPO / "scripts")},
    )


@pytest.mark.parametrize("with_a_timeout", [False, True])
def test_a_REAL_SIGKILL_of_the_GO_HOLDER_leaves_the_lock_HELD(
    with_a_timeout: bool,
) -> None:
    """§14:965 — the wedge, REPRODUCED, and the can-fail half beside it.

    `with_a_timeout=False` is the SHIPPED tree: nothing resets the lock after a
    real death, so the gate still denies. `with_a_timeout=True` runs the same
    assertions against a simulated GO-timeout that resets to flat-and-free, and
    requires them to FLIP — without that half, "the lock is still held" is a
    sentence no observation could contradict."""
    endpoint = endpoint_for(f"arc038f_{os.getpid()}_{int(with_a_timeout)}")
    child = _spawn_go_holder(endpoint)
    subscriber = StateSubscriber(endpoint, ["go"])
    try:
        messages: list = []
        deadline = time.time() + 20.0
        while not messages and time.time() < deadline:
            messages = subscriber.drain(200)
        assert messages, "no GO arrived off the real ipc:// socket"
        assert messages[0].payload["client_order_id"] == HELD_CID

        assert child.stdout is not None
        pid = int(child.stdout.readline().strip())
        assert Path(f"/proc/{pid}").exists(), "the GO holder was never alive"

        registry = _locked_registry()
        gate = GatePass(_Clear(), _manifest(registry))
        assert gate.evaluate(_order("c-2"), _picture(), 1.0).decision is Decision.DENY

        os.kill(pid, signal.SIGKILL)
        assert child.wait(timeout=20) == -9, child.returncode
        assert not Path(f"/proc/{pid}").exists(), "the corpse is still in /proc"

        if with_a_timeout:
            # What §4:212 SPECIFIES and the tree does not have: on no feedback
            # within T, reset to flat-and-free. Simulated locally, so the
            # assertions below are provably falsifiable.
            registry.force_deregister(STRATEGY)
            registry.register(STRATEGY, slot=0, now=1.0)

        locked, reason = registry.in_flight(STRATEGY)
        outcome = gate.evaluate(_order("c-3"), _picture(), 99.0)
        if with_a_timeout:
            assert locked is False, reason
            assert outcome.decision is not Decision.DENY, outcome
        else:
            assert locked is True, (
                "the lock was released without any shipped code releasing it — "
                "if a GO-timeout now exists, CHECK-DEBT D3.398 is discharged"
            )
            assert HELD_CID in reason, reason
            assert outcome.decision is Decision.DENY, outcome
            assert outcome.rule == "in_flight_lock", outcome
    finally:
        subscriber.close()
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
        # D3.347's lesson, one transport over: a SIGKILLed publisher cannot
        # unlink its own AF_UNIX path, and a leaked endpoint outlives the run.
        # The name carries this process's pid so nothing else can own it.
        Path(endpoint.removeprefix("ipc://")).unlink(missing_ok=True)
