#!/usr/bin/env python3
"""The pre-commit suite is wired in, and the hook set that runs is the one configured.

NARROWS CHECK-DEBT D1.10. All eight hooks are demonstrated able to FAIL — D3.1
through D3.6 record the plants one by one. **Nothing asserted they were wired
in.** An uninstalled `pre-commit`, a `.git/hooks/pre-commit` overwritten by
another tool, a `core.hooksPath` pointing somewhere else, a hook whose `files:`
pattern selects nothing, or a hook environment that was never installed all
produce a clean commit history *with no gate having run*. That is the last
standing shape of "a green light that measured nothing" — `debug.md` §7.12 — and
it is the one shape a per-hook can-fail cannot see, because a can-fail is taken
by invoking the hook by hand.

ONE gate, ONE property (`nix_check_contract.md` §5.5, doctrine C.9): *the
configured hook suite is effectively installed and effectively complete.* Every
arm below is a way for that one property to be false.

------------------------------------------------------------------------------
EFFECTIVE STATE, NOT DECLARED STATE — doctrine C.1
------------------------------------------------------------------------------
`pre-commit install` having been run once is a declaration. `pre-commit` being
in the venv is a declaration. `rev:` being pinned is a declaration. None of them
is evidence. What this gate reads instead:

  ARM 1 — THE GIT-LEVEL HOOK, AS GIT WILL RESOLVE IT.
      The hooks directory comes from `git rev-parse --git-path hooks`, which is
      git's own answer and is the ONLY form that is correct in every layout: it
      honours `core.hooksPath`, and in a linked WORKTREE it returns the common
      directory's `hooks/` rather than the worktree's private git dir. MEASURED
      ARC 019 inside a linked worktree whose `.git` is a FILE:
        --git-dir         .../.git/worktrees/<name>
        --git-common-dir  .../.git
        --git-path hooks  .../.git/hooks        <- the shared, real one
      A gate that had built the path itself as `<--git-dir>/hooks` would have
      looked at a directory that does not exist and reported "not installed" in
      every worktree, or — worse, had it been written to tolerate absence —
      reported green while measuring nothing. The environment the gate ran in is
      reported in `evidence` on every run (`layout=worktree` / `layout=repo`),
      because `debug.md` §8 failure mode #12 is a proof taken in one environment
      presented as a claim about another.

      The file must exist, be executable, and be PRE-COMMIT'S OWN — decided by
      calling `pre_commit.commands.install_uninstall.is_our_script()`, which
      compares against the template hashes that ship with the installed
      pre-commit. That is a derived anchor: upgrade pre-commit and the answer
      comes from the new package, not from a string written down here.

  ARM 2 — THE HOOK POINTS AT THIS CONFIG.
      pre-commit's generated hook embeds `ARGS=(hook-impl --config=<path>
      --hook-type=pre-commit)`. The gate reads that line back and asserts the
      config it names is the config this gate parsed, and that the hook type is
      `pre-commit`. This is what catches an installed hook that is real,
      executable, pre-commit's own — and pointed at a different file. It also
      asserts the hook's `INSTALL_PYTHON` interpreter exists, because a missing
      one silently demotes the hook to whatever `pre-commit` is on `PATH`.

  ARM 3 — EVERY CONFIGURED HOOK WILL ACTUALLY RUN, AND WILL SEE FILES.
      The expected hook set is DERIVED FROM THE CONFIG by pre-commit's own
      resolver (`all_hooks(load_config(...), Store())`) — never from a snapshot
      list in this file, so a hook added tomorrow is covered tomorrow with no
      edit here. For each resolved hook the gate asserts its installed
      environment directory exists, and that pre-commit's own `Classifier`
      selects a NON-EMPTY file set for it over `git.get_all_files()`, unless the
      hook is `always_run`.

      THE ZERO-SELECTION ARM IS THE "SILENTLY DROPPED" DETECTOR, and it is worth
      being explicit about why it is the right one. "No hook has been dropped"
      cannot be checked against the config, because the config IS the authority
      for what is configured — delete a hook and both sides of any config-derived
      comparison lose it together. What CAN be checked is that every hook still
      has a subject: a `files:` regex that stops matching, an `exclude:` that
      grew to cover everything, or a subject that left `git ls-files` (D1.16,
      failure mode #14) all leave the hook configured, installed, and reading
      nothing. pre-commit prints `Skipped` for those and exits 0. That is a hook
      dropped in every sense that matters.

  ARM 4 — THE ENVIRONMENT EACH HOOK RUNS IN IS THE ONE ITS `rev:` PINS.
      For every non-local repo in the config, the gate looks up `(repo, rev)` in
      pre-commit's own store database and asserts (a) a row exists, (b) its path
      exists on disk, and (c) that path is the prefix `all_hooks` handed back for
      the hooks of that repo. A missing row means the environment was never
      installed and the first commit will either install it or fail; a mismatched
      path means the hook will run somewhere other than where the pin says.

      This arm is also the reason the gate does NOT let pre-commit clone. The
      store lookup happens FIRST and a missing row is a FAILURE, not an
      invitation to fetch. A gate that runs at boot and weekly must not reach the
      network, and a gate that repairs the thing it measures has destroyed its
      own evidence.

      ARC 028 (C3), CHECK-DEBT D3.29 — **THIS ARM WAS UNREACHABLE AND IS NOT
      ANY MORE.** The refusal-to-clone above has a consequence the first
      spelling did not follow through: when an environment is missing,
      `all_hooks` is not called, so the resolved hook set is EMPTY — and the
      vacuity guard one layer up turned that empty set into CANNOT_MEASURE
      *"resolved to ZERO hooks"* before arm 4 ever ran. ARC 027 found it by
      attempting the plant (`PRE_COMMIT_HOME` at an empty directory against the
      REAL repository) and measured the gate reporting zero hooks while it held,
      in the same payload, the exact `(repo, rev)` with no store row. Not a
      false green — CANNOT_MEASURE withholds certification — but it cost the
      operator doctrine C.2's naming.
      **The repair is ordering:** `repo_defects` runs BEFORE `_vacuity_complaint`,
      so a missing environment is reported as the FAILURE it is, naming
      `repo@rev`, and only a zero hook set with no environment defect behind it
      is still CANNOT_MEASURE. The prefix-agreement branch keeps its old
      position, because it is only meaningful when hooks were actually resolved;
      `hooks_resolved` in the payload says which world the verdict came from.

------------------------------------------------------------------------------
THE CACHED-BANDIT QUESTION — answered, and the answer is "partly"
------------------------------------------------------------------------------
ARC 018 re-measured the pre-ARC-010 bandit environment and classified it as
**owed, not acceptable standing risk**: that cached environment is still on this
machine and still reproduces the ARC 006 vacuum verbatim — every production file
"exception while scanning file", zero findings, **exit 0** — while the pinned
1.9.4 environment flags the same planted `shell=True` High and exits 1.

WHAT THIS GATE DOES DETECT. Arm 4 proves the environment each hook will actually
run in is the store row keyed to the rev the config pins, so it can say that the
stale sibling is not the one being used. It also NAMES every other resident
environment for the same repo as an advisory on every run, so "there is more than
one bandit env on this box" stops being something only a person who went looking
knows. MEASURED ARC 019: the store holds bandit at both `1.8.6` and `1.9.4`, and
the hooks resolve to the `1.9.4` path.

WHAT IT DOES NOT DETECT, and this is the part that stays owed. It cannot tell
whether the PINNED environment is itself vacuous. Nothing structural
distinguishes a bandit that scans 21 files from one that raises on all 21 and
exits 0 — only running it against a known-bad input does, which is a per-hook
canary plant, which is exactly what the D3 series is and exactly what D1.10 says
"capturing it by hand is not a gate". Checking out a commit that moves the pin
therefore still re-arms the vacuum with no visible change to any instrument.

**That is a different property from this gate's, so it is a different row, not a
silent gap: CHECK-DEBT D3.7.** Recorded rather than folded in, because folding it
in would let a green from this gate be read as covering it.

------------------------------------------------------------------------------
§7.12 THE STANDING QUESTION — what would have to be true for this gate to PASS
while measuring nothing?
------------------------------------------------------------------------------
Eight conditions, each stated so it could be planted.

 1. The config file is absent or holds an empty `repos:` list, so the derived
    hook set is empty and a loop over zero hooks reports no problems.
    GUARDED: a missing config is CANNOT_MEASURE naming the path, and an empty
    resolved hook set is CANNOT_MEASURE, never PASS.
    **NARROWED ARC 028 (C3), and the narrowing is the D3.29 repair.** An empty
    hook set is no longer answered the same way whatever caused it. When the
    cause is a pinned rev with no installed environment, that is arm 4's FAIL,
    named `repo@rev`; CANNOT_MEASURE is reserved for an empty set with no
    environment defect behind it. A guard that answers "I could not measure"
    about a state it has fully measured is a guard shadowing a real arm.

 2. `git.get_all_files()` returns nothing — an empty repository, a `git` that
    did not run, a wrong cwd — so every hook's selection is legitimately zero and
    arm 3 has nothing to compare.
    GUARDED: the tracked-file count is asserted non-zero and printed on every
    run. Arm 3 is skipped-as-CANNOT_MEASURE rather than passed if it is zero.

 3. The probe subprocess fails to import pre-commit — no venv, a broken
    interpreter — and its empty answer reads as "no hooks are broken".
    GUARDED: the probe reports structured JSON or the gate is CANNOT_MEASURE
    (exit 2, distinct from FAIL — doctrine B.2, failure mode #10). An arm that
    could not run is never an arm that passed.

 4. The gate looks for the hook in the WRONG directory and treats absence as
    "nothing installed here, fine". This is the worktree trap and it is the
    reason arm 1 exists in the shape it does.
    GUARDED: the path comes from `git rev-parse --git-path hooks`, absence is a
    FAILURE and never a skip, and the resolved layout is printed so a reader can
    see which of the two environments produced the verdict.

 5. Arm 3 is satisfied vacuously because every hook is `always_run`. A suite of
    `always_run` hooks has no selection to collapse, so the zero-selection
    detector has no subject.
    NOT A DEFECT BUT NOT INVISIBLE EITHER: the count of file-scoped hooks that
    were actually selection-checked is printed on every run. If it ever reads 0
    the arm has lost its subject and the number says so. It is not made a
    failure, because an all-`always_run` suite is a legitimate configuration.

 6. UNGUARDED, AND THE REAL LIMIT — the pinned hook environment is itself
    vacuous. Every arm here is structural; none of them runs a hook against a
    known-bad input. A bandit that scans nothing and exits 0 satisfies arms 1-4
    completely. See the cached-bandit block above; the row is CHECK-DEBT D3.7.

 7. UNGUARDED — `git commit --no-verify`. The suite can be perfectly installed
    and simply bypassed. `debug.md` §6 says an undisclosed bypass is
    indistinguishable from a gate that never ran, and no static gate can see one:
    it needs a reflog or a CI-side assertion, which is CHECK-DEBT D2.4's
    territory (nothing banks a verdict at an arc boundary).

 8. UNGUARDED — hook types other than `pre-commit`. This gate asserts the
    `pre-commit` hook only. `pre-push`, `commit-msg` and friends are not
    configured in this repo today, so asserting them would be a rule with no
    subject; if one is added, this gate will not notice that it was never
    installed. Plantable: add a `default_install_hook_types` entry and observe
    that nothing here changes.
"""

