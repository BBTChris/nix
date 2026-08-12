#!/usr/bin/env python3
"""Stage 3 runtime gate — a pytest run that cannot report green having measured nothing.

Invoked by the `pytest-affected` pre-commit hook. `.pre-commit-config.yaml` carries the
`debug.md` §7.12 answer for the hook as a whole; this docstring carries the answer for the
gate program, and the two are meant to be read together.

WHY THIS EXISTS (CHECK-DEBT D2.13, opened ARC 017, discharged ARC 018)
----------------------------------------------------------------------
The hook used to be `entry: ./.venv/bin/pytest --testmon`. Measured ARC 017 on pytest 9.1.1
+ testmon 2.2.0: a warm run with an unchanged dependency graph prints `changed files: 0`,
`collected 0 items`, `no tests ran`, and exits **0**. That is the normal steady state, so
the gate reported GREEN having executed nothing on most commits.

The defect is NOT that testmon selects nothing. Selecting nothing is correct when nothing
changed. The defect is that a run which measured nothing was **indistinguishable from a run
that measured everything and passed**. This program makes those two outcomes different.

TWO DESIGNS REJECTED, because the rejection is the argument
-----------------------------------------------------------
* **Full sweep on every commit.** Trades a silent-green defect for a slow gate people route
  around, which is worse by §7.12's own logic. Escalation here is conditional, so the fast
  incremental path stays the default for the case it is genuinely good at.
* **A floor on the collected count** (`assert n >= k`). `k` is a literal anchor (`debug.md`
  §8 failure mode #4) that goes stale the moment the suite changes, and it still cannot tell
  "nothing changed" from "the selector is broken".

VERDICTS
--------
    MEASURED-PASS     exit 0   SELECTED > 0 and every selected test passed
    FAIL              exit 1   pytest failed; pytest named the site in its own output
    SELECTOR-BROKEN   exit 1   nothing selected, yet the db record disagrees with the tree,
                               or the db records a failed test nobody re-ran
    SCOPE-BLIND       exit 2   a file changed against HEAD that the db has no fingerprint for
    NOTHING-SELECTED  exit 2   nothing selected and nothing contradicts it — the legitimate
                               "nothing changed" outcome, and it is CANNOT-MEASURE, not PASS
    CANNOT-MEASURE    exit 2   db unreadable, or pytest wrote no parsable report

Exit 2 is kept distinct from exit 1 deliberately: `VERIFY-AND-CHECKS.md` B.2 and `debug.md`
§8 failure mode #10 both require "could not measure" to be a different signal from "measured
and it is bad".

EVERY zero-selection verdict except CANNOT-MEASURE is terminal ONLY under
`NIX_RUNTIME_GATE=noescalate`, which exists so the taxonomy stays demonstrable. On the
default path — what a commit uses — they all escalate to a non-incremental run, and the
verdict name is carried into `mode=full-escalated(NAME:why)` so the reason for the escalation
is still on the record. `CANNOT-MEASURE` on an unreadable database stays terminal: if the
database cannot be read, the escalated run's own bookkeeping is equally untrustworthy.

WHY DRIFT ESCALATES RATHER THAN FAILING — MEASURED IN ARC 018 PHASE 4, AND THE FIRST DESIGN
WAS WRONG
--------------------------------------------------------------------------------------------
`SELECTOR-BROKEN` originally terminated on `drift and selected == 0`. Integration proved that
unusable, and the reproduction is one line: append a comment to any test file and run the
gate twice.

    RUNTIME-GATE drift (db record does not match tree content): scripts/tests/test_check_venv.py
    RUNTIME-GATE verdict: SELECTOR-BROKEN - 2 in-scope file(s) differ ... yet nothing was
    selected                                                                        exit 1

Both runs identical — it does not self-clear, so a commit touching only comments or
docstrings is permanently red with a verdict naming a selector that is working correctly.

The cause is a real asymmetry, not a bug in either tool: this gate's corroboration is
**content-based** (a git blob hash of the file), while testmon's selection is **semantic**
(per-method checksums). A behaviour-neutral edit — a comment, a docstring, a reformat —
legitimately changes the content hash while changing no method checksum, so testmon correctly
selects nothing and the file correctly reads as drift. Content drift is therefore evidence
that the record is *stale*, which is NOT the same claim as "the selector is broken", and the
old arm conflated the two.

Escalating preserves the property that matters (a commit is never waved through unmeasured)
without asserting a diagnosis the evidence does not support: the full run measures
everything, so a subsequent pass is honest, and `drift=` still names every affected file on
the scope line. The A2-ii demonstration — a deliberately corrupted `fsha` reading as
SELECTOR-BROKEN — is unchanged under `noescalate`, which is how it was demonstrated in the
first place.

HOW THE SCOPE NUMBER IS OBTAINED
--------------------------------
`SELECTED` comes from **pytest's own JUnit XML**, not from scraping stdout. A gate that
parses the prose of the tool it is measuring inherits every wording change as a silent
failure.

Corroboration is **independent of testmon**: `file_fp.fsha` is a git-blob SHA-1, and this
program recomputes it from the working tree with `hashlib` rather than asking testmon what
changed. Both of testmon's spellings are accepted — the plain blob hash for a clean file,
and testmon's character-length variant from `read_source_sha` for a dirty one — so a
non-ASCII source file cannot produce a false red.

Note that testmon's own change detection is git-index-driven, not purely content-driven
(`noncached_get_files_shas` shells out to `git ls-files --stage -m`). The gate's scope
therefore depends on git state as well as file content, which is why the fingerprint is a
git blob hash and not a plain sha256.

§7.12 — WHAT WOULD HAVE TO BE TRUE FOR THIS GATE TO PASS WHILE MEASURING NOTHING
--------------------------------------------------------------------------------
1. GUARDED. Zero selection. Reported as NOTHING-SELECTED (exit 2) or escalated to a full run.
2. GUARDED. A stale, corrupt or foreign `.testmondata`. Its state is printed on every run and
   is part of the verdict: `db=`, `known_files=`, `drift=`, `alien_env=`. Measured ARC 018 —
   zeroing one `file_fp.fsha` produced `collected 0` / exit 0 under the old entry, and
   `SELECTOR-BROKEN` / exit 1 here.
3. GUARDED. A tracked source file with no fingerprint in the graph. Measured ARC 018 —
   `scripts/nixverify/__init__.py` was in every other hook's scope and had no fingerprint at
   all; changing it selected nothing and the old gate was green over a real, tracked, changed
   file. Now `SCOPE-BLIND`, and `uncovered=` lists such files by name on every run.
4. UNGUARDED — a test in a file the db has no fingerprint for **that is also unchanged
   against HEAD**. Nothing selects it and nothing flags it. Visible only on the incremental
   path; the escalated run does execute it.
5. UNGUARDED — testmon's method-level `method_checksums` blobs are not re-verified. Only the
   per-file `fsha` is corroborated.
6. UNGUARDED, AND NOT CLOSEABLE HERE — this gate proves what ran. It cannot prove the suite
   is **adequate**. A green MEASURED-PASS over a suite that asserts nothing is still green.
7. NARROWED, NOT CLOSED — `.testmondata` is still untracked and still per-machine. Its state
   became visible and load-bearing; it did not become **reviewable**. Two people on the same
   commit can still get different scopes — but they can now both see that they did.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import sqlite3
import subprocess  # nosec B404 - fixed argv, shell=False, no untrusted input
import sys
import tempfile
import xml.etree.ElementTree as ET  # nosec B405 - input is our own mkstemp file, see run_pytest
from dataclasses import dataclass, field

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

# pylint: disable=wrong-import-position
from nixverify.gitenv import scrubbed_env

#: Excluded from scope for the same reason every pre-commit hook excludes it: the
#: `databases/schema/` tree is verbatim-extracted DB-spec artifact, never lint-fixed.
_SCHEMA_PREFIX = "databases/schema/"

#: Set to "noescalate" to make SCOPE-BLIND / NOTHING-SELECTED terminal instead of escalating.
#: Exists so the taxonomy is demonstrable; a commit never sets it.
_NOESCALATE_ENV = "NIX_RUNTIME_GATE"


@dataclass
class DbState:
    """What the gate could learn about `.testmondata` before running anything."""

    state: str = "absent"
    known: dict[str, set[str]] = field(default_factory=dict)
    envs: list[str] = field(default_factory=list)
    recorded_tests: int = 0
    recorded_failures: int = 0
    uncovered: list[str] = field(default_factory=list)
    drift: list[str] = field(default_factory=list)


def blob_shas(path: pathlib.Path) -> set[str]:
    """Both git-blob SHA-1 spellings testmon may have recorded for `path`.

    testmon stores a git blob hash, but computes the header length from the *decoded*
    normalised text for a dirty file (`read_source_sha`) and from the raw bytes for a clean
    one. Accepting both is what keeps a non-ASCII source file from reading as drift.
    """
    raw = path.read_bytes()
    normalised = raw.replace(b"\f", b" ").replace(b"\r\n", b"\n")
    plain = hashlib.sha1(b"blob %u\0" % len(raw), usedforsecurity=False)  # nosec B324
    plain.update(raw)
    decoded_len = len(normalised.decode("utf-8", "replace"))
    variant = hashlib.sha1(b"blob %u\0" % decoded_len, usedforsecurity=False)  # nosec B324
    variant.update(normalised)
    return {plain.hexdigest(), variant.hexdigest()}


def git(*args: str) -> list[str]:
    """Whitespace-split stdout of a git command, or [] if it failed.

    THE ENVIRONMENT IS SCRUBBED, AND FOR THIS CALLER IT IS THE POINT (D3.22).
    `git` honours `GIT_DIR`, `GIT_WORK_TREE` and `GIT_INDEX_FILE` **ahead of `cwd`**,
    and *this program is invoked by `pre-commit`, from inside a `git commit`, with those
    variables exported*. It was the one git caller in the tree with no scrub at all while
    being the most exposed: `main()` derives the gate's entire SCOPE from `git ls-files`
    and its changed set from `git diff --name-only HEAD`, so an inherited `GIT_INDEX_FILE`
    sets what this gate measures. A scope silently set by ambient tracking state is
    `debug.md` §8 failure mode #14, and it is the same mechanism that bared this repository.

    Nothing is lost by scrubbing: on the normal path the variables git exports point at the
    repository `cwd` already resolves to, so the answers are identical. They differ only in
    the case this exists to refuse.
    """
    proc = subprocess.run(  # nosec B603 - literal argv, shell=False
        ("git",) + args,
        capture_output=True,
        text=True,
        check=False,
        env=scrubbed_env(),
    )
    return proc.stdout.split() if proc.returncode == 0 else []


def read_db(db: pathlib.Path, scope: list[str], root: pathlib.Path) -> DbState:
    """Read `.testmondata` and corroborate its record against the working tree."""
    out = DbState()
    if not db.exists():
        return out
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        for filename, fsha in con.execute("select filename, fsha from file_fp"):
            out.known.setdefault(filename, set()).add(fsha)
        out.envs = [
            f"{name}@{version}"
            for name, version in con.execute(
                "select environment_name, python_version from environment"
            )
        ]
        out.recorded_tests, out.recorded_failures = con.execute(
            "select count(*), coalesce(sum(failed),0) from test_execution"
        ).fetchone()
        con.close()
        out.state = "present"
    except (sqlite3.Error, OSError, ValueError) as exc:
        out.state = f"unreadable({type(exc).__name__})"
        return out
    out.uncovered = [f for f in scope if f not in out.known]
    out.drift = [
        f for f in scope if f in out.known and not out.known[f] & blob_shas(root / f)
    ]
    return out


def run_pytest(extra: list[str]) -> tuple[int, int, int]:
    """Run pytest with `extra`, returning (returncode, tests_run, tests_bad).

    Counts come from pytest's own JUnit XML. (-1, -1) means no parsable report, which is a
    CANNOT-MEASURE rather than an assumption that zero ran.
    """
    handle, xml_path = tempfile.mkstemp(suffix=".xml")
    os.close(handle)
    rc = subprocess.run(  # nosec B603 - sys.executable with a literal argv
        [sys.executable, "-m", "pytest", "--junit-xml=" + xml_path] + extra, check=False
    ).returncode
    total = bad = -1
    try:
        # nosec B314 - not untrusted XML: `xml_path` is a mkstemp file created three lines
        # above and written only by the pytest subprocess we just spawned. Pulling in
        # defusedxml would add a runtime dependency to harden against an attacker who
        # would already have to control our own temp file to exploit it.
        root = ET.parse(xml_path).getroot()  # nosec B314
        suite = root if root.tag == "testsuite" else root.find("testsuite")
        if suite is not None:
            total = int(suite.get("tests") or 0)
            bad = int(suite.get("failures") or 0) + int(suite.get("errors") or 0)
    except ET.ParseError, OSError, TypeError, ValueError:
        pass
    os.unlink(xml_path)
    return rc, total, bad


@dataclass
class Run:
    """One invocation of the gate: what it knew, and what it has measured so far."""

    db: DbState
    scope: list[str]
    mode: str = "incremental"
    selected: int = -1

    def emit(self) -> None:
        """Print the gate's own scope. A gate that cannot say what it measured is not evidence."""
        major, minor, micro = sys.version_info[:3]
        alien = [e for e in self.db.envs if not e.endswith(f"@{major}.{minor}.{micro}")]
        print(
            f"RUNTIME-GATE scope: db={self.db.state} known_files={len(self.db.known)} "
            f"in_scope_files={len(self.scope)} uncovered={len(self.db.uncovered)} "
            f"drift={len(self.db.drift)} recorded_tests={self.db.recorded_tests} "
            f"recorded_failures={self.db.recorded_failures} "
            f"env={','.join(self.db.envs) or '-'} alien_env={len(alien)} "
            f"mode={self.mode} SELECTED={self.selected}"
        )
        if self.db.uncovered:
            print(
                "RUNTIME-GATE uncovered (a change to these selects no test): "
                + " ".join(self.db.uncovered)
            )
        if self.db.drift:
            print(
                "RUNTIME-GATE drift (db record does not match tree content): "
                + " ".join(self.db.drift)
            )

    def verdict(self, name: str, code: int, why: str = "") -> None:
        """Emit scope, print the verdict, and exit. Never returns."""
        self.emit()
        print(f"RUNTIME-GATE verdict: {name}{(' - ' + why) if why else ''}")
        raise SystemExit(code)


