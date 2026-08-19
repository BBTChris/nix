"""ARC 038 sub-agent G — THE UNPARSEABLE-SUBJECT PROBE: does a gate read its
subject at the home it was GIVEN, or at the home its `sys.path` happens to name?

`ctx.nix_home` is the one input that tells a check WHICH TREE to measure. Every
staged-tree can-fail in this repo depends on it: stage a copy, plant the defect
in the copy, point the gate at the copy, require red. `docs/CHECK-DEBT.md`
D3.344 is what happens when that pointing silently fails — two suites inherited
a `PYTHONPATH` naming the real tree, the staged gate imported the PRODUCTION
module, and **every plant was defeated while the gate reported on the staged tree
and PASSED.** D3.344 closed its own instance and left the class open in one
sentence: *"nothing enumerates which staged-tree runners pass an env and which
inherit one."*

This suite answers a strictly stronger question, because it does not depend on
the environment at all:

> **Given a home in which the gate's own declared `SUBJECTS` are files that are
> not valid Python, can the gate still return PASS?**

A gate that can is not measuring its subject at that home. There is no reading of
"the subject is fine" that survives the subject not existing as Python, so a PASS
here is a refutation rather than a matter of interpretation. It needs no model of
the gate's arms, so it works uniformly over a population of seventy-three, and it
cannot be defeated by an environment variable because it changes the ARGUMENT,
not the path.

MEASURED, ARC 038, worktree `arc-038-g` at `f059ea4`: **thirteen of seventy-three
gates certified over a corrupt subject.** `check_picture_atomicity` was repaired
in the same arc (it now refuses, naming both paths); the other twelve are
enumerated below with a reason each, and CHECK-DEBT D3.408 owns them.

## THE PROBE HOME IS A FULLY STAGED TREE, AND THAT WAS MEASURED, NOT ASSUMED

The first version of this suite built a MINIMAL home containing only the gate's
own corrupted subjects, on the reasoning that a smaller home could only make a
gate refuse sooner. **That reasoning was wrong and the measurement said so.**
Three gates that certify over a corrupt subject in a full tree
(`check_plane1_degraded`, `check_plane1_event_coverage`, `check_plane1_schema`)
REFUSE a minimal one — for absence, not for corruption — and one gate that
correctly refuses a full tree (`check_limiter_gate`) PASSES a minimal one,
because with the package's `__init__.py` missing its loader falls through to
importing the module by name. A minimal home is unsound in BOTH directions, so
the home here is a real staged tree and only the subjects are corrupt: one
variable changed relative to an ordinary run, and it is the tree.

## §7.12 — what would have to be true for THIS SUITE to measure nothing?

1. **The population could be empty**, and "no gate certified over a corrupt
   subject" would be the purest vacuous green. *Closed:* `MIN_POPULATION`, and
   the population is derived from `checks/` ON DISK by `declarations.read_all`,
   never from the registry — a registry-derived population cannot report an
   orphan.
2. **The probe could plant nothing.** A `SUBJECTS` entry naming a path that does
   not exist would be silently skipped and the gate refused for absence instead.
   *Closed:* every probed subject must exist in the real tree AND in the staged
   tree, and the corrupt bytes are read back before the gate runs. A plant that
   plants nothing reddens the plant, not the subject (`debug.md` §8 #4).
3. **The child could measure a tree the parent did not name** — D3.344 itself.
   *Closed:* the child is launched with an EXPLICIT `env`, and it prints the
   resolved `__file__` of a witness module from inside its own process; the suite
   ASSERTS that path rather than assuming it.
4. **The staging could be a poor copy**, so a refusal means "your tree is
   broken" rather than "your subject is corrupt". *Closed by the control:* the
   same staged tree, with NOTHING corrupted, must let a sample of gates reach a
   verdict that is not a staging complaint — `test_control_the_STAGED_TREE_is_a
   _working_tree`.
5. **A gate could hang and its silence be read as a refusal.** *Closed:* a
   timeout is `TIMEOUT`, reported by name, folded into neither verdict, and
   counted against a ceiling so the suite cannot decay into one that measures
   nobody.
6. **The exception list could absorb the finding.** *Closed in BOTH directions:*
   a gate NOT on the list which certifies is a FAIL (new debt is red), and a gate
   ON the list which now refuses is ALSO a FAIL (a repaired gate must leave the
   list, or the list becomes the suppression drawer
   `check_artifact_gate_coverage`'s own §7.12 rule 3 refuses). The list can only
   tighten.

Every assertion names the REASON — the gate, the corrupt subject, the verdict —
never an exit code (check contract rule 11).
"""

