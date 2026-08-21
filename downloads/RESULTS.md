# ARC 051 RESULTS — I12 input freshness (cc -> claude.ai)

## 2026-08-21 — ARC 051: I12 input freshness — never act on a stale, out-of-order or half-built input

**TIER = INTERIOR. Limiter STAYS RED. I12 DISCHARGED: clean 10/12 -> 11/12, open = 1 (`I1`).**
Predecessor tip DERIVED as **`652f9e5`**, not the brief's approximate `ffd6b69` — `ffd6b69` is 050's
series-row commit and `652f9e5` is its final-measurement commit one further on. Every freeze and diff
in this arc is against `652f9e5`.

### The baseline was MEASURED, and it refuted the number the brief carried

`verify.py` at `652f9e5`, before a line changed: **`91 passed | 4 failed | 3 cannot measure |
0 skipped | 1 guarded`, exit 1** — not 050's closing `92|4|2|0|1`. The mover is a real finding and it
is this arc's D3.464: **`check_arc_status_contract` went PASS -> CANNOT-MEASURE with nothing in the
tree changing**, because its subject `scratchpad/arc_logs/arc_050.log` carries no
`**** ARC completed ****` line — `grep -c` returns **0** — while the log's last beat is 100% at
`HEAD 652f9e5`. The marker was printed to the chat and never passed through the `tee`. It cannot be
repaired retroactively (banked evidence, directive 6), so ARC 051's own log carries it and ARC 052
will read PASS. This is D3.455's neighbour one layer up: 050 taught the check to exclude the RUNNING
arc's log and name the previous one, which is precisely why 050's gap is visible from here.
**Memory #19 again: the carried figure was wrong and the measurement said so in the first minute.**

### The ownership census, taken BEFORE the gate was written (the I4/I9 lesson)

Four gates touch freshness and **every one of them owns exactly ONE FILE**: `check_staleness` ->
`freshness.py` + `staleness.config.json`; `check_picture_atomicity` -> `picture.py`;
`check_allocator_mirror` -> `nixalloc/mirror.py`; `check_limiter_gate` -> `gate.py`. **None owns the
RELATION I12 names** — *an input added to the gate tomorrow with no freshness check*. That input
would sit inside `gate.py` (invisible to `check_staleness`), would not move dispatch order
(`check_limiter_gate` stays green), and would touch neither mirror. D3.392 is the standing proof that
this blind spot is real and not theoretical: the Limiter's margin cap read no stop distance for three
arcs while `check_allocator_caps` stayed green, *"because its `SUBJECTS` is `nixalloc/caps.py` ...
`gate.py` is not in scope, so both facts were invisible to it by construction."* **Verdict: a NEW
gate file, `passed +1`.** Predicted before the run; measured after.

### S1 — REPRODUCED, and I12 is MET IN CODE (the I3/I4/I9 pattern)

Twelve arms driven on real objects at the library level, all twelve holding, non-vacuity first:

| driven | result |
|---|---|
| every configured feed stamped 100 ms ago | `GatePass.evaluate` -> **APPROVE**, all 10 rules in `evaluated` |
| `price` 900 000 ms old (threshold 2 000, deadline 3 750) | **DENY at `data_staleness`**, reason names the key and both numbers |
| `price` 2 500 ms old — INSIDE the retry window | state `STALE`, `blocked=False`, gate **APPROVE** — §6.4's ladder runs BEFORE the halt and no second retry is added |
| `price` never observed | state `EMPTY`, **DENY** — stale-until-proven-fresh (§17) |
| older instant / same instant lower `source_seq` / exact duplicate | **3 discarded, `admitted` unchanged, held stamp did not move** (§6.4b, V27) |
| a 900 s-old stamp admitted under `margin:NQ` | `margin:ES` unmoved — per-key isolation |
| a late poll arriving AFTER the feed went silent | `observe` -> **False**, gate still **DENY** — a late packet cannot refresh its own age (§0a, watched past the tick) |
| mirror mid-rebuild, then delta-only | `tradable()` **False** both times, naming `('tbl.financial_picture',)` (§12.7, V31) |
| the SNAPSHOT lands | `tradable()` **True** — the act side, so this is a refusal and not a habit |
| that snapshot aged 900 s past a 5 s ceiling | `tradable()` **False** again |
| `seq=1` replayed after `seq=2` | `applied` unchanged, `out_of_order=1`, mirrored version still 8 |
| net-liq mark `(10_000_000.0, fresh=False)` | **DENY at `survival_headroom`** — a comfortable NUMBER with a dead stamp is still refused |
| §12.3: a source stamp 60 s AHEAD of local; a skew observation 900 s old | both **block**; a fresh in-spec observation clears |

