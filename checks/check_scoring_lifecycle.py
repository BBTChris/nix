#!/usr/bin/env python3
# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK — `PRIVILEGE`/`INTERACTIVE`/
# `DISRUPTIVE`, `DEPENDS_ON`/`RESOURCES`/`TIME_BOUND`/`CORRECTABLE`/`SUBJECTS`,
# and the `standalone_main` `__main__` — against every other check's. That
# similarity is the CONTRACT (`nix_check_contract.md` §4.2, §4.4).
"""Gate: the score row OUTLIVES ITS PROCESS, and quarantine archives EXACTLY
one strategy's pairs — measured across real SIGKILLs, never in-process.

Subject: `scripts/nixscore/store.py`.
Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §6.6:429-433 (*Ownership &
authority (locked)*), §4:275-280 (*Score handling across death (locked)*),
§12.11:779 (verb 3, `quarantine-restore`).

## THE TWO PROPERTIES, AND THE TWO WAYS A GATE FAKES THEM

§6.6 locks one key and gives the reason in the same breath: *"This is the only
keying under which the rest of the design is simultaneously true: score persists
across process death (keyed to the pair, not the process — §4) and quarantine
removes exactly that strategy's rows (archived, not destroyed)."*

Each half has a characteristic counterfeit, and this gate is built around
refusing both:

1. **"Persists across process death", proven without a death.** Constructing a
   store, writing, constructing a second store over the same file and reading
   back proves SERIALISATION. It runs entirely inside one interpreter, so a
   store that kept its rows in a module-level dict would pass it. **Every value
   this gate compares therefore crosses a process boundary**: the writer
   `SIGKILL`s itself after its last durable write, the parent confirms
   `returncode == -SIGKILL`, and a **different pid** reads the value back.
2. **"Removes exactly that strategy's rows", proven with one strategy.** With a
   single strategy in the table, "removed exactly its rows" and "removed
   everything" are the same set, so an archive that truncated the table would
   pass. **The fixture is therefore deliberately entangled**: `alpha` holds two
   symbols (ES and NQ), ES is shared by `alpha` and `beta`, NQ is shared by
   `alpha` and `gamma`. Archiving `alpha` must leave `beta`/ES and `gamma`/NQ
   untouched, so over-removal by symbol and over-removal wholesale are both
   visible. The gate refuses to judge (CANNOT_MEASURE) if that shape is not
   present before the archive.

## debug.md §7.12 — the standing question, asked where this gate is built

**What would have to be true for this gate to PASS while measuring nothing?**

1. **No process ever died.** *Closed:* the parent asserts each writer arm was
   reaped with `-SIGKILL`; a writer that exited any other way is
   CANNOT_MEASURE, not a pass.
2. **The value read back is a default, not the value written.** *Closed by the
   NONCE:* every EMA is derived from a per-run seed, so the number that survives
   is one no cold-start path could produce. And a **COLD-START CONTROL** store at
   a second path is opened in the same reader process and must be EMPTY — so
   "the reader found rows" cannot be the reader inventing them.
3. **The table was trivial, so "exactly" is an identity.** *Closed:* the
   pre-archive shape is asserted — 4 pairs, 3 strategies, one strategy holding
   two symbols, two symbols each shared by two strategies — before any archive
   verdict is believed.
4. **Archived is indistinguishable from destroyed.** *Closed:* every archived
   pair must read back `Presence.ARCHIVED`, a fabricated pair must read back
   `Presence.ABSENT`, and the archived RECORD's own EMA must still equal the
   pre-archive value. A store that deleted the rows would answer `ABSENT`.
5. **Restore "worked" because it re-derived plausible numbers.** *Closed:* the
   restored EMAs are compared for exact float equality against the values the
   writer arm printed BEFORE it died, pair by pair, not for non-emptiness.
6. **Atomicity passed because no kill ever landed during a write.** *Closed by
   the revision counter:* the store persists a monotonic durable-write count, so
   each kill trial reports how many whole documents the victim committed before
   it died, and the arm is CANNOT_MEASURE below `MIN_CHURN_WRITES` total. The
   bound this cannot reach is stated in the evidence.

## WHAT THIS GATE CANNOT BOUND, and does not pretend to

The atomicity arm proves that **no observed post-kill state was torn** over N
kills spanning M durable writes. It does NOT prove the kill ever landed *inside*
`os.replace` — that instant is not addressable from outside the victim, and a
gate that claimed otherwise would be claiming a schedule it does not control.
What it does establish is a real, falsifiable population: the plant suite
(`scripts/tests/test_check_scoring_lifecycle.py`) replaces the atomic write with
a truncate-then-write and this same arm reddens, so the arm is demonstrably
capable of seeing a torn store.
"""

