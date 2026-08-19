# ARC 038 sub-agent F — LIVENESS, WEDGE, AND THE HOT PATH

Worktree: `/home/bbt/nix-wt-arc-038-f`   Branch: `arc-038-f`   Interpreter: `/home/bbt/nix-wt-arc-038-f/.venv/bin/python` (CPython 3.14.4)
Invariants assigned: **I5** — *"One in-flight action per strategy — and it can never wedge (GO-timeout)"* (§14:965; C6 §15:994; §4:210-212) · **I9** — *"Hot path = cache reads + arithmetic only"* (§14:965; §11:579; §5:306; §6.5:408)

All `§` citations are to `docs/nics_risk_subsystem_spec_v1.3.md` (FROZEN). v1.4 was not read as authority and is not cited.

## VERDICT TABLE

| invariant | red-team attempt | outcome | gate audited | gate non-vacuous? | gate reddens on plant? |
|---|---|---|---|---|---|
| I5 | real `SIGKILL` of a real child process holding a GO published over a real `ipc://` socket, then wait past `go_timeout_s`=10 | **VIOLATION** (FF1) | `check_orphan_recovery` | yes — `settrace` over a real run counted `recovery.py` `beat`x1 `miss`x4 `poll`x8 `arm`x14 `register`x12 `take_in_flight`x2 `force_deregister`x8 `recover`x7 | yes — PLANT A (`dead = False`) → RED naming `scripts/nixrisk/recovery.py:heartbeat`; PLANT B (teardown leaves the row) → RED naming `scripts/nixrisk/recovery.py:force-deregister: the one-in-flight lock survived the teardown` |
| I5 | double / 8-way concurrent GO for one strategy | **VIOLATION** (FF2) — 8 takes accepted, lock silently re-pointed | `check_limiter_gate` | partly — it executes `InFlightLockRule.evaluate` x4, but only through an always-clear port | **NO — GREEN under PLANT C** (FF3): the rule's whole DENY branch deleted, `check_limiter_gate`, `check_orphan_recovery`, `check_allocator_sizing` all pass, 116 tests pass |
| I5 | backwards clock step of 1e6 s against the death detector | **RESISTED** (RF1) | `check_supervision` | yes | yes — PLANT E (cap never trips) → RED naming `scripts/nixrisk/supervision.py:cap` |
| I5 | is the wedge-breaker WIRED? shipped-population census | **VIOLATION** (FF5) — built, gated, called by nothing shipped | `check_mirror_liveness` | yes — real `SIGKILL`, `-9` reaped, `/proc` gone, 42,411 decisions off the corpse | yes — PLANT F (a dead peer reads ALIVE) → RED naming `scripts/nixscore/liveness.py:PublisherLiveness[window]` |
| I9 | PEP-578 audit-hook census over 2,000 real gate evaluations, three port configurations | **RESISTED** (RF2) — zero `open` / `socket` / `subprocess` / `os.*` events in every arm | `check_plane1_hot_path` | yes — 2,543 `scripts/nixrisk/gate.py` call events traced during `baseline(50)`; `_ledger` printed as `None` | yes — PLANT 1 (2 ms block in `GatePass.evaluate`) → RED; PLANT 2 (real `write(2)` per evaluation) → RED. **Site named is a WRONG CONSTANT** (FF6) |
| I9 | put the REAL `ReservationLedger` + REAL `Plane1Wal` on the timed path, as production does | **VIOLATION of the GATE's coverage** (FF4) — one unbuffered `write(2)` per approval, max 13.3 → 1169.8 µs | `check_staleness` | yes — 10 arms over the real `freshness.py` from the real config | yes — PLANT D (stale never blocks) → RED naming `FreshnessTracker.reading` **and** `StalenessFlagPort.read` |
| I9 | 20,000 ranking-table cache MISSES: is a miss a hidden compute or fetch? | **RESISTED** (RF3) — 0 audit events, 0 `RealizedEmaEngine` calls, 81 ns/read | `check_allocator_lifecycle` | yes | yes — PLANT H (dying strategy still eligible) → RED naming `lifecycle.py:eligibility_from_mirror`. (PLANT G, quarantine screen deleted, left it green — correctly: that subject belongs to `check_allocator_weighting`, which went RED, 6 tests failed) |

---

## FINDINGS

