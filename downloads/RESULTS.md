# ARC 032 — R3-B: The Widened Picture, the Closed Cap, and Recovery Reflection

**Canonical path:** `/home/bbt/nix` (absolute, unmoved). Nothing was relocated.
**Not pushed.** `origin/main` is where ARC 031 left it; the push is the operator's.

---

## 0.1 — BASELINE, AND EVERY FIGURE NAMES ITS INTERPRETER

D3.140 made the baseline interpreter-dependent, so a tally that does not say which launch mode it
was taken under is under-specified. Both were run on trunk at `d1525ba`, same tree, same commit:

| launch mode | resolved `sys.executable` | verify.py |
|---|---|---|
| venv | `/home/bbt/nix/.venv/bin/python` | `47 passed \| 1 failed \| 2 cannot measure \| 0 skipped \| 1 guarded` · exit 1 |
| system | `/usr/bin/python3` | `47 passed \| 2 failed \| 1 cannot measure \| 0 skipped \| 1 guarded` · exit 1 |

51 checks in both. The single cell that moves is `check_observed_resource_claims`: **FAIL** under the
system interpreter (naming `check_extract_sources:subprocess:/usr/bin/python3` verbatim),
**CANNOT_MEASURE** under the venv. That is D3.140 and nothing else.

```
pytest scripts/tests   →  1858 passed, 2 skipped, 2 xfailed   (0:11:12)   exit 0
claims harness         →  green, 13/13 claims + 2/2 demonstrations re-executed
CHECK-DEBT             →  172   (derived:ledger_rows=172, stated:series_table_latest_row=172)
```

Every figure the brief predicted, reproduced. **No delta beyond the interpreter split.**

**One figure the brief predicted that MEASURED DIFFERENTLY, and the cause is this arc's own hand.**
The binding census on trunk read **BOUND=50, EXERCISED-NEVER-RED=1, UNBOUND=0** over 1,249
observations — not 49/2/0. The moved row is `check_untracked_attribution`, and it moved because the
census ran while `docs/BRANCH-PROTECTION-PROPOSAL.md` sat uncommitted in the canonical tree: the gate
correctly reddened on *"work exists in the canonical tree that no commit on any branch contains"*,
and a red is what BINDS a check. **That is not a discharge of D3.139.** D3.139's finding is that the
gate's can-fail suite drives `gate.evaluate(...)` and never `gate.run(...)`, so the tracer cannot see
the reds the suite already proves. An incidental real red does not repair an instrument gap; it
disguises one. The row stays open and the figure is reported with its cause rather than as a delta.

**A baseline the brief did not name, and it is red: `pre-commit run --all-files`.** Measured against
the *pristine* `d1525ba` bytes of the three files in question, checked out into a scratch tree so the
measurement could not be contaminated by this arc:

```
ruff check --no-fix scripts/{harness,monitor,pty_test}.py   →  Found 75 errors
ruff format --check scripts/{harness,monitor,pty_test}.py   →  3 files would be reformatted
```

`pre-commit run --all-files` was already failing on trunk before ARC 032 existed, on three files this
arc does not own. **NOT FIXED, deliberately:** they are untested dev scripts — that is precisely why
all three sit in `check_artifact_gate_coverage`'s ceiling-guarded bucket — so a lint rewrite is a
change I could not verify, on files outside this arc's scope. Owned as a debt row instead. The
per-commit hook path, which is file-scoped to what is staged, passed on **every** commit this arc
made, including the full Stage-3 runtime pass each time.

---

## 0.2 / 0.3 / 0.4 — THE THREE BLOCKING ITEMS

### 0.3 — BRANCH PROTECTION: THE BRIEF'S PREMISE IS STATED BACKWARDS

Five read-only `gh api` GETs. **Nothing was written to GitHub.**

```
gh api repos/BBTChris/nix/rulesets                                  →  []
gh api repos/BBTChris/nix/branches/main/protection/required_status_checks
                                                                    →  404 "not enabled"
gh api repos/BBTChris/nix/actions/workflows                         →  {"total_count":0,...}
gh api repos/BBTChris/nix/commits/main/check-runs                   →  {"total_count":0,...}
gh api repos/BBTChris/nix/branches/main/protection
    required_pull_request_reviews.required_approving_review_count   →  0
    required_pull_request_reviews.require_last_push_approval        →  false
    required_pull_request_reviews.require_code_owner_reviews        →  false
    enforce_admins.enabled                                          →  false
    allow_force_pushes.enabled / allow_deletions.enabled            →  false / false
```

**Configured, and bypassable — the bypass is exactly one field, `enforce_admins: false`.** It is
CLASSIC branch protection, not a ruleset; `rulesets` is empty.

**And the deadlock the ruling exists to dissolve is not the deadlock that is configured.** The brief
describes *"PR-only + sole maintainer + self-approval-forbidden strands every PR"*.
`required_approving_review_count` is **0**. No approval is required by anyone for any PR on `main`.
**A PR opened today can be merged by its own author with zero reviews.** There is no human review to
replace. The ruling is still right — a PR rule everything bypasses is dishonest state either way —
but what it actually does here is ADD a gate where none exists and CLOSE an admin bypass, which is
the opposite of its written rationale. Adopting it on the written argument would mean believing the
config forbids something it permits.