from __future__ import annotations

import json
import re
import subprocess  # nosec B404 - fixed argv, shell=False, no user input
import sys
from pathlib import Path
from typing import NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status
from nixverify.gitenv import scrubbed_env

# R0801 (duplicate-code) is disabled at module scope for the same reason every
# other gate carries it: `nix_check_contract.md` §4.2 requires each
# checks/check_*.py be independently runnable and map status -> exit code
# identically, and doctrine B.2 requires the crash path return CANNOT_MEASURE in
# both. Those blocks are MANDATED to be the same text; the only way to
# deduplicate them is a shared helper, which §4.2 forbids.
# pylint: disable=duplicate-code
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

NAME = "check_hook_suite"

# --- ARC 025 orchestration declarations (read statically, never imported) ---
#: DEPENDS ON THE VENV, and cannot repair it. `_probe_interpreter` prefers
#: `.venv/bin/python3` and falls back to `sys.executable` — which is the ENGINE's
#: interpreter, where `pre_commit` is not installed — so an absent venv turns
#: every arm into `probe output unparseable`. The gate then reports honestly and
#: measures nothing, which is a coverage defect set by the box's state rather
#: than by the subject.
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: THE HOOKS DIRECTORY IS SHARED AND THE SHARING IS MEASURED, NOT ASSUMED: on
#: this box `git rev-parse --git-path hooks` resolves to
#: `/home/bbt/nix/.git/hooks` from ALL FIVE worktrees (the repository and four
#: linked ones), i.e. one directory, five potential writers. The gate only READS
#: it, but a parallel block member that wrote it would be altering the commit
#: gate of every concurrently-running worktree.
#: `pre-commit-store` is `PRE_COMMIT_HOME` — arms 3 and 4 read the installed
#: environments there, and it is shared with every other worktree in exactly the
#: same way.
#: ARC 025 Stage 2.4 — `subprocess:git` added after the runtime observer caught
#: it. This gate asks git itself where hooks resolve (`git rev-parse
#: --git-path hooks`), which is the whole reason it is not fooled by a hook
#: installed at the conventional path while `core.hooksPath` points elsewhere —
#: so spawning git is load-bearing, not incidental, and it was undeclared.
RESOURCES: tuple[str, ...] = (
    "git-hooks",
    "pre-commit-store",
    "venv",
    "subprocess:git",
)
#: TIME-BOUND, and this is the one gate here where the bound really does
#: dominate: the probe subprocess resolves pre-commit's store and classifies
#: every tracked file for eight hooks. `EXPECTED_S` is derived from
#: `_PROBE_TIMEOUT` below — the module's own constant — never from an observed
#: run (§4.4). One probe invocation, so the bound is that constant.
TIME_BOUND = True
EXPECTED_S = 180.0
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the only repair this gate's subject admits is `pre-commit install`, which "
    "writes `/home/bbt/nix/.git/hooks/pre-commit` — MEASURED as the single "
    "directory all five worktrees resolve, so one worktree's --correct rewrites "
    "the commit gate every other worktree is committing through, mid-commit. "
    "This gate's own companion suite already refuses to write there for exactly "
    "that reason (scripts/tests/test_check_hook_suite.py: uninstalling the hook "
    "to prove a can-fail 'would disarm the gate for whatever else is committing "
    "at the time'), and a --correct that wrote what the tests refuse to write "
    "would make the gate more dangerous than the drift it repairs. Arms 3 and 4 "
    "are not repairable at all without editing .pre-commit-config.yaml or "
    "mutating the shared store"
)
#: `.pre-commit-config.yaml` is the artifact this gate measures — the hook set is
#: DERIVED from it on every run, never snapshotted. It is not in
#: `check_artifact_gate_coverage`'s tracked set (that gate includes only `.py`
#: and `.json`), so declaring it adds no coverage there; it is declared because
#: SUBJECTS states what a check measures, not what happens to be enumerated.
SUBJECTS: tuple[str, ...] = (".pre-commit-config.yaml",)