from __future__ import annotations

# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
import json
import os
import shutil
import subprocess  # nosec B404 - runs this repo's own interpreter, fixed argv
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

from nixverify.declarations import read_all  # pylint: disable=wrong-import-position

#: The bytes written over every probed subject. Not valid Python in any version.
CORRUPT = "@@@ ARC 038 G unparseable-subject probe @@@ not Python (\n"

#: Below this the probe is not credible: this tree has dozens of gates declaring
#: code subjects, and a handful would mean `read_all` or the glob broke.
MIN_POPULATION = 50

#: Per-gate ceiling. Several probed gates build ephemeral PostgreSQL clusters or
#: spawn `strace`; the budget is a broken-machine detector, not a performance
#: assertion. A timeout is TIMEOUT, never a verdict.
PROBE_TIMEOUT_S = 300

#: At most this many gates may TIMEOUT before the suite refuses to conclude.
MAX_TIMEOUTS = 6

#: Directories copied into the probe home. `.venv`/`.venv-dev` are excluded BY
#: NAME for D3.206's reason: seven fixtures copied both venvs into a shared tmpfs
#: in one arc and produced 234 red tests across twenty unrelated subjects.
_STAGED_DIRS = ("scripts", "checks", "docs", "databases", "risks", "web")
_STAGED_FILES = ("VERSION", "pyproject.toml", "CLAUDE.md", "install.sh")

#: MEASURED 2026-08-18 in worktree `arc-038-g` at `f059ea4`: each of these
#: returns PASS over a staged home whose every declared `.py` subject is
#: unparseable. Each resolves its subject through the PROCESS's `sys.path` (or
#: through a `REPO` constant derived from the gate's own `__file__`) instead of
#: through `ctx.nix_home`, so its verdict is a function of the interpreter's path
#: and not of the tree it was handed, and a staged-tree plant pointed at it via
#: `nix_home` is silently defeated. CHECK-DEBT D3.408.
#:
#: THIS LIST MAY ONLY SHRINK, and a gate that leaves it must be deleted from it in
#: the same commit — `test_no_KNOWN_ROOT_BLIND_gate_has_quietly_been_repaired` is
#: what makes that mechanical rather than a hope.
KNOWN_ROOT_BLIND: dict[str, str] = {
    "check_feed_kill_drill": (
        "drives `scripts/feed_kill_drill.py` as a program resolved from this "
        "process, so the four declared subjects are never opened at ctx.nix_home"
    ),
    "check_mirror_liveness": (
        "its staged can-fail works by launching the STAGED COPY of the gate "
        "with an explicit PYTHONPATH (the D3.344 repair); there is no "
        "ctx.nix_home path into it at all, and a mismatch is accepted silently"
    ),
    "check_plane1_crash_gap": (
        "run() builds two ephemeral clusters and imports `plane1_crash_drill` "
        "by NAME; ctx.nix_home selects nothing"
    ),
    "check_plane1_degraded": (
        "run() imports `nixrisk.degraded` / `nixrisk.stops` by NAME; the two "
        "declared subjects are never opened at ctx.nix_home"
    ),
    "check_plane1_event_coverage": (
        "the §12.10 census drives the sink imported by NAME, so the drive half "
        "is rooted at sys.path even where `classify` is handed the home"
    ),
    "check_plane1_hot_path": (
        "run() does `del ctx` outright and imports `plane1_hotpath_drill` by "
        "NAME — the most explicit case in the population"
    ),
    "check_plane1_projection": (
        "the projection is rebuilt through modules imported by NAME; the two "
        "declared .py subjects are never opened at ctx.nix_home"
    ),
    "check_plane1_wal": (
        "run() drives the WAL kill drill through modules imported by NAME; the "
        "declared subjects are never opened at ctx.nix_home"
    ),
    "check_plane2_across_kill": (
        "drives capture and the kill drill as programs resolved from this "
        "process; the three declared subjects are never opened at ctx.nix_home"
    ),
    "check_scoring_fallback": (
        "same shape as check_mirror_liveness — the staged plants reach the gate "
        "through an explicit child PYTHONPATH, never through ctx.nix_home"
    ),
    "check_state_bus": (
        "run() imports `nixbus.statebus` by NAME for the real socket "
        "round-trip; the declared subject is never opened at ctx.nix_home"
    ),
    "check_verify_logging": (
        "DELIBERATE AND DOCUMENTED: its suite says nix_home points at a scratch "
        "tree only to keep arm 4's file out of the worktree, and the plants go "
        "into the real scripts/nixverify/plane2.py. Listed because the gate "
        "still ACCEPTS a mismatched home in silence rather than saying so"
    ),
}