### FF1 — §14's GO-timeout does not exist, and a real death wedges the lock permanently
- **Invariant:** I5. §14:965 — *"One in-flight action per strategy — **and it can never wedge (GO-timeout)**."* §15:994 C6 — *"**GO-timeout** — lost-GO deadlock on the one-in-flight lock broken. §4, CC-10."* §4:212 — *"if a strategy receives no sized/denied feedback within T of emitting GO (**e.g. Allocator died holding it**), it treats the GO as denied and resets to flat-and-free. The in-flight lock can never wedge on a lost message."*
- **Site:** `scripts/nixrisk/recovery.py:424` — `def take_in_flight(self, strategy_id, client_order_id)` — and the absence of any counterpart. The ONLY shipped site that clears the field is `scripts/nixrisk/recovery.py:465` — `row.in_flight = None`, inside `force_deregister`. `risks/limiter.config.json:go_timeout_s = 10` is read by exactly one shipped module, `scripts/risk_config.py:408`, and only to cross-validate it against `pending_ack_timeout_ms`.
- **Scenario (executed):** a real child process (`StatePublisher` on a real `ipc://` endpoint) published one GO; the Limiter side received it through a real `StateSubscriber`, registered the strategy in the shipped `StrategyRegistry`, took the in-flight lock, and built the shipped `GatePass` over the shipped `default_manifest` with the registry as the `InFlightPort`. The child was killed with `os.kill(pid, signal.SIGKILL)`, reaped, and its `/proc` entry checked. Then the drill waited past the configured timeout and re-read the lock and the gate. Command: `.venv/bin/python <scratch>/wedge_drill.py`; the durable form is `scripts/tests/test_arc038_f_inflight_lock.py::test_a_REAL_SIGKILL_of_the_GO_HOLDER_leaves_the_lock_HELD`.
- **Observed:**
  ```
  GO received off a REAL ipc:// socket: {'strategy_id': 's1', ... 'client_order_id': 'c-1', 'pid': 2700546}
  child pid 2700546 alive: True
  BEFORE death: gate on a NEW proposal -> deny | in_flight_lock
  SIGKILL: reaped rc=-9 (expect -9); /proc/2700546 exists: False
  AFTER 11.0s (go_timeout_s=10):
    registry.in_flight('s1') -> (True, 's1: one-in-flight lock held by c-1 (§4:210)')
    gate on a NEW proposal   -> deny | in_flight_lock | s1: one-in-flight lock held by c-1 (§4:210)
    registration still held  -> True
  VERDICT: WEDGED
  ```
  Elapsed time to reset: **never**. The configured knob is 10 s; there is no code that reads it as a deadline. An AST census over the shipped population (`git ls-files scripts` minus `scripts/tests/`) returned ONE release site and SIX modules that merely mention the `go_timeout` token — five as a Plane-1 event-type *name* (`plane1_sink.py:261`, `plane1_seed.py:297`, `projection.py:161`, `seam.py:483`, `nixscore/ema.py:205`) and one as the boot validator.
- **Why the tests did not catch it:** the tree's entire evidence for C6 is (a) `test_risk_config.py::test_go_timeout_REJECTS_a_breaker_that_outruns_the_resolution`, which asserts a *relation between two knobs*, and (b) `check_plane1_schema` accepting `go_timeout` as a spellable event kind. Both are true of a system with no timer. No instrument asks *"does anything measure T?"*, and §11.9-style "the mechanism exists" evidence was never distinguished from "the mechanism runs".
- **Status:** **BLOCKS.** Building the timer is BUILDING, which this arc forbids ("It BUILDS NOTHING"). What IS discharged: the wedge and the census are pinned as a one-way ratchet in `scripts/tests/test_arc038_f_inflight_lock.py`, with a can-fail half (`with_a_timeout=True`) that simulates the §4:212 reset and requires every assertion to flip — so the assertions are provably falsifiable and the fix cannot land unnoticed.
- **Debt row:** D3.398 (and D3.405 for the missing Allocator watcher, D3.407 for the unwired spine)

### FF2 — the one-in-flight LOCK does not enforce one in flight; only the rule that reads it does
- **Invariant:** I5. §4:210 — *"**one in-flight action per strategy.**"*
- **Site:** `scripts/nixrisk/recovery.py:424-428` — `row.in_flight = client_order_id` / `row.pending[client_order_id] = "pending"`, with no guard on the prior value, in a method whose docstring reads *"Occupy the one-in-flight lock (§4:210-212)"*.
- **Scenario (executed):** `take_in_flight` called twice, then eight times from eight real threads at a `threading.Barrier`. Command: `.venv/bin/python <scratch>/lock_variants.py`.
- **Observed:**
  ```
  after first take : (True, 's1: one-in-flight lock held by c-1 (§4:210)')
  SECOND take ACCEPTED (no refusal raised)
  after second take: (True, 's1: one-in-flight lock held by c-2 (§4:210)')
  row.pending      : {'c-1': 'pending', 'c-2': 'pending'}
  teardown reports released_in_flight = c-2 dropped_pending = ('c-1', 'c-2')
  ...
  takes accepted: 8 refused: 0
  lock now names: s4: one-in-flight lock held by c-7 (§4:210)
  pending rows  : ['c-0' ... 'c-7']
  ```
  The lock names only the newest `client_order_id`; the older one is live in `pending` and unreachable through `in_flight()`, and `force_deregister` reports **one** `released_in_flight` for **eight** takes. A denial an operator reads names `c-7` while `c-0..c-6` are equally pending.
- **Why the tests did not catch it:** `test_recovery.py:520` and `checks/check_orphan_recovery.py:516,684` each call `take_in_flight` exactly ONCE per world. No instrument ever called it twice, so the unguarded mutator was never asked the question. `ReservationLedger.take` DOES refuse a duplicate — the registry's own docstring cites §4's one-in-flight rule as that ledger's justification, while itself enforcing nothing.
- **Status:** **DISCHARGED IN THIS ARC.** Minimal, local, reversible guard added to `take_in_flight`: a second take while the lock is held raises `RecoveryError` naming BOTH client_order_ids and §4:210, and changes nothing. Control: `scripts/tests/test_arc038_f_inflight_lock.py::test_a_SECOND_TAKE_of_the_inflight_lock_is_REFUSED_and_says_why` and `::test_CONCURRENT_takes_cannot_BOTH_hold_the_lock`. Proof the control can fail: `::test_the_UNGUARDED_SHAPE_produces_the_orphan_FF2_measured` runs the UNPROTECTED half FIRST — writing the field directly, exactly as the old code did — and requires the bad outcome (lock names only `c-2`, teardown reports one release for two takes) to APPEAR.
- **Debt row:** D3.399 (the residual: a retired `client_order_id` is re-admitted after a re-registration)