CONFIG_FILE = ".pre-commit-config.yaml"
HOOK_TYPE = "pre-commit"

# pre-commit writes `ARGS=(hook-impl --config=<path> --hook-type=<type>)` into
# the hook it generates. Read back, never rewritten.
_ARGS_LINE = re.compile(r"^ARGS=\((.*)\)\s*$", re.MULTILINE)
_INSTALL_PYTHON = re.compile(r"^INSTALL_PYTHON=(.*)$", re.MULTILINE)

_PROBE_TIMEOUT = 180


class Probe(NamedTuple):
    """The venv-side answer, or the reason there is not one."""

    payload: dict
    complaint: str


# ===========================================================================
# GIT — effective paths, from git itself (§7.12 condition 4).
# ===========================================================================


def _clean_git_env() -> dict[str, str]:
    """The ambient environment with every `GIT_*` variable removed.

    MEASURED ARC 019, and this is not a hypothetical. git exports `GIT_DIR`,
    `GIT_INDEX_FILE` and friends into every hook it runs, and those variables
    take precedence over `cwd`. A `git` invocation that inherits them answers
    about the repository that STARTED the hook, not the one at `cwd` — so this
    gate, run from inside a pre-commit hook, would report the hook state of a
    different repository while looking as though it had measured `nix_home`.
    That is `debug.md` §8 failure mode #12 with a mechanism.

    It was found the hard way: the companion test suite's throwaway-repository
    fixture shelled out to `git init` / `git add -A` / `git commit` inside
    `tmp_path` during a real `git commit`, inherited `GIT_DIR`, and committed
    against the worktree instead. Stripping the prefix makes `cwd` the only
    thing that decides which repository is being asked.

    **ARC 026 (B4): the prefix rule this function pioneered is now the shared
    one.** `nixverify.gitenv.scrubbed_env` strips `GIT_*` exactly as this did —
    the two weaker private copies elsewhere in the check population were raised
    to it rather than this one being lowered to them. Behaviour here is
    unchanged; the name is kept because the committed suite asserts on it.
    """
    return scrubbed_env()