#: The witness module the child resolves and PRINTS from inside its own process,
#: so §7.12/3 is closed by assertion rather than by assumption.
WITNESS = "nixverify.contract"

_CHILD = r"""
import json, sys
sys.path.insert(0, SCRIPTS)
from pathlib import Path
import importlib
witness = importlib.import_module(WITNESS)
row = {"witness_file": witness.__file__}
from nixverify import loader
from nixverify.contract import Context, Mode
loaded = loader.load_check(Path(CHECKS), GATE)
row["load_error"] = loaded.load_error
if loaded.run is None:
    print(json.dumps(row)); raise SystemExit(0)
try:
    r = loaded.run(Mode.VERIFY, Context(nix_home=Path(HOME), mode=Mode.VERIFY))
    row["status"] = str(getattr(r.status, "name", r.status))
    row["detail"] = (r.detail or "")[:800]
    row["site"] = (r.site or "")[:200]
    row["evidence"] = (r.evidence or "")[:200]
except BaseException as exc:
    row["status"] = "RAISED:" + type(exc).__name__
    row["detail"] = str(exc)[:800]
print(json.dumps(row))
"""


def _program(gate: str, checks: Path, home: Path) -> str:
    """The child program, with its four inputs bound as literals.

    Bound by prepending assignments rather than by `str.format`: the child body
    contains braces of its own, and a formatted template that silently swallows
    one is a plant that plants nothing.
    """
    header = (
        f"SCRIPTS = {str(REPO / 'scripts')!r}\n"
        f"CHECKS = {str(checks)!r}\n"
        f"GATE = {gate!r}\n"
        f"HOME = {str(home)!r}\n"
        f"WITNESS = {WITNESS!r}\n"
    )
    return header + _CHILD


