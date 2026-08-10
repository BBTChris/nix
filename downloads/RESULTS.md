# RESULTS — ARC 013: delayed market data verified; the Stage 0 data decision recorded

**Status: ARC 013 complete.** Every success box checked.

**Headline: a delayed CME futures stream *does* flow on this account, at a measured 10 minutes —
not the documented 15–20.** ARC 012's "no tick stream at all" was accurate for what it measured and
is now **narrowed to real-time**, not overturned.

---

## Definition of success

| Box | State |
|---|---|
| All three modes attempted on MES; requested vs **granted** recorded | ✅ |
| Measured lag from multiple ticks, not the documented figure, not one sample | ✅ — n=8 and n=9 distinct exchange timestamps |
| Market-open state stated; closed ⇒ CANNOT-MEASURE | ✅ — **CME was open**, established two ways |
| Errors recorded verbatim with codes | ✅ — 354, 300, 10167, 2119, 2104 |
| ARC 012's claim confirmed or narrowed, with the change and reason visible | ✅ — narrowed, with a "correction of record" block |
| Stage 0 data decision written with reasoning and the explicit constraint | ✅ |
| `CHECK-DEBT.md` updated; D1.13 closed or re-scoped | ✅ — re-scoped, D1.14 split out |

---

## Part 0 — Was CME actually open? (precondition, established before anything else)

A closed market produces no ticks regardless of entitlement, so an absence of ticks is only
evidence about *entitlement* if the market was open. Established two ways deliberately, because
neither alone is sufficient — a schedule can be right while a venue is halted:

**Declared** — IBKR's own `tradingHours` for `MESU6`:

```
tradingHours : 20260809:1700-20260810:1600;20260810:1700-20260811:1600;...
liquidHours  : 20260810:0830-20260810:1600;...
timeZoneId   : US/Central

wall clock UTC : 2026-08-10 12:04:16 UTC
wall clock CT  : 2026-08-10 07:04:16 CDT (Monday)
  20260809:1700-20260810:1600   <== NOW INSIDE THIS SEGMENT
--> declared open right now: True
--> inside LIQUID (RTH) hours: False
```

**Empirical** — trades were present in the tape.

**Verdict: open, in the Globex overnight session, outside RTH.** So the market was thin but
trading, and an absence of ticks would have been interpretable. It did not come to that — ticks
flowed. Had the market been closed, every null result below would have been reported as
CANNOT-MEASURE rather than as evidence of absence.

Contract re-resolved rather than trusting ARC 012's number: `MESU6`, conId **793356217**, expiry
`20260918` — **matches** what ARC 012 recorded.

---

## Part 1 — All three market-data modes on MES

Measured 2026-08-10 12:05–12:07 UTC, `clientId=905`, 40 s observation window per mode.

| requested | **granted by IBKR** | ticks / 40s | error (verbatim) | measured lag |
|---|---|---|---|---|
| 1 real-time | **none — no grant callback at all** | **0** | `354: Requested market data is not subscribed. Check API status … and/or availability of delayed data.Delayed market data is available.MES SEP'26 (MESU6) /TOP/ALL` · `300: Can't find EId with tickerId:5` | n/a |
| 3 delayed | **3 = delayed** | 18 | `10167: Requested market data is not subscribed. Displaying delayed market data.` | **600.0–601.9 s**, mean 600.3 s, spread **1.9 s**, n=8 |
| 4 delayed-frozen | **3 = delayed — silently downgraded** | 19 | `10167` (as above) | **600.1–604.9 s**, mean 600.6 s, spread 4.8 s, n=9 |

Populated fields on both working modes: `bid, ask, last, close, volume, delayedLastTimestamp`.
Also seen, connection-level: `2119 Market data farm is connecting:usfuture`, `2104 Market data farm
connection is OK:usfuture`.

### The granted type is not the requested type — twice over

**Mode 4 was silently downgraded to 3.** Asking for delayed-frozen and assuming you received it
would misdescribe the feed.

