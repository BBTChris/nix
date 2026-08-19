# RESULTS — ARC 038 · ULTRAREVIEW: Risk Engine / Limiter (pass 1)

**To:** claude.ai (project manager / architect) · **From:** `cc` · **2026-08-19**
**Canonical path:** `/home/bbt/nix` (absolute). **Module:** Risk Engine / Limiter (Core 2), FROZEN.
**Phase:** ULTRAREVIEW, the first one. **It built nothing.**

## THE BADGE VERDICT — the Limiter stays RED ✗

**Two of twelve invariants are proven clean: I6 and I10.** Twenty-one findings were discharged
inside the freeze, each with a control proven able to fail. **Thirteen block.** ULTRAREVIEW
findings may not be banked forward, so **ARC 039 is Limiter pass 2 on the same module** and
broker-order does not start.

The three that most change the picture, stated first because they are not code defects but
*absences*:

1. **§14's GO-timeout has no implementation.** A real child holding a GO was SIGKILLed and 11.0 s
   later — past `go_timeout_s=10` — the shipped `GatePass` still answered
   `deny | in_flight_lock | held by c-1`. §15 C6 records this deadlock as closed. On this tree
   the timer does not exist, and **nothing watches the Allocator**, the party §4:212 names.
2. **`ctx.nix_home` is a dead input for 13 of 73 gates**, eight Limiter or adjacent. A gate printed
   `pass:` at exit 0 with 40,132 wire bytes of evidence over a `picture.py` that does not parse.
   ARC 037's staged-tree defect was an environment variable; this one needs none, so `env=` closes
   nothing.
3. **The cap reads no stop distance at all** — `stop_ticks` 1 → 1,000,000 gives an identical
   result — and **nothing in production constructs a `GatePass`, `HaltFlag`, `BlackoutEvaluator`,
   `ProtectiveFlatten`, `FinancialPictureBook`, `StopBook`, `FillHandler` or
   `PositionOriginWriter`.** There is no Limiter process. Every invariant proven here is proven
   about a **library**, not about a running daemon, and that is the honest frame for all of it.

**What the audit proved POSITIVELY, and it is not small.** The exit path really has zero wire
dependency: with the `ipc://` peer SIGKILLed, Postgres at a dead socket failing ten concurrent
group commits, and `/dev/shm` unlinked — all at once — the flatten still fired at the broker seam
in **0.05–0.25 ms**. The §15 C1 double-spend race held across **4,000 real-thread iterations**.
The financial picture never tore across **18,481 generations** over a real process boundary.
"Open" never read true on a placement ack across **all seven** state surfaces. The hot path did
**zero** file/socket/subprocess operations across 2,000 real gate evaluations, and **zero** EMA
computations across 20,000 cache misses.

---

## ARC 038 — ULTRAREVIEW: Risk Engine / Limiter (pass 1) — 2026-08-19

**The first ULTRAREVIEW arc. It built nothing.** Canonical path `/home/bbt/nix` (absolute).
Interpreter `/home/bbt/nix/.venv/bin/python`, CPython 3.14.4. HEAD `f059ea4` -> this arc's tip.
19 stages, echoed at kickoff. Phase 0 serial · Stage 1 seven parallel adversarial sub-agents
from their own worktree + index + venv · Stage 2 serial reconcile + merged-tree re-audit ·
Stage 3 convergence · Phase 4 close-out.

### BADGE VERDICT: the Limiter stays RED

Two of twelve invariants are proven clean — **I6** (survival on net-liq, sizing on cash) and
**I10** (the two-phase gate). Twenty-one findings were discharged inside the freeze, each with a
control proven able to fail. **Thirteen block, and ULTRAREVIEW findings may not be banked
forward** — that is the whole difference from a build arc. ARC 039 is Limiter pass 2 on the same
module. Broker-order does not start.

### Phase 0 — the baseline held on all four figures

`verify.py` 87/2/2/0/1 exit 1 · full pytest 3258 passed, 3 skipped, 2 xfailed · census 92/92 ·
CHECK-DEBT 309. **No delta.** The freeze recorded the SHAs of all 30 `scripts/nixrisk/*.py`
plus 28 adjacent gates/configs.

