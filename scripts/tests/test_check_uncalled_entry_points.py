"""ARC 034 (D) — the can-fail suite for `check_uncalled_entry_points`.

**EVERY CONTROL ASSERTS THE REASON.** Check-contract rule 11: an exit code is a
shared namespace — the detector firing, the resolver breaking and the
interpreter refusing to start all reach the same integer — so every assertion
below names the message, the site, or the measured field. The one place a bare
status is asserted is beside a message assertion, never instead of one.

**No plant touches a production artifact** (doctrine C.8). Every ratchet plant
lands in a throwaway git repository under `tmp_path`; the two tests that touch
the real tree only READ it.

**THE ORACLE IS SYNTHETIC AND ITS ANSWER IS KNOWN.** A resolver can only be
measured against code whose call graph is decided in advance, so the fixture
tree below is written to have exactly one correct answer per property: a called
function, an uncalled twin with the SAME method name, a Protocol dispatch, a
receiver nothing types, a gate-only caller, and the three shapes that must not
be judged at all. The live-tree test then asserts the same instrument reports
the eight symbols ARC 034's D3.191 audit measured by hand.
"""
# pylint: disable=invalid-name,protected-access,redefined-outer-name
# pylint: disable=import-outside-toplevel,duplicate-code,too-many-lines
# Test names SHOUT the property under test.

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_uncalled_entry_points as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)
from nixverify.gitenv import scrubbed_env  # pylint: disable=wrong-import-position

GIT = "/usr/bin/git"

#: Enough filler to clear both credibility floors with room, and NOT set to the
#: floor itself: a fixture sized exactly at the threshold cannot tell a working
#: floor from one that is off by one.
_FILLER_MODULES = 46
_FILLER_VERBS = 6
#: How many filler verbs `wired.py` actually calls. The rest are the fixture's
#: own honest backlog, which is what makes the ratchet plants below realistic.
_WIRED = 200

_FIXTURE_CLOSED = tuple(range(1, 21))
#: The arc the fixture's ledger has a series row for and the session log does
#: NOT close — `in_flight_arc`'s own derivation, so §0g has something to refuse.
_FIXTURE_IN_FLIGHT = "ARC 021"
#: A FUTURE arc: neither closed nor in flight, so it is the one value that
#: clears both the read rule and the assignment rule.
_FIXTURE_LIVE_ARC = "ARC 022"


def _git(home: Path, *args: str) -> None:
    """Run git against `home` and NOTHING else.

    `env=scrubbed_env()` is not decoration (D3.22): pre-commit exports
    `GIT_INDEX_FILE`, git honours it AHEAD of `-C`, and a `git add -A` in a
    throwaway repo has been measured staging that repo's tree over this
    worktree's real index. The harness runs git exactly the way the gate does.
    """
    subprocess.run(
        [GIT, "-C", str(home), *args],
        check=True,
        capture_output=True,
        env=scrubbed_env(),
    )


# ---------------------------------------------------------------------------
# THE FIXTURE TREE — every property below has ONE known-correct answer.
# ---------------------------------------------------------------------------

#: `Alpha.ping` and `Beta.ping` share a method NAME and only ONE of them is
#: called, through a receiver whose type is written down. A name-only matcher
#: reports both as called; the resolver must report exactly `Beta.ping`. This is
#: `SourceMonotonicGuard.keys` from the real tree, reduced to its skeleton.
_SUBJECT = '''\
"""Fixture subject module. Every answer here is decided in advance."""

from typing import Protocol


class Alpha:
    def ping(self) -> str:
        return "alpha"


class Beta:
    def ping(self) -> str:
        return "beta"


class PingPort(Protocol):
    def pong(self) -> None: ...


class PongImpl:
    def pong(self) -> None:
        return None


class GateOnly:
    def only_verb(self) -> int:
        return 1


class Danger:
    def dangle(self) -> int:
        return 2


class _Hidden:
    def hidden_verb(self) -> int:
        return 3


class Public:
    def __eq__(self, other: object) -> bool:
        return True

    def called_verb(self) -> int:
        return 4


class Caller:
    def __init__(self, alpha: Alpha) -> None:
        self._alpha = alpha

    def go(self) -> str:
        return self._alpha.ping()


def drive(port: PingPort) -> None:
    port.pong()


def loose(obj) -> int:
    return obj.dangle()


def outer() -> int:
    def inner_nested() -> int:
        return 5

    return inner_nested()
'''

#: The shipped consumer. It calls `Caller.go`, `drive`, `loose`, `outer` and
#: `Public.called_verb`, so each of those is CALLED and none may be reported.
_WIRING = '''\
"""Fixture production wiring."""

from subject import Alpha, Caller, Danger, Public, PongImpl, drive, loose, outer


def boot() -> None:
    Caller(Alpha()).go()
    drive(PongImpl())
    loose(Danger())
    outer()
    Public().called_verb()
'''

_GATE_MODULE = '''\
"""Fixture gate. The ONLY caller of GateOnly.only_verb."""

DEPENDS_ON = ()
RESOURCES = ()
SUBJECTS = ()


def run(mode, ctx):
    from subject import GateOnly

    probe = GateOnly()
    return probe.only_verb()
'''


def _write_completion_record(home: Path) -> None:
    """A session log and a ledger series table for the throwaway tree.

    Without them `completed_arcs` errors and every owner arm reads
    CANNOT_MEASURE forever, which would make the owner plants unmeasurable —
    the fixture would agree with a broken gate for the wrong reason.
    """
    (home / "sessions").mkdir(parents=True, exist_ok=True)
    (home / "docs").mkdir(parents=True, exist_ok=True)
    (home / "sessions" / "SESSION.md").write_text(
        "".join(f"## 2026-01-01 — ARC {n:03d}: closed\n\n" for n in _FIXTURE_CLOSED),
        encoding="utf-8",
    )
    (home / "docs" / "CHECK-DEBT.md").write_text(
        "| date | arc | open | note |\n|---|---|---|---|\n"
        f"| 2026-01-01 | ARC {max(_FIXTURE_CLOSED):03d} | 5 | fixture |\n"
        f"| 2026-01-02 | {_FIXTURE_IN_FLIGHT} | 5 | the arc IN FLIGHT |\n",
        encoding="utf-8",
    )