from __future__ import annotations

import json
import os
import random
import signal
import subprocess  # nosec B404 - the subject is behaviour ACROSS a real process death
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import (
    CheckResult,
    Context,
    Mode,
    Status,
    result_from_defects,
)

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: Declared against what this gate OBSERVABLY does, because
#: `check_observed_resource_claims` compares declarations to runtime use
#: (§17 / contract rule 12), not to each other:
#: * `subprocess:python3` / `subprocess:python` — the writer, reader and churn
#:   children, spawned through `sys.executable`. Both spellings: the observer
#:   matches a subprocess claim by BASENAME and `sys.executable` differs between
#:   the runners.
#: * `file-write:/tmp` — every store this gate creates lives in a
#:   `TemporaryDirectory` (doctrine C.8: no plant, and no drill, touches a
#:   production artifact). The store's own temp file is a sibling of the store,
#:   so it is under the same root.
RESOURCES: tuple[str, ...] = (
    "subprocess:python3",
    "subprocess:python",
    "file-write:/tmp",
)
TIME_BOUND = True
#: Six sequenced children for the three lifecycle arms plus `KILL_TRIALS` × 2 for
#: the atomicity arm, each an interpreter start, plus the jitter window.
#: MEASURED 1.6 s on this node; the budget carries slack for a loaded box.
EXPECTED_S = 8.0
ON_FAIL = "continue"
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is what a store does across a kill; 'correcting' it would mean "
    "writing the rows whose survival is under measurement"
)
SUBJECTS: tuple[str, ...] = ("scripts/nixscore/store.py",)

NAME = "check_scoring_lifecycle"

#: The entangled fixture. `alpha` holds TWO symbols; ES and NQ are each shared by
#: two strategies. Without this shape "removed exactly alpha's rows" is an
#: identity — see the module docstring, counterfeit 2.
QUARANTINED = "alpha"
#: A pair no seeding path creates, used to prove ABSENT is a reachable answer and
#: therefore that ARCHIVED is a distinguishable one.
FABRICATED = ("delta", "CL")
#: How many kills the atomicity arm takes, and the window it jitters them into.
KILL_TRIALS = 10
JITTER_MIN_S = 0.005
JITTER_MAX_S = 0.060
#: Below this the victims barely wrote and "nothing was torn" is a statement
#: about an empty set.
MIN_CHURN_WRITES = 40
CHILD_TIMEOUT_S = 30.0

# ---------------------------------------------------------------------------
# The children. Each is a REAL process; none of them shares memory with this one.
# ---------------------------------------------------------------------------

#: Seeds the entangled table, prints exactly what it made durable, then SIGKILLs
#: ITSELF. The kill is after the last `record()` returns, so every value printed
#: is a value the store said was durable before the process ceased to exist.
WRITER = """
import json, os, sys
from nixscore.store import ScoreStore
path, seed = sys.argv[1], float(sys.argv[2])
rows = [
    ("alpha", "ES", seed + 1.5, 7),
    ("alpha", "NQ", -(seed + 0.25), 4),
    ("beta", "ES", seed + 9.75, 9),
    ("gamma", "NQ", seed + 0.5, 2),
]
store = ScoreStore(path)
for sid, sym, ema, days in rows:
    store.record(sid, sym, ema, days, now=1700000000.0)
print(json.dumps({"pid": os.getpid(), "revision": store.revision, "rows": rows}))
sys.stdout.flush()
os.kill(os.getpid(), 9)
"""