### S2 — EMPTY BY DESIGN, and proved so

No subject was edited. **Eighteen files byte-identical by `git hash-object`**, including all three
subjects: `freshness.py` `5466041a`, `gate.py` `69eef09f`, `picture.py` `dcbb5a67`, plus
`pollers.py`, `calendar_seam.py`, `nixbus/statebus.py`, `nixalloc/mirror.py`, `seam.py`, the fill
path (`fills.py`, `stops.py`), the exit path (`flatten.py`), the two-phase state (`positions.py`,
`projection.py`), I2's `outcomes.py`/`reservations.py`, the hot-path files (`loop.py`, `wal.py`) and
`risks/staleness.config.json`. `CORRECTABLE=False` means this in practice as well as in the
declaration. **The arc's work is the gate.**

### S4 — `checks/check_input_freshness.py`, and the input set is DERIVED, not transcribed

Everything the census judges is read off the shipped AST, in four derivations held against each
other, so the arc that adds the seventh port cannot silently outrun it:

1. **PORT TYPES** — every `class X(Protocol)` in `gate.py`, with each verb's RETURN annotation.
   Measured: **5**. The annotation is what classifies: `tuple[float, bool]` is a `(value, fresh)`
   pair the rule must branch on; `tuple[bool, str]` is §11.1's `(blocked, reason)` flag.
2. **INPUTS** — every parameter of `default_manifest`, `GatePass.__init__` and every `evaluate`.
   Measured: **15**, each landing in exactly one bucket — 6 flag ports, 1 fresh-pair, 1 stamped
   snapshot, 1 in-process proposal, 1 per-pass clock read, 3 §12A knobs, 2 structural.
3. **STAMP FIELDS** — attributes that FRESHNESS-REFUSAL SITES read, a site being derived as *a
   function that calls a clock and subtracts an attribute from it*. Measured: **16**, and
   `published_ts` resolves to `nixrisk/picture.py:707:tradable` and `nixalloc/mirror.py:339:snapshot`
   — two modules, neither of them named in the check.
4. **CLOCK-SOURCED FIELDS** — keywords anywhere in shipped code whose value expression contains a
   clock call. This is what finds `signal_ts`.

**A field that is clock-sourced but is NOT a stamp field is a time quantity on a gate input nothing
gates on**, and the derivation found exactly one: **`ProposedOrder.signal_ts`** (D3.463). It is
admitted BY NAME in a one-way ratchet with its reasoning — §6.4b scopes its guard to *"ALL
venue-sourced state"* and a GO is strategy-sourced; §4:210-212 bounds admission -> feedback on the
loop's own monotonic tick clock, a different quantity; the frozen spec never says whether signal age
should bound entry. The sharper half is in the daemon: `limiterd.py:1168` is
`signal_ts=float(raw.get("signal_ts") or time.time())`, so **an ABSENT signal instant is silently
dated NOW.** Not called clean, not called a defect, not silently absorbed — recorded, with the
architect ruling named as the discharge. A SECOND ungated time field is a FAIL.

### The gate is BOUND — four plants, and the rule-4 ordering TESTED rather than reasoned about

`scripts/tests/test_check_input_freshness.py`, 9 tests, all passing, every plant on a COPY:

* **PLANT A** — `StalenessFlagPort.read` stops reporting its blocking feeds: **exit 1**,
  `THE GATE SIZED ON A STALE INPUT`, naming `price`, the age, both thresholds and the ignored key.
* **PLANT B** — the monotonic discard removed: **exit 1**, `THE HELD VALUE REGRESSED`, §6.4b named.
* **PLANT C** — `PictureMirror.picture` stops refusing an incomplete mirror: **exit 1**,
  `A DELTA COMPLETED THE MIRROR`, §12.7 named.
