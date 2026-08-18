#!/usr/bin/env python3
"""§4:274's quarantine, DRIVEN ACROSS A REAL PROCESS BOUNDARY — `scripts/nixrisk/supervision.py`.

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md` unless another document
is named on the same line.

THE PROPERTY, AND WHY A SECOND OBJECT WOULD NOT PROVE IT

§4:274 is four words long and absolute: *"Quarantine is NOT auto-resurrected;
return is operator-driven."* The event it has to survive is **supervision's own
restart**, which is not a second `CrashLoopBreaker` in one interpreter — it is a
new PROCESS constructing a new breaker over the same on-disk state. ARC 036
measured the tree failing exactly there (CHECK-DEBT D3.250): three restarts
fsynced into `RestartLedger`, `is_quarantined -> True` on the breaker that
counted them, and a second breaker over the SAME ledger answering
`is_quarantined -> False` while `restarts_in_window` still returned 3 at a cap of
3. D3.251 is the mirror image: the §12.11:779 restore FLOOR lived in the same
process memory, so a restart un-did the operator's restore and re-quarantined a
strategy on restarts it had already been forgiven for.

So every drive below happens in a **`subprocess`**, never in this interpreter. A
same-process second object would be satisfied by a module-level cache, and a
module-level cache is precisely the defect wearing the repair's clothes.

THE FOUR ARMS

  1. **THE VERDICT SURVIVES A FRESH PROCESS.** Process A drives the cap to a trip
     and exits. Process B — a genuinely new interpreter over the same book —
     must answer `is_quarantined -> True` and `may_relaunch -> (False, …)`.
  2. **THE REASON AGREES WITH THE BOOK.** This gate reads the quarantine ledger's
     JSON lines ITSELF and requires the refusal text from process B to name that
     record's own `seq`, `restarts_in_window` and `cap`. D3.250's second half was
     a reason reading *"the §4:272 cap of 3 restart(s) per 10.0 min has not been
     reached"* while the ledger it had just read held three: an exit code or a
     bare `False` would have been green over that. Check contract v2 §11.
  3. **THE RESTORE FLOOR SURVIVES A FRESH PROCESS.** Process C restores at an
     instant strictly INSIDE the restart series, so the post-restore count is a
     specific non-zero number that differs from the pre-restore one. Process D —
     new interpreter — must report the POST-restore count. Reporting the
     pre-restore count is D3.251 exactly; reporting zero would be a deletion,
     which directive 6 forbids and which would also pass a naive "it changed"
     assertion.
  4. **NON-VACUITY.** Process Z reads the SAME book path BEFORE any record is
     written and must answer NOT quarantined, `may_relaunch -> True`. A gate that
     cannot distinguish the two states of one file measured nothing, and a
     constructor hard-wired to `True` fails here while passing arm 1.

§7.12 — WHAT WOULD HAVE TO BE TRUE FOR THIS TO COMPLETE WHILE MEASURING NOTHING?

 1. **THE BOOK IS WRITTEN AND NEVER QUERIED.** CLOSED by construction: the
    reading breaker is built by `subprocess.run` in a fresh interpreter over a
    ledger a DIFFERENT process wrote, so no in-process state can carry the
    verdict across. Arm 1 requires `is_quarantined -> True` there.
 2. **THE REFUSAL REASON STILL CONTRADICTS THE LEDGER.** CLOSED: arm 2 asserts
    the REASON, never the bool and never an exit code, and the numbers it
    requires are parsed by this gate out of the ledger FILE — a different source
    from the object being judged.
 3. **THE RESTORE FLOOR IS STILL IN MEMORY.** CLOSED: arm 3 restores in one
    process and reads the count in another, and requires the post-restore figure
    (`cap - 1`, derived from the config, not typed here).
 4. **THE GATE IS GREEN BECAUSE NOTHING WAS EVER QUARANTINED.** CLOSED: arm 4
    reads the same book before the record exists and requires NOT-quarantined,
    so the two states are distinguished by the same instrument.
 5. **THE GATE READS ITS EXPECTED CAP OUT OF THE SUBJECT.** CLOSED: the cap and
    window come from `risks/supervision.config.json` through
    `scripts/risk_config.py` — a different artifact from
    `scripts/nixrisk/supervision.py` — and every driver subprocess reports the
    knobs it loaded so the two derivations are compared.
 6. **THE DRIVER SILENTLY FAILED AND ITS SILENCE READ AS AGREEMENT.** CLOSED:
    every driver run must print one JSON object; a non-zero exit, empty stdout or
    an `error` field is a finding naming the stderr, never a skipped assertion.
 7. **A GREEN COULD IMPLY SCORE HANDLING ACROSS DEATH WORKS.** CLOSED: the
    evidence PRINTS `supervision.SCORE_BOUNDARY`, which since ARC 037 names the
    absent JOIN between this module and `scripts/nixscore/store.py` rather than
    claiming (falsely, on this tree) that no score store exists.
"""