def _zero_selection(run: Run, blind: list[str]) -> str:
    """Handle a run that selected nothing (or was blind to a change). Returns the new mode.

    Every terminal outcome here exits via `Run.verdict`; returning means the caller escalates.
    """
    db = run.db
    if db.state.startswith("unreadable"):
        # Terminal even with escalation available: if the database cannot be read, the
        # escalated run's own bookkeeping is equally untrustworthy. Refusing to guess is
        # the whole point of keeping CANNOT-MEASURE distinct from FAIL.
        run.verdict(
            "CANNOT-MEASURE",
            2,
            "testmon database present but unreadable, so scope is unknowable",
        )

    if run.selected == 0 and db.drift:
        name, code = "SELECTOR-BROKEN", 1
        why = f"{len(db.drift)} in-scope file(s) differ from the db record yet nothing was selected"
    elif run.selected == 0 and db.recorded_failures:
        name, code = "SELECTOR-BROKEN", 1
        why = (
            f"db records {db.recorded_failures} failed test(s) yet nothing was selected"
        )
    elif blind:
        name, code = "SCOPE-BLIND", 2
        why = "changed-but-uncovered:" + ",".join(blind)
    else:
        name, code = "NOTHING-SELECTED", 2
        why = "zero-selection"

    if os.environ.get(_NOESCALATE_ENV) == "noescalate":
        run.verdict(
            name,
            code,
            f"{why}; escalation suppressed by {_NOESCALATE_ENV}=noescalate; "
            f"this run measured {max(run.selected, 0)} test(s)",
        )
    return f"full-escalated({name}:{why})"


def main() -> None:
    """Run the gate. Exits with the taxonomy code; never returns normally."""
    root = pathlib.Path.cwd()
    scope = [f for f in git("ls-files", "*.py") if not f.startswith(_SCHEMA_PREFIX)]
    staged = set(git("diff", "--name-only", "HEAD"))
    run = Run(db=read_db(root / ".testmondata", scope, root), scope=scope)

    rc, run.selected, bad = run_pytest(["--testmon"])
    blind = sorted(set(run.db.uncovered) & staged)

    if run.selected < 0:
        run.verdict(
            "CANNOT-MEASURE", 2, "pytest wrote no parsable report; the gate did not run"
        )
    if run.selected == 0 or blind:
        run.mode = _zero_selection(run, blind)
        rc, run.selected, bad = run_pytest(["--testmon-noselect"])
        if run.selected <= 0:
            run.verdict(
                "CANNOT-MEASURE",
                2,
                "the escalated full run also selected nothing; the suite itself is empty",
            )
    if rc != 0 or bad:
        run.verdict(
            "FAIL",
            1,
            f"{bad} of {run.selected} selected test(s) failed; pytest named the site above",
        )
    run.verdict("MEASURED-PASS", 0)


if __name__ == "__main__":
    main()