### FF3 — the rule that enforces §14's lock had no can-fail control anywhere in the tree
- **Invariant:** I5. §14:965 and §4:210-212.
- **Site:** `scripts/nixrisk/gate.py:339-343` — `locked, reason = self._port.in_flight(order.strategy_id)` / `if locked: return _blocked(...)`. `grep -rn InFlightLockRule` over the entire tree returns exactly **two** hits: `gate.py:315` (its own `class`) and `gate.py:944` (the one `default_manifest` line that constructs it).
- **Scenario (executed):** the whole blocking branch deleted (`del locked, reason` in its place — PLANT C), then every gate and test that touches the pass was run. Commands: `.venv/bin/python checks/check_limiter_gate.py`, `checks/check_orphan_recovery.py`, `checks/check_allocator_sizing.py`, `.venv/bin/python -m pytest scripts/tests/test_limiter_gate.py scripts/tests/test_presize_integration.py scripts/tests/test_recovery.py scripts/tests/test_reservations.py scripts/tests/test_allocator_sizing.py -q`.
- **Observed:** all three gates **pass**; `116 passed in 0.27s` (plant verified in place by `grep -n ARC038F-PLANT-C scripts/nixrisk/gate.py` immediately before the run). A whole-suite run under the same plant was started and then ABANDONED — it was still inside `test_check_derived_claims` when the plant had to come out, and a partial result is not a result, so nothing is claimed from it. Cause, measured: every instrument in the tree hands `default_manifest` an always-clear `in_flight` port — `checks/check_limiter_gate.py:_shipped_manifest` (`in_flight=clear`), `checks/check_allocator_sizing.py:949` (`in_flight=_Free()`), `scripts/tests/test_limiter_gate.py:189,268,334` (`in_flight=clear`), `scripts/tests/test_presize_integration.py:199` (`in_flight=_InFlight()` returning `False, ""`). The shared `Flag` double in `test_limiter_gate.py` already implements `in_flight(strategy_id)` and could have been blocked with one argument; it never was. The other eight rules' blocking branches ARE driven, so this is one rule, not a class.
- **Why the tests did not catch it:** the split stated in `test_limiter_gate.py`'s own docstring — *"anything about DISPATCH ORDER … belongs to the check; anything about what an individual rule DECIDES belongs here"* — is honoured for eight rules and silently skipped for the ninth.
- **Status:** **DISCHARGED IN THIS ARC** by a pytest suite rather than a new gate (doctrine C.9: `check_limiter_gate` already owns the pass, and a second gate re-asserting it is the duplicate instrument C.9 forbids). `scripts/tests/test_arc038_f_inflight_lock.py::test_the_INFLIGHT_LOCK_RULE_DENIES_through_the_shipped_manifest` drives the DENY through the shipped `default_manifest` with the REAL `StrategyRegistry` and asserts the decision, the rule NAME, the held `client_order_id`, the `§4:210` citation and §5's fail-fast (the rules after the lock never ran). Proof it can fail: `::test_the_DENY_assertions_REJECT_a_lock_rule_that_never_blocks` substitutes a never-blocking rule at the same manifest position and requires APPROVE.
- **Debt row:** D3.401

### FF4 — `check_plane1_hot_path` measures a gate with `ledger=None`, so the only I/O the shipped approve path performs is outside every timed region
- **Invariant:** I9. §14:965 — *"Hot path = cache reads + arithmetic only."* §11 item 6 — *"**Group-commit** event-log writes off hot path (WAL-buffered)."*
- **Site:** `scripts/plane1_hotpath_drill.py:_gate()` — `return GatePass(clear, list(rules))`, i.e. `GatePass.__init__`'s third parameter `ledger` defaults to `None`. Measured directly: `drill GatePass._ledger : None`. The path it therefore excludes is `gate.py:_settle` → `reservations.py:297 take` → `reservations.py:418 _emit` → `reservations.py:_emit → plane1.enqueue` → `wal.py:304 enqueue` → `self._fh.write(record)` on a handle opened `open(self.path, "ab", buffering=0)` (`wal.py:290`).
- **Scenario (executed):** the same shipped gate, the same order, the same picture, the same `default_manifest`, run in three port configurations — the drill's stub ports; the REAL `StalenessFlagPort`/`ClockSkewMonitor`/`HaltFlag`/`StrategyRegistry`; and those plus the REAL `ReservationLedger` over a REAL `Plane1Wal` — timed with `perf_counter_ns`, then re-run under `strace -f -c -e trace=write,fsync,fdatasync,openat`. Commands: `.venv/bin/python <scratch>/hotpath_observe.py {time,census}-{stub,real,real-ledger} --n {2000,4000}` and `strace -f -c -e trace=write,fsync,fdatasync,openat .venv/bin/python <scratch>/hotpath_observe.py time-real-ledger --n 4000`.
- **Observed:** n = 4,000 evaluations per arm.

  | arm | p50 µs | p99 µs | **max µs** | clock reads/eval | WAL appends | fsyncs |
  |---|---|---|---|---|---|---|
  | stub ports (**what the gate measures**) | 8.19 | 9.78 | **13.32** | 0 | — | — |
  | real §11.1 ports | 21.97 | 24.26 | **46.09** | 5.0 | — | — |
  | real ports + real ledger + real WAL | 34.26 | 38.40 | **1169.80** | 5.0 | 4,200 | 0 |

  `strace -c` on the third arm: **`write` 4,202 calls**, `openat` 125, `fsync` 0 — i.e. **one unbuffered `write(2)` syscall per approved gate evaluation.** The `buffering=0` is deliberate and documented (`wal.py`: *"so `enqueue` issues the `write(2)` itself rather than handing bytes to a userspace buffer that a SIGKILL would take with it"*), so this finding is NOT "the WAL is wrong" — it is that the standing gate's timed region excludes it, and the excluded thing carries an 88x tail nobody measures.