def _git(nix_home: Path, *args: str) -> str | None:
    """One `git` query about `nix_home`. None when git could not answer.

    Never a guessed path: a question git declines to answer is reported as
    unanswered, and the caller turns that into a FAILURE rather than a skip.
    """
    try:
        # nosec B603 B607 - fixed argv, shell=False, no user input. `git` is
        # resolved from PATH deliberately: the check contract's own floor
        # component list treats git as a system tool (D1.7), and hardcoding a
        # path here would be a literal anchor to one distribution's layout.
        proc = subprocess.run(  # nosec B603 B607
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            cwd=str(nix_home),
            env=_clean_git_env(),
        )
    except OSError, subprocess.SubprocessError:
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


class GitLayout(NamedTuple):
    """Where git will look for hooks, and which repository layout produced it."""

    hooks_dir: Path | None
    layout: str
    hooks_path_config: str | None


def git_layout(nix_home: Path) -> GitLayout:
    """Resolve the hooks directory the way git resolves it, in any layout.

    `--git-path hooks` is deliberately used instead of composing
    `<git-dir>/hooks`: in a linked worktree the git dir is private and holds no
    `hooks/`, while the hooks git will actually run live in the common dir.
    """
    raw = _git(nix_home, "rev-parse", "--git-path", "hooks")
    git_dir = _git(nix_home, "rev-parse", "--git-dir")
    common = _git(nix_home, "rev-parse", "--git-common-dir")
    layout = "unknown"
    if git_dir and common:
        layout = "repo" if Path(git_dir).name == Path(common).name else "worktree"
    hooks = None
    if raw:
        candidate = Path(raw)
        hooks = candidate if candidate.is_absolute() else (nix_home / candidate)
    return GitLayout(hooks, layout, _git(nix_home, "config", "--get", "core.hooksPath"))


