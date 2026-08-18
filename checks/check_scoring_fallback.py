#!/usr/bin/env python3
# pylint: disable=duplicate-code,too-many-lines
# C0302 (too-many-lines): one arm per declared property, each carrying its own
# reason string — an operator reads those instead of the code, and
# `docs/nix_check_contract.md` §5.5 keeps ONE gate to ONE property, so splitting
# the arms across two modules would create a second gate over half a property.
# §4.2 forbids the shared helper module that is the only other way to shorten it.
# R0801 pairs this file's DECLARATION BLOCK — `PRIVILEGE`/`INTERACTIVE`/
# `DISRUPTIVE`, `DEPENDS_ON`/`RESOURCES`/`TIME_BOUND`/`CORRECTABLE`/`SUBJECTS`,
# and the `standalone_main` `__main__` — against every other check's. That
# similarity is the CONTRACT (`docs/nix_check_contract.md` §4.2, §4.4): the
# symbols are read STATICALLY, by AST, without importing the check, so a shared
# base module would be invisible to that reader and would break the contract to
# satisfy a similarity counter.
"""Gate: order flow SURVIVES the Scoring process being killed, and a stale table
falls back exactly as an absent one does.

Every bare `§` cites `docs/nics_risk_subsystem_spec_v1.3.md`, the frozen risk
spec. Where another document is meant it is named on the line.

ARC 036 / sub-agent C. The property is **§6.6:465's locked fallback, holding
against a real death and a real clock.**

Subjects: `scripts/nixscore/process.py` and `scripts/scoring_kill_drill.py`,
driven as REAL objects in REAL processes — never re-implemented here. One gate
over one property, as `docs/nix_check_contract.md` §5.5 requires.

`checks/check_scoring_seam.py` already drives all five FCFS triggers IN-PROCESS
and this gate does not repeat it (doctrine C.9). What that gate structurally
cannot do is the thing §6.6 is actually about: **kill the writer.** Every outage
it drives is a Python object that was never fed. So the division is exact —
that gate owns the seam's SHAPE and its five triggers; this one owns what
happens when a pid stops existing.

------------------------------------------------------------------------------
THE ARMS
------------------------------------------------------------------------------

* **ARM KILL — the death was real.** The reaped wait status must be exactly
  `-SIGKILL` for a pid the CHILD announced, the pid must be alive before the
  signal and gone from `/proc` after the reap. Paired with **ARM CLEAN**, the
  §18 discriminator: the identical child stopped with `SIGTERM` reaps
  `SIGNALLED_EXIT`, so "it died" cannot be satisfied by "it exited" — and a
  child that never started raises inside the drill before any arm runs, so it
  cannot be satisfied by "it never lived" either.

* **ARM FLOW — order flow did not halt, MEASURED.** Every arbitration carries a
  monotonic stamp and the gate reads the WORST gap between consecutive ones,
  including the gap that straddles the kill instant. A mean would hide the one
  event that matters. Floors on the decision counts before and after, because
  "it never stopped" is a statement about a loop that never ran unless the loop
  ran. Any exception out of the order path is a defect: §6.6 forbids the stall,
  and a raise is a stall wearing a traceback.

* **ARM LIVE — the ranking was working before the kill.** `fcfs_pre` must be
  ZERO and `ranked_pre` above its floor. Without this the "fallback" could be a
  mirror that was cold from the start, and the kill would have changed nothing.

* **ARM CONTROL — the un-break half.** The same loop for the same wall-clock
  with the publisher ALIVE: zero FCFS, still fresh at the end, no alert. This is
  what makes the FCFS in ARM KILL attributable to the kill rather than to the
  passage of time.

* **ARM STALE — a LIVE process whose table stopped moving.** The dangerous case
  and the reason this arm exists separately: the table is real, complete,
  populated and confidently answerable, and it stopped being true. Nothing died,
  so an implementation keying freshness on process liveness passes every other
  arm and fails only here. Driven from BOTH sides of the threshold against REAL
  elapsed wall-clock, plus never-fed — the middle of the range is the one place
  a broken predicate and a correct one agree. `rows_held == 2` on both samples
  is the *present* in stale-but-present.

* **ARM WINDOW — the interval in which readers RANK on a dead process's table.**
  Not a defect: it is what §12.7's freshness model costs, and it is exactly
  `stale_after_s` long. It is gated anyway, in both directions — a window of
  zero would mean the threshold is not being measured against elapsed time, and
  an unbounded one would mean the transition never happens. The count of orders
  ranked from a corpse's table is reported as evidence rather than left to be
  discovered.

* **ARM ALERT — §12.9's Warning tier fired, with the cause.** *Scoring down ⇒
  FCFS fallback* must reach an operator once (edge, not level) carrying the age,
  the threshold and the row count — §12.9: *"alerts carry the cause and the
  relevant snapshot values, not just a code"*.

* **ARM RESTART — nothing wedges.** Scoring relaunches on the same endpoint and
  the reader, which was NOT restarted and NOT resubscribed, must RANK again.
  If it could not, an operator restarting Scoring would leave every consumer on
  FCFS permanently and silently — the alarm is edge-triggered and has already
  fired.

* **ARM SHAPE — the hazard stated backwards.** §6.6 forbids the fallback from
  denying or stalling. So `RankingReader.arbitrate` must be a pure delegation
  (no raise, no loop, no try, no I/O), and `process.py` must contain no
  HALT/deny/flatten verb anywhere: a Scoring module that can halt order flow is
  the failure this whole section is written to prevent, spelled as a feature.

------------------------------------------------------------------------------
THE STANDING QUESTION (`docs/debug.md` §7.12) — WHAT WOULD HAVE TO BE TRUE FOR
THIS GATE TO PASS WHILE MEASURING NOTHING
------------------------------------------------------------------------------

1. *The drill reported a kill it never made.* Closed by reading the KERNEL's
   reaped status and `/proc`, and by ARM CLEAN producing a DIFFERENT status from
   the same code path.
2. *Every arm read the same one drill run, so a broken drill greens everything.*
   Closed by the counter-arms: ARM CONTROL and ARM STALE run their own processes
   and demand OPPOSITE answers, so a drill that returned a constant fails at
   least one.
3. *The gate's defect functions cannot fire.* Closed by `_arms_can_fail`, which
   feeds each defect function a DOCTORED outcome — a reap status of 0, a decision
   gap of ten seconds, a stale sample reported fresh, a delegating `arbitrate`
   rewritten to loop — and refuses to certify unless every one of them produces a
   finding. A control that cannot demonstrate the defect is BLIND, not passing.
4. *The plants ran against the shipped files.* They do not: every AST plant is a
   source STRING authored in this file (doctrine C.8), and no arm writes to a
   production artifact.
5. *Everything was inspected and nothing was counted.* Closed by the floors, all
   of which are ORDERS OF MAGNITUDE below the figures measured on this node
   (`docs/debug.md` §7.4) and none of which is zero.
6. *`pyzmq` is missing so the gate skipped and the runner read the skip as
   fine.* Closed by `docs/nix_check_contract.md` §17: an unimportable drill is
   `CANNOT_MEASURE`, never PASS, and the reason names the interpreter.
7. *The boundary arm reddened because the box was busy, and someone widened it.*
   The inverse failure, and the likelier one: three sub-agents ran `pytest`
   concurrently on this node while this gate was built, and the two freshness
   samples sit 100 ms either side of the threshold. Closed WITHOUT widening
   anything — `_sample_defects` judges the verdict against the age it MEASURED
   rather than the offset the drill aimed at, and `boundary_unmeasurable` makes
   a run whose samples failed to straddle the threshold `CANNOT_MEASURE`.
   Widening the offsets was the cheap fix and is refused for `docs/CHECK-DEBT.md`
   D3.204's reason: a tolerated failure is invisible where a CANNOT_MEASURE is
   loud, and a red attributed to the scheduler is as dishonest as a green.
8. *The shape arm scanned the WRONG `RankingReader`.* ADDED ARC 037, and it is
   not hypothetical: ARC 036 shipped TWO classes of that name in
   `scripts/nixscore/` (CHECK-DEBT D3.271), so this gate was naming
   `process.py` as a constant while `scripts/scoring_kill_drill.py` drove the
   other one. A gate can scan a pure delegation forever while the order path
   that actually runs is somewhere else. Closed by `reader_module`, which
   DERIVES the single module defining the class and makes **any other count a
   defect naming every file it found** — with `_reader_module_arm` planting a
   duplicate, and a vacuum, on every run so the derivation's silence is worth
   something. `SUBJECTS` still names the file statically and the two can
   disagree; that gap is recorded as CHECK-DEBT D3.338 rather than claimed shut.
"""