def _filler_sources() -> dict[str, str]:
    """`_FILLER_MODULES` modules of uniquely-named module-level functions."""
    out = {}
    for index in range(_FILLER_MODULES):
        body = "".join(
            f"def f_{index}_{verb}() -> int:\n    return {verb}\n\n\n"
            for verb in range(_FILLER_VERBS)
        )
        out[f"scripts/filler_{index:02d}.py"] = body
    return out


def _wired_source(names: list[str]) -> str:
    """A shipped module that REFERENCES `names`, making each one CALLED."""
    body = "".join(f"    {name}()\n" for name in names)
    return "def use_everything() -> None:\n" + body


def _measure(home: Path) -> gate.Measured:
    """The analysis, with the refusal turned into a loud failure."""
    state, error = gate.analyse(home)
    assert state is not None, f"the fixture tree could not be analysed: {error}"
    return state


def _write_baseline(home: Path, state: gate.Measured, owner: str) -> None:
    """A baseline that accepts EXACTLY what this tree measures."""
    modules: dict[str, dict] = {}
    for sid, bucket in sorted(state.findings.items()):
        path, _, symbol = sid.partition("::")
        module = modules.setdefault(
            path, {"owner": owner, "reason": "fixture row", "symbols": {}}
        )
        module["symbols"][symbol] = {"bucket": bucket, "admitted": "ARC 020"}
    _save(home, {"schema": 1, "modules": modules})


def _save(home: Path, payload: dict) -> None:
    (home / gate.BASELINE).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load(home: Path) -> dict:
    return json.loads((home / gate.BASELINE).read_text(encoding="utf-8"))


def _build(
    home: Path, *, owner: str = _FIXTURE_LIVE_ARC, commit_baseline: bool = True
) -> Path:
    """A throwaway git repo whose call graph is decided in advance."""
    (home / "checks").mkdir(parents=True)
    (home / "scripts").mkdir(parents=True)
    sources = _filler_sources()
    sources["scripts/subject.py"] = _SUBJECT
    sources["scripts/wiring.py"] = _WIRING
    every = [f"f_{i}_{v}" for i in range(_FILLER_MODULES) for v in range(_FILLER_VERBS)]
    sources["scripts/used.py"] = _wired_source(every[:_WIRED])
    sources["checks/check_one.py"] = _GATE_MODULE
    for path, text in sources.items():
        (home / path).write_text(text, encoding="utf-8")
    _write_completion_record(home)
    _git(home, "init", "-q")
    _git(home, "config", "user.email", "t@example.com")
    _git(home, "config", "user.name", "t")
    _git(home, "add", "-A")
    _git(home, "commit", "-qm", "population")
    _write_baseline(home, _measure(home), owner)
    if commit_baseline:
        _git(home, "add", "-A")
        _git(home, "commit", "-qm", "baseline")
    return home


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """The default population: baseline committed, so the ratchet has a mark."""
    return _build(tmp_path / "repo")


def _run(home: Path):
    """The gate, exactly as `verify.py` runs it."""
    return gate.run(Mode.VERIFY, Context(nix_home=home, mode=Mode.VERIFY))


def _sid(symbol: str, module: str = "scripts/subject.py") -> str:
    return f"{module}::{symbol}"


# ===========================================================================
# NON-VACUITY FIRST — the fixture must be capable of exhibiting the property.
# ===========================================================================


def test_the_fixture_tree_is_a_CREDIBLE_population_before_anything_is_planted(
    repo: Path,
) -> None:
    """A plant against a tree the gate refuses to report on measures nothing."""
    state = _measure(repo)
    assert state.shipped_modules >= gate.MIN_CREDIBLE_MODULES, state.shipped_modules
    assert len(state.points) >= gate.MIN_CREDIBLE_ENTRY_POINTS, len(state.points)
    assert gate.vacuity_refusal(state) == "", gate.vacuity_refusal(state)
    assert state.count(gate.CALLED) >= _WIRED, (
        "the fixture must contain real, resolvable call sites or every plant "
        f"below is measuring an empty walk (got {state.count(gate.CALLED)})"
    )


def test_the_UNPLANTED_fixture_is_CLEAN_so_every_red_below_is_the_plant(
    repo: Path,
) -> None:
    """The control. The gate must not be reporting on this tree already."""
    result = _run(repo)
    assert result.status is not Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "ratchet high-water mark" in result.evidence, result.evidence


# ===========================================================================
# THE SCOPE RULE — asserted directly, because it is the whole premise.
# ===========================================================================


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("scripts/nixrisk/halt.py", "shipped"),
        ("scripts/verify.py", "shipped"),
        ("checks/check_halt.py", "gate"),
        ("scripts/tests/test_halt.py", ""),
        ("scripts/tests/independent_claims.py", ""),
        ("databases/schema/extract_sources.py", ""),
        ("docs/CHECK-DEBT.md", ""),
        ("checks/registry.json", ""),
    ],
)
def test_the_SCOPE_RULE_puts_each_path_where_the_docstring_says(
    path: str, expected: str
) -> None:
    """`checks/` is a GATE and `scripts/tests/` is NEITHER — the two decisions
    the whole instrument rests on, asserted as values rather than inferred from
    a verdict."""
    assert gate.scope_of(path) == expected, (
        f"{path} classified as {gate.scope_of(path)!r}, expected {expected!r} — "
        "the scope rule IS the property; a gate counted as shipped code would "
        "make the instrument agree with the defect it exists to name"
    )


