# ARC 037 Phase 0.4 — THE THREE SEAM FREEZES

Frozen BEFORE Stage 1 dispatch so six blind worktrees build against one shape.
Authority read directly from `docs/nics_risk_subsystem_spec_v1.3.md` (frozen).
Every literal below is a DECISION, and each carries the reddening plant that
proves the seam gate is not green over nothing.

---

## SEAM (a) — the realized-P&L event on Plane-1  (D3.220, keystone)

**WHICH §12.10 ROW.** No new event type. §12.10:744's inventory has no
realized-P&L row, and minting one would put a row the spec never authorised into
the money record. The figure RIDES the rows that already book a realization:

  * `closed`            — §9's terminal round trip
  * `protective_exit`   — a protective close or scale-out
  * `sentinel_flatten`  — booked via marker replay (§12.1)

which is byte-for-byte `nixscore.ema.REALIZING_EVENT_TYPES` as ARC 036 froze it.
The figure lands in `plane1_event_log.payload` under the key
`nixscore.ema.REALIZED_FIELD == "realized_pnl"`, beside `payload.symbol`, via
`EventRow.fields` (`plane1_sink._values_clause` serialises `fields` into the
JSONB payload). §12.10:768's own rule: *"the final trail level rides the `closed`
row"* — a per-trade figure riding its terminal row is that pattern, not a new one.

**COMPUTED WHERE.** `scripts/nixrisk/realized.py` (new), a pure function over
the trade's own entry and exit facts:

    realized = direction * (exit_price - entry_price) * qty * point_value
             - commission_in - commission_out - fees - slippage_cost

