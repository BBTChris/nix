# ARC 013 — Delayed Market Data Verification; Record the Stage 0 Data Decision

## Context

ARC 012 confirmed `Err 10189` on both ES and MES — no **real-time** tick stream on account
DUR250018, and the error names the product class (`CME FUT`) rather than the contract, so no
instrument selection reaches it. ARC 012's report concludes *"no CME futures tick stream is
available on this account at all."*

**That conclusion is untested for one case: delayed data.** IBKR provides free delayed market data
on paper accounts by default; real-time requires a subscription mirrored from a linked funded live
account, which this account does not have. Critically, **delayed data does not arrive via
`reqTickByTickData` at all** — that path is real-time-only, which is why 10189 is what came back.
Delayed data arrives through `reqMktData` *after* setting the market-data type.

So the open question is narrow and worth settling: **does a delayed stream flow on CME futures on
this account, and with what actual lag?**

The human has already made the commercial decision — **Stage 0 runs on IBKR's free feed; no
market-data subscription will be purchased for IBKR.** This arc does not revisit that. It measures
what "free" actually delivers, and writes the decision down with its consequences.

## Part 1 — Measure all three market-data modes on MES

Connect via `ib_async` on **clientId=905** (never 1, reserved for the future Risk Engine; never 0,
permanently excluded — it implicitly adopts manually-placed TWS orders). Use MES front month
(`MESU6`, conId 793356217 as measured in ARC 012 — re-resolve rather than trusting that number).

For each of the three market-data types, using `ib.reqMarketDataType(n)` then `reqMktData`:

| n | mode |
|---|---|
| 1 | real-time (expected to fail — this is the control) |
| 3 | delayed |
| 4 | delayed-frozen |

For each, record:
- Whether ticks arrive at all, and how many within a fixed observation window
- The **ticker type IBKR actually returns** — note that a delayed request can be silently
  downgraded or upgraded, and `ib_async` exposes the granted type; report the *granted* type, not
  the requested one
- Any error code returned (10189, 10197, 354, or otherwise) verbatim
- **The measured lag**: tick timestamp vs wall clock at receipt. **Do not report the documented
  15–20 minute figure — measure it.** Report the observed spread across several ticks, not a single
  sample, since a one-shot reading can't distinguish steady lag from a stale first tick.

Run this **while CME is open** so the absence of ticks means something. If the market is closed at
run time, say so explicitly and treat a null result as CANNOT-MEASURE rather than as evidence of
absence — a closed market produces no ticks regardless of entitlement, and reporting that as "no
delayed data available" would be a false negative.

Clean disconnect. Report as a plain table: mode requested / mode granted / ticks / error / measured
lag.

## Part 2 — Reconcile with ARC 012's conclusion

ARC 012 stated no CME futures tick stream exists on this account. Depending on Part 1's result,
that statement is either confirmed, or too broad and needs narrowing to *real-time*.

- If delayed **works**: correct the claim in `dev_and_services_plan.md` and `CHECK-DEBT.md` to say
  no *real-time* stream exists, and that a delayed stream does. Don't quietly overwrite — note that
  ARC 012's statement was accurate for what it measured and is being narrowed by a later
  measurement, so the record shows why it changed.
- If delayed **also fails**: ARC 012's conclusion stands as written and this arc confirms it across
  a second request path. Say so plainly — a confirming negative is a real result, not a wasted arc.

## Part 3 — Record the Stage 0 data decision and its constraints

Add to `docs/dev_and_services_plan.md`'s IBKR section, as a stated decision with reasoning so a
later author does not relitigate it:

**Decision:** Stage 0 runs on IBKR's free market data. No subscription will be purchased.

**Reasoning:** IBKR is permanently paper-only Stage 0; Tradovate is the live broker at cutover.
`dev_and_services_plan.md` already states strategy results from the IBKR phase are not to be
trusted. A subscription bought here is discarded at that boundary.

**What this forbids — state as a constraint, not a footnote.** On free data, no latency
measurement, fill-realism claim, slippage estimate, or strategy performance figure from the IBKR
phase carries meaning. Stage 0 exercises the *plumbing* — connection handling, reconnect, bar
construction, the broker-datafeed interface shape — and says nothing about *edge*. Any later
document citing a Stage 0 backtest or paper P&L as evidence of anything is misusing it. Write this
so it is legible to someone who arrives without this session's context.

**What it means for broker-datafeed's design**, carried forward explicitly:
- Whatever Part 1 establishes about the available stream (or its absence) is the feed shape the
  module must be built against at Stage 0
- Bar immutability remains Nix's own obligation regardless — polled history is re-requestable and
  can return revised values, so the bar builder needs its own seal-and-never-rewrite rule
- The vendor-neutral interface must not encode any assumption that only holds for a delayed or
  polled feed, since Tradovate's shape is expected to differ

Update `docs/CHECK-DEBT.md`: close or re-scope **D1.13** in light of the decision and Part 1's
measurement. If a gate is now owed for whatever data path Stage 0 actually uses, record it rather
than building it here — this arc is measurement and documentation, not construction.

## Definition of success

- [ ] All three market-data modes attempted on MES; requested vs **granted** type recorded for each
- [ ] Measured lag reported from multiple ticks, not the documented figure and not a single sample
- [ ] Market-open state at run time stated; a closed market treated as CANNOT-MEASURE, not as
      evidence of absence
- [ ] Errors recorded verbatim with codes
- [ ] ARC 012's "no tick stream at all" claim either confirmed or narrowed, with the change and its
      reason visible in the record rather than silently overwritten
- [ ] Stage 0 data decision written into `dev_and_services_plan.md` with reasoning and the explicit
      constraint on what Stage 0 numbers may be used for
- [ ] `CHECK-DEBT.md` updated; D1.13 closed or re-scoped

## Out of scope

- No subscription purchase, and no recommendation to make one — the decision is made
- No broker-datafeed or broker-order code
- No new check gates — record what is owed, build it in its own arc
- No reboot (D1.12 stays open until separately authorized)

**Standing gate — do not skip:** append a summary to the end of `~/nix/sessions/SESSION.md`,
overwrite `~/nix/downloads/RESULTS.md` with this arc's results, `cat` both files, and paste their
resulting state into the response before declaring `**** ARC completed ****`.