# ===========================================================================
# THE ORACLE — a synthetic call graph with one correct answer per property.
# ===========================================================================


def test_a_CALLED_entry_point_is_NOT_reported(repo: Path) -> None:
    """The false-positive direction, and it is the one that gets a gate ignored."""
    state = _measure(repo)
    for symbol in ("Caller.go", "Public.called_verb", "drive", "loose", "outer"):
        assert state.verdicts[_sid(symbol)] == gate.CALLED, (
            f"{symbol} is called by scripts/wiring.py and must be CALLED, not "
            f"{state.verdicts[_sid(symbol)]!r}"
        )
        assert _sid(symbol) not in state.findings, symbol


def test_an_UNCALLED_TWIN_of_a_CALLED_method_is_the_only_one_reported(
    repo: Path,
) -> None:
    """THE RESOLVER'S HEADLINE PROPERTY, and the real tree's `keys` case.

    `Alpha.ping` and `Beta.ping` share a name; `Caller.go` calls the one whose
    receiver is typed `Alpha`. A name-only matcher cannot tell them apart and
    reports NEITHER; the resolver must report EXACTLY `Beta.ping`.
    """
    state = _measure(repo)
    assert state.verdicts[_sid("Alpha.ping")] == gate.CALLED, state.verdicts[
        _sid("Alpha.ping")
    ]
    assert state.findings.get(_sid("Beta.ping")) == gate.UNCALLED, (
        "Beta.ping has no caller anywhere and must be reported UNCALLED; got "
        f"{state.verdicts[_sid('Beta.ping')]!r}"
    )
    assert _sid("Beta.ping") not in state.name_only_findings, (
        "with resolution OFF this finding must DISAPPEAR — if it survives, the "
        "differential in `vacuity_refusal` is measuring something else"
    )


def test_a_PROTOCOL_TYPED_PARAMETER_is_a_REAL_call_site(repo: Path) -> None:
    """`port.pong()` where `port: PingPort` calls every structural implementer."""
    state = _measure(repo)
    assert state.verdicts[_sid("PongImpl.pong")] == gate.CALLED, (
        "PongImpl satisfies PingPort structurally and `drive` calls the verb "
        "through the port — reporting it would be the over-reporting that gets "
        f"a gate routed around (got {state.verdicts[_sid('PongImpl.pong')]!r})"
    )
    assert state.verdicts[_sid("PingPort.pong")] == gate.CALLED, state.verdicts[
        _sid("PingPort.pong")
    ]


def test_an_UNRESOLVED_RECEIVER_yields_CANNOT_RESOLVE_and_NEVER_a_finding(
    repo: Path,
) -> None:
    """The resolver's ignorance must cost findings, never invent them."""
    state = _measure(repo)
    assert state.verdicts[_sid("Danger.dangle")] == gate.CANNOT_RESOLVE, (
        "`loose(obj)` has no annotation, so `obj.dangle()` cannot be attributed; "
        "that must SUPPRESS the finding, not create one (got "
        f"{state.verdicts[_sid('Danger.dangle')]!r})"
    )
    assert _sid("Danger.dangle") not in state.findings


def test_a_GATE_is_NOT_shipped_code_so_its_only_caller_reports_GATE_ONLY(
    repo: Path,
) -> None:
    """The ARC 033 shape: the only thing that constructs it is the check."""
    state = _measure(repo)
    assert state.findings.get(_sid("GateOnly.only_verb")) == gate.GATE_ONLY, (
        "checks/check_one.py is the ONLY caller, and a gate is not production "
        f"wiring (got {state.verdicts[_sid('GateOnly.only_verb')]!r})"
    )


@pytest.mark.parametrize(
    ("symbol", "why"),
    [
        ("_Hidden.hidden_verb", "a module-private class is not a contract seam"),
        ("Public.__eq__", "a dunder is dispatched by the language, not by a caller"),
        ("inner_nested", "a nested def is a closure, not an entry point"),
    ],
)
def test_the_JUDGED_POPULATION_excludes_what_is_not_an_entry_point(
    repo: Path, symbol: str, why: str
) -> None:
    """Over-reporting is how a gate gets routed around (`debug.md` §7.12)."""
    state = _measure(repo)
    assert _sid(symbol) not in state.points, f"{symbol} must not be judged — {why}"


# ===========================================================================
# THE RATCHET. Every plant lands in the throwaway repo, never in the tree.
# ===========================================================================


def test_a_NEW_FINDING_the_baseline_does_not_accept_is_a_LOUD_FAIL(
    repo: Path,
) -> None:
    """The arm this gate exists for: a producer lands and nothing calls it."""
    (repo / "scripts" / "orphan.py").write_text(
        "class Orphan:\n    def never_called(self) -> int:\n        return 1\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A")
    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "scripts/orphan.py::Orphan.never_called" in result.site, result.site
    assert "NO call site in shipped code" in result.detail, result.detail
    assert "not in the accepted baseline" in result.detail, result.detail


def test_an_ACCEPTED_entry_that_ACQUIRES_a_caller_is_a_STALE_BASELINE_FAIL(
    repo: Path,
) -> None:
    """A ratchet may only shrink. Good news the baseline must record."""
    (repo / "scripts" / "late_caller.py").write_text(
        "from subject import Beta\n\n\ndef wire() -> str:\n    return Beta().ping()\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A")
    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "scripts/subject.py::Beta.ping" in result.detail, result.detail
    assert "shipped code now CALLS it" in result.detail, result.detail


def test_an_ACCEPTED_entry_whose_SYMBOL_IS_GONE_is_a_ROT_FAIL(repo: Path) -> None:
    """A row describing nothing is a suppression entry, and says so."""
    payload = _load(repo)
    payload["modules"]["scripts/subject.py"]["symbols"]["Beta.vanished"] = {
        "bucket": "uncalled",
        "admitted": "ARC 020",
    }
    _save(repo, payload)
    _git(repo, "add", "-A")
    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "Beta.vanished" in result.detail, result.detail
    assert "no longer exists" in result.detail, result.detail


