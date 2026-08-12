#!/usr/bin/env python3
"""Gate: one artifact, one name — no manifest-as-identifier survives ARC 026 (B1).

## What this gate exists to stop

`checks/registry.json` is the master execution plan. ARC 010 renamed the FILE
from `verify_manifest.json` and stopped there, so the artifact wore two names one
layer apart: the file said `registry`, while the module (`nixverify/manifest.py`),
the exception (`ManifestError`), the loader (`load_manifest()`), the CLI flag
(`--manifest`) and the file's own version key (`manifest_version`) all said
`manifest`. That is this project's `ORDERS_OPEN` / `avg_price` failure class —
two live spellings of one thing, the last writer winning — and it is a defect
regardless of how the open operator ruling on the FILENAME lands, because
whichever name is chosen, only one of them may survive.

**THE FILE NAME IS NOT THIS GATE'S SUBJECT.** `registry.json` versus
`manifest.json` is an OPEN OPERATOR RULING and this gate takes no position on it:
it never reads the filename and would pass unchanged if the operator renamed the
file tomorrow. What it forbids is the *vocabulary* disagreeing with itself.

## Why identifiers and not the English word

`manifest` is a legitimate English word and, more importantly, a legitimate term
in the FROZEN risk spec: §5 is titled *"Rule Manifest, Executor & Threading
Model"*, and `risks/broker_order.config.json` refers to "the rule manifest"
correctly. A gate that banned the word would redden correct code that names a
different concept — doctrine B.4's `stream-no-compression` lesson exactly, where
a blanket ban would have reddened the REST path. So the ban is over a DECLARED
LIST OF IDENTIFIER SPELLINGS (`BANNED`), each of which names the execution plan
and nothing else.

## debug.md §7.12 — the standing question

**What would have to be true for this gate to PASS while measuring nothing?**

1. **The scanned population could be empty.** A `git ls-files` that returns
   nothing — wrong cwd, git absent, an inherited `GIT_DIR` pointing at another
   repository — yields "zero files, zero offenders, PASS". *Closed three ways:*
   git runs under `nixverify.gitenv.scrubbed_env()` so the environment cannot
   redirect it (D3.22); an empty or sub-credible population is CANNOT_MEASURE;
   and the scan must contain `WITNESS_PATHS` — the files that DID carry the
   vocabulary — or the gate reports that its scope has lost its subject.
2. **The banned list could be empty**, and every file would trivially pass.
   *Closed:* an empty `BANNED` is CANNOT_MEASURE, not a pass.
3. **The exemption list could grow until it covers the tree.** An exemption is
   how a gate is quietly unregistered without unregistering it (doctrine B.4).
   *Closed only partially, and stated rather than hidden:* `EXEMPT` is a short
   fixed tuple of HISTORICAL RECORDS — an amendment ledger, a session log, the
   architect's arc briefs, the changelog — whose whole function is to record what
   the vocabulary USED to be. Directive 6 forbids rewriting banked evidence, so
   these cannot be repaired and must be exempt. Nothing else may be added without
   the diff being read. **A future arc that widens `EXEMPT` to make a red go
   green is doing the forbidden thing.**
4. **The gate could exempt ITSELF.** It must name the spellings it bans, so its
   own source contains every one of them, and so does its test. Both are exempt
   by name — which means a real occurrence hidden inside either file would be
   invisible to this gate. That residual is real and is recorded as CHECK-DEBT
   D3.23 rather than argued away.
"""

# pylint: disable=duplicate-code
# R0801 pairs this module's §4.4 declaration preamble with the other gates that
# spawn `git`. THE DUPLICATION CANNOT BE FACTORED OUT AND THAT IS THE DESIGN:
# `PRIVILEGE`, `DEPENDS_ON`, `RESOURCES` and the rest are read STATICALLY, by AST,
# without importing the check, so a shared base module would be invisible to the
# reader they exist for. Every check carries its own literals by construction.
from __future__ import annotations