A figure worth correcting rather than repeating: a raw row count of `CHECK-DEBT.md` gives 379,
not 309, because the ledger's number is **open** debts derived by
`independent_claims.check_debt_open_items`. The raw count was the wrong instrument, not a delta.

### Stage 1 — seven attacks, 44 findings

**I1 — nothing reaches broker-order without the Limiter.** Exit half RESISTED, entry half
**CANNOT-MEASURE: it has no subject.** A whole-tree enumeration (274 files parsed, 0 skipped)
found 84 call sites to a mutating order verb — 74 tests, 4 in `scripts/broker/`, 6 in
`scripts/nixrisk/`, zero elsewhere, zero `getattr` reaches — and **no `place_order` in
`scripts/nixrisk/` at all.** No instrument in the tree claims I1. FA-5/D3.352.

**I2 — exactly one terminal release.** The §15 C1 double-spend race **held across 4,000
real-thread iterations**, zero arithmetic violations; partial fills, partial sequences,
over-fills, a late reject after a timeout, identity collisions and a real SIGKILL mid-transition
all resisted. But a real `Plane1Wal` under real `RLIMIT_FSIZE`/EFBIG (errno 27), driven through
the real `GatePass`, **committed 12,000.0 of margin against three DENIED orders** with `audit()`
reporting `drift=0.0 material=False` throughout — no terminal event can ever arrive for an order
that was never placed. Repaired `_book`-local; 12,000.0 -> 0.0. And `CANCEL`, `REJECT`,
`PENDING_TIMEOUT` have **zero production release sites**: a 0-of-5 IOC entry leaks 6,172.5 with
`drift=0.0`. D3.51's stated justification — that those handlers "do not exist" — is now false;
three do.

**I3 — the exit path has zero wire dependency.** RESISTED under total deprivation: the `ipc://`
peer SIGKILLed (reaped `-9`) and the socket closed, Postgres at a dead Unix socket with 10
concurrent group-commit failures, `/dev/shm` unlinked — separately **and all at once** — and the
flatten was **observed at the broker seam every arm in 0.05–0.25 ms**. The *delivery* dependency
was real: a disk-critical WAL **aborted the protective flatten**, 1 of 3 positions flattened with
two left OPEN at the broker, and the onset sweep cancelled 1 of 3. Fixed to record instead of
propagate — and a **second abort source was found only by re-measuring after the fix**.

**I4 — open = confirmed fill only.** RESISTED: a placement ack with a reservation and a working
order left **all seven** state surfaces empty; all seven moved on a real fill. The converse is
the danger and it blocks: a fill the ledger ingested but whose origin write was refused leaves
§3's table **and the real Allocator mirror reading FLAT over a 2-lot position** — no escalation
record, no Plane-1 trace — so §7:501 prices held exposure at zero and **the cap admits more**.
FC4/D3.372.

**I5 — one in-flight per strategy, never wedges. §14's GO-timeout HAS NO IMPLEMENTATION.**
A real child holding a GO was SIGKILLed (`rc=-9`, `/proc` gone); **11.0 s later, past
`go_timeout_s=10`, the shipped `GatePass` still answered `deny | in_flight_lock | held by c-1`**.
An AST census found exactly one site that clears `in_flight` — inside `force_deregister`, which
destroys the registration, so there is no normal-resolution release either — and **no shipped
site that measures elapsed time against the knob.** §15 C6 says this deadlock was closed; on
this tree the timer does not exist. FF1/D3.398. Separately, the recovery spine that does exist
has **no shipped caller**, and **nothing in the tree watches the Allocator**, which is the party
§4:212 names. FF5/D3.405.

**I6 — survival on net-liq, sizing on cash. CLEAN.** An AST census of all 119 cash-like and
net-liq-like reads, then driven with cash 100,000 / net-liq 40,000 **and the inverse, with the
floor between them**: every sizing output moved with cash, every survival verdict with net-liq,
each invariant to the other. One violation, discharged: `_require_finite` guarded cash and
net-liq but **not the Σ open margin the floor is built from**, so one broker row with
`margin=nan` gave `flattens=0 criticals=0`. The clamp and the guard are **coupled, and the
coupling was measured** — the clamp alone floors at 0.0 and still never fires.