def test_an_UNADMITTED_ADDITION_relative_to_the_COMMITTED_MARK_is_a_FAIL(
    repo: Path,
) -> None:
    """The laundering move: land a finding and accept it in the same motion.

    The high-water mark is derived from the baseline's own git history, which
    the edit under judgement cannot reach — so accepting a new finding without
    naming the arc that admitted it is loud even though the file is internally
    consistent.
    """
    (repo / "scripts" / "orphan.py").write_text(
        "class Orphan:\n    def never_called(self) -> int:\n        return 1\n",
        encoding="utf-8",
    )
    payload = _load(repo)
    payload["modules"]["scripts/orphan.py"] = {
        "owner": _FIXTURE_LIVE_ARC,
        "reason": "smuggled in",
        "symbols": {"Orphan.never_called": {"bucket": "uncalled", "admitted": ""}},
    }
    _save(repo, payload)
    _git(repo, "add", "-A")
    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "a ratchet may only shrink" in result.detail, result.detail
    assert "requires a named arc in `admitted`" in result.detail, result.detail


def test_a_MISDESCRIBED_BUCKET_is_a_FAIL_naming_BOTH_values(repo: Path) -> None:
    """`gate_only` and `uncalled` are the diagnostic; an unchecked label rots."""
    payload = _load(repo)
    payload["modules"]["scripts/subject.py"]["symbols"]["GateOnly.only_verb"][
        "bucket"
    ] = "uncalled"
    _save(repo, payload)
    _git(repo, "add", "-A")
    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "recorded 'uncalled', MEASURED 'gate_only'" in result.detail, result.detail


def test_a_MODULE_ROW_WITH_NO_REASON_is_a_FAIL(repo: Path) -> None:
    """A row that cannot say why it is unwired is a suppression entry."""
    payload = _load(repo)
    payload["modules"]["scripts/subject.py"]["reason"] = "   "
    _save(repo, payload)
    _git(repo, "add", "-A")
    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "scripts/subject.py:reason" in result.site, result.site
    assert "no `reason`" in result.detail, result.detail


def test_an_UNREADABLE_BASELINE_is_CANNOT_MEASURE_and_names_the_file(
    repo: Path,
) -> None:
    """Never a PASS: a ratchet that cannot read its own accepted set is blind."""
    (repo / gate.BASELINE).write_text("{ not json", encoding="utf-8")
    _git(repo, "add", "-A")
    result = _run(repo)
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert gate.BASELINE in result.detail and "unreadable" in result.detail


def test_a_BASELINE_WITH_NO_COMMIT_HISTORY_is_CANNOT_MEASURE_never_a_PASS(
    tmp_path: Path,
) -> None:
    """Without a prior mark the accepted set cannot be shown not to have grown."""
    home = _build(tmp_path / "fresh", commit_baseline=False)
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "has no commit history" in result.detail, result.detail


# ===========================================================================
# THE OWNER RULES — doctrine B.3, and §0g at assignment.
# ===========================================================================


def test_an_UNASSIGNED_owner_DEFERS_HONESTLY_rather_than_certifying(
    tmp_path: Path,
) -> None:
    """`unassigned` is honest and is NOT owned; the gate must not guard it."""
    home = _build(tmp_path / "unowned", owner=gate.UNASSIGNED)
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "`unassigned`" in result.detail, result.detail
    assert "No arc has committed" in result.detail, result.detail


def test_a_LIVE_ARC_owner_reaches_GUARDED_and_carries_the_owner(
    repo: Path,
) -> None:
    """The positive control for the owner arms — without it `unassigned` above
    would be indistinguishable from an owner rule that always defers."""
    result = _run(repo)
    assert result.status is Status.GUARDED, result.detail
    assert result.guard_owner == _FIXTURE_LIVE_ARC, result.guard_owner
    assert "entry point(s) with no shipped caller" in result.detail, result.detail


def test_a_COMPLETED_ARC_owner_DEFERS_and_names_the_completion(
    repo: Path,
) -> None:
    """Doctrine B.3: an owner that cannot pay is no owner wearing a name."""
    payload = _load(repo)
    payload["modules"]["scripts/subject.py"]["owner"] = "ARC 005"
    _save(repo, payload)
    _git(repo, "add", "-A")
    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "ALREADY COMPLETED" in result.detail, result.detail


def test_the_ARC_IN_FLIGHT_is_REFUSED_AT_ASSIGNMENT_under_section_0g(
    repo: Path,
) -> None:
    """§0g of `docs/nix_check_contract.md`: a promise made by the arc that
    closes by making it is dead the moment it is written (D3.40)."""
    payload = _load(repo)
    payload["modules"]["scripts/subject.py"]["owner"] = _FIXTURE_IN_FLIGHT
    _save(repo, payload)
    _git(repo, "add", "-A")
    result = _run(repo)
    assert result.status is Status.FAIL_NEEDS_OPERATOR, result.detail
    assert "is the arc IN FLIGHT" in result.detail, result.detail


# ===========================================================================
# THE VACUITY FLOORS — §7.12 points 1 to 4 of the gate's own docstring.
# ===========================================================================


def test_a_TINY_ENUMERATION_is_CANNOT_MEASURE_and_names_the_floor(
    tmp_path: Path,
) -> None:
    """Zero entry points, zero findings, PASS is the purest vacuous green."""
    home = tmp_path / "tiny"
    (home / "scripts").mkdir(parents=True)
    (home / "scripts" / "only.py").write_text("def solo() -> int:\n    return 1\n")
    _git(home, "init", "-q")
    _git(home, "config", "user.email", "t@example.com")
    _git(home, "config", "user.name", "t")
    _git(home, "add", "-A")
    _git(home, "commit", "-qm", "tiny")
    result = _run(home)
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "credibility floor" in result.detail, result.detail
    assert str(gate.MIN_CREDIBLE_MODULES) in result.detail, result.detail


