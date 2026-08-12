"""Tests for `scripts/runtime_gate.py` — the Stage 3 runtime gate (CHECK-DEBT D2.16).

ARC 018 sub-agent A built the gate that discharges D2.13, but had to leave the program
itself inside the `entry:` string of `.pre-commit-config.yaml`, outside every static gate
and every test. That is the instrument that closes this project's worst vacuity defect
being, itself, unmeasured — so it was opened as D2.16 rather than carried silently.

Phase 4 lifted the program to `scripts/runtime_gate.py`. This module is the other half of
that discharge.

WHAT IS DELIBERATELY NOT TESTED HERE: `main()`. Driving it would spawn pytest from inside
pytest, and the resulting recursion would take longer than the whole suite and prove less
than the plant/restore cycle already banked in `docs/CHECK-DEBT.md` D2.13. What is tested is
every decision `main()` delegates: the fingerprint, the database read, the corroboration,
and each arm of the verdict taxonomy.

NON-VACUITY: `test_gate_under_test_is_the_one_the_hook_runs` asserts this module tests the
same file `.pre-commit-config.yaml` actually invokes. Without it, the gate could be renamed
or the hook re-pointed and every test below would keep passing against an orphan.
"""

import hashlib
import sqlite3
import subprocess  # nosec B404 - fixed argv, shell=False, repo-local
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error
import runtime_gate  # pylint: disable=import-error
from nixverify.gitenv import scrubbed_env  # pylint: disable=import-error

# W0212 protected-access is disabled for this module, deliberately and with a reason.
# `_zero_selection` and `_NOESCALATE_ENV` are private to `runtime_gate` because nothing
# outside it should CALL them — not because they are unimportant. They carry the entire
# verdict taxonomy that discharges D2.13, and `main()` cannot be driven from inside pytest
# without spawning pytest recursively. Testing them through the public surface only would
# mean testing them not at all, which is the vacuous-control outcome these gates exist to
# prevent. The alternative — making them public so a test may touch them — would widen the
# module's API to satisfy a linter.
# pylint: disable=protected-access

REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_db(path: Path, rows: list[tuple[str, str]], *, failed: int = 0) -> None:
    """Build a minimal `.testmondata` carrying only what the gate reads."""
    con = sqlite3.connect(path)
    con.execute("create table file_fp (filename text, fsha text)")
    con.execute("create table environment (environment_name text, python_version text)")
    con.execute("create table test_execution (failed int)")
    con.executemany("insert into file_fp values (?, ?)", rows)
    con.execute("insert into environment values ('default', '3.14.4')")
    con.execute("insert into test_execution values (?)", (failed,))
    con.commit()
    con.close()


# --------------------------------------------------------------------------------------
# Non-vacuity — this suite must be pointed at the program the hook really runs.
# --------------------------------------------------------------------------------------


def test_gate_under_test_is_the_one_the_hook_runs() -> None:
    """The module imported here is the file `.pre-commit-config.yaml` invokes.

    Derived from the config, never restated: a hard-coded path here would be exactly the
    stale literal anchor (`debug.md` §7.4) these gates exist to remove.
    """
    config = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    entries = [
        line.split("entry:", 1)[1].strip()
        for line in config.splitlines()
        if line.strip().startswith("entry:")
    ]
    runtime_entries = [e for e in entries if "runtime_gate" in e]
    assert len(runtime_entries) == 1, (
        f"expected exactly one runtime-gate entry, got {entries}"
    )
    invoked = runtime_entries[0].split()[-1]
    assert (REPO_ROOT / invoked).resolve() == Path(runtime_gate.__file__).resolve()


# --------------------------------------------------------------------------------------
# blob_shas — the independent corroboration of testmon's own record.
# --------------------------------------------------------------------------------------