**THE PREREQUISITE IS A HARD BLOCK, NOT A CAVEAT.** Zero workflows and zero check runs exist in this
repository's entire history. A required status-check context that never reports leaves the PR at
*"Expected — waiting for status to be reported"* **permanently**, and the same edit sets
`enforce_admins: true`, removing the only escape. Applied before CI exists, the replacement rule
**reintroduces the ARC 019 deadlock from the other side, for every PR, with the hatch nailed shut.**

A second half that is not obvious: `verify.py`'s honest exit code on this tree is **1**, and several
checks are NODE-scoped (`check_node_identity` reads a gitignored file holding this box's hardware
UUID; `check_reserved_cores`, `check_core_map`, `check_price_ring`, `check_capture_plane2`,
`check_plane2_across_kill` have subjects a cloud runner does not have). **`verify.py` is not
straightforwardly a CI job at all**, and deciding which checks gate a merge is an architect's call,
not a workflow author's.

**Delivered, not applied:** `docs/BRANCH-PROTECTION-PROPOSAL.md` carries the measured state, the
recommended ruleset JSON (one `gh api -X POST --input`), the classic-protection alternative, the
rollback for both, a per-field table of why each value is what it is, and the drafted CI workflow
with its gaps named. **`cc` produced it; the operator clicks.** Owned as **D3.141**.
### 0.4 — THE WIDENED SEAM, AND THE INSTRUCTION THAT COULD NOT BE FOLLOWED AS WRITTEN

`nixrisk.seam.PositionRow` gains **`stop_distance: int`** (ticks, **REQUIRED, no default**),
`nixrisk.picture` carries it both codec directions, `WIRE_SCHEMA` **1 → 2**,
`nixalloc.seam.SEAM_REV` **1.0.0 → 1.1.0** — bumped because the bytes moved, which is the rule ARC
031 wrote down when it refused to bump on a decision alone.

**Required with no default is the load-bearing choice.** A default of `0` would let every existing
construction site keep compiling while publishing *"this position has no stop distance"* — which is
exactly the zero-priced row that made the bucket look emptier than it was. The field is required so a
writer that does not know the distance fails loudly at construction (directive 4) instead of quietly
re-opening D3.136 under a new spelling. Twenty-three construction sites were updated; the one that
mattered was `nixrisk.flatten._confirmed_rows`, which now **carries** the mirror row's own distance
rather than the placeholder a bulk edit had put there — that constructor exists to move a row to
CLOSING and change nothing else.

**THE BRIEF'S 0.4 INSTRUCTION, TAKEN LITERALLY, WOULD HAVE REDDENED THE GATE ON THE SPOT.** It said
*"`MIRRORED_FIELDS` must be PINNED to a literal at `SEAM_REV`"*, and D3.136's own ruling said
*"`MIRRORED_FIELDS` gains it"*. `MIRRORED_FIELDS` was **already** a literal, and it pins the fields of
**`FinancialPicture`**. `stop_distance` is a field of **`PositionRow`** — one level down, inside the
`positions` tuple. Adding the name there would have made the tuple disagree with
`dataclasses.fields(FinancialPicture)` and reddened `check_allocator_seam` immediately. §0b: the
spelling was a sketch; the invariant binds.

**AND THE INVARIANT IT WAS REACHING FOR HAD NO HOME AT ALL — this is the real 0.4 finding.**
Nothing in this tree pinned the published ROW's schema. `check_limiter_seam` pins the picture's nine
field names with their §3 reasons; `check_allocator_seam` ARM 2 compared `MIRRORED_FIELDS` against
the picture's dataclass. **Neither named one field of `PositionRow`.** So renaming
`PositionRow.margin`, or deleting `PositionRow.state`, changed the published wire and left every seam
gate GREEN.

**That claim is DRIVEN, not asserted.** `test_the_PRE_WIDENING_GATE_was_BLIND_to_the_row` checks the
**pre-widening gate's own bytes** out of git (found by `-S POSITION_ROW_FIELDS`, never a hard-coded
sha), runs them against a copy of the pre-widening seam with `PositionRow.margin` renamed, and
asserts that gate **PASSES**. A first draft measured a *mutilated copy of today's* gate instead — it
deleted the pin and expected blindness — and it **FAILED, correctly**: with the pin gone the literal
reads `()`, the comparison is `() != (seven fields)`, and the arm still reddens naming the renamed
field. Removing a gate's input does not reproduce a gate that never had one. The failed draft is
recorded in the test's docstring because it is the more instructive half.

The repair is `POSITION_ROW_FIELDS` (a LITERAL, checked against `dataclasses.fields(PositionRow)`,
never derived) plus `STOP_DISTANCE_FIELD` as its own finding — for the same reason `VERSION_FIELD`
gets its own: §3's atomicity is observable only through the version stamp and §7's cap is computable
only through the stop distance, and losing either does not make its rule wrong, it makes the rule
**silently unenforceable**.