from __future__ import annotations

import importlib
import json
import subprocess  # nosec B404 - the SUBJECT is a process boundary; see below
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

# B404 (`import subprocess`) is suppressed at the import above and B603
# (`subprocess.run` without `shell=True`) at the call site, each with the reason
# on the line rather than by widening the hook's scope (`nix_check_contract.md`
# §5.2). Both are bandit's INFORMATIONAL pair over the SAFE spelling: every argv
# here is a literal list whose head is `sys.executable`, there is no shell, and
# no element comes from outside this file except paths this gate itself built.
# The tests-side bandit hook already skips exactly B404 and B603 for exactly this
# reason (`.pre-commit-config.yaml`); the production hook has no skip, so the
# narrowing is written per site instead of per tree.
import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code,too-few-public-methods,too-many-locals
# pylint: disable=missing-function-docstring,missing-class-docstring
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = False
DEPENDS_ON: tuple[str, ...] = ()
#: This gate imports `risk_config` out of `ctx.nix_home` (shared interpreter
#: import state) to derive the expected cap, RUNS a driver script it writes as a
#: real subprocess with the same interpreter, and WRITES its scratch ledgers
#: under `/tmp`. Rule 12: declared claims are checked against OBSERVED ones, so
#: both interpreter spellings are declared — standalone the observed one is the
#: `.venv` `python`, under `verify.py` it is `/usr/bin/python3`.
RESOURCES: tuple[str, ...] = (
    "interpreter:sys.modules",
    "interpreter:sys.path",
    "subprocess:python",
    "subprocess:python3",
    "file-write:/tmp",
)
ON_FAIL = "continue"
#: NON-CORRECTABLE: the subject is risk-path source — the §4:272-274 breaker that
#: decides whether a dead strategy is allowed back into trading. A gate empowered
#: to edit it until its own drive came back clean would manufacture green over
#: the mechanism that keeps a crash-looping strategy out of the market.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is risk-path source (scripts/nixrisk/supervision.py decides "
    "§4:273 quarantine and §12.11:779 restore); a repair that edited it to "
    "satisfy its own gate is the class of action risk spec §4 forbids"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/nixrisk/supervision.py",
    "risks/supervision.config.json",
)

NAME = "check_quarantine_durability"

SUPERVISION_FILE = "scripts/nixrisk/supervision.py"
CONFIG_FILE = "risks/supervision.config.json"
PACKAGE = "nixrisk"
SUBJECT = "strat-quarantine-durability"
#: The restart series. Chosen so the restore instant can sit STRICTLY BETWEEN
#: two restarts, which makes the post-restore count a specific non-zero number.
BASE_TS = 1_700_000_000.0
RESTORE_TS = BASE_TS + 0.5


class Finding(NamedTuple):
    site: str
    why: str


class Loaded(NamedTuple):
    risk_config: ModuleType
    cap: int
    window_min: float


# --------------------------------------------------------------------------
# The expected figures — read from the CONFIG, never from the subject
# --------------------------------------------------------------------------


def load(home: Path) -> tuple[Loaded | None, str]:
    saved_path = list(sys.path)
    saved_rc = sys.modules.pop("risk_config", None)
    sys.path.insert(0, str((home / "scripts").resolve()))
    importlib.invalidate_caches()
    try:
        risk_config = importlib.import_module("risk_config")
        values = risk_config.load_risk_configs(home).modules["supervision"].values
        return Loaded(
            risk_config=risk_config,
            cap=int(values["crash_loop_max"]),
            window_min=float(values["crash_loop_window_min"]),
        ), ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"cannot read the §12A supervision knobs out of {home}/{CONFIG_FILE}: "
            f"{type(exc).__name__}: {exc}"
        )
    finally:
        if saved_rc is not None:
            sys.modules["risk_config"] = saved_rc
        else:
            sys.modules.pop("risk_config", None)
        sys.path[:] = saved_path