def test_blob_shas_matches_git_hash_object(tmp_path: Path) -> None:
    """The plain spelling is a real git blob hash, cross-checked against git itself."""
    target = tmp_path / "sample.py"
    target.write_bytes(b"x = 1\n")
    # nosec B607 - `git` is resolved from PATH deliberately: this test's whole value is
    # cross-checking our hash against the real git binary as an independent oracle, and
    # pinning an absolute path would make the test machine-specific for no security gain
    # (the repo is already being driven by git in every other hook).
    # ARC 026 (B4): scrubbed like every other git call in the tree. `hash-object`
    # of an absolute path is not repository-relative, so this one was never the
    # exposure — but a harness with one unscrubbed git call is a harness whose
    # rule has an exception, and D3.22 is exactly a rule that was applied
    # everywhere except one place.
    proc = subprocess.run(  # nosec B603,B607 - literal argv, shell=False
        ["git", "hash-object", str(target)],
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_env(),
    )
    assert proc.stdout.strip() in runtime_gate.blob_shas(target)


def test_blob_shas_accepts_both_testmon_spellings(tmp_path: Path) -> None:
    """A non-ASCII file yields two distinct hashes, so it cannot read as false drift.

    testmon derives the blob header from the *decoded* character count for a dirty file and
    from the raw byte count for a clean one. For non-ASCII content those differ.
    """
    target = tmp_path / "unicode.py"
    target.write_text('S = "café"\n', encoding="utf-8")
    shas = runtime_gate.blob_shas(target)
    assert len(shas) == 2, "non-ASCII content must produce both spellings"

    raw = target.read_bytes()
    expected_variant = hashlib.sha1(  # nosec B324
        b"blob %u\0" % len(raw.decode("utf-8")), usedforsecurity=False
    )
    expected_variant.update(raw)
    assert expected_variant.hexdigest() in shas


# --------------------------------------------------------------------------------------
# read_db — database state is an explicit input to the verdict (D2.13 / A2).
# --------------------------------------------------------------------------------------


def test_read_db_absent(tmp_path: Path) -> None:
    """A missing database is 'absent', not an error and not a silent empty scope."""
    state = runtime_gate.read_db(tmp_path / ".testmondata", [], tmp_path)
    assert state.state == "absent"
    assert not state.known


def test_read_db_unreadable(tmp_path: Path) -> None:
    """Random bytes are reported as unreadable, never treated as an empty graph."""
    db = tmp_path / ".testmondata"
    db.write_bytes(b"\x00\x01\x02not a database at all")
    state = runtime_gate.read_db(db, [], tmp_path)
    assert state.state.startswith("unreadable("), state.state


def test_read_db_present_reports_uncovered(tmp_path: Path) -> None:
    """A tracked file with no fingerprint is listed as uncovered — finding A2-i."""
    covered = tmp_path / "covered.py"
    covered.write_bytes(b"a = 1\n")
    (tmp_path / "orphan.py").write_bytes(b"b = 2\n")
    db = tmp_path / ".testmondata"
    _make_db(db, [("covered.py", min(runtime_gate.blob_shas(covered)))])

    state = runtime_gate.read_db(db, ["covered.py", "orphan.py"], tmp_path)
    assert state.state == "present"
    assert state.uncovered == ["orphan.py"]
    assert not state.drift
    assert state.recorded_tests == 1


def test_read_db_present_reports_drift(tmp_path: Path) -> None:
    """A corrupted fingerprint is drift — finding A2-ii, which testmon itself misses."""
    tracked = tmp_path / "tracked.py"
    tracked.write_bytes(b"a = 1\n")
    db = tmp_path / ".testmondata"
    _make_db(db, [("tracked.py", "0" * 40)])

    state = runtime_gate.read_db(db, ["tracked.py"], tmp_path)
    assert state.drift == ["tracked.py"]
    assert not state.uncovered


def test_read_db_clean_file_is_neither_uncovered_nor_drift(tmp_path: Path) -> None:
    """The control: a correctly fingerprinted, unmodified file raises no flag at all.

    Without this, every assertion above would pass on a corroborator that always reports
    drift — the vacuous-control class (`debug.md` §7.12).
    """
    tracked = tmp_path / "tracked.py"
    tracked.write_bytes(b"a = 1\n")
    db = tmp_path / ".testmondata"
    _make_db(db, [("tracked.py", min(runtime_gate.blob_shas(tracked)))])

    state = runtime_gate.read_db(db, ["tracked.py"], tmp_path)
    assert not state.drift
    assert not state.uncovered


# --------------------------------------------------------------------------------------
# The verdict taxonomy — every arm, including the exit-1/exit-2 split.
# --------------------------------------------------------------------------------------


