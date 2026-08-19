# ARC 039R — Limiter slice 1: CLOSE-OUT AND BANK (INTERIOR tier)

**Status: COMPLETE and BANKED.** **Limiter badge: RED** (slice 1 of many).
Ledger 371 -> 375. HEAD advanced `17bb390` -> `a64978a` -> the write-back commit.

---

## 0. What this arc was, and what it was not

ARC 039 slice 1 — the minimal Limiter runtime loop — was **already built and
committed at `17bb390`**. That run was **killed during close-out**: the full
pytest + full binding census tail turned a ~1h slice into 2.5h+. It left two
files modified-not-committed (`checks/gate_coverage_baseline.json`,
`docs/CHECK-DEBT.md`).

039R **does not rebuild the loop**. It banks it under the **INTERIOR tier** of
the tiered close-out rule. `scripts/nixrisk/loop.py`, `scripts/limiterd.py`,
`checks/check_limiter_loop_alive.py` and the tests were on disk and committed
before this arc started.

**This is an interior slice. The Limiter badge stays RED.**

---

## 1. DEFERRED — a stated decision, not a silent skip

| deferred | to | why |
|---|---|---|
| the full ~3400-test pytest suite | the Limiter's **GREENING slice** | tiered close-out: an interior slice runs the interior tier. This tax is what killed the previous run. |
| the full binding census | the Limiter's **GREENING slice** | same rule. `check_limiter_loop_alive`'s binding was instead established from an **already-observed real FAIL** (S3c). |

What ran in their place — a derived reverse-dependency closure, proven
non-vacuous before it was trusted — is in §5.

---

## 2. S1 — the committed slice, re-measured from OUTSIDE the process

`17bb390`'s commit message was not trusted. The running process was measured.

