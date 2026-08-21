# ARC 050 — RESULTS. Limiter slice 10: **I9 DISCHARGED → 10/12.** Limiter STAYS RED.

**Tier INTERIOR.** Predecessor **DERIVED**: the brief said "≈ `67ce36f`"; `git rev-parse HEAD`
said **`89e0e2a`**. Everything frozen and diffed against `89e0e2a`.

## Measured baseline, and one prediction the measurement refused

**`91 passed | 4 failed | 2 cannot-measure | 0 skipped | 1 guarded`, exit 1 at `89e0e2a`.**

FAILs: `check_ibgateway_service` (4002 ECONNREFUSED), `check_monitor_tui` (stale pin),
`check_uncalled_entry_points` (54 findings), `check_untracked_attribution`
(`downloads/Pinokio-8.0.40-arm64.dmg`, still present, NOT deleted — not this arc's file to rule on).

**The brief predicted `check_arc_status_contract` would read cannot-measure at this baseline. It
read PASS**, auditing `arc_049.log`. Recorded as measured, not as predicted (directive 2).

## Gate ownership census — stated BEFORE the run, and it decided the delta

Four gates in this tree touch the words "hot path". **None owned this property.**

| gate | what it owns | I9? |
|---|---|---|
| `check_plane1_hot_path` | §11.6 group-commit **latency** isolation, a µs relation over one off-path item; D3.400 records it times a `GatePass` with `ledger=None` | no |
| `check_limiter_gate.arm_hot_path` | §11.3's O(1)-in-\|positions\| **shape**; µs explicitly excluded from its verdict (D3.39) | no |
| `check_flatten` ARM 6 | wire-freedom of the **exit** path | no |
| `check_pollers` | that §6.4's caches are **maintained** | no |

→ **NEW gate is correct (doctrine C.9 permits a new instrument for a new property). Predicted
`passed +1` before the run.**

## S1 — I9 was NOT met-in-code. The charter's defect, reproduced.

I9's charter names *"a synchronous I/O or compute on the gate path"*. 2,000 real APPROVE
decisions through the shipped path, non-vacuous (`{'APPROVE': 2000}`, Σ reserved 16,000,000):

| arm | raw `write(2)` | PEP-578 events | roots |
|---|---|---|---|
| A per-GO gate | **2000 = 1.000/approval** | **0** | gate, reservations, seam, **wal**, **json**, enum |
| B per-tick stop-eval (\|stops\|=5) | 0 | 0 | stops, seam, dataclasses |
| C O(1) aggregate reads | 0 | 0 | picture, reservations |

**THE HEADLINE IS NOT THE COUNT — IT IS THAT THE AUDIT HOOK SAW NOTHING.** Zero PEP-578 events
against 2,000 kernel `write(2)`. `Plane1Wal` opens `buffering=0` and appends through
`_io.FileIO.write` on an already-open descriptor; PEP 578 audits `open`, not `write`. **An
audit-hook-only purity gate is vacuous by construction** — now a measurement of this tree, not a
hypothesis. Banked **D3.461**, scoped to the mechanism: `scripts/nixverify/observe.py` inherits
the blind spot and its "NOT observed" table does not name it.

## S2 — EMPTY BY DESIGN. Subject byte-identical.

`git hash-object` vs `89e0e2a`, all IDENTICAL: `gate.py` `69eef09f` · `stops.py` `ca907302` ·
`loop.py` `723feacc` · `wal.py` `bf9c08f1` · `reservations.py` `ecf9d22d` · `picture.py`
`dcbb5a67` · `flatten.py` `d2c825f7` · `positions.py` `1561c8e2` · `projection.py` `2ee2ef13` ·
`outcomes.py` `ebff41ad` · `fills.py` `847af3de` · `fill_seam.py` `339ca62f` · `plane1_sink.py`
`a6f0027d` · `limiterd.py` `432781f8`. **`CORRECTABLE = False` honoured in fact.**

**Why the write is not moved off — argued from the spec, not assumed.** §11.6 verbatim:
*"**Group-commit** event-log writes off hot path (WAL-buffered)."* What §11.6 puts OFF the path
is the group-commit; the mechanism is that the hot path is *WAL-buffered*. §11.6 therefore places
the WAL append ON the path by its own words, and `check_flatten` already banked that reading.
**And `buffering=0` is load-bearing**: it is what gets bytes into the page cache before `fsync`,
which is `check_plane1_crash_gap`'s property. Flipping it would green this arc by breaking
another gate's subject. **Banked OPEN as D3.458** — the real §11.6 shape is an architect ruling,
not a flag.

## The gate: `checks/check_hot_path_purity.py`

* **ALLOW-SET, not a ban-list.** A root outside `_ALLOWED_ROOTS` ⇒ CANNOT_MEASURE naming it,
  never PASS.
* **Entry points DERIVED BY SHAPE** — the `GatePass` method dispatching a `.evaluate`, the
  `LimiterLoop` method calling `.take_in_flight`, the public `StopBook` methods that **LOOP over**
  `self._by_symbol` (§15's one permitted traversal). `ast.walk`/`iter_child_nodes`, never a bare
  `.keys` (the 049 hazard).
* **THREE mechanisms**, because S1 proved one is vacuous: `sys.setprofile` (frames + per-eval
  imports) · `sys.addaudithook` (open/socket/subprocess/exec) · **`/proc/self/io` `syscw`** (the
  only one that sees D3.400's write). Count from 3, site from 1.
* **The `nixrisk.wal` permission is BOUNDED three ways**: `MAX_WRITES_PER_APPROVAL = 1`; **any
  hot-path fsync is an unconditional FAIL** (that is §11.6's actual prohibition — measured 0 over
  2,000 approvals); and **ARM 2, the DISCRIMINATOR** — the same pass with the WAL swapped for an
  in-memory sink must record **0** writes. It does. ARM 2 is what makes ARM 1 honest.
* **ARM 4 — the off-path work still HAPPENS**: 4,000 rows made durable off-path (fsyncs 0→1),
  §11.7's full-scan reconcile ran and saw the ledger, `commit()` raised the version the hot path
  reads O(1). Purity by dropping the work would be a worse bug.

**BOUND — 7/7, plants into a COPY of the tree so the subject was never touched:**
**A** `open` on the gate path → **exit 1**, names the op · **B** per-eval `import queue` →
**exit 1**, names it · **C** unclassifiable `base64` → **exit 2** CANNOT_MEASURE, names it ·
**plants removed → exit 0 on the same tree** · derived shape broken → exit 2 naming ARM 6 ·
empty home → exit 2, no fall-through (D3.124).

## Four findings about the INSTRUMENT, recorded because they were measured

1. The first drill **denied all 2,000** — a port double answered the wrong verb, and every "no
   forbidden op" it printed was true and worthless. Hence `MIN_APPROVALS` and the Σ-reserved
   assertion live in the gate.
2. The gate's first green run **reddened on its own sibling arm** — ARM 4's `sync_to_disk()` ran
   before the fsync assertion read the counter. `fsyncs_on_path` is now snapshotted.
3. **ARM 2's non-zero write count was CANNOT_MEASURE and should have been FAIL.** It had
   *positively observed* a writer. Cannot-measure is for what an instrument could not see.
4. **The ladder let an unclassifiable root mask a positive observation** — PLANT A's `codecs`
   beat its own `open`. UNCLASSIFIABLE is now judged LAST: rule 10's principle one layer down.

## Debt banked

**D3.462** basetemp-inside-the-tree recursion (this arc caused it) · **D3.458** 1 `write(2)`/approval, `buffering=0` vs §11.6's "WAL-buffered" — and why the flag must
NOT be flipped · **D3.459** the allow-set is a measured property of today's path (D3.454's shape)
· **D3.460** `GatePass.evaluate` has no production caller; the daemon's decision is
`take_in_flight`, so seven of nine rules are proven pure of code `limiterd` does not yet run —
I1's work · **D3.461** the PEP-578 write blind spot, scoped to the mechanism and to `observe.py`.

## Not claimed

D3.372 · D3.450 · D3.453 (I1 ARC C) · **D3.104** — its eight exclusions re-pointed `→ ARC 051`
**before** SESSION.md named this arc complete. **Fifth consecutive bump on the same eight
artifacts.** The brief calls it a pay-down candidate, not a perpetual re-point; this bump does
not answer that.

## An ops finding this arc CAUSED — reported, not buried

**`--basetemp` inside `~/nix` filled the disk: 620 GB, `/` at 100%.** The tree-copying tests copy
the WHOLE canonical tree into `tmp_path`, so a basetemp under `scratchpad/` makes each copy
re-copy its own growing destination, every level carrying the 137 MB `.dmg`. **cc's flag, not the
test's defect.** Nothing was corrupted — every written artifact was re-verified intact afterwards
— but that was luck, not design. **The rule this measured: basetemp must be OUTSIDE `~/nix`
entirely, because the tests copy `~/nix`; a cleaned basetemp inside the tree is still a recursive
one.** Banked **D3.462** with a mechanical discharge. Re-run from `/var/tmp/arc050_pt`; disk back
to 727 GB free.

## FINAL MEASUREMENT — **PREDICTION MISSED, then reached**

Predicted delta on the baseline `91|4|2|0|1` at `89e0e2a`: `passed +1` from a NEW gate (stated
from the census BEFORE the run) → `92|4|2|0|1`.

**The FIRST re-measure read `91 | 5 | 2 | 0 | 1` — a MISS.** New failure: `check_derived_claims`,
*"derived:ledger_rows=408, stated:series_table_latest_row=403"* — cc appended five debt rows and
did not move the ARC-TOTAL series row, which is close-out obligation (d). **Directive 3 enforced
mechanically against this arc's own write-back; the gate was right.** Row re-derived whole off the
instrument, not typed as 403 + arithmetic.

**Final, at `ffd6b69`: `92 passed | 4 failed | 2 cannot-measure | 0 skipped | 1 guarded`, exit 1.**
`check_hot_path_purity` `[ok]` · `check_derived_claims` `[ok]` (13/13, `registered_check_count=99`)
· `check_arc_status_contract` `[ok]` auditing `arc_049.log` at BOTH baseline and re-measure — the
brief predicted cannot-measure at baseline; it was PASS both times.

Four FAILs, all the baseline four, none this arc's: ibgateway 4002 · monitor_tui stale pin ·
uncalled_entry_points (**no ratchet movement**) · untracked_attribution (the `.dmg`, still present,
deliberately not deleted).

**The predicted tuple was reached only AFTER the gate caught the omission. The prediction MISSED
on the first measurement of the merged tree.**

## BADGE

**I9 DISCHARGED. Clean `{I2, I3, I4, I5, I6, I7, I8, I9, I10, I11} = 10/12`, open = 2
(`I1` daemon capstone, `I12` freshness). Limiter STAYS RED.**