def _run(
    *,
    state: str = "present",
    drift: list[str] | None = None,
    uncovered: list[str] | None = None,
    recorded_failures: int = 0,
) -> runtime_gate.Run:
    db = runtime_gate.DbState(
        state=state,
        drift=drift or [],
        uncovered=uncovered or [],
        recorded_failures=recorded_failures,
    )
    return runtime_gate.Run(db=db, scope=["a.py"], selected=0)


def test_verdict_exits_with_its_code_and_names_itself(
    capsys: pytest.CaptureFixture,
) -> None:
    """A verdict always prints its own scope line and its name before exiting."""
    run = _run(state="present")
    run.selected = 12
    with pytest.raises(SystemExit) as exc:
        run.verdict("MEASURED-PASS", 0)
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "RUNTIME-GATE verdict: MEASURED-PASS" in out
    assert "SELECTED=12" in out


def test_zero_selection_unreadable_db_is_cannot_measure(
    capsys: pytest.CaptureFixture,
) -> None:
    """An unreadable database means scope is unknowable: exit 2, not exit 1.

    ARC 025 Stage 3.3: this control asserts the REASON, not the exit code alone.
    Exit 2 is reachable from four distinct arms of `_zero_selection` and from an
    unrelated crash; a control that reads only the number cannot tell which one
    fired, which is the exact shape of ARC 024's re-verify defect.
    """
    with pytest.raises(SystemExit) as exc:
        runtime_gate._zero_selection(_run(state="unreadable(DatabaseError)"), [])
    assert exc.value.code == 2
    out = capsys.readouterr().out
    assert "RUNTIME-GATE verdict: CANNOT-MEASURE" in out
    assert "unreadable, so scope is unknowable" in out