def test_a_RESOLVER_THAT_CHANGES_NOTHING_is_REFUSED_by_the_DIFFERENTIAL(
    repo: Path, monkeypatch
) -> None:
    """§7.12 point 4, driven rather than asserted.

    The differential is the only every-run control over the resolver itself, so
    it has to be shown FIRING. `receiver_type` is neutered — which is exactly
    what a broken resolver looks like — and the run must refuse rather than
    report a smaller, quieter finding set.
    """
    monkeypatch.setattr(gate._Walk, "receiver_type", lambda self, node: "")
    state = _measure(repo)
    refusal = gate.vacuity_refusal(state)
    assert "RECEIVER RESOLUTION CHANGED NOTHING" in refusal, refusal
    result = _run(repo)
    assert result.status is Status.CANNOT_MEASURE, result.detail
    assert "RECEIVER RESOLUTION CHANGED NOTHING" in result.detail, result.detail


def test_the_DIFFERENTIAL_is_NOT_an_identity_on_the_fixture(repo: Path) -> None:
    """The control for the control: with the resolver intact, the two walks
    must genuinely disagree, or the test above proves only that a constant is
    a constant."""
    state = _measure(repo)
    delta = len(state.findings) - len(state.name_only_findings)
    assert delta > 0, (
        "receiver resolution must produce findings a name-only walk cannot see "
        f"({len(state.findings)} vs {len(state.name_only_findings)})"
    )
    assert state.ruled_out > 0, (
        "the resolver must be RULING references OUT, not merely agreeing"
    )


# ===========================================================================
# THE LIVE TREE — read-only, and the calibration ARC 034's audit measured.
# ===========================================================================


#: The eight symbols the D3.191 audit found by hand. If this instrument misses
#: one, it is not measuring the thing that let the ARC 033 cap ship unfed.
#:
#: `StopBook.arm` and `PositionOriginWriter.on_fill` are listed with the buckets
#: they hold ON THIS BRANCH. Sub-agent A is landing production callers for both
#: in a parallel worktree, so after that merge they become CALLED and this list
#: must SHRINK — a shrink is the ratchet working, and the integrator re-measures.
#: THE TWO THE DETECTOR WAS BUILT FOR, AND THEY ARE NO LONGER UNCALLED.
#: `StopBook.arm` and `PositionOriginWriter.on_fill` were the calibration cases —
#: D3.178's own subject, built and gated with zero production callers, which is
#: what let §7:501's bucket cap price held positions off a field nothing wrote.
#: ARC 034's sub-agent A landed `nixrisk/fills.py` in a parallel worktree, and on
#: the MERGED tree this detector independently reports both as `called`.
#:
#: They are moved OUT of the calibration set and asserted the other way round, by
#: `test_the_TWO_D3178_SUBJECTS_ARE_NOW_CALLED` below. That is a stronger test
#: than leaving them here: a second instrument, written by a different author
#: against a different question, confirms the fix — and if the wiring is ever
#: removed, that test reddens instead of this one quietly passing again.
_D3178_NOW_CALLED = (
    "scripts/nixrisk/stops.py::StopBook.arm",
    "scripts/nixrisk/positions.py::PositionOriginWriter.on_fill",
)

_CALIBRATION = (
    "scripts/nixrisk/session.py::SessionFlattener.is_due",
    "scripts/nixrisk/pollers.py::PushDemotion.last_push",
    "scripts/nixrisk/freshness.py::SourceMonotonicGuard.keys",
    "scripts/nixrisk/freshness.py::ClockSkewMonitor.latest",
    "scripts/nixrisk/session.py::SessionFlattener.fired_outcome",
    "scripts/nixrisk/roll.py::RollIdentityBook.next_roll_instant",
)


def test_the_LIVE_TREE_reports_every_symbol_the_D3_191_AUDIT_found_BY_HAND() -> None:
    """The calibration. Read-only; nothing is planted in the real tree.

    Each of these was found by a human reading six modules and six gates. An
    instrument that cannot re-find them is not measuring the class.
    """
    state = _measure(REPO)
    missing = [
        sid for sid in _CALIBRATION if sid not in state.findings and sid in state.points
    ]
    assert not missing, (
        "these entry points have no shipped caller and the gate did not report "
        f"them: {missing} (verdicts: "
        f"{ {sid: state.verdicts.get(sid) for sid in missing} })"
    )


def test_the_TWO_D3178_SUBJECTS_ARE_NOW_CALLED() -> None:
    """D3.178 closed, confirmed by an instrument that did not fix it.

    `StopBook.arm` and `PositionOriginWriter.on_fill` shipped built, gated and
    with ZERO production callers — ARC 029 and ARC 033 respectively — so the
    bucket cap priced held positions off a `stop_distance` nothing wrote. This
    detector was calibrated against exactly that pair.

    ARC 034's fill handler wired them, and the assertion is INVERTED rather than
    deleted: if the wiring is ever removed, this test reddens. Deleting it would
    let the fix rot silently, which is the shape D3.178 exists to name.
    """
    state = _measure(REPO)
    wrong = {
        sid: state.verdicts.get(sid)
        for sid in _D3178_NOW_CALLED
        if state.verdicts.get(sid) != gate.CALLED
    }
    assert not wrong, (
        "D3.178's two subjects must have a SHIPPED caller — nixrisk/fills.py is "
        f"the fill handler that calls them. Verdicts now: {wrong}"
    )