# ===========================================================================
# ARM 1 + ARM 2 — the installed hook file.
# ===========================================================================


def _hook_args(text: str) -> list[str]:
    match = _ARGS_LINE.search(text)
    return match.group(1).split() if match else []


def hook_file_defects(layout: GitLayout, is_ours: bool | None) -> list[tuple[str, str]]:
    """Arms 1 and 2 over the resolved hook file. Absence is a FAILURE, not a skip."""
    if layout.hooks_dir is None:
        return [
            (
                "git rev-parse --git-path hooks",
                "git did not answer; cannot locate the hook",
            )
        ]
    hook = layout.hooks_dir / HOOK_TYPE
    if not hook.is_file():
        return [
            (
                str(hook),
                (
                    "no pre-commit hook installed at the path git resolves — "
                    "`pre-commit install` has not been run, or it was removed"
                ),
            )
        ]
    defects: list[tuple[str, str]] = []
    if not hook.stat().st_mode & 0o111:
        defects.append((str(hook), "hook file is not executable; git will not run it"))
    if is_ours is False:
        defects.append(
            (
                str(hook),
                (
                    "hook exists but is NOT pre-commit's own script "
                    "(pre_commit.is_our_script said no) — it was overwritten"
                ),
            )
        )
    text = hook.read_text(encoding="utf-8", errors="replace")
    args = _hook_args(text)
    wanted_config = f"--config={CONFIG_FILE}"
    if wanted_config not in args:
        defects.append(
            (
                str(hook),
                (
                    f"installed hook does not name {CONFIG_FILE}; its ARGS are "
                    f"{args} — the hook that runs is configured by a different "
                    f"file than the one this gate checked"
                ),
            )
        )
    if f"--hook-type={HOOK_TYPE}" not in args:
        defects.append((str(hook), f"installed hook is not a {HOOK_TYPE} hook: {args}"))
    interpreter = _INSTALL_PYTHON.search(text)
    if interpreter and not Path(interpreter.group(1).strip()).is_file():
        defects.append(
            (
                str(hook),
                (
                    f"hook's INSTALL_PYTHON {interpreter.group(1).strip()!r} does "
                    f"not exist; the hook silently falls back to whatever "
                    f"`pre-commit` is on PATH, or to exit 1"
                ),
            )
        )
    return defects


# ===========================================================================
# ARMS 3 + 4 — the resolved hook set. Computed venv-side; see `_probe_main`.
# ===========================================================================


def _probe_interpreter(nix_home: Path) -> Path:
    """The venv, whose pre-commit is the one the git hook will import."""
    venv = nix_home / ".venv" / "bin" / "python3"
    return venv if venv.is_file() else Path(sys.executable)


def probe(nix_home: Path) -> Probe:
    """Re-enter this module under the venv to ask pre-commit about itself.

    The program lives in this file and is re-entered, rather than being an
    `entry:`-style source string: CHECK-DEBT D2.16 is the measured instance of a
    gate's own program sitting outside every linter, type checker and test, and
    the repair recorded there was to make it ordinary tracked code.

    The probe runs with `GIT_*` stripped for the reason `_clean_git_env` records:
    pre-commit's own `git.get_all_files()` would otherwise enumerate whichever
    repository exported those variables, and arm 3's selection counts would be
    taken against the wrong tree while reading as though they were `nix_home`'s.
    """
    argv = [
        str(_probe_interpreter(nix_home)),
        str(Path(__file__).resolve()),
        "--probe",
        str(nix_home),
    ]
    try:
        proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
            argv,
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT,
            check=False,
            cwd=str(nix_home),
            env=_clean_git_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return Probe({}, f"probe did not run ({exc!r})")
    try:
        return Probe(json.loads(proc.stdout), "")
    except json.JSONDecodeError:
        tail = (proc.stderr or proc.stdout or "").strip()[-400:]
        return Probe({}, f"probe output unparseable — {tail}")