def test_zero_selection_with_drift_is_selector_broken(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Under noescalate, drift with zero selection is named SELECTOR-BROKEN: exit 1.

    ARC 025 Stage 3.3: asserts the taxonomy NAME and the drift count that
    justified it, not the exit code alone — exit 1 is shared with the
    recorded-failures arm and with an outright crash.
    """
    monkeypatch.setenv(runtime_gate._NOESCALATE_ENV, "noescalate")
    with pytest.raises(SystemExit) as exc:
        runtime_gate._zero_selection(_run(state="present", drift=["a.py"]), [])
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "RUNTIME-GATE verdict: SELECTOR-BROKEN" in out
    assert "1 in-scope file(s) differ from the db record" in out
    assert "escalation suppressed" in out


def test_zero_selection_with_recorded_failures_is_selector_broken(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A recorded failure nobody re-ran is named, not treated as an absence of evidence."""
    monkeypatch.setenv(runtime_gate._NOESCALATE_ENV, "noescalate")
    with pytest.raises(SystemExit) as exc:
        runtime_gate._zero_selection(_run(state="present", recorded_failures=3), [])
    assert exc.value.code == 1
    out = capsys.readouterr().out
    # ARC 025 Stage 3.3 — the REASON, not the code. This arm shares exit 1 with
    # the drift arm, so the count is what distinguishes them.
    assert "RUNTIME-GATE verdict: SELECTOR-BROKEN" in out
    assert "db records 3 failed test(s) yet nothing was selected" in out


def test_drift_escalates_rather_than_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    """THE PHASE 4 REGRESSION GUARD. Drift must escalate, never terminate red.

    A behaviour-neutral edit (comment, docstring, reformat) changes this gate's content
    hash while changing no testmon method checksum, so drift with zero selection is the
    NORMAL outcome of commenting a test file. Terminating on it made the gate permanently
    red on such commits and it did not self-clear. Measured ARC 018 Phase 4.
    """
    monkeypatch.delenv(runtime_gate._NOESCALATE_ENV, raising=False)
    mode = runtime_gate._zero_selection(_run(state="present", drift=["a.py"]), [])
    assert mode.startswith("full-escalated(SELECTOR-BROKEN:")


def test_unreadable_db_stays_terminal_even_with_escalation_available(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """An unreadable database is the one arm escalation cannot rescue.

    ARC 025 Stage 3.3: the whole point of this control is WHICH arm terminated —
    with escalation available, every other zero-selection path returns instead of
    exiting. Asserting only `code == 2` would pass if the function crashed before
    reaching the unreadable branch at all.
    """
    monkeypatch.delenv(runtime_gate._NOESCALATE_ENV, raising=False)
    with pytest.raises(SystemExit) as exc:
        runtime_gate._zero_selection(_run(state="unreadable(DatabaseError)"), [])
    assert exc.value.code == 2
    out = capsys.readouterr().out
    assert "RUNTIME-GATE verdict: CANNOT-MEASURE" in out
    assert "unreadable, so scope is unknowable" in out
    # Escalation was AVAILABLE and was not taken — that is the property.
    assert "escalation suppressed" not in out


def test_zero_selection_nothing_changed_is_cannot_measure_not_pass(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """THE DEFECT D2.13 NAMES. A legitimate 'nothing changed' must never report PASS."""
    monkeypatch.setenv(runtime_gate._NOESCALATE_ENV, "noescalate")
    with pytest.raises(SystemExit) as exc:
        runtime_gate._zero_selection(_run(state="present"), [])
    assert exc.value.code == 2
    assert "NOTHING-SELECTED" in capsys.readouterr().out


def test_zero_selection_blind_change_is_scope_blind(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A changed file the database cannot see is distinguishable from 'nothing changed'."""
    monkeypatch.setenv(runtime_gate._NOESCALATE_ENV, "noescalate")
    with pytest.raises(SystemExit) as exc:
        runtime_gate._zero_selection(
            _run(state="present", uncovered=["a.py"]), ["a.py"]
        )
    assert exc.value.code == 2
    out = capsys.readouterr().out
    assert "SCOPE-BLIND" in out
    assert "changed-but-uncovered:a.py" in out


def test_zero_selection_escalates_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the opt-out, zero selection escalates rather than terminating.

    This is what stops the fix from being 'report exit 2 on every quiet commit', which
    would be a gate nobody could commit through.
    """
    monkeypatch.delenv(runtime_gate._NOESCALATE_ENV, raising=False)
    mode = runtime_gate._zero_selection(_run(state="present"), [])
    assert mode == "full-escalated(NOTHING-SELECTED:zero-selection)"


# --------------------------------------------------------------------------------------
# run_pytest — the count comes from JUnit XML, and an absent report is CANNOT-MEASURE.
# --------------------------------------------------------------------------------------


def test_run_pytest_reports_negative_when_no_report_is_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If pytest writes no parsable report the count is -1, never an assumed 0.

    -1 routes to CANNOT-MEASURE. An assumed 0 would route to the zero-selection path and
    could escalate into a full run on a gate that never actually ran — measuring nothing
    while looking busy.
    """

    class _Proc:  # pylint: disable=too-few-public-methods
        returncode = 0

    monkeypatch.setattr(runtime_gate.subprocess, "run", lambda *_a, **_k: _Proc())
    rc, total, bad = runtime_gate.run_pytest(["--collect-only"])
    assert (rc, total, bad) == (0, -1, -1)


def test_run_pytest_parses_counts_from_junit_xml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Counts are read from the XML attributes, not scraped from stdout prose."""
    xml = '<testsuites><testsuite tests="9" failures="1" errors="0"/></testsuites>'

    class _Proc:  # pylint: disable=too-few-public-methods
        returncode = 1

    def fake_run(argv: list[str], **_kwargs: object) -> _Proc:
        path = next(a.split("=", 1)[1] for a in argv if a.startswith("--junit-xml="))
        Path(path).write_text(xml, encoding="utf-8")
        return _Proc()

    monkeypatch.setattr(runtime_gate.subprocess, "run", fake_run)
    rc, total, bad = runtime_gate.run_pytest([])
    assert (rc, total, bad) == (1, 9, 1)


def test_git_returns_empty_list_on_failure() -> None:
    """A failed git call yields [], so a broken repo narrows scope visibly, not silently."""
    assert runtime_gate.git("rev-parse", "--verify", "no/such/ref/arc018") == []


def test_module_is_importable_without_running(capsys: pytest.CaptureFixture) -> None:
    """Importing the gate must not execute it — the `__main__` guard is load-bearing.

    `sys.modules` already holds it from the import at the top of this file; if importing
    had side effects, the whole suite would have run the gate before reaching any test.
    """
    assert "runtime_gate" in sys.modules
    assert capsys.readouterr().out == ""