| claim | evidence | verdict |
|---|---|---|
| a live process on its own PID | pid **3869046**, `PPid 1` (own session, not this shell's child), `exe -> python`, `cwd -> /home/bbt/nix`, `Threads 2` | PASS |
| the heartbeat advances on the tick | `seq 22->23->24->25->26->27`, `ts` strictly increasing, and **every beat carries `pid: 3869046`** — the beat names its own publisher | PASS |
| SIGKILL **by PID** kills the beat | `/proc/3869046` gone, `kill -0` -> ESRCH, **`seq` froze at 54 across two 3s windows** (~12 heartbeat intervals, zero beats) | PASS |
| a SIGKILL leaves no clean stop record | `limiter.runtime.json` -> `stopped_ts: null`, §12.2:617's documented signature | PASS |
| restart proves flat | **new** pid 3887085, `flat: true`, `in_flight: []`, `seq` restarting at 4 — bound to the process, not to the file the killed one left | PASS |
| SIGTERM gives the clean record | `ticks=135, heartbeats=26, sender_alive=false, sender_joined=true, overruns=0, faults=[]`, `reason` naming the site | PASS |

`pkill -f` was never used — kills were by PID throughout (the ARC 038 hazard).
The hazard was nonetheless **observed live** this arc: `pgrep -af "scripts/verify.py"`
matched **its own wrapper shell** (pid 3889610) alongside the real process (3889646).

**§0a — what would make this pass while measuring nothing?** A "loop" that is a
function called once: refuted by `PPid 1` residency plus 135 ticks in one run.
A heartbeat set by a test rather than the tick: refuted structurally —
`loop.py:71` refuses `_publish_heartbeat` unless the caller is the tick thread,
and `heartbeat_publisher_idents` (`loop.py:79`) is the set the gate reads — and
empirically, the beat froze the instant the process died.

---

## 3. S2 — the gate ships with a demonstrated FAIL

`scripts/tests/test_check_limiter_loop_alive.py`: **6 passed in 15.0s**. Every
plant asserts the **reason**, never the exit code.

| plant | status asserted | site asserted | detail asserted |
|---|---|---|---|
| ghost heartbeat outliving the killed loop | `FAIL_NEEDS_OPERATOR` | *"seq advanced after death"* | *"THE HEARTBEAT ADVANCED WITHOUT THE LOOP"*, *"blind to a dead Limiter"* |
| entrypoint that returns (rc 0) | `FAIL_NEEDS_OPERATOR` | `scripts/limiterd.py` | *"EXITED with rc 0"*, *"A Limiter is a resident loop"*, **and asserts *"below the floor"* is ABSENT** — a subject that silences the instrument by dying must not buy the milder verdict |
| heartbeat naming a foreign pid | `FAIL_NEEDS_OPERATOR` | `risk_engine.heartbeat.json:pid` | *"is another process's beat"*, both pids, **plus a `pgrep` leak control** proving the gate reaps what it launched |

**Non-vacuity, three independent ways:** the real-daemon arm PASSES (so the arm
*can* pass — the plants drive something); an absent entrypoint is
`CANNOT_MEASURE` naming the path, never a Pass; and S1 killed a real loop by hand.

---

## 4. S3a — `verify.py` on trunk: ONE delta, and it was ours

`87 passed | 3 failed | 2 cannot measure | 0 skipped | 1 guarded — exit 1`
against the ARC 038 baseline `87 / 2 / 2 / 0 / 1, exit 1`.
Totals 93 vs 92 because **`check_limiter_loop_alive` is new** and ran `[ok]`.

| verdict | check | reason |
|---|---|---|
| FAIL | `check_ibgateway_service` | 127.0.0.1:4002 ECONNREFUSED — **baseline FAIL, unchanged** |
| FAIL | `check_uncalled_entry_points` | 25 unadmitted public entry points; plus `scripts/nixrisk/gate.py::GatePass.manifest` recorded `uncalled`, **measured** `gate_only` — **baseline FAIL, unchanged** |
| **FAIL** | **`check_derived_claims`** | **THE DELTA.** `derived:ledger_rows=374` vs `stated:series_table_latest_row=371` |
| ?? | `check_ibgateway_config` | ECONNREFUSED. Correctly Cannot-measure, **not Pass** (check-contract rule 10) |
| ?? | `check_observed_resource_claims` | downstream of the unreachable gateway; its resource use is UNOBSERVED |
| **GRD** | `check_artifact_gate_coverage` | `EXCLUDED -> ARC 040`, guard owner **live** |

The delta is **not a regression in the slice**: the killed run appended three
ledger rows (D3.420–D3.422) and never wrote the series row. Discharged in S3d.

---

## 5. S3b — the DERIVED closure, non-vacuity proven BEFORE it was trusted

**30 test files**, derived by grepping the tree for importers/readers of the six
changed artifacts. Not the ~3400-test suite.

**Non-vacuity gate (run first — a closure that is empty goes green by having
nothing in it):**

| changed artifact | closure members referencing it |
|---|---|
| `scripts/nixrisk/loop.py` | 1 |
| `scripts/limiterd.py` | 3 |
| `checks/check_limiter_loop_alive.py` | 1 |
| `checks/registry.json` | 18 |
| `checks/gate_coverage_baseline.json` | 5 |
| `docs/CHECK-DEBT.md` | 9 |

All six covered; every member exists on disk. **Non-vacuous.**

**Result: 7 failed, 644 passed (27m17s).** All 7 in **one** module,
`test_check_derived_claims.py`, each naming
`check_debt_open_items: DISAGREEMENT derived:ledger_rows=374,
stated:series_table_latest_row=371` with the **other 12 of 13 claims agreeing**.
One root cause, two independent instruments reddened by it.

*Cost note:* the closure took 27 min because `test_end_to_end.py` — a legitimate
reverse-dependency of the changed `registry.json` — runs whole `verify.py`
invocations. A reference-derived closure can pull in the most expensive module in
the tree; worth knowing before the greening slice sizes its own.

---

## 6. S3c — binding, without re-running the census

`check_limiter_loop_alive` is **BOUND**. The census keys a binding on a
`CheckResult` with a failing status returned by the gate's own `run()` (D3.418).
S2 observed exactly that **three times**, asserted by status object plus `site`
plus `detail`. No census re-run was needed to establish it.

---

## 7. S3d — the reconcile, and a gate that refused a bad token

1. **D3.423 opened** (the inode finding, §9).
2. **ARC 039 series row written stating 375** — derived by the gate's own probe
   `_p_check_debt_open_count`, not by arithmetic on a remembered figure.
3. The row's owning module was first written **`environment`**. The gate
   **REFUSED it**: `ProbeError: open row(s) carry no valid 'owning module' token:
   D3.423=environment` — loud, naming the row by id, exactly the failure mode
   that controlled vocabulary exists to produce. Corrected to **`verify`**, by
   that table's own rule *"the artefact that must CHANGE for the row to be
   discharged"*: discharging D3.423 means writing `checks/check_tmpfs_headroom.py`,
   and `verify` owns every `checks/check_*.py`. `node` owns the box's identity and
   units; it does not own the instrument that is missing.

**Independent re-measurement — fresh process, the check's own CLI, verify-only:**
`pass: 13/13 claim(s) compared`, `check_debt_open_items=375
[derived:ledger_rows=375, stated:series_table_latest_row=375]`, **exit 0**.

**The 7 closure failures went green:** `test_check_derived_claims.py` **16 passed**.
Closure total now **651 passed / 0 failed**.

---

## 8. S4 — guard survival, re-pointed BEFORE the write-back

All **eight** CHECK-A8/CHECK-A9 exclusions read `owner = ARC 040`,
`temporary = true`:
`actuation.py`, `contract.py`, `engine.py`, `gitenv.py`, `loader.py`,
`optimize.py`, `registry.py`, `render.py`.

Nothing was discharged — they are nixverify machinery already driven by pytest,
and doctrine C.9 still forbids a second instrument over them. The re-point is made
**before** `sessions/SESSION.md` names this arc complete: `guard_owner_defect`
reads the completion record, so an exclusion still owned by a completed arc would
take the gate GUARDED -> CANNOT_MEASURE and the guarded count 1 -> 0. The
D3.342 / D3.417 pattern, applied in the right order.

---

## 9. FINDING — the arc was stopped mid-flight by an exhausted INODE table

`/tmp` (tmpfs): **1,048,576 of 1,048,576 inodes used, 0 free — with 16 GB of
space still available.**

It surfaced as a bare `bash: /tmp/...: No space left on device` that silently
swallowed a file write and prevented `scripts/limiterd.py` from starting at all.
**It read as a code fault**, and it was diagnosed as one until `df -i` was run:
every operator reflex answers "No space left on device" with `df -h`, and `df -h`
said the disk was 49% full.

Consumer: `/tmp/pytest-of-bbt/` — **1,004,087 inodes across 32 retained pytest
basetemp sessions**, 96% of the whole tmpfs inode table. The accumulated debris of
exactly the full-suite runs this tiered close-out exists to avoid. `rm -rf`
reclaimed **1,004,194 inodes and 14 GB**.

Nothing in `checks/` samples `os.statvfs(...).f_favail`. **D3.423**, owed to
**ARC 040**: a `check_tmpfs_headroom` sampling *both* `f_bavail` and `f_favail`
against declared floors and refusing on either, plus a basetemp reaper in the
close-out path. Its can-fail plant must fill a scratch tmpfs's **inode** table and
require the gate to name the **inode** axis — a gate that only reads bytes passes
on the very state that stopped this arc.

---

## 10. The status contract (the new observability system)

- **Total stages fixed at kickoff: 11**, enumerated once, tier declared INTERIOR.
- **Background heartbeat watchdog** on its own 300s timer, a separate detached
  process (pid 3868453) writing its own log — so no foreground operation can
  starve it. It beat through a 7-minute `verify.py`, a 27-minute closure, and the
  inode exhaustion itself.
- **Self-verify at kickoff caught a real defect — in the instrument.** The first
  self-verify returned **FAIL**, and the watchdog was alive the whole time: `$!`
  under `setsid` names the **wrapper**, which had already exited. The pid was
  recovered from the watchdog's own first log line (`[watchdog] up pid=...`) and
  the instrument corrected. A blind run would have carried a wrong pid all arc.
  **This is the argument for requiring the self-verify, made by the self-verify.**
- **Progress file** `scratchpad/arc_progress.txt` stamped `arc=039R` + a monotonic
  timestamp; the watchdog validated the stamp before trusting it (STALE PROGRESS
  FILE otherwise) and re-derived HEAD live from `git log --oneline -1` on a
  scrubbed git env every beat, never from a cached summary. Motion reported per
  beat; no STALL WARNING fired.

---

## 11. Badge verdict and slice 2

**Limiter: RED.** Slice 1 — the minimal runtime loop — is **banked**: it is a
resident process, its heartbeat is published from the tick and dies with the
process, and a gate proves that by killing it.

**Slice 2 = the GO-TIMEOUT (I5)**, driven against this now-running loop.
Its first input is already on the ledger: **D3.420** — `§4:210` is the
GO-timeout, not the one-in-flight lock, and shipped code has been citing it for
the lock since ARC 034. Also standing against the Limiter: **D3.421** (the daemon
has no systemd unit, so §12.2's supervision governs a process nothing starts) and
**D3.422** (the tick cadence is a declared Nix addition with no home in `risks/`).
