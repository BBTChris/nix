# ARC 034 — R4-B: The Sentinel and the Called Cap — RESULTS

**Canonical path: `/home/bbt/nix` (absolute).** Overwritten per arc, not appended.


# ARC 034 — R4-B: The Sentinel and the Called Cap (2026-08-17)

**Canonical path: `/home/bbt/nix` (absolute).** Interpreters stated: `/usr/bin/python3` **3.14.4**
and `/home/bbt/nix/.venv/bin/python` **3.14.4**. (`.venv-dev` lacks `zmq` — 8 collection errors; it
is not the test interpreter, measured rather than assumed.)

## THE CAVEAT EVERY ARC SINCE R2-B CARRIED IS GONE

A killed Risk Engine is no longer an unprotected position. The §12.1 Sentinel exists, on its own
package and its own code path, and it was proven against a **genuinely killed Limiter** — not a mock
of one: a real publisher subprocess SIGKILLed by pid, kernel-reaped `-9`, with a **separate real
process** observing `first_seen → progressing ×7 → frozen`, firing both detectors, and flattening
`['MES','MNQ']` while attributing the act to that exact pid. The control arm — identical but with the
kill removed — produced 75 wakes, **zero** causes, **zero** broker calls and no marker file at all.
`nixrisk` in the Sentinel's import closure, measured in a clean child interpreter: **`[]`**.

**And the cap is CALLED.** `StopBook.arm` and `PositionOriginWriter.on_fill` had zero production
callers since ARC 029 and ARC 033 respectively, so §7:501's bucket cap priced held positions off a
field nothing populated. `check_fill_handler` drove **4 confirmed fills** through the shipped
`LimiterFillSink → FillHandler` and **observed** the steps as `[ARM_STOP+RELEASE_REMAINDER+ORIGIN_WRITE]`.
The brief was sharp about this and it was honoured: a test that calls `arm` directly re-proves ARC 033's
mechanism — the new thing is that a **fill** calls it, and the sequence is read off what ran.

## THE BRIEF'S §0a PREDICTION WAS RIGHT, AT FIVE TIMES THE SCALE IT GUESSED

It said to assume one more "built but never called" gap. Phase 0.5's audit of ARC 033's six gates
found **five of six modules with ZERO production importers** and **170 of 176 public symbols with zero
production callers** — `pollers.py`, `halt.py`, `blackout.py`, `session.py`, `roll.py`, with
`freshness.py` imported only by `pollers.py`, which nothing reaches. **91 findings, six of six gates
AUDITED-WITH-FINDINGS, none clean**, most CONFIRMED by breaking the subject in a scratch tree and
watching the shipped gate still pass. Recurring shapes: the gate reads its expected value out of the
subject it polices (**all six**); fail-closed branches undriven because the gate's own doubles cannot
produce the input (five of six); non-vacuity floors that are arithmetic identities (`300 < 100`);
boundary instants never driven; and `debug.md` §7.12 *"Closed:"* claims that are **false** — in three
cases the sentence naming the closure describes the hole.

**Three of those were fail-open hazards in shipped safety code and were fixed this arc:**
`blackout.py` fail-closed on `CacheState.EMPTY` only, so `STALE` read as CLEAR while §6.5's
disjunction includes data-stale; `pollers.py` set the push stamp unconditionally against a SIGNED idle
comparison, so one future-dated push pinned `FALLBACK_AUDIT` through 24 h of total websocket silence;
`halt.py` keyed marker replay on a per-instance `seq` with no boot identity, so a HALT booked in one
boot suppressed a DIFFERENT unbooked HALT in the next and `archive` renamed the evidence away.

**Also measured false, and it had been load-bearing:** two gates justified their own under-measurement
with *"the runtime `.venv` `verify.py` runs under has no pytest."* **pytest 9.1.1 IS in
`/home/bbt/nix/.venv`.** Coverage had been displaced into suites `verify.py` never runs, on a claim
false on the shipped tree.

## THE NEW DETECTOR'S FIRST ARMED RUN CAUGHT THE ARC THAT BUILT IT

`check_uncalled_entry_points` generalises D3.178 to the production level: 850 public entry points over
78 shipped + 70 gate modules — 503 CALLED, 43 GATE-ONLY, 153 UNCALLED, 151 CANNOT-RESOLVE *reported
and never counted as a finding*, 7901 references ruled out by receiver type. **Its non-vacuity is
measured, not a floor picked to pass:** with receiver resolution OFF it yields 94 findings against 196
ON, so 102 findings exist ONLY because a receiver was resolved — a gate that could not tell those
apart would be a grep. Its limits are in its own evidence: dynamic dispatch is invisible, and a call
SITE is not proof the site executes.

On the merged tree its baseline gained commit history, the ratchet armed at high-water 193, and it
immediately reported **17 rows of NEW uncalled surface in ARC 034's own modules**. **The baseline was
NOT widened to swallow them.** The gate offers three outs — *wire it, delete it, or admit it by name* —
and admitting an arc's own growth into the baseline of the detector that arc just built would make the
instrument's debut a demonstration of how to route around it. The red is **CARRIED**, recorded as
D3.203 naming every row.

