# ARC 041-T — STATUS-EMIT TOOLING · RESULTS

**Tier: TOOLING.** No Limiter slice, no invariant, no badge movement. `I8 / D3.425` remain ARC 042.
**Predecessor derived live:** brief said `≈ e033f98`; `git rev-parse HEAD` said **`41299aa`**, and
every figure below is measured against that tip.

---

## 1. Installed (byte-verbatim, `cmp`-clean before anything else ran)

| path | note |
|---|---|
| `scripts/arc_heartbeat.sh` | `chmod +x`, mode `755` |
| `checks/check_arc_status_contract.py` | + verify.py contract adapter appended (see §5) |
| `checks/check_tmpfs_inode_headroom.py` | + adapter, + ONE fixture change (see §6) |
| `CLAUDE.md` `## STATUS EMIT` | appended verbatim, + `### The standing arc prompt, rewired` |
| `CLAUDE-CHANGELOG.md` | instruction change recorded, per Change control |

## 2. Step 1 — BIND `check_arc_status_contract` from its own FAIL

```
$ .venv/bin/python checks/check_arc_status_contract.py --selftest
  [ok] clean -> PASS                                        (got=0, want=0)
  [ok] non-vacuity: detector sees >=1 pulse in clean log     (got=2, want=>=1)
  [ok] PLANT no-heartbeat -> FAIL                            (got=1, want=1)
  [ok] PLANT leaked-watchdog -> FAIL                         (got=1, want=1)
  [ok] kernel [watchdogd] after marker -> still PASS         (got=0, want=0)
  [ok] no-marker -> CANNOT-MEASURE                           (got=2, want=2)
  [ok] teardown only for kernel thread -> FAIL               (got=1, want=1)
=== SELF-TEST PASS ===   exit=0
```

## 3. Step 2 — EMITTER↔READER PARITY (the second-implementation trap), GREEN

The log below was **produced by the script**, not typed. `selfcheck` and `pulse` wrote their own
lines into it; only the kickoff line, the `[watchdogd]` decoy, the teardown and the marker were added.

```
kickoff: ARC 041T STATUS-EMIT TOOLING, 12 stages
watchdog started pid=4107773 (arc_heartbeat)
[ARC 041T ###----- 40% stage 5/12 - emitter-reader parity - 22s - ~33s - HEAD 41299aa no motion]
HEARTBEAT SELF-VERIFY: ok (emitter produced a pulse)
[ARC 041T ####---- 50% stage 6/12 - parity second beat - 22s - ~22s - HEAD 41299aa ADVANCED]
[watchdogd] kernel thread present pid=165 (must be ignored)
WATCHDOG TEARDOWN: confirmed dead (pid 4107773 / arc_heartbeat)
**** ARC completed ****

$ .venv/bin/python checks/check_arc_status_contract.py --log <that file>
[PASS] arc_status_contract  arc=041T  pulses=2  teardowns=1  wd_pid=4107773   exit=0
```

`RE_PULSE` accepts the script's real `#`/`-` bar; `arc` and `wd_pid` were both DERIVED from the log;
the `[watchdogd]` line was correctly ignored. **They agree.** One honest gap found and kept: the
STALE pulse renders `stage ?/?` and does not match `\d+/\d+` — correct, a stale beat is not evidence
the operator was informed.

## 4. Step 3 — BIND `check_tmpfs_inode_headroom` + live node02

```
$ .venv/bin/python checks/check_tmpfs_inode_headroom.py --selftest
  [ok] healthy -> PASS · non-vacuity: parser extracts real usage (4%, 1008363 free)
  [ok] EXHAUSTED (039R state) -> FAIL · at-ceiling 90% -> FAIL · just-under floor -> FAIL
  [ok] no-inode-limit -> CANNOT · wrapped fs name -> PASS · malformed -> CANNOT
=== SELF-TEST PASS ===   exit=0                       (8/8)

kickoff basetemp clean: /tmp/pytest-of-bbt removed — 888 inodes, 4 retained sessions
  (pgrep -x pytest == 0 first; never pkill -f on cc's own patterns)

$ .venv/bin/python checks/check_tmpfs_inode_headroom.py --mount /tmp
[PASS] tmpfs_inode_headroom  mount=/tmp  iuse=5%  free=1003613  (ceiling 90% / floor 20000)  exit=0
```

## 5. The adapter, and why it needed its OWN can-fail

`nixverify.loader` requires a module-level `run` and `engine._run_block` calls it as
`run(mode, ctx) -> CheckResult`. Both drop-ins already define a `run`, with a different signature —
registering them as shipped would have loaded cleanly and raised at call time, which is a gate that
reports nothing. An **append-only** adapter block was added to each (nothing above it altered): it
declares `DEPENDS_ON`/`RESOURCES`/`ON_FAIL`/`CORRECTABLE`/`SUBJECTS` for the AST reader and
DISPATCHES on the first argument's type, so the CLI and the engine share ONE measurement
implementation rather than acquiring a second (doctrine C.9).

