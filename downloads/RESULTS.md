## ARC 040 — ULTRAREVIEW: Limiter, slice 2 of many — the GO-timeout (I5)

**Tier: INTERIOR.** The Limiter badge **STAYS RED**. This is not the greening slice.
**Canonical path: `/home/bbt/nix`** (absolute). **Predecessor: ARC 039R, HEAD `39b8a45`.**
Interpreter for every measurement below: `/home/bbt/nix/.venv/bin/python` → `/usr/bin/python3.14`
(Python 3.14.4).

### What this slice discharged

**I5 — §4:210-212's GO-timeout, the deadlock breaker on the one-in-flight lock.** ARC 038 found it
had **no implementation anywhere in shipped code**: `limiter.go_timeout_s` was a knob whose only
reader was the boot cross-validator, which validates the value and acts on nothing. §14:971 locks
*"One in-flight action per strategy — and it can never wedge (GO-timeout)"*; the invariant was
prose.

### S1 — the defect REPRODUCED FIRST, on the live ARC-039 loop, before a line changed

A real `limiterd` process. A real GO admitted through the real `StrategyRegistry`. The **GO HOLDER
killed by `SIGKILL`, by PID taken from its own self-report** (never `pkill -f`).

```
AT ADMISSION  t+0.0s   in flight [['s-040', 'c-040']]
SIGKILL sent to the GO HOLDER pid=3941502
  t+ 23.35s  in_flight=[['s-040', 'c-040']]   <-- LAST SAMPLE
VERDICT: LOCK STILL HELD at t+23.35s = +13.35s PAST the 10.0s knob. NOT RELEASED.
STOP RECORD: flat=False in_flight=[['s-040','c-040']] ticks=501
             go_timeouts=<field absent — no timeout machinery in this build>
```

The loop **ticked 501 times and beat 25 times** while holding it. It was alive, healthy, and simply
never measured elapsed time. 038 measured 11.0 s past; this run measured 13.35 s past, and the only
difference is that it watched longer.

### S2 — the implementation

`scripts/nixrisk/loop.py`:
* `go_timeout_from_config()` — the read ARC 038 measured as missing, through `load_risk_configs` so
  the config's own `liveness.go_timeout_outlasts_pending_ack` cross-knob rule governs the reader.
* `take_in_flight` **stamps the loop's own monotonic clock** at admission.
* `_break_go_deadlocks()` — the whole mechanism is one comparison, `elapsed >= self.go_timeout_s`,
  run once per tick, and that comparison is what did not exist anywhere in the tree.
* **Placed AFTER the drain and BEFORE the beat**, and both halves are the invariant: after the drain
  so terminal feedback arriving in the same tick wins (no false release); before the beat so
  §12.1's `positions_open_hint` never advertises a lock this same tick already broke.
* **NO retry, NO auto-resend** (§4:240-241). `GoTimeout.resent` is a recorded `False`, a field and
  not a comment.

`scripts/nixrisk/recovery.py`: `StrategyRegistry.release_in_flight` — the **flat-and-FREE** release
§4:211-212 needs and `force_deregister` could not be. `force_deregister` is §4:266-268 and takes
slot and registration down with the lock: right for a strategy that has DIED, catastrophic for one
that merely lost a message. Purely additive; no existing method changed.

`scripts/limiterd.py`: `--go-timeout`, the `resolve` verb (§4:203-206 terminal feedback), and
`go_timeouts` rows in the stop record — the evidence the gate reads from outside the process.

### S3 — proven in BOTH directions, on real processes

**(a) It FIRES on a real kill.** Same scenario as S1, knob driven at 4.0 s:

```
  t+  3.54s  in_flight=[['s-040','c-040']]  go armed [[...,3.6]], go timeouts 0
  t+  4.10s  in_flight=[]                   go armed [],          go timeouts 1
VERDICT: lock RELEASED at t+4.10s (+0.10s vs the 4.0s knob)
STOP RECORD: flat=True registrations=['s-040']
  elapsed_s 4.049889  timeout_s 4.0  released True  resent False
```

Released **one tick** past T, not 11 s past it. `registrations=['s-040']` with `in_flight=[]` is
flat-and-**free**: the strategy survived, which is what distinguishes §4:211-212 from a
deregistration.

**(b) It does NOT fire early.** Terminal feedback at t+1.10 s against a 3.0 s knob released the lock
normally, and the run was then **watched to t+4.96 s = 1.65×T** — past the point the breaker would
have fired — with `go timeouts 0` at every sample and `go_timeouts=[]` in the stop record. **Zero
false releases.** Stopping at the healthy release would have proven only that the breaker had not
fired *yet*, which is the §0a trap this direction exists to close.

### S4 — `checks/check_go_timeout.py`, with a demonstrated FAIL in BOTH arms

Two arms, because neither alone is the check: an **AST string-literal reader census** that NAMES the
unread site, and a **live drive** of a real `limiterd` (register → admit a GO → abandon it → watch
the lock through the process's own `status` verb → then a second GO fed normal feedback and held
past T).