- **Why the tests did not catch it:** the drill's `§0a` is written entirely about *concurrency with the group-commit* — baseline vs concurrent vs synchronous control — and that relation is real and correctly measured. The question *"is the ledger even on the path we are timing?"* is a different one, and the drill answers it by construction (`ledger=None`) rather than by measurement.
- **Status:** **DISCHARGED-BY-SUITE for the property, BLOCKS for the standing gate.** `scripts/tests/test_arc038_f_hot_path_ledger.py` owns the arm the drill lacks: the append COUNT (`wal.enqueued == EVALUATIONS`, `wal.fsyncs == 0`), a PEP-578 audit-event census over the real approve path in a CHILD interpreter with an explicit `env=` and the child's own `nixrisk.gate.__file__` asserted (D3.344), and a timing arm with a sleeping Plane-1 port proving elapsed time inside `evaluate` can see blocking. Its can-fail halves: a socket dialled per approval must appear as `socket.connect` in the census, and the ledgerless configuration must FAIL the append-count assertion — which is precisely the drill's configuration. Pointing the drill itself at a real ledger is a fourth arm and belongs to ARC 039.
- **Debt row:** D3.400

### FF5 — the wedge-breaker that DOES exist is on no live path, and it watches the wrong side of the GO
- **Invariant:** I5. §4:260-274 (heartbeat miss ⇒ presumed dead ⇒ flatten ⇒ force-deregister) is the only mechanism in the tree that can release a held in-flight lock.
- **Site:** `scripts/nixrisk/recovery.py:198 HeartbeatMonitor`, `:387 StrategyRegistry`, `:696 RecoverySequencer`, `:1055 heartbeat_from_config`.
- **Scenario (executed):** `checks/check_uncalled_entry_points.py` run to completion, plus a `grep` census over the shipped population, plus a `settrace` census over a real `check_orphan_recovery` run.
- **Observed:** the gate is **`fail_needs_operator`** and lists `scripts/nixrisk/recovery.py::HeartbeatMonitor.beat` as UNCALLED and `::StrategyRegistry.register` as GATE_ONLY; `recovery.py` is not in `checks/uncalled_entry_points_baseline.json` at all, so these are new, unadmitted findings. Independent grep: no caller of `beat`/`miss`/`poll`/`arm`/`register`/`take_in_flight`/`force_deregister`/`recover` exists outside `checks/` and `scripts/tests/`. **And the wiring would not help:** §4:212's breaker is on the STRATEGY side of a lost GO, while `HeartbeatMonitor` watches strategies — so in FF1's scenario the strategy is alive and the Allocator is the corpse. Enumerating the tree's liveness observers: `nixsentinel/watchdog.py` watches the **Risk Engine**; `nixscore/liveness.py::PublisherLiveness` watches the **Scoring publisher**; `HeartbeatMonitor` watches **strategies**. **Nothing watches the Allocator.**
- **Why the tests did not catch it:** every instrument asks *"does this behave correctly when driven?"*; `check_uncalled_entry_points` is the one that asks *"does anything drive it?"* and it is RED on exactly these rows today.
- **Status:** **BLOCKS** (wiring a loop is building). Recorded, with the liveness-coverage measurement, as debt.
- **Debt rows:** D3.405, D3.407 (and D3.404 for the mis-bucketing that made this harder to read)

### FF6 — `check_plane1_hot_path` names a constant `site` that is neither the defect nor on the path
- **Invariant:** I9, and check-contract rule 11 / `nix_check_contract.md` §18.
- **Site:** `checks/check_plane1_hot_path.py:163` — `_SITE = "scripts/nixrisk/wal.py:GroupCommitWriter.drain_once (off the hot path)"`, returned as `site=` on every FAIL and every CANNOT_MEASURE.
- **Scenario (executed):** a 2 ms `time.sleep` planted inside `scripts/nixrisk/gate.py:GatePass.evaluate` (PLANT 1), gate run.
- **Observed:** RED with an accurate detail — `§11 item 6: with a group-commit in flight the gate's p99 was 7324.9us, above 200us (10% of one commit)` — and a `site` pointing at a collaborator the same string describes as *"off the hot path"*. The detail carries the reason, so the gate is not vacuous; the site carries no information about which subject moved and actively misdirects.
- **Why the tests did not catch it:** `test_check_plane1_hot_path.py` hands `judge()` doctored result dicts and asserts on the returned defect strings, which is the right design — but `site` is assembled in `run()`, outside `judge()`, from a module constant, so no doctored input can reach it.
- **Status:** **DISCHARGED IN THIS ARC.** `_SITE` re-pointed at the measured hot path with the commit path named beside it. Control: `scripts/tests/test_arc038_f_hot_path_ledger.py` does not re-assert the gate's own relation (C.9); the site change is proven by re-running the PLANT-1 measurement and reading the new site:
  ```
  status: fail_needs_operator
  SITE  : scripts/nixrisk/gate.py:GatePass.evaluate (the timed hot path) vs scripts/nixrisk/wal.py:GroupCommitWriter.drain_once (the commit, off it)
  detail: §11 item 6: with a group-commit in flight the gate's p99 was 4309.4us, above 200us (10% of one commit) ...
  restore byte-identical: True
  ```