def test_the_LIVE_TREE_clears_every_vacuity_floor_this_gate_declares() -> None:
    """A refusal on the real tree would make every green above local to a fixture."""
    state = _measure(REPO)
    assert gate.vacuity_refusal(state) == "", gate.vacuity_refusal(state)
    assert state.count(gate.CALLED) >= state.count(gate.CANNOT_RESOLVE), (
        f"{state.count(gate.CALLED)} called vs "
        f"{state.count(gate.CANNOT_RESOLVE)} unresolvable"
    )


#: ARC 034's CARRIED RED, pinned by name (CHECK-DEBT D3.203).
#:
#: This detector's FIRST ARMED RUN caught the arc that built it: once its baseline
#: gained commit history the ratchet armed, and it reported these entry points as
#: new uncalled surface in ARC 034's own modules.
#:
#: THE BASELINE WAS NOT WIDENED TO SWALLOW THEM, and that is the whole point of
#: this constant. The gate's own verdict offers three outs — wire it, delete it,
#: or admit it by name — and admitting an arc's own growth into the baseline of
#: the detector that arc just built would make the instrument's debut a
#: demonstration of how to route around it.
#:
#: So the red is CARRIED and pinned HERE instead: the set may not GROW (a new
#: uncalled entry point is a fresh failure) and it may not SHRINK silently either
#: (wiring one means removing it from this tuple, which is a visible diff). The
#: ratchet's job is done by the gate; this test's job is to stop the carried red
#: from becoming a place to hide.
_ARC034_CARRIED = (
    "scripts/nixrisk/fills.py::ApprovedOrderBook.approved",
    "scripts/nixrisk/fills.py::FillHandler.armed_orders",
    "scripts/nixrisk/fills.py::FillHandler.disagreements",
    "scripts/nixrisk/fills.py::IocRemainder.history",
    "scripts/nixrisk/join.py::production_origins",
    "scripts/nixrisk/recovery.py::HeartbeatMonitor.beat",
    "scripts/nixrisk/recovery.py::HeartbeatMonitor.grace_cycles",
    "scripts/nixrisk/recovery.py::HeartbeatMonitor.interval_s",
    "scripts/nixrisk/recovery.py::HeartbeatMonitor.miss",
    "scripts/nixrisk/recovery.py::StrategyRegistry.register",
    "scripts/nixrisk/recovery.py::heartbeat_from_config",
    "scripts/nixrisk/supervision.py::CrashLoopBreaker.is_quarantined",
    "scripts/nixrisk/supervision.py::CrashLoopBreaker.knobs",
    "scripts/nixrisk/supervision.py::CrashLoopBreaker.quarantine_verdict",
    "scripts/nixrisk/supervision.py::CrashLoopBreaker.restore",
    "scripts/nixrisk/supervision.py::CrashLoopBreaker.scope",
    "scripts/nixrisk/supervision.py::not_installed",
    "scripts/nixsentinel/config.py::SentinelKnobs.limiter_grace_s",
    "scripts/risk_config.py::knob",
)

#: ARC 035 / sub-agent D — the SAME treatment, applied to this arc's own growth,
#: because the alternative is the move D3.203 refused by name.
#:
#: `scripts/nixrisk/drift_audit.py` is §11 item 7's periodic full-scan reconcile. Its
#: `run`, `due`, `full_scan` and `classify` ARE called in shipped code (by each
#: other); the six below are not called by anything but the gate and the suite,
#: and there is no Limiter run loop in this tree to call them from — §11 item 7 says
#: *periodic* and nothing in `scripts/` schedules anything.
#:
#: **NOT added to `checks/uncalled_entry_points_baseline.json`, deliberately.**
#: The gate's verdict offers three outs — wire it, delete it, or admit it by name
#: — and putting an arc's own growth into the detector's ratchet is how a debut
#: becomes a demonstration of routing around the instrument. The gate therefore
#: stays RED on these six, which is the honest state; this tuple only stops the
#: SUITE from reporting them as an unexplained regression, and it may not grow
#: silently (a new uncalled entry point is a fresh failure) or shrink silently
#: (wiring one means deleting a line here, which is a visible diff).
#:
#: Per-row honesty, since "admit it by name" means naming what each one IS:
#:   * `run_if_due` / `interval_s` / `last_run` — §11 item 7's *periodic* half. They
#:     exist because the word is in the spec; nothing schedules them.
#:   * `AuditOutcome.clean` / `.material` — observables the gate asserts against.
#:     Production reads `AuditOutcome` through no caller at all yet.
#:   * `projection_from_rows` — the declared seam to sub-agent B's Plane-1
#:     positions projection. This is `join.py::production_origins`' exact shape,
#:     the one D3.203 says most likely wants WIRING rather than admitting, and it
#:     is admitted here only because the reader it pairs with is on another branch.
_ARC035_D_CARRIED = (
    "scripts/nixrisk/drift_audit.py::AuditOutcome.clean",
    "scripts/nixrisk/drift_audit.py::AuditOutcome.material",
    "scripts/nixrisk/drift_audit.py::DriftAudit.interval_s",
    "scripts/nixrisk/drift_audit.py::DriftAudit.last_run",
    "scripts/nixrisk/drift_audit.py::DriftAudit.run_if_due",
    "scripts/nixrisk/drift_audit.py::projection_from_rows",
)