* **PLANT A** — the knob key renamed away, 038's exact *knob-present-but-unread* state:
  `fail_needs_operator`, **exit 1**, naming `scripts/nixrisk/loop.py`.
* **PLANT B** — the knob read but the comparison neutered: `fail_needs_operator`, **exit 1**, naming
  `scripts/nixrisk/loop.py` and reporting the measured wedge (`8.0s later, against T=2.0s`,
  `go armed [[...,8.04]]`, `go timeouts 0`).
* **Plants removed**: `pass`, **exit 0**.
* **NON-VACUITY is asserted, not assumed**: the drive REQUIRES the status verb to report the lock
  **HELD** before any later empty reading may count as a release. A run that watched an empty
  registry returns CANNOT_MEASURE, never PASS (§17 / rule 10).

### TWO FINDINGS AGAINST THE ARC'S OWN INSTRUMENT — both caught by the plants, both recorded

* **D3.426** — the static arm was **VACUOUS as first written** and PLANT A **passed it**. It matched
  the substring `go_timeout_s` anywhere in a module, so a constructor parameter name and an argparse
  help string counted as "reading the knob". It was measuring the spelling of an identifier. Now an
  AST census for a string **literal** equal to the key.
* **D3.427** — the gate first reported a positively-observed **WEDGE as `cannot_measure` (exit 2)**
  rather than FAIL. With the lock wedged, the second arm's GO was refused *by the wedged lock
  itself*, and that consequential refusal was raised as the gate's `Cannot`, overwriting a finding it
  had already made. Fail-closed held; the REASON did not, which is the half check contract v2 rule 11
  makes the assertion. Fixed; the plant now returns exit 1.

A third finding was caught the same way and fixed in flight: the arc's own S3a **driver printed a
VERDICT that contradicted the samples printed above it** — it parsed `in flight` by splitting on a
field that the post-fix status string no longer put next to it, so a released lock read as held.
The fix is in the harness and the same bounded-parse discipline is in the gate's `_held`.

### FREEZE — held

`git diff --stat 39b8a45 -- risks/` is **empty**. The knob was already on disk; this slice made it
**read**. No other invariant's logic moved. Production changes: `loop.py` (the breaker),
`limiterd.py` (flag/verb/records), `recovery.py` (one additive verb). Two test files changed because
the change necessarily invalidated them — see below.

### The ARC 038 defect-witness ratchets fired, and were READ rather than absorbed

`scripts/tests/test_arc038_f_inflight_lock.py` pinned three censuses so the fix could not land
unnoticed. All three moved, exactly as designed:
* the release-site census gained `StrategyRegistry.release_in_flight`;
* `test_NO_shipped_module_MEASURES_the_go_timeout_knob` was **INVERTED** into
  `test_the_LOOP_MEASURES_the_go_timeout_knob` — the inversion IS the discharge;
* the mention census now records that two of its entries are no longer names.

### CLOSE-OUT (INTERIOR tier — a STATED decision, not a silent skip)

**The full ~3400-test pytest run and the full binding census are DEFERRED to the Limiter's greening
slice**, per the tiered rule. What was run instead:

* **(b) The DERIVED reverse-dependency closure**, derived from the tree by grepping importers of the
  changed files: **281 passed, 0 failed**. **Non-vacuity proven before trusting green** — the
  closure contains `test_limiter_loop.py` and `test_arc038_f_inflight_lock.py`, the direct dependents
  of the changed files, and both were **RED before the fix and GREEN after**. **COST-AWARE
  EXCLUSIONS, named**: `test_check_artifact_gate_coverage.py` and `test_check_uncalled_entry_points.py`
  were detected as shelling out to `verify.py`/the census and excluded (deferred to the greening
  slice) — the detection was a scan, not a guess.
* **(c)** `check_go_timeout` is **BOUND** from its **observed real FAIL** — two independent planted
  defects, each returning exit 1 with the site named, not a constructed exit code.
* **(d)** CHECK-DEBT reconciled: **D3.398 DISCHARGED** with its residual named rather than absorbed;
  **D3.425/426/427 opened**.

### Residual explicitly NOT claimed as done

**D3.425 — the `go_timeout` Plane-1 row is still unwritten.** §9:553 lists GO-timeout among the
event types the sole writer books, and `projection.py` already carries the event name. The breaker
now fires and releases, and every firing is in the runtime record and readable live — but that is a
RUNTIME record, not §9's evidence plane, and `limiterd` has no Plane-1 writer wired at all. Blocked
behind I8, which is slice 3.

### BADGE VERDICT — Limiter STAYS RED

**Discharged: I5** (the GO-timeout), one invariant, reproduced → fixed → re-audited in both
directions → gated with a demonstrated FAIL. **Eleven invariants remain open** from 038's pass 1.
**Slice 3 targets I7 (commit-before-validate torn state) + I8 (sole-writer enforcement)** — the next
blockers, and I8 is what unblocks D3.425.