- **Debt row:** D3.406

---

## PROOFS OF RESISTANCE

### RF1 — I5 held: a backwards clock step cannot stop the death detector
- **Attack:** `HeartbeatMonitor` built with an injectable clock; one miss recorded at t=1000.0, then the clock stepped **backwards by 1,000,000 s**, then a second miss. Then a forward jump to 1e12 and a beat.
- **Command + output:** `.venv/bin/python <scratch>/lock_variants.py`
  ```
  ---- V5: CLOCK JUMP against the heartbeat (injectable clock) ----
    after 2 misses with the clock stepped BACKWARDS:
     presumed_dead = True | misses = 2
     reason: scripts/nixrisk/recovery.py: 's5' PRESUMED DEAD — 2 consecutive heartbeat miss(es) at a grace of 1 cycle(s) of 1.0s (§4:260-261 ...)
    after a forward jump, a BEAT still clears: ()
  ```
- **What this does and does NOT prove:** it proves the death verdict is a function of the CONSECUTIVE-MISS COUNT and not of elapsed time, so §12.3's clock faults cannot suppress it — the design choice `HeartbeatMonitor`'s docstring argues for is real. It does **not** prove any timeout is clock-safe, because **there is no timeout** (FF1); and it does not prove the monitor ever runs (FF5). The clock is only the *stamp* in the reason, and a backwards clock therefore produces a reason with a nonsensical `now` — reported, not repaired.

### RF2 — I9 held: no blocking operation on the hot path, in any port configuration
- **Attack:** a PEP-578 audit hook armed around 2,000 real `GatePass.evaluate` calls, recording EVERY audit event (no whitelist), in three configurations: stub ports; real `StalenessFlagPort` + `ClockSkewMonitor` + `HaltFlag` + `StrategyRegistry`; and those plus the real `ReservationLedger` over a real `Plane1Wal`. An audit hook cannot be removed and cannot be bypassed by re-import, so a clean result is an observation rather than a belief.
- **Command + output:** `.venv/bin/python <scratch>/hotpath_observe.py census-{stub,real,real-ledger} --n 2000`
  ```
  {"mode": "stub",        "evaluations": 2000, "audit_events_total": 0, "audit_events": {}, "blocking_class": {}}
  {"mode": "real",        "evaluations": 2000, "audit_events_total": 0, "audit_events": {}, "blocking_class": {},
   "clock_calls_per_eval": {"datetime_clock": 5.0}}
  {"mode": "real-ledger", "evaluations": 2000, "audit_events_total": 0, "audit_events": {}, "blocking_class": {},
   "clock_calls_per_eval": {"datetime_clock": 5.0},
   "wal_enqueued": 2001, "wal_bytes": 493753, "wal_fsyncs": 0}
  ```
  Zero events of ANY kind in 2,000 evaluations, in all three arms: no `open`, no `socket.connect`, no `subprocess.Popen`, no `os.*` mutator, no `time.sleep`. `gate.py` imports nothing from `nixscore`, so no EMA can be reached from it.
- **What this does and does NOT prove:** it proves the hot path performs no operation CPython audits — which is the whole family of blocking I/O. It does **not** cover `write(2)` on an already-open fd (PEP 578 has no event for it), which is exactly the hole FF4's `strace` arm fills and which turns out to be non-empty: 4,202 writes per 4,200 approvals. It does not prove the hot path is *arithmetic* — five wall-clock samples per evaluation are neither a cache read nor arithmetic (D3.402) — and it says nothing about a sink that burns CPU in Python, which the drill's own docstring already names as its residual.

### RF3 — I9 held: a ranking-table cache MISS is a miss, not a hidden recompute or fetch
- **Attack:** `nixscore.seam.RankingMirror` constructed and never fed a snapshot; the shipped consumer adapter `nixalloc.wiring._MirrorRankingTable` driven for 20,000 `row()` misses and 20,000 `available()` calls, with an audit hook armed and **every public callable on `RealizedEmaEngine` wrapped in a counting spy** so a recompute could not hide.
- **Command + output:** `.venv/bin/python <scratch>/ema_miss.py`
  ```
  {"misses_driven": 20000, "row_returned_non_None": 0, "available_true": 0,
   "audit_events_during_40000_reads": {}, "ema_engine_calls": {}, "ns_per_read": 81.3}
  ```
- **What this does and does NOT prove:** it proves §11.9's *"Ranking-table lookup only"* holds at the consumer: a miss returns `None`, `available()` returns `False`, the caller falls back to FCFS, and nothing recomputes or fetches. It does **not** prove the Limiter's other caches behave the same way, and `_MirrorRankingTable.row` does take one wall-clock sample per call when `self.now` is unset — a `time.time()` per lookup, on the same footing as D3.402.

---

## GATE AUDIT