def hook_defects(payload: dict) -> list[tuple[str, str]]:
    """ARM 3 — every resolved hook is installed and has a subject to read."""
    defects: list[tuple[str, str]] = []
    for hook in payload["hooks"]:
        key = hook["key"]
        if not hook["prefix_exists"]:
            defects.append(
                (
                    f"{CONFIG_FILE}:{key}",
                    (
                        f"hook environment {hook['prefix']} does not exist — the "
                        f"hook is configured but was never installed"
                    ),
                )
            )
        if hook["always_run"]:
            continue
        if hook["selected"] == 0:
            defects.append(
                (
                    f"{CONFIG_FILE}:{key}",
                    (
                        "hook selects ZERO files — configured, installed, and "
                        "reading nothing; pre-commit reports this as `Skipped` "
                        "and exits 0"
                    ),
                )
            )
    return defects


def repo_defects(payload: dict) -> tuple[list[tuple[str, str]], list[str]]:
    """ARM 4 — the environment each pinned rev names. Returns (defects, advisories).

    ARC 028 (C3), D3.29. Split out of `hook_set_defects` so `run` can ask it
    BEFORE the vacuity guard: an environment that is not installed is precisely
    the state that empties the hook set, so an arm that runs after the empty-set
    check can never see its own subject.

    `hooks_resolved` defaults True for a caller that hands over a payload with
    no such key — the prefix-agreement branch compares against prefixes
    `all_hooks` produced, and when `all_hooks` was never called those lists are
    empty for EVERY repo, which would turn one missing environment into a
    spurious mismatch for all of them.
    """
    resolved = payload.get("hooks_resolved", True)
    defects: list[tuple[str, str]] = []
    advisories: list[str] = []
    for repo in payload["repos"]:
        if repo["local"]:
            continue
        site = f"{CONFIG_FILE}:{repo['repo']}@{repo['rev']}"
        if not repo["store_path"]:
            defects.append(
                (
                    site,
                    (
                        "no environment installed for the pinned rev — "
                        "pre-commit's store has no row for it"
                    ),
                )
            )
        elif not repo.get("store_path_exists", True):
            defects.append(
                (
                    site,
                    (
                        f"the pinned rev's store row names {repo['store_path']}, "
                        f"which is not a directory — pre-commit's store has a row "
                        f"for an environment that is no longer on disk"
                    ),
                )
            )
        elif resolved and repo["store_path"] not in repo["hook_prefixes"]:
            defects.append(
                (
                    site,
                    (
                        f"hooks resolve to {repo['hook_prefixes']} but the pinned "
                        f"rev's store row is {repo['store_path']} — the hook will "
                        f"not run in the environment the pin names"
                    ),
                )
            )
        if repo["other_revs"]:
            advisories.append(
                f"RESIDENT-SIBLING {repo['repo']} pinned {repo['rev']}, other "
                f"environment(s) still on disk for rev(s) "
                f"{', '.join(repo['other_revs'])} — not used by this config; "
                f"whether a pinned environment is itself vacuous is CHECK-DEBT D3.7"
            )
    return defects, advisories


def hook_set_defects(payload: dict) -> tuple[list[tuple[str, str]], list[str]]:
    """Arms 3 and 4 together. One rule, two callers (doctrine C.9).

    `run` calls the two halves separately and in order; this composition is kept
    because it is the predicate the committed suite drives field by field over a
    real payload, and two spellings of one rule would disagree the first time
    either was edited.
    """
    repo_found, advisories = repo_defects(payload)
    return hook_defects(payload) + repo_found, advisories


# ===========================================================================
# VERDICT
# ===========================================================================


def _cannot_measure(detail: str) -> CheckResult:
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


def _vacuity_complaint(payload: dict) -> str:
    """§7.12 conditions 1, 2 and 5: an empty measurement is never a PASS.

    ARC 028 (C3): reached only AFTER `repo_defects`. A zero hook set caused by an
    uninstalled environment is now arm 4's FAIL, named `repo@rev`; what survives
    to here is a zero hook set with no environment defect behind it — an empty
    `repos:` list, a config that resolves nothing — which is genuinely something
    this gate could not measure.
    """
    if not payload.get("hooks"):
        return (
            f"{CONFIG_FILE} resolved to ZERO hooks — a loop over no hooks finds nothing"
        )
    if not payload.get("all_files"):
        return (
            "git reports zero tracked files, so every file-scoped hook selects "
            "zero legitimately and arm 3 has no subject"
        )
    return ""