#: Opens the store, reports EVERYTHING, opens a second EMPTY store as the
#: cold-start control, then SIGKILLs itself so no arm is ever read from a process
#: that outlived its own measurement.
READER = """
import json, os, sys
from nixscore.store import Presence, ScoreStore
path, cold, probes = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
out = {"pid": os.getpid(), "error": ""}
try:
    store = ScoreStore(path)
    out["revision"] = store.revision
    out["live"] = [
        [k[0], k[1], store.get(*k).realized_ema, store.get(*k).days_observed]
        for k in store.live_pairs()
    ]
    out["archived"] = [
        [k[0], k[1], store.archived_record(*k).realized_ema,
         store.archived_record(*k).days_observed]
        for k in store.archived_pairs()
    ]
    out["presence"] = [[p[0], p[1], str(store.presence(p[0], p[1]))] for p in probes]
    out["reasons"] = {k[0]: store.archive_reason(k[0]) for k in store.archived_pairs()}
    out["cold_live"] = len(ScoreStore(cold).live_pairs())
except Exception as exc:  # noqa: BLE001
    out["error"] = repr(exc)
print(json.dumps(out))
sys.stdout.flush()
os.kill(os.getpid(), 9)
"""

#: Archives the quarantined strategy, prints the outcome's own account of what
#: moved and what did not, then dies. §4:279's consequence, taken by a process
#: that does not survive to be asked about it.
ARCHIVER = """
import json, os, sys
from nixscore.store import ScoreStore
path, strategy = sys.argv[1], sys.argv[2]
store = ScoreStore(path)
out = store.archive_strategy(strategy, "crash-loop cap hit (§4:273)", now=1700000100.0)
print(json.dumps({
    "pid": os.getpid(),
    "archived": [list(k) for k in out.archived],
    "untouched": [list(k) for k in out.untouched],
    "reason": out.reason,
    "moved": out.moved,
}))
sys.stdout.flush()
os.kill(os.getpid(), 9)
"""

#: §12.11 verb 3, twice: once for the archived strategy and once for a strategy
#: that was NEVER archived — the case that would otherwise be silent.
RESTORER = """
import json, os, sys
from nixscore.store import ScoreStore
path, strategy, phantom = sys.argv[1], sys.argv[2], sys.argv[3]
store = ScoreStore(path)
real = store.restore_strategy(strategy, "operator-under-test")
ghost = store.restore_strategy(phantom, "operator-under-test")
print(json.dumps({
    "pid": os.getpid(),
    "restored": [list(k) for k in real.restored],
    "reason": real.reason,
    "ghost_rehydrated": ghost.rehydrated,
    "ghost_reason": ghost.reason,
    "ghost_names_subject": phantom in ghost.reason,
}))
sys.stdout.flush()
os.kill(os.getpid(), 9)
"""

#: Seeds, signals readiness by creating a marker, then archives and restores in a
#: tight loop FOREVER. It is killed from outside at a jittered instant. The
#: marker is what stops the parent from killing a victim that had not started.
CHURN = """
import os, sys
from nixscore.store import ScoreStore
path, ready = sys.argv[1], sys.argv[2]
store = ScoreStore(path)
for sid, sym, ema, days in [
    ("alpha", "ES", 1.5, 7), ("alpha", "NQ", -0.25, 4),
    ("beta", "ES", 9.75, 9), ("gamma", "NQ", 0.5, 2),
]:
    store.record(sid, sym, ema, days, now=1700000000.0)
open(ready, "w").close()
while True:
    store.archive_strategy("alpha", "churn", now=1700000100.0)
    store.restore_strategy("alpha", "churn")
"""

SEEDED_PAIRS = (("alpha", "ES"), ("alpha", "NQ"), ("beta", "ES"), ("gamma", "NQ"))