**Can-fail, all green, every control asserting the REASON:** every pinned row field renamed in turn
(enumerated from the literal, so a field a later arc adds is covered without anyone remembering);
`stop_distance` renamed → the fail-open finding by name; `stop_distance` dropped from the ROW;
`stop_distance` dropped from the PIN (the other direction — a suite that only perturbs the dataclass
says nothing about a consumer quietly narrowing what it promises); and a **vacuity control** that
plants the DERIVED pin ARC 031 measured passing on eight of nine renames, and asserts the gate then
passes on a renamed row field. That last one proves the arm would NOT have worked written the
plausible way, which is the claim actually in doubt.

**`stop_distance` is a sixth field on §3:159's five-field enumeration**, so it is recorded as
**SPEC-A9** rather than slipped in. The frozen document is not edited.

**SPEC-A9 broke a gate on its first draft, and the break is worth reporting.** The table carried
`| terminal-path additions | *(none — this amendment adds no TerminalPath member)* |`.
`check_limiter_seam` derives the EFFECTIVE terminal-path roster by parsing the frozen §3 sentence
UNIONED with that row across every amendment, and it read the prose as a path named `TERMINALPATH`:
*"§3 release paths 7 != TerminalPath members 6"*. The row is machine-read, so the only correct way to
say "this amendment adds none" is to **not have the row**. Fixed, and the reason written where the
row would have been.

---

## STAGE 2 — THE CAP CLOSES. THIS IS THE ARC'S PAYOFF.

**D3.136 DISCHARGED.** `PublishedExposures` prices a held position from `row.stop_distance` on the
same versioned snapshot that carries `balance`, so every term of
`Σ dollar_risk(open + pending in B) + proposed ≤ bucket_cap_pct(B) × balance` is real.

### The before/after, and the BEFORE half is executed, not described

One scenario, two code paths. The BEFORE half is the **actual pre-widening** `wiring.py`, `caps.py`,
`sizing.py` and both seams, checked out of git and run. Two held same-bucket positions — ES 2 @ 20
ticks, NQ 3 @ 20 ticks — a 1.5% ceiling on a $100,000 balance, and a third ES proposal:

| | contracts admitted | binding constraint | `bucket_used` | ceiling | cap |
|---|---|---|---|---|---|
| **BEFORE** (pre-widening bytes) | **36** | `risk` | **$0.00** | $1,500 | INCOMPLETE, both rows unpriced |
| **AFTER** (widened row) | **22** | `bucket_cap` | **$880.00** | $1,500 | complete |

**Fourteen extra contracts — 63% more — admitted on identical inputs.** `$880 = $550 (ES) + $330
(NQ)`: neither position alone and not the larger of them, so the figure cannot be produced by a
max-shaped or single-position cap. §16 U5's rationale now names `BUCKET_CAP` as the binding
constraint where it binds, with real terms.

**A before/after whose "before" is a hand-written approximation of code that no longer exists is a
comparison against the author's memory.** The loader carries its own non-vacuity assertion — the
pre-widening `PositionRow` must NOT have `stop_distance` — and **that assertion FIRED on the first
draft**, which restored `sys.modules` after each module and so let `nixalloc.seam`'s own
`from nixrisk.seam import PositionRow` resolve against the LIVE widened module. The "before" half was
silently the "after" half, and the control said so before any number was reported.

### The out-of-band stop table is DELETED, not defaulted

`stop_ticks_by_trade` was the *measurement of the gap*. Keeping it as a fallback would leave a second,
unversioned input a gate can manufacture — the exact shape that let ARC 031 ship three green gates
over a cap that could not run. With it gone, **the only way into the cap is to publish a row**, and
that is recorded as §7.12 answer 7 on the gate: closed AT THE SOURCE rather than in the arm.

### A SECOND FAIL-OPEN DOOR, found while closing the first, and it is NOT closed

§7:498's bucket map is keyed on **LOGICAL** symbols (`ES`, `NQ`, `CL`, `GC`, `ZN`). **Nothing pins
what vocabulary the published `symbol` field speaks**, and this tree publishes all three spellings in
its own fixtures: `ES`, `MES`, and `ESZ6` / `MESU6`. The pre-ARC-032 filter was one comprehension —
`BUCKET_OF.get(row.symbol) is bucket` — so a contract-spelled row matched nothing and left the bucket
**with no counter and no note**: priced at zero by **OMISSION** rather than by valuation, in the
**same admitting direction** as D3.136. Reading the stop distance off the row does nothing for a row
that never reaches the bucket.

**Narrowed, not closed.** `PublishedExposures.classify` returns a third class (`unbucketed`),
`BucketCapAdapter` carries it into §16 U5's rationale by name, `PathwayReport.cap_unbucketed` reports
it, and `PathwayReport.cap_complete` folds BOTH classes so a caller cannot read an unbucketed table as
a whole one. The test asserts the row stayed out of the SUM **by the figure** (`bucket_used == 880.0`)
and not by the counter — a counter can be incremented by code that also counted the row. What is owed
is a DECISION about what the field means: **D3.142**, architect.

### 2.3 — nothing the Allocator emits reaches a broker

Re-proven at the wider seam by ARM 5, **by ATTEMPT** over 10 verbs and 6 venue fields, not by reading
source. `reaches_broker` is a literal `False`, `MirrorPort` still declares no mutating verb, and the
widening added no write path.
---