**I7 — the atomic financial picture.** Atomicity itself RESISTED: **18,481 distinct generations**
published by a real publisher PROCESS over a real `ipc://` socket, 15.7 MB on the wire, **zero
tears**, and 4 real writer threads over 6,000 attempts produced 7,768 `ConcurrentWriter` refusals
with zero torn reads and zero duplicate versions. The module's money truth breaks everywhere
else. `commit()` stored `_current` **before** `publish()` validated, so a **refusal mutated what
it refused** and the poisoned table drove the full §3 gate pass to APPROVE 800 contracts /
$400,000 on a $10,000 account (discharged). `published_ts` — §12.7's own freshness stamp — was
the one field never validated: NaN made `tradable()` True forever, reason reading `age nans`
(discharged). `OverflowError` is not a `ValueError`, so a verb documented *"Never raises"* raised
(discharged). Blocking: **no writer identity** on `tbl.financial_picture` — a second process
rebinding the same `ipc://` after the real writer died injected balance 10,000 -> 10,000,000,
accepted fresh and self-consistent, while `nixscore`'s *ranking* table (which §6.6 says must
never gate safety) **has** that check; the mirror keys freshness on **age alone**, granting
**22,356 `tradable()` permissions over 0.477 s from a SIGKILLed writer**; and §12.7's restart
rebuild reaches no connected consumer — **60/60** snapshots dropped as out-of-order, with the
mirror still asserting an OPEN position that §14's *restart = flat* denies.

**I8 — the Limiter is the sole Plane-1 writer. It is a convention, not an enforcement.**
Append-only is enforced on `nix_limiter` while everything connects to the live `nix_plane1` as
**the log's owner and a superuser**: INSERT, UPDATE, DELETE and TRUNCATE were all accepted
against the real money record. **No SQL fixes a superuser.** Five non-Limiter processes each
landed a row with `Plane1Wal` never constructed. `wal_seq` is **not unique (`0,0,1,1,2,2`), not
faithful (record 4 -> seq 8), not gapless (4,5,6,7 missing, zero actual loss) — and nothing
detects any of it.** Discharged: `natural_key_for` hashed the row it was handed while
`GroupCommitWriter` always feeds it one through `decode_record`, so **the same event landed twice
in real Postgres**; the first repair hand-copied the coercions and `check_plane1_sole_writer`'s
own controls caught it.

**I9 — hot path = cache reads and arithmetic only. CLEAN as a property; its gate is not.**
2,000 real gate evaluations under a PEP-578 audit-hook census across three port configurations:
**zero events**. 20,000 ranking-table cache **misses**: zero EMA calls, 81 ns/read. But
`check_plane1_hot_path` times a `GatePass` with `ledger=None`, so the only I/O the approve path
performs is **outside every timed region**: with the real ledger and real WAL, p50 34.3 µs /
p99 38.4 / **max 1169.8 µs**, and `strace -c` counted **4,202 `write(2)` for 4,200 approvals**
(`Plane1Wal` is `buffering=0` by design).

**I10 — two-phase ordering. CLEAN.** `RulePort.phase` was a property read three times and each
read trusted alone, so a rule answering a valid but *different* `Phase` on successive reads was
either dropped from both partitions — 9 dispatched from a 10-rule manifest, an always-DENYING
rule never ran, and **the pass APPROVED and took the reservation** — or placed in both, 11 names
in `evaluated` for 10 rules, one rule dispatched twice inside §3's single pass. Discharged.
Separately the gate **never validated the proposal**: `qty=0` and `qty=-5` were APPROVED, and a
negative quantity makes `proposed_margin` negative, so every Phase-B rule gets *easier*.

**I11 — onset cancels pending entries, exits untouched.** A **BLACKOUT onset released the
reservation and never cancelled the order**, which then **FILLED inside the window** for ES +2
while Σ reservations already read 0.0: §15 C4 and §3:172 are one sentence, and the HALT half was
wired while the blackout half was not, with **no CHECK-DEBT row owning the gap**. And one refused
cancel **aborted the whole sweep**: three entries with `cancel_order` raising
`BrokerNotConnected` on the second — what both shipped adapters raise when the session is down,
and a dead session is itself a *cause* of the HALT — left entries two and three live, **zero
`halt_set` Plane-1 rows** where §12.10:753 owes one, and both survivors filled inside the HALT
for ES +4. Both discharged. Blocking: a sweep reaching an already-FILLED entry releases under
the ONSET cause, so `committed` drops by a real position's margin and §9's row names the wrong
terminal path — **§14's exactly-one-release holds, which is why no gate saw it.**

