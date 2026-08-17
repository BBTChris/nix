#!/usr/bin/env python3
"""The §6.6 Scoring seam holds: readers look up, the fallback answers, one writer.

Three properties, and each is gated because each has a way of failing that
leaves every other gate green.

## 1. READERS LOOK UP, THEY NEVER COMPUTE

§6.6: *"Nobody but the Scoring process COMPUTES the score … Both hot paths do an
O(1) table lookup, never math."* §11:595 says the same one layer up. A reader
that recomputes an EMA is correct — it produces the right number — and is a
hot-path violation that no output check can see, because the output is
identical. It is only visible in the SHAPE of the read path, so that is what is
measured: the AST of `RankingMirror.lookup` and `RankingMirror.arbitrate`, plus
every consumer that calls them.

## 2. THE FALLBACK ANSWERS, IT NEVER STALLS

§6.6: *"a scoring outage must NEVER halt order flow."* The dangerous failure is
not "FCFS was wrong", it is "the reader waited". A gate that only asserts the
FCFS *verdict* would pass over an `arbitrate` that blocks for two seconds on a
socket before returning the right answer — and it would pass in a suite where
Scoring is never actually down.

So both halves are measured: the RETURN VALUE under each of the five documented
triggers, and the SHAPE (no `raise`, no loop, no sleep, no I/O on the
arbitration path) — and the gate proves its own timing arm can fail by driving
a deliberately stalling reader through it.

## 3. ONE WRITER, ENFORCED WHERE AN IMPOSTOR WOULD ARRIVE

§6.6 makes Scoring the sole writer. A publisher-side assertion is the wrong
place for it: a second process binding the same endpoint never consults the
first publisher's code. The check that matters is at the CONSUMER, so the gate
drives a foreign-identity snapshot into a mirror and requires it to be rejected
AND counted — a silent drop would be indistinguishable from a message that
never arrived.

## Non-vacuity

Every arm carries its own plant, driven in-process on a COPY of the shipped
behaviour, never on the shipped module (doctrine C.8). An arm that cannot show
itself reddening is reported as blind rather than as green.
"""

# pylint: disable=duplicate-code
# R0801 pairs this module's §4.4 declaration preamble with every other check.
# THE DUPLICATION CANNOT BE FACTORED OUT AND THAT IS THE DESIGN: `PRIVILEGE`,
# `DEPENDS_ON`, `RESOURCES` and the rest are read STATICALLY, by AST, without
# importing the check (check contract §4.4), so a shared base module would be
# invisible to that reader.
from __future__ import annotations

import ast
import dataclasses
import inspect
import sys
import time
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: Nothing must run first. This gate imports the seam and drives it in-process.
DEPENDS_ON: tuple[str, ...] = ()
#: Nothing outside this process. The seam is driven with no transport: the
#: publisher is injected, so no socket, no port, no file is touched.
#: `check_observed_resource_claims` reports on this file like any other, and if
#: the observer sees more, the observer is right (§17) — that is exactly how
#: `check_git_env_scrub`'s own declaration was corrected this arc.
RESOURCES: tuple[str, ...] = ()
#: The artifacts this gate MEASURES, for `check_artifact_gate_coverage`.
#: `seam.py` is parsed AND driven here; `__init__.py` is named because importing
#: `nixscore.seam` executes it, so a defect in it is a defect this gate would
#: hit — which is the honest ground for the claim, and the only one.
SUBJECTS: tuple[str, ...] = (
    "scripts/nixscore/seam.py",
    "scripts/nixscore/__init__.py",
)
#: FALSE on the facts: an AST parse of one module and a few hundred in-process
#: calls.
TIME_BOUND = False
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "Every finding here is a design defect in the read path — a reader that "
    "computes, a fallback that can block, a mirror that accepts a foreign "
    "writer. There is no mechanical edit that repairs any of them without "
    "deciding what the code was FOR, and an automated rewrite of the "
    "arbitration path is an automated rewrite of the thing that keeps order "
    "flow alive when Scoring dies. A human edits it."
)
INSTALLABLE = False
ON_FAIL = "continue"

NAME = "check_scoring_seam"

SEAM_MODULE = "scripts/nixscore/seam.py"