### check_plane1_hot_path
- **Claims:** §11 item 6 — the gate never blocks on a group-commit. `SUBJECTS = ("scripts/plane1_hotpath_drill.py", "scripts/nixrisk/plane1_sink.py")`.
- **Scope containment proven by:** a `settrace` census over `plane1_hotpath_drill.baseline(50)` counting frames whose `co_filename` ends `nixrisk/gate.py` — **2,543 call events**, of which `evaluate` x500, `_dispatch` x100, `_settle` x50, `_verdict_defect` x450. The real `gate.py` IS executed. Also measured: `drill GatePass._ledger : None`, `_halt : _Clear`, manifest = the nine shipped rules.
- **Plant 1:** `import time; time.sleep(0.002)` at the head of `GatePass.evaluate` → **verdict: RED** — `§11 item 6: with a group-commit in flight the gate's p99 was 7324.9us, above 200us`, control arm still discriminating (p99 5500 µs against a 2000 µs delay). Site named: `scripts/nixrisk/wal.py:GroupCommitWriter.drain_once (off the hot path)` → **FF6**.
- **Plant 2:** a real `os.write` to an appended fd per evaluation, no sleep → **verdict: RED** — `the gate's p99 rose from 10.7us with nothing happening to 119.1us with commits in flight — more than 10.0x`; the plant's own log confirmed 16,493 writes. So the gate CAN see a synchronous write when one is on the path it times — which is what makes `ledger=None` (FF4) the whole gap.
- **Restore:** `cmp` byte-identical, `sha256 a1cd82fc…5dfff45c` before and after, `git status --short` empty → verdict green again.

### check_limiter_gate
- **Claims:** §3's two-phase pass — dispatch order, HALT position, fail-fast, hot-path shape.
- **Scope containment proven by:** a `settrace` census over a real `run()` — `GatePass.evaluate` x12, `_dispatch`, `_settle` x8, `InFlightLockRule.evaluate` **x4**, plus every other rule's `evaluate`.
- **Plant C:** `InFlightLockRule.evaluate`'s entire blocking branch removed → **verdict: GREEN (FINDING)**. `check_orphan_recovery` and `check_allocator_sizing` also green; 116 collected tests pass. Cause: `_shipped_manifest` wires `in_flight=clear`, so the branch is unreachable inside this gate. → **FF3**.
- **Restore:** byte-identical (`sha256` match), green.

### check_orphan_recovery
- **Claims:** §4:260-274 — heartbeat, the flatten-before-deregister ORDER, the four teardowns, the crash-loop cap.
- **Scope containment proven by:** `settrace` over a real `run()` — the SHIPPED `recovery.py` executed `beat` x1, `miss` x4, `poll` x8, `presumed_dead` x1, `_verdict` x18, `arm` x14, `disarm` x8, `register` x12, `take_in_flight` x2, `in_flight` x3, `force_deregister` x8, `recover` x7.
- **Plant A** (`dead = misses > self._grace` → `dead = False`): **RED**, site `scripts/nixrisk/recovery.py:heartbeat`, reason *"a SECOND consecutive miss did not presume death"* plus *"the death verdict carries no reason"*.
- **Plant B** (`force_deregister` leaves the row, lock and slot): **RED**, sites `…recovery.py:force-deregister: the registration survived the teardown`, `…: the one-in-flight lock survived the teardown`, and the order falsifier correctly reported that it no longer falsifies.
- **Restore:** byte-identical both times (`cmp` + `sha256`), green.

### check_supervision
- **Plant E** (`tripped = len(counted) >= crash_loop_max` → `False`): **RED**, site `scripts/nixrisk/supervision.py:cap`, reason quoting the shipped verdict at 3 and at 4 restarts against a cap of 3 read from `risks/supervision.config.json`. Restore byte-identical (`064b5591e547`), green.

### check_staleness
- **Plant D** (`blocked = age_ms > deadline` → `False`): **RED**, sites `scripts/nixrisk/freshness.py:FreshnessTracker.reading` **and** `…:StalenessFlagPort.read` — both halves named, plus a third defect that the denial reason no longer says `LAST ARRIVAL` (rule 11). Restore byte-identical (`db6b94b271a5`), green.

### check_mirror_liveness
- **Plant F** (`if self._peer is False:` → `if False:` — a dead writer reads ALIVE): **RED**, site `scripts/nixscore/liveness.py:PublisherLiveness[window]`, reason *"42411 arbitration(s) decided RANKED from the dead process's frozen table, over the 25 ceiling"*. The gate does a real `SIGKILL` and reaps `-9` with `/proc` gone in both arms. Restore byte-identical (`710c22c3c5ab`), green.

### check_allocator_lifecycle
- **Plant G** (the §4:272-274 quarantine screen deleted): **GREEN** — and correctly so: that subject belongs to `check_allocator_weighting`, which went **RED**, together with 6 failures in `test_allocator_weighting.py` (`…the_PATHWAY_denies_a_quarantined_strategy_through_the_real_pass` among them). Reported so the green is not read as a gap.
- **Plant H** (the in-flight-closing screen deleted, so a dying strategy still gets capital): **RED**, site `scripts/nixalloc/lifecycle.py:eligibility_from_mirror`, quoting the shipped verdict's own contradictory sentence back. Restore byte-identical (`571a8b884a69`), green.

