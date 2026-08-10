## Development and Services Plan — Nix

# GitHub
Nix will have a private repo tracking versioning; dev engineer will set up and provide credentials.

# Backblaze
Nix will use Backblaze as the backup target; dev engineer will set up and provide API key and
credentials.

# IBKR
**Stage 0** — IBKR is the initial data feed and test broker, since both broker libraries are
abstracted behind the vendor-neutral seam. This carries the majority of module development.
Dev engineer will set up the account and provide account credentials and API key.
Never trust strategy results from the IBKR phase — plumbing only. **See the Stage 0 data decision
below for what that forbids concretely, and why: Stage 0 runs on a measured 10-minute delayed
feed.**

**IB Gateway auth expectation (ARC 006, so it's not tribal knowledge):** IBKR does not support
headless first-auth — the initial GUI login + IB Key 2FA approval on the human operator's phone
is a hard vendor constraint, not a tooling gap, and cannot be scripted or worked around. Paper
socket port is 4002 (live is 4001, not used at Stage 0); "Enable ActiveX and Socket Clients" and
trusted IP `127.0.0.1` must be set in the GUI after first login, since these live in the per-user
`Jts` profile that doesn't exist until then. Auto-restart-vs-auto-logoff is likewise a post-login
GUI setting — unreachable before the first human login creates the profile.

**Lock-and-Exit setting changed to Auto restart (ARC 010).** It was *Auto logoff at 23:45*, which
tore the session down nightly and forced a full 2FA re-login **daily**. It is now *Auto restart at
03:00*: the JVM cycles but the session survives, so the human's IB Key tap drops to IBKR's own
mandatory weekly re-auth. `jts.ini` `[u:<hash>] AutoRestart=1` was verified on disk in ARC 010;
the **03:00 time itself is not verifiable** — it lives in the `IBGZENC`-encrypted settings store,
and `check_ibgateway_config.py` reports only what it can actually measure.

**Where the API settings actually live (ARC 010, measured).** `~/Jts/jts.ini` carries **only**
`TrustedIPs` and `AutoRestart` in plaintext. The socket port, `ReadOnlyApi`, and the
localhost-only flag are in the encrypted store. Note the trap: `jts.ini`'s
`[IBGateway] LocalServerPort=4000` is **not** the API port — it is the SSL tunnel to
`ndc1.ibllc.com`. Anything that "reads the port from jts.ini" reads 4000 and is wrong. Nix's
expected values are therefore declared in `checks/ibgateway_expected.json` and asserted against
reality.

**Market data: no *real-time* CME futures stream; a *delayed* stream does flow, at a measured
10 minutes (ARC 010 on ES, ARC 012 on MES, ARC 013 on all three market-data modes).**

> **Correction of record — the earlier claim was too broad, and this is why it changed.**
> ARC 010 and ARC 012 concluded *"no CME futures tick stream is available on this account at
> all."* That was **accurate for what those arcs measured** — `reqTickByTickData`, which is a
> **real-time-only** request path. Delayed data never arrives on it, which is precisely why
> `Err 10189` was the answer. ARC 013 tested the path those arcs never used —
> `reqMarketDataType(n)` then `reqMktData` — and found a delayed stream that works. The earlier
> statement is **narrowed to real-time**, not overturned: no measurement has been contradicted,
> only extended.

Measured on `MESU6` (conId 793356217), 2026-08-10 12:05–12:07 UTC, **CME confirmed open** (Globex
segment `20260809:1700-20260810:1600` CT; outside RTH, which begins 08:30 CT):

| requested | **granted by IBKR** | ticks / 40s | error (verbatim) | measured lag |
|---|---|---|---|---|
| 1 real-time | **none — no grant callback at all** | **0** | `354: Requested market data is not subscribed. … Delayed market data is available. MES SEP'26 (MESU6) /TOP/ALL` | n/a |
| 3 delayed | **3 delayed** | 18 | `10167: Requested market data is not subscribed. Displaying delayed market data.` | **600.0–601.9 s** (mean 600.3 s, spread 1.9 s, n=8) |
| 4 delayed-frozen | **3 delayed — silently downgraded** | 19 | `10167` (as above) | **600.1–604.9 s** (mean 600.6 s, spread 4.8 s, n=9) |

Four things in that table are load-bearing and easy to get wrong:

1. **Report the granted type, never the requested one.** Mode 4 was silently downgraded to 3.
   Asking for delayed-frozen and assuming you got it would misdescribe the feed.
2. **Mode 1 receives no grant at all.** `ib_async`'s `Ticker.marketDataType` *defaults* to `1`, so
   a naive read reports "granted real-time" for a subscription that returned zero ticks and error
   354. Verified by sentinelling the field to `0` after subscribing: for mode 1 it never moved, so
   IBKR sent no `marketDataType` callback. For modes 3 and 4 it moved to `3`.
3. **The lag is 10 minutes, not the documented 15–20.** Measured from the exchange timestamp the
   feed itself carries (tick 88 → `delayedLastTimestamp`) against wall clock at receipt, across
   distinct timestamps rather than one sample. The spread of **1.9 s over 8 samples** is what
   makes it a steady pipeline delay rather than a stale first tick.
4. **`reqHistoricalTicks` is delayed by the same ~10 minutes** — it is not a real-time back door.
   This was visible in ARC 010's own output and went unread: its newest historical tick was
   `09:29:30` against a connection time of `09:39:54`, i.e. **624 s = 10.4 min** old. ARC 013
   re-measured 604 s. The "polled fallback" both earlier arcs relied on is a *delayed* polled
   fallback.

**Still not solvable by instrument selection or by code.** `10189` names the *product class*
(`CME FUT`), not the contract; MES is CME FUT exactly as ES is. Real-time is an account-level
subscription and the only place it changes is IBKR Account Management. See the Stage 0 data
decision below — that question is now closed, not open.

Consequence for the broker-datafeed spec, and it is **sharper** than ARC 012 recorded: the Stage 0
feed is **delayed and polled**. Bar immutability remains an obligation Nix must enforce itself —
polled history is re-requestable and can return revised values, so the bar builder needs its own
seal-and-never-rewrite rule regardless of feed.

## DECISION — Stage 0 runs on IBKR's free market data (ARC 013, settled)

**No market-data subscription will be purchased for IBKR. This is decided, not open.** Earlier
records in this file surfaced it as a pending human decision; it has been made, and this section
supersedes those. Do not reopen it without new information about the *Tradovate* cutover, which is
the only thing that could change the reasoning.

**Reasoning.** IBKR is permanently paper-only Stage 0; Tradovate is the live broker at cutover. Any
subscription bought here is discarded at that boundary. This file has said since ARC 006 that
strategy results from the IBKR phase are not to be trusted — paying for data does not change that,
because the constraint is the *phase*, not the data quality.

### What this forbids — a constraint, not a footnote

Stage 0 runs on a **10-minute delayed, polled** feed. On that feed the following are **meaningless
and must not be produced, cited, or carried forward**:

- **Latency measurements** of any kind — tick-to-signal, signal-to-order, round-trip. The feed's
  own 10-minute delay dominates every number by three orders of magnitude.
- **Fill realism, slippage, or spread-capture estimates.** Fills are simulated against prices that
  are ten minutes stale; the market being modelled no longer exists at the moment of the decision.
- **Strategy performance figures** — P&L, Sharpe, hit rate, drawdown, expectancy — from any Stage 0
  backtest or paper run.
- **Any claim about *edge*.** Not "weak evidence of edge", not "directionally encouraging". None.

**What Stage 0 *is* for:** exercising the **plumbing**. Connection handling, reconnect and session
recovery, bar construction, persistence, the shape of the broker-datafeed interface, gate and
risk-path wiring, order lifecycle mechanics against a paper account. These are all fully
exercisable on delayed data, because they are about *structure and correctness*, not about price.

> **If you are reading this because a document you are holding cites a Stage 0 backtest or paper
> P&L as evidence of anything — that document is misusing it.** The number is not weak evidence; it
> is not evidence. The feed it was computed from was ten minutes behind the market, measured, on
> 2026-08-10. Discard the conclusion, keep the plumbing lesson.

The Crucible pipeline's scoring gates (`nix-strategy-evaluator-pipeline-6.docx`) therefore cannot
be run to a *verdict* at Stage 0. They can be run to prove the pipeline mechanically executes.

### What it means for broker-datafeed's design

Carried forward explicitly, because these outlive Stage 0:

1. **Build against the feed that actually exists**: delayed (`reqMarketDataType(3)` → `reqMktData`)
   plus polled history (`reqHistoricalTicks`, itself ~10 min delayed). That is the Stage 0 shape.
2. **Bar immutability is Nix's own obligation, regardless of feed.** Polled history is
   re-requestable and can return revised values, so the bar builder needs its own
   seal-and-never-rewrite rule. This does not become unnecessary when a real-time feed arrives.
3. **The vendor-neutral interface must encode no assumption that holds only for a delayed or
   polled feed.** Tradovate's shape is expected to differ — real-time, push-based. Anything in the
   seam that assumes "data arrives late", "data arrives on request", or "timestamps trail wall
   clock by a constant" is a Stage 0 artifact leaking into a permanent interface, and is a defect.
4. **Never infer the market-data mode from what was requested.** ARC 013 measured a request for
   delayed-frozen (4) being silently granted as delayed (3), and a request for real-time (1)
   returning no grant callback at all while the client library's field still read `1` by default.
   The feed module must read and record the *granted* type and treat a downgrade as a real event.

**Margin: MES is affordable, ES is not (ARC 012, measured via `whatIfOrderAsync`).**
Account DUR250018, net liquidation **20,344.34 USD**:

| | ES (`ESU6`) | MES (`MESU6`) |
|---|---|---|
| conId | 649180671 | 793356217 |
| expiry | 20260918 | 20260918 |
| multiplier | 50 | **5** |
| initial margin | 35,035.87 | **3,503.59** |
| maintenance margin | 25,029.29 | 2,502.93 |
| headroom vs net liq | **−14,691.53** | **+16,840.75** |
| contracts affordable | **0** — rejected, err 201 | **5** |

Margin scales at exactly 10.0×, tracking the multiplier. **MES is the instrument to develop
against at Stage 0** — but note it fixes *margin only*. The two problems are independent and only
one of them has been solved.

Method note for whoever repeats this: `ib.whatIfOrder()` (sync) returns an **empty** `OrderState`
here — its internal wait expires before IB answers, and the rejection then surfaces seconds later
against an unrelated request. Use `whatIfOrderAsync` awaited under an explicit timeout, or the
margin figures come back as `None` and read as "undetermined" when they are merely late.

**`clientId` allocation scheme (ARC 008 — a decision being recorded here, not a value discovered
from the environment):** the TWS API keys every concurrent session by `clientId`; two processes
sharing one id collide, and id `0` additionally binds to manually-placed TWS orders, which is
exactly the order-ownership ambiguity the mission scope forbids. The space is therefore allocated
deliberately, not first-come.

| `clientId` | reserved for | status |
|---|---|---|
| `0` | never used — implicit adoption of manual/TWS-placed orders | permanently excluded |
| `1` | the live Risk Engine process | **reserved — not yet built; connect nothing else on `1`** |
| `905` | diagnostics / tooling (`check_ibgateway_config.py` and ad-hoc connection probes) | allocated |

Ids outside this table are unallocated: assign one here before using it, not at the call site.

# Transition to DataBento and Tradovate
Once the system is near release-candidate stage, we transition to the final stream and broker
providers, DataBento and Tradovate. At this point the user funds a live account so we have
continuous access to the demo account. User pays $25/mo for API access.

**Stage 1** — DataBento historical data and servers (much cheaper to develop and test) +
Tradovate demo account and API.

**Stage 2** — Very near release candidate: DataBento live data + Tradovate demo account for
proof of system.

**Stage 3** — Cut over to QuantVPS; DataBento live + Tradovate live, **micro contracts only**.

**Stage 4** — DataBento live + Tradovate **mini** contracts.

(The two vendor cutovers — datafeed and broker — remain independent gates per the risk spec's
arc R6; the stages above sequence when each gate opens.)

# Boot persistence — `nix-xvfb.service` and `nix-ibgateway.service` (ARC 011)

Before ARC 011, Xvfb and IB Gateway existed **only as manually-started foreground jobs**. Neither
survived a reboot; recovering from one meant a VNC session just to get the processes running. Two
units now own them.

**Cutover performed ARC 012 (2026-08-10).** Both processes are now systemd-owned, verified by
cgroup rather than by unit status:

| | before cutover | after cutover |
|---|---|---|
| Xvfb | PID 236457, `user.slice/user-1000.slice/session-231.scope` | PID 260814, `/system.slice/nix-xvfb.service` |
| Gateway JVM | PID 236482, `session-231.scope` | PID 261046, `/system.slice/nix-ibgateway.service` |
| API socket 4002 | served by 236482 | served by **261046 — the unit's own `MainPID`** |

`ExecStartPre` (the `xdpyinfo` display-readiness gate) exited `0/SUCCESS`, so the Gateway→display
dependency worked as a real precondition and not as incidental ordering. Both units report
`NRestarts=0`. `verify.py`: 6 passed, exit 0, with `check_ibgateway_service` now reading
`enabled/active` for both units where it read `enabled/inactive` before.

> **⚠ Boot behaviour is still NOT verified — CHECK-DEBT D1.12 remains open.** No reboot was
> performed; it was offered as a separate authorization and declined, because it costs a second IB
> Key tap. **`systemctl is-enabled` is a declaration that these units start at boot, not evidence
> that they do.** Discharge condition: reboot, then run `check_ibgateway_service` **before anyone
> touches the console** — a human logging in first contaminates the measurement by creating the
> very state the check is trying to observe independently.

**The unreachable-vs-misconfigured distinction was confirmed against reality during the cutover**,
not just against ARC 010's planted port. With the Gateway stopped and nothing on 4002:
`check_ibgateway_config` → `CANNOT_MEASURE` (exit 2, *"Gateway down or not logged in; that is not
a misconfiguration"*); `check_ibgateway_service` → `FAIL` (exit 1, naming
`127.0.0.1:4002 (nix-ibgateway.service)`). Same observation, two gates, two correct and different
verdicts.

Gateway's API configuration **survived the restart** — `check_ibgateway_config` passed unchanged
afterwards, so the settings live in the profile rather than in process state.

> ## ⚠ Boot persistence is **not** unattended authentication
>
> After a reboot, Gateway comes back up **sitting on its login screen**, waiting for credentials
> and an IB Key 2FA tap on the operator's phone. The units guarantee the *process* returns, and
> nothing more. Gateway's own "Auto restart at 03:00" does not help here either — that is an
> internal application cycle that only fires while the process is already alive, so it does
> nothing after a reboot, a crash, or an OOM kill.
>
> Auth automation is **deliberately out of scope**: no credential automation, no IBC, no TOTP, no
> browser automation. IBKR is permanently paper-only Stage 0 plumbing and Tradovate is the live
> broker at cutover, so anything built against IBKR's auth flow is thrown away at that boundary —
> and one candidate approach is terms-grey. The manual IB Key tap is an accepted cost.

| unit | owns | restart policy |
|---|---|---|
| `nix-xvfb.service` | display `:99`, `-screen 0 1440x900x24`, `User=bbt` | `Restart=always` — a display server has no legitimate "finished" state |
| `nix-ibgateway.service` | `/home/bbt/ibgateway/ibgateway`, `DISPLAY=:99`, `User=bbt` | `Restart=on-failure` — survives a crash or OOM kill, does not fight a deliberate operator shutdown |

**Dependency is `BindsTo=`, not `Requires=`.** `Requires=` propagates a failed *start* and an
explicit stop, but leaves Gateway running when Xvfb dies on its own — and a Gateway whose X server
vanished is exactly the "unit active, thing unusable" state `check_ibgateway_service.py` exists to
catch. `BindsTo=` makes that state impossible instead of merely detectable. `After=` orders the two
on the way up, and an `ExecStartPre` polls `xdpyinfo` until the display genuinely answers —
ordering alone is not a real dependency, since Xvfb's unit is "active" milliseconds before the
display accepts clients.

**Neither unit joins `nix-trading.slice`, deliberately.** That slice is `AllowedCPUs=0-5` and
exists to mirror the risk spec §10 core map (0 OS, 1 capture, 2 Risk Engine, 3 Allocator, 4–5
pool). Neither Xvfb nor the Gateway JVM appears anywhere in that map — the trading path's broker
contact is the `broker-datafeed` and `broker-order` *libraries*, not this JVM. On QuantVPS the
slice is the whole 6-core box so membership would be a no-op; on this 20-core dev box it is a real
restriction, and confining a 768 MB-heap Swing/JavaFX JVM that runs G1GC with
`-XX:ParallelGCThreads=20` into cores 0–5 would put its GC pauses directly on the cores §11's
hot-path discipline exists to keep clear. Both units run in `system.slice`. When Tradovate becomes
trading-path at cutover, that membership gets decided against the core map on its own merits
rather than inherited from this Stage 0 decision.

Both units are written by `install.sh` and gated by `checks/check_ibgateway_service.py`, which
proves the display answers `xdpyinfo` and the API completes a real handshake — `systemctl
is-enabled` and process-alive are recorded as evidence, never as the verdict.

# Initial Dev Box
Minisforum MS-01 · 20 cores · 61 GB RAM · 1 TB HDD · 1G Ethernet

**Core discipline:** the spec's core map (cores 0–5) is pinned **identically** on this box; the
remaining 14 cores stay **outside** the trading core-set. Dev behavior must equal prod behavior —
no "optimizing" onto spare cores that production will not have. This box satisfies every spec
reference to "node02" (the Nix dev/execution node).

# QuantVPS
VPS Pro+ (https://www.quantvps.com/tradovate-vps)
16 GB DDR5 RAM · AMD Ryzen 6 cores · 150 GB NVMe · 3 Gbps NIC (burst 10 Gbps) ·
Ubuntu 26.04 LTS · same datacenter as Tradovate (latency 0.52 ms) — matches the spec's 6-core map
and platform line exactly.