## STAGE 1 — THE THREE SUB-AGENTS, AND EACH FOUND A HAZARD I HAD STATED BACKWARDS IN ITS OWN PROMPT

That is the §0a result worth leading with. Each sub-agent was told to assume its prompt contained a
manufactured-input pass and a backwards hazard. **All three found one, none of them the same one, and
in two cases following the instruction literally would have produced a green that measured nothing.**

### SUB-AGENT A — the atomicity identity, RE-PROVEN on the wider row

**The third plant IS Option B.** `_StopBookJoinBook` keeps stop distances in a SECOND table and joins
them at read time — §6.4's cross-table skew, executed rather than argued — and because its FIRST
table is the real `FinancialPictureBook`, `balance`, `size` and `margin` stay atomic under one version
stamp, so **the only field it can possibly tear on is the one this arc added.**

| arm | reads | versions | tears | rate | **tears on the `stop_distance` axis** |
|---|---|---|---|---|---|
| PLANT two-read consumer | 2000 | 1998 | 1998 | 99.9% | **0** |
| PLANT two-attribute book | 2000 | 1975 | 40 | 2.0% | **0** |
| **PLANT stop-book join (NEW)** | 2000 | 1960 | 41 | 2.1% | **41 — all of them** |
| **measured (`FinancialPictureBook`)** | 2000 | 77 | **0** | 0.0% | **0** |

The two older plants tear at 99.9% and 2.0% **with zero power over the new field**. The architect's
refusal of Option B is now a measurement in this tree, not only an argument in a ledger.

The assertion that catches a fresh distance against a stale size references `snapshot.balance`
**nowhere** — that independence is what lets it see a join that leaves balance and the table mutually
perfect: *"TORN ROW at version 73 [stop_distance axis]: row T0 carries stop_distance 91 (generation
71) against size 72 (generation 72)…"*

**A REAL PROCESS BOUNDARY WAS CROSSED.** A child interpreter binds the `ipc://` endpoint and
publishes ONE picture *before this process has any subscriber*: child pid `3092594` against parent
`3092549`, 444 wire bytes, mirror FRESH/sizeable in 0.75s carrying `stop_distance` 137 — with a
**killed-child CONTROL** that took 0 bytes and reported EMPTY, because without it arrival would only
prove that *something* delivered a picture. **D3.122 is NARROWED, not discharged**, and the four
things the arm does not reach are enumerated rather than implied (D3.148).

**A's §0a findings against my prompt:**
1. **The "13,924 races / 83,971 planted tears" figures are not this gate's.** `SESSION.md:3187`
   attributes them to `check_allocator_mirror` A1, and they are *observations*, not races.
   `check_picture_atomicity` runs four races of 2,000 reads and cannot emit a figure near 13,924.
   **Had A "compared the new numbers against ARC 031's" as instructed, it would have produced a table
   that looked like a regression and measured nothing.** Both instruments are reported against their
   own priors instead; `check_allocator_mirror` A1 reproduces at 14,380 observations / 0 torn /
   falsifier 84,820.
2. **A manufactured-input pass in my A3.2.** "A `WIRE_SCHEMA` 1 body is refused naming the SCHEMA" is
   satisfied by taking a v2 body and setting `schema = 1` — that body **still carries `stop_distance`
   on every row**, so it passes against a decoder with only a schema check *and* against one with
   only a key check, proving nothing about which fired. Closed with a *genuine* v1 body plus a
   control under the current stamp that must name the FIELD instead.
3. **A second, quieter one in my A2.** "Encode the generation in `stop_distance` too" plus a single
   `MIN_TEARS` floor is satisfied by the two existing plants, **which have zero power over the new
   field**. A single floor would have been green while the harness could not see `stop_distance` at
   all. Closed with `MIN_STOP_TEARS` as a separate floor and a control that swaps the join plant for
   a two-attribute book — it still tears, so only the stop-axis floor catches it.
4. **And A refused to claim the strong reading for free.** The measured arm's stop-axis clean sheet
   is *guaranteed by construction* (`_world` publishes one immutable row object, so the subject
   cannot separate the fields). The gate now states the narrow claim — *a publisher that JOINED would
   be caught, and this one does not join* — and D3.146 records the limit.

### SUB-AGENT B — D3.140, discharged on both halves

**On trunk the two documented launch modes disagreed. They now agree, and the gate that reports them
has measured both.** `check_observed_resource_claims` sweeps the whole population once per documented
launch mode, proves the two are genuinely different interpreters, and returns CANNOT_MEASURE — never
PASS — when one is missing or when both resolve to the same one. Every finding carries the
interpreter that observed it.

**MY §0a INSTRUCTION FOR THIS WAS ITSELF STATED BACKWARDS, AND B REFUSED IT.** I wrote *"assert
resolved `sys.executable` paths differ"* via `os.path.realpath`. Measured:

```
/home/bbt/nix/.venv/bin/python -> sys.executable=/home/bbt/nix/.venv/bin/python | realpath=/usr/bin/python3.14
/usr/bin/python3               -> sys.executable=/usr/bin/python3               | realpath=/usr/bin/python3.14
```