from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path
from typing import Any

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status, result_from_defects

# pylint: disable=duplicate-code

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: The drill spawns `.venv/bin/python` children that import `pyzmq`.
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: Declared against what the drill OBSERVABLY does, not against what it intends
#: (check contract rule 12 / §17: the observer outranks the declaration).
#: * `subprocess:python` / `subprocess:python3` — the drill spawns
#:   `scripts/nixscore/process.py` under `sys.executable`, six times. BOTH
#:   spellings, because the observer matches a subprocess claim by BASENAME and
#:   `sys.executable` is `.venv/bin/python` under pytest and `/usr/bin/python3`
#:   under `nix-verify.service`.
#: * `file-write:/tmp` — the bus root is a `tempfile.TemporaryDirectory`.
#: * `zmq-ipc` — `StatePublisher` binds an `ipc://` endpoint and
#:   `StateSubscriber` connects it. NOT observable by
#:   `check_observed_resource_claims` (libzmq calls `bind(2)` from C, so no
#:   Python-level syscall is seen), so it is declared for the PLAN's benefit:
#:   shared with `check_state_bus`, `check_feed_kill_drill` and the allocator
#:   mirror gates, which must therefore not run parallel with this one.
RESOURCES: tuple[str, ...] = (
    "subprocess:python",
    "subprocess:python3",
    "file-write:/tmp",
    "zmq-ipc",
)
TIME_BOUND = True
#: Five arms, each spawning at least one real interpreter, plus a ~1.0 s kill
#: window and a ~0.6 s staleness sweep. MEASURED on this node at ~5.5 s; the
#: declaration carries headroom for a loaded box.
EXPECTED_S = 15.0
ON_FAIL = "continue"
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is what the READERS do when the Scoring process stops "
    "existing. There is no state on disk to repair, and a 'correction' would "
    "mean editing the fallback while the fallback is the thing under "
    "measurement — the one path in §6.6 that keeps order flow alive when a "
    "process just died."
)
INSTALLABLE = False
#: The artifacts this gate MEASURES, for `check_artifact_gate_coverage`.
#: `scripts/nixscore/seam.py` is deliberately NOT claimed here: it is frozen and
#: `check_scoring_seam` owns it, and a second declarer would be the duplicate
#: instrument doctrine C.9 forbids.
#:
#: `scripts/nixscore/publisher.py` JOINED THIS TUPLE IN ARC 037. The order path
#: `RankingReader.arbitrate` lived in `process.py` until D3.271's collapse moved
#: it; this gate's shape scan follows it, so the file it now parses is declared.
#: `check_ranking_table` also declares `publisher.py` and that is not a duplicate
#: instrument: it measures the PUBLISH/READ transport, this measures whether the
#: order path can stall. Two properties, two gates, one file.
SUBJECTS: tuple[str, ...] = (
    "scripts/nixscore/process.py",
    "scripts/nixscore/publisher.py",
    "scripts/scoring_kill_drill.py",
)

NAME = "check_scoring_fallback"

PROCESS_MODULE = "scripts/nixscore/process.py"
DRILL_MODULE = "scripts/scoring_kill_drill.py"

#: FLOORS, all orders of magnitude below what this node measures (133k pre-kill
#: and 340k post-kill decisions, 9 snapshots), so they are floors and not a
#: restatement of today's throughput — a figure anchored to the current rate
#: would redden the day the box got slower for an unrelated reason
#: (`docs/debug.md` §7.4).
MIN_SNAPSHOTS = 3
MIN_PRE_DECISIONS = 200
MIN_PRE_RANKED = 200
MIN_POST_DECISIONS = 200
MIN_POST_FCFS = 50
MIN_CONTROL_DECISIONS = 200

#: Ceiling on the gap between two consecutive order decisions. Observed on this
#: node: ~3.3 ms, including the gap that straddles the kill. The ceiling is two
#: orders of magnitude above that and still infinitely below "halted", which is
#: the only alternative §6.6 cares about.
MAX_DECISION_GAP_S = 0.5

#: How far past the freshness threshold the FCFS transition may land. Slack for
#: a loaded scheduler, not for a broken predicate: on the AGE route the LOWER
#: bound is what catches a threshold that is not real elapsed time.
WINDOW_SLACK_S = 0.5

#: ARC 037 / sub-agent D, CHECK-DEBT D3.244. The reader now carries a SECOND
#: fallback trigger — `nixscore.liveness.PublisherLiveness`, which observes the
#: WRITER through libzmq's own peer-disconnect event instead of inferring its
#: death from the table's age. When that trigger is the one that fires, the
#: old lower bound below is not merely wrong, it FORBIDS THE REPAIR: it read
#: *"something told the reader the process had died, and §6.6's condition is
#: the TABLE's age, not the writer's liveness"*, which is §6.6:465 stated
#: backwards — the section's condition is *"the Scoring process is DOWN **or**
#: its table is STALE"*, two conditions, and the age was standing in for the
#: first. So the arm now judges against WHICH ROUTE fired, and each route keeps
#: the bound that can catch its own vacuity.
#:
#: Ceiling on the liveness route: MEASURED on this node at 3.46 ms end-to-end
#: (SIGKILL to first FCFS verdict), against ARC 036's 0.483 s on the age route.
#: Two orders of magnitude of headroom, and still two orders of magnitude below
#: `stale_after_s` — which is the property, because a liveness route that drifts
#: up to the threshold has quietly become the age route again.
MAX_LIVENESS_WINDOW_S = 0.100

#: Ceiling on decisions RANKED from a corpse's table. Zero is what this node
#: measures and zero is not the floor demanded: one arbitration can be in
#: flight in the microseconds before the monitor is drained, and a gate that
#: reddens on a scheduling accident is a gate that gets widened. ARC 036's
#: figure on the age route was 144,699.
MAX_RANKED_FROM_CORPSE = 25