def _spawn(home: Path, program: str, *args: str) -> subprocess.Popen[str]:
    """Start one child with `home/scripts` on its path. A REAL separate process."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(home / "scripts"), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    return subprocess.Popen(  # nosec B603 - fixed argv, no shell, interpreter is ours
        [sys.executable, "-c", program, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )


def _run_child(home: Path, program: str, *args: str) -> dict[str, Any]:
    """Run one self-killing child to completion and parse its one JSON line.

    Returns `{"__failed__": why}` rather than raising, so every blocked path in
    this gate becomes a CANNOT_MEASURE naming the reason instead of a traceback.
    """
    proc = _spawn(home, program, *args)
    try:
        out, err = proc.communicate(timeout=CHILD_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        return {"__failed__": f"child exceeded {CHILD_TIMEOUT_S}s and was killed"}
    if proc.returncode != -signal.SIGKILL:
        return {
            "__failed__": (
                f"child was reaped with returncode {proc.returncode} rather than "
                f"-SIGKILL ({-signal.SIGKILL}); this gate's whole premise is that "
                f"the value crossed a REAL process death. stderr: {err.strip()[:400]}"
            )
        }
    line = out.strip().splitlines()
    if not line:
        return {"__failed__": f"child printed nothing. stderr: {err.strip()[:400]}"}
    try:
        parsed = json.loads(line[-1])
    except json.JSONDecodeError as exc:
        return {"__failed__": f"child output is not JSON: {exc!r} / {line[-1][:200]!r}"}
    parsed["__stderr__"] = err.strip()[:400]
    return parsed


def _pairs(rows: list[list[Any]]) -> tuple[tuple[str, str], ...]:
    """The sorted `(strategy, symbol)` set of a reported row list."""
    return tuple(sorted((str(r[0]), str(r[1])) for r in rows))


def _values(rows: list[list[Any]]) -> dict[tuple[str, str], tuple[float, int]]:
    """`{pair: (ema, days)}` from a reported row list."""
    return {(str(r[0]), str(r[1])): (float(r[2]), int(r[3])) for r in rows}


def _shape_defect(written: dict[tuple[str, str], tuple[float, int]]) -> str:
    """NON-VACUITY: the fixture must be entangled before "exactly" means anything."""
    pairs = set(written)
    strategies = {p[0] for p in pairs}
    symbols = {p[1] for p in pairs}
    multi_symbol = {
        s for s in strategies if len({p[1] for p in pairs if p[0] == s}) > 1
    }
    shared = {y for y in symbols if len({p[0] for p in pairs if p[1] == y}) > 1}
    if len(pairs) < 4 or len(strategies) < 3 or not multi_symbol or len(shared) < 2:
        return (
            f"the pre-archive table is not entangled enough to make 'exactly' a real "
            f"claim: {len(pairs)} pair(s), {len(strategies)} strategies, "
            f"multi-symbol strategies {sorted(multi_symbol)}, shared symbols "
            f"{sorted(shared)} — need >=4 pairs, >=3 strategies, >=1 strategy on two "
            f"symbols and >=2 symbols shared by two strategies"
        )
    return ""


def _arm_survives_death(
    writer: dict[str, Any], reader: dict[str, Any], defects: list, ev: list
) -> dict[tuple[str, str], tuple[float, int]]:
    """D1 — the SAME values, read by a DIFFERENT pid, after a real SIGKILL."""
    site = "scripts/nixscore/store.py:ScoreStore._commit"
    written = _values(writer["rows"])
    seen = _values(reader["live"])
    if seen != written:
        defects.append(
            (
                site,
                (
                    f"pid {writer['pid']} made {sorted(written.items())} durable and then "
                    f"died by SIGKILL; pid {reader['pid']} read back "
                    f"{sorted(seen.items())} — the score did NOT persist across process "
                    f"death (§6.6:430, §4:275)"
                ),
            )
        )
        return written
    if reader.get("cold_live", -1) != 0:
        defects.append(
            (
                site,
                (
                    f"the COLD-START CONTROL store was not empty ({reader.get('cold_live')} "
                    f"live pair(s)) — so 'the reader found rows' is not attributable to "
                    f"the surviving file"
                ),
            )
        )
        return written
    ev.append(
        f"SURVIVED: writer pid={writer['pid']} wrote {len(written)} pair(s) "
        f"(revision {writer['revision']}) and was reaped with -SIGKILL; reader "
        f"pid={reader['pid']} — a DIFFERENT process — read back byte-identical "
        f"values {sorted(seen.items())}, while the cold-start control store opened "
        f"in the same reader was empty (0 pairs)"
    )
    return written


def _arm_archive_exactly(
    archiver: dict[str, Any],
    reader: dict[str, Any],
    written: dict[tuple[str, str], tuple[float, int]],
    defects: list,
    ev: list,
) -> None:
    """D2 — archival moves EXACTLY the quarantined strategy's pairs, and no others."""
    site = "scripts/nixscore/store.py:ScoreStore.archive_strategy"
    expect_gone = tuple(sorted(p for p in written if p[0] == QUARANTINED))
    expect_live = tuple(sorted(p for p in written if p[0] != QUARANTINED))
    live = _pairs(reader["live"])
    archived = _pairs(reader["archived"])
    if live != expect_live or archived != expect_gone:
        defects.append(
            (
                site,
                (
                    f"archiving {QUARANTINED!r} should have left live={list(expect_live)} "
                    f"and archived={list(expect_gone)}; after the archiver died, pid "
                    f"{reader['pid']} read live={list(live)} archived={list(archived)} — "
                    f"the archive did not remove EXACTLY that strategy's rows (§6.6:431)"
                ),
            )
        )
        return
    ev.append(
        f"EXACTLY: archiver pid={archiver['pid']} moved {list(archived)} and left "
        f"{list(live)} untouched across its own SIGKILL — {QUARANTINED!r} held two "
        f"symbols and both of its symbols are each shared with another strategy, so "
        f"over-removal by symbol and wholesale truncation were both visible and "
        f"neither happened"
    )