**Both realpath to the same binary.** That branch would have made the gate report *"only one
interpreter is present on this box"* **forever**, while a live, reproducible, already-measured split
sat in front of it. The discriminator is the CHILD-REPORTED `sys.executable`, whose **basename** is
precisely what `covers()` matches on — and the refusal is written into the gate's docstring so it is
not re-litigated.

Two more of mine: *"update `EXPECTED_S` from a real measurement of your own run"* contradicts
`nix_check_contract.md` §4.4 (*"never from an observed run"*) and is mechanically enforced by the
gate's own suite — B moved the BOUND and recorded the measurement beside it as evidence rather than
as source. And my B3 hazard was backwards: `_disjointness` is set intersection, so **widening is
monotone and can only ADD collisions**; a false parallel claim requires a NARROWED declaration. Proven
three ways, including a counterfactual re-derivation of `level-0` without the new token that produced
an identical 96-reason set.

**B2 swept all 50 declarations under both interpreters, 100 observations: exactly ONE differed**, and
it is the one D3.140 names. Three successor rows (D3.152–D3.154), the sharpest being that **24 of 50
checks carry a declared token no observed claim can falsify** — the gate owns under-declaration only.

### SUB-AGENT C — §4's lifecycle reflection, and the brief's premise measured instead of believed

C's transition ran over the **real producer, the real wire and the real mirror consumer** — the only
stand-in on the path is the broker, which provably cannot be real:

`FinancialPictureBook.commit()` → `StateBusPictureSink` → `StatePublisher` over a real `ipc://`
socket → `StateSubscriber` → `AllocatorMirror` → the screen → `contention.rank_eligible`. The middle
snapshot is written by `ProtectiveFlatten.fire(UNCERTAINTY)` — the shipped Limiter code writes the
`CLOSING` row, not the gate.

| step | published version | rows in the screened state | eligible | ordering |
|---|---|---|---|---|
| held | v2 | 0 | **True** | `('strat-dying', 'strat-healthy')` |
| mid-recovery | v3 | **1** | **False** | `('strat-healthy',)` |
| flat | v4 | 0 | **True** | `('strat-dying', 'strat-healthy')` |

The value **changed and changed back**, and the arm asserts that exact sequence, so a screen
hard-wired to either polarity fails. `strat-dying` arrives FIRST, so under §6.6:466's FCFS fallback it
heads the ordering when healthy — asserted *before* the disappearance, or the disappearance would
prove nothing. `strat-healthy` survives all three steps, so "refuse everyone" cannot pass.

**C's §0a finding is the largest of the three, and it is my prompt's load-bearing sentence.** I wrote
*"the producer of these states is R5 and absent"*. Measured against the frozen spec and the tree, that
is wrong three ways:
* **The producer is NOT absent.** `nixrisk/flatten.py:_confirmed_rows` (ARC 029 / R2) publishes
  `CLOSING` rows through the real book whenever a protective flatten fired and broker truth still
  shows the symbol held (§12.6). C's ARM 5 census measures it: `['scripts/nixrisk/flatten.py']`.
  **This is what made the transition drivable without manufactured inputs** — had C believed me, ARM 2
  would have had to construct its own `FinancialPicture`s, which is exactly the manufactured-input
  pass the same brief warned about.
* **The supervisor is R4, not R5** (§12B:872-876, §12.2:616-618). Strategy-death recovery is R5
  (§12B:878-880). Two different arcs, merged in my prompt.
* **Flatten is R2 and built** (§12B:858-863).

`IN_FLIGHT_CLOSING` is not trusted from the module: ARM 1 parses the bolded phrase
`**in-flight-closing**` out of §4's own sentence at run time, requires the match inside §4's derived
line span, and maps it onto `PositionState` by value. **No lifecycle state name appears in the gate's
executable code**, asserted over the AST — a control that fired on its first run and caught two.

### THE INTEGRATION FOUND WHAT NEITHER STAGE-1 GATE COULD — AGAIN

C proved §4:284-286 as a RULE and its gate is green. From a worktree that could not edit `wiring.py`,
it also measured that **nothing on a production path called the screen**, and that `wiring.py`'s
docstring asserted a `contention.rank` wiring that did not exist. **That is D3.136's shape one layer
up**, inside the module whose whole job is to state what the composition cannot do.

Wired here (D3.147, opened and discharged in the same arc): the pathway holds a `LifecycleViewPort`,
**defaulted to a view over its own mirror rather than to `None`** — an opt-in safety screen is off in
every caller that forgets it, and D3.136 is this arc's evidence that a defaulted-off safety input is
not a smaller version of a safety input. The screen runs BEFORE sizing, because §4:284-285 says a
dying strategy is NEVER COUNTED eligible, so its rationale reports ZERO for every §7 term rather than
plausible figures for a pass that never ran.

**The abstain boundary was MEASURED, not designed.** The first draft screened unconditionally;
`eligibility_from_mirror` folds §12.7's freshness refusal into its own answer (right for a contention
race, wrong here), so a stale mirror came back INELIGIBLE and the pathway reported `NO_SIZE_DENY`.
ARM 1 reddened instantly: *"the three non-sizing outcomes collapsed into 2 — a pathway that cannot
tell a dead signal from a stale mirror hides the §0i class entirely."* The screen now abstains when
there is no FRESH picture. Two rules, two owners, and a plant holds the boundary in place.

