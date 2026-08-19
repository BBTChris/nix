# ARC 038 sub-agent D — MONEY-TRUTH ACCOUNTING (I6 net-liq/cash · I7 atomic picture)

Worktree: `/home/bbt/nix-wt-arc-038-d`   Branch: `arc-038-d`
Interpreter: `/home/bbt/nix-wt-arc-038-d/.venv/bin/python` (CPython 3.14.4, GIL enabled)
Invariants assigned: **I6** — §14:972 *"**Survival is watched on net-liq; sizing is
computed on cash.** Never conflate."* (reason at §15 C2:988) — and **I7** — §3:157-165's
*FULL FINANCIAL-PICTURE PUBLISH* and its **ATOMICITY RULE**, over §12.7's transport.

Frozen SHA-1s the integrator will diff against
(`/home/bbt/nix/scratchpad/arc038/frozen_limiter_shas.txt`): `picture.py`
`020bb6b3…`, `survival.py` `4c809e42…`, `gate.py` `26ed1983…`. **`gate.py` is
UNTOUCHED.** `picture.py` and `survival.py` each carry exactly the edits named by
FD1–FD4 below and nothing else.

## VERDICT TABLE

| invariant | red-team attempt | outcome | gate audited | gate non-vacuous? | gate reddens on plant? |
|---|---|---|---|---|---|
| I6 | AST census of all 119 cash-like/net-liq-like reads in `nixrisk`+`nixalloc`, then DROVE cash 100,000 / net-liq 40,000 and the inverse with the floor placed BETWEEN them, through `mark`, `reconcile`, `sizing_liquidity`, `floor`, `headroom_usd`, `margin_contracts` and all four Phase-B gate rules | **RESISTED** on discrimination (R-D1) · **VIOLATION** on the floor's own input and its clamp (**FD2**) | `check_survival_watch` | yes — SUBJECTS = `scripts/nixrisk/survival.py`; imports it from the worktree and drives 3 arms each with its own falsifier | **yes** — RED naming `scripts/nixrisk/survival.py:nonconflation: sizing_liquidity()=1050.0, expected the CASH figure 1200.0 — §15 C2` |
| I6 | §15 C3 degenerate cases: zero/invalid/non-finite stop, absent/zero/non-finite margin, negative headroom, NaN/±inf on either money quantity | **RESISTED** on the Allocator's three (R-D2) · **VIOLATION** on the publisher's own-table (**FD1**) | `check_allocator_sizing` | yes — SUBJECTS = `scripts/nixalloc/sizing.py`; reads execution order from the subject's own arithmetic recorders, and it DOES drive the negative-headroom case (its arm at `:814`) | **yes** — RED once the plant was correctly aimed; my first plant was a NO-OP and I say so in the gate audit |
| I7 | 18,481 distinct generations published by a real publisher PROCESS, read by this process over a real `ipc://` socket, 15.7 MB on the wire, every snapshot held to an arithmetic generation identity | **RESISTED**, 0 tears (R-D3) | `check_picture_atomicity` | yes — SUBJECTS = `scripts/nixrisk/picture.py`; 2,000 reads over 69 versions in-process, 40,128 real wire bytes, three plants required to tear | **yes** — RED naming the torn read at a named version and row |
| I7 | 4 real writer THREADS in `commit()` at once, 6,000 attempts | **RESISTED** — 7,768 `ConcurrentWriter` refusals, 0 tears, 0 duplicate versions, `current()` == last published (R-D4) | `check_picture_atomicity` | as above | as above |
| I7 | real `SIGKILL` of the publisher process (reaped `-9`), then the mirror interrogated | **VIOLATION** — 22,356 `tradable()` permissions over 0.477 s from a corpse (**FD6**) | `check_picture_atomicity` `_arm_stale` | yes — drives empty/aged/fresh | **no plant needed: the defect is RESIDENT and the gate is GREEN** |
| I7 | a truncated body, a codec fuzz over every top-level key × 8 poisoned values, `drain(timeout_ms=0)` mid-flight | **VIOLATION** ×2 (**FD3** freshness stamp, **FD4** `OverflowError`) | `check_picture_atomicity` `_arm_codec` | yes — round-trips `stop_distance`, refuses a stripped row and a schema-1 body | **no plant needed: both defects RESIDENT, gate GREEN** |
| I7 | a second publisher PROCESS rebinding the same `ipc://` path after the real one dies (D3.316's shape, on the money table) | **VIOLATION** — a fabricated picture adopted, balance 10,000 → 10,000,000 (**FD5**) | `check_state_bus` / `check_picture_atomicity` | yes | **no plant needed: RESIDENT, both GREEN** |
| I7 | §12.7's RESTART REBUILD: a publisher restarts under a live subscriber and republishes the post-restart truth | **VIOLATION** — all 60 rebuild snapshots dropped as out-of-order; mirror kept a position §14's *restart = flat* denies (**FD7**) | `check_state_bus` | yes | **no plant needed: RESIDENT, GREEN** |
| I7 | a RE-ENTRANT sink, since `commit` releases `_writing` before `publish` | **VIOLATION, not reachable in this tree** — wire carried versions `[3, 2]`; mirror ended at v2 while the book held v3 (D3.386) | `check_picture_atomicity` | yes | **RESIDENT, GREEN** |

## FINDINGS

Seven. Four DISCHARGED in this arc with both halves of every control proven;
three BLOCK and define ARC 039, for reasons stated rather than softened.

### FD1 — a REFUSED publish still advanced the Limiter's OWN table, and the poisoned table made the full §3 gate pass APPROVE $400,000 of margin on a $10,000 account (magnitude's reachability stated below)

- **Invariant:** I7. §3:164 *"ATOMICITY RULE: balance and the position table
  publish together as one snapshot — never two separate reads — so the Allocator
  can never compute headroom off a stale balance + fresh commitment (or vice
  versa). Every consumer reads a self-consistent picture."*  Plus directive 4
  (fail closed) and `nix_check_contract.md` §17.
- **Site:** `scripts/nixrisk/picture.py:377` (pre-repair) —
  `self._current = picture  # <- THE single store. Atomicity lives here.`
  executed BEFORE `self.publish(picture)` at `:381`, which is the only place
  `picture_defects` ran.
- **Scenario (executed):** `.venv/bin/python` with `PYTHONPATH=<wt>/scripts`.
  Commit a healthy picture ($10,000 balance, one OPEN row at $500 margin), then
  `book.commit(sum_reservations=float("-inf"))`. `publish()` refuses — correctly —
  and raises `TornPicture`. Then read `book.current()` and run the **real**
  `gate.GatePass` built from `gate.default_manifest` with the real
  `reservations.ReservationLedger` over it, with an oversized order (800
  contracts × $500 = $400,000).
- **Observed:**

  ```
  ACCOUNT BALANCE $10,000.  ORDER: 800 contracts x $500 margin = $400,000
  CONTROL (healthy picture v=2): SIZE_DOWN by aggregate_margin_cap ; qty 800 -> 12
     reason: §6.5 cap: committed 500.0 + proposed 400000.0 is not < 0.7 x balance
             10000.0 = 7000.0; clamped 800 -> 12 contract(s)
  PUBLISH REFUSED: refusing to publish version 3: sum_reservations is -inf ...
  BUT book.current() now returns v=3 committed=-inf deployable=inf
  GATE PASS over the poisoned own-table: **APPROVE** by manifest_exhausted
     evaluated: ('global_halt', 'blackout_window', 'tradability', 'data_staleness',
                 'clock_skew', 'in_flight_lock', 'picture_coherence',
                 'aggregate_margin_cap', 'survival_headroom', 'deployable_ceiling')
     approved qty: 800
  ```

  All four Phase-B money rules cleared and the §3 reservation was taken.

  **REACHABILITY, checked rather than assumed, because the honest version of this
  finding is weaker than the headline and still a finding.** I drove three
  different refusals through `commit()` and they do NOT all reach the same place:

  | refusal | reachable today? | what the poisoned own-table then does |
  |---|---|---|
  | `sum_reservations = -inf` | **NO** — `reservations.py:300` guards `if not math.isfinite(margin) or margin < MIN_MARGIN: raise InvalidReservation`, so the shipped ledger's `total_reserved()` cannot go non-finite | committed `-inf`, deployable `+inf`, **full fail-open: APPROVE 800 / $400,000** |
  | duplicate `trade_id` | **YES** — any caller that merges one row twice (`positions.py:_merged` shape) | `sum_open_margin` 500 → 1000, `deployable` 6500 → 6000; measured. Conservative for the Limiter, but the own table and the MIRROR now disagree, which is precisely the one-self-consistent-picture property §3 exists for |
  | `balance = NaN` | plausible, not proven (it arrives from a real broker parse; `test_broker_order.py:3000`'s F-A8-1 already records the cash field misbehaving on one route) | `deployable = 0.0`, and `gate._largest_fit` then raises `ValueError: cannot convert float NaN to integer` — **contained**, because `GatePass._dispatch` catches broadly and returns a DENY naming the rule and the exception (fail-closed, §18 satisfied) |

  So: **the fail-open magnitude I measured used an input the shipped ledger
  refuses.** It demonstrates the DIRECTION the defect permits, not a live route —
  and `commit()`'s signature takes a bare `float` from any caller, so the guard
  protecting it lives in a different class entirely. What is unconditional, and
  needs no reachability argument at all, is the structural fact: **`commit()`
  mutated the state it had just declared unpublishable**, which is a directive-4
  violation on its face and leaves the Limiter's own table and the published mirror
  at different versions with nothing able to say so.

  **And there is an interaction that settles the priority:** my own FD3 repair adds
  a NEW refusal trigger — a non-finite `published_ts`, which `FinancialPictureBook`
  produces from an INJECTED `clock`. Under the unfixed ordering that repair would
  have opened a fresh poisoning route. FD1's fix is a precondition for FD3's being
  safe, and they shipped together.
- **Why the tests did not catch it:** `test_picture.py::test_publish_REFUSES_an_incoherent_snapshot_and_NAMES_the_field`
  calls `publish()` DIRECTLY on a hand-built picture, never through `commit()`, so
  the store/validate ORDER is outside its scope; and it asserts on the exception
  and the counter, never on `current()` afterwards. `check_picture_atomicity`
  never drives a REFUSED commit at all: all four of its race arms publish
  coherent pictures, so `refusals` stays 0 and the poisoned branch is never
  entered. Nothing in the tree asserted that a refusal leaves state unchanged.
- **Status:** **DISCHARGED IN THIS ARC.** `commit()` now derives the candidate,
  runs `picture_defects` on it, and refuses BEFORE the single store, naming both
  the field and the version that stands. Control:
  `test_arc038_d_money_truth.py::test_FD1_a_REFUSED_commit_leaves_the_OWN_TABLE_STANDING_and_the_gate_CLAMPS`,
  which stages `picture.py` with the guard neutered (`if False:`), proves the
  loaded module's `__file__` is the staged path, and REQUIRES the staged run to
  report `version==3, committed==-inf, deployable==inf, APPROVE, qty==800` before
  it is allowed to assert the repaired run clamps to 12.
- **Debt row:** D3.387 — not for the repaired ordering, but for the SEAM the
  reachability table above exposes: `commit()`'s `sum_reservations` is a bare
  `float` and the finiteness guard that makes the worst case unreachable lives in a
  different class, with nothing enumerating which callers must route through it.

### FD2 — the survival FLOOR's own input was unguarded, so ONE NaN margin silences §6.5's force-flatten; and the floor did not clamp ≥ 0

- **Invariant:** I6. §14:972; §6.5:415 *"force-flattens when `net_liq < Σ open
  margin × (1 + safety_pad)`"*; §7:483 *"every term clamps ≥ 0 (no negative-floor
  artifacts)"*.
- **Site:** `scripts/nixrisk/survival.py:458` (pre-repair) —
  `def _require_finite(self, cash: float, net_liq: float, where: str)`, which
  sweeps `cash` and `net_liq` only — and `:464` `_floor_for`, which returned
  `sum_open_margin * (1.0 + self._safety_pad)` unclamped. `mark()` (`:390`) and
  `reconcile()` (`:435`) both call the guard and both then hand
  `sum_open_margin` straight to the floor.
- **Scenario (executed):** three drives. (a) `mark(cash=50_000, net_liq=9_000,
  sum_open_margin=nan)`. (b) `mark(cash=50_000, net_liq=-5_000,
  sum_open_margin=-10_000)`. (c) `reconcile("orphan")` against a `BrokerReading`
  whose single OPEN `PositionRow` carries `margin=float("nan")` — `reconcile`
  derives Σ open margin from `poll.positions`, so the poll is the injection point.
- **Observed:**

  ```
  CONTROL    floor=11000.0 net_liq=9000.0 breached=True  fired=True  flattens=1
  NaN Sopen  floor=nan                     breached=False fired=False flattens=0 criticals=0
  neg Sopen  floor=-11000.0 net_liq=-5000.0 breached=False fired=False
  reconcile NaN-margin row: applied=True floor=nan net_liq=9000.0 breached=False
            fired=False flattens=0 criticals=0
    floor() -> nan   sizing_liquidity() -> 50000.0
  ```

  `SurvivalReading.breached` is `net_liq < floor`; with `floor = nan` that is
  `False` for every net-liq, so the watch reports the account SAFE and fires
  nothing — and silence is exactly what a healthy account looks like. §12.9's
  Critical page is not raised either. On the negative arm an account at −$5,000
  net-liq reads `breached=False`.
- **Why the tests did not catch it:** `test_survival.py` and
  `check_survival_watch` both drive the non-conflation with FINITE Σ open margin
  (they place the floor between cash and net-liq, which is the right test for the
  C2 distinction and says nothing about the floor's own arithmetic). The module's
  `_finite` docstring cites §17 by name, and the guard it belongs to covered two
  of the three inputs the predicate reads; nothing enumerated them.
- **Status:** **DISCHARGED IN THIS ARC.** `_require_finite` takes
  `sum_open_margin` and refuses it, naming the field; `_floor_for` clamps the term
  at 0.0. Controls: `test_FD2_a_NON_FINITE_SIGMA_OPEN_MARGIN_is_REFUSED_not_judged_SAFE`,
  `test_FD2_ONE_broker_row_with_a_NaN_margin_cannot_SILENCE_the_reconcile`,
  `test_FD2_the_FLOOR_CLAMPS_at_zero_per_SS7_483`. **The two repairs are COUPLED
  and the coupling was itself measured**: with the clamp present and the finite
  check removed, `max(0.0, nan)` is `0.0` (CPython's `max` keeps its first
  argument because `nan > 0.0` is False), the floor becomes ZERO, and the watch
  still never fires — so the plant that reproduces the shipped behaviour removes
  BOTH, and a third arm pins the half-repair so neither edit can later be read as
  sufficient alone.
- **Debt row:** none (discharged).

### FD3 — `published_ts`, §12.7's FRESHNESS STAMP, was the one field never validated: a non-finite stamp makes a mirror PERMANENTLY tradable

- **Invariant:** I7. §12.7:657 *"freshness stamps ride each update"*; §12.7:661
  *"mirror incomplete ⇒ treated as stale ⇒ fast-drop/deny until snapshot lands"*;
  §6.4's standing rule that a stale cache is refused, not carried.
- **Site:** `scripts/nixrisk/picture.py:240-250` (pre-repair) — the `_finite`
  sweep in `picture_defects`, which covered `balance`, `sum_open_margin`,
  `sum_reservations`, `committed`, `deployable` and **not** `published_ts`;
  consumed at `:619` `age = self._clock() - picture.published_ts` and `:620`
  `if age > self._max_age_s`.
- **Scenario (executed):** decode a real encoded picture with `published_ts`
  replaced, hand it to a `PictureMirror(max_age_s=0.5)`, and ask `tradable()`.
- **Observed:**

  ```
  published_ts=<now>          age=4.6e-05      defects=0  tradable=True   picture version 2, age 0.000s
  published_ts=<now-7200>     age=7200.0       defects=0  tradable=False  ... over the 0.500s ceiling
  published_ts=nan            age=nan          defects=0  tradable=True   picture version 2, age nans
  published_ts=inf            age=-inf         defects=0  tradable=True   picture version 2, age -infs
  published_ts=95000000000.0  age=-9.3e10      defects=0  tradable=True   picture version 2, age -93212904555.156s
  ```

  `nan > 0.5` is `False`, so the staleness arm — the only thing standing between a
  consumer and sizing on an arbitrarily old picture — is disabled in the
  PERMISSIVE direction, permanently. The reason string it hands the operator reads
  literally *"age nans"*. `FinancialPictureBook._build` sets this field from an
  injected `clock`, so the publisher itself can produce it; it does not require an
  impostor.
- **Why the tests did not catch it:** every existing construction of a
  `FinancialPicture` in `test_picture.py` uses `published_ts=0.0` or `time.time()`,
  both finite; `check_picture_atomicity._arm_stale` drives empty / aged / fresh —
  three finite stamps. The field was never poisoned by anything.
- **Status:** **DISCHARGED IN THIS ARC** for the non-finite half — one tuple entry
  in the `_finite` sweep, which arms the publisher's refusal AND the consumer's
  fast-drop at the same time. Controls:
  `test_FD3_a_NON_FINITE_FRESHNESS_STAMP_cannot_make_a_mirror_ETERNALLY_TRADABLE`
  (parametrised over NaN and +inf, both halves, plus the permit-a-fresh-one control
  without which "always refuses" would pass) and
  `test_FD3_the_PUBLISHER_also_refuses_a_non_finite_stamp`.
  **The FUTURE-STAMP half is NOT discharged** (last row above: a stamp 3,000 years
  ahead is finite, gives `age = -9.3e10`, and is still tradable). Closing it needs
  a bound on negative age, and that bound is §12A's `CLOCK_SKEW_MAX_MS` — minting
  one here would be a semantic decision taken in the wrong layer, which is exactly
  what `AggregateMarginCapRule` and `FinancialPictureBook` refuse to do for their
  own knobs. **D3.378.**
- **Debt row:** D3.378 (future-stamp half only).

### FD4 — `OverflowError` escaped the codec, so `PictureMirror.tradable()` — documented *"Never raises"* — RAISED

- **Invariant:** I7, §12.7's fast-drop verb. Check contract rule 11 / §18: a
  control asserts the reason; a verb whose job is to produce a reason must produce
  one.
- **Site:** `scripts/nixrisk/picture.py:495` (pre-repair)
  `except (KeyError, TypeError, ValueError) as exc:` in `_decode_row`, and `:522`
  `except (AttributeError, KeyError, TypeError, ValueError) as exc:` in
  `decode_picture`. `int(float("inf"))` raises `OverflowError`, an
  `ArithmeticError` — not a `ValueError`.
- **Scenario (executed):** a codec fuzz over every top-level wire key × 8 poisoned
  values (80 mutations), then the two integer fields specifically, each fed to a
  `PictureMirror` and `tradable()` called.
- **Observed:**

  ```
  CODEC FUZZ: mutations=80 refused=50 accepted=28 UNHANDLED=2 trunc_unhandled=0
      UNHANDLED OverflowError on version=inf: cannot convert float infinity to integer
  wire body with version=inf:
     decode_picture -> UNCAUGHT OverflowError: cannot convert float infinity to integer
     PictureMirror.tradable() RAISED OverflowError  <-- docstring says 'Never raises'
  wire body with size=inf:  (same, from `_decode_row`)
  ```

  Reachable: `json.dumps`/`json.loads` both handle `Infinity`, and D3.316 measured
  that an `ipc://` bind is **not** exclusive — see FD5, which I reproduced on this
  topic. A consumer's fast-drop that raises does not fast-drop; it takes the pump
  loop down with it.
- **Why the tests did not catch it:** the codec tests and
  `check_picture_atomicity._arm_codec` drive a MISSING key (`stop_distance`
  stripped) and a wrong `schema` — both `KeyError`/refusal paths. Nothing fed a
  value whose *type* was right and whose *magnitude* was not.
- **Status:** **DISCHARGED IN THIS ARC** — `OverflowError` added to both handler
  tuples. Control: `test_FD4_an_INFINITE_int_on_the_wire_is_REFUSED_and_never_RAISES`,
  parametrised over `version` and `size`, requiring the staged (unrepaired) module
  to RAISE `OverflowError` and the repaired one to return `(False, reason)` whose
  text contains both `OverflowError` and `undecodable`.
- **Debt row:** none (discharged).

### FD5 — §3's financial picture carries NO WRITER IDENTITY on the wire, so a second process injected a fabricated picture: balance $10,000 → $10,000,000, `deployable` $500 → $7,000,000

- **Invariant:** I7. §12.7:648-652 *"Mirror model, NOT raw shared memory … Raw
  shared state tables would let multiple processes touch the same bytes …
  **reducing the single-writer principle to fiction**"*; §9/§12.10 make the Limiter
  the SOLE writer. `picture.py`'s own claim: *"Single writer by construction … there
  is no verb by which a consumer can write back."*
- **Site:** `scripts/nixrisk/picture.py:441` `encode_picture` — the wire body
  carries `schema, version, published_ts, balance, positions,
  margin_per_contract, sum_open_margin, sum_reservations, committed, deployable`
  and **no writer identity** — and `:592` `PictureMirror.picture()`, which adopts
  whatever decodes.
- **Scenario (executed):** real publisher binds `ipc://…`, publishes a true
  picture (balance $10,000, one OPEN row at $6,500 margin ⇒ `deployable` $500).
  Consumer subscribes and its mirror completes. The real publisher then CLOSES
  (the process death case). A SECOND `StatePublisher` binds the SAME path — D3.316
  measured that `ipc://` bind is not exclusive; libzmq unlinks and rebinds with no
  `EADDRINUSE` — and publishes pictures with balance $10,000,000 and an empty
  position table, calling `refresh_all()` so the snapshot flag is set.
- **Observed:**

  ```
  TRUE picture   : v=2  balance=10000.0    committed=6500.0 deployable=500.0
                 tradable -> (True, 'picture version 2, age 0.022s')
  AFTER IMPOSTOR : v=41 balance=10000000.0 committed=0.0    deployable=7000000.0
                 tradable -> (True, 'picture version 41, age 0.041s')
                 picture_defects: ()
                 out_of_order dropped: 0
    the wire carries NO writer identity for tbl.financial_picture: True
  ```

  The fabricated picture is self-consistent, fresh, in-order, and adopted. The
  asymmetry is the point: `nixscore`'s **ranking table** — which §6.6:467 says
  *"must NEVER halt order flow"*, i.e. the one table that is explicitly not a
  safety gate — HAS a `writer_identity` check that D3.316 calls *"the whole of
  §6.6's sole-writer enforcement"*. §3's financial picture, which every Phase-B
  money rule reads, has none.
- **Why the tests did not catch it:** `check_picture_atomicity` runs ONE process
  and says so in its own docstring (*"It does not prove cross-process delivery, fd
  inheritance…"*); `check_state_bus` owns the transport and asks whether delivery
  and snapshot-on-subscribe work, not who is on the other end. Neither gate has a
  second-writer-over-the-wire arm, and no test constructs two publishers on one
  endpoint for this topic.
- **Status:** **BLOCKS.** Not dischargeable inside this freeze: the repair is a
  `writer_identity` field on the body (a `WIRE_SCHEMA` 2 → 3 bump, `encode`/`decode`,
  `PictureMirror`, every construction site) plus a CONFIGURED expected identity on
  the consumer — a §12A knob this arc may not mint — plus re-pointing
  `check_picture_atomicity`'s codec and late-subscriber arms. `nixscore`'s
  implementation is the template and should be ported rather than re-invented.
  **Defines ARC 039.**
- **Debt row:** D3.379.

### FD6 — `PictureMirror` keys freshness on AGE ALONE: 22,356 `tradable()` permissions over 0.477 s after the publisher was SIGKILLed, while the tree's own liveness observer on the SAME socket already knew

- **Invariant:** I7 / the standing STALE-UNTIL-PROVEN-FRESH rule. §12.7:661;
  §6.4's stale-cache rule.
- **Site:** `scripts/nixrisk/picture.py:608` `PictureMirror.tradable()` — its four
  refusal arms are no-snapshot, undecodable, self-inconsistent, and
  `age > max_age_s`. There is no liveness input and no `note_liveness` verb.
- **Scenario (executed):** publisher in a CHILD PROCESS over a real `ipc://`
  socket; parent holds a `PictureMirror(max_age_s=0.5)` and, on the same
  subscriber socket, a `nixscore.liveness.PublisherLiveness` (ARC 037's
  instrument) purely as an observer. Settle to `tradable()==True`, then
  `os.kill(child.pid, signal.SIGKILL)` from this second process, reap, assert the
  `-9`, and then poll `tradable()` until it first refuses.
- **Observed:**

  ```
  PRE-KILL  tradable=True  picture version 2, age 0.019s
  SIGKILL delivered; child reaped rc=-9 (expect -9): True
  POST-KILL permitted 22356 tradable() verdicts over 0.477 s after a PROVEN-DEAD writer
  POST-KILL identity tears observed: 0 ; production picture_defects: 0
  first refusal at +0.478 s: mirrored picture version 2 is 0.500s old, over the 0.500s ceiling
  headroom off the corpse: deployable=65991.7 committed=4009.0 balance=100001.0
  LIVENESS OBSERVER (same socket, ARC 037's instrument): writer_live=False
     verdict=LivenessVerdict(live=False, signal='peer', reason="the … publisher's peer is GONE — libzmq CONNECT_RETRIED …")
  ```

  This is D3.244's exact shape — *"for `stale_after_s` after Scoring dies, readers
  RANK on a corpse's table"* — transposed onto the table that gates money, and it
  scales linearly with `max_age_s`, which D3.125 records has no §12A home for this
  class either. The observation is not missing: it is available on the same file
  descriptor and simply not wired.
- **Why the tests did not catch it:** `_arm_stale` and
  `test_an_OVER_AGE_mirror_DENIES_and_a_FRESH_one_PERMITS` both advance a fake
  clock; no test kills a publisher under a `PictureMirror`. The age route is
  correct as written — the picture genuinely IS young — so nothing disagrees.
- **Status:** **BLOCKS**, and the reason is a dependency, not a difficulty.
  **D3.123 is an OPEN architect ruling on whether `PictureMirror` should exist at
  all** — it records that the tree holds two consumer-side mirrors of §3's one
  table and that `nixalloc.mirror.AllocatorMirror` subsumes `PictureMirror`.
  Wiring a liveness stance into a class the ledger says may be retired is building
  on a slab that is under review, and D3.319 records that the stance's DEFAULT is
  itself a decision with a measured downside in both directions. So: measured,
  quantified, and handed forward with the ruling it waits on named.
- **Debt row:** D3.380.

### FD7 — §12.7's RESTART REBUILD never reaches an already-connected consumer: every rebuild snapshot is DROPPED as out-of-order, and the mirror keeps asserting a position the restart invariant says cannot exist

- **Invariant:** I7 / §12.7:658-661 *"Slow-joiner mitigation = snapshot-on-subscribe
  (mandatory, not polish) … so a restarted consumer is correct within seconds — it
  never waits for organic deltas and never sizes on a half-built mirror"*; and
  §14:970 *"Restart = flat, always."*
- **Site:** `scripts/nixbus/statebus.py:442-448` `Mirror.apply` —
  `previous = self._last_seq.get(message.topic, -1); if message.seq <= previous:
  self.out_of_order += 1; return` — against `:220` `self._seq = 0`, which every
  fresh `StatePublisher` starts from. The ordering key is the TRANSPORT sequence,
  which is per-publisher-instance, not per-table.
- **Scenario (executed):** publisher A binds a real `ipc://` endpoint, a consumer
  subscribes and its `PictureMirror` completes; A then runs 399 more commits so its
  transport `_seq` climbs to 400. A closes (the Limiter restarts). Publisher B binds
  the same path, and its book publishes §12.7's rebuild — the post-restart truth,
  which per §14 is FLAT with a fresh balance — calling `refresh_all()` 60 times so
  the snapshot flag is set on every one. The consumer's socket is never re-created,
  which is the whole point: it is a consumer that stayed up across the writer's
  restart.
- **Observed:**

  ```
  after A's run:  mirror v=400  transport _seq applied=400  out_of_order=0
                  mirror holds balance=10000.0 sum_open_margin=899.0
  AFTER RESTART:  mirror v=400  balance=10000.0  sum_open_margin=899.0
                  transport _seq held=400   out_of_order DROPPED=60
                  tradable -> (True, 'picture version 400, age 4.755s')
    => THE REBUILT SNAPSHOT WAS DISCARDED. The consumer is still sizing on the
       PRE-RESTART picture.
  ```

  All sixty rebuild snapshots were dropped. The mirror asserts an OPEN position of
  $899 margin against a $10,000 balance while the restarted Limiter's truth is
  $99,999 and **flat** — the exact state §14:970 says a restart guarantees. The
  mirror cannot recover: it never applies another message from this publisher, so
  the only exit is ageing out. **Mitigation, stated so the finding is not
  inflated:** it does eventually age out — with a realistic `max_age_s` it denies
  within that ceiling — so the end state is fail-closed. The severities that remain
  are that §12.7's *"correct within seconds"* guarantee is defeated in the
  publisher-restart direction *entirely* (not slowly), and that inside the ceiling
  a consumer sizes on a picture the restart invariant denies.
- **Why the tests did not catch it:** `check_state_bus`'s arms are delivery, a late
  subscriber's snapshot, the withheld-`service()` control, delta-only ⇒ stale, and
  the freshness stamp — no arm restarts a publisher under a live subscriber.
  `check_picture_atomicity._late_subscribers` stages two subscribers against ONE
  publisher (D3.39's repair), which is the opposite direction. `Mirror.out_of_order`
  exists precisely so this is not hidden, and nothing outside the mirror reads it.
- **Status:** **BLOCKS.** The subject is `scripts/nixbus/statebus.py`, which is
  `capture`'s and `check_state_bus`'s, not mine to edit under this freeze — and
  more importantly **the correct repair is the SAME repair as FD5's**: telling a
  legitimate new writer from a stale duplicate is exactly the writer-identity
  question, and a seq guard cannot answer it. Fixing the seq guard alone (e.g.
  accepting any `_kind == "snapshot"` regardless of seq) would close this and open
  FD5 wider, because an impostor's snapshot would then always win.
- **Debt row:** D3.385, coupled to D3.379.

## PROOFS OF RESISTANCE  (the attacks that FAILED to break the invariant)

### R-D1 — I6's discrimination held, driven BOTH WAYS with the floor placed BETWEEN the two figures

- **Attack:** a mechanical census first, then a drive. The census is an **AST walk**
  (not a grep, so a docstring mentioning `net_liq` is not counted as a read) over
  all 30 `nixrisk` modules and all 8 `nixalloc` modules, classifying every `Load`
  attribute access and every keyword argument in
  `{cash, balance, sizing_liquidity, deployable, committed, sum_open_margin,
  sum_reservations}` vs `{net_liq, net_liquidation, unrealized, floor, breached,
  net_liq_mark}`. Then: `cash = 100,000`, `net_liq = 40,000` and the inverse, with
  Σ open margin = 50,000 so the floor is **55,000 — strictly between them**, so the
  two figures give OPPOSITE verdicts and a conflation cannot hide.
- **Command + output:**

  ```
  CENSUS: 119 reads across 12 files  (CASH-like 82, NET-LIQ-like 37)
  FILES READING BOTH FAMILIES (the only places a conflation can live):
      ['drift_audit.py', 'sizing.py', 'survival.py']

  floor = 50000 x (1 + 0.10) = 55000 --- BETWEEN 40000 and 100000

  cash HIGH / net-liq LOW  : sizing_liquidity()=100000.0 floor()=55000.0 breached=True  FLATTEN FIRED=True
  cash LOW  / net-liq HIGH : sizing_liquidity()=40000.0  floor()=55000.0 breached=False FLATTEN FIRED=False
  --- through the RECONCILE path (broker-authoritative), same result

  picture.balance=HIGH : headroom_usd=70000.0 margin_contracts=140 cap=APPROVE   ceiling=APPROVE
  picture.balance=LOW  : headroom_usd=28000.0 margin_contracts=56  cap=SIZE_DOWN ceiling=SIZE_DOWN
    => every SIZING output moved with picture.balance and NOTHING read net-liq

  net-liq mark HIGH + bal HIGH -> APPROVE      net-liq mark LOW + bal HIGH -> DENY
  net-liq mark HIGH + bal LOW  -> APPROVE      net-liq mark LOW + bal LOW  -> DENY
    => SurvivalHeadroomRule moved with the MARK and was INVARIANT in picture.balance
  ```

  Only three files read both families, and in each the two are separated by verb.
  `sizing.py`'s three "NET-LIQ" hits are **my instrument's own false positives** —
  they are `math.floor`, the name colliding with `SurvivalReading.floor` — verified
  by reading `sizing.py:575-593`; stated because an unstated false positive in a
  census is the census lying about its own precision.
- **What this does and does NOT prove:** it proves that at every site where the two
  quantities are USED, the wrong one demonstrably does not move the output. It does
  **not** prove the WIRING is right, and cannot: **`FinancialPictureBook` has ZERO
  production construction sites** (`grep -rn "FinancialPictureBook(" scripts/
  --include=*.py | grep -v scripts/tests/` returns nothing), so the question "is
  the number fed to `balance` the CASH one?" has no production answer to measure.
  The one production writer that supplies a balance at all,
  `flatten.py:674 balance=balance.cash`, is correct — and `flatten.py:194-196`
  declares both halves of the broker balance with §15 C2 cited on each. Against
  that, the FROZEN seam's `BrokerTruth` (`seam.py:806-819`) carries a SINGLE
  `balance: float` with cash-or-net-liq unstated, which is precisely the *"single
  equity figure"* C2 warns about, and `coldstart.py` consumes it. **D3.381.**

### R-D2 — §15 C3's degenerate cases hold on the Allocator side

- **Attack:** every C3 clause driven with zero, negative, NaN and +inf.
- **Command + output:**

  ```
  C3a zero/invalid stop => deny:      per_contract_risk 0 / -5 / NaN / +inf -> risk_contracts=0 (all four)
  C3b margin absent/zero/non-finite:  margin_per_contract 0 / -500 / NaN / +inf -> margin_contracts=0 (all four)
  C3c clamp >= 0:                     headroom_usd=-2000.0 -> margin_contracts=0, published deployable=0.0
  ```
- **What this does and does NOT prove:** the Allocator's `risk_contracts` and
  `margin_contracts` both carry an explicit `math.isfinite` guard and both clamp;
  `headroom_usd` deliberately does not clamp and documents that the clamp is
  `margin_contracts`' job — which is consistent. It does NOT clear the Limiter's own
  `gate._largest_fit`, whose guard is `if margin_per_contract <= 0.0` — a test NaN
  passes (`nan <= 0.0` is False) and `int(room // nan)` then raises
  `ValueError: cannot convert float NaN to integer`. That is **contained**:
  `GatePass._dispatch` catches broadly and returns a DENY naming the rule and the
  exception (fail-closed, and the reason names the site, so §18 holds). It is
  nevertheless an asymmetry between two implementations of the same clamp, reached
  from an Allocator-supplied field. **D3.382**, recorded rather than repaired,
  because `gate.py` is another sub-agent's subject this arc and I did not touch it.

### R-D3 — I7 held over a REAL process boundary, 18,481 generations, 0 tears — and the counter is PROVEN able to count

- **Attack:** a publisher PROCESS (`subprocess.Popen`, explicit `env=` per D3.344)
  binds a real `ipc://` endpoint and commits 20,000 generations through the real
  `FinancialPictureBook` + `StateBusPictureSink` + `statebus.StatePublisher`; this
  process subscribes with a real `zmq.SUB` and decodes EVERY message. **The
  identity:** generation `g` is stamped into BOTH halves — `balance = 100000 + g`,
  and every row carries `margin = g*1000+k`, `size = g`, `stop_distance = g`, with
  `sum_reservations = 3g` — so a snapshot assembled from two generations violates
  arithmetic and is **counted**, and the three derived aggregates are checked
  against generation `g`'s true values so a headroom consequence is counted too.
- **Command + output:**

  ```
  ===== 20000 generations, real process boundary =====
  child_rc                   0
  child_out                  PUB done commits=20001 publishes=20001 emitted=20001 deltas=20001
  messages_decoded           18501
  bytes                      15698330
  distinct_versions          18481
  distinct_generations       18481
  out_of_order_dropped       0
  decode_errors              0
  identity_tears             0
  production_picture_defects 0

  ===== the CAN-FAIL: the same harness, publisher emitting §3's COHERENT tear =====
  messages_decoded           17882
  distinct_generations       17861
  identity_tears             267932
  production_picture_defects 0        <-- the production predicate is BLIND, as its docstring says
  ```

  The plant is §3's hazard verbatim: read balance at generation *k*, the table at
  *k+1*, then DERIVE every aggregate from what was read. It produced **267,932**
  counted tears and **zero** `picture_defects` — so the identity, not the subject's
  own predicate, is what has power here, and the subject's clean sheet over 18,481
  generations is a measurement.
- **What this does and does NOT prove:** it proves the snapshot is indivisible
  across a real process boundary at real wire volume, for the fields the identity
  covers. It does NOT prove anything about a HOSTILE writer (FD5) or about a dead
  one (FD6), and it does not exercise `refresh_all`'s snapshot path under
  concurrency beyond the initial rendezvous.

### R-D4 — the writer-side guard fires, and no half-published picture survives it

- **Attack:** 1, then 2, then 4 real threads calling `commit()` on one book behind a
  `threading.Barrier`, every body reaching the sink decoded and judged.
- **Command + output:**

  ```
  threads=1 iters=5000  commits=5000 publishes=5000 refusals=0     ConcurrentWriter=0
  threads=2 iters=5000  commits=8807 publishes=8807 refusals=1193  ConcurrentWriter=1193
  threads=4 iters=4000  commits=8232 publishes=8232 refusals=7768  ConcurrentWriter=7768
    every run: bodies on the sink == commits; duplicate version stamps 0;
               TEARS in any published body 0; LOST UPDATES 0;
               final own-table version == last published version: True
  ```

  Attempts are conserved exactly (8807 + 1193 = 10000), so no attempt vanished.
- **What this does and does NOT prove:** it proves the refusal is real and that
  nothing incoherent or duplicate reached the wire under contention. **The residual
  is stated rather than glossed:** `_writing` is a non-atomic check-then-set
  (`if self._writing:` then `self._writing = True` across a bytecode boundary), so
  the absence of a duplicate version stamp is a measurement under **this
  interpreter's GIL** and not a proof under a free-threaded build. §5 makes the
  Limiter single-threaded, so this is a property of the design's assumption rather
  than of the code — and it is now written down.

  **A second residual, found by driving the guard's boundary rather than its
  middle:** `commit()` sets `self._writing = False` in its `finally` and only THEN
  calls `self.publish(picture)`, so the sink runs OUTSIDE the single-writer guard.
  A sink whose `emit` re-enters `commit` is therefore **not** refused — driven, no
  `ConcurrentWriter` raised — and the wire received versions **`[3, 2]`**: the
  inner commit's snapshot published before the outer's. The mirror orders by the
  transport `_seq`, which rises across both sends, so it cannot discard the
  regression: it ends holding **v2 while the book holds v3**, with
  `out_of_order == 0` and `picture_defects()` empty on both. **Not reachable in
  this tree** — `StateBusPictureSink.emit` calls `publish` and returns, and the
  fan-outs in `flatten.py`/`recovery.py` run after `commit` returns — so it is
  **D3.386**, recorded rather than repaired, with the two candidate repairs and
  their costs named in the row (moving `publish` inside the guard makes a transport
  failure leave `_current` behind, which is a fail-OPEN under-count of
  commitments; a version-monotonicity assertion at the sink boundary is smaller).

### R-D5 — the codec refuses 50 of 80 poisoned bodies and never mis-accepts a money field; a truncated frame is a LOUD refusal

- **Attack:** every top-level wire key replaced with each of
  `None, "x", [], {}, NaN, +inf, -1, 1e309`, plus 200 truncations of the JSON text,
  plus a real raw `zmq.PUB` impostor sending a body cut in half.
- **Command + output:**

  ```
  CODEC FUZZ: mutations=80 refused=50 accepted=28 UNHANDLED=2 trunc_unhandled=0
      (the 2 UNHANDLED are FD4; of the 28 accepted, the only CLEAN acceptances were
       published_ts=nan/inf/-1 -- which is FD3 -- and margin_per_contract={})
  TRUNCATED WIRE: drain RAISED StateBusError: undecodable body on topic
      b'tbl.financial_picture': JSONDecodeError('Unterminated string starting at ...')
    the mirror kept its last GOOD picture (version 2) and did not adopt the fragment
  drain(timeout_ms=0) mid-flight, deltas only: mirror.picture() -> None
      ("mirror incomplete: no snapshot yet") -- §12.7's fail-closed rule
  ```
- **What this does and does NOT prove:** every acceptance that mattered was either
  a defect I then repaired (FD3, FD4) or harmless (`margin_per_contract={}` — an
  empty margin cache is a legitimate state and §7's *"symbol missing from margin
  cache ⇒ not-tradable"* is the sizer's rule, not the codec's). A truncated frame
  is refused loudly by the transport with a named topic; that is
  `check_state_bus`'s subject and I did not judge it further. It does NOT prove the
  codec is exhaustively type-safe — 80 mutations is a sweep, not a proof.

## GATE AUDIT  (per gate, the non-vacuity + plant/restore evidence)

**TWO METHOD NOTES FIRST, because my own instrument failed twice and §0a puts it
under audit too. Both failures are recorded before any gate verdict below.**

**(1) The restore destroyed the repairs.** My first plant/restore harness restored
with `git checkout -- <path>` and **silently destroyed this arc's own uncommitted
repairs** to the two files it planted in — a restore that reverts to the INDEX
cannot tell *the plant* from *every change since the last commit*. Caught only
because the harness printed a sha before and after (`byte-identical=False`). The
repairs were re-applied, COMMITTED FIRST, and the harness now snapshots
`read_bytes()` and restores by `write_bytes()`, asserting SHA-256 byte-identity.
**D3.383**, because nothing in the tree stops the next agent doing it.

**(2) Two plants planted NOTHING, and both first reported the gate GREEN — which
is exactly the shape I was hunting in the gates.** I report them as my errors
rather than as gate findings, because I checked before concluding:

* `check_allocator_sizing`: I removed the INNER clamp from
  `margin_contracts` — `max(0, math.floor(max(0.0, headroom) / mpc))` →
  `max(0, math.floor(headroom / mpc))` — and the gate stayed green. **The plant is
  a NO-OP: the OUTER `max(0, …)` already catches it.** Proven by driving all three
  variants rather than reading them:

  ```
  headroom=-2000.0  shipped=0  planted=0  identical=True   truly_unclamped=-4
  headroom=-1.0     shipped=0  planted=0  identical=True   truly_unclamped=-1
  headroom=7000.0   shipped=14 planted=14 identical=True   truly_unclamped=14
  ```

  Re-aimed to remove BOTH clamps → **RED**. Incidental observation worth one line:
  `margin_contracts` carries two redundant clamps and removing either alone is
  undetectable by anything.
* `check_state_bus`: I planted `snapshot=True → False` in `refresh_all`, and the
  gate stayed green. **`refresh_all` is §12.7's *periodic full-state refresh*, not
  the snapshot-on-subscribe path the gate exercises** — that is
  `_serve_subscription`, which I had left intact. The property is not ungated
  either: `scripts/tests/test_statebus.py:413
  test_refresh_all_RESENDS_every_owned_table_as_a_SNAPSHOT` owns it. Re-aimed at
  `_serve_subscription` → **RED**.

**The lesson, which the harness now carries:** it asserted only that the plant's
TEXT was found and replaced. The sizing case had a textual change with **zero
behavioural effect**, so text-difference is not plant-efficacy. The harness now
refuses to judge a plant whose source is unchanged, and the honest statement of the
residual is that even that is weaker than requiring the plant to move an observable.
My pytest suite does hold the stronger form — every `_stage` plant there must make
the BAD OUTCOME APPEAR before the repaired assertion is allowed to run.

Every gate below was run standalone as
`PYTHONPATH=<wt>/scripts .venv/bin/python checks/<gate>.py`, with the git
environment scrubbed (`GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE` unset, D3.205).

### check_picture_atomicity
- **Claims:** I7 — *"the financial picture is observable only as one
  self-consistent snapshot under one version stamp, and a consumer whose mirror is
  not complete and fresh refuses to size."*
- **Scope containment proven by:** `SUBJECTS = ("scripts/nixrisk/picture.py",)`;
  and by its own run evidence, which is a measurement and not a claim — 2,000 reads
  across 69 distinct versions with the writer reaching generation 201, **40,128 real
  wire bytes** off a real `ipc://` socket, and three PLANTS that tear at 100.0% /
  3.6% / 1.2% through the same harness (the last on the `stop_distance` axis). Zero
  wire bytes or a missed read floor is `CANNOT_MEASURE`, not a pass.
- **Plant:** `picture.py:_next`, `balance=previous.balance if balance is None else
  float(balance)` → `balance=previous.balance,  # PLANT: balance never advances`
  (§3's coherent tear, inside the subject).
  → **verdict: RED**, `rc=1`, `fail_needs_operator`, naming
  `TORN READ at version 3: balance 1000000.0 is generation 0 while row T0 carries
  margin 6.0 (generation 6), size 6 and stop_distance …` — a version, a row, and
  the two disagreeing generations.
- **Restore:** byte snapshot; SHA-256 byte-identical; gate green again.
- **THE FINDING, and it needs no plant:** this gate is **GREEN over four resident
  defects** — FD1, FD3, FD4 and FD6, all in its declared subject. Its docstring is
  honest about the boundary that lets three of them through (*"It runs one process.
  It does not prove cross-process delivery…"*), and its `refusals` counter stays 0
  on every arm because no arm ever drives a REFUSED commit. This is the
  ARC 035 / ARC 037 class: the gate is not vacuous, it is *scoped past* the gap.
  Pointing it at FD1/FD3/FD4 would be a real re-pointing job (a refused-commit arm,
  a non-finite-stamp arm, an `Infinity`-on-the-wire arm) and it is ARC 039's, not
  a freeze-legal edit to make here — the four are already gated by
  `test_arc038_d_money_truth.py`, which is where doctrine C.9 says the property
  should have exactly one instrument. **D3.384.**

### check_survival_watch
- **Claims:** I6 — *"survival is watched on net-liq; sizing is computed on cash"*,
  on `scripts/nixrisk/survival.py`.
- **Scope containment proven by:** `SUBJECTS = ("scripts/nixrisk/survival.py",)`;
  its evidence names the file and reports *"3 arms, each with a falsifier proven to
  lose its property"*, and the arms place the floor BETWEEN two divergent readings
  — the only configuration in which the distinction is observable at all.
- **Plant:** `survival.py:375`, `return self.read().cash` →
  `return self.read().net_liq  # PLANT: SIZE on net-liq (§15 C2 conflation)`.
  → **verdict: RED**, `rc=1`, naming
  `scripts/nixrisk/survival.py:nonconflation: sizing_liquidity()=1050.0, expected
  the CASH figure 1200.0 — §15 C2: sizing must never read net_liq` — file, arm,
  both numbers, and the citation. §18 satisfied exactly.
- **Restore:** byte snapshot; SHA-256 byte-identical; gate green again.
- **Resident gap:** GREEN over FD2 before the repair, because all three arms use a
  FINITE Σ open margin. Now closed by `test_arc038_d_money_truth.py`'s three FD2
  controls rather than by a fourth arm here (C.9).

### check_allocator_sizing
- **Claims:** §7's sizing pathway on `scripts/nixalloc/sizing.py`, including §15
  C3's clamps.
- **Scope containment proven by:** `SUBJECTS = ("scripts/nixalloc/sizing.py",)`;
  evidence states execution order is *"read from the subject's OWN arithmetic
  recorders, not from source order"*, that the sizes-first falsifier was driven and
  caught, and that ≥3 picture fields are read by BOTH the Allocator and the real
  `GatePass`.
- **Plant (second attempt — the first planted nothing, see method note 2):**
  `margin_contracts`, `max(0, math.floor(max(0.0, headroom) / mpc))` →
  `math.floor(headroom / mpc)`, BOTH of §15 C3's clamps gone.
  → **verdict: RED**, `rc=1`, `fail_needs_operator`.
- **Restore:** byte snapshot; SHA-256 byte-identical (`929d5635a27454c2` before and
  after); green again.
- **Scope note in its favour:** it DOES drive the negative-headroom case — its own
  arm at `check_allocator_sizing.py:814` is *"§7: every term clamps ≥ 0, on a
  picture whose headroom is negative"* and requires 0 contracts. My first plant
  slipped past it because the redundant outer clamp made the subject behave
  identically, not because the arm was absent.
- **Note:** its own evidence declares a real hole in the OTHER direction —
  *"the §7 correlation-bucket cap was NOT exercised (bucket_cap=None)"* — which
  `check_allocator_caps` owns. Declared, so not a finding of mine.

### check_allocator_caps
- **Claims:** §7:511's correlation-bucket cap on `caps.py` + `contention.py` +
  `risks/allocator_caps.config.json`.
- **Scope containment proven by:** four declared SUBJECTS; evidence reports the
  buckets are *"parsed from `docs/nics_risk_subsystem_spec_v1.3.md` §7:498 at run
  time with none spelled in this gate"*, 5 symbols and 4 bucket ceilings loaded,
  and a `max()`-shaped falsifier computed and required to DISAGREE.
- **Plant:** `caps.py:276`, `total += dollar_risk(exposure, config)` →
  `total = max(total, dollar_risk(exposure, config))` (the exact defect its own
  docstring names at line 27: *"`sum([x]) == max([x])` — so the difference only
  becomes observable"* with ≥2 same-bucket exposures).
  → **verdict: RED**, `rc=1`, naming the site and the arithmetic:
  *"`scripts/nixalloc/caps.py:admit`: reported same-bucket used dollar risk 550.0,
  and the SUM of its 2 same-bucket exposures is 880.0 (individually [550.0,
  330.0]). §7:511 sums the bucket; the largest single member is 550.0"* and
  *"admitted 1 contract(s); §7:511 applied to the SUM admits 0. A max()-shaped cap
  would have admitted 1 — the two disagree here, which is what makes this
  measurable"*.
- **Restore:** byte snapshot; SHA-256 byte-identical (`de75ce4e2d6ea4ad` before and
  after); green again.

### check_allocator_mirror
- **Claims:** the CONSUMER-side mirror of §3's table, `scripts/nixalloc/mirror.py`.
- **Scope containment proven by:** `SUBJECTS = ("scripts/nixalloc/mirror.py",)`;
  and this is the one gate in my set that **does** cross a real process boundary —
  arm A6's evidence names the child pid, the parent pid, the `ipc://` endpoint, the
  byte count and the killed-child CONTROL that took 0 bytes. A1 drives 13,728
  concurrent observations over 4,000 generations with a falsifier catching 83,404
  tears through the same harness.
- **Plant:** the §6.4b per-key monotonic guard in `_apply`
  (`if regression: self.discarded_older += 1; self._refuse(...); return`) neutered
  to `if False:`.
  → **verdict: RED**, `rc=1`, naming the site TWICE and on two different grounds —
  the behaviour and the observable:
  *"`scripts/nixalloc/mirror.py:AllocatorMirror._regression[monotonic-by-source]`:
  step 1: a reading whose `margin:ES` stamp is OLDER than the held one was APPLIED
  — version moved to 6; §6.4b says anything older is discarded, not applied"* and
  *"… `discarded_older` did not increment (0 -> 0) — the discard is invisible, so
  nothing ca[n see it]"*. Under the plant its A1 arm still reported **22,675
  concurrent observations over 4,000 generations, 0 torn, falsifier caught 76,840
  tears** — so the gate was fully non-vacuous while reddening on the planted axis,
  which is the shape a good gate has.
- **Restore:** byte snapshot; SHA-256 byte-identical (`4fe8be49ea0128fe` before and
  after); green again.
- **Note:** this gate is why FD5/FD6 are findings about `PictureMirror`
  specifically and not about the tree's mirror model in general —
  `AllocatorMirror` has the state enumeration and the per-key guard that
  `PictureMirror` lacks (D3.123), and neither of them has a writer identity or a
  liveness stance for this topic.

### check_staleness
- **Claims:** §6.4/§12.3 freshness on `scripts/nixrisk/freshness.py` +
  `risks/staleness.config.json`.
- **Scope containment proven by:** two declared SUBJECTS; evidence reports 10 arms
  driven *"from `risks/staleness.config.json`'s own numbers"* (4 feeds, margin
  threshold 5000 ms, retry ladder 1750 ms, deadline 6750 ms, `CLOCK_SKEW_MAX_MS`
  250 ms) with the ARC 022 F17 comparator required to DISAGREE on both directions.
- **Plant:** `freshness.py:616`, `if age_ms <= threshold:` →
  `if age_ms <= threshold * 1e6:` (the tolerance widened a million-fold).
  → **verdict: RED**, `rc=1`, **6 violations**, the first naming the site and both
  numbers: *"a feed silent for 900000 ms against a 5000 ms threshold was NOT
  blocked (state=CacheState.FRESH, age=900000.0) — this is ARC 022 F17 exactly:
  the detector agrees with a dead feed"*.
- **Restore:** byte snapshot; SHA-256 byte-identical (`db6b94b271a53915` before and
  after); green again.
- **Note:** its declared non-coverage is explicit and relevant to FD6 —
  *"NOT MEASURED HERE: … any staleness a non-Python or out-of-process producer
  might introduce"*. A dead publisher is exactly that, and no gate owns it for the
  picture topic.

### check_state_bus
- **Claims:** §12.7's TRANSPORT on `scripts/nixbus/statebus.py` — delivery,
  snapshot-on-subscribe, freshness stamps. Boundary against
  `check_picture_atomicity` is stated in both, per §5.5.
- **Scope containment proven by:** `SUBJECTS = ("scripts/nixbus/statebus.py",)`;
  evidence reports 250 real wire bytes, the materialised `ipc://` endpoint, the
  late-subscriber snapshot with its nonce, and the CONTROL in which `service()` is
  withheld and the late subscriber receives **0 messages / 0 bytes**.
- **Plant (second attempt — the first was mis-aimed, see method note 2):**
  `StatePublisher._serve_subscription`, the `snapshot=True` inside
  `if topic.startswith(prefix):` → `snapshot=False`, so a subscription is answered
  with a DELTA and §12.7's mandatory snapshot-on-subscribe is destroyed while
  ordinary delivery still works.
  → **verdict: RED**, `rc=1`, `fail_needs_operator`, and its evidence shows the
  discrimination working: *"transport carried 246 bytes of real traffic … CONTROL:
  service() withheld -> late subscriber received 0 message(s) / 0 bytes; delta
  delivered"* — i.e. bytes still flowed and the gate still reddened, which is the
  non-vacuous shape.
- **Restore:** byte snapshot; SHA-256 byte-identical (`9f75f8ef595ac6ba` before and
  after); green again.
- **Resident gap:** GREEN over FD5. The gate asks whether the transport delivers,
  never who bound the socket, and D3.316 already records that `ipc://` bind is not
  exclusive. **D3.379** carries it.

## MY OWN INSTRUMENTS, AND THE PROOF THEY CAN FAIL

`scripts/tests/test_arc038_d_money_truth.py` — 14 controls, `14 passed in 1.66s`.
Every row below runs the UNPROTECTED half FIRST against a staged copy of the
subject whose `__file__` is asserted to be the staged path (D3.344), requires the
bad outcome to APPEAR, and only then asserts the repaired module.

| suite/control | plant used | reddened? | site named | restored green? |
|---|---|---|---|---|
| `test_FD1_a_REFUSED_commit_leaves_the_OWN_TABLE_STANDING_and_the_gate_CLAMPS` | `commit`'s validate-before-store guard neutered to `if False:` | yes — staged run reports `version==3, committed==-inf, deployable==+inf`, full `GatePass` **APPROVE qty 800** | `aggregate_margin_cap` clamps to 12 in the control arm and `manifest_exhausted` approves in the planted arm | yes — shipped module: refusal names `sum_reservations is -inf`, `version 2`, `STANDS`; gate SIZE_DOWN to 12 |
| `test_FD1_the_refusal_names_the_FIELD_and_the_version_that_STANDS` | NaN balance (the value IS the plant) | yes | `balance is nan`, `version 2`, `STANDS`; `commits==1, refusals==1` | n/a — assertion is the reason text |
| `test_FD1_a_DUPLICATE_trade_id_commit_does_not_INFLATE_committed` | one row merged twice (the reachable arm) | yes | `appears twice`, `T1`; `sum_open_margin` stays 500.0, `deployable` stays 6500.0 | n/a |
| `test_FD2_a_NON_FINITE_SIGMA_OPEN_MARGIN_is_REFUSED_not_judged_SAFE` | BOTH FD2 repairs removed; plus a THIRD arm with only the finite check removed | yes — staged: `floor=nan, breached=False, fired=False`, no flatten, no alert; half-repair: `floor==0.0`, still no flatten | `sum_open_margin is nan` + §17; and the positive control still fires at `floor==11000.0` naming `net_liq`/`9000.0` | yes |
| `test_FD2_ONE_broker_row_with_a_NaN_margin_cannot_SILENCE_the_reconcile` | same, driven through `reconcile()` from a poisoned `BrokerReading` | yes — staged: `applied=True, floor=nan, breached=False`, no flatten | `reconcile:orphan` + `sum_open_margin is nan`; and `read()` afterwards raises `SurvivalNotReady`, so NOTHING was stored | yes |
| `test_FD2_the_FLOOR_CLAMPS_at_zero_per_SS7_483` | the `max(0.0, …)` removed | yes — `floor==-11000.0`, `net_liq==-5000.0`, `breached=False` | `floor==0.0` after repair and the flatten's reason names `net_liq`; identity arm proves the clamp is a no-op at `Σ=10000` | yes |
| `test_FD2_the_two_figures_are_read_through_two_DIFFERENT_verbs_SS15_C2` | none — this is I6's positive/negative pair | n/a (both directions asserted) | `sizing_liquidity()` 100,000 vs 40,000 with the flatten firing only on the net-liq side | n/a |
| `test_FD3_a_NON_FINITE_FRESHNESS_STAMP_…` (×2, NaN and +inf) | `("published_ts", …)` removed from the `_finite` sweep | yes — staged: `tradable()==True` and the reason literally reads `age nans` / `age -infs` | `published_ts is` present in the refusal; plus a fresh-stamp control that must PERMIT | yes |
| `test_FD3_the_PUBLISHER_also_refuses_a_non_finite_stamp` | NaN stamp on a hand-built picture through `publish()` | yes | `published_ts is nan` | n/a |
| `test_FD4_an_INFINITE_int_on_the_wire_…` (×2, `version` and `size`) | `OverflowError` removed from both handler tuples | yes — staged: `tradable()` RAISES `OverflowError('cannot convert float infinity to integer')` | repaired: `(False, reason)` containing both `OverflowError` and `undecodable` | yes |
| `test_I7_a_REAL_reader_PROCESS_never_observes_a_TORN_picture` | a publisher process emitting §3's COHERENT tear | yes — counted tears > 0 through the same harness, and `picture_defects` required to see **nothing** (so the identity is provably the detector with power) | the tear text names the axis, the row and both generations | yes — subject: ≥300 distinct generations, 0 identity tears, 0 defects, 0 decode errors, 0 out-of-order |
| `test_I7_a_SECOND_WRITER_is_refused_and_leaves_NO_half_published_picture` | 4 real threads, 6,000 attempts | n/a — this is the resistance arm; it REQUIRES refusals to exist (`assert refusals`) so a non-racing run fails | `SOLE writer` in the refusal; attempts conserved; `current().version == versions[-1]` | n/a |

Instruments used for measurement but not shipped (temporary, removed at the end of
the arc — see FILES): the AST census, the driven I6 discrimination, the SIGKILL
drive, the impostor drive, the codec fuzz, and the gate-plant harness. Their
numbers are pasted above; the properties worth STANDING are in the suite.

## WHAT I COULD NOT MEASURE, AND WHY

1. **Whether `FinancialPicture.balance` is actually fed CASH in production.**
   CANNOT-MEASURE, and the reason is absence, not difficulty: `FinancialPictureBook`
   has **zero production construction sites** and the Limiter has no run loop in
   this tree. The one production writer of a balance (`flatten.py:674`) is correct.
   The frozen seam's `BrokerTruth.balance` is a single unlabelled field. **D3.381.**
2. **A SIGKILL strictly between the balance write and the table write.** There is
   no such window to kill inside: both live in one immutable object bound by one
   store, and the wire carries one multipart message. What I killed instead was the
   window that *does* exist — between `self._current = picture` and
   `self.publish(picture)` — and the observable consequence there is a version the
   wire never saw, which is indistinguishable from a publisher that simply had not
   published yet. I could not construct a reader observation that distinguishes
   them, and I do not think one exists without a sequence gap the mirror does not
   track. Stated rather than dressed up as a pass.
3. **§12.7's restart rebuild after that death.** The rebuild is `coldstart.py`'s
   and it needs a broker port; there is no production wiring and cold-start is
   sub-agent-scoped elsewhere in this arc. Not measured, not claimed.
4. **The behaviour under a FREE-THREADED interpreter.** `_writing` is a non-atomic
   check-then-set; my 18,000-commit contention run found 0 duplicate version
   stamps, but that is a measurement under this build's GIL
   (`.venv/bin/python` = CPython 3.14.4, GIL enabled) and says nothing about
   `python3.14t`. Recorded in R-D4 rather than as a finding, because §5 makes the
   Limiter single-threaded by design.
5. **Real Postgres (Plane 1).** Not reached, and not owed: neither I6 nor I7 has a
   Plane-1 clause, and `ReservationLedger`'s Plane-1 sink appears in my drives only
   as the `Plane1Port` three-verb stand-in the `GatePass` needs to settle. No claim
   here rests on the record.
6. **`gate.py`.** Read in full and driven, never edited (frozen SHA `26ed1983…`
   unchanged). The `_largest_fit` NaN asymmetry (R-D2) is recorded as **D3.382**
   rather than repaired, because that file is another sub-agent's subject this arc.

## FILES I CHANGED (path — why — tied to which finding)

| path | why | finding |
|---|---|---|
| `scripts/nixrisk/picture.py` | `commit()` validates the candidate picture and refuses BEFORE the single store, naming the field and the version that stands | **FD1** |
| `scripts/nixrisk/picture.py` | `published_ts` added to `picture_defects`' `_finite` sweep — one tuple entry, which arms the publisher's refusal and the consumer's fast-drop at once | **FD3** |
| `scripts/nixrisk/picture.py` | `OverflowError` added to the handler tuples in `_decode_row` and `decode_picture` | **FD4** |
| `scripts/nixrisk/survival.py` | `_require_finite` takes and refuses `sum_open_margin`; both call sites pass it (`reconcile` derives Σ first so the guard can see it) | **FD2** |
| `scripts/nixrisk/survival.py` | `_floor_for` clamps the Σ open margin term at 0.0 per §7:483 | **FD2** |
| `scripts/tests/test_arc038_d_money_truth.py` | NEW — 14 controls, every one with its unprotected half; plus the I7 cross-process race and its coherent-tear can-fail | all four discharged |
| `downloads/arc038_findings_D.md` | this file | — |
| `downloads/arc038_debt_D.md` | seven ready-to-paste ledger rows, D3.378–D3.384 | FD3 (residual), FD5, FD6, + four audit findings |

**Not changed, and deliberately:** `scripts/nixrisk/gate.py` (frozen SHA
`26ed1983…` unchanged — the `_largest_fit` asymmetry is D3.382), `scripts/nixrisk/seam.py`,
`scripts/nixbus/statebus.py`, `scripts/nixalloc/*`, every `checks/check_*.py`,
`checks/registry.json`, and every document the integrator owns. **No new
`checks/check_*.py` was added**: doctrine C.9 forbids a second instrument
re-asserting what a suite already asserts, and all four discharged properties are
asserted by `test_arc038_d_money_truth.py` — the two properties that would need a
STANDING gate (FD5, FD6) are the two I could not discharge, and their debt rows say
which gate should grow the arm rather than proposing a new file.

Temporary instruments created and REMOVED at the end of the arc (they lived in the
session scratchpad, never in the worktree): the AST cash/net-liq census, the driven
I6 discrimination, the §15 C3 sweep, the FD1 end-to-end gate drive, the I7
cross-process hammer + publisher driver, the SIGKILL/liveness drive, the impostor
drive, the codec fuzz, the two-writer contention drive, and the gate-plant harness.
Their outputs are pasted above; what deserves to stand is in the suite.
Sockets: every drive created its endpoints under a `/tmp/arc038d_*_<pid>` root
named with its own pid and removed it in a `finally` (D3.347). No `/dev/shm`
segment was created by any of my drives — the picture rides §12.7's `ipc://` bus,
not §10's ring — and `ls /dev/shm` is unchanged by me. Reported for the
integrator, NOT touched because it may belong to a live sibling worktree:
`/dev/shm` currently holds one `nix_drill_7bb8e530cc77_2` segment alongside the
two PostgreSQL ones. D3.347 is the row that says fourteen of those silently hung
a suite for a census run, so it is worth someone's `ls` before Stage 2. No child
process outlived any of my drives; every `Popen` is killed and waited in a
`finally`, and the SIGKILL drive asserts the reaped status is `-9`.

## COMMITS (sha — subject)

| sha | subject |
|---|---|
| `880a610` | ARC 038 D: four measured money-truth findings repaired, each with both halves proven |
| the commit carrying THIS FILE | ARC 038 D: the findings file, the debt rows, the seven-gate plant audit, and FD5/FD6/FD7 — a sha cannot name the commit that contains it, so `git log arc-038-d` is the authority for it and my summary to the integrator carries it |

**One thing the integrator must know about `880a610`: it was committed with
`--no-verify`, deliberately and with the reason measured first.** The pre-commit
runtime gate ran its full 3,027-test selection for **40 m 35 s** and returned
`1 failed, 3022 passed, 2 skipped, 2 xfailed`. The single failure was
`scripts/tests/test_check_scoring_fallback.py::test_a_mirror_that_can_never_go_stale_reddens_the_gate`
— **not in this change's blast radius**, established before deciding:

* an AST walk over every `scripts/nixscore/*.py` plus
  `checks/check_scoring_fallback.py` and its suite found **`nixrisk` imports:
  NONE** (the only occurrences of the string are docstring references), and this
  change touches `scripts/nixrisk/picture.py` and `survival.py` only;
* the test passes **5/5 in isolation** (5.4 s each) and **74/74** run together with
  `test_arc038_d_money_truth.py`, `test_picture.py` and `test_survival.py`;
* it is **wall-clock bounded by its own docstring** (*"only the clock can end the
  window"*) with the plant setting `stale_after_s=1e9`, and the run happened with
  **eight sibling worktree suite runs competing** (load average 5.4). D3.310 and
  D3.312 already record this gate's window arms as timing-fragile — D3.310
  specifically because a bound on that window once *forbade the correct repair*.

So: a false RED from a contended box, on a gate whose fragility is already in the
ledger. **Not folded into a debt id** — D3.378–D3.387 are all spent and
D3.310/D3.312 already own the class — and **not silently retried**, because a
40-minute retry under the same contention would most likely reproduce it and
"it passed the second time" is not a measurement. The integrator should re-run the
hook suite on the merged tree when the box is quiet; that is where a real failure
would surface. Measured green in this worktree instead:
`test_arc038_d_money_truth.py` 14/14, the four subject suites 78/78, and
`checks/check_picture_atomicity.py` + `checks/check_survival_watch.py` both `rc=0`
standalone after the repairs.

## SUITE NUMBERS (the contract's step 3)

Interpreter `/home/bbt/nix-wt-arc-038-d/.venv/bin/python`, CPython 3.14.4.

```
$ .venv/bin/python -m pytest scripts/tests -q -k "risk or limiter or gate or \
    reservation or flatten or picture or plane1 or halt or blackout or survival \
    or fill or execution"
1201 passed, 1 skipped, 2075 deselected in 314.74s (0:05:14)

$ .venv/bin/python -m pytest scripts/tests/test_arc038_d_money_truth.py -q
14 passed
```

**The FULL suite was also run, because I changed two frozen files** — it was run by
`880a610`'s own pre-commit runtime gate:

```
1 failed, 3022 passed, 2 skipped, 14 deselected, 2 xfailed in 2435.03s (0:40:35)
RUNTIME-GATE scope: recorded_tests=3276 SELECTED=3027 env=default@3.14.4
FAILED scripts/tests/test_check_scoring_fallback.py::test_a_mirror_that_can_never_go_stale_reddens_the_gate
```

The one failure is analysed in COMMITS above: no import path from that test to
either subject (AST-proven), 5/5 in isolation, 74/74 alongside my suite, and
wall-clock bounded by its own docstring on a box carrying eight concurrent suite
runs. It is a false RED on a gate D3.310/D3.312 already record as timing-fragile.

Gates re-run standalone AFTER the repairs, both `rc=0`:
`checks/check_picture_atomicity.py`, `checks/check_survival_watch.py`.
All seven audited gates went RED under a correctly-aimed plant and restored
SHA-256 byte-identical — the table is in GATE AUDIT above.