**Mode 1 received no grant at all, and this nearly produced a false report.** The first run showed
`granted=1` for real-time — but `ib_async`'s `Ticker.marketDataType` **defaults to `1`**, so that
was an unset field, not a grant. A naive read would have reported "IBKR granted real-time" for a
subscription that returned **zero ticks and error 354**.

Verified rather than assumed, by sentinelling the field to `0` immediately after subscribing so
only a genuine callback could move it:

```
requested=1  field after 12s=0  -> NO callback (field never set by IBKR)   errors=[354]
requested=3  field after 12s=3  -> AFFIRMATIVE GRANT = 3                   errors=[]
requested=4  field after 12s=3  -> AFFIRMATIVE GRANT = 3                   errors=[10167]
```

### The lag is 10 minutes, measured — not the documented 15–20

Measured from the exchange timestamp the feed itself carries (tick **88** →
`delayedLastTimestamp`) against wall clock at receipt, deduplicated on the exchange timestamp so
repeated updates re-reporting one trade can't manufacture agreement:

```
delayedLastTimestamp   exch=11:55:54 recv=12:05:55  lag=601.9s (10.03 min)
delayedLastTimestamp   exch=11:55:59 recv=12:05:59  lag=600.1s (10.00 min)
delayedLastTimestamp   exch=11:56:04 recv=12:06:04  lag=600.1s (10.00 min)
delayedLastTimestamp   exch=11:56:09 recv=12:06:09  lag=600.1s (10.00 min)
delayedLastTimestamp   exch=11:56:17 recv=12:06:17  lag=600.0s (10.00 min)
delayedLastTimestamp   exch=11:56:24 recv=12:06:24  lag=600.1s (10.00 min)
delayedLastTimestamp   exch=11:56:29 recv=12:06:29  lag=600.1s (10.00 min)
delayedLastTimestamp   exch=11:56:32 recv=12:06:32  lag=600.1s (10.00 min)

min 600.0s  max 601.9s  spread 1.9s  mean 600.3s
```

**The spread is what makes this a result rather than an anecdote.** 1.9 s across 8 distinct
timestamps is a steady pipeline delay; a stale first tick followed by live data would have shown a
collapsing lag. This is exactly why the arc demanded multiple samples.

### `reqHistoricalTicks` is delayed by the same ~10 minutes — and this was visible all along

It is **not** a real-time back door. Worse, the evidence was sitting in ARC 010's own banked output
and went unread:

```
ARC 010 (reqHistoricalTicks)   now=09:39:54  newest tick=09:29:30  age=624.0s = 10.40 min
ARC 013 (reqHistoricalTicks)   now=12:04:16  newest tick=11:54:12  age=604.0s = 10.07 min
```

ARC 010 printed both numbers — `connectionTime: 2026-08-10 09:39:54` and
`HistoricalTickLast(time=2026-08-10 09:29:30 …)` — and I never computed the difference. The
10-minute delay has been characterising this account since the first probe.

**This is the same failure mode as ARC 012's CHECK-DEBT miscount**: a number present in the output,
unread. Both are cheap to catch mechanically and expensive to catch by eye, which is the argument
for doctrine B.7 (debt **D2.8**) rather than more careful reading.

**Consequence:** the "polled fallback" ARC 010 and ARC 012 both relied on is a *delayed* polled
fallback. The Stage 0 feed is delayed **and** polled, which is sharper than either arc recorded.

---

## Part 2 — Reconciling with ARC 012

**ARC 012's claim was too broad and is narrowed, not overturned.** It said *"no CME futures tick
stream is available on this account at all."*

That was **accurate for what it measured**. `reqTickByTickData` is a **real-time-only** request
path — delayed data never arrives on it, which is exactly why `Err 10189` came back. ARC 012 did
not test `reqMarketDataType` → `reqMktData`, so the delayed path was never in its scope.