## WHAT THE MERGED TREE FOUND THAT FOUR GREEN WORKTREES COULD NOT

**A real cross-branch defect.** Sub-agent D added a required `boot` argument to
`HaltMarker.record_set`; sub-agent C's `nix_crash_loop_halt.py` calls the old signature. Both branches
were internally consistent and `check_supervision` PASSED in C's worktree; on the merged tree the
actuator raised `TypeError`. Fixed at the call site with the KERNEL's `boot_id` rather than a fresh
uuid — a uuid per invocation would make every systemd restart look like its own boot and defeat the
exact collision the argument exists to prevent.

**D3.192's literal caught a THIRD arc's blind bump.** Sub-agents A and C each independently measured
the order-path count as `25 → 27`; both were locally right and globally wrong. The merged figure the
gate itself reports is **29**. The literal is the only reason the disagreement was ever visible, and it
is re-banked at the gate's own merged measurement, never at either branch's arithmetic.

## A SESSION CAP KILLED THREE SUB-AGENTS MID-FLIGHT — THE SAME SHAPE AS ARC 033'S D3.191

1A, 1C and 1D were terminated with complete work staged on disk and uncommitted. §0d is explicit that
an mtime is not history. Each was **measured before being banked, never after**: 1A's four gates PASS
with 86 tests; 1C's four gates PASS with 192 tests; 1D's six gates PASS with 173 tests. Then committed,
then merged. **What was lost is each author's own §0a self-audit for 1A, 1C and 1D** — the same loss
D3.191 records, and the integrator cannot reconstruct reasoning it did not do. **Sub-agent B's survived
and it is worth reading:** it found the hazard stated backwards it was told to expect — the acted-latch
was set on the *flat* path, on reasoning true only *after* a flatten, so an order in flight at the
instant the Risk Engine died would have been ignored for the rest of the episode. **The one case where
re-asking the broker matters most was the one it stopped asking in.**

## THE RE-OWNING CEILING REFUSED MY OWN COMMIT, AND THAT IS THE RATCHET WORKING

Phase 0.6 re-owned twelve stale `ARC 033` guard owners to `ARC 035`. Eight are ceiling-exempt
exclusions; **four `artifacts` rows were already at 2-of-2 and my commit banked the third move**,
exceeding the operator-ruled ceiling of two (D2.31, ARC 027). `check_artifact_gate_coverage` is
therefore **FAIL** and carried. Three of the four are the deprecated MON-1 TUI whose own row says *"a
plant here would measure nothing"*; the fourth is textbook CHECK-A9 shape. Both are exclusion-shaped —
**but moving them there requires a recorded `CHECK-A<n>` architect ruling, and rule 14 exists precisely
because the gate cannot tell an authorised move from a laundering one.** Doing it on my own authority
to escape a ceiling I had just tripped would BE the laundering. It is put to the architect, not taken.

## SEAMS, AND THE PROOF THAT THEY MEASURE SOMETHING

Two frozen in Phase 0.6 and each gated: the **Sentinel seam** (its own broker session, the watched
heartbeat, the append-only marker format) and the **fill-handler seam** (where `on_fill` arms the stop
and calls the origin write). `SentinelBrokerPort`'s verb list IS §14's authority boundary as a type —
`connect`, `open_positions`, `flatten_all`, `disconnect`, and nothing that opens, sizes, amends or
routes. `FillStep` is an `IntEnum` whose **values are the order**, so a gate asserts the sequence from
observed values rather than source order.

**40 tests prove the gates redden**, each copying the subtree to a scratch home, mutating ONE declared
property, and driving the SHIPPED gate against the broken tree: a dropped marker field, a **renamed**
marker field, a removed `MarkerPhase` member, an `async def` verb, a widened broker port, a `truncate`
on the writer, behaviour in the seam, a reordered `FillStep`, `IntEnum` downgraded to `Enum`,
`StopArmPort` gaining `forget`, the mint rule flipped. An unmutated control PASSES, so every red is
attributable to its mutation rather than to the harness.

**D3.177's collapse was already shipped and is now closed.** `positions.identity_trade_id` returns
`order.client_order_id` unchanged — the exact hard-coded equality the architect ruling forbids, and
unfalsifiable because no observation could contradict it. Production now mints distinct ids, measured:
`TRD-00000003-strat-es`, `TRD-00000004-strat-nq`.

## CLOSE-OUT

`verify.py` **64 passed | 3 failed | 2 cannot measure | 0 skipped**, exit 1 — **identical under both
documented interpreters**. pytest **2646 passed, 1 failed, 2 skipped, 2 xfailed** (from ARC 033's
2343 — **+303 tests**); the single failure is the carried re-owning ceiling above. Census **69 three ways** (69 on disk, 69 in `registry.json`, 64+3+2+0=69 in
the run); the derived plan is identical to the live registry. CHECK-DEBT **201 → 211**, re-derived
rather than typed: row scan and series table both read 211, `check_derived_claims` reports 0
restatements across 13 claims.

