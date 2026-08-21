## ARC 055 — I1 ARC C1: the stop protective-exit path (poll + maintain + breach → flatten)

**TIER: INTERIOR. Limiter STAYS RED. Count STAYS 11/12** (I1 discharges at ARC D's convergence gate,
not here). Derived tip `66f9f8b` (the brief said ≈`58c9582`; the real tip was ARC 054's re-measure
commit). Measured baseline **`93 | 5 | 2 | 0`**; predicted delta `+1 passed`; **measured
`94 | 5 | 2 | 0`. PREDICTION MET.**

**The baseline was NOT the brief's `94|4|2|0`.** `check_arc_status_contract` moved cannot-measure →
**FAIL**, auditing `arc_054.log`: *no watchdog self-verify line (HEARTBEAT SELF-VERIFY: ok) before
marker*. ARC 054 genuinely never emitted `selfcheck` into its own log. That log is banked evidence
(directive 6) and was not rewritten; ARC 055 wrote the line into its own log so ARC 056 measures PASS.

### S1 — D3.451 reproduced on the live loop

A real `limiterd`, a real reservation, a real fill, a real armed stop:

| measurement | result |
|---|---|
| non-vacuity: stop genuinely armed | `level=4998.0` = `5000.0 − 8 × 0.25`, `anchor=5000.0` |
| **NO MAINTAIN** | 101 real ticks (8→109); `level` **invariant** |
| **NO PRICE INGRESS** | dirs `[completions, inbox, onset, outbox, status]`; verbs `[register, go, status, resolve, reserve]`; no price block |
| **NO BREACH** | `RecordedCancels` verbs `['cancel_order','issued']` → `hasattr(flatten)==False`; `SYNTHETIC_STOP`, `.maintain(`, `.breached(` all absent from `limiterd.py` |
| non-vacuity: the LIBRARY works on the same numbers | armed 4998.0 → trails to **5002.0**; `breached(level−1 tick)` returns it |

The mechanism worked and **nothing with a pid drove it**.

### S2 — what was wired