---

## STAGE 3 — CONVERGENCE

**3.1** `verify.py --optimize --commit` → **"derived plan is identical to the live registry"**, then
INSTALLED. Five branches touched `checks/registry.json` and the union was only a way to reach
parseable JSON; the derivation confirmed it independently.

**3.2 — the observer sweep, and it is subject to D3.140's own finding, so it ran under both.**
Three orders × two sweeps × **two interpreters** = 12 sweeps, 51 subjects each, **612 observations**.
Permutation is WITHIN a registry block only, after proving from `DEPENDS_ON` that no member depends on
a block-mate (`intra-block deps: NONE`), because permuting across blocks would reorder declared
dependencies and a finding from that is a finding about the harness.

```
                    order-dependent   unstable   claims/sweep   findings
venv    (12 sweeps)        0             0           121            0
system  (12 sweeps)        0             0           121            0
```

**121 claims per sweep, IDENTICAL under both interpreters** — which is D3.140's discharge confirmed
by an instrument that knows nothing about it. The claim count is also the non-vacuity floor: zero
findings across twelve sweeps means something only against an observer that demonstrably fired.

**3.3 — census three ways.** `checks/check_*.py` glob = **52**; `registry.json` membership = **52**;
`verify.py`'s own executed tally = **52** (48 + 1 + 2 + 1). Two of the three are compared by
`check_derived_claims` on every run; the third is the close-out run below.

**3.4 — the binding table, REBUILT from measured observations, not carried forward.**

```
BOUND = 50    EXERCISED-NEVER-RED = 2    UNBOUND = 0        1,626 observations
```

Floor 49, measured 50. **Both new checks land BOUND**: `check_allocator_lifecycle` with 19 reds
(`CANNOT_MEASURE:4, FAIL_NEEDS_OPERATOR:19, PASS:17`), and every changed check stayed bound.

**AND THE 49/2/0 THE BRIEF PREDICTED IS RESTORED, which resolves the Phase-0.1 delta rather than
leaving it hanging.** Trunk measured 50/1/0 because the census ran while
`docs/BRANCH-PROTECTION-PROPOSAL.md` sat uncommitted: `check_untracked_attribution` correctly reddened
on *"work exists in the canonical tree that no commit on any branch contains"*, and a red is what
BINDS a check. Committing the file returned it to EXERCISED-NEVER-RED. **That was never a discharge of
D3.139** — its finding is that the suite drives `evaluate()` and never `run()`, so the tracer cannot
see the reds the suite already proves. An incidental real red disguises an instrument gap; it does not
repair one.

---

## THE LEDGER — 172 → 186

**Seventeen opened, three discharged, and TWELVE of the seventeen were opened by an instrument or a
sub-agent measuring something a brief asserted**, rather than by the work itself. The figure was not
typed: `check_derived_claims` FAILED against the stale 172 inside the same edit that staled it
(*"derived:ledger_rows=186, stated:series_table_latest_row=172"*), and the cell was re-derived to what
the rows say.

**DISCHARGED:** D3.136 (the cap), D3.140 (the interpreter split), D3.147 (opened and discharged in
the same arc — the wiring that did not exist).

**The four rows that closing D3.136 EXPOSED**, and none of them is closed by the discharge:

| row | what it says |
|---|---|
| **D3.142** | the published `symbol` has no pinned vocabulary — a contract-spelled row never reaches its bucket at all, priced at zero by OMISSION, same admitting direction |
| **D3.143** | §7:502's micro weight is not published; the error is conservative and is still an error |
| **D3.150** | **NOTHING IN PRODUCTION EVER CHOOSES A `stop_distance`.** Exactly two production constructors exist: the codec, which READS it off the wire, and `flatten._confirmed_rows`, which CARRIES it. **The field is proven to TRAVEL and not to be RIGHT, and only the first is banked** |
| **D3.146 / D3.151** | the new atomicity axis has conditional power over the measured arm, and the wire arms have no per-run floor on it — recorded so the weaker green is never read as the stronger |

**D3.150 is the one to read.** §7:501 prices bucket exposure from the distance, so a row published
with a placeholder feeds §7's cap a number no sizing pass computed. A wrong-but-present value is not
obviously safer than the absent one it replaced, and the discharge is the Limiter's fill path writing
the sizer's own `stop_ticks` onto the row it publishes.

---

## CLOSE-OUT GATES

**`verify.py` on trunk, under BOTH documented interpreters** — and D3.140 is resolved, so they agree:

| launch mode | resolved interpreter | result |
|---|---|---|
| venv | `/home/bbt/nix/.venv/bin/python` | `48 passed \| 1 failed \| 2 cannot measure \| 0 skipped \| 1 guarded` · exit 1 |
| system | `/usr/bin/python3` | `48 passed \| 1 failed \| 2 cannot measure \| 0 skipped \| 1 guarded` · exit 1 |

**Every non-PASS, named:**
* **FAIL — `check_ibgateway_service`**: `127.0.0.1:4002 (nix-ibgateway.service): API endpoint not
  reachable — ConnectionRefusedError: [Errno 111]`. The standing tap-session FAIL, by design, and the
  only code-independent one.