def _evidence(payload: dict, layout: GitLayout, advisories: list[str]) -> str:
    """What was measured, in which environment, on every run."""
    hooks = payload["hooks"]
    scoped = [h for h in hooks if not h["always_run"]]
    selections = ", ".join(f"{h['key']}={h['selected']}" for h in hooks)
    return (
        f"layout={layout.layout}, hooks_dir={layout.hooks_dir}, "
        f"core.hooksPath={layout.hooks_path_config or 'unset'}, "
        f"is_our_script={payload.get('is_our_script')}; "
        f"{len(hooks)} hook(s) derived from {CONFIG_FILE} over "
        f"{payload['all_files']} tracked file(s), {len(scoped)} file-scoped and "
        f"selection-checked; selections {selections}; "
        f"{len(payload['repos'])} repo(s), pinned revs "
        f"{[r['rev'] for r in payload['repos'] if not r['local']]}; "
        + ("; ".join(advisories) if advisories else "0 advisories")
    )


def _preflight(nix_home: Path) -> tuple[Probe, str]:
    """Run the probe and decide whether its answer is believable at all.

    Every rejection here is CANNOT_MEASURE, never FAIL: doctrine B.2 and failure
    mode #10 — a gate that did not measure must not report a violation.
    """
    if not (nix_home / CONFIG_FILE).is_file():
        return Probe({}, ""), (
            f"{nix_home / CONFIG_FILE} is absent — nothing to derive a hook set from"
        )
    answer = probe(nix_home)
    if answer.complaint:
        return answer, f"{answer.complaint} (one arm is not the gate)"
    if answer.payload.get("error"):
        return answer, f"probe reported: {answer.payload['error']}"
    return answer, ""


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Four arms over the effective state. Never installs, never clones, never repairs.

    A gate that installs the thing it measures has destroyed the evidence that it
    was missing, and this one runs at boot and weekly with no operator present.
    """
    try:
        answer, complaint = _preflight(ctx.nix_home)
        if complaint:
            return _cannot_measure(complaint)

        layout = git_layout(ctx.nix_home)
        # ARM 4 FIRST (ARC 028 / C3, D3.29). A missing environment is the state
        # that empties the hook set, so it must be judged before the empty set
        # is judged — otherwise the cause is reported as an inability to measure
        # its own effect, and the operator loses the `repo@rev`.
        env_defects, advisories = repo_defects(answer.payload)
        if env_defects:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in env_defects),
                evidence=_evidence(answer.payload, layout, advisories),
                detail="; ".join(f"{site}: {why}" for site, why in env_defects),
            )

        vacuity = _vacuity_complaint(answer.payload)
        if vacuity:
            return _cannot_measure(f"{vacuity} (§5.3: an empty scope is never a PASS)")

        defects = hook_file_defects(layout, answer.payload.get("is_our_script"))
        defects.extend(hook_defects(answer.payload))

        evidence = _evidence(answer.payload, layout, advisories)
        if defects:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in defects),
                evidence=evidence,
                detail="; ".join(f"{site}: {why}" for site, why in defects),
            )
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1 —
        # exit 1 would report a violation the gate never observed.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# ===========================================================================
# THE PROBE — runs under the venv, where pre-commit is importable.
# ===========================================================================


def _store_rows(store) -> dict[tuple[str, str], str]:  # type: ignore[no-untyped-def]
    """Every (repo, rev) -> path pre-commit's own store knows about.

    Read directly out of the store database rather than inferred, so a pinned
    rev with no installed environment is a MISSING ROW rather than a clone.
    """
    import sqlite3  # pylint: disable=import-outside-toplevel

    path = Path(store.db_path)
    if not path.is_file():
        return {}
    with sqlite3.connect(str(path)) as conn:
        return {
            (repo, ref): where
            for repo, ref, where in conn.execute("SELECT repo, ref, path FROM repos")
        }


def _repo_records(config: dict, rows: dict[tuple[str, str], str]) -> list[dict]:
    """One record per configured repo, carrying its pinned rev's store row.

    `other_revs` is every OTHER environment the store holds for the same repo —
    the cached-sibling visibility that the ARC 018 bandit finding asked for.
    """
    records = []
    for entry in config["repos"]:
        source = entry["repo"]
        local = source in ("local", "meta")
        rev = entry.get("rev", "")
        records.append(
            {
                "repo": source,
                "rev": rev,
                "local": local,
                "store_path": None if local else rows.get((source, rev)),
                # ARC 028 (C3): a row whose DIRECTORY is gone is a different
                # defect from a row that was never written, and the first
                # spelling of arm 4 could see only the second — while
                # `_environments_all_present` already treated both as absent,
                # so the missing directory emptied the hook set and produced a
                # vacuity complaint with no site in it.
                "store_path_exists": bool(
                    not local
                    and rows.get((source, rev))
                    and Path(str(rows.get((source, rev)))).is_dir()
                ),
                "other_revs": sorted(
                    ref for (repo, ref) in rows if repo == source and ref != rev
                ),
                "hook_prefixes": [],
            }
        )
    return records


def _environments_all_present(records: list[dict]) -> bool:
    """True when every non-local repo's pinned rev has an installed environment.

    Consulted BEFORE `all_hooks`, because `all_hooks` would install a missing one
    — and a gate that repairs what it measures has destroyed its own evidence.
    """
    return not any(
        not record["local"]
        and (not record["store_path"] or not Path(record["store_path"]).is_dir())
        for record in records
    )


def _record_for(records: list[dict], source: str) -> dict | None:
    for record in records:
        if record["repo"] == source:
            return record
    return None


def _resolved_hooks(  # type: ignore[no-untyped-def]
    hooks: list, records: list[dict], classifier
) -> list[dict]:
    """Flatten pre-commit's own Hook objects into the probe's JSON shape."""
    resolved = []
    for hook in hooks:
        record = _record_for(records, hook.src)
        if record is not None and hook.prefix.prefix_dir not in record["hook_prefixes"]:
            record["hook_prefixes"].append(hook.prefix.prefix_dir)
        resolved.append(
            {
                "key": hook.alias or hook.id,
                "id": hook.id,
                "name": hook.name,
                "always_run": hook.always_run,
                "prefix": hook.prefix.prefix_dir,
                "prefix_exists": Path(hook.prefix.prefix_dir).is_dir(),
                "selected": len(list(classifier.filenames_for_hook(hook)))
                if classifier
                else 0,
            }
        )
    return resolved


def _probe_payload(nix_home: Path) -> dict:
    """pre-commit's own answer about itself, computed under the venv."""
    # Imported here, not at module scope: the engine may run this check under the
    # stdlib-only system interpreter, where pre_commit does not exist.
    # pylint: disable=import-outside-toplevel,import-error
    from pre_commit import git
    from pre_commit.clientlib import load_config
    from pre_commit.commands.install_uninstall import is_our_script
    from pre_commit.commands.run import Classifier
    from pre_commit.repository import all_hooks
    from pre_commit.store import Store

    config = load_config(str(nix_home / CONFIG_FILE))
    store = Store()
    records = _repo_records(config, _store_rows(store))
    files: list[str] = git.get_all_files()
    resolved = _environments_all_present(records)
    hooks = all_hooks(config, store) if resolved else []
    classifier = Classifier.from_config(files, "", "^$") if files else None
    return {
        "hooks": _resolved_hooks(hooks, records, classifier),
        "repos": records,
        # ARC 028 (C3): whether `all_hooks` was actually called. Without it a
        # consumer cannot tell an empty `hook_prefixes` list that MEANS a
        # mismatch from one that only means the resolver was never run.
        "hooks_resolved": resolved,
        "all_files": len(files),
        "is_our_script": is_our_script(
            str(Path(_hooks_dir_for_probe(nix_home)) / HOOK_TYPE)
        ),
    }