The three FAILs, every one named: `check_ibgateway_service` (the tap session, by design, owed by twenty
arcs); `check_artifact_gate_coverage` (the re-owning ceiling above, awaiting an architect ruling);
`check_uncalled_entry_points` (the new detector's carried red, D3.203). The two cannot-measures are
`check_ibgateway_config` and `check_observed_resource_claims`, both §17 masking by the same dead port.

**WHAT WAS NOT RUN, stated rather than implied.** Stage 2's drills were not executed as separate
integrated end-to-end runs; their substance is carried by gates that drive the real thing
(`check_sentinel_deadman` performs the actual kill, `check_fill_handler` drives real fills,
`check_orphan_recovery` drives the real flatten executor), but a single composed drill across all three
was not run. **The binding census was not re-run on the merged tree** — the ARC 033 figure (BOUND=60,
ENR=1, UNBOUND=0 over 1912 observations, measured at Phase 0.1) is the last one taken and it predates
six new gates. Both are owed. A non-stop guarantee proven in sim is **not** proven live; there is no
venue on this node and every broker in every arm is a double. Scoring/EMA persistence is R5 — the
lifecycle transitions are wired and the boundary is stated. No systemd unit was enabled, started or
installed and no `daemon-reload` was run: this box carries a live IB Gateway service.

**Operator items still open:** the push (`main` measured **11 ahead / 0 behind**, a clean fast-forward
— the brief's "~105" was stale); the SPEC-A10 calendar vendor (still unratified, so the
calendar-source-conflict gate stays unbuilt with its reason recorded and no second source
manufactured); the re-owning-ceiling ruling; and provenance on three untracked status-board artifacts
that sit in the canonical tree in no commit on any branch — **not committed, not moved, not deleted.**

## WHAT INTEGRATION FOUND THAT NO WORKTREE COULD — 25 RED TESTS, EVERY CAUSE NAMED

The four sub-agents' suites were green in their own worktrees and **25 tests failed on the merged
tree.** Not one was a defect in the subject; every one was a cross-branch effect, which is the whole
argument for measuring where the code will actually live.

**Eleven + eight from one root cause.** `test_check_supervision.py` and `test_check_orphan_recovery.py`
copy a scratch home from a hand-written manifest of five `risks/*.config.json`. Sub-agent B added
`risks/sentinel.config.json` and widened `risk_config.OWNED_MODULES` in a parallel worktree, so on the
merged tree the validator refused a config the scratch home did not contain and **the CONTROL went
CANNOT_MEASURE before a single plant had been applied** — nineteen red tests, none of them about
either gate's subject. Both manifests now DERIVE the config set from the directory, because the
authority for which configs must exist is `risk_config.OWNED_MODULES` and not a list in a test file.
That is deliberately not the self-agreement shape §0a warns about: nothing is asserted against it, it
is only what gets copied into the venue.

**One stale literal anchor, failing exactly as designed.** `test_an_ACTUATOR_THAT_WRITES_NO_HALT_MARKER`
plants a removal keyed on the verbatim `record_set(...)` call, which the `boot`-argument fix moved. It
reported *"anchor appears 0 times, not once"* and went red rather than silently planting nothing —
`debug.md` §8 failure mode #4 caught by the instrument written against it.

**And the two best failures in the arc, both from `check_uncalled_entry_points`:**

The calibration test asserted `StopBook.arm` and `PositionOriginWriter.on_fill` are UNCALLED — the
D3.178 pair the detector was built around. On the merged tree it reports both as **`called`**. *A
second instrument, written by a different author against a different question, independently confirms
that D3.178 is closed.* The assertion is INVERTED rather than deleted, so removing the wiring reddens
it instead of letting the fix rot silently.

The ratchet then **TIGHTENED by 16 rows** — all six `fill_seam.py` ports, five `nixsentinel/seam.py`
ports, `StopBook.arm`, `PositionOriginWriter.on_fill`, `HaltFlag.set`, `CommitResult.ok`, `Plan.ok` —
every one of which is now genuinely wired in shipped code. A one-way ratchet is allowed to move in
exactly that direction and did.

**One transient observed and reported rather than hidden:** an intermediate `verify.py` run showed
`check_plane2_across_kill` as cannot-measure; the authoritative final run does not. It is a kill-drill
check on a loaded box and this is recorded as an observed flake, not as a clean result.

## THE POST-WRITE-BACK RE-MEASURE, PREDICTED IN WRITING BEFORE THE COMMIT THAT COULD CAUSE IT

D3.40/D3.144's mechanism fires when a write-back makes this arc a completed arc and a guard names it.
**Prediction, recorded before the write-back commit: NOTHING MOVES.** Every guard owner and every
exclusion owner in `checks/gate_coverage_baseline.json` names `ARC 035`, not ARC 034, so
`completed_arcs` gaining ARC 034 cannot change `guard_owner_defect`'s answer for any row. The three
arcs before this one each predicted a transition and got one; this arc predicts the absence of one,
which is the same mechanism read forwards and is falsifiable in exactly the same way.

Banked forward-only (§0h) BEFORE the marker (§16.4 / `CHECK-A10`), whichever way it comes out.