def _arm_archived_not_absent(
    reader: dict[str, Any],
    written: dict[tuple[str, str], tuple[float, int]],
    defects: list,
    ev: list,
) -> None:
    """§6.6's *archived, not destroyed* — as a fact a CONSUMER can read."""
    site = "scripts/nixscore/store.py:ScoreStore.presence"
    presence = {(str(p[0]), str(p[1])): str(p[2]) for p in reader["presence"]}
    gone = sorted(p for p in written if p[0] == QUARANTINED)
    wrong = [p for p in gone if presence.get(p) != "archived"]
    fabricated = presence.get(FABRICATED)
    if wrong or fabricated != "absent":
        defects.append(
            (
                site,
                (
                    f"archived pairs must read ARCHIVED and an unknown pair must read "
                    f"ABSENT; {[(p, presence.get(p)) for p in gone]} and "
                    f"{FABRICATED}={fabricated!r} — if a consumer cannot tell archived "
                    f"from absent, §6.6's 'archived, not destroyed' is prose"
                ),
            )
        )
        return
    kept = _values(reader["archived"])
    lost = {p: (kept.get(p), written[p]) for p in gone if kept.get(p) != written[p]}
    if lost:
        defects.append(
            (
                site,
                (
                    f"the archived RECORDS no longer carry the values that were archived: "
                    f"{lost} — archived-not-destroyed requires the history, not a tombstone"
                ),
            )
        )
        return
    ev.append(
        f"ARCHIVED != ABSENT: {gone} read back as Presence.ARCHIVED carrying their "
        f"pre-archive values, the never-seeded pair {FABRICATED} reads ABSENT, and "
        f"the archive names its cause ({reader['reasons'].get(QUARANTINED, '')[:90]}…)"
    )