**Check-contract rule 9: a retrofitted check is a NEW check.** The adapter arm was therefore bound
separately, against the real `load_check → run(Mode, Context) → validate_result` path:

```
check_arc_status_contract   [1] no fresh log       -> cannot_measure
                            [2] complete arc log   -> pass    (pulses=2 teardowns=1)
                            [3] PLANT no-heartbeat -> fail_needs_operator, site named
                            [4] plant removed      -> pass
check_tmpfs_inode_headroom  [1] live /tmp healthy  -> pass    (5%, 1003613 free)
                            [2] PLANT 039R state   -> fail_needs_operator, site=/tmp
                            [3] PLANT no inode cap -> cannot_measure
                            [4] plants removed     -> pass
```

## 6. The ONE departure from verbatim — found by a gate, not by taste

`check_price_ring` FAILED on `checks/check_tmpfs_inode_headroom.py:163`: the `_NOLIMIT` self-test
fixture named `/dev/shm` in its "Mounted on" column, and risk spec §12.7 gives the price firehose
the sole shared-memory exception. Adding the path to the gate's `ALLOWED` set would be closing a red
by weakening the instrument — **doctrine B.4 forbids it and the gate is right**. Fixed at the
subject: the column reads `/mnt/nolimit`. The fixture asserts that `df` printing `-` yields
CANNOT-MEASURE; the mount's spelling is no part of it. `--selftest` 8/8 before and after.

### 6b. A SECOND departure — this tree's pre-commit chain refused the drop-ins as shipped

"Pre-validated in a real interpreter" is not the same as validated against this tree's gates, and
four of them refused:

| gate | finding | repair |
|---|---|---|
| `ruff check` | `EXE001`, `PLW1510`, `ISC004`, `RUF059`, 4x `BLE001` | `chmod +x`, `check=False`, parens, `_ok0`; the blind excepts are check-contract rule 1 and were KEPT with `# noqa` + the reason, never narrowed |
| `ruff format --check` | both files | `ruff format` (the hook is a reporter, never a repairer — ARC 018) |
| `bandit (production)` | `B404`, `B603`, `B607`, 2x `B108` | `# nosec` + stated reason. **`# nosec B603,B607` silenced B607 and NOT B603** — the space-separated form is the one that works |
| `pylint --fail-on=E,F` / `mypy` | `E0102` / `no-redef` on the adapter's `run` | it IS a deliberate redefinition and is now declared as one |

**And one that was a real design fault, caught by a TEST rather than a linter.**
`test_check_standalone_nonvacuity.py::test_every_real_check_standalone_block_calls_validate_result`
named both files: every `checks/check_*.py` must route `__main__` through `validate_result` (or
`standalone_main`, which applies it). The drop-ins could not — their `__main__` sat ABOVE the
appended adapter, so the CLI exited before the engine entry point existed. Correct, and correct *by
statement order*. The block moved to the END of each file and now splits two surfaces: the
drop-in's own flags keep the drop-in's CLI (the brief's binding steps are spelled in them, and a
`--selftest` has no `CheckResult` to validate); everything else goes through `standalone_main`.
Both end at the same `run`.

**Every self-test, the parity check, the live measurement and the four-arm adapter can-fail were
re-run after each repair. None of them moved.**

## 7. Step 4 — REGISTRATION, and both are PERIODIC

`VERIFY-AND-CHECKS.md` was read directly. Part B.1: *"`bank.sh` runs the registered gates at STEP 2
of every arc bank"*, and B.6 names the only non-registry category (`prove_*` harnesses). **There is
no close-out-invoked tier to wire into** — registry membership IS periodic. Both gates are in
`checks/registry.json`, block `level-0`, `parallel: false`, `on_fail: continue`, and the plan was
**derived** by `verify.py --optimize --commit`, never hand-written. Registered checks 94 → 96
(`check_derived_claims`: `registered_check_count=96` from both `derived:checks_glob` and
`derived:registry_json`, 0 restatements).

- `check_tmpfs_inode_headroom` — **PERIODIC, +1 PASS** on a healthy box, live node state each sweep.
- `check_arc_status_contract` — **PERIODIC, +1 CANNOT-MEASURE** in the bare sweep. It defaults
  `--log` to the newest `scratchpad/arc_logs/*.log` within a 24 h window; with no fresh log, and
  with a log that has not yet reached its marker, it returns CANNOT-MEASURE and **never PASS**
  (rule 10). It PASSED against a real completed log in §3. **What that costs is D3.433.**

Also caught by the re-derivation: the committed plan had silently drifted — `--optimize` proposed
dropping `file-write:tmp` and `process:limiterd` from `level-0`'s claims, and no check declares
either any more. **D3.432.**