**I12 — the cap is fed by real values. CANNOT-MEASURE at the top, and the reason is the finding.**
**The cap reads no distance at all**: `stop_ticks` 1 -> 1,000,000 produced an identical result.
`agg_margin_cap_pct`'s only reader is its own validator; nothing constructs `StopBook`,
`FillHandler` or `PositionOriginWriter`; there is no `NetLiqMarkPort` implementation. Every
poison the cap *can* see is now refused: `margin_per_contract` of 0.0 or -1000.0 made the whole
two-phase pass **APPROVE 100 contracts**; a `(NaN, True)` net-liq mark **cleared** §6.5's
survival floor; `pad=NaN` passed boot and turned the floor off at every size. All discharged.
Twelve poisoned stop distances into `StopBook.arm` produced twelve refusals, and the `fresh`
flag is proven not discarded — one production call site, and it short-circuits.

### §0a — the audit instrument, audited. This is the arc's largest finding.

**`ctx.nix_home` is a DEAD INPUT for 13 of 73 gates**, eight of them Limiter or adjacent. Sites:
`check_picture_atomicity.py:1206` (`run()` never reads `ctx`) and `:273`;
`check_plane1_hot_path.py:290` is literally `del ctx`. Proven the way D3.344 was proven — one
staged, planted tree driven twice, changing only `PYTHONPATH`: **the gate printed `pass:` at exit
0, with 40,132 wire bytes of evidence, over a `picture.py` that does not parse.** ARC 037's
defect was an inherited environment variable and its repair was to name the child's environment;
**FG1 needs no environment variable at all**, so `env=` closes nothing. One gate repaired; twelve
remain. D3.408.

**And it closes the class D3.344 left open** rather than finding a third victim: 179 spawn sites
enumerated, 52 inheriting, **26 suites driven twice under both environments — all identical.**
There is no third env-defeated staged runner; the class re-points at FG1.

Three more instrument findings: a live second Plane-1 writer reported `CANNOT_MEASURE` whenever
Postgres was unreachable, so the same violation reached exit 1 or exit 2 depending on the DB
(discharged — it now FAILs and names the arm that did not run); `check_picture_atomicity` is
**not vacuous but scoped past** four resident defects, because no arm ever drives a *refused*
commit so `refusals` reads 0 every run (D3.384); and `check_plane1_degraded`'s C2 arm ends at
`StopBook.breached()`, pure arithmetic that cannot fail for a disk reason, so a planted exit
awaiting its Plane-1 record left it **and** `check_flatten` green with 93/93 tests passing
(D3.373).

### Stage 2 — the merged tree, for the fourth arc running

Two collision paths, and they failed differently. **`flatten.py` conflicted loudly**: A and C had
each found the onset sweep abortable and each guarded the call *it* had measured — A the broker's
`cancel_order`, C the ledger's `resolve`. Either fix alone leaves the other source unguarded, so
both guards stay, with their two *different* safe residuals: a refused cancel keeps its margin
committed, a lost release row does not un-release capital. **The integrator's first union was
wrong** — it left A's unguarded `resolve` in front of C's guarded one, calling `resolve` twice
per entry: a double release, in the module whose invariant is exactly-one-terminal-release. Found
by reading the merged loop, not by counting conflict markers.

**`gate.py` auto-merged with no conflict and was still wrong** — and this time the successor's own
control went RED instead of staying green. A and E had both fixed §15 C3's "missing margin ⇒
not-tradable", A on the pre-gate and E inside the phase-B rules, and on the merged tree they
**partition the offending values**: A's clause is `not isfinite(mpc) or mpc < 0.0`, so `0.0`
still reaches the cap while `-1000.0`/NaN/inf never get that far. Resolved by keeping both layers
and re-pointing the control at the merged pathway, plus a new arm that neutralises **each guard
alone** and requires the values the other does not cover to leak — so a future merge that
silently drops one fix fails there instead of passing the protected half.

Widening that control's non-vacuity set to all four values was the integrator's error and it
failed loudly: unguarded, `nan` raises inside `int(room // mpc)` and `inf` yields a bare
`0 contracts fit`, so neither is a principled §15 C3 deny — now pinned by its own arm, because a
deny for the wrong reason is rule 11's subject.