def _probe_main(nix_home: Path) -> int:
    """`--probe <nix_home>`: print pre-commit's own answer about itself as JSON."""
    try:
        payload = _probe_payload(nix_home)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        payload = {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(payload))
    return 0


def _hooks_dir_for_probe(nix_home: Path) -> str:
    """Git's own hooks path, resolved probe-side so `is_our_script` reads the real file."""
    resolved = git_layout(nix_home).hooks_dir
    return str(resolved) if resolved else str(nix_home / ".git" / "hooks")


# Deliberately duplicated across every checks/check_*.py: the check
# contract (§4.2) requires each module be independently runnable, so this
# block cannot be factored into a shared helper without breaking that.
# The disable pragma must be on its own line, not trailing on the `if` —
# pylint's Similarities checker (R0801) does not honour a same-line
# trailing disable comment here (verified empirically, pylint v4.0.6).
# pylint: disable=duplicate-code
if __name__ == "__main__":
    # `--probe` is this module re-entering itself under the venv interpreter to
    # ask pre-commit about itself. It is not an actuation verb and is
    # intercepted before `parse_actuation`, which would reject it.
    if "--probe" in sys.argv[1:]:
        sys.exit(_probe_main(Path(sys.argv[sys.argv.index("--probe") + 1])))

    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