* **PLANT D** — a new gate input the census cannot classify (`venue_feed: VenueFeedPort = None`,
  added compatibly so nothing raises): **exit 2**, `UNCLASSIFIABLE GATE INPUT`, naming it. Never PASS.
* **PLANT A + PLANT D TOGETHER** — a FAIL on one arm and a CANNOT_MEASURE on another,
  simultaneously: **exit 1. FAIL WINS.** Check contract rule 4, and the ordering four consecutive
  gate first-drafts got wrong (045, 049, 050 x2). It is now a test, not an argument.
* **Denial-by-construction control** — a port that blocks every reading: **exit 1**,
  `NON-VACUITY FAILED`. Freshness achieved by refusing everything is safe and useless, and the gate
  says so.
* Plants removed on the SAME tree: **exit 0**. A home with no `nixrisk`: **exit 2**, §17 named.

Every assertion is on the REASON, never the exit code alone (rule 11). Registry: hand-added to
`level-0`, then `verify.py --optimize --commit` reported *"derived plan is identical to the live
registry"* and INSTALLED — the derivation agreed with the hand-add rather than being trusted.

### Close-out

**(b)** Derived closure by detection (D3.444 — the import graph is blind to subprocess callers):
**184 passed, 0 failed** over 11 modules, `--basetemp=/var/tmp/arc051_pt` OUTSIDE the tree (D3.462).
`test_picture.py` and `test_statebus.py` are uncollectable under `.venv-dev` for the PRE-EXISTING
`import zmq` reason ARC 047 recorded; `scripts/nixbus/` is byte-identical this arc and both their
gates pass under `verify.py`. Tripwire guard honoured: `test_check_order_path_bans` and
`test_check_uncalled_entry_points` run EXPLICITLY (52 passed). Lint scoped to the two CHANGED files,
never `ruff .`. **(c)** The gate is bound from all four plants plus the rule-4 plant-both.
**(d)** CHECK-DEBT reconciled: D3.463 and D3.464 appended and the **ARC 051 series row written at
410, re-derived WHOLE off `check_derived_claims`'s `derived:ledger_rows`** — read off the instrument,
not 408 plus arithmetic. `check_derived_claims` exit 0. `uncalled_entry_points_baseline.json`
UNMOVED. The `check_artifact_gate_coverage` guard re-pointed **ARC 051 -> ARC 052** (8 exclusions,
still GUARDED, ceiling-exempt) because a completed owner is Cannot-measure and cannot outlive itself.

### RESIDUAL — explicitly NOT claimed

* The **flatten-open half** of §6.4 (STALE_PRICE producer) — **D3.453 = I1 ARC C**. I12 proves
  stale => deny (halt new entries); flattening an already-open position on stale is the capstone.
* **V32** one-version cross-table coherence is the atomic-snapshot property and belongs to
  `check_picture_atomicity`. It intersects here only in that both read `FinancialPicture.version`,
  and it is not re-litigated.
* D3.372, D3.458, D3.450, D3.104 (8 exclusions, now 6 arcs re-pointed — the pay-down is overdue),
  D3.428, D3.434, D3.438-D3.464, D3.359/360/361/363 — standing named debt.
* `downloads/Pinokio-8.0.40-arm64.dmg` is still untracked and `check_untracked_attribution` still
  FAILs on it. It is a user's file in a user's directory and it is not cc's to delete.

### BADGE — Limiter STAYS RED, and this was the LAST point-fix

**clean = `{I2, I3, I4, I5, I6, I7, I8, I9, I10, I11, I12}` = 11/12, open = 1: `I1`**, the
daemon-wiring capstone. **After this arc the only thing between the Limiter and a green badge is the
I1 tail plus the greening close-out.**

**Recommended next, BEFORE ARC A** (pre-pay-the-tax): a consolidation arc — cover the
`limiterd.py`-class daemon files under testmon, pay down D3.104's 8 exclusions (six arcs re-pointed
is a ceiling being walked, not a debt being held), and finalize the ARC C flatten-producer plan.
