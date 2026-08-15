# ARC 031 — R3-A: The Allocator (Sizing Off the Mirror)

**Canonical path:** `/home/bbt/nix` (absolute, unmoved).
**`origin/main`:** `0f9c5b9` — **NOT pushed.** 0.2 is an operator ruling and it is still open.

---

## OPEN RULINGS RETURNED TO YOU

### 1. PUSH `main`? — 0.2, reported and NOT acted on

```
git fetch origin                    → clean
git log --oneline main..origin/main → 0 commits   (EMPTY — no remote divergence)
git log --oneline origin/main..main → 103 commits (94 inherited + 9 this arc)
```

**The brief said 92. It was 93 at `9858b37`** — the commit the brief itself names — **and 94 at the
real `HEAD`** when this arc opened. A fast-forward is mechanically safe. It is outward-facing on a
public repo, so it is yours.

### 2. D3.138 — two ratchet rows at the ceiling with no legal move (NEW, needs `CHECK-A9`)

`scripts/nixverify/gitenv.py` and `scripts/nixverify/registry.py` are at **2 of 2** re-ownings and
owned by `ARC 031`, which stops being able to pay the moment this arc's summary lands in
`SESSION.md`. Every move is closed to me:

- **Re-point to ARC 032** = a third re-owning = *exactly* the move that produced D3.120. Doing that
  in the same arc that discharged D3.120 by measurement would demonstrate having learned nothing.
- **Real coverage** = dishonest here, and this was measured rather than assumed:
  `test_gitenv_hostile.py` already drives `scrubbed_env` with the both-halves control (each
  invocation runs UNSCRUBBED first and must report the DECOY repo). A second instrument is what
  doctrine C.9 forbids.
- **An `exclusions` move** needs a new `CHECK-A<n>`; CHECK-A8 is scoped to the original thirteen and
  rule 14 requires the ruling be recorded, because the gate cannot tell an authorized move from a
  laundering one.

**Recommend (a): a `CHECK-A9` extending the exclusion to these two on the C.9 grounds above.** The
alternative is raising the operator's ceiling, which sets the precedent the ceiling exists to refuse.
Until then `check_artifact_gate_coverage` reads **CANNOT_MEASURE** after this arc closes — the honest
statement that a real debt has an owner who cannot pay.

### 3. D3.136 — §7's correlation-bucket cap has NO production input path (NEW)

The cap prices exposure as `(stop_ticks + slippage_pad) × tick_value × contracts`, so applying it to
positions **already** in a bucket needs each held position's stop distance. The published
`PositionRow` carries `trade_id, symbol, strategy_id, size, margin, state` — **no stop distance.**
It lives in the Limiter's stop book, which is not published. Both routes are closed: reading the
stop book is the cross-table skew §6.4 refuses in the same breath as it fixes one snapshot, and
putting the distance on the published row is a `SEAM_REV` bump plus your ruling.

**Three gates were green while the cap could not run.** C drove `caps.admit` with `Exposure` rows it
constructed; B drove `BucketCapPort` with `None`. The argument between them was never made until
Stage 2 made it. The direction is measured, not asserted: an unpriced position valued at zero makes
the bucket look emptier, and an emptier bucket **admits more**.

### 4. D3.126 — the frozen spec contradicts itself on instrument-selection ordering (NEW)

§3:132 puts selection AFTER `min(risk, margin, symbol_cap)`; §7:488-493 makes it a function of the
risk-ideal ALONE and prior to the rest. They are not the same pipeline: under §3's literal order a
risk-ideal of 0.6 fulls floors to `min(...) = 0` and denies before micros are ever considered.
§7's order shipped, because `margin_contracts` divides by live per-symbol margin and `symbol_cap` is
per-instrument — neither term is DEFINED until the instrument is known. Needs a `SPEC-A<n>`.

### 5. The tap session — unchanged, still the only code-independent FAIL.

---

## WHAT LANDED

**`scripts/nixalloc/`** — the Allocator, the PERMISSIVE side (§2). Frozen consumer seam · mirror
consumer · sizing pathway · correlation-bucket cap · FCFS contention · Stage-2 wiring.
**Six new gates**, all BOUND: `check_measurement_path`, `check_allocator_seam`, `_mirror`, `_sizing`,
`_caps`, `_pathway`.

| | ARC 030 close | ARC 031 close |
|---|---|---|
| `verify.py` | 40 pass / **3 fail** / 1 cannot-measure / 0 skip / 1 guarded | **47 pass / 1 fail / 2 cannot-measure / 0 skip / 1 guarded** (before write-back)<br>**47 / 1 / 3 / 0 / 0** (after — see below) |
| registered checks | 45 | **51** |
| `pytest` | 1,620 passed / 2 skipped / 2 xfailed | **1,858 passed / 2 skipped / 2 xfailed / 0 failed** |
| binding | 43 BOUND / 2 ENR / 0 UNBOUND | **49 BOUND / 2 ENR / 0 UNBOUND** |
| CHECK-DEBT open | 155 | **173** |

**FAILs went 3 → 1.** The one that remains is `check_ibgateway_service`; two of the three
CANNOT_MEASUREs trace to that same dead port. D3.120 and D3.118 were discharged **by measurement**,
not by exemption.