def _arm_restore(
    restorer: dict[str, Any],
    reader: dict[str, Any],
    written: dict[tuple[str, str], tuple[float, int]],
    defects: list,
    ev: list,
) -> None:
    """§12.11 verb 3 — the rows come back, at the same values, and a ghost says so."""
    site = "scripts/nixscore/store.py:ScoreStore.restore_strategy"
    seen = _values(reader["live"])
    if seen != written:
        defects.append(
            (
                site,
                (
                    f"after 'quarantine-restore' the live table should be exactly the "
                    f"pre-archive table {sorted(written.items())}; pid {reader['pid']} "
                    f"read {sorted(seen.items())} — §12.11:779 returns the ARCHIVED ROWS, "
                    f"not a recomputation"
                ),
            )
        )
        return
    if restorer["ghost_rehydrated"] or not restorer["ghost_names_subject"]:
        defects.append(
            (
                site,
                (
                    f"restoring a strategy that was never archived reported "
                    f"rehydrated={restorer['ghost_rehydrated']} and a reason that "
                    f"{'names' if restorer['ghost_names_subject'] else 'does NOT name'} "
                    f"the subject — a mistyped operator id must not be a silent no-op"
                ),
            )
        )
        return
    ev.append(
        f"RESTORED: restorer pid={restorer['pid']} returned {restorer['restored']} and "
        f"pid {reader['pid']} read the full pre-archive table back at byte-identical "
        f"values; a restore of a never-archived strategy returned rehydrated=False "
        f"with a reason naming it, not silence"
    )


def _kill_trial(home: Path, root: Path, index: int, rng: random.Random) -> dict:
    """One victim churning archive/restore, SIGKILLed from OUTSIDE at a jitter."""
    store = root / f"trial{index}" / "scores.json"
    ready = root / f"trial{index}.ready"
    proc = _spawn(home, CHURN, str(store), str(ready))
    deadline = time.monotonic() + CHILD_TIMEOUT_S
    while not ready.exists() and proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.002)
    if not ready.exists():
        proc.kill()
        proc.communicate(timeout=CHILD_TIMEOUT_S)
        return {"__failed__": f"churn victim {index} never signalled readiness"}
    time.sleep(rng.uniform(JITTER_MIN_S, JITTER_MAX_S))
    proc.kill()
    proc.communicate(timeout=CHILD_TIMEOUT_S)
    if proc.returncode != -signal.SIGKILL:
        return {"__failed__": f"churn victim {index} exited {proc.returncode}, not -9"}
    seen = _run_child(home, READER, str(store), str(root / "cold.json"), "[]")
    seen["victim_pid"] = proc.pid
    return seen


def _arm_atomicity(trials: list[dict], defects: list, ev: list) -> None:
    """The archive is ATOMIC: after any kill, every pair is on exactly one side."""
    site = "scripts/nixscore/store.py:ScoreStore._commit"
    seeded = set(SEEDED_PAIRS)
    writes = 0
    sides = {"live": 0, "archived": 0}
    for index, trial in enumerate(trials):
        if trial["error"]:
            defects.append(
                (
                    site,
                    (
                        f"trial {index} (victim pid {trial['victim_pid']}) left a store "
                        f"the next process could not read: {trial['error']} — a killed "
                        f"writer must leave the whole previous document or the whole "
                        f"next one"
                    ),
                )
            )
            return
        live, archived = _pairs(trial["live"]), _pairs(trial["archived"])
        writes += int(trial.get("revision", 0))
        if set(live) | set(archived) != seeded or set(live) & set(archived):
            defects.append(
                (
                    site,
                    (
                        f"trial {index} (victim pid {trial['victim_pid']}) left "
                        f"live={list(live)} archived={list(archived)} — the seeded pairs "
                        f"{sorted(seeded)} must appear on exactly one side each; a pair "
                        f"in NEITHER place is a half-archived strategy"
                    ),
                )
            )
            return
        sides["archived" if archived else "live"] += 1
    if writes < MIN_CHURN_WRITES:
        defects.append(
            (
                site,
                (
                    f"the {len(trials)} victims committed only {writes} durable write(s) "
                    f"in total (floor {MIN_CHURN_WRITES}) — 'nothing was torn' over a "
                    f"population that small is a statement about an empty set"
                ),
            )
        )
        return
    ev.append(
        f"ATOMIC: {len(trials)} SIGKILLs from outside, landing after {writes} durable "
        f"whole-document writes in total; every post-kill store parsed, and in every "
        f"one the four seeded pairs sat on exactly one side "
        f"({sides['archived']} kills landed with alpha archived, {sides['live']} with "
        f"it live). BOUND: this does not prove a kill landed INSIDE os.replace — that "
        f"instant is not addressable from outside the victim — only that no observed "
        f"post-kill state was torn"
    )