import subprocess  # nosec B404 - git ls-files, fixed argv, no shell
import sys
from pathlib import Path

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status
from nixverify.gitenv import scrubbed_env

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
DEPENDS_ON: tuple[str, ...] = ()
#: This gate SPAWNS git (`ls-files`). Declared because it is spawned, not because
#: anything is contended for — `check_observed_resource_claims` will report on
#: this file like any other, and if the observer sees more, the observer is right.
RESOURCES: tuple[str, ...] = ("subprocess:git",)
TIME_BOUND = False
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "a mechanical rename is exactly the repair that caused the defect: ARC 010 "
    "renamed the file and left the identifiers, and a --correct that swapped "
    "tokens would happily rewrite an amendment ledger's record of what the "
    "vocabulary used to be (directive 6). Report the site; let a human rename"
)
#: The registry is the artifact whose name this gate keeps coherent, and
#: `verify.py` is the consumer that reads it — both are genuinely measured here
#: (they are in the scan, and `WITNESS_PATHS` proves it on every run).
SUBJECTS: tuple[str, ...] = (
    "checks/registry.json",
    "scripts/verify.py",
)

NAME = "check_name_coherence"

#: Manifest-as-IDENTIFIER. Every entry names the execution plan and nothing else,
#: so none of them can collide with the frozen risk spec's "rule manifest" (§5)
#: or with the ordinary English word. Substring match is deliberate: these are
#: distinctive enough that a word-boundary regex would buy nothing and would miss
#: `nixverify.manifest` inside a dotted path.
BANNED: tuple[str, ...] = (
    "manifest_version",
    "ManifestError",
    "load_manifest",
    "--manifest",
    "nixverify/manifest.py",
    "nixverify.manifest",
    "<manifest>",
)

#: HISTORICAL RECORDS. Each one's function is to say what the vocabulary was, so
#: repairing it would destroy banked evidence (`CLAUDE.md` directive 6). See
#: §7.12 answer 3 — this tuple is the gate's own soft spot and must not grow to
#: make a red go green.
EXEMPT: tuple[str, ...] = (
    "docs/CHECK-CONTRACT-AMENDMENTS.md",  # the amendment ledger, by definition
    "docs/CHECK-DEBT.md",  # debt rows quote the vocabulary they owe against
    "sessions/SESSION.md",  # append-only arc history
    "CLAUDE-CHANGELOG.md",  # append-only instruction history
    "downloads/",  # the architect's arc briefs — not ours to edit
    "docs/superpowers/plans/",  # dated plan records, ARC 008-009; history, not code
    "checks/check_name_coherence.py",  # this file: it must name what it bans
    "scripts/tests/test_check_name_coherence.py",  # and so must its control
)

#: NON-VACUITY ANCHOR, and it anchors to an INVARIANT rather than to a count: the
#: two files that actually carried the vocabulary must be inside the scan. If a
#: future refactor moves them, this gate goes CANNOT_MEASURE and says so, which is
#: the honest outcome — a scope that has silently lost its subject is failure mode
#: #14 and is precisely what doctrine C.3 requires be asserted BEFORE any plant.
WITNESS_PATHS: tuple[str, ...] = ("scripts/verify.py", "checks/registry.json")

#: Below this the enumeration is not credible. A floor, never today's count —
#: a threshold equal to the current number reddens the moment a file is added.
MIN_CREDIBLE_FILES = 20

#: Binary and generated trees this gate cannot read as text. Not an exemption
#: from the rule: nothing under here can hold a Python identifier this project
#: consumes, and a decode error would otherwise be reported as a defect.
_SKIP_SUFFIXES = (".docx", ".png", ".jpg", ".pdf", ".sqlite", ".db")