#: ARC 036 Phase 0.4 — the §6.6 Scoring seam, CARRIED BY NAME, not absorbed.
#:
#: The seam is frozen before the fan-out that builds its consumers, which is the
#: whole point of a Phase 0: five sub-agents cannot build against an interface
#: that does not exist yet. So for the length of this arc the read side has no
#: production caller, and `check_uncalled_entry_points` is RIGHT to say so.
#:
#: It is enumerated here rather than added to the baseline for D3.203's reason,
#: verbatim: a ratchet whose accepted set grows to meet its findings is not a
#: ratchet. And the `vanished` assertion below is what makes this an obligation
#: rather than a note — the moment sub-agent E wires the Allocator to
#: `arbitrate`, that name STOPS being a finding and this tuple must shrink with
#: it, or the test goes red for the opposite reason. A carried red that cannot
#: be quietly kept is the only kind worth carrying. CHECK-DEBT D3.214.
#: SHRUNK by ARC 036 sub-agent B, which is the obligation above being paid
#: rather than a note being edited. `scripts/nixscore/publisher.py` is the real
#: publish path and it CALLS `RankingMirror.arbitrate`, `RankingMirror.fresh`,
#: `RankingMirror.lookup`, `RankingPublisher.service` and
#: `RankingSnapshot.lookup` from shipped code, so all five stopped being
#: findings and had to leave this tuple in the same commit. What remains is what
#: is still genuinely unwired: `RankingMirror.span_days` (nothing reads the span
#: yet) and `Verdict.fell_back` (the Limiter's convenience predicate, and the
#: Limiter does not exist).
_ARC036_PHASE0_CARRIED = (
    "scripts/nixscore/seam.py::RankingMirror.span_days",
)

#: SHRUNK, ARC 036 Stage 1 / sub-agent C — seven to three, and the four that
#: left are the obligation above being paid rather than waived. `arbitrate`,
#: `fresh` and `lookup` acquired shipped callers in
#: `nixscore.process.RankingReader` / `FallbackAlarm` / `scoring_kill_drill`,
#: and `RankingPublisher.service` in `ScoringProcess.tick`. The three that
#: remain are still uncalled and still carried BY NAME: `span_days` and
#: `RankingSnapshot.lookup` are read-side conveniences no consumer needs yet,
#: and `Verdict.fell_back` is the predicate the Allocator will branch on when
#: sub-agent E wires it. CHECK-DEBT D3.214.
_ARC036_PHASE0_CARRIED = (
    "scripts/nixscore/seam.py::RankingMirror.span_days",
)

#:
#: **ARC 036 sub-agent E SHRANK THIS BY FIVE, which is the obligation being
#: paid rather than a relaxation of it.** `scripts/nixalloc/wiring.py` now
#: reads the mirror on the Allocator's production path — `_MirrorRankingTable`
#: calls `fresh` and `lookup`, `AllocatorPathway.propose_contended` reads
#: `span_days`, and `_pairwise` calls `arbitrate` and reads `Verdict.fell_back`
#: — so those five stopped being findings and left this tuple in the same edit.
#:
#: What remains is the SCORING side of the seam and the seam's INGRESS, and
#: none of the three is the Allocator's to wire: `RankingPublisher.service`
#: serves §12.7's snapshot-on-subscribe, `RankingSnapshot.lookup` reads a table
#: the WRITER holds, and `RankingMirror.apply` is fed from a subscriber socket
#: that nothing in production holds because nothing publishes the `ranking`
#: topic. All three get their production caller when the Scoring process and the
#: Allocator's own subscriber loop land (R5 / §12B), and until then they are
#: carried for the same reason the original seven were.
#:
#: **`RankingMirror.apply` is an ADDITION, and it is one this arc MADE VISIBLE
#: rather than one it created.** At ARC 036 Phase 0 the gate reported it
#: `cannot_resolve` — no receiver anywhere resolved to a `RankingMirror`, and
#: the gate is explicit that a cannot-resolve is reported and never counted as a
#: finding. `checks/check_scoring_consumption.py` constructs one by name, so the
#: receiver now resolves and the honest verdict is `gate_only`: a gate calls it
#: and shipped code does not. Carrying it by name is the mechanism for that;
#: leaving it unresolvable would have been a suppression that cost nothing to
#: keep.
_ARC036_PHASE0_CARRIED = (
    "scripts/nixscore/seam.py::RankingMirror.apply",
    "scripts/nixscore/seam.py::RankingPublisher.service",
    "scripts/nixscore/seam.py::RankingSnapshot.lookup",
)

#: ARC 036 Stage 1 / sub-agent A — the §6.6 realized-P&L EMA engine's ONE door.
#:
#: `scripts/nixscore/ema.py` computes the score. Nothing calls it, because the
#: Scoring PROCESS that would is sub-agent C's mandate and the publisher is B's,
#: so a Stage-1 branch cannot contain its own caller. Same shape as the seam's
#: carry above and as D3.213 one module over. CHECK-DEBT D3.222.
#:
#: **It is ONE name and that is the point.** The gate first reddened on
#: `realized_closes` — the log EXTRACTOR — which was not a carry-worthy finding
#: at all but a missing verb: the engine had no call that ran the whole path,
#: so its own extractor sat on a gate-only branch. `snapshot_from_log` is that
#: verb, and it collapsed the finding from an internal function to the module's
#: single public door. What is left is the honest statement — the engine has
#: exactly one entry point and nothing walks through it — and it is admitted
#: here rather than absorbed into the baseline for D3.203's reason: a ratchet
#: whose accepted set grows to meet its findings is not a ratchet. The
#: `vanished` assertion makes it an obligation: the moment the Scoring process
#: calls it, this tuple must shrink or the test reddens the other way.
_ARC036_STAGE1_A_CARRIED = (
    "scripts/nixscore/ema.py::RealizedEmaEngine.snapshot_from_log",
)

