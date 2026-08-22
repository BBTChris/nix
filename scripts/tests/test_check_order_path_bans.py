"""`check_order_path_bans` — the DETECTION can-fail, committed rather than banked.

ARC 027 / A3. This gate stands over the frozen risk spec's no-auto-resend
invariant — `nics_risk_subsystem_spec_v1.3.md` §2A:71 (*pending-timeout
resolution, **never auto-resend***), §4:241 (the Limiter *"issues order-status
query, **never auto-resends**"*) and §12A:830 (`PENDING_ACK_TIMEOUT_MS` … *"status
query, **never resend**"*). A retry on the order path turns one intended order
into two, at the venue, with real money. It is the most consequential property
any gate in this tree guards.

--------------------------------------------------------------------------
WHY THIS FILE EXISTS: A BINDING THAT WAS REAL AND WAS NOT DURABLE
--------------------------------------------------------------------------
CHECK-DEBT's ARC 022 census records this gate **BOUND against both subjects**,
and that record is true: ARC 020 planted a genuine 3x retry into
`IBKRBrokerOrder._emit_flatten_leg`, and ARC 022 re-took `import tenacity` into
`broker_order_ibkr.py` and `import backoff` into `broker_datafeed_ibkr.py`, four
outputs and a sha256 either side of every one.

**Every one of those plants was taken by hand and banked in a results document.**
§0e says a binding claim requires a COMMITTED, RUNNABLE artifact that reproduces
the can-fail, and D2.30 is the row for exactly this class. `binding_census.py`,
run over the whole committed suite on commit `2ef4585`, reported:

    check_order_path_bans            EXERCISED-NEVER-RED      PASS:7  |  -

Seven observations of the shipped gate, all PASS. `test_actuation.py` names this
gate, but what it binds is the ACTUATION REFUSAL — that `--correct` is declined
because the order path is non-correctable. That is a different subject from the
detection path, and refusing to repair a defect proves nothing about noticing
one.

--------------------------------------------------------------------------
THE SUBJECT, AND THE VENUE
--------------------------------------------------------------------------
The subjects are the real order-path modules under `scripts/broker/` and the
gate's one declared static artifact, `checks/order_path_retry_reviewed.json`.
Every plant below lands in one of those files — never in a fabricated adapter.
The CHECK-DEBT rule of record is explicit that a plant into a purpose-built fake
proves the gate can discriminate and not that it discriminates against its real
subject, and it names ARC 018's invented `scripts/limiter/limiter_order_adapter.py`
as the worked example of the form that does NOT bind.

The VENUE is a scratch copy of the tree (doctrine C.8 / `debug.md` §7.2): real
subject, reversible venue. `scripts/broker/` is not touched.

Two drive paths, chosen per plant rather than uniformly:

  * **IN-PROCESS** for the source-code plants. `derive_scope(ctx.nix_home)` walks
    whatever tree it is handed, so the SHIPPED gate object reads the scratch
    copies of the real modules. This is the shipped bytes, in the traced
    process, which is what `binding_census.py` keys its verdict on.
  * **THE SCRATCH TREE'S OWN CLI** for the suppression-registry plants.
    `load_suppressions` resolves the registry from the gate's own `__file__`
    and ignores `ctx.nix_home` — the same trap CHECK-DEBT D2.23 records for
    `check_derived_claims`, met here rather than read about. An in-process drive
    would have measured THIS worktree's registry while wearing the scratch
    tree's name, so those two plants are driven through the scratch tree's own
    byte-identical copy of the gate.

--------------------------------------------------------------------------
§7.12 THE STANDING QUESTION, asked of this file: what would have to be true
for these tests to PASS while measuring nothing?
--------------------------------------------------------------------------
 1. **The gate could be reddening for a reason other than the plant.** A
    `SyntaxError` from a botched substitution, a missing venv, an unparseable
    probe — all reach `FAIL` or exit 1 through the same shared namespace.
    *Closed:* every assertion names the SITE and the SENTENCE the arm emits, so
    a gate broken by the harness fails these tests instead of passing them.
 2. **The scan could have collapsed to nothing** and reported no violations over
    zero files. *Closed by `test_the_scope_is_non_vacuous_before_any_plant`,*
    which asserts the derived file set, the required members, and the derived
    send-path verb set BEFORE any plant is applied, and by
    `test_an_empty_scope_is_cannot_measure_and_never_a_pass`.
 3. **The suppression registry could be silencing the plant.** A gate whose
    reviewed-site list had grown to cover the planted shape would go green and
    look tolerant. *Closed:* the registry is asserted to hold exactly one entry,
    and every shape plant is taken at a site that entry does not key.
 4. **One arm could be carrying all three.** `import tenacity` alone reddens the
    gate and would leave arms (ii) and (iii) unexercised while the gate looked
    covered. *Closed:* the plants are split per arm and per shape — three retry
    shapes, a banned library, a banned call, a resident banned module, and both
    suppression-registry failure modes — each asserting its own arm's sentence.
 5. **The restores could be nominal.** *Closed:* the `plant` fixture asserts
    every touched file returns byte-identically by sha256, and a final control
    re-passes on the restored tree.

--------------------------------------------------------------------------
WHAT IS NOT PROVEN HERE — stated, because the alternative is a silent gap
--------------------------------------------------------------------------
Arm (ii)'s plant makes a banned root package **resolvable on the order path's
own import path** and the gate reports it resident. It does NOT reproduce the
transitive case the arm was written for — a third-party dependency dragging
`tenacity` in — because doing that means installing a retry library into the
shared `.venv`, which three agents and a pre-commit hook are using. Refused for
the same reason `check_hook_suite`'s suite refuses to write the shared hooks
directory. **CHECK-DEBT D3.27.**
"""