# --------------------------------------------------------------------------
# The driver — a REAL separate interpreter, which is the whole point
# --------------------------------------------------------------------------

DRIVER = """
import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from nixrisk.supervision import (
    SCORE_BOUNDARY,
    BreakerScope,
    CrashLoopBreaker,
    RestartLedger,
    SupervisionKnobs,
)
import risk_config


class _Alerts:
    def __init__(self):
        self.raised = []

    def alert(self, code, message):
        self.raised.append((code, message))


class _Plane2:
    def emit(self, event, **fields):
        return event


def main():
    home, ledger_path, verb = Path(sys.argv[2]), sys.argv[3], sys.argv[4]
    values = risk_config.load_risk_configs(home).modules["supervision"].values
    knobs = SupervisionKnobs.from_config(values)
    alerts = _Alerts()
    breaker = CrashLoopBreaker(
        knobs=knobs,
        scope=BreakerScope.STRATEGY,
        ledger=RestartLedger(ledger_path),
        alert=alerts,
        plane2=_Plane2(),
    )
    subject, now = sys.argv[5], float(sys.argv[6])
    out = {
        "pid": os.getpid(),
        "verb": verb,
        "cap": knobs.crash_loop_max,
        "window_min": knobs.crash_loop_window_min,
        "quarantine_book": str(breaker.quarantine_book.path),
        "score_boundary": SCORE_BOUNDARY,
    }
    if verb == "crash":
        verdicts = [
            breaker.record_restart(subject, now=now + i)
            for i in range(knobs.crash_loop_max)
        ]
        out["tripped"] = verdicts[-1].tripped
        out["quarantined_by_verdict"] = verdicts[-1].quarantined
        out["alerts"] = [code for code, _ in alerts.raised]
    elif verb == "restore":
        lifted = breaker.restore(subject, "operator-under-test", now=now)
        out["lifted"] = lifted is not None
    elif verb != "probe":
        out["error"] = "unknown verb " + repr(verb)
    allowed, why = breaker.may_relaunch(subject)
    out["is_quarantined"] = breaker.is_quarantined(subject)
    out["may_relaunch"] = allowed
    out["reason"] = why
    out["restarts_in_window"] = len(breaker.restarts_in_window(subject, now + 100.0))
    verdict = breaker.quarantine_verdict(subject)
    out["verdict_restarts"] = None if verdict is None else verdict.restarts_in_window
    out["verdict_reason"] = None if verdict is None else verdict.reason
    print(json.dumps(out))


try:
    main()
except Exception as exc:  # noqa: BLE001
    print(json.dumps({"error": type(exc).__name__ + ": " + str(exc)}))
"""


class Drive(NamedTuple):
    ok: bool
    data: dict[str, Any]
    why: str