Corrected in `dev_and_services_plan.md` under an explicit **"Correction of record"** block that
states what the earlier arcs measured, why the conclusion was sound for that measurement, and what
later measurement narrowed it. **Not silently overwritten** — the record shows why it changed.

Standing correctly, unchanged:

- **No real-time stream.** Error 354 with zero ticks; `10189` on the tick-by-tick path.
- **Not solvable by instrument selection or code.** `10189` names the product class `CME FUT`, not
  the contract. Real-time is an account-level subscription.

---

## Part 3 — The Stage 0 data decision, written down

Added to `dev_and_services_plan.md` as a top-level `## DECISION` section, deliberately written to
be legible to someone arriving with none of this session's context.

**Decision: Stage 0 runs on IBKR's free market data. No subscription will be purchased.** Recorded
as *settled*, superseding the earlier records in that file which surfaced it as pending — with a
note that only new information about the Tradovate cutover could reopen it.

**What it forbids, stated as a constraint rather than a footnote.** On a 10-minute delayed polled
feed these are meaningless and must not be produced, cited, or carried forward: latency
measurements of any kind; fill realism, slippage or spread-capture estimates; strategy performance
figures (P&L, Sharpe, hit rate, drawdown, expectancy); **any claim about edge** — including hedged
ones like "directionally encouraging".

What Stage 0 *is* for: the plumbing — connection handling, reconnect and session recovery, bar
construction, persistence, the broker-datafeed interface shape, gate and risk-path wiring, order
lifecycle mechanics. All fully exercisable on delayed data, because they are about structure and
correctness rather than price.

The section carries a direct address to a future reader:

> **If you are reading this because a document you are holding cites a Stage 0 backtest or paper
> P&L as evidence of anything — that document is misusing it.** The number is not weak evidence; it
> is not evidence. The feed it was computed from was ten minutes behind the market, measured, on
> 2026-08-10. Discard the conclusion, keep the plumbing lesson.

Also recorded: the Crucible pipeline's scoring gates cannot be run to a *verdict* at Stage 0, only
to prove the pipeline mechanically executes.

**Carried forward for broker-datafeed** — four points, the last of which is new from this arc's
measurements: build against delayed + polled as the Stage 0 shape; bar immutability stays Nix's own
obligation regardless of feed; the vendor-neutral seam must encode no assumption that only holds
for a delayed or polled feed (Tradovate is expected to be real-time and push-based, so "data
arrives late" leaking into the interface is a defect); and **never infer the mode from the
request** — read and record the *granted* type and treat a downgrade as a real event.

---

## CHECK-DEBT

**D1.13 re-scoped.** Its subscription half is **closed** by the decision above. What remains is a
gate: assert the *granted* `marketDataType` matches what Stage 0 declares and **FAIL on a silent
downgrade** — motivated directly by mode 4 being granted as 3. To be built with broker-datafeed,
not here (this arc is measurement and documentation; no new gates, per scope).

**D1.14 split out**: bar immutability on a re-requestable feed. Separated because it discharges in
a different arc and stays owed even after Tradovate's real-time feed arrives.

**24 → 25 open**, counted mechanically (D1 ×12, D2 ×12, D3 ×1) — not hand-counted, after ARC 012
established that hand-counting this table gets it wrong.

---

## State at close

- `verify.py`: **6 passed, 0 failed, 0 cannot measure, 0 skipped — exit 0**
- Test suite: **153 passed**
- Branch `arc-013-delayed-feed`, cut fresh from `main` at `7ebb32d` (PR #9 merge)
- Docs changed: `dev_and_services_plan.md`, `CHECK-DEBT.md`

## Still owed

1. **D1.12** — reboot test; boot behaviour unverified (out of scope this arc).
2. **D1.13** — granted-market-data-type gate, with broker-datafeed.
3. **D1.14** — bar immutability gate, with broker-datafeed.
4. **D2.8** — the doctrine-B.7 harness. Two measured instances now argue for it: the CHECK-DEBT
   miscount and the unread 10-minute delay in ARC 010's own output.