net of the modelled costs the sizing path already knows (§7:480's
`slippage_pad`, §6.5:409-410 *"changes on fills **and commissions/fees**, which
debit on close"*). NOT the account balance delta: `flatten.ScoringSink.
book_realized` carries an account-level delta that cannot be keyed to
`(strategy_id, symbol)`, and §6.6:448 locks the pair as the canonical key.

**WRITTEN BY WHOM, AT WHICH TRANSITION.** The **Limiter, sole writer** (§9 — no
new writers, ever). The write happens inside the existing exit booking, at the
closed / protective-exit lifecycle transition, in `nixrisk.flatten`'s `_book`.
No second writer, no new port, no new daemon.

**CLOSED-ONLY IS THE LOAD-BEARING HALF.** §6.6:435 — *"Realized P&L only —
closed trades. Unrealized/paper gains never steer capital (a green open position
can reverse before it closes)."* The computed figure is a function of the EXIT
FILL and of nothing else; no mark, no peak, no high-water value may reach it.

**THE SEAM GATE REDDENS ON — "written but not read".** `check_realized_pnl`
drives a real close, reads the row back out of `nix_plane1` **by SQL**, folds it
through `nixscore.ema.RealizedEmaEngine`, and requires the EMA to ADVANCE off
that row. Plants that MUST redden:
  1. the writer stops emitting `realized_pnl` -> `MissingRealized` names the key;
  2. the figure is written as the OPEN MARK (peak) rather than the close ->
     an arm drives green-while-open -> closes-red and requires the written
     figure to equal the CLOSE and to be NEGATIVE;
  3. the row lands in Plane-1 and the engine is fed a FIXTURE instead of the
     written row -> the arm asserts the EMA moved from the value the DATABASE
     holds, sourced by `SELECT`, never from a literal.

---

## SEAM (b) — the weight function  (D3.260)

§6.6:459 gives the Allocator the read *"to weight sizing"* and **the frozen spec
fixes no transform**. This is the architect ruling the brief's 0.4 commissions.

**THE TRANSFORM (frozen).** Ordinal in the RANK, never in the score — the score
is Scoring's to compute (§6.6:461) and a consumer deriving a weight from an EMA
magnitude would be doing allocation judgment inside the gate.

    NEUTRAL_WEIGHT  = 1.0
    WEIGHT_STEP     = 0.25
    WEIGHT_FLOOR    = 0.60
    WEIGHT_CEILING  = 1.40

    raw(rank, n)    = 1.0 + WEIGHT_STEP * ((n + 1) / 2 - rank)
    weight(rank, n) = min(WEIGHT_CEILING, max(WEIGHT_FLOOR, raw(rank, n)))

  * rank 1 is the best (highest realized-P&L EMA) — §6.6:431 *"Feed the winners."*
  * the neutral point is the MEDIAN rank: `raw == 1.0` exactly at
    `rank == (n+1)/2`, so a field's total weighted risk is centred on unweighted.
  * **DECLARED NEUTRAL CASES, all exactly 1.0**: FCFS policy (every fallback
    route), an absent pair-row, tied EMAs, cold start, and `n == 1` — a single
    contender carries no ordering information and must not be re-sized by a race
    it did not have. This preserves §6.6:455's FCFS neutrality exactly.
  * **THE CLAMP GENUINELY BINDS.** At `n = 8`, `raw(1, 8) = 1.875 > 1.40` and
    `raw(8, 8) = 0.125 < 0.60`. The bound is reachable by a drivable rank, not
    an unreachable decoration. §6.6:443 cautions early realized samples are thin,
    which is exactly why an unbounded upsize off a two-close history is refused.

**WHERE IT IS APPLIED.** To §7:478's **risk budget** — `per_trade_risk_$` is
multiplied by the weight BEFORE `risk_contracts = floor(...)`. §7's own key
finding is that *"risk binds intraday, not margin"*, so the risk term is where a
weight actually moves a size. Margin, symbol cap and the correlation-bucket cap
are NOT weighted: they are capital-safety ceilings, and scaling a safety ceiling
by a performance score is the direction that must never exist. The weight is
recorded on `SizingRationale.score_weight` (a new trailing field; `SEAM_REV` is
NOT bumped — `SizingRationale` is an in-process value, never on the §12.7 wire,
and this project's rule is that the literal moves when the BYTES move).

**THE SEAM GATE REDDENS ON — "a weight that never differs from neutral".**
`check_score_weighting` drives two ranked pairs through the real pathway and
requires **two DISTINCT contract counts** from two identical GOs that differ only
in their rank; an arm requires `weights` to contain at least two distinct values
whenever `policy is PERFORMANCE_WEIGHTED and n > 1`; a plant that pins the
transform to `NEUTRAL_WEIGHT` must FAIL, and the failure must name the constant.
A separate arm drives `n = 8` and requires the ceiling AND the floor to be the
binding term, named.

---

## SEAM (c) — the durable-quarantine ledger  (D3.250 / D3.251)

**THE BOOK.** `nixrisk.supervision.QuarantineLedger` — append-only, one
`write(2)` + one `fsync(2)` per record, JSON lines, 0600, sited beside the
existing `RestartLedger` (default: `<restart-ledger>.quarantine`). Two record
kinds and no more:

    {"kind":"quarantine","subject":...,"ts":...,"seq":...,"reason":...,
     "restarts_in_window":...,"cap":...,"window_s":...}
    {"kind":"restore","subject":...,"ts":...,"seq":...,"operator":...,
     "counter_floor":...}

Never rewritten; a restore is an APPEND that supersedes, never a deletion
(directive 6, and the same argument `RestartLedger` already makes for restarts).
A damaged line is REPORTED, never skipped — a quarantine that was written and
cannot be read is a resurrection the cap will not see.

**CONSULTED AT CONSTRUCTION.** `CrashLoopBreaker.__init__` folds the ledger into
`_quarantined` and `_floors` BEFORE it answers anything. §4:274 — *"Quarantine
is NOT auto-resurrected; return is operator-driven."* A supervision restart is
exactly a new `CrashLoopBreaker` over the same on-disk state, and that is the
event the book exists to survive.

**THE REASON MUST AGREE WITH THE LEDGER.** D3.250's second half: `may_relaunch`
returned a §18 reason that was MEASURABLY FALSE on the same object. The rebuilt
verdict carries the ledger's own `reason`, its `restarts_in_window` and its
`seq`, and the refusal text quotes them, so the reason cannot contradict the
record it was read from.

**THE SEAM GATE REDDENS ON — "durable in a table the breaker never queries".**
`check_quarantine_durability` writes a quarantine record, constructs a **FRESH**
breaker over that ledger in a **fresh process**, and requires
`is_quarantined -> True` and `may_relaunch -> (False, reason)` where the reason
names the ledger's recorded count. Plants that MUST redden:
  1. the constructor stops reading the book -> fresh breaker says NOT quarantined;
  2. the restore floor is kept in memory only -> a fresh breaker reports the
     PRE-restore count (D3.251 exactly);
  3. the book is written but `may_relaunch` reads only `_quarantined` populated
     by this process -> the reason disagrees with the ledger's own count.

---

## SEAM (d, carried) — mirror LIVENESS, not staleness  (D3.244)

Recorded here because sub-agent D builds against it and the distinction is the
whole point. **Staleness is an age over a table. Liveness is a fact about the
WRITER.** ARC 036 measured 144,699 RANKED decisions over 0.483 s from a corpse
because the only signal was the table's age.

The liveness signal is the **transport's own peer-disconnect event** — the SUB
socket's `zmq` monitor raises `EVENT_DISCONNECTED` when the publisher's process
dies and its `ipc://` peer goes away. That is an observation of the writer, not a
timeout, so the RANKED-from-a-corpse window collapses to disconnect-detection
latency instead of scaling with `stale_after_s`. A heartbeat deadline is carried
as the SECOND signal (a publisher that is alive but wedged never disconnects),
bounded far tighter than `stale_after_s`.

**Both signals fall back to FCFS and NEITHER may halt** — §6.6:467: *"a scoring
outage must NEVER halt order flow."* Liveness makes the fallback fire SOONER; it
may never make it fail.