from __future__ import annotations

# R0801: every instrument's control stands on its own file. One shared helper
# would let a single edit un-bind several gates at once.
# pylint: disable=duplicate-code
import hashlib
import json
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
import check_order_path_bans as gate  # pylint: disable=import-error
from nixverify.contract import (  # pylint: disable=import-error
    Context,
    Mode,
    Status,
)
from nixverify.loader import load_check  # pylint: disable=import-error

GATE = "checks/check_order_path_bans.py"
REGISTRY = f"checks/{gate.SUPPRESSIONS_FILE}"
ORDER = "scripts/broker/broker_order_ibkr.py"
DATAFEED = "scripts/broker/broker_datafeed_ibkr.py"
SEAM = "scripts/broker/broker_seam.py"
VENV_PYTHON = REPO / ".venv" / "bin" / "python"

# The exact send block in `IBKRBrokerOrder._emit_flatten_leg`. Anchored on the
# whole statement rather than on a line number: `debug.md` §8 failure mode #4 is
# the stale literal anchor, and the `plant` fixture asserts the anchor is present
# so a refactor breaks this file loudly instead of silently planting nothing.
_SEND = """        try:
            self.place_order(
                NeutralOrder(
                    client_order_id=cid,
                    symbol=sym,
                    side=side,
                    qty=qty,
                    order_type=OrderType.MARKET,
                    tif=TimeInForce.IOC,
                )
            )
        except Exception as exc:  # noqa: BLE001
"""

_HANDLER = """            log.error("flatten failed for %s: %s", sym, exc)
            return None, (sym, str(exc))
"""


# ---------------------------------------------------------------------------
# THE SCRATCH TREE. Doctrine C.8: no plant touches a production artifact.
# ---------------------------------------------------------------------------