def tracked_files(home: Path) -> tuple[list[str], str]:
    """Every git-tracked path under `home`. Returns (paths, error).

    `git ls-files` and not a filesystem walk: the tracked set is what a reviewer
    sees and what every other gate in this project scopes to. The environment is
    scrubbed (D3.22) so an inherited `GIT_DIR` cannot silently point the
    enumeration at a different repository.
    """
    git = "git"
    try:
        # nosec B603 B607 - fixed argv, shell=False, no user input. `git` from
        # PATH deliberately, matching check_canonical_tree's reasoning: this must
        # be the same git the operator and the hooks invoke.
        proc = subprocess.run(  # nosec B603 B607
            [git, "-C", str(home), "ls-files"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=scrubbed_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [], f"git ls-files failed: {exc!r}"
    if proc.returncode != 0:
        return [], f"git ls-files exit {proc.returncode}: {proc.stderr.strip()}"
    return sorted(line for line in proc.stdout.splitlines() if line.strip()), ""


def _exempt(rel: str) -> bool:
    """True when `rel` is a historical record this gate may not repair."""
    return any(rel == item or rel.startswith(item) for item in EXEMPT)


def _offenders_in(rel: str, text: str) -> list[tuple[str, str]]:
    """Every `(site, why)` a single file's text carries.

    Split from `offenders` so the enumeration and the scan are separately
    readable; the scan is the part a reviewer has to trust.
    """
    found: list[tuple[str, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for token in BANNED:
            if token in line:
                found.append(
                    (
                        f"{rel}:{number}",
                        (
                            f"manifest-as-identifier {token!r} survives — the "
                            f"execution plan has one name and it is `registry` "
                            f"(ARC 026 B1): {line.strip()[:160]}"
                        ),
                    )
                )
    return found


def _readable(home: Path, rel: str) -> str | None:
    """A scannable file's text, or None when it is not one this gate reads."""
    if _exempt(rel) or rel.endswith(_SKIP_SUFFIXES):
        return None
    path = home / rel
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return None


def offenders(home: Path, paths: list[str]) -> list[tuple[str, str]]:
    """Every `(site, why)` where a banned identifier survives outside EXEMPT.

    The site names `path:line`, and the reason quotes the token AND the line —
    doctrine C.2 requires the gate name the site, and the check contract §18
    requires the reason be asserted rather than an exit code.
    """
    found: list[tuple[str, str]] = []
    for rel in paths:
        text = _readable(home, rel)
        if text is not None:
            found.extend(_offenders_in(rel, text))
    return found


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Scan the tracked tree for manifest-as-identifier and report every site."""
    home = Path(ctx.nix_home)
    if not BANNED:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail="BANNED is empty — every file would pass having been tested "
            "against nothing (§7.12 answer 2)",
        )
    paths, error = tracked_files(home)
    if error:
        return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
    if len(paths) < MIN_CREDIBLE_FILES:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=(
                f"only {len(paths)} tracked file(s) enumerated at {home}, below the "
                f"credibility floor of {MIN_CREDIBLE_FILES} — a tiny or empty "
                "population would make every file trivially clean"
            ),
        )
    missing = [w for w in WITNESS_PATHS if w not in paths]
    if missing:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=(
                f"the scan does not contain {missing} — these are the files that "
                "carried the vocabulary this gate purged, so a scope without them "
                "cannot demonstrate it is still looking where the defect lives "
                "(doctrine C.3)"
            ),
        )
    scanned = [p for p in paths if not _exempt(p) and not p.endswith(_SKIP_SUFFIXES)]
    evidence = (
        f"{len(paths)} tracked file(s), {len(scanned)} in scope after "
        f"{len(EXEMPT)} historical-record exemption(s); {len(BANNED)} banned "
        f"identifier spelling(s) {list(BANNED)}; witnesses {list(WITNESS_PATHS)} "
        "present in scope"
    )
    defects = offenders(home, paths)
    if defects:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site="; ".join(site for site, _ in defects[:20]),
            evidence=evidence,
            detail="; ".join(f"{site}: {why}" for site, why in defects[:20]),
        )
    return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)


if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