**D3.138 predicted the third, and then caused it on purpose.** `verify.py` was run once before this
arc's summary landed in `SESSION.md` and once after. The single moved verdict is
`check_artifact_gate_coverage`, **GUARDED → CANNOT_MEASURE**, naming its own cause verbatim: *"2
rows [`gitenv.py:owner`, `registry.py:owner`]: 'ARC 031' has ALREADY COMPLETED — its close-out
summary is in sessions/SESSION.md. A guard may only name an arc that can still discharge it
(doctrine B.3)."* That is the trap D3.138 was opened to name, fired by the write-back itself, on
exactly the two rows the per-row headroom measurement refused to move. **Predicted before the fact,
not explained after it** — and it clears the moment you rule on `CHECK-A9`.

---

## THE THINGS THAT MEASURED ME WRONG

**Four §0a findings against the brief and against my own work, all of them caught by driving rather
than reading:**

1. **The 0.6 requirement caught my own seam gate.** "Prove the gate reddens on a change to EACH
   declared property" — the can-fail enumerates the fields and renames each in turn, and my first
   draft stayed **GREEN on eight of nine**, because `MIRRORED_FIELDS` was DERIVED from the same
   dataclass and moved with the rename. That is the ARC 028/029 seam-gate defect rebuilt one arc
   later, by an argument that sounded like doctrine C.4. Now a pinned literal at `SEAM_REV`.
2. **`check_measurement_path`'s own §7.12 question caught it mid-build:** `changed_paths` raises the
   SAME `RangeError` for "git could not answer" as for "the range is empty", so the empty-range arm
   passed **vacuously against every non-git tree**.
3. **The observer sweep was unfalsifiable on its first run:** comparing raw claim strings reported 13
   of 51 checks "differing", all of it random tempdir names — and a real order dependency would have
   been invisible inside that noise. Re-run at the granularity the gate itself judges: **zero**
   order-dependent claims across 306 observations.
4. **`check_coldstart` and `check_survival_watch` returned PASS over a completely empty directory**
   (D3.124, found by sub-agent A, re-measured here before anything changed). Both fixed.

**And three findings against the brief I wrote for the sub-agents** — each measured independently by
all three, from three worktrees with no visibility into each other:

- the `risks/allocator_*.config.json` I told them to create would have been a **second home** for
  §12A knobs that already have one (`check_risks_data_only` ARM 2 goes red — C *built* it in a
  scratch tree and ran the shipped gate rather than reasoning about it);
- "append rows, do not touch the series table" is **not satisfiable in this tree**, and a branch
  obeying both cannot be committed at all;
- the 0.70 deployable constant **is** a real knob (`limiter.deployable_pct`), read not carved.

---

## HYPOTHESES, AND HOW EACH WAS FALSIFIED-OR-NOT

| | measurement | the falsifier that proves it could have failed |
|---|---|---|
| **A1** atomicity | 4,000 generations, **13,924 concurrent observations, 0 torn** | a nine-slot torn mirror through the SAME harness: **83,971 tears caught** |
| **A2** half-built = stale | EMPTY / PARTIAL / unstamped / FRESH / STALE from one object, each naming itself | `_HeardBlind` collapses PARTIAL into EMPTY; `_AcceptsUnstamped` holds an unstamped picture |
| **A3** monotonic-by-source | an OLDER reading discarded, ES unmoved AND NQ unmoved (per-key) | `_Unguarded` regresses ES through the same assertions |
| **A4** read-only | 4 mutations **attempted**, the raised exception IS the evidence | a writable stand-in absorbs 3 of 4 through the same harness |
| **B1** execution order | a dead signal produces exactly `["tradability.tradable"]` — no mirror read, no arithmetic | `_SizesFirst` driven every run; the arm fails if the instrument reports U1 order for it |
| **C1** the SUM | two same-bucket positions where sum ⇒ 0 and max ⇒ 1 contract | the `max()` shape driven in **three** places, incl. inside the gate, which REFUSES to report unless the two still disagree |

---

## SAID IN THE GATES, NOT IMPLIED

- **`PERFORMANCE_WEIGHTED` is unreachable in production.** No Scoring writer exists (R5). **FCFS is
  the only policy this system can take.** A green from the caps gate means the fallback is correct,
  deterministic, arrival-ordered, symbol-neutral and cannot stall — not that any score was ever
  computed, published, read or acted on.
- The §7 cap **runs over an incomplete bucket** on any real snapshot (D3.136), and every §16 U5
  rationale says so.
- `tick_value` has **no source on this box** (D3.128) — injected, and every green is over specs the
  gate constructed.
- The one-versioned-row identity is proven **within one process** (D3.130); the cross-process wire is
  `picture.py`'s codec and nothing yet drives both ends together (D3.122).
- Blackout/calendar pollers (R4) and the strategy FSM: absent, and no gate implies otherwise.

---

## NEXT

**R3-B** — per-strategy state reflection through recovery, the in-flight-closing transitional state,
and the D3.136 wiring once you rule. Then **R4** blackouts.