* **NEW `scripts/nixrisk/stopwatch.py`** — `PriceRing` (§5:322's ring, `head()` = one dict read) and
  `StopWatch` (poll → `maintain` → `breached` → mark flatten-in-flight → enqueue). Holds **no broker,
  no Plane-1 sink and no clock**, structurally. `BreachFiring` carries **no timestamp** — a clock read
  on the hot path is what the I9 arm refuses.
* **`scripts/limiterd.py`** — `VERB_PRICE`; `RecordedVenue` (the broker **gains `flatten`**, which 054
  deliberately withheld); `StopWatchDriver` (`before()` on the hot loop, `send()` on the sender
  thread); the tick order is now `poll prices → poll onset → book firings → read commands → read
  completions → poll overdue`; **ONE** `ProtectiveFlatten` shared by the onset sweep and the stop
  exit, so §4's arbiter reads one `_closed` book.
* **`scripts/nixrisk/loop.py`** — `SenderThread` gains an **additive** `send` callback (`set_send`,
  refused once running) and `LimiterLoop.attach(sender_send=...)`. `None` keeps the ARC 040 stub
  behaviour exactly. This file is **NOT on the brief's freeze list** and is disclosed as the one
  deviation: §5:323's thread was a recorder, and C1 cannot send off the hot path without it.

**Spec-citation correction:** the brief cites **§7.4** for the trailing stop. **§7.4 does not exist**
in frozen v1.3 (§7 → §7.5). The authority is **§4:187-196**, which `stops.py` itself cites, and that
is what this arc's code and gates cite.

### S3 — proven on the running daemon, watched past the tick

* **BREACH FIRES** — price crosses 4998.0 → `fires=1`, `sends=1`, broker `flattened=['ES']`,
  trigger `synthetic_stop`, `executed=[True]`, `in_flight=['csm-fixed']`, no refusals, no send errors.
* **SEND IS OFF THE HOT PATH** — send ran on native tid = the **sender thread's**, ≠ the loop's.
* **FIRE-ONCE** — 116 further polls with price still past the level: still `sends=1`,
  `flattened=['ES']`, `suppressed=76`.
* **TRAIL MONOTONIC** — armed 4998.0 → tightens to 5002.0 (hwm 5003.0 − 4×0.25); retrace to 5002.75
  leaves the level at 5002.0 and the high-water at 5003.0; a **descending walk** of 3 steps never
  lowers it; crossing 5001.75 fires ONE firing naming **5002.0**, not the armed level.

### The two discharged invariants, RE-PROVEN over the new code

* **I9 (hot-path purity)** — `check_hot_path_purity` gains **ARM 3c**: 2 × 2000 real polls, both
  branches driven, roots `['__main__','dataclasses','nixrisk.seam','nixrisk.stops','nixrisk.stopwatch']`,
  `write(2)=0`, 0 PEP-578 events. `stopwatch.StopWatch.poll` is now **DERIVED by shape** into ARM 6's
  entry-point set, so a later second poll fails ARM 6 until it is driven.
* **I3 (exit-path wire-freedom)** — `check_stop_maintenance` ARM 4 traces the **daemon's own send
  closure** under a transport ban-set and finds nothing. That subject is invisible to `check_flatten`
  ARM 6, which never imports `limiterd`.

### S4 — the gate, and the four plants it is BOUND from

**NEW `checks/check_stop_maintenance.py`** (+1 passed). Census: `check_synthetic_stop_only` owns the
§12.1 prohibition; `check_flatten` owns the executor as a library; `check_limiter_daemon_dispatch`
owns the completion routes; `check_hot_path_purity` owns purity. **Monotonicity-under-drive and
fire-once were owned by nothing.**

| plant | verdict |
|---|---|
| **A** the poll never tests for breach | **exit 1** — *THE DAEMON DID NOT FIRE A PROTECTIVE FLATTEN FOR AN UNPROTECTED POSITION*, naming `'csm-fixed'` and level 4998.0 |
| **B** the ratchet reads the CURRENT price | **exit 1** — §4:190-196, *THE HIGH-WATER RETREATED from 5003.0 to 5002.75* |
| **B′** the trail widened AWAY from price | **exit 1** — §4:190-196, *the trail did not TIGHTEN* |
| **C** the fire-once mark ignored | **exit 1** — *DOUBLE-FLATTEN … sends=76* |
| **D** I/O on the poll path | **exit 1** via `check_hot_path_purity` — *FORBIDDEN SYSCALL … open('/dev/null','w')* |
| all removed | **exit 0 / exit 0** |

**A first PLANT B did NOT fire and that was a finding about the gate, not the tree**: widening
`_tighter` is invisible to a single retrace comparison, because the high-water is monotone and so is
the level it implies. ARM 3 was strengthened to a **descending-walk sequence property** before the
plant was accepted.

### THE HEADLINE FINDING — D3.474, and it was not looked for

Driving the monotonic-trail proof through the daemon revealed that **this build CANNOT ARM A TRAILING
STOP AT ALL**. Measured on a live `limiterd`: `reserve(stop_mode=trailing)` → `accepted: true`, 1000.0
committed; the `on_fill` that follows → `last_disposition: refused`, `InvalidStopIntent: a trailing
stop needs a trail distance, which the frozen ProposedOrder does not carry`. `fills.py` calls
`arm(report.price, order)` with no `trail_ticks`. `stops.py` documented the seam gap; **nobody had
measured what it does to a running process, which is that the position never opens and the
reservation stays taken.** NOT fixed here — the repair edits the frozen `ProposedOrder` and the fill
path, both of which this arc freezes byte-identical.

### FREEZE — asserted with `git hash-object` against `66f9f8b`

**IDENTICAL:** `flatten.py`, `outcomes.py`, `reservations.py`, `fills.py`, `fill_seam.py`, `stops.py`,
`picture.py`, `positions.py`, `completions.py`, `freshness.py`, `seam.py`, `execution.py`, `join.py`,
`wal.py`, `gate.py`. **Changed:** `limiterd.py`, `nixrisk/loop.py` (disclosed above),
`check_hot_path_purity.py`, `registry.json`, `CHECK-DEBT.md`, `test_check_order_path_bans.py`.
**New:** `nixrisk/stopwatch.py`, `check_stop_maintenance.py`, `test_stopwatch.py`,
`test_check_stop_maintenance.py`.
**`uncalled_entry_points_baseline.json` did NOT move** — every new public entry point has a call site.
`check_order_path_bans` scope grew 38 → **39** modules (`stopwatch.py` joined) and still reports
**0 banned modules, 0 banned calls**; the tripwire's banked number was bumped **in the arc that caused
it**, not two arcs later.

### CHECK-DEBT

**D3.451 DISCHARGED.** **D3.473 OPENED** (the ring is fed by a `price` command — no capture feed, so
no green may be read as *the Limiter is receiving real prices*). **D3.474 OPENED** (the trailing-fill
refusal above). ARC-TOTAL re-derived whole by `check_derived_claims`: **414** (+1 net; two opened, one
discharged), read off the instrument, not typed.

### RESIDUAL — explicitly NOT claimed

* **I1 is NOT discharged.** C2 (the three uncertainty producers, D3.453/372/469) and D (flatten
  completions + the convergence gate) remain. **Count stays 11/12.**
* **The completion path is ARC D.** C1 fires and sends; the closing fill, the §12.10 `closed` row, the
  position close and the release are D. A flatten sent here is IN FLIGHT until D reconciles it.
* **Nothing reaches a venue.** `RecordedVenue.flatten` records; there is no vendor integration.
* **No green here means the daemon has real prices** (D3.473) or **that it can hold a trailing stop**
  (D3.474).

### POST-WRITE-BACK RE-MEASURE — ARC 055

Measured on the MERGED tree at `4601a06` (the arc's own write-back commit), after `SESSION.md` and
`RESULTS.md` landed and after every one of this arc's untracked files became tracked:

```
94 passed | 5 failed | 2 cannot measure | 0 skipped     exit 1
```

**PREDICTION MET.** Baseline at the derived tip `66f9f8b` was `93 | 5 | 2 | 0`; the predicted delta
was `+1 passed` from a genuinely unowned `check_stop_maintenance` and no other movement; the merged
tree measures `94 | 5 | 2 | 0`.

The five reds are the standing set, unchanged by this arc:

| check | why |
|---|---|
| `check_arc_status_contract` | audits `arc_054.log`, which carries no `HEARTBEAT SELF-VERIFY: ok` before its marker. Banked evidence, not rewritten (directive 6). ARC 055's own log carries the line, so ARC 056 measures PASS. |
| `check_ibgateway_service` | `127.0.0.1:4002` — no gateway on this box. Environmental, standing. |
| `check_monitor_tui` | `scripts/monitor.py` — the operator-deprecated MON-1 trio (D3.113). Standing. |
| `check_uncalled_entry_points` | the ratchet. **It did NOT move in this arc** — every new public entry point on `stopwatch.py`, `StopWatchDriver`, `RecordedVenue` and `SenderThread` has a call site. |
| `check_untracked_attribution` | `downloads/Pinokio-8.0.40-arm64.dmg`, the operator's file. This arc's own new artifacts are gone from the list because they are committed. |

`check_stop_maintenance` is PASS at the merged tree on all four arms, and `check_hot_path_purity` is
PASS with ARM 3c over the new poll.