def _blocked(
    stages: dict[str, dict[str, Any]], *, store_error_blocks: bool = True
) -> CheckResult | None:
    """Every state in which this gate has not earned a verdict. Never a PASS.

    `store_error_blocks` is FALSE for the kill trials, and that distinction is
    load-bearing: an unreadable store is a HARNESS problem in the lifecycle arms
    (nothing was set up) and is the DEFECT ITSELF in the atomicity arm (a killed
    writer left a torn document). Folding the second into CANNOT_MEASURE would
    make the atomicity arm unable to fail — the exact shape of a blind control.
    """
    for label, payload in stages.items():
        why = payload.get("__failed__")
        if why:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                detail=f"{label}: {why}",
            )
        if store_error_blocks and payload.get("error"):
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                detail=f"{label}: the store could not be opened: {payload['error']}",
            )
    return None


def _drive(home: Path, root: Path) -> dict[str, dict[str, Any]]:
    """The three lifecycle arms, each across a real death, in order."""
    store = str(root / "live" / "scores.json")
    cold = str(root / "cold.json")
    probes = json.dumps([list(p) for p in SEEDED_PAIRS] + [list(FABRICATED)])
    seed = f"{random.SystemRandom().uniform(1.0, 900.0):.6f}"  # nosec B311 - a nonce
    stages = {"writer": _run_child(home, WRITER, store, seed)}
    stages["reader1"] = _run_child(home, READER, store, cold, probes)
    stages["archiver"] = _run_child(home, ARCHIVER, store, QUARANTINED)
    stages["reader2"] = _run_child(home, READER, store, cold, probes)
    stages["restorer"] = _run_child(home, RESTORER, store, QUARANTINED, "no-such-id")
    stages["reader3"] = _run_child(home, READER, store, cold, probes)
    return stages


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Kill real processes around a real store and read the rows back from another."""
    home = ctx.nix_home
    if not (home / "scripts" / "nixscore" / "store.py").exists():
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"no scripts/nixscore/store.py under {home} — nothing to measure",
        )
    with tempfile.TemporaryDirectory(prefix="nixscorelife-") as tmp:
        root = Path(tmp)
        stages = _drive(home, root)
        stopped = _blocked(stages)
        if stopped is not None:
            return stopped
        rng = random.Random(20360)  # nosec B311 - jitter, not a secret
        trials = [_kill_trial(home, root, i, rng) for i in range(KILL_TRIALS)]
    stopped = _blocked(
        {f"kill-trial-{i}": t for i, t in enumerate(trials)}, store_error_blocks=False
    )
    if stopped is not None:
        return stopped
    return _verdict(stages, trials)


def _verdict(stages: dict[str, dict[str, Any]], trials: list[dict]) -> CheckResult:
    """Fold the five arms into one result. Kept out of `run` for the locals cap."""
    evidence: list[str] = []
    defects: list[tuple[str, str]] = []
    written = _values(stages["writer"]["rows"])
    shape = _shape_defect(written)
    if shape:
        return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=shape)
    evidence.append(
        f"NON-VACUITY: the pre-archive table held {sorted(written)} — "
        f"{QUARANTINED!r} on two symbols, and ES and NQ each shared with a second "
        f"strategy, so 'removed exactly' is not an identity"
    )
    _arm_survives_death(stages["writer"], stages["reader1"], defects, evidence)
    _arm_archive_exactly(
        stages["archiver"], stages["reader2"], written, defects, evidence
    )
    _arm_archived_not_absent(stages["reader2"], written, defects, evidence)
    _arm_restore(stages["restorer"], stages["reader3"], written, defects, evidence)
    _arm_atomicity(trials, defects, evidence)
    return result_from_defects(NAME, defects, "; ".join(evidence))


if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