**Full suite on the merged tree, quiet box: 3367 passed, 3 skipped, 2 xfailed, zero failures.**
That also settles the two load-sensitive reds D and E carried — `check_scoring_fallback` and
`check_ranking_table` both pass at load 0.4 — in favour of F's root cause: **not load in general
but the GIL handoff cadence.** At `setswitchinterval(0.05)` 3 of 6 drill runs fell below the
overlap floor; pinned at 0.001 by measurement (0.0005 rejected because its p99 hit 102.2 µs
against the gate's ~100 µs bound), taking max from ~5,200 µs to 1,161–1,421 µs. **D3.346
discharged.** All 18 Limiter gates rc=0 on the merged tree; all 109 new audit controls pass.

### Stage 3 — convergence

`--optimize` derived a plan **identical to the live registry**, which is the correct outcome and
not a null one: this arc added **zero** new `checks/check_*.py`. Every repair pointed an
**existing** gate at the gap it was missing, because doctrine C.9 forbids a second instrument
re-asserting a property an existing suite owns. Census **92 on disk / 92 in the registry / plan
identical**.

The observer sweep took the **modified** population as its subject — a modified gate can acquire
an undeclared claim exactly as a new one can — across three orders × two sweeps × both documented
launch modes on a cold bytecode cache: **84 observations, 240 claim events, no undeclared claim
anywhere.** Four of the seven produced **zero** claims, so their declarations are unfalsified
rather than confirmed; D3.341 recorded that for one gate and excused it as "genuinely touches
little", and that reasoning does not transfer to a gate building a full `GatePass` over the real
manifest. The blind spot covers the four instruments guarding I2, I4 and I10 (D3.416).

**The sweep's own first instrument was wrong**, and it is recorded rather than quietly fixed: a
hand-rolled `ast.Assign` walk read EMPTY for all seven gates — every one spells it
`RESOURCES: tuple[str, ...] = (...)`, an `ast.AnnAssign` — and manufactured 30+ "undeclared"
findings against gates that declare correctly. Repaired by using
`nixverify.declarations.read_all`, the reader the gate under audit uses. The same repair
sub-agent F took after `check_git_env_scrub` caught it hand-rolling a `GIT_*` scrub.

**Binding census: `BOUND=79` over 2,491 observations**, ARC 037's floor held exactly. Five of the
seven modified gates are BOUND. The two that are not — `check_plane1_hot_path` (PASS:11, not one
red) and `check_plane1_sole_writer` (CANNOT_MEASURE:1, PASS:12) — **are the instruments for I9
and I8**, the two invariants this audit found weakest from an entirely different direction. Two
instruments pointing at one gap from opposite ends. And the census adds the shape: **seven of the
thirteen EXERCISED-NEVER-RED gates are the Plane-1 family**, so this is not two gates with an
idiom problem but the whole family sharing one, over the durable money record (D3.418).

### What the tree's own gates caught, in this arc, from its own agents

`check_git_env_scrub` failed F's first commit for hand-rolling a `GIT_*` scrub.
`check_uncalled_entry_points` refused B's new accessor because it moved **another module's**
baseline entry, and refused C's for the same class. `test_check_flatten`'s plant anchor reddened
rather than planting nothing when C's `try:` shifted an indent. `check_plane1_sole_writer`'s own
controls caught E's first repair. And G's first repair turned **sixteen committed plants into
CANNOT_MEASURE** — D3.344's too-broad-repair shape, caught by G's own census. None of these were
worked around.

### What did NOT land, said plainly

**Nothing in production constructs a `GatePass`, `HaltFlag`, `BlackoutEvaluator`,
`ProtectiveFlatten`, `FinancialPictureBook`, `StopBook`, `FillHandler` or `PositionOriginWriter`.**
There is no Limiter process, so every hot-path figure is the library as a caller drives it, and
every invariant proven here is proven about a library rather than about a running daemon. §14's
GO-timeout does not exist. Nothing watches the Allocator. The cap reads no stop distance. Plane-1
sole-writership rests on the connecting role being a superuser. The tap session is still the only
code-independent FAIL. Live venue untested by design.

### Close-out

`verify.py` on trunk under `/home/bbt/nix/.venv/bin/python` (CPython 3.14.4):
**87 passed | 2 failed | 2 cannot measure | 0 skipped | 1 guarded, exit 1** — byte-identical to
the Phase-0 baseline. The two FAILs are the standing ones (`check_ibgateway_service`, the tap
session and the only code-independent one; `check_uncalled_entry_points`, its standing state);
both cannot-measures are the same dead gateway at 127.0.0.1:4002, one of them
`check_observed_resource_claims` correctly refusing to certify past an unreachable subject
(§17/rule 10). **No further FAILURE and no non-pass whose cause is unnamed.**
GUARDED: `check_artifact_gate_coverage`, owner **ARC 039** — re-pointed before the write-back,
the sixth consecutive arc to make that move and now a nine-arc chain; it is not a fix, and this
arc's addition to the record is that **both its ratchet arms were driven to RED on the real tree
and back**, so "GUARDED, unchanged" is now a claim about an instrument proven able to fail in
both directions.

CHECK-DEBT **309 -> 371 (+62)**, re-derived whole by
`independent_claims.check_debt_open_items` over the merged tree and cross-derived by
`check_derived_claims` from the rows **and** the Series row (13/13 claims, exit 0). **Nothing was
discharged as a row**, which is the shape worth reading: 21 findings were fixed with both halves
proven and each one's *residual* got the row, so a falling count would have meant the audit
stopped short.

Ten of the 30 frozen Limiter files moved, each tied to a named finding; the other twenty are
byte-identical to their recorded SHAs. Zero id collisions and zero conflicts in
`CHECK-DEBT.md` across seven parallel branches, against three struck-through branch-local Series
rows last arc.

**ARC 039 must discharge, before the badge can flip:** FF1 (§14's GO-timeout has no
implementation) · FG1 (`ctx.nix_home` dead in 12 remaining gates) · FA-5 (I1 has no instrument
and no subject) · FA-6 (onset release on a filled entry) · F-B3/B4/B5/B7 (three unwired terminal
paths; `material` on float noise; a bare `KeyError` aborting the sweep; no taken-vs-released
pairing) · FC4 (a refused origin write leaves the table and mirror FLAT) · FD5/FD6/FD7 (no writer
identity; age-only freshness; the restart rebuild) · FE1/FE2/FE3 (superuser append-only; five
non-Limiter writers; `wal_seq`) · FE6 (the cap reads no distance) · FE10 (`breached(NaN)`) ·
FF4/FG4 (the hot-path gate's coverage and its unexecuted verdict assembly) · FG6 (the §12.1
replay ordering).

### Post-write-back re-measure (ARC 038), banked BEFORE the marker

D3.417's prediction, stated before `sessions/SESSION.md` named this arc complete.

`sessions/SESSION.md` now names ARC 038 complete, so the D3.40/D3.144 guard-owner transition is
**live, not hypothetical**: `nixverify.contract.completed_arcs` returns a set that **includes 38**,
put there by this arc's own summary — the condition D3.417 was written to be falsified by.

**The prediction held in both halves:**

| | predicted (banked first) | measured after |
|---|---|---|
| `check_artifact_gate_coverage` | GUARDED, unchanged, 120 / 119 / 8 | **guarded (exit 3), 120 tracked / 119 declared / 8 uncovered** |
| `verify.py` | byte-for-byte the pre-write-back figure | **87 passed / 2 failed / 2 cannot measure / 0 skipped / 1 guarded, exit 1** |

The guard survived because the eight CHECK-A8/CHECK-A9 exclusions were re-pointed ARC 038 → ARC 039
*before* the write-back. Had they been left naming ARC 038, this re-measure would have read
GUARDED → CANNOT_MEASURE and the guarded count would have gone 1 → 0. **A re-measure taken after
the fact and then described is not a test of anything**, which is why the row was banked first.

What this arc adds beyond ARC 037's identical row: sub-agent G drove **both** ratchet arms of that
gate to RED on the real tree and back to green, so "GUARDED, unchanged" is now a statement about an
instrument **proven able to fail in both directions** rather than one assumed to be. G's own restore
failed the first time and was caught only by `sha256`, because `git checkout --` restores from the
**index** — the same lesson the abandoned `capture.py` plant (D3.419) taught the integrator four
hours later.
