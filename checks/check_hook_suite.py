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
import os
import re
import subprocess  # nosec B404 - fixed argv, shell=False, no user input
import sys
from pathlib import Path
from typing import NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

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
    """
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


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


def hook_set_defects(payload: dict) -> tuple[list[tuple[str, str]], list[str]]:
    """Arms 3 and 4 over the resolved hook set. Returns (defects, advisories)."""
    defects: list[tuple[str, str]] = []
    advisories: list[str] = []
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
    for repo in payload["repos"]:
        if repo["local"]:
            continue
        if not repo["store_path"]:
            defects.append(
                (
                    f"{CONFIG_FILE}:{repo['repo']}@{repo['rev']}",
                    (
                        "no environment installed for the pinned rev — "
                        "pre-commit's store has no row for it"
                    ),
                )
            )
        elif repo["store_path"] not in repo["hook_prefixes"]:
            defects.append(
                (
                    f"{CONFIG_FILE}:{repo['repo']}@{repo['rev']}",
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


# ===========================================================================
# VERDICT
# ===========================================================================


def _cannot_measure(detail: str) -> CheckResult:
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


def _vacuity_complaint(payload: dict) -> str:
    """§7.12 conditions 1, 2 and 5: an empty measurement is never a PASS."""
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
    complaint = _vacuity_complaint(answer.payload)
    if complaint:
        return answer, f"{complaint} (§5.3: an empty scope is never a PASS)"
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
        defects = hook_file_defects(layout, answer.payload.get("is_our_script"))
        set_defects, advisories = hook_set_defects(answer.payload)
        defects.extend(set_defects)

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
    hooks = all_hooks(config, store) if _environments_all_present(records) else []
    classifier = Classifier.from_config(files, "", "^$") if files else None
    return {
        "hooks": _resolved_hooks(hooks, records, classifier),
        "repos": records,
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
    if "--probe" in sys.argv[1:]:
        sys.exit(_probe_main(Path(sys.argv[sys.argv.index("--probe") + 1])))

    from nixverify.contract import exit_code_for, validate_result

    HOME = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().parent.parent
    )
    OUTCOME = validate_result(
        run(Mode.VERIFY, Context(nix_home=HOME, mode=Mode.VERIFY))
    )
    print(f"{OUTCOME.status.value}: {OUTCOME.evidence or OUTCOME.detail}")
    if OUTCOME.detail and OUTCOME.evidence:
        print(f"  detail: {OUTCOME.detail}")
    sys.exit(exit_code_for(OUTCOME.status))