## 8. Step 5/6 — CLAUDE.md and the standing arc prompt

The block was appended verbatim. The rewire subsection makes the wiring explicit — kickoff →
`selfcheck`, every in-stage pulse and watchdog beat → `pulse`, every transition → `banner --name` —
and states that where the WAYPOINT BANNERS prose and the script's output differ, **the script is the
format**. **DOGFOODED:** every banner and pulse in this run came from the script; cc hand-formatted
nothing after Stage 2.

## 9. Close-out — `verify.py` on trunk, and the baseline is the interesting half

| | passed | failed | cannot | skipped | guarded |
|---|---|---|---|---|---|
| ARC 041 banked, at `41299aa` | 89 | 2 | 2 | 0 | 1 |
| **THIS ARC'S BASELINE, same commit, clean tree** | **86** | **5** | **2** | **0** | **1** |
| **post-change on trunk** | **88** | **4** | **3** | **0** | **1** |

**Three gates had moved before this arc wrote a line.** Two were its own untracked inbox
(`check_untracked_attribution`, and `check_price_ring` reading the `/dev/shm` literal in the
`downloads/` copy) and both cleared. The third is **D3.431** — `check_monitor_tui` ARM3 STALE PIN,
arms whose subject is the operator's out-of-tree statusline. Skipping the baseline would have
attributed all three to this arc; that is the incident `VERIFY-AND-CHECKS.md` B.6 records.

**How it moved, baseline → post-change:** `+2 passed` = the inode gate's new PASS, plus
`check_price_ring` recovering when the inbox copy was removed. `-1 failed` = the same recovery.
`+1 cannot-measure` = the status gate, exactly as the brief predicted. `check_untracked_attribution`
names precisely the three new uncommitted files and is a statement about the write-back.

Both `--selftest`s green. Parity check green. **No full pytest, no census** — no trading-path code
and no invariant touched.

## 10. CHECK-DEBT reconciled — 379 → 382 (+4 opened, −1 DISCHARGED)

Both figures are `check_derived_claims._p_check_debt_open_count`'s own, re-derived whole; neither
was typed.

- **D3.423 — DISCHARGED ARC 041-T.** The row ARC 039R opened when `/tmp` exhausted its inode table
  with 16 GB free and the arc read as a code fault. The gate is registered, bound from that exact
  state as its plant, and PASSES live on node02.
- **D3.430** — the RESIDUAL, named rather than absorbed into the word DISCHARGED: D3.423 asked for
  BOTH `f_bavail` and `f_favail` plus a basetemp reaper. Only the inode axis ships, and **D3.206 is
  the byte axis stopping an arc too**.
- **D3.431** — `check_monitor_tui` RED at the same commit ARC 041 banked green; verdict set by
  out-of-tree state.
- **D3.432** — the committed execution plan drifts from its own declarations and nothing compares
  them at load.
- **D3.433** — `check_arc_status_contract` audits the PREVIOUS arc by construction; its honest duty
  cycle is one arc behind.

## 11. Housekeeping

`/tmp/pytest-of-bbt` removed at kickoff. The three drop-in duplicates and the CLAUDE.md block source
removed from `downloads/` (the brief stays). Scratch under `scratchpad/` and the session scratchpad;
both gitignored.

---

## 12. POST-WRITE-BACK RE-MEASURE — banked at `1492beb`

`verify.py` over the merged tree: **89 passed | 3 failed | 3 cannot measure | 0 skipped | 1 guarded,
exit 1.**

| | passed | failed | cannot | skipped | guarded |
|---|---|---|---|---|---|
| ARC 041 banked (`41299aa`) | 89 | 2 | 2 | 0 | 1 |
| this arc's baseline (same commit, clean tree) | 86 | 5 | 2 | 0 | 1 |
| pre-commit, on trunk | 88 | 4 | 3 | 0 | 1 |
| **post-write-back (`1492beb`)** | **89** | **3** | **3** | **0** | **1** |

`86 → 89 passed`: the inode gate's new PASS, plus `check_price_ring` and
`check_untracked_attribution` recovering — the first when the `/dev/shm` literal left `downloads/`,
the second when the three new files stopped being untracked. `5 → 3 failed`: the same two
recoveries. `2 → 3 cannot-measure`: `check_arc_status_contract`, exactly as the brief predicted.

Three standing reds, none of them this arc's: `check_ibgateway_service` (tap, ECONNREFUSED),
`check_uncalled_entry_points` (standing since ARC 041), and `check_monitor_tui` — **already red at
this arc's baseline, at the commit ARC 041 banked green** — now D3.431.

The emitter's STALL arm fired for real during this run, unplanted: three pulses against a frozen
progress file produced `STALL WARNING: no motion in 3 intervals`.