#: Tokens that mean "this function is doing the Scoring process's job". Not a
#: style list — each is a way of computing a score on a read path.
#:
#: `rank_rows` is included deliberately: it is the seam's OWN ranking function
#: and it is legitimate exactly once, inside the Scoring process, before
#: `publish`. A reader calling it is a reader computing the ranking.
BANNED_ON_READ_PATH = (
    "exp",
    "log",
    "pow",
    "mean",
    "ema",
    "smooth",
    "alpha",
    "rank_rows",
    "sum",
    "sorted",
    "statistics",
)

#: Constructs that can make a read path take unbounded time. §6.6's fallback
#: must answer at the instant a process just died.
STALLING_NODES = (ast.While, ast.AsyncFor, ast.Await, ast.Try)

#: The read-path functions, by qualified name. DERIVED from the seam module's
#: own class rather than listed as strings alone: a rename that orphans this
#: list must be a loud miss, not a silently-empty scan.
READ_PATH = ("lookup", "arbitrate", "fresh", "age_s")

#: Wall-clock ceiling for one arbitration, in seconds. Generously above any
#: dict lookup and far below anything that touched a socket. A figure this
#: gate MEASURES against, not one it asserts is met.
ARBITRATION_BUDGET_S = 0.01

#: How many arbitrations the timing arm drives. One call can be unlucky under
#: load; the arm reports the WORST, so a single stall cannot average away.
TIMING_DRIVES = 200


@dataclasses.dataclass(frozen=True)
class Finding:
    """One defect, anchored to the site that carries it and the reason (§18)."""

    site: str
    why: str


def pytest_approx(expected: float, tol: float = 1e-6):
    """A float comparison a check can make without importing pytest.

    A check is a standalone executable (§4.2) and must not depend on the test
    runner. Named for what it does rather than borrowed from where the idea
    came from.
    """

    class _Near:
        def __eq__(self, other: object) -> bool:
            return isinstance(other, (int, float)) and abs(other - expected) <= tol

        def __repr__(self) -> str:  # pragma: no cover - diagnostics only
            return f"~{expected}"

    return _Near()


