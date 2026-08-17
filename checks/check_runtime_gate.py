#!/usr/bin/env python3
"""The Stage 3 pre-commit runtime gate, DRIVEN — `scripts/runtime_gate.py`.

ONE gate, FOUR properties CHECK-DEBT D2.16 opened this program for (a pytest
run that must not report green having measured nothing) and its own 24-test
suite `scripts/tests/test_runtime_gate.py` already drives in isolation — this
gate is what makes that drive REACHABLE from `verify.py` rather than only
from a manual `pytest` invocation (D3.104: "measured by tests; no check
declares it"):

  1. **`blob_shas` corroborates testmon's record independently of testmon**,
     cross-checked against the real `git hash-object` on a sample file, and
     produces BOTH spellings for a non-ASCII file (so it cannot false-drift).
  2. **`read_db` classifies db state and correctly computes `uncovered`/
     `drift`** against real file content in a real sqlite `.testmondata`.
  3. **The verdict taxonomy's arms are each distinguishable by NAME**, not
     merely by exit code: CANNOT-MEASURE (unreadable, terminal even with
     escalation available), SELECTOR-BROKEN (drift, and separately recorded
     failures — noescalate terminal), SCOPE-BLIND vs NOTHING-SELECTED, and
     escalation happening by DEFAULT (the Phase-4 regression guard: drift
     must never terminate red on a behaviour-neutral edit).
  4. **`run_pytest`'s counts come from JUnit XML, never from returncode
     alone**: no parsable report reads -1 (CANNOT-MEASURE), never an assumed
     0 (which would misroute into the zero-selection/escalation path on a
     gate that never actually ran).

WHY EVERY SUBPROCESS CALL IS PATCHED, EXCEPT `git hash-object`. Driving
`main()` would spawn pytest from inside pytest/verify.py (the module's own
test suite refuses this for the same reason); every internal decision point
`main()` delegates to is driven directly instead, with `subprocess.run`
replaced by a controlled double everywhere it stands in for pytest. The one
REAL subprocess call this gate makes is `git hash-object` against a tmp file
it creates itself — the same real-oracle cross-check the module's own test
suite uses, chosen because a corroboration double that computed testmon's
hash algorithm from the SAME formula as the subject would prove nothing.

§7.12 — WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING?

 1. The subject could fail to load. CLOSED: CANNOT_MEASURE naming the
    exception (§17, never a PASS).
 2. `read_db`'s drift/uncovered sets could be checked only in the arm that
    finds something, which a function that ALWAYS reports drift would also
    pass. CLOSED: a clean, correctly-fingerprinted file is driven and
    required to raise NEITHER flag (the vacuous-control class the module's
    own suite calls out by name).
 3. The verdict taxonomy could be checked only by exit code, which SEVERAL
    arms share (exit 1: drift vs recorded-failures; exit 2: unreadable vs
    blind vs nothing-selected). CLOSED: every arm's assertion reads the
    printed verdict NAME and the reason clause, never the code alone.
 4. Escalation-by-default could go untested, leaving the Phase-4 regression
    (drift terminating red on a comment-only edit) reachable again. CLOSED:
    the default-env drive requires `full-escalated(...)`, and the
    `noescalate`-env drive requires the SAME scenario to terminate instead —
    proving the escalation decision is real, not a fixed string.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sqlite3
import subprocess  # nosec B404 - fixed argv, shell=False, no untrusted input
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status
from nixverify.gitenv import scrubbed_env

# pylint: disable=duplicate-code,too-few-public-methods,too-many-locals
# missing-function-docstring,missing-class-docstring: the test doubles'
# verbs are named after the ports they stand in for, and each arm function's
# name states its own property (§7.12 answer per arm) — a docstring would
# restate the name. too-few-public-methods: several doubles are one-verb
# stand-ins for a frozen port's single relevant method. too-many-locals: an
# arm's local count is the drive's own inputs/outputs, not incidental state.
# pylint: disable=missing-function-docstring,missing-class-docstring
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = True
EXPECTED_S = 10.0
DEPENDS_ON: tuple[str, ...] = ()
#: `git hash-object` against a tmp file this gate creates itself (read-only
#: repository state; writes nothing) plus a scratch sqlite db under a tempdir.
#: `sys.modules["runtime_gate"]` is touched transiently (see `load`'s
#: docstring) and restored in a `finally`. `run_pytest`'s own double writes a
#: JUnit XML report via `tempfile.mkstemp`. `subprocess:git`/`subprocess:python`
#: match by basename (nixverify.observe.covers).
RESOURCES: tuple[str, ...] = (
    "file-write:/tmp",
    "interpreter:sys.modules",
    "subprocess:git",
    "subprocess:python",
)
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject decides whether a commit's own test evidence is trustworthy "
    "(D2.13's vacuity defect); an instrument empowered to edit its verdict "
    "taxonomy until its own drive came back clean would be deciding, "
    "unattended, what counts as a measured commit"
)
SUBJECTS: tuple[str, ...] = ("scripts/runtime_gate.py",)

NAME = "check_runtime_gate"

GATE_FILE = "scripts/runtime_gate.py"
GATE_MODULE = "runtime_gate"


class Finding(NamedTuple):
    site: str
    why: str


def load(home: Path) -> tuple[ModuleType | None, str]:
    """Load by EXACT FILE PATH — see `check_d1_12_reboot_capture.load` for why
    a flat module must never be resolved through a `sys.path` NAME search."""
    path = home / GATE_FILE
    if not path.is_file():
        return None, f"{GATE_FILE}: not present under {home} — nothing to measure (§17)"
    spec = importlib.util.spec_from_file_location(GATE_MODULE, path)
    if spec is None or spec.loader is None:
        return None, f"{GATE_FILE}: could not build an import spec for {path}"
    module = importlib.util.module_from_spec(spec)
    # Python's own `dataclasses` needs `sys.modules[cls.__module__]` populated
    # DURING class-body execution (it resolves annotations that way), so the
    # module must be registered under its OWN name for the duration of
    # `exec_module` — the standard `importlib` recipe. This is transient
    # bookkeeping, not a name-based search: the module was already located by
    # EXACT PATH above, so registering and immediately un-registering it
    # cannot cause the sys.path-search leak `check_d1_12_reboot_capture.load`
    # documents avoiding — nothing here ever asks "where is `runtime_gate`".
    previous = sys.modules.get(GATE_MODULE)
    sys.modules[GATE_MODULE] = module
    try:
        spec.loader.exec_module(module)
        return module, ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{GATE_FILE}: cannot execute {path} — {type(exc).__name__}: {exc}. "
            "The subject is unavailable, so nothing was measured (§17: never a PASS)"
        )
    finally:
        if previous is None:
            sys.modules.pop(GATE_MODULE, None)
        else:
            sys.modules[GATE_MODULE] = previous


def _make_db(path: Path, rows: list[tuple[str, str]], *, failed: int = 0) -> None:
    con = sqlite3.connect(path)
    con.execute("create table file_fp (filename text, fsha text)")
    con.execute("create table environment (environment_name text, python_version text)")
    con.execute("create table test_execution (failed int)")
    con.executemany("insert into file_fp values (?, ?)", rows)
    con.execute("insert into environment values ('default', '3.14.4')")
    con.execute("insert into test_execution values (?)", (failed,))
    con.commit()
    con.close()


# --------------------------------------------------------------------------
# ARM 1 — blob_shas, cross-checked against the real git binary
# --------------------------------------------------------------------------


def _arm_blob_shas(module: ModuleType, tmp: Path) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{GATE_FILE}:blob_shas"

    target = tmp / "sample.py"
    target.write_bytes(b"x = 1\n")
    try:
        proc = subprocess.run(  # nosec B603 B607 - literal argv, shell=False, read-only
            ["git", "hash-object", str(target)],
            capture_output=True,
            text=True,
            check=True,
            timeout=EXPECTED_S,
            # D3.205/D3.22 — an inherited GIT_OBJECT_DIRECTORY changes where this
            # oracle looks, and this gate compares its answer against the module's
            # own. Gated by `check_git_env_scrub`.
            env=scrubbed_env(),
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        return [
            Finding(site, f"could not run the real `git hash-object` oracle: {exc}")
        ]
    real_hash = proc.stdout.strip()
    shas = module.blob_shas(target)
    if real_hash not in shas:
        findings.append(
            Finding(
                site, f"real git hash {real_hash!r} not in blob_shas() output {shas!r}"
            )
        )

    unicode_target = tmp / "unicode.py"
    unicode_target.write_text('S = "café"\n', encoding="utf-8")
    uni_shas = module.blob_shas(unicode_target)
    if len(uni_shas) != 2:
        findings.append(
            Finding(
                site,
                f"a non-ASCII file produced {len(uni_shas)} spelling(s), expected 2",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM 2 — read_db: state classification + real uncovered/drift computation
# --------------------------------------------------------------------------


def _arm_read_db(module: ModuleType, tmp: Path) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{GATE_FILE}:read_db"

    absent = module.read_db(tmp / "no-such.testmondata", [], tmp)
    if absent.state != "absent":
        findings.append(
            Finding(
                site, f"a missing db read state={absent.state!r}, expected 'absent'"
            )
        )

    garbage = tmp / "garbage.testmondata"
    garbage.write_bytes(b"\x00\x01not a database")
    unreadable = module.read_db(garbage, [], tmp)
    if not unreadable.state.startswith("unreadable("):
        findings.append(
            Finding(
                site,
                f"a corrupt db read state={unreadable.state!r}, expected 'unreadable(...)'",
            )
        )

    covered = tmp / "covered.py"
    covered.write_bytes(b"a = 1\n")
    orphan = tmp / "orphan.py"
    orphan.write_bytes(b"b = 2\n")
    db = tmp / "real.testmondata"
    _make_db(db, [("covered.py", min(module.blob_shas(covered)))])
    present = module.read_db(db, ["covered.py", "orphan.py"], tmp)
    if present.state != "present":
        findings.append(
            Finding(site, f"a real db read state={present.state!r}, expected 'present'")
        )
    if present.uncovered != ["orphan.py"]:
        findings.append(
            Finding(site, f"uncovered={present.uncovered!r}, expected ['orphan.py']")
        )
    if present.drift:
        findings.append(
            Finding(
                site, f"a correctly-fingerprinted file read as drift: {present.drift!r}"
            )
        )

    tracked = tmp / "tracked.py"
    tracked.write_bytes(b"a = 1\n")
    drift_db = tmp / "drift.testmondata"
    _make_db(drift_db, [("tracked.py", "0" * 40)])
    drifted = module.read_db(drift_db, ["tracked.py"], tmp)
    if drifted.drift != ["tracked.py"]:
        findings.append(
            Finding(
                site,
                f"a corrupted fingerprint did not read as drift: {drifted.drift!r}",
            )
        )
    if drifted.uncovered:
        findings.append(
            Finding(site, "a tracked-but-drifted file was ALSO reported uncovered")
        )
    return findings


# --------------------------------------------------------------------------
# ARM 3 — the verdict taxonomy: named arms, not exit codes alone
# --------------------------------------------------------------------------


def _make_run(module: ModuleType, **kwargs: Any) -> Any:
    db = module.DbState(
        state=kwargs.pop("state", "present"),
        drift=kwargs.pop("drift", []) or [],
        uncovered=kwargs.pop("uncovered", []) or [],
        recorded_failures=kwargs.pop("recorded_failures", 0),
    )
    return module.Run(db=db, scope=["a.py"], selected=0)


def _capture_exit(fn, *args, **kwargs) -> tuple[int | str | None, str]:
    buf = io.StringIO()
    code: int | str | None = None
    with contextlib.redirect_stdout(buf):
        try:
            fn(*args, **kwargs)
        except SystemExit as exc:
            code = exc.code
    return code, buf.getvalue()


def _taxonomy_unreadable(module: ModuleType, site: str) -> list[Finding]:
    """Unreadable db: terminal (exit 2) even with escalation available."""
    os.environ.pop(module._NOESCALATE_ENV, None)  # pylint: disable=protected-access
    code, out = _capture_exit(
        module._zero_selection,  # pylint: disable=protected-access
        _make_run(module, state="unreadable(DatabaseError)"),
        [],
    )
    if code != 2 or "CANNOT-MEASURE" not in out or "escalation suppressed" in out:
        return [Finding(f"{site}:unreadable", f"code={code!r} out={out!r}")]
    return []


def _taxonomy_drift(module: ModuleType, site: str) -> list[Finding]:
    """Drift, noescalate: SELECTOR-BROKEN, exit 1, naming the count."""
    os.environ[module._NOESCALATE_ENV] = "noescalate"  # pylint: disable=protected-access
    code, out = _capture_exit(
        module._zero_selection,  # pylint: disable=protected-access
        _make_run(module, state="present", drift=["a.py"]),
        [],
    )
    if (
        code != 1
        or "SELECTOR-BROKEN" not in out
        or "in-scope file(s) differ" not in out
    ):
        return [Finding(f"{site}:drift", f"code={code!r} out={out!r}")]
    return []


def _taxonomy_recorded_failures(module: ModuleType, site: str) -> list[Finding]:
    """Recorded failures, noescalate: SELECTOR-BROKEN, exit 1, naming the count."""
    code, out = _capture_exit(
        module._zero_selection,  # pylint: disable=protected-access
        _make_run(module, state="present", recorded_failures=3),
        [],
    )
    if code != 1 or "SELECTOR-BROKEN" not in out or "3 failed test(s)" not in out:
        return [Finding(f"{site}:recorded-failures", f"code={code!r} out={out!r}")]
    return []


def _taxonomy_blind(module: ModuleType, site: str) -> list[Finding]:
    """Blind change: SCOPE-BLIND, exit 2."""
    code, out = _capture_exit(
        module._zero_selection,  # pylint: disable=protected-access
        _make_run(module, state="present", uncovered=["a.py"]),
        ["a.py"],
    )
    if code != 2 or "SCOPE-BLIND" not in out or "changed-but-uncovered:a.py" not in out:
        return [Finding(f"{site}:blind", f"code={code!r} out={out!r}")]
    return []


def _taxonomy_nothing_selected(module: ModuleType, site: str) -> list[Finding]:
    """Nothing changed, noescalate: NOTHING-SELECTED, exit 2 (never PASS — D2.13)."""
    code, out = _capture_exit(
        module._zero_selection,  # pylint: disable=protected-access
        _make_run(module, state="present"),
        [],
    )
    if code != 2 or "NOTHING-SELECTED" not in out:
        return [Finding(f"{site}:nothing-selected", f"code={code!r} out={out!r}")]
    return []


def _taxonomy_escalation(module: ModuleType, site: str) -> list[Finding]:
    """THE PHASE-4 REGRESSION GUARD: drift escalates by DEFAULT, never terminates."""
    os.environ.pop(module._NOESCALATE_ENV, None)  # pylint: disable=protected-access
    mode = module._zero_selection(  # pylint: disable=protected-access
        _make_run(module, state="present", drift=["a.py"]), []
    )
    if not str(mode).startswith("full-escalated(SELECTOR-BROKEN:"):
        return [
            Finding(
                f"{site}:escalation",
                f"default-env drift returned {mode!r}, expected full-escalated(...)",
            )
        ]
    return []


#: One rule per taxonomy arm. Each owns its OWN env setup (some arms need
#: noescalate, one needs it absent), so the table is a plain sequence rather
#: than a dispatch dict — an arm's env precondition is part of its body, not
#: a shared property the table could get wrong for one member.
_TAXONOMY_ARMS: tuple[Any, ...] = (
    _taxonomy_unreadable,
    _taxonomy_drift,
    _taxonomy_recorded_failures,
    _taxonomy_blind,
    _taxonomy_nothing_selected,
    _taxonomy_escalation,
)


def _arm_taxonomy(module: ModuleType) -> list[Finding]:
    site = f"{GATE_FILE}:_zero_selection"
    saved_env = os.environ.get(module._NOESCALATE_ENV)  # pylint: disable=protected-access
    try:
        return [finding for arm in _TAXONOMY_ARMS for finding in arm(module, site)]
    finally:
        if saved_env is None:
            os.environ.pop(module._NOESCALATE_ENV, None)  # pylint: disable=protected-access
        else:
            os.environ[module._NOESCALATE_ENV] = saved_env  # pylint: disable=protected-access


# --------------------------------------------------------------------------
# ARM 4 — run_pytest: counts from JUnit XML, -1 on no parsable report
# --------------------------------------------------------------------------


def _arm_run_pytest(module: ModuleType) -> list[Finding]:
    findings: list[Finding] = []
    site = f"{GATE_FILE}:run_pytest"
    real_run = module.subprocess.run

    class _NoReport:  # pylint: disable=too-few-public-methods
        returncode = 0

    module.subprocess.run = lambda *_a, **_k: _NoReport()  # type: ignore[assignment]
    try:
        rc, total, bad = module.run_pytest(["--collect-only"])
    finally:
        module.subprocess.run = real_run  # type: ignore[assignment]
    if (rc, total, bad) != (0, -1, -1):
        findings.append(
            Finding(
                site,
                f"no parsable report read ({rc}, {total}, {bad}), expected (0, -1, -1)",
            )
        )

    xml = '<testsuites><testsuite tests="9" failures="1" errors="0"/></testsuites>'

    class _WithReport:  # pylint: disable=too-few-public-methods
        returncode = 1

    def fake_run(argv, **_kwargs):
        path = next(a.split("=", 1)[1] for a in argv if a.startswith("--junit-xml="))
        Path(path).write_text(xml, encoding="utf-8")
        return _WithReport()

    module.subprocess.run = fake_run  # type: ignore[assignment]
    try:
        rc, total, bad = module.run_pytest([])
    finally:
        module.subprocess.run = real_run  # type: ignore[assignment]
    if (rc, total, bad) != (1, 9, 1):
        findings.append(
            Finding(
                site, f"JUnit XML parsed as ({rc}, {total}, {bad}), expected (1, 9, 1)"
            )
        )
    return findings


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    try:
        module, error = load(ctx.nix_home)
        if module is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        findings: list[Finding] = []
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            findings += _arm_blob_shas(module, tmp_path)
            findings += _arm_read_db(module, tmp_path)
        findings += _arm_taxonomy(module)
        findings += _arm_run_pytest(module)
        evidence = (
            f"{GATE_FILE}: drove blob_shas against a real `git hash-object` "
            "oracle, read_db's state/uncovered/drift classification over a "
            "real sqlite fixture, all 6 named arms of the verdict taxonomy "
            "(unreadable/drift/recorded-failures/blind/nothing-selected/"
            "escalation-by-default), and run_pytest's JUnit-XML parsing"
        )
        if findings:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(f.site for f in findings),
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