### D3.346 / D3.347 — the two named hazards
- **D3.346 (load sensitivity of `MIN_OVERLAP_COMMITS`):** did NOT reproduce under this arc's six-sibling load — 8 consecutive `concurrent()` runs all reached overlap 6 (check floor 3, drill floor 5). The MECHANISM reproduces deterministically, and it is the GIL handoff cadence the drill's own docstring already names: at `sys.setswitchinterval(0.05)`, **3 of 6 runs fell to overlap 1–2**, below the check's floor, i.e. CANNOT_MEASURE. Discharged by pinning the switch interval for the arm's duration (restored in `finally`, reported in the result together with `iterations_driven` and `overlap_stretch_cap_hit`).

  **The constant was chosen by measurement, and the losing candidates matter**, because the obvious move — as small as possible — is the wrong one. The gate has TWO ceilings: p99 < 200 µs, and p99 < 10x the BASELINE arm's ~10 µs, i.e. ~100 µs. Eight runs each:

  | switch interval | overlaps | p99 µs | max µs | verdict |
  |---|---|---|---|---|
  | 0.05 (starvation proxy) | 6, 2, 5, 1, 5, 2 | 15.3–16.8 | 484–7,732 | **3 of 6 below the floor — D3.346** |
  | default 0.005, unpinned | 6 x8 | 15.9–17.5 | 5,085–5,234 | passes today; cadence-dependent |
  | 0.0005 | 6 x8 | 17.7–**102.2** | 639–1,660 | **rejected** — 102.2 is inside the 10x-baseline bound by 3 µs. Trading a CANNOT_MEASURE flake for a FAIL flake is worse |
  | 0.002 | 6 x8 | 16.3–39.4 | 2,124–**11,092** | rejected — one max outlier |
  | **0.001** | **6 x8** | **16.3–20.4** | **1,161–1,421** | **chosen** — ~3 µs cost against the unpinned arm, max down 4x |

  Final gate reading after the change: `pass … CONCURRENT (n=9967, 6 commit(s) completed during the loop): p50 8.3us, p99 20.1us, max 1372.7us — 167x below the synchronous control`, and `sys.getswitchinterval()` back to 0.005 afterwards. See D3.403.
- **D3.347 (leaked `/dev/shm nix_drill_*`):** not applicable to my drills — I opened no `/dev/shm` segment. Every `ipc://` endpoint I created is named with my own pid (`arc038f_<pid>_<n>`), every child is killed and reaped in a `finally`, every subscriber closed, and every WAL written under a `tempfile.TemporaryDirectory` prefixed `arc038f-<pid>-`. Verified: `ls /dev/shm` shows only the two PostgreSQL segments.

---

## MY OWN INSTRUMENTS, AND THE PROOF THEY CAN FAIL

| suite/control | plant used | reddened? | site named | restored green? |
|---|---|---|---|---|
| `test_arc038_f_inflight_lock::test_the_INFLIGHT_LOCK_RULE_DENIES_through_the_shipped_manifest` | `_NeverBlocks` substituted at the manifest's lock position (`::test_the_DENY_assertions_REJECT_a_lock_rule_that_never_blocks`) | yes — the falsifier produces APPROVE, which the control rejects | `in_flight_lock`, the held cid, `§4:210` | yes |
| `…::test_a_SECOND_TAKE_of_the_inflight_lock_is_REFUSED_and_says_why` | the UNPROTECTED half driven first (`::test_the_UNGUARDED_SHAPE_produces_the_orphan_FF2_measured`) writes `row.in_flight` directly, as the old code did | yes — the bad outcome (lock names only `c-2`, one release reported for two takes) must APPEAR | both client_order_ids, `§4:210` | yes |
| `…::test_CONCURRENT_takes_cannot_BOTH_hold_the_lock` | same unprotected half; 8 threads at a barrier, exactly 1 accepted / 7 refused | yes | `§4:210` in all 7 refusals | yes |
| `…::test_the_GO_TIMEOUT_CENSUS_the_wedge_ARC_038_measured` | a one-way RATCHET over the shipped population; it fails the day a release verb or a `go_timeout_s` reader appears | by construction (growth ⇒ RED) | the moved set, printed against the baseline, and D3.398 | n/a — the baseline IS today's measurement |
| `…::test_a_REAL_SIGKILL_of_the_GO_HOLDER_leaves_the_lock_HELD[with_a_timeout=True]` | a SIMULATED §4:212 reset-to-flat-and-free | yes — every assertion flips (lock free, gate no longer denies) | `in_flight_lock` / D3.398 | n/a |
| `test_arc038_f_hot_path_ledger::test_the_SHIPPED_APPROVE_PATH_enters_NO_blocking_audit_event` | a `socket.connect` per approval behind the ledger's Plane-1 port (`::test_the_CENSUS_SEES_a_socket_on_the_approve_path`) | yes — `socket.connect` ≥ 600 in the census | the event name and its count | yes |
| `…::test_the_SHIPPED_APPROVE_PATH_makes_exactly_ONE_WAL_APPEND_per_approval` | the drill's own `ledger=None` shape (`::test_the_APPEND_COUNT_assertion_REJECTS_a_ledgerless_gate`) | yes — 0 appends against 600 approvals | the two counts, and §3's approve⇒reserve | yes |
| `…::test_a_SLEEPING_PLANE1_PORT_shows_UP_in_the_pass` | both halves in one test: the real path must be FAST first, then a 2 ms sleeping Plane-1 port must inflate the p50 | yes | the two p50s against the delay | n/a |
| the `git ls-files` call in the census | none needed — `check_git_env_scrub` FOUND my first spelling: a hand-rolled pop of four `GIT_*` names is not the house scrub, and under a hook `-C` does not override an exported `GIT_DIR`. Re-routed through `nixverify.gitenv.scrubbed_env()`. This is the contract's own D3.205/D3.22 warning landing on me, and it is recorded rather than quietly fixed | yes — the gate failed the commit | `scripts/tests/test_arc038_f_inflight_lock.py:330` | yes |
| the census child itself | D3.344: explicit `env=`, `PYTHONPATH` set to this worktree's `scripts`, and the child PRINTS `nixrisk.gate.__file__`, asserted under this worktree BEFORE any count is read | n/a — this is the anti-defeat proof | the child's own `__file__` | n/a |

---

## WHAT I COULD NOT MEASURE, AND WHY