#: ARC 036 sub-agent B — `scripts/nixscore/publisher.py`, the same shape one
#: layer out and stated as such rather than discovered later.
#:
#: The publish path's writer is driven by the Scoring process (sub-agent C) and
#: its reader by the Allocator and Limiter (sub-agent E). Neither exists in this
#: sub-agent's tree, so every public verb on `RankingWriter` and `RankingReader`
#: has gates and tests for callers and nothing else — which is exactly what
#: `check_uncalled_entry_points` was built to name, and it is right.
#:
#: Carried BY NAME, never absorbed into the baseline (D3.203). The `vanished`
#: assertion makes it an obligation: as Stage 2 wires the Scoring process and
#: the Allocator, these names stop being findings and this tuple must shrink in
#: the same commit. CHECK-DEBT D3.230.
_ARC036_B_CARRIED = (
    "scripts/nixscore/publisher.py::PumpResult.carried_nothing",
    "scripts/nixscore/publisher.py::RankingReader.applied",
    "scripts/nixscore/publisher.py::RankingReader.arbitrate",
    "scripts/nixscore/publisher.py::RankingReader.bytes_received",
    "scripts/nixscore/publisher.py::RankingReader.close",
    "scripts/nixscore/publisher.py::RankingReader.foreign_rejected",
    "scripts/nixscore/publisher.py::RankingReader.fresh",
    "scripts/nixscore/publisher.py::RankingReader.malformed_rejected",
    "scripts/nixscore/publisher.py::RankingReader.mirror",
    "scripts/nixscore/publisher.py::RankingReader.pump",
    "scripts/nixscore/publisher.py::RankingReader.stale",
    "scripts/nixscore/publisher.py::RankingReader.view",
    "scripts/nixscore/publisher.py::RankingWriter.close",
    "scripts/nixscore/publisher.py::RankingWriter.publish_rows",
    "scripts/nixscore/publisher.py::RankingWriter.published",
    "scripts/nixscore/publisher.py::RankingWriter.service",
    "scripts/nixscore/publisher.py::RankingWriter.snapshots_served",
    "scripts/nixscore/publisher.py::RankingWriter.subscribes_seen",
    "scripts/nixscore/publisher.py::ranking_endpoint",
)

#: ARC 036 Stage 1 / sub-agent D — the §6.6 durable score store, CARRIED BY NAME.
#:
#: `scripts/nixscore/store.py` is the archive/restore half of §4:279 and §12.11's
#: verb 3. Its counterpart is `nixrisk.supervision.CrashLoopBreaker`, whose
#: `restore`, `is_quarantined` and `quarantine_verdict` are themselves UNCALLED on
#: this tree — the two ends of one seam exist and no code joins them, which is
#: CHECK-DEBT D3.252 and is Stage 2 integration work, not this sub-agent's.
#:
#: Enumerated here for D3.203's reason and never absorbed into
#: `uncalled_entry_points_baseline.json`: a ratchet whose accepted set grows to
#: meet its findings is not a ratchet. The `vanished` assertion below makes it an
#: obligation — the moment the Scoring process (`nixscore/process.py`) holds one
#: of these behind `ScoreStorePort`, that name stops being a finding and this
#: tuple must shrink with it.
#:
#: **`ScoreStorePort`'s own verbs are in here, and that is the honest reading.**
#: A Protocol method has no body and is never called; it is the SHAPE a caller
#: must satisfy. This gate cannot see the difference between a declared seam
#: awaiting its consumer and a method nobody wanted, and admitting the Protocol
#: rows silently would hide the first case behind the second. They are listed.
#:
#: NOTE, and it is why this tuple had to be written at all: the SHIPPED gate's
#: own detail names only its first 25 un-baselined findings and does not say it
#: truncated, so every name below was INVISIBLE in two consecutive runs of
#: `checks/check_uncalled_entry_points.py`. This suite caught what that output
#: hid. CHECK-DEBT D3.253.
_ARC036_STAGE1_D_CARRIED = (
    "scripts/nixscore/store.py::ArchiveOutcome.moved",
    "scripts/nixscore/store.py::RestoreOutcome.rehydrated",
    "scripts/nixscore/store.py::ScoreStore.archive_reason",
    "scripts/nixscore/store.py::ScoreStore.archive_strategy",
    "scripts/nixscore/store.py::ScoreStore.archived_pairs",
    "scripts/nixscore/store.py::ScoreStore.archived_record",
    "scripts/nixscore/store.py::ScoreStore.live_pairs",
    "scripts/nixscore/store.py::ScoreStore.presence",
    "scripts/nixscore/store.py::ScoreStore.restore_strategy",
    "scripts/nixscore/store.py::ScoreStore.revision",
    "scripts/nixscore/store.py::ScoreStorePort.archive_strategy",
    "scripts/nixscore/store.py::ScoreStorePort.archived_pairs",
    "scripts/nixscore/store.py::ScoreStorePort.live_pairs",
    "scripts/nixscore/store.py::ScoreStorePort.presence",
    "scripts/nixscore/store.py::ScoreStorePort.restore_strategy",
)


def test_the_LIVE_BASELINE_accepts_EXACTLY_what_the_LIVE_TREE_measures() -> None:
    """The ratchet, read against the real tree, MINUS ARC 034's carried red.

    Neither direction may drift. The carried set is enumerated in
    `_ARC034_CARRIED` rather than absorbed into the baseline — see that constant
    for why, and CHECK-DEBT D3.203 for the ledger row.
    """
    state = _measure(REPO)
    baseline = gate.load_baseline(REPO)
    assert baseline.error == "", baseline.error
    carried = (
        set(_ARC034_CARRIED)
        | set(_ARC035_D_CARRIED)
        | set(_ARC036_PHASE0_CARRIED)
        | set(_ARC036_STAGE1_A_CARRIED)
        | set(_ARC036_B_CARRIED)
        | set(_ARC036_STAGE1_D_CARRIED)
    )
    unaccepted = sorted(set(state.findings) - baseline.accepted - carried)
    stale = sorted(baseline.accepted - set(state.findings))
    vanished = sorted(carried - set(state.findings))
    assert not unaccepted, (
        "findings that are neither in the baseline nor in ARC 034's named carried "
        f"set — this is NEW uncalled surface and it is a fresh failure: {unaccepted[:8]}"
    )
    assert not stale, f"baseline rows that are no longer findings: {stale[:8]}"
    assert not vanished, (
        "these were carried by name and are no longer findings — WIRING one is "
        "good news, and the tuple must shrink with it so the carried red cannot "
        f"become a place to hide: {vanished}"
    )