def _load_seam(home: Path):
    """Import the seam from `home`, or return (None, error)."""
    scripts = str(home / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    try:
        from nixscore import seam  # pylint: disable=import-outside-toplevel

        return seam, ""
    except ImportError as exc:
        return None, f"cannot import nixscore.seam from {scripts}: {exc!r}"


# ---------------------------------------------------------------------------
# ARM 1 — the read path does not compute
# ---------------------------------------------------------------------------


def read_path_defects(source: str) -> tuple[list[Finding], int]:
    """Banned computation on the seam's read path. Returns (findings, scanned).

    Exported so the plant arm can drive it over a source it authored, which is
    how this arm's can-fail binding is re-established every run rather than
    recorded.
    """
    findings: list[Finding] = []
    scanned = 0
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [Finding(SEAM_MODULE, f"cannot parse: {exc}")], 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in READ_PATH:
            continue
        scanned += 1
        site = f"{SEAM_MODULE}:{node.name}"
        for inner in ast.walk(node):
            findings += _read_path_defect(site, inner)
    return findings, scanned


def _read_path_defect(site: str, inner: ast.AST) -> list[Finding]:
    """One node's verdict on the read path, or nothing."""
    if isinstance(inner, ast.Call):
        name = _called_name(inner)
        if name and name.split(".")[-1] in BANNED_ON_READ_PATH:
            return [
                Finding(
                    site,
                    f"calls {name}() on the hot read path. §6.6: the Allocator "
                    "and Limiter do an O(1) table lookup, NEVER math — "
                    "computing the score is the allocation judgment that stays "
                    "out of the gate",
                )
            ]
        return []
    if isinstance(inner, (ast.For, ast.comprehension)):
        return [
            Finding(
                site,
                "iterates on the hot read path. A scan over the ranking table "
                "is O(n) where §6.6 and §11:595 require O(1)",
            )
        ]
    if isinstance(inner, ast.BinOp) and isinstance(
        inner.op, (ast.Mult, ast.Div, ast.Pow)
    ):
        return [
            Finding(
                site,
                f"performs {type(inner.op).__name__} arithmetic on the hot read "
                "path — the shape of an EMA being recomputed by a reader (§11 "
                "hot-path violation)",
            )
        ]
    return []


def _called_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def stalling_defects(source: str) -> tuple[list[Finding], int]:
    """Constructs on the arbitration path that could take unbounded time."""
    findings: list[Finding] = []
    scanned = 0
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [Finding(SEAM_MODULE, f"cannot parse: {exc}")], 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "arbitrate":
            continue
        scanned += 1
        site = f"{SEAM_MODULE}:arbitrate"
        for inner in ast.walk(node):
            findings += _stalling_defect(site, inner)
    return findings, scanned


def _stalling_defect(site: str, inner: ast.AST) -> list[Finding]:
    """One node's verdict on the arbitration path, or nothing."""
    if isinstance(inner, STALLING_NODES):
        return [
            Finding(
                site,
                f"contains {type(inner).__name__} — the fallback must answer at "
                "the instant a process died. §6.6: ranking is an optimization, "
                "never a safety gate; a scoring outage must NEVER halt order flow",
            )
        ]
    if isinstance(inner, ast.Raise):
        return [
            Finding(
                site,
                "can raise. An exception out of the arbitration path is a stall "
                "wearing a traceback: the caller is an order path that has to "
                "keep going",
            )
        ]
    if isinstance(inner, ast.Call):
        name = _called_name(inner) or ""
        if name in ("sleep", "recv", "send", "poll", "read", "connect"):
            return [Finding(site, f"calls {name}() — I/O on the fallback path")]
    return []


# ---------------------------------------------------------------------------
# ARM 2 — the fallback is DRIVEN, under every documented trigger
# ---------------------------------------------------------------------------


def _snapshot(seam, pairs: dict, span: int = 10, identity: str | None = None):
    rows = seam.rank_rows(pairs)
    return seam.RankingSnapshot(
        rows=rows,
        span_days=span,
        writer_identity=identity or seam.SCORING_WRITER_IDENTITY,
    )


def _feed(seam, mirror, snapshot, now: float, seq: int = 1) -> bool:
    from nixbus.statebus import StateMessage  # pylint: disable=import-outside-toplevel

    return mirror.apply(
        StateMessage(
            topic=seam.RANKING_TOPIC,
            payload=snapshot.as_wire(),
            seq=seq,
            stamp=now,
            snapshot=True,
        ),
        now=now,
    )


def drive_fallback(seam) -> list[Finding]:
    """Every FCFS trigger, driven. The verdict AND the fact that it returned."""
    findings: list[Finding] = []
    first, second = ("s1", "ES"), ("s2", "ES")

    # 1 — never fed. §12.7: an incomplete mirror IS stale.
    cold = seam.RankingMirror(stale_after_s=5.0)
    findings += _expect_fcfs(cold, first, second, 100.0, "never-fed mirror")

    # 2 — genuinely stale, by the CLOCK, not by a flag. The table is real, is
    #     present, and is old; a stale-but-present table read as fresh is the
    #     silent failure this trigger exists for.
    stale = seam.RankingMirror(stale_after_s=5.0)
    _feed(seam, stale, _snapshot(seam, {first: 900.0, second: 100.0}), now=100.0)
    findings += _expect_fcfs(stale, first, second, 100.0 + 5.001, "stale table")

    # THE FRESHNESS PREDICATE ITSELF, DRIVEN FROM BOTH SIDES OF THE BOUNDARY.
    #
    # ADDED BECAUSE A PLANT CAUGHT THIS GATE BLIND. `arbitrate` computes the age
    # inline, so a `fresh()` rewritten to `return self._applied_at is not None`
    # — a mirror that calls a dead table fresh forever — left every arm above
    # green. `fresh()` is not decoration: it is the predicate the Allocator and
    # Limiter read for §12.7's fast-drop, and §0i says a mirror is stale until
    # PROVEN fresh. A predicate that can only say "yes" proves nothing.
    #
    # Three points, because one is an arithmetic identity: just inside, just
    # outside, and never-fed. The middle of the range is the one place a broken
    # predicate and a correct one agree.
    if not stale.fresh(now=100.0 + 4.999):
        findings.append(
            Finding(
                f"{SEAM_MODULE}:fresh",
                "a table 4.999s old under a 5s threshold reported STALE — the "
                "threshold is not being measured against real elapsed time, so "
                "the fallback would fire on a healthy table",
            )
        )
    if stale.fresh(now=100.0 + 5.001):
        findings.append(
            Finding(
                f"{SEAM_MODULE}:fresh",
                "a table 5.001s old under a 5s threshold reported FRESH. A "
                "stale-but-present table read as fresh is the silent failure: "
                "the reader answers instantly and confidently from a ranking "
                "that stopped being updated when Scoring died, which is worse "
                "than no table at all because it never falls back (§12.7)",
            )
        )
    if seam.RankingMirror(stale_after_s=5.0).fresh(now=100.0):
        findings.append(
            Finding(
                f"{SEAM_MODULE}:fresh",
                "a mirror that has NEVER received a snapshot reported FRESH. "
                "§0i and §12.7: a mirror is stale until proven fresh, and an "
                "incomplete mirror IS stale",
            )
        )
    if stale.age_s(now=100.0 + 3.0) != pytest_approx(3.0):
        findings.append(
            Finding(
                f"{SEAM_MODULE}:age_s",
                f"a table fed at t=100 reported age {stale.age_s(now=103.0)!r} at "
                "t=103. The freshness threshold is compared against this number, "
                "so an age that is not elapsed time makes the whole staleness "
                "test a proxy",
            )
        )

    # 3 — a contender with no row at all (cold start, no realized history).
    partial = seam.RankingMirror(stale_after_s=5.0)
    _feed(seam, partial, _snapshot(seam, {first: 900.0}), now=100.0)
    findings += _expect_fcfs(partial, first, second, 100.5, "absent pair-row")

    # 4 — equal EMAs. §6.6: "Equal or absent scores => FCFS."
    tied = seam.RankingMirror(stale_after_s=5.0)
    _feed(seam, tied, _snapshot(seam, {first: 500.0, second: 500.0}), now=100.0)
    findings += _expect_fcfs(tied, first, second, 100.5, "equal realized EMA")

    # 5 — a foreign writer's snapshot never becomes the table.
    foreign = seam.RankingMirror(stale_after_s=5.0)
    accepted = _feed(
        seam,
        foreign,
        _snapshot(seam, {first: 900.0, second: 1.0}, identity="impostor"),
        now=100.0,
    )
    if accepted:
        findings.append(
            Finding(
                f"{SEAM_MODULE}:RankingMirror.apply",
                "a snapshot stamped by an identity that is NOT the Scoring "
                "process was ACCEPTED into the mirror. §6.6 makes Scoring the "
                "sole writer, and the consumer is the only place an impostor "
                "publisher can be refused",
            )
        )
    if foreign.foreign_rejected != 1:
        findings.append(
            Finding(
                f"{SEAM_MODULE}:RankingMirror.foreign_rejected",
                f"a foreign snapshot was dropped without being COUNTED "
                f"(foreign_rejected={foreign.foreign_rejected}). A silent drop "
                "is indistinguishable from a message that never arrived",
            )
        )
    findings += _expect_fcfs(foreign, first, second, 100.5, "foreign writer refused")

    # And the positive half: a fresh, complete, honestly-written table RANKS.
    live = seam.RankingMirror(stale_after_s=5.0)
    _feed(seam, live, _snapshot(seam, {first: 900.0, second: 100.0}), now=100.0)
    verdict = live.arbitrate(first, second, now=100.5)
    if verdict.outcome is not seam.Arbitration.RANKED or verdict.winner != first:
        findings.append(
            Finding(
                f"{SEAM_MODULE}:arbitrate",
                f"a fresh table with unequal EMAs did not RANK: got "
                f"{verdict.outcome}/{verdict.winner}. Without this half the "
                "gate would pass a seam that answers FCFS to everything",
            )
        )
    # THE FLIP. Ranking that never changes an outcome is not a ranking.
    flipped = seam.RankingMirror(stale_after_s=5.0)
    _feed(seam, flipped, _snapshot(seam, {first: 100.0, second: 900.0}), now=100.0)
    flip = flipped.arbitrate(first, second, now=100.5)
    if flip.winner != second:
        findings.append(
            Finding(
                f"{SEAM_MODULE}:arbitrate",
                f"reversing the two pairs' realized EMAs did NOT reverse the "
                f"winner (still {flip.winner}) — the verdict is not a function "
                "of the table",
            )
        )
    return findings


def _expect_fcfs(mirror, first, second, now: float, label: str) -> list[Finding]:
    """One trigger: it must RETURN, must be FCFS, must name a reason."""
    started = time.perf_counter()
    verdict = mirror.arbitrate(first, second, now=now)
    elapsed = time.perf_counter() - started
    site = f"{SEAM_MODULE}:arbitrate[{label}]"
    out: list[Finding] = []
    if str(verdict.outcome) != "fcfs":
        out.append(
            Finding(
                site,
                f"expected the FCFS fallback and got {verdict.outcome!r}. "
                "§6.6 locks the fallback: ranking is an optimization, never a "
                "safety gate",
            )
        )
    if verdict.winner != first:
        out.append(
            Finding(
                site,
                f"FCFS named {verdict.winner!r} the winner, not the earlier "
                f"arrival {first!r}. First-come-first-served IS the arrival "
                "order; anything else is a preference wearing the fallback's name",
            )
        )
    if not verdict.reason.strip():
        out.append(
            Finding(
                site,
                "the fallback fired with no reason. Five different conditions "
                "reach FCFS and an operator cannot tell them apart from the "
                "outcome alone (check contract §18)",
            )
        )
    if elapsed > ARBITRATION_BUDGET_S:
        out.append(
            Finding(
                site,
                f"took {elapsed * 1000:.3f}ms, over the {ARBITRATION_BUDGET_S * 1000:.1f}ms "
                "budget. A fallback that waits has not fallen back",
            )
        )
    return out


def worst_arbitration_s(mirror, first, second, drives: int = TIMING_DRIVES) -> float:
    """The WORST single arbitration over `drives` calls, never the mean.

    A mean hides exactly the event that matters: one call in two hundred that
    blocked. Exported so the plant arm can drive a deliberately stalling reader
    through the same measurement.
    """
    worst = 0.0
    for index in range(drives):
        started = time.perf_counter()
        mirror.arbitrate(first, second, now=100.0 + index * 1e-6)
        worst = max(worst, time.perf_counter() - started)
    return worst


def timing_arm_can_fail() -> tuple[bool, str]:
    """Drive a deliberately stalling reader and require the arm to catch it."""

    class _Stalling:  # pylint: disable=too-few-public-methods
        """A reader with the right answer and the wrong latency."""

        def arbitrate(self, first, second, now=None):
            """Sleep, then answer. The verdict is fine; the latency is not."""
            # pylint: disable=unused-argument
            time.sleep(ARBITRATION_BUDGET_S * 3)

    worst = worst_arbitration_s(_Stalling(), ("a", "b"), ("c", "d"), drives=2)
    if worst <= ARBITRATION_BUDGET_S:
        return False, (
            f"a reader sleeping {ARBITRATION_BUDGET_S * 3:.4f}s per call measured "
            f"{worst:.6f}s worst-case — the timing arm cannot see a stall, so "
            "its silence is blind, not green"
        )
    return True, ""


def read_path_arm_can_fail() -> tuple[bool, str]:
    """Drive the AST arm over a reader that computes, and require a finding."""
    computing = (
        "class RankingMirror:\n"
        "    def lookup(self, strategy_id, symbol):\n"
        "        rows = self._rows\n"
        "        return sum(r.realized_ema for r in rows.values()) / len(rows)\n"
    )
    findings, scanned = read_path_defects(computing)
    if scanned != 1:
        return False, f"the read-path arm scanned {scanned} function(s), expected 1"
    if not findings:
        return False, (
            "a reader that sums and divides the whole ranking table produced NO "
            "finding — the read-path arm cannot see a computing reader, so its "
            "silence is blind, not green"
        )
    clean, clean_scanned = read_path_defects(
        "class RankingMirror:\n"
        "    def lookup(self, strategy_id, symbol):\n"
        "        return self._rows.get((strategy_id, symbol))\n"
    )
    if clean_scanned != 1 or clean:
        return False, (
            "a plain dict lookup was reported as computing "
            f"({[f.why for f in clean]}) — the arm flags everything, which is "
            "the same blindness pointed the other way"
        )
    return True, ""


def stalling_arm_can_fail() -> tuple[bool, str]:
    """Drive the shape arm over an arbitration that loops, and require a finding."""
    looping = (
        "class RankingMirror:\n"
        "    def arbitrate(self, first, second, now=None):\n"
        "        while not self._ready:\n"
        "            pass\n"
        "        return None\n"
    )
    findings, scanned = stalling_defects(looping)
    if scanned != 1 or not findings:
        return False, (
            f"an arbitration spinning on `while` produced {len(findings)} "
            f"finding(s) over {scanned} scanned function(s) — the shape arm "
            "cannot see a stall it can read, so its silence is blind"
        )
    return True, ""


# ---------------------------------------------------------------------------


def _arms_can_fail() -> tuple[str, str]:
    """The first arm that cannot demonstrate a defect, or ("", "")."""
    for label, control in (
        ("read-path", read_path_arm_can_fail),
        ("shape", stalling_arm_can_fail),
        ("timing", timing_arm_can_fail),
    ):
        ok, why = control()
        if not ok:
            return label, why
    return "", ""


def _writable_surface(mirror_class) -> list[str]:
    """Public verbs on the mirror beyond the read contract. §12.7."""
    allowed = {"apply", "lookup", "arbitrate", "fresh", "age_s"}
    return sorted(
        name
        for name, member in inspect.getmembers(mirror_class)
        if not name.startswith("_") and callable(member) and name not in allowed
    )


def _static_defects(source: str) -> tuple[list[Finding], int, int]:
    """The two AST scans plus their own non-vacuity floors."""
    compute_findings, read_scanned = read_path_defects(source)
    shape_findings, shape_scanned = stalling_defects(source)
    findings = compute_findings + shape_findings
    if read_scanned < len(READ_PATH):
        findings.append(
            Finding(
                f"{NAME}:non-vacuity",
                f"the read-path scan found {read_scanned} of the "
                f"{len(READ_PATH)} functions it judges ({', '.join(READ_PATH)}) "
                f"in {SEAM_MODULE} — a scan over nothing cannot report a "
                "computing reader",
            )
        )
    if shape_scanned != 1:
        findings.append(
            Finding(
                f"{NAME}:non-vacuity",
                f"the arbitration-shape scan found {shape_scanned} `arbitrate` "
                f"definitions in {SEAM_MODULE}, expected 1",
            )
        )
    return findings, read_scanned, shape_scanned


def run(  # pylint: disable=unused-argument,too-many-locals
    mode: Mode, ctx: Context
) -> CheckResult:
    """Measure it. See the module docstring for what and why."""
    try:
        home = ctx.nix_home
        blind, why = _arms_can_fail()
        if blind:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site=f"{NAME}:{blind}-arm",
                detail=f"the {blind} arm cannot fail: {why}",
            )

        seam, error = _load_seam(home)
        if seam is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        try:
            source = (home / SEAM_MODULE).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                detail=f"cannot read {SEAM_MODULE}: {exc!r}",
            )

        findings, read_scanned, shape_scanned = _static_defects(source)
        findings += drive_fallback(seam)

        writable = _writable_surface(seam.RankingMirror)
        if writable:
            findings.append(
                Finding(
                    f"{SEAM_MODULE}:RankingMirror",
                    f"exposes {', '.join(writable)} beyond the read contract. "
                    "§12.7: a consumer keeps a private read-only mirror it NEVER "
                    "writes",
                )
            )

        live = seam.RankingMirror(stale_after_s=5.0)
        _feed(
            seam, live, _snapshot(seam, {("s1", "ES"): 900.0, ("s2", "ES"): 1.0}), 100.0
        )
        worst = worst_arbitration_s(live, ("s1", "ES"), ("s2", "ES"))
        if worst > ARBITRATION_BUDGET_S:
            findings.append(
                Finding(
                    f"{SEAM_MODULE}:arbitrate",
                    f"worst of {TIMING_DRIVES} arbitrations took "
                    f"{worst * 1000:.3f}ms, over the "
                    f"{ARBITRATION_BUDGET_S * 1000:.1f}ms budget",
                )
            )

        evidence = (
            f"{SEAM_MODULE} seam_rev {seam.SEAM_REV}: scanned {read_scanned} "
            f"read-path function(s) and {shape_scanned} arbitration path for "
            f"computation, iteration, unbounded constructs and I/O; drove all "
            f"five documented FCFS triggers (never-fed, stale-by-clock, absent "
            f"pair-row, equal EMA, foreign writer) plus the RANKED half and the "
            f"flip; worst of {TIMING_DRIVES} arbitrations {worst * 1000:.4f}ms "
            f"against a {ARBITRATION_BUDGET_S * 1000:.1f}ms budget; all three "
            f"arms proved they can fail on planted subjects this run"
        )
        if findings:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(sorted({f.site for f in findings})),
                evidence=evidence,
                detail="; ".join(f"{f.site}: {f.why}" for f in findings),
            )
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
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
