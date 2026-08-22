# ARC 058 RESULTS — I1 ARC D (the finale): flatten completions + the convergence gate

**TIER = GREENING.** **I1 IS DISCHARGED. The clean set is 12/12.**
Discharges **D3.481 · D3.477**. Opens **D3.482 · D3.483 · D3.484**. Ledger **417**, re-derived whole.

**Predecessor DERIVED, not assumed:** the brief said `≈ ARC 057's write-back`; `git rev-parse HEAD` =
**`9bc04d9`**. Everything below is frozen and diffed against **9bc04d9**.

**Baseline MEASURED FIRST, before a line was written: `96 | 4 | 2 | 0`** — the predicted tuple, met.
`check_arc_status_contract` **PASSES** auditing `arc_057.log`, as predicted (057 tee'd both lines).

---

## THE HEADLINE

**A flatten sent is IN FLIGHT until its closing fill comes back, and until this arc nothing reconciled
one.** C1 (055) fires on a breached synthetic stop; C2 (057) fires on each of §14's four
unprotectable conditions. Both *fire and send*. Neither closed the book.

Reproduced on a live `limiterd` at S1 before a line was written — a reserve, an entry fill, a price
through the stop, then the flatten's own exec report handed back through `completions/`:

| owed by §12.10 / §4 / §3 | S1, BEFORE | S3, AFTER |
|---|---|---|
| the §12.10 `closed` row | **absent** — WAL held `reservation_taken`, `reservation_released`, `protective_exit` | **written**, carrying `close_price=4997.0`, `exec_id`, `closing_order_id`, `symbol` |
| the §3 position | **`state: "open"`** | **`state: "closed"`** |
| the open margin | **`sum_open_margin` stuck at 1000.0** | **released to `0`** — the writer's own published Σ |
| §4's synthetic stop | still armed at 4998.0 in `StopBook` | **`stops: []`** |
| C1's fire-once mark (D3.481) | **`in_flight: ["entry-0001"]`** | **`in_flight: []`** |
| §4:203-206's `closed` notify | **never sent** | `TRD-….closed.json`: `hard_reset=true`, **`fsm="flat"`**, reason carried from §4's arbiter |

**And one finding nobody budgeted for.** The closing exec report was dispatched down the ENTRY path
and refused as an `UnapprovedFill` — *"this Limiter holds no approved order under that id"* — then
landed in §14's `unclassified` list, which `check_uncertainty_flatten` ARM 6 reads as CANNOT_MEASURE.
**A flatten's own confirmation was poisoning the gate that owns flattens.** After the wiring,
`unclassified` is `[]`.

---

## PART 1 — `scripts/nixrisk/closing.py`, THE CLOSING-FILL HANDLER (named, +1 file)

**§2A:74-84's `on_fill` carries no role**, and nothing on the wire ever will — the same gap `OrderRole`
was minted for on the cancel side. So a close is **DERIVED from three facts this process already
holds**, and a fill failing any of them is NOT adopted:

1. it is a fill (`on_cancel`/`on_reject` are §3's release paths, `outcomes.py`'s, unchanged);
2. its order is **not an approved ENTRY** in §3/§4's own join;
3. **this process SENT a protective flatten for that symbol and it is still in flight** — the daemon's
   own `FlattenInFlightBook`, armed at the send site on the far side of the `fire`.

Fact 3 is the load-bearing one and it is deliberately the daemon's record rather than a read of
`ProtectiveFlatten`'s private `_closed`/`_intents`: §5:323 puts the send on the sender thread and
§5:322 drains the completion on the loop thread, so the two halves are genuinely two events and the
book is what joins them. **A fill satisfying (1) and (2) but not (3) is left to the ordinary dispatch**,
which refuses it by name — adopting it would be closing a position off a venue message nothing in this
process asked for.

**THE ORDER IS THE SAFETY PROPERTY.** §3 commit → stops forgotten → §12.10 row → §4's `closed` notify.
The commit is FIRST and it is the authority: if `FinancialPictureBook.commit` refuses, the close is
REFUSED WHOLE, the flatten STAYS ARMED, and nothing downstream runs — capital stays committed and the
stop stays armed, which is the conservative error. The opposite order would tell a strategy it was flat
while §3 still carried the position. Everything after the commit is ATTEMPTED AND RECORDED, never
raised (`flatten._book`'s FC1 ruling, one module over).

**THE `closed` ROW BOOKS NO REALIZED FIGURE, AND THAT IS MEASURED, NOT LAZY.** `flatten.py` records it
at the site: `request_close` books a `protective_exit` row with `realizing=True`, `nixscore.ema.
daily_advances` SUMS every realizing row in a pair's day, and the guard that stops a double
(`_realized_booked`) lives inside `ProtectiveFlatten` and cannot see a row booked from here. So the
terminal row is NON-REALIZING and carries a `realized_status` naming why. D3.220's wire is undamaged.

**IDEMPOTENT ON TWO KEYS, because there are two ways to double-close.** The exec report, through the
SAME `ExecReportDedup` the entry dispatcher claims against — never a second book, or a re-delivery
would be a duplicate to one and news to the other. And the trade, whose §3 row is no longer LIVE.
Measured: the same exec report re-delivered took `completions.duplicates` 0→1, left `closed` at 1,
`picture.commits` at 3 and `sum_open_margin` at 0, with one `closed` push.

**`limiterd.py` gains `ClosedFeedback`** — §4:203-206's `closed` outcome, the mirror of ARC 047's
`OpenFeedback`. `UnwiredExitSinks` is KEPT and still RAISES: its only caller is
`ProtectiveFlatten._fan_out`, reached only from `reconcile_and_publish`, which awaits the two ASYNC §2A
query verbs this daemon's stub venue does not have. Two sinks because there are two paths and only one
of them exists.

---

## PART 2 — `check_i1_convergence`, AND ITS PASS IS I1's DISCHARGE (+1 file)

**The census this gate was opened against.** Every path in this tree has a gate that proves its
CORRECTNESS, each scrupulously scoped to ONE property: `check_limiter_daemon_dispatch` (fill / cancel /
reject / pending-timeout dispatch), `check_stop_maintenance` (§4:187-196's trail and the breach),
`check_uncertainty_flatten` (§14's four producers and THAT family's completeness), `check_flatten` (the
executor as a LIBRARY), `check_go_timeout`, `check_limiter_loop_alive`, `check_two_phase_entry`,
`check_limiter_gate`. **Not one of them asks whether the SET is complete** — each is blind, by design,
to a path that exists in a library and is reachable from no running process. A tree of green
single-path gates and a daemon that invokes half of them look identical from every one of those gates.
Doctrine C.9 respected rather than argued around.

**THE REQUIRED SET IS DERIVED FROM FIVE VOCABULARIES IN THE SUBJECT'S OWN SOURCE**, by AST, and this
file holds no copy of any of them:

| family | vocabulary | ARC 058 members |
|---|---|---|
| `completion:<event>` | `completions.py`'s `SPEC_EVENTS` (§2A:74-84) | 8 |
| `uncertainty:<condition>` | `limiterd.py`'s `UncertaintyCondition` (§14) | 4 |
| `ingress:<name>` | classes declaring `before(self, inner)` **and** constructed in `main()` (§5:322's tick-wrapper contract) | 5 |
| `handler:<param>` | `CompletionHandler.__init__`'s collaborators | 4 |
| `sender:<name>` | `ProtectiveSenders.__init__` (§5:323's protective fan-out) | 2 |

**23 paths.** Add a ninth §2A event, a fifth §14 condition, a sixth per-tick composer, a fifth
completion collaborator or a third protective sender and `required` grows on the next run with no edit
to the gate. **A required path it cannot classify is CANNOT_MEASURE NAMING IT, never PASS.**

* **ARM 1** — the set, derived. Nothing is imported from the subject; the derivation is AST-only and
  the drive is a subprocess, which is D3.224's *one tree per interpreter* taken as a rule rather than
  as a caveat (the measurement ARC 057's re-measure paid for).
* **ARM 2** — every path **DAEMON-INVOKED**, proven structurally: its owner is CONSTRUCTED in `main()`
  and REACHES §5:322's loop through `attach(ingress=)`, `attach(handler=)` or `attach(sender_send=)`.
  **A path present in a library and absent from that composition is the library-not-daemon state I1
  forbids.**
* **ARM 3** — every path **DRIVEN**, through a real `limiterd`'s own ingress: files in `inbox/`,
  `completions/`, `status/`, `onset/` — never a direct handler call, because ARC 038's deepest finding
  was that every Limiter invariant in this tree had been proven about a library a test constructed.
* **ARM 4** — completeness: `driven == required == invoked`, both differences named.
* **ARM 5** — non-vacuity: quiet start, `last_source` naming the ingress directory, and the protective
  send proven to have run on §5:323's thread and not the loop's.

**MEASURED: `invoked 23/23 · driven 23/23 · unservable 0`, exit 0.** Six `limiterd` processes — one
main daemon and one per §14 producer, separate because the conditions are not independent inside one
(a breach that closes the ES position removes the OPEN row `stale_open` is about, and a shared daemon
would make the drive order decide the verdict).

### BOUND FROM SIX SOURCE PLANTS, EVERY SUBJECT RESTORED BYTE-IDENTICALLY

`git hash-object` compared before and after each: `limiterd.py` `aafb21c0e23a1c26`,
`completions.py` `ea1c9db2495a0871`, `closing.py` `14ba00869a899fe6`.

| plant | what it broke | exit | the sentence |
|---|---|---|---|
| **A1** | `closing` deleted from `main()`'s one `CompletionHandler(...)` call — library intact | **1** | LIBRARY-NOT-DAEMON *…`main()` hands it NOTHING* + NOT DRIVEN + the ARM 4 gap |
| **A2** | `onset.before(...)` deleted from the tick composition | **1** | *LIBRARY-NOT-DAEMON: per-tick path 'onset' is not composed into `loop.attach(ingress=...)`* |
| **A3** | `STALE_OPEN` deleted from `_UNCERTAINTY_TRIGGER` | **1** | *the condition is detectable and not actionable* |
| **B** | a fifth `UncertaintyCondition` with no producer | **1** | LIBRARY-NOT-DAEMON naming `orphan_position` |
| **B2** | the same member **plus** a trigger entry — a required path this instrument cannot reach | **2** | *UNCLASSIFIABLE REQUIRED PATH … it is not a pass* |
| **C** | the closing path wired and reachable, made unexercisable | **1** | NOT DRIVEN naming it — and, correctly, **no** library-not-daemon finding |
| — | plants removed | **0** | `invoked 23/23 · driven 23/23` |

Plus the **rule-4 plant-both** and 14 further controls in `scripts/tests/test_check_i1_convergence.py`
(15 passed), including a subject whose vocabularies are nothing like the real tree's — the gate must
answer *that* subject's set, never a constant.

### TWO DEFECTS THE PLANTS FOUND IN THE GATE ITSELF

Both fixed at their sites, both regression-guarded in the test module.

1. **PLANT A1 FIRST EXITED 2, NOT 1.** The drive's `Missed` propagated to `run`'s catch-all and came
   back *cannot_measure: gate raised Missed* — taking the ARM 2 finding that named the path with it.
   *A defect downgraded to CANNOT_MEASURE is a defect that never names itself* (`check_uncertainty_
   flatten`'s ARC 057 / S4b ruling, met again here). A missed drive is now a NOT-DRIVEN **finding**
   carrying the daemon's last published status.
2. **PLANT A2 FIRST SHRANK THE REQUIRED SET, 23 → 22.** The ingress family was derived from
   `loop.attach(ingress=...)` — the very composition it is compared against — so un-wiring a path
   stopped it being required, and the library-not-daemon state made itself invisible. The vocabulary
   is now the SHAPE (`def before(self, inner)` **and** constructed in `main()`), so un-wiring leaves
   the path REQUIRED and NOT INVOKED, which is exactly what it is.

---

## PART 3 — THE GREENING CLOSE-OUT

### (A) FULL PYTEST — the whole suite, not a derived closure

**`3632 passed | 9 failed | 3 skipped | 2 xfailed` in 2997 s (49:57)**, `--basetemp=/var/tmp/arc058_pt`
OUTSIDE the tree.

* **ONE failure was this arc's, and it is FIXED.** `test_check_order_path_bans` BANKS the order-path
  module count and it moved **39 → 40**, because `nixrisk/closing.py` is a new module under an anchor
  directory. Re-banked from the gate's OWN printed evidence, never from arithmetic — and re-read rather
  than assumed: over the widened scope the gate reports the SAME 3 advisory sites and **no** new banned
  module, banned call or retry shape. `closing.py` declares no order-port verb and sends nothing; the
  venue was already reached by the flatten it reconciles. Re-verified 15/15, gate PASSES.
* **EIGHT are INHERITED, and that is PROVEN rather than argued** — the whole of `test_realized_pnl.py`,
  `test_flatten.py::test_the_R4_partition_covers_the_WHOLE_enum` and
  `test_coldstart_reconcile.py::test_flatten_to_flat_REFUSES_a_shut_market`. They pass STANDALONE
  (`88 passed`) and reproduce at HEAD `9bc04d9` in a CLEAN `git worktree` with a byte-identical
  signature: `KeyError: <EventKind.CLOSED: 'closed'>` at `test_realized_pnl.py:586`, on a dict keyed by
  `EventKind`. **That is TWO MODULE OBJECTS FOR ONE FILE IN ONE INTERPRETER** — D3.224's *one tree per
  interpreter*, the class ARC 057's own re-measure paid for. **D3.484 opened.**
* **D3.481 CLEARS** — `test_check_uncalled_entry_points::test_the_LIVE_BASELINE_accepts_EXACTLY_what_the_LIVE_TREE_measures`
  is green. **D3.477 CLEARS** — `test_check_limiter_daemon_dispatch` is **26/26** with `test_PLANT_053B`
  driving its plant again.

### (B) FULL BINDING CENSUS

**103 checks on disk, 103 registered, ZERO orphans in either direction, ZERO declared subjects missing
from disk.** 98 of 103 carry a test module; 100 of 103 carry one that asserts a non-PASS verdict.
The three that carry no can-fail control at all — `check_go_timeout`, `check_crucible_calendar`,
`check_tmpfs_inode_headroom` — are **D3.483**, opened rather than passed over. None is this arc's.

### (C) FULL `verify.py` AT THE MERGED TREE — `97 | 4 | 2 | 0`, THE PREDICTED TUPLE

`check_i1_convergence` **[ok] under `verify.py`, not standalone** — which is the verdict that counts
(ARC 057's lesson: *a gate that passes alone and fails in the suite measured one tree and was asked
about another*). Every neighbouring invariant gate green: `check_stop_maintenance`,
`check_uncertainty_flatten`, `check_limiter_daemon_dispatch`, `check_fill_handler`,
`check_hot_path_purity`, `check_two_phase_entry`, `check_plane1_sole_writer`,
`check_artifact_gate_coverage`, `check_derived_claims`. `check_arc_status_contract` **[ok]** auditing
`arc_057.log`, as predicted.

**EVERY REMAINING RED, DISPOSITIONED EXPLICITLY — NONE IS AN INVARIANT FAILURE:**

| red | disposition |
|---|---|
| `check_ibgateway_service` | **ENVIRONMENTAL** — `127.0.0.1:4002` ECONNREFUSED. The gateway is down and needs the operator's tap. |
| `check_ibgateway_config` *(cannot-measure)* | **ENVIRONMENTAL** — same unreachable port. Rule 10 working: a property whose subject is unavailable is not proven. |
| `check_observed_resource_claims` *(cannot-measure)* | **ENVIRONMENTAL** — downstream of the same port. |
| `check_monitor_tui` | **OPERATOR-DEPRECATED MON-1 (D3.113).** ARM3 stale pin over retired tooling. |
| `check_untracked_attribution` | **OPERATOR'S ARTIFACT** — `downloads/Pinokio-8.0.40-arm64.dmg`, not this project's work. |
| `check_uncalled_entry_points` | **INHERITED PUBLIC-SURFACE BACKLOG (D3.200/D3.203)**, where the ledger itself records that *an architect ruling is owed, not a code fix*. Not named by the brief and so stated explicitly: 54 unaccepted rows across `nixscore/store.py`, `publisher.py`, `supervision.py`, `drift_audit.py`, `recovery.py`, `fills.py` — **not one of them a risk-path safety property, and not one of them this arc's.** This arc SHRANK it: baseline 170 → 166 accepted, UNCALLED 170 → 167, unaccepted 55 → 54, high-water untouched. |

### (D) CLAIMS HARNESS

`check_derived_claims` **exit 0, 13/13** — 103 checks registered, 3645 tests collected, and
`check_debt_open_items=417` with `derived:ledger_rows=417` agreeing with the ARC 058 series row. **417
was read off the instrument, never typed:** it reported `DISAGREEMENT derived:ledger_rows=417,
stated:series_table_latest_row=416` inside the same edit that staled it, exactly as at ARC 057.

---

## FREEZE — ASSERTED WITH `git hash-object`, NOT CLAIMED

The diff is **exactly** the declared set: `scripts/limiterd.py`, the closing-fill handler
`scripts/nixrisk/closing.py` (named), the convergence gate + its test, the D3.477 test-anchor fix,
`docs/CHECK-DEBT.md` — plus `checks/registry.json` (the +1 registration the check contract requires),
the `uncalled_entry_points_baseline.json` shrink the brief anticipated, `test_check_order_path_bans.py`
(the re-banked count), and `scripts/tests/test_closing.py`.

**BYTE-IDENTICAL to `9bc04d9`, all twenty:** `stopwatch.py` **`274f6aa7224fda5c`** — *the `forget`
METHOD is unchanged and what moved is the CALL SITE* — `stops.py`, `flatten.py`, `fills.py`,
`fill_seam.py`, `positions.py`, `execution.py`, `join.py`, `outcomes.py`, `reservations.py`,
`completions.py`, `freshness.py`, `picture.py`, `seam.py`, `wal.py`, `projection.py`, `gate.py`,
`sizing.py`, `ema.py`, `realized.py`.

**WHAT MOVED INSIDE `limiterd.py` AND IS NAMED RATHER THAN LEFT TO BE FOUND.** The C2 producers'
LOGIC is untouched: the only deletions are the two `reason=` strings bound to named locals (same text,
because the close must carry §6.1b:352's word and deriving it twice would be the system choosing one
fact twice), the two constructor signatures, the three construction sites, and **two inherited
`ruff format` sites that were already red at HEAD**. `UnwiredExitSinks` is KEPT and still RAISES.

**`uncalled_entry_points_baseline.json` MOVEMENT, named:** four accepted rows removed —
`stops.py::StopBook.forget` (which HAD to go in the same commit, or wiring it would have become a
*shipped code now CALLS it* regression), `positions.py::EntryOrderOrigins.origin_for_trade`, and the
two inherited `seam.py::StopBookPort.breached/maintain` rows the gate had been asking to tighten. A
SHRINK in every counter; the high-water is untouched.

**A DEFECT THIS ARC FOUND IN ITS OWN FIRST ATTEMPT.** `closing.py` originally declared its own
`StopBookPort` / `StopWatchPort` / `OriginPort` Protocols. `check_uncalled_entry_points` resolves a
call to the DECLARED type of its receiver — so both `forget` verbs stayed UNCALLED through a module
that calls them on every close, and **D3.481 would have read as unpaid while it was being paid.** The
books are now typed concretely, which is `flatten.ProtectiveFlatten.__init__`'s own line (concrete for
the Limiter's books, Protocol for the §4 fan-out sinks) and the only spelling that keeps the caller
visible to the instrument that hunts for callers.

---

## RESIDUAL — WHAT A GREEN 12/12 DOES AND DOES **NOT** MEAN

**It means:** given correct inputs, the daemon provably runs the COMPLETE risk machinery — it reserves,
gates, fills, protects, trails, breaches, flattens, reconciles and releases, each proven and **none in
a library-not-daemon state.**

**It does NOT mean operationally live**, and these are later modules by correct decomposition, not gaps
in I1:

* **D3.473** — no real price-capture feed. The ring is command-fed; that is broker-datafeed's job.
* **D3.470** — the daemon DISPATCHES onset; it does not DETECT it (`BlackoutEvaluator`/`HaltFlag`).
* **D3.468** — the pending-timeout status directory has no producer.
* **D3.476** — `nixalloc/sizing.py` carries no trail distance; the Allocator is not on the approval path.
* **D3.480** — not-tradable deny-at-approval (D3.372's root) is separated, not built.
* **The broker is a STUB.** Nothing in this tree reaches a venue.

---

## BADGE VERDICT

**PART 2's convergence gate PASSES under `verify.py` ⇒ I1 DISCHARGED ⇒ clean set = 12/12.**

**PART 3's greening is CLEAN**: the full suite's only new red was this arc's and is fixed, the other
eight are proven inherited; the binding census has no orphan, no unregistered check and no gate
pointed at a subject that does not exist; the claims harness is exit 0; and **every remaining
`verify.py` red is environmental or operator, not an invariant failure** — stated one by one above so
the decision is auditable.

⇒ **LIMITER BADGE RED → GREEN. MODULE 1 COMPLETE.**

### THE BOARD, REDRAWN

| | |
|---|---|
| clean set | **12 / 12** |
| open invariants | **none** |
| Limiter badge | **GREEN** |
| Module 1 | **COMPLETE** |