def _child_env() -> dict[str, str]:
    """The child's environment, NAMED and never inherited (D3.344).

    The real `scripts/` is kept on it deliberately: that is the condition every
    committed suite runs under (`sys.path.insert(0, REPO/"scripts")` and then
    `Context(nix_home=tree)`), so the probe changes ONE thing relative to an
    ordinary run — the home — rather than starving the child of its imports and
    manufacturing a refusal.
    """
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/root"),
        "PYTHONPATH": str(REPO / "scripts"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    # `USER`/`LOGNAME` are kept for a MEASURED reason, not for tidiness: without
    # them `check_plane1_degraded`'s ephemeral cluster came up owned by a role
    # `createdb` then could not find (`FATAL: role "bbt" does not exist`), and the
    # gate refused for that instead of for the corrupt subject. That is §7.12/4 —
    # a refusal manufactured by starving the child — committed by this very
    # function on its first draft, and caught by the stale-list control.
    for keep in (
        "USER",
        "LOGNAME",
        "PGHOST",
        "PGPORT",
        "PGUSER",
        "PGDATA",
        "LANG",
        "LC_ALL",
        "TMPDIR",
    ):
        if keep in os.environ:
            env[keep] = os.environ[keep]
    return env


def _run_child(gate: str, checks: Path, home: Path) -> dict:
    """One probe child. Returns its record, or a TIMEOUT/no-record row."""
    try:
        done = subprocess.run(  # nosec B603 - fixed argv, shell=False
            [sys.executable, "-c", _program(gate, checks, home)],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_S,
            check=False,
            env=_child_env(),
        )
    except subprocess.TimeoutExpired:
        return {"gate": gate, "status": "TIMEOUT", "detail": "the probe timed out"}
    line = next(
        (ln for ln in reversed(done.stdout.splitlines()) if ln.startswith("{")), ""
    )
    if not line:
        return {
            "gate": gate,
            "status": "NO-RECORD",
            "detail": f"child emitted no record; stderr={done.stderr[-400:]!r}",
        }
    row = json.loads(line)
    row["gate"] = gate
    return row


def _population() -> dict[str, tuple[str, ...]]:
    """gate -> its declared `.py` subjects that exist. Derived from the FOLDER."""
    out: dict[str, tuple[str, ...]] = {}
    for name, decl in read_all(REPO / "checks").items():
        subs = tuple(
            s for s in decl.subjects if s.endswith(".py") and (REPO / s).is_file()
        )
        if subs:
            out[name] = subs
    return out


@pytest.fixture(name="staged", scope="module")
def _staged(tmp_path_factory) -> Path:
    """One staged tree for the whole module. Copied, never symlinked into."""
    home = tmp_path_factory.mktemp("arc038g_home") / "tree"
    home.mkdir()
    for name in _STAGED_DIRS:
        src = REPO / name
        if src.is_dir() and not src.is_symlink():
            shutil.copytree(
                src,
                home / name,
                ignore=shutil.ignore_patterns("__pycache__", ".venv", ".venv-dev"),
            )
    for name in _STAGED_FILES:
        if (REPO / name).is_file():
            shutil.copy2(REPO / name, home / name)
    for name in ("logs", "downloads", "sessions", "state"):
        (home / name).mkdir(exist_ok=True)
    return home


@pytest.fixture(name="probed", scope="module")
def _probed(staged: Path) -> dict[str, dict]:
    """The whole population, probed once against ONE staged tree.

    Per gate: corrupt that gate's own declared subjects in the staged tree, run
    the gate against that tree in a child, restore the bytes. Sequential and
    restoring, so no gate is probed against another gate's plant.
    """
    population = _population()
    assert len(population) >= MIN_POPULATION, (
        f"population is {len(population)} gates, below the floor of "
        f"{MIN_POPULATION} — the probe would report a clean sheet over almost "
        "nothing (§7.12/1)"
    )
    out: dict[str, dict] = {}
    for gate, subjects in sorted(population.items()):
        saved: dict[str, bytes] = {}
        for rel in subjects:
            target = staged / rel
            assert target.is_file(), f"{gate}: {rel} absent from the staged tree"
            saved[rel] = target.read_bytes()
            target.write_text(CORRUPT, encoding="utf-8")
            assert target.read_text(encoding="utf-8") == CORRUPT, (
                f"{gate}: the plant did not apply at {target} (§7.12/2)"
            )
        try:
            row = _run_child(gate, REPO / "checks", staged)
        finally:
            for rel, blob in saved.items():
                (staged / rel).write_bytes(blob)
        row["subjects"] = list(subjects)
        out[gate] = row
    return out


# --------------------------------------------------------------- THE CONTROLS


def test_the_probe_child_resolved_the_tree_the_parent_NAMED(probed) -> None:
    """D3.344's closure, asserted rather than assumed.

    The child PRINTS the resolved `__file__` of a witness module from inside its
    own process. If these children were reaching some other tree, every verdict
    below would be about that tree and nothing here would say so — which is the
    whole of D3.344.
    """
    expected = str(REPO / "scripts" / "nixverify" / "contract.py")
    seen = {row["witness_file"] for row in probed.values() if "witness_file" in row}
    assert seen, "no child reported a witness path at all"
    assert seen == {expected}, (
        f"a probe child resolved {WITNESS} somewhere other than the named tree: "
        f"{sorted(seen)} (expected {expected!r})"
    )


def test_the_probe_is_not_mostly_TIMEOUT(probed) -> None:
    """A probe that timed out over the population is not a clean sheet (§7.12/5)."""
    stuck = sorted(
        g for g, r in probed.items() if r.get("status") in ("TIMEOUT", "NO-RECORD")
    )
    assert len(stuck) <= MAX_TIMEOUTS, (
        f"{len(stuck)} gate(s) produced no verdict, over the ceiling of "
        f"{MAX_TIMEOUTS}: {stuck}. Nothing below is a measurement."
    )


def test_control_the_STAGED_TREE_is_a_working_tree(staged: Path) -> None:
    """§7.12/4. With NOTHING corrupted, a sample of gates must reach a verdict
    that is not a complaint about the staging.

    Without this, every refusal below could be "your copy is broken" rather than
    "your subject does not parse", and the two are different facts.
    """
    for gate in ("check_limiter_gate", "check_reservation_lifecycle"):
        row = _run_child(gate, REPO / "checks", staged)
        assert row.get("status") == "PASS", (
            f"{gate} did not pass against the uncorrupted staged tree, so the "
            f"staging is not a working tree: {row}"
        )


def test_control_most_gates_REFUSE_a_home_whose_subject_does_not_parse(
    probed,
) -> None:
    """The unbroken half of the population. A probe on which nobody refused would
    mean the corruption never reached anything, and every PASS would be the
    harness rather than the gate."""
    refused = sorted(
        g
        for g, r in probed.items()
        if r.get("status") not in ("PASS", "TIMEOUT", "NO-RECORD")
    )
    assert len(refused) >= 40, (
        f"only {len(refused)} gate(s) noticed a corrupt subject at the home they "
        f"were given, which is too few for the PASSes to be attributable: {refused}"
    )


# ------------------------------------------------------- THE RATCHET, BOTH WAYS


def test_no_NEW_gate_certifies_over_a_subject_that_does_not_parse(probed) -> None:
    """A gate returning PASS here reads its subject somewhere other than the home
    it was handed. New instances are a REGRESSION, not accepted debt."""
    certified = sorted(g for g, r in probed.items() if r.get("status") == "PASS")
    unknown = sorted(set(certified) - set(KNOWN_ROOT_BLIND))
    assert not unknown, (
        "gate(s) returned PASS over a staged home in which their own declared "
        f"SUBJECTS are not valid Python, and are not on the measured list: "
        f"{unknown}. Each reads its subject through sys.path or through a REPO "
        "constant rather than through ctx.nix_home, so a staged-tree plant "
        "pointed at it is silently defeated (CHECK-DEBT D3.344 / D3.408). Either "
        "root the gate at ctx.nix_home, or make it REFUSE when the home it is "
        "given is not the tree its subject resolved from — see "
        "`check_picture_atomicity.subject_root_complaint`, which is that repair."
    )


def test_no_KNOWN_ROOT_BLIND_gate_has_quietly_been_repaired(probed) -> None:
    """The stale half. Without it the list only ever grows —
    `check_artifact_gate_coverage`'s §7.12 rule 3, one layer over."""
    stale = sorted(
        g
        for g in KNOWN_ROOT_BLIND
        if probed.get(g, {}).get("status") not in ("PASS", "TIMEOUT", "NO-RECORD")
    )
    assert not stale, (
        f"{stale} now REFUSE a home whose subject does not parse — they are "
        "repaired and must be deleted from KNOWN_ROOT_BLIND in the same commit. "
        "An accepted-defect list that outlives the defect is the drawer this "
        "ratchet exists to refuse."
    )


def test_every_KNOWN_ROOT_BLIND_entry_names_a_real_gate_and_a_reason() -> None:
    """A list entry with no gate behind it, or no reason, is decoration."""
    for gate, why in KNOWN_ROOT_BLIND.items():
        assert (REPO / "checks" / f"{gate}.py").is_file(), f"no such gate: {gate}"
        assert len(why.split()) >= 10, f"{gate}: the reason is too thin: {why!r}"


def test_the_REPAIRED_gate_is_not_on_the_list(probed) -> None:
    """`check_picture_atomicity` was the finding's exemplar and was repaired in
    this arc. It must be measured as repaired, here, by the same probe that
    found it."""
    assert "check_picture_atomicity" not in KNOWN_ROOT_BLIND
    row = probed["check_picture_atomicity"]
    assert row.get("status") == "CANNOT_MEASURE", row
    assert "THE TREE MEASURED IS NOT THE TREE NAMED" in row.get("detail", ""), row


# ------------------------------------------- §0a — THIS SUITE'S OWN CAN-FAIL


_SYNTHETIC_BLIND = '''\
"""A synthetic gate that certifies without reading its subject."""
import sys
sys.path.insert(0, SCRIPTS_DIR)
from nixverify.contract import CheckResult, Status
SUBJECTS = ("scripts/nixrisk/gate.py",)
DEPENDS_ON = ()
RESOURCES = ()
NAME = "check_arc038g_synthetic_blind"


def run(mode, ctx):
    return CheckResult(name=NAME, status=Status.PASS, evidence="looked at nothing")
'''

_SYNTHETIC_ROOTED = '''\
"""A synthetic gate that reads its subject AT ctx.nix_home."""
import ast
import sys
from pathlib import Path
sys.path.insert(0, SCRIPTS_DIR)
from nixverify.contract import CheckResult, Status
SUBJECTS = ("scripts/nixrisk/gate.py",)
DEPENDS_ON = ()
RESOURCES = ()
NAME = "check_arc038g_synthetic_rooted"


def run(mode, ctx):
    target = Path(ctx.nix_home) / SUBJECTS[0]
    try:
        ast.parse(target.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=SUBJECTS[0],
            detail=str(target) + " did not parse: " + repr(exc),
        )
    return CheckResult(name=NAME, status=Status.PASS, evidence="read it at nix_home")
'''


def _probe_synthetic(tmp_path: Path, body: str, name: str) -> dict:
    """Drive this suite's own mechanism against a gate written for the purpose."""
    checks = tmp_path / "checks"
    checks.mkdir()
    source = f"SCRIPTS_DIR = {str(REPO / 'scripts')!r}\n" + body
    (checks / f"{name}.py").write_text(source, encoding="utf-8")
    home = tmp_path / "home"
    target = home / "scripts" / "nixrisk" / "gate.py"
    target.parent.mkdir(parents=True)
    target.write_text(CORRUPT, encoding="utf-8")
    return _run_child(name, checks, home)


def test_CANFAIL_the_probe_catches_a_gate_that_certifies_over_nothing(
    tmp_path: Path,
) -> None:
    """THE UNPROTECTED HALF. A gate that never opens its subject must be caught.

    Without this the ratchet above could be structurally unable to see the class
    it names, and its green would be D3.16 exactly — doctrine C.3, prove
    non-vacuity BEFORE any plant, applied to the probe itself.
    """
    row = _probe_synthetic(tmp_path, _SYNTHETIC_BLIND, "check_arc038g_synthetic_blind")
    assert row.get("load_error") == "", row
    assert row.get("status") == "PASS", row
    # and the ratchet's own predicate, applied to it, must flag it
    unknown = sorted({"check_arc038g_synthetic_blind"} - set(KNOWN_ROOT_BLIND))
    assert unknown == ["check_arc038g_synthetic_blind"], unknown


def test_CANFAIL_the_probe_clears_a_gate_that_reads_its_subject_at_nix_home(
    tmp_path: Path,
) -> None:
    """THE PROTECTED HALF, which is what makes the red above attributable.

    Same probe, same corrupt home, one difference in the gate: this one resolves
    the subject through `ctx.nix_home`. It must not pass — and it must NAME the
    file it could not parse, never merely return a status (check contract 11).
    """
    row = _probe_synthetic(
        tmp_path, _SYNTHETIC_ROOTED, "check_arc038g_synthetic_rooted"
    )
    assert row.get("status") == "CANNOT_MEASURE", row
    assert "did not parse" in row.get("detail", ""), row
    assert "scripts/nixrisk/gate.py" in row.get("detail", ""), row