@pytest.fixture(name="scratch", scope="module")
def _scratch(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A full copy of the tree, `.venv` symlinked rather than duplicated.

    `state/` is excluded deliberately: it is a symlink back to the canonical
    tree and `copytree` would follow it into live operational data.
    """
    home = tmp_path_factory.mktemp("order_path_bans") / "nix"
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


@pytest.fixture(name="plant")
def _plant(scratch: Path) -> Iterator[Callable[[str, str, str], None]]:
    """Substitute one string in a named REAL subject file, then restore it.

    Both halves of doctrine C.2: the caller measures with the plant in, and the
    teardown asserts every file touched came back with the sha256 it went in
    with. Files created by a test (rather than edited) are removed by the test
    itself; this fixture owns edits.
    """
    originals: dict[Path, tuple[str, str]] = {}

    def _purge() -> None:
        for cache in scratch.rglob("__pycache__"):
            shutil.rmtree(cache, ignore_errors=True)

    def _apply(relative: str, old: str, new: str) -> None:
        target = scratch / relative
        if target not in originals:
            originals[target] = (target.read_text(encoding="utf-8"), _sha(target))
        before, before_sha = originals[target]
        assert old in before, f"plant anchor is not in {relative}: {old[:60]!r}"
        _purge()
        target.write_text(before.replace(old, new, 1), encoding="utf-8")
        assert _sha(target) != before_sha, "the plant changed nothing"

    yield _apply
    _purge()
    for target, (before, before_sha) in originals.items():
        target.write_text(before, encoding="utf-8")
        assert _sha(target) == before_sha, f"{target} was not restored byte-identically"


def _verdict(home: Path):  # type: ignore[no-untyped-def]
    """Drive the SHIPPED gate in this process against `home`."""
    loaded = load_check(CHECKS, "check_order_path_bans")
    assert loaded.run is not None, loaded.load_error
    return loaded.run(Mode.VERIFY, Context(nix_home=home, mode=Mode.VERIFY))


def _cli(home: Path) -> tuple[int, str]:
    """Drive the SCRATCH TREE'S OWN copy of the gate as a program.

    `PYTHONPATH` is PREPENDED, never replaced: `checks/_preamble.py` APPENDS its
    `scripts/` directory, so a real `scripts/` already on the path would shadow
    the scratch one; and `binding_census.py` installs its tracer through
    `PYTHONPATH`, so replacing it would make this verdict invisible to the one
    instrument that has to confirm the binding.
    """
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        [str(home / "scripts")] + ([existing] if existing else [])
    )
    proc = subprocess.run(  # nosec B603 - fixed argv, shell=False, scratch tree
        [str(VENV_PYTHON), str(home / GATE), str(home)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(home),
        env=env,
    )
    return proc.returncode, (proc.stdout or proc.stderr).strip()


# ===========================================================================
# NON-VACUITY — asserted before any plant (doctrine C.3).
# ===========================================================================


def test_the_scope_is_non_vacuous_before_any_plant(scratch: Path) -> None:
    """§7.12 conditions 1-2: an empty scope or an empty ban list finds nothing.

    Asserted against the DERIVED scope rather than against `ORDER_PATH_DIRS`,
    because the anchor is a floor and the live scope is what the scan reads.
    """
    scope = gate.derive_scope(scratch)
    assert scope.complaint == "", scope.complaint
    names = {path.name for path in scope.files}
    for member in gate.REQUIRED_MEMBERS:
        assert member in names, names
    assert scope.send_verbs >= {"place_order", "flatten"}, scope.send_verbs
    assert gate.BANNED_MODULES and gate.BANNED_CALLS and gate.RETRY_SHAPES


def test_the_control_passes_and_its_evidence_names_what_it_read(
    scratch: Path,
) -> None:
    """CONTROL. A PASS is only accepted from a run that demonstrably measured."""
    result = _verdict(scratch)
    assert result.status is Status.PASS, result.detail
    evidence = result.evidence or ""
    assert "broker_order_ibkr.py" in evidence
    assert "send-path ['cancel_order', 'flatten', 'place_order']" in evidence
    # ARC 029: the order path acquired a package home (scripts/nixrisk, the exit
    # half), so arm(ii) now imports the broker modules AND the nixrisk package
    #
    # ARC 033 / Stage 1, integration: 18 -> 24, reached by FIVE independent bumps
    # from five worktrees none of which could see the others:
    #   1A  +1  blackout.py                (§6.1-6.3 window evaluator)
    #   1B  +2  session.py, roll.py        (§6.1b deadline, §7.5 roll instant)
    #   1C  +2  pollers.py, freshness.py   (§6.4 pollers, §6.4/§12.3 detector)
    #   1D  +1  halt.py                    (§12.5 HALT state machine)
    # Each branch was right about its own modules and wrong about the total, and
    # this ONE LINE caught every collision -- three separate merge conflicts.
    # TWO of the bumps were made by the INTEGRATOR, because a session cap killed
    # 1C's and 1D's authors inside this very gate and nobody was left to answer
    # the tripwire.
    #
    # 1A's own comment PREDICTED the collision in writing -- "if another Stage 1
    # sub-agent adds a scripts/nixrisk/ module in a parallel worktree, this line
    # conflicts at integration, which is the tripwire doing its job". It did,
    # three times.
    #
    # Re-banked at the figure `check_order_path_bans` ITSELF reports on the MERGED
    # tree, never at any branch's arithmetic -- that distinction is the lesson:
    # five correct local answers summed to a wrong global one, and only a literal
    # a human must meet made the disagreement visible. Every admitted module is a
    # declaration or detector surface: none declares an order-port verb, sends
    # anything, carries a retry shape or imports anything banned, and the gate
    # re-scanned the widened scope and still reports 0 banned calls.
    #
    # Kept a LITERAL, deliberately. Deriving it from the gate would make the test
    # agree with its subject by construction and measure nothing.
    #
    # ARC 034 / Phase 0.6: 24 -> 25, ONE bump, from `scripts/nixrisk/fill_seam.py`
    # — the frozen fill-handler seam. The tripwire fired on the very next arc, as
    # D3.192 said it would, and this time from a SERIAL phase rather than parallel
    # worktrees, so there was one bump instead of five and no merge conflict. The
    # admitted module is a declaration surface: `check_order_path_bans` re-scanned
    # the widened scope and still reports 0 banned calls, 0 banned modules, and no
    # retry shape. Re-banked at the figure the gate ITSELF reports on the merged
    # tree, never at arithmetic done here.
    #
    # ARC 034 INTEGRATION: 25 -> FOUR bumps, and D3.192's cost paid for the third
    # arc running. Sub-agent A added `scripts/nixrisk/fills.py` (the fill handler
    # D3.178 said was missing) and `scripts/nixrisk/join.py` (D3.177's production
    # trade<->order mint); sub-agent C added `scripts/nixrisk/supervision.py`
    # (§12.2's crash-loop breaker) and `scripts/nixrisk/recovery.py` (§4's
    # orphan/strategy-death sequencer). BOTH branches independently wrote
    # "25 -> 27" and BOTH were locally right and globally wrong — the literal is
    # the only reason that disagreement was ever visible, which is D3.192's whole
    # argument restated by a live instance.
    #
    # These are the first bumps in the series that admit real BEHAVIOUR rather
    # than declaration surface, so the re-scan mattered more than usual and was
    # READ rather than assumed: over the widened scope the gate still reports 0
    # banned calls, 0 banned modules and no retry shape. `fills.py` reaches the
    # venue through ONE narrow injected port carrying `cancel_order` alone (§4's
    # IOC cancel) with no `place_order` and no `flatten` on it; `recovery.py`
    # reaches the broker only by handing a `FlattenTrigger` to `nixrisk.flatten`,
    # the one place a flatten is issued (§14).
    #
    # Re-banked at the figure `check_order_path_bans` ITSELF reports on the MERGED
    # tree, never at either branch's arithmetic. Kept a LITERAL: deriving it from
    # the gate would make this test agree with its subject by construction.
    # RE-BANKED ARC 035 / Stage 1 / sub-agent B: 29 -> 31. `scripts/nixrisk/`
    # gained `projection.py` (§9's positions fold) and `plane1_seed.py` (the
    # scratch-log fixture conduit), and arm(ii) imports the directory. The gate
    # itself is UNCHANGED and still reports 0 banned modules and 0 banned calls
    # under arm(ii) — the literal went stale, not the property.
    #
    # **INTEGRATOR: THIS FIGURE IS BRANCH ARITHMETIC AND MUST BE RE-MEASURED ON
    # THE MERGED TREE.** The comment above says the figure is banked at what the
    # gate reports on the MERGED tree, never at a branch's; three sibling
    # branches may also add `scripts/nixrisk/` modules, and every one of them
    # moves this number. 31 is what arc-035-b alone measures.
    # RE-BANKED AT THE GATE'S OWN MERGED MEASUREMENT — ARC 035 Stage 2, and this
    # is D3.192's shape for the FOURTH arc running. Three parallel sub-agents
    # each bumped this literal from a worktree that could not see the other two:
    # A said 30 (plane1_sink.py), B said 31 (projection.py + plane1_seed.py),
    # C said 30 (degraded.py). Every one of them was locally right and globally
    # wrong; the merged tree's own figure is 34, larger than all three, because
    # `scripts/nixrisk/` gained six modules across four branches and arm(ii)
    # imports the directory.
    #
    # The literal is the ONLY reason that disagreement was ever visible, and it
    # is re-banked from the gate's printed evidence rather than from anybody's
    # arithmetic. Re-read rather than assumed: over the widened scope the gate
    # still reports 0 banned modules and 0 banned calls under arm(ii) — the
    # literal went stale, the property did not.
    # ARC 037 / sub-agent A: 34 -> 35. `scripts/nixrisk/realized.py` (D3.220's
    # realized-P&L arithmetic) is the thirty-fifth module arm(ii) imports. This
    # is D3.192's shape for the FIFTH arc running and the bump is made from a
    # worktree that cannot see its five siblings, so it is EXPECTED to be wrong
    # again on the merged tree — the integrator re-banks it from the gate's own
    # merged evidence, exactly as ARC 035 Stage 2 did. Re-read rather than
    # assumed: over the widened scope the gate still reports 0 banned modules
    # and 0 banned calls under arm(ii).
    # ARC 039: 35 -> 36. `scripts/nixrisk/loop.py` — the §5:322 single-threaded
    # event loop this arc stood up — is the thirty-sixth module arm(ii)
    # imports, and it is IN this gate's scope by construction rather than by
    # accident: arm(ii) imports `scripts/nixrisk/` whole, and the loop is the
    # process the order path will run inside. D3.192's shape for the SIXTH arc
    # running, and this time the bump is made by the integrator from the
    # merged tree, so the worktree-blindness that made ARC 035 and ARC 037
    # re-bank it does not apply. Re-read rather than assumed: over the widened
    # scope the gate still reports 0 banned modules and 0 banned calls under
    # arm(ii) — 232 modules resident, 0 banned. The literal went stale; the
    # property did not.
    # ARC 046: 36 -> 38, and it is TWO bumps in one edit because the literal was
    # ALREADY STALE when this arc opened. MEASURED both sides: with ARC 046's
    # file moved aside the merged tree reports 37, with it present 38.
    #   36 -> 37  `scripts/nixrisk/outcomes.py`, landed in ARC 044 (4d04bfd)
    #             without bumping this line.
    #   37 -> 38  `scripts/nixrisk/completions.py`, ARC 046's §5:322 completion
    #             parse + §4:214 dedup + dispatch.
    #   38 -> 39  `scripts/nixrisk/stopwatch.py`, ARC 055's §5:322 price poll +
    #             §4:190-196 trail maintenance + breach DETECTION. It joined the
    #             derived scope the moment it landed under `scripts/nixrisk`, and
    #             the gate re-read over the widened scope still reports 0 banned
    #             modules and 0 banned calls: the poll DETECTS and ENQUEUES and
    #             reaches no order verb at all — `StopWatch` holds no broker by
    #             construction (`test_stopwatch.py` asserts the absence). This
    #             arc's own bump, made in the arc that caused it rather than
    #             discovered two arcs later.
    # WHY IT SURVIVED TWO ARCS, which is the part worth keeping: ARC 044 and
    # ARC 045 both committed on the testmon-SELECTED path — neither touched a
    # testmon-uncovered file, so neither escalated, and this test was never
    # selected because its own file had not changed. That is
    # `scripts/runtime_gate.py`'s hazard #4 verbatim ("a test in a file the db
    # has no fingerprint for that is ALSO unchanged against HEAD... visible only
    # on the incremental path; the escalated run does execute it"). ARC 046
    # touches `scripts/limiterd.py`, which IS uncovered, so its commit escalated
    # to the full pass and the two-arc-old red surfaced. FOUND, not caused —
    # and it is the second reason S4.4 recommends bringing limiterd.py under
    # testmon: an escalation that only happens by accident is not a schedule.
    # Re-banked from the gate's OWN printed evidence on the merged tree, never
    # from arithmetic here. Re-read rather than assumed: over the widened scope
    # the gate still reports 0 banned modules, 0 banned calls, and no new retry
    # shape; `completions.py` declares no order-port verb and sends nothing.
    # ARC 058 (I1 ARC D): 39 -> 40. `scripts/nixrisk/closing.py` is a NEW module
    # under an anchor directory, so the gate's DERIVED scope widened by one and
    # arm(ii) imports one module more. **Re-banked from the gate's OWN printed
    # evidence on the merged tree, never from arithmetic here** — and the reason
    # this number is banked at all is that a scope collapse and a scope that
    # merely moved must be different readings. Re-read rather than assumed: over
    # the widened scope the gate still reports the SAME 3 advisory sites and NO
    # new banned module, banned call or retry shape. `closing.py` declares no
    # order-port verb and sends nothing: §4's close it performs is a §3 commit,
    # two stop-book forgets, a §12.10 row and a strategy notify — the venue was
    # already reached by the flatten this module reconciles.
    assert "arm(ii) imported 40 order-path module(s)" in evidence, evidence


def test_the_reviewed_suppressions_are_the_two_known_fanouts_and_no_plant_is_pre_silenced(
    scratch: Path,
) -> None:
    """§7.12 answer 3 of this file: a grown registry would silence the plants.

    TWO fan-out reviews now exist, both `loop_contains_send`, both genuine:
    `IBKRBrokerOrder.flatten` / `_emit_flatten_leg` (ARC 018, one close per
    symbol) and, ARC 029, `ProtectiveFlatten.cancel_entries_on_onset` /
    `cancel_order` (one entry-cancel per pending order). The property this test
    guards is unchanged: NEITHER key covers `IBKRBrokerOrder._emit_flatten_leg`,
    where every shape plant below is taken, so no plant is pre-silenced. A THIRD,
    unexplained entry — the way a registry rots into a detector-silencer — still
    fails here.
    """
    payload = json.loads((scratch / REGISTRY).read_text(encoding="utf-8"))
    keys = {(e["qualname"], e["shape"], e["verb"]) for e in payload["reviewed"]}
    assert keys == {
        ("IBKRBrokerOrder.flatten", gate.SHAPE_LOOP, "_emit_flatten_leg"),
        ("ProtectiveFlatten.cancel_entries_on_onset", gate.SHAPE_LOOP, "cancel_order"),
    }, keys
    # The plant site is covered by NEITHER review, so the shape plants below still
    # redden the gate rather than landing pre-silenced.
    assert not any(
        e["qualname"] == "IBKRBrokerOrder._emit_flatten_leg"
        for e in payload["reviewed"]
    )
    for entry in payload["reviewed"]:
        assert entry["justification"].strip() and entry["reviewed_in"].strip()


def test_the_main_guard_discrimination_is_still_an_advisory_not_a_violation(
    scratch: Path,
) -> None:
    """ARC 017's measured calibration, pinned so a future edit cannot erase it.

    `seam_simulate.py`'s `sys.exit(asyncio.run(main()))` inside a module-level
    `__main__` guard is the correct implementation of a CLI driver. Doctrine B.4
    makes a gate that reddens correct code broken rather than strict, so the
    site is an ADVISORY that is counted and named on every run. If it ever
    becomes a violation this test says so, and if the advisory disappears
    entirely the gate has stopped looking.
    """
    evidence = _verdict(scratch).evidence or ""
    assert "ADVISORY seam_simulate.py" in evidence
    assert "inside __main__ guard, not imported" in evidence


# ===========================================================================
# ARM (i) — BANNED RETRY LIBRARIES AND LOOP-BLOCKING CALLS.
# ===========================================================================


def test_a_banned_retry_library_on_the_order_adapter_is_named_by_file_and_line(
    scratch: Path, plant: Callable[[str, str, str], None]
) -> None:
    """CAN-FAIL, arm (i), SUBJECT 1 — `scripts/broker/broker_order_ibkr.py`.

    This is ARC 020/022's plant, made reproducible. `tenacity` is the canonical
    instance of the banned class: a `@retry` decorator on `place_order` sends the
    order again after the venue already had it.
    """
    plant(
        ORDER,
        "from __future__ import annotations",
        "from __future__ import annotations\n\nimport tenacity",
    )
    result = _verdict(scratch)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "broker_order_ibkr.py" in (result.site or "")
    assert "banned retry library 'tenacity'" in (result.detail or "")


def test_a_banned_retry_library_on_the_datafeed_adapter_binds_the_second_subject(
    scratch: Path, plant: Callable[[str, str, str], None]
) -> None:
    """CAN-FAIL, arm (i), SUBJECT 2 — `scripts/broker/broker_datafeed_ibkr.py`.

    Clause 2 of the CHECK-DEBT rule of record: *a second subject re-opens the
    question* — a gate bound against one module is unbound against the next. This
    module entered scope in ARC 021 and is planted separately for that reason,
    not for symmetry.
    """
    plant(
        DATAFEED,
        "from __future__ import annotations",
        "from __future__ import annotations\n\nimport backoff",
    )
    result = _verdict(scratch)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "broker_datafeed_ibkr.py" in (result.site or "")
    assert "banned retry library 'backoff'" in (result.detail or "")


def test_a_loop_blocking_call_reachable_by_import_is_a_violation_not_an_advisory(
    scratch: Path, plant: Callable[[str, str, str], None]
) -> None:
    """CAN-FAIL, arm (i), the OTHER ban class, and the discrimination that matters.

    §2A:103-107 invariant 5: the send path is non-blocking regardless of vendor,
    and `flatten()` is the protective path that must not block. The advisory test
    above proves the same call inside a `__main__` guard is tolerated; this
    proves that the moment it is reachable by importing the seam it is a
    violation. One plant without the other would leave the discrimination
    unmeasured in one direction.
    """
    plant(
        SEAM,
        "\nORDER_PORT_VERBS",
        "\ndef _drain_now(loop):\n    return loop.run_until_complete(None)\n\n\n"
        "ORDER_PORT_VERBS",
    )
    result = _verdict(scratch)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "broker_seam.py" in (result.site or "")
    assert "banned loop-blocking call 'run_until_complete'" in (result.detail or "")


# ===========================================================================
# ARM (iii) — THE THREE HAND-ROLLED RETRY SHAPES. One plant each.
# ===========================================================================


def test_a_bounded_retry_loop_around_the_send_is_detected_structurally(
    scratch: Path, plant: Callable[[str, str, str], None]
) -> None:
    """CAN-FAIL, arm (iii) SHAPE 1 — ARC 020's plant, in the same method.

    `for _attempt in range(3): self.place_order(...)` passes both of the older
    arms — no retry library, no loop-blocking call — and sends up to three
    market orders where the caller intended one. CHECK-DEBT D2.14 is this shape.
    """
    plant(
        ORDER,
        _SEND,
        """        try:
            for _attempt in range(3):
                self.place_order(
                    NeutralOrder(
                        client_order_id=cid,
                        symbol=sym,
                        side=side,
                        qty=qty,
                        order_type=OrderType.MARKET,
                        tif=TimeInForce.IOC,
                    )
                )
        except Exception as exc:  # noqa: BLE001
""",
    )
    result = _verdict(scratch)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert "IBKRBrokerOrder._emit_flatten_leg" in (result.site or "")
    assert f"[{gate.SHAPE_LOOP}]" in (result.site or "")
    assert "send-path verb called inside a `for` body" in (result.detail or "")


def test_a_bounded_counter_guarding_the_send_is_detected_without_a_name_heuristic(
    scratch: Path, plant: Callable[[str, str, str], None]
) -> None:
    """CAN-FAIL, arm (iii) SHAPE 2 — the retry that is NOT a loop.

    A re-entrant callback guarded by a counter the same function mutates is a
    bounded retry with no `for` anywhere. The gate detects it from the MUTATION,
    not from the identifier's spelling; the planted counter is deliberately
    named `_resend_tries` and the gate's reported reason must quote the name it
    found by structure rather than one it pattern-matched.
    """
    plant(
        ORDER,
        _SEND,
        """        self._resend_tries = getattr(self, "_resend_tries", 0)
        if self._resend_tries < 3:
            self._resend_tries += 1
            self.place_order(
                NeutralOrder(
                    client_order_id=cid,
                    symbol=sym,
                    side=side,
                    qty=qty,
                    order_type=OrderType.MARKET,
                    tif=TimeInForce.IOC,
                )
            )
"""
        + _SEND,
    )
    result = _verdict(scratch)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert f"[{gate.SHAPE_COUNTER}]" in (result.site or "")
    assert "mutated in the same function (bounded retry counter)" in (
        result.detail or ""
    )
    assert "_resend_tries" in (result.detail or "")


def test_an_except_handler_that_re_invokes_the_send_is_detected(
    scratch: Path, plant: Callable[[str, str, str], None]
) -> None:
    """CAN-FAIL, arm (iii) SHAPE 3 — a retry by definition.

    The `try` body sent, the send raised, and the handler sends again. This is
    the shape the reviewed suppression on `IBKRBrokerOrder.flatten` names in its
    own `re_review_if` trigger as the thing it does NOT cover, so the gate must
    redden on it even though a suppression exists one frame up.
    """
    plant(
        ORDER,
        _HANDLER,
        """            log.error("flatten failed for %s: %s", sym, exc)
            self.place_order(
                NeutralOrder(
                    client_order_id=cid,
                    symbol=sym,
                    side=side,
                    qty=qty,
                    order_type=OrderType.MARKET,
                    tif=TimeInForce.IOC,
                )
            )
            return None, (sym, str(exc))
""",
    )
    result = _verdict(scratch)
    assert result.status is Status.FAIL_NEEDS_OPERATOR
    assert f"[{gate.SHAPE_EXCEPT}]" in (result.site or "")
    assert "`except` handler re-invokes place_order()" in (result.detail or "")


# ===========================================================================
# ARM (ii) — THE DYNAMIC ARM. See the module docstring for what this does NOT
# reproduce (CHECK-DEBT D3.27).
# ===========================================================================


def test_a_banned_module_resident_after_importing_the_order_path_is_reported(
    scratch: Path,
) -> None:
    """CAN-FAIL, arm (ii). The arm reads a real child interpreter's `sys.modules`.

    Arm (i) cannot see a banned package that no in-scope file imports by name;
    arm (ii) exists for that case. The plant makes `tenacity` resolvable on the
    order path's own import path, and the gate reports it resident and names the
    interpreter that held it.
    """
    fake = scratch / "scripts" / "broker" / "tenacity.py"
    fake.write_text("VERSION = '0'\n", encoding="utf-8")
    try:
        result = _verdict(scratch)
        assert result.status is Status.FAIL_NEEDS_OPERATOR
        assert "sys.modules['tenacity']" in (result.site or "")
        assert "banned module reachable by import" in (result.detail or "")
    finally:
        fake.unlink()
    assert _verdict(scratch).status is Status.PASS


# ===========================================================================
# THE DECLARED STATIC SUBJECT — `checks/order_path_retry_reviewed.json`.
# Driven through the SCRATCH TREE'S OWN CLI; see the module docstring on D2.23.
# ===========================================================================


def _write_registry(home: Path, mutate: Callable[[dict], None]) -> str:
    payload = json.loads((home / REGISTRY).read_text(encoding="utf-8"))
    mutate(payload)
    (home / REGISTRY).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return ""


def test_an_unsigned_suppression_is_a_violation_and_the_site_it_hid_returns(
    scratch: Path,
) -> None:
    """CAN-FAIL against the gate's declared SUBJECT, and it fires TWICE over.

    An entry with no `justification` is not a review, so the gate rejects it as
    a defect AND the site it was covering comes back as an unsuppressed hit.
    Both sentences are asserted: a gate that only did the first would be
    silencing a real site on the strength of an entry it had itself refused.
    """
    before = (scratch / REGISTRY).read_text(encoding="utf-8")
    before_sha = _sha(scratch / REGISTRY)
    try:
        _write_registry(
            scratch, lambda p: p["reviewed"][0].update({"justification": ""})
        )
        code, out = _cli(scratch)
        assert code == 1, out
        assert "unsigned — missing justification" in out, out
        assert "an unsigned suppression is not a review" in out, out
        assert "IBKRBrokerOrder.flatten [loop_contains_send]" in out, out
    finally:
        (scratch / REGISTRY).write_text(before, encoding="utf-8")
    assert _sha(scratch / REGISTRY) == before_sha


def test_a_suppression_that_matches_nothing_is_a_violation_not_a_no_op(
    scratch: Path,
) -> None:
    """CAN-FAIL, the self-expiring property — measured, not asserted in prose.

    ARC 020 met this for real: extracting the send into `_emit_flatten_leg`
    moved the site and the ARC 018 review went stale, and the gate reported it.
    The plant reproduces the move by renaming the qualname the entry keys.
    """
    before = (scratch / REGISTRY).read_text(encoding="utf-8")
    before_sha = _sha(scratch / REGISTRY)
    try:
        _write_registry(
            scratch,
            lambda p: p["reviewed"][0].update(
                {"qualname": "IBKRBrokerOrder.flatten_everything"}
            ),
        )
        code, out = _cli(scratch)
        assert code == 1, out
        assert "STALE SUPPRESSION" in out, out
        assert "the review no longer applies" in out, out
    finally:
        (scratch / REGISTRY).write_text(before, encoding="utf-8")
    assert _sha(scratch / REGISTRY) == before_sha


# ===========================================================================
# THE VACUITY GUARD, AND THE RESTORE.
# ===========================================================================


def test_an_empty_scope_is_cannot_measure_and_never_a_pass(tmp_path: Path) -> None:
    """§5.3 / check contract §10. A gate that could not look must not report clean.

    Exit 2, not 1 and not 0: the gate did not observe a violation and it did not
    observe compliance either. The REASON is asserted, because 2 is as shared a
    namespace as 1.
    """
    result = _verdict(tmp_path)
    assert result.status is Status.CANNOT_MEASURE
    assert "an empty scope is never a PASS" in (result.detail or "")


def test_the_control_is_green_again_once_every_plant_is_gone(scratch: Path) -> None:
    """The unplant leg of doctrine C.2, taken after the plants rather than beside them.

    The `plant` fixture asserts each file's sha256 came back; this asserts the
    GATE agrees, and compares the scratch subjects against the real ones so a
    plant that leaked into a file the fixture never recorded would be caught.
    """
    for relative in (ORDER, DATAFEED, SEAM, REGISTRY):
        assert _sha(scratch / relative) == _sha(REPO / relative), relative
    assert _verdict(scratch).status is Status.PASS