1. **"The timeout racing a LATE feedback", "the timeout firing DURING a reset", "two timeouts firing at once" — CANNOT-MEASURE.** There is no timeout (FF1). The subject of those three scenarios does not exist in the tree, so driving them would mean driving a fake I had written, and a race against my own stub measures my stub. What I drove instead is the closest real thing: a late re-acquire against the only reset that exists (`force_deregister`) — **REFUSED** with `'s3' is not registered in the Risk Engine` when the strategy is gone, and **ACCEPTED** once it re-registers (D3.399).
2. **A clock jump against the GO-timeout — CANNOT-MEASURE**, same reason. The clock jump WAS driven against the heartbeat, through its injectable clock, and resisted (RF1).
3. **`write(2)` on an already-open fd is invisible to a PEP-578 audit hook.** No audit event exists for it. Covered instead by `strace -c` and by the WAL's own counters; stated so nobody reads RF2's zero as covering it.
4. **The blackout and tradability ports were left as stubs in the real-ports arm.** Constructing a real `BlackoutEvaluator` needs a window cache, a margin-baseline cache and a picture port; that scaffolding is three more objects and the arm already moved the p99 by 2.2x without them. So the real per-evaluation cost of the phase-A caches is a LOWER BOUND, not a measurement of the whole pathway. `check_blackout_windows` owns that port and is outside my assignment.
5. **Whether the Limiter's daemon would do any of this at all.** There is no Limiter loop in the tree (FF5), so every hot-path figure here is measured on the library as a caller would drive it, not on a running process. Stated rather than implied: `nix_check_contract.md` §17 — a property proven while its subject is unavailable is not proven — and the subject here is the *shipped pass*, which IS available; the *process* is not.
6. **`check_uncalled_entry_points`' full 56-finding set.** Its own output truncates at 25 rows (`31 further finding(s) NOT SHOWN`), and D3.253 is the recorded case of reading a truncated list as the whole one. I read the rows that name `recovery.py` and did not attempt the rest.

---

## FILES I CHANGED

| path | why | finding |
|---|---|---|
| `scripts/nixrisk/recovery.py` | a second take of the one-in-flight lock is REFUSED, naming both client_order_ids and §4:210. Minimal, local, reversible: one guard clause, no new state, no signature change. | FF2 |
| `scripts/plane1_hotpath_drill.py` | `concurrent()` pins `sys.setswitchinterval` for the arm's duration (restored in `finally`) and reports it, so the overlap floor is reachable independently of the box's GIL handoff cadence. Biases the measurement AGAINST a pass. | D3.346 / D3.403 |
| `checks/check_plane1_hot_path.py` | `_SITE` re-pointed at the measured hot path, with the commit path named beside it. | FF6 |
| `scripts/tests/test_arc038_f_inflight_lock.py` | NEW. The missing can-fail control for `InFlightLockRule`'s DENY, the FF2 guard in both halves, the GO-timeout census ratchet, and the real-`SIGKILL` wedge with its falsifier. | FF1, FF2, FF3 |
| `scripts/tests/test_arc038_f_hot_path_ledger.py` | NEW. The approve-path arm the drill lacks: append count, audit-event census in a child with an explicit `env=`, and a timing arm proven able to see blocking. | FF4 |
| `downloads/arc038_findings_F.md`, `downloads/arc038_debt_F.md` | the deliverables. | — |

No `checks/check_*.py` was ADDED: `check_limiter_gate` already owns the pass and `check_plane1_hot_path` already owns §11 item 6, so a second gate re-asserting either is the duplicate instrument doctrine C.9 forbids. Both gaps are closed by pytest suites and by pointing an existing gate's `site` at the truth.

## SUITE NUMBERS, on the committed tree

| run | result |
|---|---|
| `.venv/bin/python -m pytest scripts/tests -q` (FULL — required, a frozen file moved) | **3273 passed, 3 skipped, 2 xfailed, 0 failed** in 2191 s |
| the contract's Limiter `-k` subset (`risk or limiter or gate or reservation or flatten or picture or plane1 or halt or blackout or survival or fill or execution`) | **1200 passed, 1 skipped, 2077 deselected** in 309 s |
| my two new suites alone | **15 passed** in 1.7 s |
| the commit's own runtime gate (`pytest --testmon`, the pre-commit Stage 3) | **Passed** — `SELECTED=1258`, 0 failures |
| the seven audited gates, after every plant was restored | `check_plane1_hot_path` pass · `check_orphan_recovery` pass · `check_limiter_gate` pass · `check_supervision` pass · `check_staleness` pass · `check_mirror_liveness` pass · `check_allocator_lifecycle` pass |
| tree hygiene | `check_name_coherence` pass · `check_derived_claims` pass (13/13) · `check_canonical_tree` pass · `check_artifact_gate_coverage` **guarded** (unchanged — my new files are under `scripts/tests/` and `downloads/`, both excluded prefixes) |

Interpreter: `/home/bbt/nix-wt-arc-038-f/.venv/bin/python`, CPython 3.14.4, throughout.

**Frozen-set census, `git hash-object` against `scratchpad/arc038/frozen_limiter_shas.txt`:
exactly ONE of the 30 files moved — `scripts/nixrisk/recovery.py`, for FF2.** The other 29
are byte-identical, and every plant used during the gate audit was restored and proven so
by `cmp` and by `sha256sum` before and after.

## COMMITS

| sha | subject |
|---|---|
| `c71bf2f` | ARC 038 (F) I5: §14's one-in-flight lock — a real SIGKILL wedges it forever, and its DENY branch had no control |