* **CANNOT_MEASURE — `check_ibgateway_config`**: same dead port, §4.1.
* **CANNOT_MEASURE — `check_observed_resource_claims`**: §17 masking by the same dead port. **This is
  not the D3.140 verdict** — that one was interpreter-dependent and is gone; this is the standing
  `ECONNREFUSED` the gate has always reported, and it is now identical under both interpreters.
* **GUARDED — `check_artifact_gate_coverage`**, owner printed verbatim below.

**Baseline comparison, stated exactly:** ARC 031 closed at `47 passed | 1 failed | 2 cannot measure`
(venv) and `47 | 2 | 1` (system). This arc closes at `48 | 1 | 2` under **both** — one more PASS
(`check_allocator_lifecycle`, the new check), and the system-interpreter FAIL gone because D3.140 is
discharged. **No further FAIL, and no further non-PASS whose cause is not named.**
**The GUARDED check and its owner, printed VERBATIM:**

```
[GRD]  check_artifact_gate_coverage
  scripts/harness.py            -> ARC 033 (2 of 2 re-owning(s) used, measured_by=tests)
  scripts/monitor.py            -> ARC 033 (2 of 2 re-owning(s) used, measured_by=tests)
  scripts/nixrisk/execution.py  -> ARC 032 (2 of 2 re-owning(s) used, measured_by=tests)
  scripts/nixverify/venv_lock.py-> ARC 033 (2 of 2 re-owning(s) used, measured_by=tests)
  scripts/pty_test.py           -> ARC 033 (2 of 2 re-owning(s) used, measured_by=none)
  scripts/nixverify/actuation.py EXCLUDED -> ARC 033 (CHECK-A8/CHECK-A9 holding state, ceiling-exempt, temporary)
  scripts/nixverify/contract.py  EXCLUDED -> ARC 033 (…)   scripts/nixverify/engine.py   EXCLUDED -> ARC 033 (…)
  scripts/nixverify/gitenv.py    EXCLUDED -> ARC 033 (…)   scripts/nixverify/loader.py   EXCLUDED -> ARC 033 (…)
  scripts/nixverify/optimize.py  EXCLUDED -> ARC 033 (…)   scripts/nixverify/registry.py EXCLUDED -> ARC 033 (…)
  scripts/nixverify/render.py    EXCLUDED -> ARC 033 (…)
```