#: The substring that identifies each route in the first post-kill FCFS reason.
#: Read from the REASON the shipped seam produced, not from a flag the drill
#: set: check contract §18 makes the reason the assertable artifact.
_LIVENESS_MARK = "writer not live"
_AGE_MARK = "stale"

#: Ceiling on the un-restarted reader re-acquiring the table after Scoring comes
#: back. Observed: ~30 ms via libzmq reconnect plus §12.7 snapshot-on-subscribe.
MAX_REGAIN_S = 3.0

#: Verbs that would make a scoring outage produce a deny or a stall rather than
#: FCFS — §6.6's hazard stated backwards. Not a style list: each one is a way
#: for the optimization to become the safety gate §6.6 forbids it from being.
BANNED_VERBS = ("halt", "set_halt", "flatten", "deny", "refuse_entry", "quarantine")

#: Constructs that make a delegation stop being one.
STALLING_NODES = (ast.While, ast.For, ast.AsyncFor, ast.Await, ast.Try)

_ORDER_PATH = "RankingReader.arbitrate"

#: The package the consumer-side reader lives in, and the class name. The FILE
#: is deliberately NOT named here — see `reader_module`.
READER_PACKAGE = "scripts/nixscore"
READER_CLASS = "RankingReader"


def reader_module(repo: Path) -> tuple[str, str]:
    """The ONE module in `scripts/nixscore/` defining `RankingReader`.

    DERIVED, never restated, and the derivation is itself the control.

    **ARC 036 SHIPPED TWO CLASSES OF THIS NAME IN THIS PACKAGE** — sub-agent B's
    in `publisher.py` and sub-agent C's in `process.py`, invented in parallel
    worktrees that could not see each other (CHECK-DEBT D3.271). The order path
    this gate exists to police was one of them, and a gate that names its file as
    a constant would have kept scanning the one that was NOT being called while
    `scripts/scoring_kill_drill.py` drove the other. Deriving the file makes the
    duplicate impossible to reintroduce quietly: **anything other than exactly
    one definition is an error naming every file that defines it**, which is
    D3.271's property gated rather than remembered.

    Returns `(relative_path, error)`. A non-empty error is a defect, never a
    skip: a scan that cannot find its subject has not proven the subject is fine.
    """
    package = repo / READER_PACKAGE
    if not package.is_dir():
        return "", f"{READER_PACKAGE}/ is absent — the reader has no home to scan"
    found: list[str] = []
    unreadable: list[str] = []
    for path in sorted(package.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            unreadable.append(f"{path.name}: {exc!r}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == READER_CLASS:
                found.append(f"{READER_PACKAGE}/{path.name}")
    if unreadable:
        return "", f"{READER_PACKAGE}/ did not parse: {'; '.join(unreadable)}"
    if len(found) == 1:
        return found[0], ""
    if not found:
        return "", (
            f"no class named {READER_CLASS} exists anywhere in {READER_PACKAGE}/ "
            "— the order path this gate polices has no definition to scan, and a "
            "scan over nothing proves nothing (§17)"
        )
    return "", (
        f"{len(found)} classes named {READER_CLASS} live in {READER_PACKAGE}/ "
        f"({', '.join(found)}). That is the duplicate instrument doctrine C.9 "
        "forbids, and it is measurably worse than untidy: "
        "`check_uncalled_entry_points` resolves a call site by ATTRIBUTE NAME "
        "(D3.234), so one class's callers are credited to the other and a real "
        "finding silently stops being one. CHECK-DEBT D3.271 is the record of "
        "this happening. Collapse them; do not rename one"
    )


def _load_drill() -> tuple[Any, str]:
    """Import the drill lazily. CANNOT_MEASURE when the interpreter lacks pyzmq —
    `nix-verify.service` runs `verify.py` under `/usr/bin/python3` (§17)."""
    scripts = Path(__file__).resolve().parent.parent / "scripts"
    if str(scripts) not in sys.path:
        sys.path.append(str(scripts))
    try:
        import scoring_kill_drill  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        return None, (
            f"cannot import scoring_kill_drill under {sys.executable}: {exc!r} — "
            "the subject is unreachable, and §17 makes an unobservable subject "
            "CANNOT_MEASURE, never PASS"
        )
    return scoring_kill_drill, ""


# ---------------------------------------------------------------------------
# ARM KILL + ARM CLEAN — the death was real, and it was a death
# ---------------------------------------------------------------------------


def kill_defects(kill: dict, clean: dict) -> list[tuple[str, str]]:
    """The kernel's account of the death, and the control that gives it meaning."""
    site = "os.kill(pid, SIGKILL) / subprocess.Popen.wait"
    out: list[tuple[str, str]] = []
    expected = kill.get("expected_reap_status")
    if kill.get("reap_status") != expected:
        out.append(
            (
                site,
                (
                    f"pid {kill.get('pid')} reaped {kill.get('reap_status')!r}, not "
                    f"{expected!r}. Only the kernel's reaped wait status distinguishes "
                    "a process that was KILLED from one that exited, one that failed "
                    "to start, and a flag that said 'down' (check contract §18)"
                ),
            )
        )
    if not kill.get("pid_alive_before_kill"):
        out.append(
            (site, "the pid was already gone before the signal — nothing was killed")
        )
    if not kill.get("pid_gone_after_reap"):
        out.append((site, f"/proc/{kill.get('pid')} still exists after the reap"))
    if clean.get("reap_status") != clean.get("expected_reap_status"):
        out.append(
            (
                "scoring_kill_drill:control_clean_exit",
                (
                    f"the SIGTERM control reaped {clean.get('reap_status')!r}, not "
                    f"{clean.get('expected_reap_status')!r}. Without a control that "
                    "exits cleanly through the same code path, '-SIGKILL' is a number "
                    "with nothing to be different from"
                ),
            )
        )
    if clean.get("reap_status") == kill.get("reap_status"):
        out.append(
            (
                "scoring_kill_drill:control_clean_exit",
                (
                    "the killed child and the cleanly-stopped child reaped the SAME "
                    "status, so the drill cannot tell a death from a shutdown"
                ),
            )
        )
    return out


# ---------------------------------------------------------------------------
# ARM FLOW + ARM LIVE — order flow kept deciding, and it had been ranking
# ---------------------------------------------------------------------------


def flow_defects(kill: dict) -> list[tuple[str, str]]:
    """§6.6:465: *a scoring outage must NEVER halt order flow.* Measured."""
    site = f"{PROCESS_MODULE}:{_ORDER_PATH}"
    out: list[tuple[str, str]] = []
    post = kill.get("post", {})
    if int(post.get("decisions", 0)) < MIN_POST_DECISIONS:
        out.append(
            (
                site,
                (
                    f"only {post.get('decisions')} arbitration(s) after the kill, "
                    f"below the {MIN_POST_DECISIONS} floor — 'order flow continued' "
                    "is a statement about a loop that never ran"
                ),
            )
        )
    for field, ceiling in (
        ("max_decision_gap_s", MAX_DECISION_GAP_S),
        ("gap_across_kill_s", MAX_DECISION_GAP_S),
    ):
        gap = kill.get(field)
        if gap is None or float(gap) > ceiling:
            out.append(
                (
                    site,
                    (
                        f"{field}={gap!r} against a {ceiling}s ceiling. §6.6 makes "
                        "ranking an optimization, never a safety gate: the reader "
                        "must keep deciding at the instant the writer dies"
                    ),
                )
            )
    errors = kill.get("order_path_exceptions") or []
    if errors:
        out.append(
            (
                site,
                (
                    f"the order path raised {errors!r}. An exception out of the "
                    "fallback is a stall wearing a traceback: the caller is an order "
                    "path that has to keep going"
                ),
            )
        )
    return out


def live_before_defects(kill: dict) -> list[tuple[str, str]]:
    """The ranking was LIVE before the kill, or the fallback proved nothing."""
    site = "scoring_kill_drill:kill_mid_contention[pre-kill]"
    out: list[tuple[str, str]] = []
    pre = kill.get("pre", {})
    if not kill.get("snapshot_landed"):
        out.append((site, "no ranking snapshot ever reached the reader"))
    if int(kill.get("snapshots_applied", 0)) < MIN_SNAPSHOTS:
        out.append(
            (
                site,
                (
                    f"{kill.get('snapshots_applied')} snapshot(s) applied, below the "
                    f"{MIN_SNAPSHOTS} floor — the mirror was barely fed"
                ),
            )
        )
    if int(pre.get("ranked", 0)) < MIN_PRE_RANKED:
        out.append(
            (
                site,
                (
                    f"only {pre.get('ranked')} RANKED verdict(s) before the kill, "
                    f"below the {MIN_PRE_RANKED} floor. A reader that was never "
                    "ranking cannot be shown to have fallen back"
                ),
            )
        )
    if int(pre.get("fcfs", 0)) != 0:
        out.append(
            (
                site,
                (
                    f"{pre.get('fcfs')} FCFS verdict(s) BEFORE the kill. The fallback "
                    "was already firing, so the kill changed nothing and the post-kill "
                    "FCFS is not attributable to it"
                ),
            )
        )
    age = kill.get("table_age_at_kill_s")
    stale_after = float(kill.get("stale_after_s", 0.0))
    if age is None or float(age) >= stale_after:
        out.append(
            (
                site,
                (
                    f"the table was {age!r}s old at the instant of the kill against a "
                    f"{stale_after}s threshold — it was already stale, so what "
                    "followed was not caused by the death"
                ),
            )
        )
    return out


# ---------------------------------------------------------------------------
# ARM WINDOW — the interval readers RANK on a dead process's table
# ---------------------------------------------------------------------------


def window_route(kill: dict) -> str:
    """Which fallback trigger ended the RANKED-from-a-corpse window this run.

    `"liveness"`, `"age"`, or `""` when the reason names neither — and the
    third case is a defect, not a default, because §18 makes the reason the
    thing an operator reads and a reason naming no trigger is unusable.
    """
    reason = str(kill.get("first_fcfs_reason") or "").lower()
    if _LIVENESS_MARK in reason:
        return "liveness"
    if _AGE_MARK in reason:
        return "age"
    return ""


def window_defects(kill: dict) -> list[tuple[str, str]]:
    """The FCFS transition happened, and it happened for a REASON that holds.

    Two routes, because ARC 037 gave the reader a second one. §6.6:465's
    condition is *"the Scoring process is DOWN or its table is STALE"* — two
    conditions — and each route is bounded by what can make IT vacuous:

    * **age** — bounded BELOW, because a transition faster than half the
      threshold means the threshold is not being measured against elapsed time.
    * **liveness** — bounded ABOVE, because a transition that takes as long as
      the threshold means the writer was never observed and the clock ended the
      window after all; and bounded by `MAX_RANKED_FROM_CORPSE`, which is the
      figure D3.244 exists over.

    Both are bounded above by the threshold plus slack, and both must hold a
    POPULATED table at the moment they fall back — that is what makes this the
    stale-but-PRESENT case rather than the absent-table trigger.
    """
    site = f"{PROCESS_MODULE}:RankingReader.mirror[freshness]"
    out: list[tuple[str, str]] = []
    post = kill.get("post", {})
    if int(post.get("fcfs", 0)) < MIN_POST_FCFS:
        out.append(
            (
                site,
                (
                    f"only {post.get('fcfs')} FCFS verdict(s) after the kill, below "
                    f"the {MIN_POST_FCFS} floor — the fallback did not take over"
                ),
            )
        )
    window = kill.get("frozen_table_window_s")
    stale_after = float(kill.get("stale_after_s", 0.0))
    if window is None:
        out.append((site, "the reader NEVER fell back to FCFS after Scoring died"))
        return out
    route = window_route(kill)
    if float(window) > stale_after + WINDOW_SLACK_S:
        out.append(
            (
                site,
                (
                    f"the reader kept RANKING for {float(window):.3f}s after the death, "
                    f"past the {stale_after}s threshold plus {WINDOW_SLACK_S}s slack"
                ),
            )
        )
    out += _route_defects(site, route, float(window), stale_after, kill)
    if int(kill.get("rows_held_at_first_fcfs", 0)) < 2:
        out.append(
            (
                site,
                (
                    "the mirror held fewer than both contenders' rows when it fell "
                    "back, so this measured the ABSENT-table trigger, not the "
                    "stale-but-PRESENT one that arrives when a publisher dies"
                ),
            )
        )
    return out


def _route_defects(
    site: str, route: str, window: float, stale_after: float, kill: dict
) -> list[tuple[str, str]]:
    """The bound that can catch THIS route's vacuity. See `window_defects`."""
    reason = str(kill.get("first_fcfs_reason") or "")
    if route == "":
        return [
            (
                site,
                (
                    f"the first post-kill FCFS named {reason!r} — it names neither "
                    "the writer's liveness nor the table's age, so an operator "
                    "cannot tell which of the six triggers fired (check contract "
                    "§18)"
                ),
            )
        ]
    if route == "age":
        if window < stale_after / 2:
            return [
                (
                    site,
                    (
                        f"the fallback fired {window:.3f}s after the kill, less than "
                        f"half the {stale_after}s threshold, while naming the TABLE'S "
                        "AGE as the trigger. The threshold is not being measured "
                        "against real elapsed time"
                    ),
                )
            ]
        return []
    out: list[tuple[str, str]] = []
    if window > MAX_LIVENESS_WINDOW_S:
        out.append(
            (
                site,
                (
                    f"the LIVENESS route took {window:.3f}s to fall back, over the "
                    f"{MAX_LIVENESS_WINDOW_S}s ceiling. A peer-disconnect observation "
                    f"costs milliseconds on this node; a liveness window that has "
                    f"drifted toward the {stale_after}s threshold is the age route "
                    f"wearing the liveness route's reason (CHECK-DEBT D3.244)"
                ),
            )
        )
    ranked = int(kill.get("post", {}).get("ranked", 0))
    if ranked > MAX_RANKED_FROM_CORPSE:
        out.append(
            (
                site,
                (
                    f"{ranked} arbitration(s) decided RANKED from the dead process's "
                    f"frozen table, over the {MAX_RANKED_FROM_CORPSE} ceiling. That "
                    "is D3.244 exactly: a complete, populated, confident mirror "
                    "answering from a corpse"
                ),
            )
        )
    if "peer" not in reason.lower() and "heartbeat" not in reason.lower():
        out.append(
            (
                site,
                (
                    f"the liveness FCFS reason {reason!r} does not say WHICH signal "
                    "fired. A dead process and a wedged one are different incidents "
                    "with different runbooks (check contract §18)"
                ),
            )
        )
    return out


# ---------------------------------------------------------------------------
# ARM CONTROL — the un-break half
# ---------------------------------------------------------------------------


def control_defects(no_kill: dict) -> list[tuple[str, str]]:
    """Publisher ALIVE for the same wall-clock: zero FCFS, still fresh, no alert."""
    site = "scoring_kill_drill:control_no_kill"
    out: list[tuple[str, str]] = []
    counts = no_kill.get("counts", {})
    if int(counts.get("decisions", 0)) < MIN_CONTROL_DECISIONS:
        out.append(
            (
                site,
                (
                    f"the control took {counts.get('decisions')} decision(s), below "
                    f"the {MIN_CONTROL_DECISIONS} floor — a control proves restraint "
                    "by running, not by being silent"
                ),
            )
        )
    if int(counts.get("fcfs", 0)) != 0:
        out.append(
            (
                site,
                (
                    f"{counts.get('fcfs')} FCFS verdict(s) with the publisher ALIVE. "
                    "The fallback fires without an outage, so the post-kill FCFS is "
                    "not evidence of anything the kill did"
                ),
            )
        )
    if not no_kill.get("still_fresh_at_end"):
        out.append(
            (
                site,
                (
                    "the mirror went STALE while its publisher was alive and "
                    "publishing — the freshness threshold is below the republish "
                    "period, which makes FCFS the normal mode"
                ),
            )
        )
    if list(no_kill.get("alert_codes") or []):
        out.append(
            (
                site,
                (
                    f"the §12.9 Warning fired {no_kill.get('alert_codes')!r} with "
                    "nothing wrong. An alarm that pages on a healthy system is an "
                    "alarm that gets muted"
                ),
            )
        )
    return out


# ---------------------------------------------------------------------------
# ARM STALE — a LIVE process whose table stopped moving
# ---------------------------------------------------------------------------


def stale_defects(stale: dict) -> list[tuple[str, str]]:
    """Stale-but-present, on a process that never died. The silent failure."""
    site = f"{PROCESS_MODULE}:RankingReader[stale-but-present]"
    out: list[tuple[str, str]] = []
    if not stale.get("publisher_alive_throughout"):
        out.append(
            (
                site,
                (
                    "the publisher was NOT alive through this arm, so it measured a "
                    "death again rather than a live process with a frozen table"
                ),
            )
        )
    threshold = float(stale.get("stale_after_s", 0.0))
    out += _sample_defects(
        site, stale.get("inside", {}), threshold, label="just inside"
    )
    out += _sample_defects(
        site, stale.get("outside", {}), threshold, label="just outside"
    )
    never = stale.get("never_fed", {})
    if never.get("fresh") or never.get("outcome") != "fcfs":
        out.append(
            (
                site,
                (
                    f"a mirror that has NEVER received a snapshot reported "
                    f"fresh={never.get('fresh')!r} / {never.get('outcome')!r}. §12.7: "
                    "an incomplete mirror IS stale, and §0i says stale until proven "
                    "fresh"
                ),
            )
        )
    if never.get("age_s") is not None:
        out.append((site, f"a never-fed mirror reported an age {never.get('age_s')!r}"))
    return out


def _sample_defects(
    site: str, sample: dict, threshold: float, *, label: str
) -> list[tuple[str, str]]:
    """One side of the freshness boundary, judged against the OBSERVED age.

    **The intended offset is not the subject; the measured age is.** The drill
    aims a sample 100 ms inside the threshold and another 100 ms outside it, and
    on a loaded box a sample can overshoot — three sub-agents ran `pytest`
    concurrently on this node while this gate was being built. Judging a
    verdict against the offset the drill AIMED at would then produce a red
    attributed to the scheduler, and `docs/CHECK-DEBT.md` D3.204 is the standing
    ruling that a red attributed to the scheduler is as dishonest as a green.

    So the property asserted here is the one that is true at any age: **the
    verdict follows the measured age.** Whether the two samples actually landed
    on opposite sides of the threshold is a separate question, and a separate
    answer — `boundary_unmeasurable` makes a run that failed to straddle it
    CANNOT_MEASURE rather than FAIL.
    """
    if not sample.get("measured"):
        return [(site, f"the {label} sample was not taken: {sample.get('why')!r}")]
    out: list[tuple[str, str]] = []
    age = float(sample.get("observed_age_s") or 0.0)
    want_fresh = age <= threshold
    if bool(sample.get("fresh")) is not want_fresh:
        out.append(
            (
                site,
                (
                    f"a table {age:.3f}s old under a {threshold}s threshold reported "
                    f"fresh={sample.get('fresh')!r}. A stale-but-present table read as "
                    "FRESH is the silent failure: the reader answers instantly and "
                    "confidently from a ranking that stopped updating, which is worse "
                    "than no table at all because it never falls back"
                ),
            )
        )
    expected = "ranked" if want_fresh else "fcfs"
    if sample.get("outcome") != expected:
        out.append(
            (
                site,
                (
                    f"the {label} sample arbitrated {sample.get('outcome')!r}, "
                    f"expected {expected!r} — the verdict does not follow the age"
                ),
            )
        )
    if int(sample.get("rows_held", 0)) < 2:
        out.append(
            (site, f"the {label} sample held {sample.get('rows_held')!r} rows, not 2")
        )
    return out


def boundary_unmeasurable(stale: dict) -> str:
    """Why the freshness boundary was not DRIVEN this run, or `""`.

    Separate from the defect list on purpose. If both samples land on the same
    side of the threshold, the arm did not compare a fresh reading with a stale
    one — it compared two readings — and §17 makes a property whose subject was
    not observable CANNOT_MEASURE, never PASS and never FAIL. The alternative
    was to widen the offsets until a stall could not reach them, and a tolerated
    failure is invisible where a CANNOT_MEASURE is loud (D3.204's reasoning,
    applied one arm over).
    """
    threshold = float(stale.get("stale_after_s", 0.0))
    inside = stale.get("inside", {})
    outside = stale.get("outside", {})
    if not (inside.get("measured") and outside.get("measured")):
        return ""
    low = float(inside.get("observed_age_s") or 0.0)
    high = float(outside.get("observed_age_s") or 0.0)
    if low <= threshold < high:
        return ""
    return (
        f"the two boundary samples aged {low:.3f}s and {high:.3f}s and did NOT "
        f"straddle the {threshold}s threshold, so this run compared two readings "
        "on the same side of it rather than a fresh one with a stale one. The "
        "usual cause is scheduler latency on a loaded box, not a defect — and a "
        "red attributed to the scheduler is as dishonest as a green (CHECK-DEBT "
        "D3.204), so this is CANNOT_MEASURE"
    )


# ---------------------------------------------------------------------------
# ARM ALERT + ARM RESTART
# ---------------------------------------------------------------------------


def alert_defects(kill: dict, down_code: str) -> list[tuple[str, str]]:
    """§12.9's Warning tier fired once, and carried the CAUSE."""
    site = f"{PROCESS_MODULE}:FallbackAlarm"
    codes = list(kill.get("alert_codes") or [])
    if codes != [down_code]:
        return [
            (
                site,
                (
                    f"expected exactly one {down_code!r} alert across the kill and got "
                    f"{codes!r}. §12.9 puts 'Scoring down ⇒ FCFS fallback' in the "
                    "Warning tier, and edge-triggering is why an operator gets one "
                    "page rather than a stream"
                ),
            )
        ]
    message = "".join(text for _, text in kill.get("alerts") or [])
    missing = [
        token
        for token in ("threshold", "snapshot", "age")
        if token not in message.lower()
    ]
    if missing:
        return [
            (
                site,
                (
                    f"the alert body omits {missing!r}. §12.9: alerts carry the cause "
                    "and the relevant snapshot values, not just a code"
                ),
            )
        ]
    return []


def restart_defects(
    restart: dict, down_code: str, up_code: str
) -> list[tuple[str, str]]:
    """Scoring comes back and the un-restarted reader RANKS again."""
    site = f"{PROCESS_MODULE}:RankingReader[restart]"
    out: list[tuple[str, str]] = []
    if not restart.get("rebound"):
        return [(site, f"Scoring could not restart: {restart.get('why')!r}")]
    regained = restart.get("regained_s")
    if regained is None or float(regained) > MAX_REGAIN_S:
        out.append(
            (
                site,
                (
                    f"the reader did not RANK again after Scoring restarted "
                    f"(regained_s={regained!r}, ceiling {MAX_REGAIN_S}s). It was not "
                    "restarted and not resubscribed, by design: if §12.7's "
                    "snapshot-on-subscribe does not carry it, an operator restarting "
                    "Scoring leaves every consumer on FCFS permanently and silently, "
                    "because the alarm is edge-triggered and has already fired"
                ),
            )
        )
    codes = list(restart.get("alert_codes") or [])
    if codes != [down_code, up_code]:
        out.append(
            (
                site,
                (
                    f"the alarm reported {codes!r} across a kill and a restart, "
                    f"expected {[down_code, up_code]!r}. An operator told the system "
                    "degraded and never told it recovered has to go and look, which "
                    "is what §12.9's push tier exists to avoid"
                ),
            )
        )
    return out


# ---------------------------------------------------------------------------
# ARM SHAPE — the hazard stated backwards
# ---------------------------------------------------------------------------


def shape_defects(
    source: str, module: str = PROCESS_MODULE
) -> tuple[list[tuple[str, str]], int]:
    """`arbitrate` is a pure delegation, and nothing here can HALT. (findings, scanned).

    `module` is the file the source came from, and it exists because ARC 037's
    D3.271 collapse moved `RankingReader` out of `process.py`: the scan follows
    the class rather than the filename. It defaults to `PROCESS_MODULE` so the
    can-fail plants below — which are source STRINGS with no file — keep reading
    the way they read before.
    """
    findings: list[tuple[str, str]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [(module, f"cannot parse: {exc}")], 0
    scanned = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "arbitrate"
        ):
            scanned += 1
            findings += _delegation_defects(node, module)
    findings += _banned_verb_defects(tree, module)
    return findings, scanned


def _delegation_defects(
    node: ast.AST, module: str = PROCESS_MODULE
) -> list[tuple[str, str]]:
    """Anything in `arbitrate` that makes it more than one delegation."""
    site = f"{module}:{_ORDER_PATH}"
    out: list[tuple[str, str]] = []
    for inner in ast.walk(node):
        if isinstance(inner, STALLING_NODES):
            out.append(
                (
                    site,
                    (
                        f"contains {type(inner).__name__} — the order path must answer "
                        "at the instant a process died (§6.6:465, §11:595)"
                    ),
                )
            )
        if isinstance(inner, ast.Raise):
            out.append((site, "can raise — a stall wearing a traceback"))
    return out


def _banned_verb_defects(
    tree: ast.AST, module: str = PROCESS_MODULE
) -> list[tuple[str, str]]:
    """A HALT/deny verb anywhere in the Scoring module. §6.6 stated backwards."""
    out: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in BANNED_VERBS:
            out.append(
                (
                    f"{module}:line {node.lineno}",
                    (
                        f"calls {name}() — §6.6:465 makes ranking an optimization, "
                        "NEVER a safety gate, and a scoring outage must never halt "
                        "order flow. A deny or a HALT reachable from this module is "
                        "the locked hazard stated backwards"
                    ),
                )
            )
    return out


# ---------------------------------------------------------------------------
# CAN-FAIL: every defect function driven over a DOCTORED subject
# ---------------------------------------------------------------------------

_GOOD_KILL = {
    "pid": 1,
    "reap_status": -9,
    "expected_reap_status": -9,
    "pid_alive_before_kill": True,
    "pid_gone_after_reap": True,
    "snapshot_landed": True,
    "snapshots_applied": 9,
    "stale_after_s": 0.5,
    "table_age_at_kill_s": 0.01,
    "pre": {"decisions": 9999, "ranked": 9999, "fcfs": 0},
    "post": {"decisions": 9999, "ranked": 5000, "fcfs": 4999},
    "max_decision_gap_s": 0.003,
    "gap_across_kill_s": 0.003,
    "frozen_table_window_s": 0.49,
    "first_fcfs_reason": "ranking table stale: age 0.500s exceeds ...",
    "rows_held_at_first_fcfs": 2,
    "order_path_exceptions": [],
    "alerts": [("scoring-down-fcfs", "age 0.5s threshold 0.5s 9 snapshot(s)")],
    "alert_codes": ["scoring-down-fcfs"],
}
#: The SAME run on ARC 037's liveness route: the writer is observed to die, so
#: the window collapses to disconnect latency and nothing is ranked from the
#: corpse. Both fixtures are healthy and they exercise OPPOSITE bounds, which
#: is what stops `_route_defects` from being satisfiable by one shape.
_GOOD_KILL_LIVE = {
    **_GOOD_KILL,
    "post": {"decisions": 9999, "ranked": 0, "fcfs": 9999},
    "frozen_table_window_s": 0.0035,
    "first_fcfs_reason": (
        "ranking WRITER not live [peer]: the Scoring publisher's peer is GONE — "
        "libzmq DISCONNECTED on the subscriber socket after 1 disconnect(s)"
    ),
}
_GOOD_CLEAN = {"reap_status": 7, "expected_reap_status": 7}
_GOOD_NO_KILL = {
    "counts": {"decisions": 9999, "ranked": 9999, "fcfs": 0},
    "still_fresh_at_end": True,
    "alert_codes": [],
}
_GOOD_SAMPLE_IN = {
    "measured": True,
    "observed_age_s": 0.4,
    "fresh": True,
    "rows_held": 2,
    "outcome": "ranked",
}
_GOOD_SAMPLE_OUT = {
    "measured": True,
    "observed_age_s": 0.6,
    "fresh": False,
    "rows_held": 2,
    "outcome": "fcfs",
}
_GOOD_STALE = {
    "publisher_alive_throughout": True,
    "stale_after_s": 0.5,
    "inside": _GOOD_SAMPLE_IN,
    "outside": _GOOD_SAMPLE_OUT,
    "never_fed": {"fresh": False, "age_s": None, "outcome": "fcfs"},
}
_GOOD_RESTART = {
    "rebound": True,
    "regained_s": 0.03,
    "alert_codes": ["scoring-down-fcfs", "scoring-restored-ranked"],
}

_DELEGATING = (
    "class RankingReader:\n"
    "    def arbitrate(self, first, second):\n"
    "        return self.mirror.arbitrate(first, second)\n"
)
_LOOPING = (
    "class RankingReader:\n"
    "    def arbitrate(self, first, second):\n"
    "        while not self._ready:\n"
    "            self.pump(10)\n"
    "        return self.mirror.arbitrate(first, second)\n"
)
_HALTING = (
    "class RankingReader:\n"
    "    def arbitrate(self, first, second):\n"
    "        return self.mirror.arbitrate(first, second)\n"
    "\n"
    "def on_scoring_stale(halter):\n"
    "    halter.set_halt('scoring down')\n"
)


def _with(base: dict, **overrides: Any) -> dict:
    """A copy of `base` with fields replaced. The plant, never the shipped dict."""
    return {**base, **overrides}


def _plants() -> tuple[tuple[str, list[tuple[str, str]]], ...]:
    """Every defect function, fed a doctored subject that MUST produce a finding."""
    return (
        (
            "kill/exited-not-killed",
            kill_defects(_with(_GOOD_KILL, reap_status=0), _GOOD_CLEAN),
        ),
        (
            "kill/indistinguishable-control",
            kill_defects(_GOOD_KILL, _with(_GOOD_CLEAN, reap_status=-9)),
        ),
        ("flow/halted", flow_defects(_with(_GOOD_KILL, gap_across_kill_s=10.0))),
        (
            "flow/raised",
            flow_defects(_with(_GOOD_KILL, order_path_exceptions=["boom"])),
        ),
        (
            "live/already-fcfs",
            live_before_defects(
                _with(_GOOD_KILL, pre={"decisions": 9999, "ranked": 0, "fcfs": 9999})
            ),
        ),
        (
            "window/never-fell-back",
            window_defects(_with(_GOOD_KILL, frozen_table_window_s=None)),
        ),
        (
            "window/instant-not-clock",
            window_defects(_with(_GOOD_KILL, frozen_table_window_s=0.001)),
        ),
        (
            "window/absent-not-stale",
            window_defects(_with(_GOOD_KILL, rows_held_at_first_fcfs=0)),
        ),
        (
            "window/reason-names-no-trigger",
            window_defects(_with(_GOOD_KILL, first_fcfs_reason="the fallback ran")),
        ),
        (
            "liveness/window-drifted-to-the-clock",
            window_defects(_with(_GOOD_KILL_LIVE, frozen_table_window_s=0.45)),
        ),
        (
            "liveness/ranked-from-a-corpse",
            window_defects(
                _with(
                    _GOOD_KILL_LIVE,
                    post={"decisions": 144699, "ranked": 144699, "fcfs": 9999},
                )
            ),
        ),
        (
            "liveness/reason-names-no-signal",
            window_defects(
                _with(
                    _GOOD_KILL_LIVE,
                    first_fcfs_reason="ranking WRITER not live: it is not live",
                )
            ),
        ),
        (
            "control/fcfs-while-healthy",
            control_defects(
                _with(
                    _GOOD_NO_KILL, counts={"decisions": 9999, "ranked": 0, "fcfs": 9999}
                )
            ),
        ),
        (
            "stale/read-fresh-when-old",
            stale_defects(
                _with(
                    _GOOD_STALE,
                    outside=_with(_GOOD_SAMPLE_OUT, fresh=True, outcome="ranked"),
                )
            ),
        ),
        (
            "stale/died-instead-of-aged",
            stale_defects(_with(_GOOD_STALE, publisher_alive_throughout=False)),
        ),
        (
            "alert/silent",
            alert_defects(_with(_GOOD_KILL, alert_codes=[]), "scoring-down-fcfs"),
        ),
        (
            "alert/no-cause",
            alert_defects(
                _with(_GOOD_KILL, alerts=[("scoring-down-fcfs", "scoring is down")]),
                "scoring-down-fcfs",
            ),
        ),
        (
            "restart/wedged",
            restart_defects(
                _with(_GOOD_RESTART, regained_s=None),
                "scoring-down-fcfs",
                "scoring-restored-ranked",
            ),
        ),
        ("shape/looping-order-path", shape_defects(_LOOPING)[0]),
        ("shape/halt-on-outage", shape_defects(_HALTING)[0]),
        (
            "boundary/not-straddled",
            _as_findings(
                boundary_unmeasurable(
                    _with(
                        _GOOD_STALE,
                        outside=_with(_GOOD_SAMPLE_OUT, observed_age_s=0.45),
                    )
                )
            ),
        ),
    )


def _as_findings(reason: str) -> list[tuple[str, str]]:
    """A CANNOT_MEASURE reason, in the shape the can-fail battery reads."""
    return [(f"{NAME}:boundary", reason)] if reason else []


def _reader_module_arm() -> tuple[str, str]:
    """CAN-FAIL for the DERIVATION itself — plant a duplicate and a vacuum.

    `reader_module` is the arm that decides WHICH file the order-path scan reads,
    so a `reader_module` that cannot see a duplicate would send this gate to
    scan one of two classes and call it the order path — which is exactly the
    state ARC 036 shipped (D3.271). Three drives, in a throwaway package:

      1. ONE definition resolves to that file and returns no error (the arm can
         return clean, so its errors carry information).
      2. TWO definitions produce an error that NAMES BOTH FILES — not "a
         duplicate exists" (check contract §18: assert the REASON).
      3. ZERO definitions produce an error, so a vacuum is never a pass.
    """
    with tempfile.TemporaryDirectory(prefix="nixscoredup") as tmp:
        pkg = Path(tmp) / READER_PACKAGE
        pkg.mkdir(parents=True)
        body = f"class {READER_CLASS}:\n    pass\n"
        (pkg / "publisher.py").write_text(body, encoding="utf-8")
        one, error = reader_module(Path(tmp))
        if error or one != f"{READER_PACKAGE}/publisher.py":
            return "reader-module/false-positive", (
                f"a package holding ONE {READER_CLASS} resolved to {one!r} with "
                f"error {error!r} — the derivation cannot return clean"
            )
        (pkg / "process.py").write_text(body, encoding="utf-8")
        _two, dup = reader_module(Path(tmp))
        if not dup or "process.py" not in dup or "publisher.py" not in dup:
            return "reader-module/duplicate-blind", (
                f"two {READER_CLASS} classes in one package produced {dup!r} — "
                "the duplicate D3.271 records is invisible, or is reported "
                "without naming both files"
            )
        (pkg / "publisher.py").unlink()
        (pkg / "process.py").unlink()
        _none, absent = reader_module(Path(tmp))
        if not absent:
            return "reader-module/vacuum-blind", (
                "a package with NO reader class produced no error — a scan with "
                "no subject would be reported as a clean order path"
            )
    return "", ""


def _arms_can_fail() -> tuple[str, str]:
    """The first arm that cannot demonstrate its defect, or ("", "")."""
    blind, why = _reader_module_arm()
    if blind:
        return blind, why
    for label, findings in _plants():
        if not findings:
            return label, (
                f"the {label} plant produced NO finding — that arm cannot see the "
                "defect it exists to see, so its silence is blind, not green"
            )
    clean_findings, scanned = shape_defects(_DELEGATING)
    if scanned != 1 or clean_findings:
        return "shape/false-positive", (
            f"a pure delegation was reported as a defect ({clean_findings!r}) over "
            f"{scanned} scanned function(s) — the arm flags everything, which is "
            "the same blindness pointed the other way"
        )
    for label, findings in (
        ("kill", kill_defects(_GOOD_KILL, _GOOD_CLEAN)),
        ("flow", flow_defects(_GOOD_KILL)),
        ("live", live_before_defects(_GOOD_KILL)),
        ("window", window_defects(_GOOD_KILL)),
        ("window-liveness", window_defects(_GOOD_KILL_LIVE)),
        ("control", control_defects(_GOOD_NO_KILL)),
        ("stale", stale_defects(_GOOD_STALE)),
        ("boundary", _as_findings(boundary_unmeasurable(_GOOD_STALE))),
        ("alert", alert_defects(_GOOD_KILL, "scoring-down-fcfs")),
        (
            "restart",
            restart_defects(
                _GOOD_RESTART, "scoring-down-fcfs", "scoring-restored-ranked"
            ),
        ),
    ):
        if findings:
            return f"{label}/false-positive", (
                f"a healthy {label} outcome produced {findings!r} — the arm cannot "
                "return clean, so its findings carry no information"
            )
    return "", ""


# ---------------------------------------------------------------------------


def _num(value: Any, scale: float = 1.0, unit: str = "s") -> str:
    """A measured number, or `n/a` — **never a crash**.

    MEASURED, ARC 036 sub-agent C: the first version of this formatter used
    plain f-string float formatting, and the staged both-halves test — a mirror
    widened so it can never go stale — turned the gate's own headline FAIL into
    `CANNOT_MEASURE: TypeError`. Every optional field here is `None` in exactly
    the case the gate exists to report, so a renderer that cannot print `None`
    is a renderer that masks the defect (§17: masking is the failure, and the
    verdict after it is not the one that was measured).
    """
    if value is None:
        return "n/a"
    return f"{float(value) * scale:.3f}{unit}"


def _evidence(outcome: dict, scanned: int) -> str:
    """What WAS measured, attached to the PASS and to the FAIL alike."""
    kill = outcome["kill"]
    stale = outcome["stale"]
    return (
        f"nonce {outcome['nonce']}: pid {kill['pid']} SIGKILLed mid-contention and "
        f"reaped {kill['reap_status']} (/proc gone={kill['pid_gone_after_reap']}), "
        f"against a SIGTERM control reaping {outcome['clean']['reap_status']}; "
        f"{kill['pre']['ranked']} RANKED decisions before the kill and "
        f"{kill['post']['decisions']} after it, worst inter-decision gap "
        f"{_num(kill['max_decision_gap_s'], 1000, 'ms')} (across-kill "
        f"{_num(kill['gap_across_kill_s'], 1000, 'ms')}) with "
        f"{len(kill['order_path_exceptions'])} order-path exception(s); "
        f"{kill['post']['ranked']} decisions RANKED from the dead process's frozen "
        f"table over a {_num(kill['frozen_table_window_s'])} window before FCFS "
        f"took over via the {window_route(kill) or 'UNNAMED'} route (ARC 036, age "
        f"route only: 144,699 over 0.483s at the same 0.5s threshold — CHECK-DEBT "
        f"D3.244); the live-publisher control took "
        f"{outcome['no_kill']['counts']['decisions']} decisions with "
        f"{outcome['no_kill']['counts']['fcfs']} FCFS; a LIVE publisher's frozen "
        f"table read fresh at {_num(stale['inside'].get('observed_age_s'))} and "
        f"stale at {_num(stale['outside'].get('observed_age_s'))} against "
        f"{stale['stale_after_s']}s with both contenders' rows present; the "
        f"un-restarted reader RANKED again "
        f"{_num(outcome['restart'].get('regained_s'))} after Scoring relaunched; "
        f"{scanned} `arbitrate` definition(s) scanned; all "
        f"{len(_plants())} defect arms proved they can fail on planted subjects "
        f"this run"
    )


def _measure(drill: Any, root: Path) -> tuple[list[tuple[str, str]], dict, int]:
    """Run the drill once and judge it. Returns (defects, outcome, scanned)."""
    outcome = drill.run_drill(root)
    repo = Path(__file__).resolve().parent.parent
    # WHERE THE ORDER PATH LIVES IS DERIVED, NOT NAMED (ARC 037 / D3.271). A
    # second class of the same name in the package is itself a defect, and the
    # shape scan then has nothing it can honestly scan.
    reader_rel, reader_error = reader_module(repo)
    shape: list[tuple[str, str]] = []
    scanned = 0
    if reader_error:
        shape.append((f"{READER_PACKAGE}:{READER_CLASS}", reader_error))
    else:
        shape, scanned = shape_defects(
            (repo / reader_rel).read_text(encoding="utf-8"), reader_rel
        )
    # The banned-verb sweep stays over the SCORING PROCESS module as well: §6.6's
    # hazard is a HALT reachable from the scoring side, and that is true whether
    # or not the reader still lives in the same file.
    process_source = (repo / PROCESS_MODULE).read_text(encoding="utf-8")
    try:
        shape += _banned_verb_defects(ast.parse(process_source), PROCESS_MODULE)
    except SyntaxError as exc:
        shape.append((PROCESS_MODULE, f"cannot parse: {exc}"))
    down = drill.SCORING_DOWN_CODE
    up = "scoring-restored-ranked"
    defects = (
        kill_defects(outcome["kill"], outcome["clean"])
        + flow_defects(outcome["kill"])
        + live_before_defects(outcome["kill"])
        + window_defects(outcome["kill"])
        + control_defects(outcome["no_kill"])
        + stale_defects(outcome["stale"])
        + alert_defects(outcome["kill"], down)
        + restart_defects(outcome["restart"], down, up)
        + shape
    )
    if scanned != 1:
        defects.append(
            (
                f"{NAME}:non-vacuity",
                (
                    f"the shape scan found {scanned} `arbitrate` definition(s) in "
                    f"{reader_rel or READER_PACKAGE}, expected 1 — a scan over "
                    "nothing cannot report an order path that stalls"
                ),
            )
        )
    return defects, outcome, scanned


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Measure it. See the module docstring for what, and for §0a."""
    try:
        blind, why = _arms_can_fail()
        if blind:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site=f"{NAME}:{blind}",
                detail=f"the {blind} arm cannot fail: {why}",
            )
        drill, error = _load_drill()
        if drill is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        with tempfile.TemporaryDirectory(prefix="nixscoregate") as tmp:
            defects, outcome, scanned = _measure(drill, Path(tmp))
        # §17 BEFORE the verdict: if the freshness boundary was not straddled,
        # the stale-but-present property had no observable subject this run, and
        # an unobservable subject is CANNOT_MEASURE — never PASS, and never a
        # FAIL the scheduler earned.
        unmeasurable = boundary_unmeasurable(outcome["stale"])
        if unmeasurable:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site=f"{NAME}:boundary",
                evidence=_evidence(outcome, scanned),
                detail=unmeasurable,
            )
        return result_from_defects(NAME, defects, _evidence(outcome, scanned))
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