def _drive(home: Path, root: Path, ledger: Path, verb: str, now: float) -> Drive:
    """One FRESH INTERPRETER. Never an object in this one (D3.250)."""
    driver = root / "driver.py"
    if not driver.exists():
        driver.write_text(DRIVER, encoding="utf-8")
    proc = subprocess.run(  # nosec B603 - literal argv, sys.executable, no shell
        [
            sys.executable,
            str(driver),
            str((home / "scripts").resolve()),
            str(home),
            str(ledger),
            verb,
            SUBJECT,
            repr(now),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(root),
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return Drive(
            False,
            {},
            f"driver verb {verb!r} exited {proc.returncode} with stdout="
            f"{proc.stdout.strip()!r} stderr={proc.stderr.strip()[-600:]!r}",
        )
    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
    except ValueError as exc:
        return Drive(False, {}, f"driver verb {verb!r} printed non-JSON: {exc!r}")
    if "error" in data:
        return Drive(False, data, f"driver verb {verb!r} raised {data['error']}")
    return Drive(True, data, "")


def _book(path: Path) -> tuple[list[dict[str, Any]], str]:
    """THIS GATE's own read of the quarantine book — a second source."""
    if not path.exists():
        return [], f"{path} does not exist"
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError as exc:
            return [], f"{path}:{index + 1} is not JSON: {exc!r}"
    return rows, ""


# --------------------------------------------------------------------------
# ARM 4 (driven FIRST) — NON-VACUITY: the same book, before the record
# --------------------------------------------------------------------------


def _arm_non_vacuity(home: Path, root: Path, ledger: Path) -> list[Finding]:
    site = f"{SUPERVISION_FILE}:non-vacuity"
    drive = _drive(home, root, ledger, "probe", BASE_TS)
    if not drive.ok:
        return [Finding(site, drive.why)]
    findings: list[Finding] = []
    if drive.data["is_quarantined"]:
        findings.append(
            Finding(
                site,
                f"a FRESH process over an EMPTY quarantine book "
                f"{drive.data['quarantine_book']} answered is_quarantined=True "
                f"for {SUBJECT!r}: {drive.data['reason']} — a breaker that "
                "cannot say NOT-quarantined proves nothing when it says "
                "quarantined",
            )
        )
    if not drive.data["may_relaunch"]:
        findings.append(
            Finding(
                site,
                f"may_relaunch refused a subject that was never quarantined: "
                f"{drive.data['reason']}",
            )
        )
    if drive.data["restarts_in_window"] != 0:
        findings.append(
            Finding(
                site,
                f"the restart ledger already held "
                f"{drive.data['restarts_in_window']} restart(s) for {SUBJECT!r} "
                "before this run wrote any — the scratch tree is not clean and "
                "every count below would be measured against the wrong base",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM 1 — the verdict survives a FRESH PROCESS
# --------------------------------------------------------------------------


def _arm_survives(
    home: Path, root: Path, ledger: Path, loaded: Loaded
) -> tuple[list[Finding], dict[str, Any], dict[str, Any]]:
    site = f"{SUPERVISION_FILE}:fresh-process-quarantine"
    findings: list[Finding] = []
    writer = _drive(home, root, ledger, "crash", BASE_TS)
    if not writer.ok:
        return [Finding(site, writer.why)], {}, {}
    if not writer.data.get("tripped") or not writer.data.get("quarantined_by_verdict"):
        findings.append(
            Finding(
                site,
                f"{loaded.cap} restart(s) inside the "
                f"{loaded.window_min} min window did not quarantine {SUBJECT!r} "
                f"in the WRITING process: {writer.data.get('reason')} — §4:272-274",
            )
        )
    reader = _drive(home, root, ledger, "probe", BASE_TS)
    if not reader.ok:
        return findings + [Finding(site, reader.why)], writer.data, {}
    if reader.data["pid"] == writer.data["pid"]:
        findings.append(
            Finding(
                site,
                f"the writer and the reader ran in ONE process (pid "
                f"{reader.data['pid']}) — the property under test is survival of "
                "a process boundary and no boundary was crossed",
            )
        )
    if not reader.data["is_quarantined"]:
        findings.append(
            Finding(
                site,
                f"a FRESH process (pid {reader.data['pid']}) over the book "
                f"pid {writer.data['pid']} wrote answered is_quarantined=False "
                f"for {SUBJECT!r} while restarts_in_window="
                f"{reader.data['restarts_in_window']} at cap {loaded.cap}: "
                f"{reader.data['reason']} — §4:274 'Quarantine is NOT "
                "auto-resurrected; return is operator-driven', and a supervision "
                "restart is exactly this new breaker (CHECK-DEBT D3.250)",
            )
        )
    if reader.data["may_relaunch"]:
        findings.append(
            Finding(
                site,
                f"a FRESH process ALLOWED the relaunch of a quarantined strategy: "
                f"{reader.data['reason']} — that is the auto-resurrection §4:274 "
                "forbids, taken with no operator and no §12.11:779 verb",
            )
        )
    return findings, writer.data, reader.data


# --------------------------------------------------------------------------
# ARM 2 — the REASON agrees with the book this gate read itself
# --------------------------------------------------------------------------


def _arm_reason(ledger: Path, reader: dict[str, Any], loaded: Loaded) -> list[Finding]:
    site = f"{SUPERVISION_FILE}:may_relaunch-reason"
    if not reader:
        return [Finding(site, "arm 1 produced no fresh-process verdict to judge")]
    book_path = Path(reader["quarantine_book"])
    rows, error = _book(book_path)
    if error:
        return [Finding(site, f"cannot read the quarantine book: {error}")]
    live = [row for row in rows if row.get("kind") == "quarantine"]
    if not live:
        return [
            Finding(
                site,
                f"{book_path} holds {len(rows)} record(s) and NO 'quarantine' "
                f"record after the cap was driven to a trip over {ledger} — the "
                "verdict was never written down, so nothing could have survived",
            )
        ]
    record = live[-1]
    reason = reader["reason"]
    findings: list[Finding] = []
    for field, value in (
        ("seq", record["seq"]),
        ("restarts_in_window", record["restarts_in_window"]),
        ("cap", record["cap"]),
    ):
        if f"{field}={value}" not in reason:
            findings.append(
                Finding(
                    site,
                    f"the §18 refusal reason does not carry the book's own "
                    f"{field}={value} (read by THIS GATE out of {book_path}): "
                    f"{reason} — D3.250's second half was a reason measurably "
                    "false on the same object, and a reason that cannot quote "
                    "the record it came from cannot be checked against it",
                )
            )
    if "has not been reached" in reason:
        findings.append(
            Finding(
                site,
                f"the refusal for a QUARANTINED subject still says 'has not been "
                f"reached' while {book_path} holds restarts_in_window="
                f"{record['restarts_in_window']} at cap {record['cap']}: "
                f"{reason} — this is CHECK-DEBT D3.250's exact string",
            )
        )
    if record["restarts_in_window"] < loaded.cap:
        findings.append(
            Finding(
                site,
                f"the quarantine record books {record['restarts_in_window']} "
                f"restart(s) but {CONFIG_FILE} says the cap is {loaded.cap} — "
                "the book and the config disagree about what tripped",
            )
        )
    if reader["verdict_restarts"] != record["restarts_in_window"]:
        findings.append(
            Finding(
                site,
                f"quarantine_verdict() rebuilt from the book reports "
                f"{reader['verdict_restarts']} restart(s) where the record says "
                f"{record['restarts_in_window']} — the rebuilt verdict is not "
                "the record",
            )
        )
    return findings


# --------------------------------------------------------------------------
# ARM 3 — the §12.11:779 restore FLOOR survives a fresh process
# --------------------------------------------------------------------------


def _arm_restore(home: Path, root: Path, ledger: Path, loaded: Loaded) -> list[Finding]:
    site = f"{SUPERVISION_FILE}:fresh-process-restore-floor"
    findings: list[Finding] = []
    #: The restore instant sits strictly between restart 0 and restart 1, so the
    #: expected post-restore count is cap - 1: a specific NON-ZERO number that
    #: differs from the pre-restore count. Zero would also "have changed", and a
    #: restore that deleted records would pass a weaker assertion.
    expected = loaded.cap - 1
    restorer = _drive(home, root, ledger, "restore", RESTORE_TS)
    if not restorer.ok:
        return [Finding(site, restorer.why)]
    if not restorer.data.get("lifted"):
        findings.append(
            Finding(
                site,
                "the restoring process reports it lifted NOTHING — either the "
                "quarantine did not survive into it (arm 1) or restore is a "
                "no-op",
            )
        )
    same = restorer.data["restarts_in_window"]
    if same != expected:
        findings.append(
            Finding(
                site,
                f"IN THE RESTORING PROCESS the post-restore count is {same}, "
                f"expected {expected} (cap {loaded.cap} restarts at "
                f"{BASE_TS!r}+0,1,2 with the floor at {RESTORE_TS!r}) — "
                "§12.11:779 resets the crash-loop counter",
            )
        )
    fresh = _drive(home, root, ledger, "probe", RESTORE_TS)
    if not fresh.ok:
        return findings + [Finding(site, fresh.why)]
    if fresh.data["pid"] == restorer.data["pid"]:
        findings.append(Finding(site, "the restore and the re-read shared one process"))
    if fresh.data["is_quarantined"]:
        findings.append(
            Finding(
                site,
                f"a FRESH process still reports {SUBJECT!r} QUARANTINED after "
                f"the operator's §12.11:779 restore: {fresh.data['reason']} — "
                "the restore record did not supersede the quarantine record",
            )
        )
    if fresh.data["restarts_in_window"] != expected:
        findings.append(
            Finding(
                site,
                f"a FRESH process reports {fresh.data['restarts_in_window']} "
                f"restart(s) after the restore, expected {expected}; the "
                f"restoring process reported {same}. If it reports "
                f"{loaded.cap} the floor never reached disk and the operator's "
                "restore is silently un-done at the next supervision restart "
                "(CHECK-DEBT D3.251); if it reports 0 the restore DELETED "
                "records, which directive 6 forbids",
            )
        )
    rows, error = _book(Path(fresh.data["quarantine_book"]))
    if error:
        findings.append(Finding(site, f"cannot read the quarantine book: {error}"))
        return findings
    kinds = [row.get("kind") for row in rows]
    if kinds.count("quarantine") < 1 or kinds.count("restore") < 1:
        findings.append(
            Finding(
                site,
                f"the book holds kinds {kinds} — a restore that SUPERSEDES must "
                "leave BOTH records on disk (directive 6: append, never rewrite)",
            )
        )
    if kinds and kinds[-1] != "restore":
        findings.append(
            Finding(site, f"the last record is {kinds[-1]!r}, expected 'restore'")
        )
    return findings


# --------------------------------------------------------------------------
# VERDICT
# --------------------------------------------------------------------------

ARMS = 4


def _remove_tree(root: Path) -> None:
    """Delete the scratch directory by ABSOLUTE path, never `shutil.rmtree`
    (MEASURED, ARC 026: `rmtree` unlinks with a bare relative name, which no
    path-rooted RESOURCES declaration can account for)."""
    if not root.is_dir():
        return
    for child in sorted(root.iterdir()):
        try:
            child.unlink()
        except OSError:
            continue
    try:
        root.rmdir()
    except OSError:
        pass


def _evidence(loaded: Loaded, writer: dict[str, Any], reader: dict[str, Any]) -> str:
    return (
        f"{ARMS} arms driving §4:274's quarantine ACROSS REAL PROCESS "
        f"BOUNDARIES at cap={loaded.cap} window={loaded.window_min}min, read "
        f"from {CONFIG_FILE} and never from a literal here. The cap was driven "
        f"to a trip in pid {writer.get('pid')} and the verdict read back in pid "
        f"{reader.get('pid')} — a genuinely new interpreter, not a second object "
        "in this one, because a module-level cache would hide the defect. The "
        "§18 refusal names the quarantine book's own seq / restarts_in_window / "
        "cap as THIS GATE parsed them out of the JSON lines, so the reason "
        "cannot contradict the record (CHECK-DEBT D3.250). The §12.11:779 "
        f"restore was taken in one process and its floor re-read in another, "
        f"requiring the POST-restore count {loaded.cap - 1} rather than the "
        f"pre-restore {loaded.cap} (D3.251) and requiring BOTH records to remain "
        "on disk. NON-VACUITY: the same book path answered NOT-quarantined "
        "before the record was written. WHAT IS NOT MEASURED — no systemd unit "
        "on this box is wired to the breaker, nothing here is installed or "
        "started, and the §12.11 operator TRANSPORT (an authenticated message to "
        "supervision) does not exist: `restore` is called directly. WHAT IS NOT "
        f"HERE — {reader.get('score_boundary', '')}"
    )


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    # B108: the scratch tree is created by `tempfile.mkdtemp`, not by
    # joining a guessable name onto /tmp. The name is still recognisable
    # (the prefix carries this gate's NAME) so an abandoned directory can
    # be attributed, and `_remove_tree` still deletes it by absolute path.
    root = Path(tempfile.mkdtemp(prefix=f"nix-{NAME}-"))
    try:
        loaded, error = load(ctx.nix_home)
        if loaded is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        root.mkdir(parents=True, exist_ok=True)
        ledger = root / "restarts.jsonl"
        findings = _arm_non_vacuity(ctx.nix_home, root, ledger)
        survived, writer, reader = _arm_survives(ctx.nix_home, root, ledger, loaded)
        findings += survived
        findings += _arm_reason(ledger, reader, loaded)
        findings += _arm_restore(ctx.nix_home, root, ledger, loaded)
        evidence = _evidence(loaded, writer, reader)
        if findings:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in findings),
                evidence=evidence,
                detail="; ".join(f"{site}: {why}" for site, why in findings),
            )
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )
    finally:
        _remove_tree(root)


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