**`scripts/nixrisk/execution.py` is the one row still owned by ARC 032, and that is deliberate.** All
thirteen were owned by the arc IN FLIGHT, so all thirteen would be dead the moment this arc's summary
was appended (`completed_arcs` reads `SESSION.md`'s `##` headings — the D3.40 shape, and exactly what
D3.138 predicted and ARC 031's post-write-back re-measure confirmed on this same gate). Twelve were
walked forward. The thirteenth's committed owner lineage is `ARC 030 → ARC 031 → ARC 032` — three
owners, **two re-ownings, exactly at `GUARD_REOWN_CEILING`** — so its two available moves are:

* re-own to ARC 033 → a **third** re-owning → `reowning_defect` escalates GUARDED to **FAIL**;
* leave at ARC 032 → a dead owner → **CANNOT_MEASURE**.

CANNOT_MEASURE is the honest one. Paying the FAIL to move it one more arc is buying a green with the
exact deferral the ceiling forbids, and the third move — real coverage — is the second instrument
doctrine C.9 refuses here, since `test_execution.py` already drives the ledger with 23 tests including
permutation-invariance. **That is CHECK-A9's own argument, and it needs the same thing: an architect
ruling. D3.144.**

**A TRANSIENT NON-PASS, NAMED RATHER THAN SUPPRESSED.** One earlier venv run reported `47 | 1 | 3`,
the extra CANNOT_MEASURE being `check_plane2_across_kill`: *"the killed producer got only 19
heartbeat(s) onto the bus before dying (floor 20) — 'nothing was lost' over a set that small is a
statement about an empty set."* It was a load artifact of two back-to-back `verify.py` invocations,
and three consecutive re-runs cleared it (51, 24, 53 heartbeats). **The gate refusing rather than
reporting a green over too small a set is it working**, and it is reported here rather than quietly
re-run until it went away.

### The rest of the close-out gates

```
pytest scripts/tests -q          →  1963 passed, 2 skipped, 2 xfailed   (0:16:18)   exit 0
claims harness                   →  green, 13/13 claims + 2/2 demonstrations re-executed
CHECK-DEBT                       →  186   (derived:ledger_rows=186 == stated:series_table_latest_row=186)
census three ways                →  52 == 52 == 52   (checks/ glob · registry.json · verify.py's tally)
binding                          →  BOUND=50 · EXERCISED-NEVER-RED=2 · UNBOUND=0 · 1,626 observations
pre-commit run --all-files       →  exit 1  — SEE BELOW
per-commit pre-commit            →  passed on every commit this arc made, full runtime gate each time
```

**`pre-commit run --all-files` is RED, and it was RED at `d1525ba` before this arc existed.** Six
hooks fail and every production site they name is one of `scripts/harness.py`, `scripts/monitor.py`,
`scripts/pty_test.py` (235 / 163 / 49 mentions), plus pre-existing `pylint R0801` and two `mypy
[arg-type]` errors in test modules this arc did not touch. Measured against the *pristine* `d1525ba`
bytes in a scratch tree: 75 ruff errors, 3 files unformatted. **NOT FIXED, deliberately** — they are
untested operator scripts, which is precisely why all three sit in the coverage guard, so a lint
rewrite is a change nothing here could verify, on files outside this arc's scope. Owned as **D3.145**,
which also records the two second-order findings: `ruff check` runs with `--fix` and **rewrites all
three on every `--all-files` invocation** (all three sub-agents hit it; all three reverted, as did
this integrator), and the per-commit path is scoped to STAGED files, so a whole-tree `mypy` error can
ride in a green commit indefinitely — which is how those two did.

---

## WHAT IS STILL YOURS

1. **The push.** Not pushed. `origin/main` is where ARC 031 left it (`a229228`).
2. **Branch protection (0.3).** `docs/BRANCH-PROTECTION-PROPOSAL.md` carries the measured state, the
   recommended ruleset JSON (one `gh api -X POST --input`), the classic-protection alternative, the
   rollback for each, and the drafted CI workflow with its gaps named. **The rule protects nothing
   until D3.141 is discharged**, and the file says so in its own text.
3. **D3.142 + D3.143 — one decision, two rows.** What vocabulary does the published `symbol` field
   speak? Declaring it the LOGICAL symbol closes the second fail-open door and lets `micro_symbols` be
   derived from the registration ACK. Declaring it the contract symbol needs a resolver on the seam.
   Either way it changes a frozen wire field's meaning, so it is yours.
4. **D3.150 — the origin write.** Nothing in production ever chooses a `stop_distance`. This arc
   proved the field travels; nothing proves it is right. The discharge is the Limiter's fill path
   writing the sizer's own `stop_ticks` onto the row it publishes, plus a gate that reddens when a
   published distance disagrees with the stop book's for the same trade.
5. **D3.144 — `scripts/nixrisk/execution.py` at the re-owning ceiling.** Either a `CHECK-A<n>` moving
   it into `exclusions` on CHECK-A9's instrument-blind-spot grounds, or a ruling that a second
   instrument is warranted. This arc refused to take either unilaterally.
6. **The tap session** — still owed by eighteen arcs, still the only code-independent FAIL, and now
   also the reason `check_observed_resource_claims` cannot judge any declaration added while the
   Gateway is down (**D3.149**).
7. **`registry.json` vs `manifest.json`** — still an open operator ruling, untouched.
8. **v1.4 fold + D3.33** — `SPEC-A9` is the ninth amendment; the v1.4 file holds seven.

---

## DEFERRALS, STATED AS THE BRIEF REQUIRED

Not in this arc and not pretended to be: the supervisor / heartbeat / orphan-recovery / crash-loop /
quarantine machinery (**R5** for strategy death, **R4** for supervision — the brief merged them and C
measured the split); the Scoring process and score-across-death persistence (R5 — the ranking table is
READ-only here and has no writer); performance-weighted contention (R5 — FCFS is the only reachable
policy, and a §16 U1 single-pass proposal has no race to arbitrate anyway); blackout/calendar pollers
(R4); the strategy FSM; the tap session; and changing branch protection, which is the operator's.

**`SEAM_REV` is 1.1.0 because the bytes moved.** ARC 031 pinned it at 1.0.0 with the target planned
and wrote down the rule that the literal moves when the wire changes and not when a decision is taken.
It changed here for the reason that rule allows.

---

## POST-WRITE-BACK RE-MEASURE — the predicted transition, fired

The write-back commit appended ARC 032's summary to `sessions/SESSION.md`, which makes ARC 032 a
COMPLETED arc to `contract.completed_arcs`. Re-measured immediately afterwards:

```
check_artifact_gate_coverage:  GUARDED (exit 3)  ->  CANNOT_MEASURE (exit 2)
  checks/gate_coverage_baseline.json:artifacts:scripts/nixrisk/execution.py:owner:
  'ARC 032' has ALREADY COMPLETED — its close-out summary is in sessions/SESSION.md

verify.py  →  48 passed | 1 failed | 3 cannot measure | 0 skipped   exit 1
```

**This was written down BEFORE the commit that caused it** — in `D3.144`, in the guard re-owning
commit `8105092`, and in the write-back commit's own message — with both available moves measured and
the reason the other was refused. It is the transition the ceiling exists to force: the work on
`scripts/nixrisk/execution.py` is overdue, a fourth owner would be a third re-owning, and paying a
FAIL to move it one more arc is buying a green with the exact deferral the ceiling forbids.

The other twelve guards were walked forward to ARC 033 and are unaffected. Nothing else moved: the
FAIL is still the tap session, the two standing cannot-measures are still §17 masking by the dead
Gateway port, and `48 passed` is unchanged.

**The final figure for this arc is therefore stated twice, and both are true of different moments:**
`48 | 1 | 2 | 0 | 1` immediately before the write-back, under BOTH interpreters, and
`48 | 1 | 3 | 0 | 0` immediately after it. Quoting only the first would hide a transition this arc
predicted; quoting only the second would hide that the arc's gates closed green.
