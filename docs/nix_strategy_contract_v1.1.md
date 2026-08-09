# Nix Strategy Contract — Pine v6 Port & Plugin Interface — v1.1.0

**`contract_rev: 1.1.0`** — every message carries this; the Nix side is built to it verbatim.
v1.1.0 supersedes v1.0.0 (16 ULTRAREVIEW defects fixed — changelog §12). Do not build to v1.0.0.

---

## 0. Purpose, audience, authority

**You are an AI agent.** You have been given (a) this document and (b) a TradingView **Pine v6
strategy**. Your job is to produce **one Python file, `strategy.py`**, that plugs into **Nix** —
BlackBox Trading LLC's autonomous futures platform — and reproduces the Pine strategy's *signal
logic* inside Nix's contract. You do not port the Pine strategy's sizing, order routing, or account
logic: Nix owns all of that, and this document defines the only mechanisms your file may touch.

Authority chain (do not violate, do not reinterpret):
1. `nics_risk_subsystem_spec_v1.3.md` — the frozen platform authority (spells the project NICS;
   read NICS as Nix). You never see it; its constraints are encoded here.
2. **This contract** — the complete and only interface available to a strategy.
3. The Pine source — *signal logic to translate*, never architecture to import.

If the Pine strategy requires something this contract does not provide, you **declare
`CANNOT MAP`** for that element (§7.5) and continue. You never improvise a mechanism, never open a
side channel, never approximate silently.

---

## 1. The hard boundary — approved mechanisms only

Your `strategy.py` process may interact with the world through **exactly three ZeroMQ sockets**
(§3) and **structured lines on stdout** (§8). Nothing else. Explicitly forbidden — the build FAILS
if any appears anywhere in the file or its import closure:

- Any broker, exchange, or market-data library or SDK; any HTTP/WebSocket/TCP client; any DNS
  lookup; any socket other than the three defined here.
- Reading or writing **any file**. State lives in memory; persistence is the platform's job.
- Any database access. The financial event log is not yours to touch.
- Reading the platform's financial picture: balance, margin, equity, open P&L, other strategies'
  positions. A strategy sees **only its own trade feedback** (§4.5). Pine logic keyed off
  `strategy.equity` or account state is `CANNOT MAP`.
- Raw ticks. Strategies consume **built bars and bricks only** (§6).
- Subprocesses, threads, multiprocessing, asyncio. **Single-threaded, single poll loop** (§8.1).
- **Wall-clock trading decisions.** All temporal trading logic derives from **bar/brick
  timestamps** delivered on the bus. Time-of-day logic is legal *only* per §8.2a (bar-timestamp
  conversion). Wall clock (`time.time()`) is permitted only for heartbeat cadence and the PENDING
  timeout of §5.
- Self-computed **session boundaries**. Session open/close truth arrives only via `sys.session`
  events (§4.8). You may filter *entries* by clock-time-of-day (§8.2a); you never decide when the
  session itself opens or closes.
- Unseeded randomness. If the Pine strategy is stochastic, `CANNOT MAP`.
- Environment variables beyond the **three** provided at launch (§2.1).
- **Import whitelist (closed):** Python stdlib — `json, math, enum, dataclasses, collections,
  itertools, statistics, signal, sys, logging, time` (time: heartbeat cadence + PENDING timeout
  only), `os` (**only** `os.environ.get` for §2.1 vars), `datetime` and `zoneinfo` (**only** for
  §8.2a bar-timestamp conversion) — plus **`zmq` (pyzmq)**. Nothing else. No numpy, no pandas, no
  TA libraries: indicators are implemented by hand in stdlib.

---

## 2. Process model & lifecycle

### 2.1 Launch
Nix's supervisor launches your file; you never daemonize, fork, or relaunch yourself.

```
python3 strategy.py            # no CLI args
```

Environment provided (the only three you may read, via `os.environ.get`):

| var | meaning |
|---|---|
| `NIX_STRATEGY_ID` | unique id, e.g. `pine_orb_es` — echo it in every message |
| `NIX_SYMBOL` | the single **logical** instrument this instance trades, e.g. `ES` |
| `NIX_RUN_DIR` | directory containing the ipc sockets |

Your file's own version is a **module constant** `STRATEGY_VERSION = "x.y.z"` — the file owns its
version; it is not injected. One strategy instance = **one symbol**. Multi-symbol Pine logic:
`CANNOT MAP`. Contract selection (micro vs mini, front-month roll) is invisible to you — you trade
the logical symbol; the platform maps it. `tick_size` is invariant across that mapping for the
supported symbols; `tick_value` is informational only.

### 2.2 Lifecycle states (the outer shell)
`START → REGISTER → WARMUP → RUN (FSM of §5) → SHUTDOWN`

- **REGISTER** (§4.2) is synchronous; you may not emit anything else first.
  **ZMQ mechanics (mandatory):** REQ is lockstep — an unanswered send cannot be re-sent on the
  same socket. Each retry **closes the REQ socket (`LINGER=0`) and creates a fresh one**: send →
  poll 5 s for reply → on timeout, close, recreate, log, retry. Retry forever; the platform may
  still be booting.
- **WARMUP**: consume the warmup bundle from REGISTER_ACK, prime indicator state, emit nothing but
  heartbeats. Exit WARMUP when **(a)** every indicator is fully primed and **(b)** the feedback
  snapshot (§4.5) has confirmed your position state. If the granted warmup depth (§4.2) is shorter
  than your indicators need, remain in WARMUP consuming **live** bars until primed — trading with
  unprimed indicators is forbidden. If still unprimed after `max_warmup_wait_s`, log ERROR once
  and continue priming from live data (heartbeats throughout); you simply start trading later.
- **SHUTDOWN**: on `SIGTERM` — send one final heartbeat with `state:"shutdown"`, close sockets,
  `sys.exit(0)`, within 2 s. **Never flatten on shutdown** — position safety on strategy death is
  the platform's orphan machinery, not yours.

### 2.3 Crash discipline
If you crash, the platform flattens your position, relaunches you, and counts it against a
crash-loop cap. Therefore: never exit on bad data — log, ignore, continue. Unknown inbound message
types are **ignored and logged**, never fatal.

---

## 3. Transport — the three sockets

All ZeroMQ over ipc, endpoints under `NIX_RUN_DIR`. All payloads **UTF-8 JSON, one object per
message** (multipart `[topic, payload]` on S3; single-frame JSON on S1/S2). **All numbers are JSON
integers where this contract says integer** — timestamps are integer nanoseconds and must never
pass through a float (Python↔Python JSON preserves big ints exactly; rely on that, never on
IEEE-754). Every outbound message includes `contract_rev`, `strategy_id`, and a monotonically
increasing `client_msg_id` (int, starts 1).

| # | socket | type | endpoint | carries |
|---|---|---|---|---|
| S1 | control | **REQ** (recreate per retry, §2.2) | `ipc://$NIX_RUN_DIR/bus_control.ipc` | REGISTER → REGISTER_ACK |
| S2 | signal | **DEALER** | `ipc://$NIX_RUN_DIR/bus_signal.ipc` | GO, EXIT_INTENT, HEARTBEAT (out only) |
| S3 | data+feedback | **SUB** | `ipc://$NIX_RUN_DIR/bus_market.ipc` | bars, bricks, own feedback, sys |

S3 subscriptions — exactly four, set before REGISTER:
`bar.M1.<SYMBOL>` · `brick.RENKO.<SYMBOL>` · `fb.<STRATEGY_ID>` · `sys`

**Exact-match discipline (mandatory):** ZMQ subscription matching is *prefix*-based —
`fb.pine_orb` also delivers `fb.pine_orb_es`. On every S3 message, compare the received topic
frame for **byte equality** against your four expected literals; drop and log anything else.
Additionally verify `strategy_id` inside every `fb.*` payload equals yours; mismatch ⇒ drop + log
WARN. Bars/bricks carry no symbol field — the exact topic match *is* the symbol check.

**Snapshot-on-subscribe and at any time:** on joining, `fb.<id>` delivers a `snapshot` before live
events. A `snapshot` may **also arrive at any later moment** (platform restart/resync). Wherever
you are, a snapshot is **authoritative resync**: adopt its state, reconcile your FSM to it, log
the transition. If it reports an open position (relaunch edge), enter `IN_POSITION` and manage
exits normally.

---

## 4. Message schemas

Field names are exact. Timestamps: **UTC, integer nanoseconds since epoch**, always from delivered
bar/brick data — wall clock only in `hb.ts`.

### 4.1 Common envelope (every message you send)
```json
{"contract_rev":"1.1.0","strategy_id":"<id>","client_msg_id":7,"type":"..."}
```
The platform deduplicates on (`strategy_id`,`client_msg_id`) — a retried send is safe (§9A).

### 4.2 REGISTER (S1) → REGISTER_ACK
```json
{"type":"register","symbol":"ES","strategy_version":"1.0.0",
 "warmup_request":{"m1_bars":3000,"renko_bricks":500}}
```
Compute `m1_bars` from your **deepest** indicator need (longest lookback × highest local
timeframe factor; e.g. 200-EMA on locally-built 15m ⇒ 200×15=3000). The platform grants up to its
cap. ACK (consume these; ignore extras):
```json
{"ok":true,
 "instrument":{"symbol":"ES","tick_size":0.25,"tick_value":12.5},
 "warmup":{"m1":[],"renko":[],"granted_m1":3000,"granted_renko":500,"renko_size_ticks":8},
 "config":{"hb_interval_s":1.0,"max_warmup_wait_s":120,"go_timeout_s":10}}
```
`ok:false` ⇒ log `reason`, idle with heartbeats; the platform decides your fate.
**`tick_size` from this ACK is the only instrument constant you may use — never hardcode (§7.2).**

### 4.3 GO (S2) — the only way to open a position
```json
{"type":"go","symbol":"ES","direction":"long","signal_ts":0,
 "stop":{"mode":"fixed","initial_ticks":16}}
```
```json
{"type":"go","symbol":"ES","direction":"short","signal_ts":0,
 "stop":{"mode":"trailing","initial_ticks":16,"trail_ticks":10}}
```
`signal_ts` = close timestamp of the triggering bar/brick. `initial_ticks`/`trail_ticks`:
**positive integers, in ticks**. No size field — the platform sizes. No price field — stops are
distances anchored at fill. **Stop parameters are immutable for the life of the trade** (§7.4).
Emission is legal only from FSM `FLAT`, at most **one GO per completed bar/brick event** — a
reversal GO issued from the closed-handler counts as that bar's one GO.

### 4.4 EXIT_INTENT (S2) — the only way to request your own exit
```json
{"type":"exit_intent","symbol":"ES","signal_ts":0,"reason":"tp"}
```
`reason` ∈ `tp | signal | reverse` (short free-text ≤16 chars allowed). Legal only from
`IN_POSITION`; **at most one per position** — while `CLOSING`, further exit desires are no-ops.
The platform answers with `closed`.

### 4.5 Feedback events (S3, topic `fb.<id>`) — consume all of these
| type | key fields | meaning / your reaction |
|---|---|---|
| `snapshot` | `state:"flat"/"in_position"`, `position_qty` (signed), `avg_price`, `halted:bool` | authoritative resync, at join or **any time** (§3) |
| `ack` | `client_msg_id` | delivery confirmation only — you are already `PENDING` (§5 inv. 1); ack changes nothing |
| `denied` | `client_msg_id`, `reason` | GO refused — `FLAT`; **no re-emit until a new bar/brick closes** |
| `fill` | `qty_filled`, `avg_price`, `position_qty` (signed), `partial:bool` | position is **fact** at `position_qty` — adopt it **from any state** (§5 inv. 9); partial fills are final, remainder was cancelled |
| `closed` | `reason: stop/trail/session/protective/operator/exit_intent/orphan/cancelled`, `position_qty:0` | position gone or order dead — **hard-reset trade state**, `FLAT`. `cancelled` = acked-but-never-filled order terminated flat |
| `halt` | `active:bool` | while active: no GO; EXIT_INTENT still permitted |

**Sign convention: `position_qty` is signed everywhere — positive long, negative short, 0 flat.**
`closed` can arrive at any moment without your having asked. Your FSM accepts it from any state.

### 4.6 HEARTBEAT (S2)
```json
{"type":"hb","ts":0,"state":"FLAT"}
```
Every `hb_interval_s` (default 1 s), in **every** lifecycle state including WARMUP and stalls,
driven by the poll loop — never by strategy logic. Keep per-event compute well under 250 ms.

### 4.7 Market data (S3) — with hygiene rules
```json
{"ts_open":0,"ts_close":0,"o":0,"h":0,"l":0,"c":0,"v":0}
```
```json
{"seq":123,"dir":"up","open":0,"close":0,"ts_close":0,"size_ticks":8}
```
`dir` ∈ `up | down`. Evaluate on **completed** events only, in arrival order. Hygiene (mandatory):
- **Sparse M1 is normal** (thin minutes produce no bar). Never assume wall-clock continuity;
  local aggregation (§6) buckets by timestamp, never by count.
- **Brick `seq` gap** ⇒ log ERROR once, continue causally from what arrives. Never extrapolate
  missing data.
- **Non-monotonic `ts_close`** (≤ your last seen, per stream) ⇒ drop + log WARN.

### 4.8 sys topic — guaranteed session events
```json
{"type":"session","open":true,"ts":0}
```
Ordered, timestamped, and **guaranteed by the platform** (§9A) at every session boundary for your
symbol. This is the **only** legal session anchor: session-scoped series (§6) reset on
`open:true`. You do not implement session-close exits — the platform force-flattens before close.

---

## 5. The strategy FSM — closed loop, mandatory shape

```
        +------------------------------- closed (any reason) ------------------+
        v                                                                      |
      FLAT --- go emitted ---> PENDING --- fill ---> IN_POSITION -- exit_intent --> CLOSING
        ^                        |   |                    |                          |
        |          denied -------+   |                    +<---- fill(partial) -----+
        |   go_timeout_s --------+---+                                        (more fills)
        +--------------------------------------- closed <----------------------+
HALT overlay: halt.active=true suppresses GO in FLAT; everything else unchanged.
```

Invariants (each is a checklist item in §10):
1. **One-in-flight, structurally:** GO emission only in `FLAT`; the transition to `PENDING`
   happens in the same statement. `ack` is confirmation only, never the state trigger.
2. **Hard reset on `closed`:** all trade-scoped state cleared in one function called on every
   `closed` (any reason, incl. `cancelled`), before re-entering `FLAT`. Indicator state persists;
   trade state never survives a close.
3. **`closed` accepted from any state**, idempotent in `FLAT`.
4. **`denied` ⇒ `FLAT` + cooldown** until the next completed bar/brick. Never re-emit same-bar.
5. **Partial fill = final fact.** Exit logic operates on actual signed `position_qty`; no top-up
   path exists.
6. **Reversals are two acts:** `exit_intent(reason:"reverse")` → await `closed` → GO from `FLAT`
   (same-bar permitted; counts as that bar's one GO).
7. **HALT** suppresses GO only; evaluation continues; exits permitted.
8. **No self-flatten on shutdown; no exit suppression** — if your logic says exit, emit it even
   during HALT.
9. **Feedback is authoritative (blanket rule):** `fill` adopts position-as-fact from **any**
   state; `snapshot` resyncs from any state; an event arriving in a state where this table has no
   edge **converges to what the event asserts**, logs WARN, and never crashes. You never "know
   better" than the platform about your own position.
10. **PENDING timeout:** if neither `ack`-then-`fill`, `denied`, nor `closed` arrives within
    `go_timeout_s` (wall clock — the one legal use beyond heartbeats), log ERROR, return to
    `FLAT`, apply the invariant-4 cooldown. A later `fill`/`closed` for that order is then
    handled by invariants 9/3 — converge, don't crash.

---

## 6. Market data usage & derived series

- Primary inputs: canonical `bar.M1` and `brick.RENKO` for your symbol.
- **Higher timeframes** (same symbol): build locally by aggregating delivered M1 — **bucketed by
  timestamp** (§4.7 sparse rule), closed-bars-only, deterministic.
- **Session-scoped series** (session VWAP, prev-session high/low, opening range): anchored
  **only** on `sys.session` events (§4.8). Prior-session levels come from warmup depth — request
  enough `m1_bars` (§4.2) to cover the sessions you reference.
- **Custom Renko:** if the Pine box size ≠ `renko_size_ticks`, derive locally from M1 closes;
  parity-note it as an M1-close approximation of tick Renko. Materially intrabrick-sensitive
  logic: `CANNOT MAP`.
- **Other symbols** (cross-symbol `security()`, spreads, breadth): `CANNOT MAP`.
- **Volume:** may be 0 during scaffold phases — tolerate 0, parity-note if volume-dependent.

---

## 7. Pine v6 → Nix translation rules

### 7.1 Construct map (binding)
| Pine v6 | Nix |
|---|---|
| `strategy.entry(id, strategy.long/short)` — market | GO from FLAT |
| `strategy.entry(..., limit=/stop=)` — resting entry | **bar-close touch-trigger**: watch M1 for the level, emit market GO on the first completed bar satisfying it; parity-note the approximation. Fill-price-precision-critical: `CANNOT MAP` |
| qty, `default_qty_*`, pyramiding>0 | qty discarded — platform sizes; pyramiding collapses to single position; parity-note |
| `strategy.exit(stop=/loss=)` | GO `stop.mode:"fixed"`, `initial_ticks` |
| `strategy.exit(trail_points/trail_offset)` | GO `stop.mode:"trailing"`, `initial_ticks`+`trail_ticks` |
| `strategy.exit(limit=/profit=)` (TP) | FSM-internal TP condition → `exit_intent("tp")` |
| **dynamic stop moves** (breakeven, tighten, re-issued `strategy.exit`) | stops are **immutable per trade** (§4.3). Map to: (a) nearest trailing-mode equivalent, or (b) strategy-side emulation — track the desired stop level internally, `exit_intent("signal")` on the first completed bar/brick breaching it (M1-granularity approximation, parity-noted), or (c) `CANNOT MAP` if intrabar stop precision is load-bearing |
| **scale-outs** (TP1/TP2, partial closes) | no partial-close message exists. Collapse to the single most load-bearing TP (parity-note the dropped legs) or `CANNOT MAP` |
| `strategy.close()` / opposite-signal exit | `exit_intent("signal")` |
| reverse-on-signal | invariant 6 |
| **time-of-day entry filters** (`time(timeframe, "0930-1500")`, hour/minute gates) | **legal and expected**: derive from `bar.ts_close` via §8.2a; identical filter semantics, DST-correct |
| session/EOD **exits** | drop — platform's session flatten owns it; parity-note |
| session-anchored series (prev-day H/L, opening range) | §6 — `sys.session` anchor + warmup depth |
| `syminfo.mintick` | `instrument.tick_size` from ACK |
| price distance → ticks | `ticks = round(distance / tick_size)`, assert ≥ 1 |
| `calc_on_every_tick=true` | completed-M1 cadence; parity-note |
| `request.security(same sym, higher TF)` | local M1 aggregation (§6) |
| `request.security(other sym)` | `CANNOT MAP` |
| `alert()`, `plot*()`, inputs UI | drop silently (inputs → module constants) |
| `strategy.equity` logic, martingale | `CANNOT MAP` |
| `barstate.isconfirmed` | implicit — completed events only |
| lookahead / repainting sources | forbidden — §7.3 |

### 7.2 Tick conversion discipline
All Pine point/price distances convert through `tick_size` **from the ACK at runtime**. A literal
tick size, tick value, or symbol constant anywhere in the file is a build failure.

### 7.3 No repainting, no lookahead
Causally clean: every decision uses only events with `ts_close ≤ now`. Repainting sources are
re-expressed causally or `CANNOT MAP`. Parity table states how each indicator was made causal.

### 7.4 Stop immutability
The stop distance and mode chosen at GO are final for that trade. Any Pine logic that would move
the stop afterward routes through the dynamic-stop row of §7.1 — never through a second GO, never
through an imagined modify message.

### 7.5 CANNOT MAP protocol
Per unmappable element: parity-table row — Pine element, why, behavioral consequence of omission.
Load-bearing `CANNOT MAP`s flagged **bold at the top** of the table. You still deliver the file;
the humans decide.

---

## 8. Runtime shape & style

### 8.1 The loop
One `zmq.Poller` over S3, tick ≤ 250 ms: poll → drain S3 in order (exact-topic filter §3) →
update series on completed events → FSM step (incl. PENDING-timeout check) → emit (≤1 GO or
exit_intent) → heartbeat if due → repeat. No other sleeps, no threads, no callbacks.

### 8.2 Determinism
Same REGISTER_ACK + same S3 sequence ⇒ byte-identical outbound sequence (`client_msg_id` values
and `hb.ts` excepted; PENDING-timeout ERROR paths excepted — they depend on real elapsed time).
No RNG, no dict-ordering dependence, no float accumulation that varies with chunking.

### 8.2a Time-of-day derivation (the only legal clock)
```python
from zoneinfo import ZoneInfo
from datetime import datetime, timezone
CT = ZoneInfo("America/Chicago")
def tod(ts_ns):  # -> (hour, minute) in exchange time, from BAR data
    return (lambda d: (d.hour, d.minute))(
        datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc).astimezone(CT))
```
Input is always a **delivered** `ts_close`/`ts_open` — never `datetime.now()`. This gives Pine's
`time()`-filter semantics, DST-correct, deterministic. Session *boundaries* still come only from
`sys.session`.

### 8.3 Logging (Plane 2)
Structured single lines to **stdout**:
`<iso8601Z> <LEVEL> nix.strategy.<id> v<STRATEGY_VERSION>/<contract_rev> <event> k=v ...`
Log lifecycle transitions, every send (type+id), every feedback, every hygiene drop (§4.7), every
runtime tolerance. Never per-bar spam at INFO.

### 8.4 Skeleton (start from exactly this shape)
```python
#!/usr/bin/env python3
# Nix strategy plugin - generated from <PINE NAME>. contract_rev 1.1.0
import json, math, os, signal as _signal, sys, time
from enum import Enum, auto
import zmq

STRATEGY_VERSION = "1.0.0"                     # the file owns its version
SID = os.environ.get("NIX_STRATEGY_ID")
SYM = os.environ.get("NIX_SYMBOL")
RUN = os.environ.get("NIX_RUN_DIR")
REV = "1.1.0"

class S(Enum):
    FLAT = auto(); PENDING = auto(); IN_POSITION = auto(); CLOSING = auto()

class Strategy:
    def __init__(self, cfg):
        self.state = S.FLAT; self.halted = False; self.msg_id = 0
        self.pos_qty = 0                        # signed: +long / -short
        self.pending_since = None               # wall clock, invariant 10
        self.last_signal_event = None           # denied / one-per-bar cooldown
        self.go_timeout_s = cfg["go_timeout_s"]
        # indicator state here (persists across trades)
        self._reset_trade_state()

    def _reset_trade_state(self):               # invariant 2 - sole reset path
        self.tp_level = None; self.entry_ref = None; self.pending_since = None

    # ---- pure signal logic, translated from Pine, closed events only ----
    def on_bar(self, bar): ...
    def on_brick(self, brick): ...
    def want_entry(self): ...                   # -> None | ("long"|"short", stop_dict)
    def want_exit(self): ...                    # -> None | reason

# (wiring the generated file must complete: REQ register, socket recreated per
#  5s retry; SUB the 4 topics with byte-exact topic filtering; DEALER out;
#  single poller loop with PENDING-timeout check; hb every hb_interval_s in
#  ALL states; snapshot resync from any state; SIGTERM -> final hb, exit 0)
```

---

## 9. What you do NOT implement (the platform owns it)
Position sizing · margin/liquidity/correlation checks · stop placement, monitoring, trailing
ratchets · session-close flatten · order routing, cancels, partial-fill remainder handling ·
reconciliation · persistence · P&L · scoring. Writing any of these means you have left the
contract.

## 9A. Platform guarantees (what Nix promises YOU — rely on these)
1. **Idempotent intake:** duplicate (`strategy_id`,`client_msg_id`) is deduplicated; retrying a
   send is safe.
2. **Snapshot on subscribe and on resync:** a `snapshot` precedes live `fb.*` events at join, and
   is re-broadcast after any platform-side restart of the feedback publisher.
3. **Terminal outcome for every GO:** every emitted GO ends in exactly one of `denied`, `fill`
   (possibly partial, then `closed` later), or `closed(reason:"cancelled")`. Nothing is left
   dangling server-side; your §5-inv-10 timeout is a belt over these braces.
4. **Guaranteed session events:** `sys.session` fires, ordered and timestamped, at every session
   boundary for your symbol.
5. **`closed` finality:** after `closed`, your `position_qty` is 0 server-side; a subsequent
   `snapshot` will agree.
6. **Warmup grant:** ACK warmup arrays match `granted_*` counts, newest-last, contiguous per
   stream (subject to §4.7 sparseness).

---

## 10. SUCCESS CHECKLIST — all boxes or no success claim

**A. Boundary & imports**
- [ ] Import closure within whitelist (§1); grep-clean of `requests|websocket|socket|sqlite|psycopg|subprocess|threading|multiprocessing|asyncio|open(`
- [ ] Zero file I/O; zero network beyond the three ipc endpoints; env reads = the three §2.1 vars via `os.environ.get` only
- [ ] No hardcoded tick_size / tick_value / symbol constants (§7.2)
- [ ] `datetime`/`zoneinfo` used only inside the §8.2a derivation on delivered timestamps; `time` only for hb cadence + PENDING timeout; no `datetime.now()` anywhere
- [ ] `STRATEGY_VERSION` module constant present and stamped into logs

**B. FSM conformance (cite line numbers for each)**
- [ ] Four states + HALT overlay; transitions exactly per §5 incl. the timeout edge
- [ ] Inv 1: GO only in FLAT, PENDING entered same statement; `ack` is confirmation-only
- [ ] Inv 2: single `_reset_trade_state()` on every `closed`, incl. `cancelled`
- [ ] Inv 3: `closed` handled from every state, idempotent in FLAT
- [ ] Inv 4: `denied` → FLAT + no re-emit until next completed bar/brick
- [ ] Inv 5: signed `position_qty` adopted as fact incl. partial; no top-up path
- [ ] Inv 6: no GO while position ≠ 0; reversal = exit → closed → GO (counts as that bar's one GO)
- [ ] Inv 7–8: HALT suppresses GO only; exits never suppressed; no self-flatten on SIGTERM
- [ ] Inv 9: `fill` and `snapshot` converge the FSM from ANY state; unexpected combos log WARN and converge, never crash
- [ ] Inv 10: PENDING timeout via `go_timeout_s` implemented; late fill/closed afterward converges
- [ ] Snapshot adoption at join AND mid-run resync (both flat and in_position paths)
- [ ] Unknown message types ignored+logged; malformed JSON logged, never fatal

**C. Protocol conformance**
- [ ] Envelope (§4.1) with monotone `client_msg_id` on every send
- [ ] GO / EXIT_INTENT schemas conform; `initial_ticks`,`trail_ticks` ints ≥ 1; stop params never re-sent (immutability §7.4)
- [ ] `signal_ts` from triggering event close, never wall clock
- [ ] Heartbeat every interval in ALL lifecycle states, loop-driven; state string accurate
- [ ] REGISTER retry recreates the REQ socket each attempt (LINGER=0)
- [ ] `warmup_request` computed from deepest indicator need; WARMUP holds until primed (live-bar top-up path present)
- [ ] Exact-topic byte-match filter + `strategy_id` verification on every fb payload
- [ ] At most one GO per completed bar/brick event, enforced structurally
- [ ] At most one exit_intent per position; no-ops while CLOSING
- [ ] Timestamps handled as ints end-to-end (no float conversion of ns values)
- [ ] §4.7 hygiene: sparse-M1-safe aggregation, seq-gap ERROR-and-continue, non-monotonic drop+WARN

**D. Pine parity table (delivered WITH the file)**
- [ ] Every Pine input, condition, and order call mapped | dropped (why) | CANNOT MAP (why + consequence)
- [ ] Every indicator: causal derivation stated (§7.3)
- [ ] qty / pyramiding / session-exit / alert / plot drops noted
- [ ] Dynamic-stop and scale-out handling per §7.1 rows, choice + approximation noted
- [ ] Limit/stop entries: touch-trigger approximation noted, or CANNOT MAP
- [ ] Time-of-day filters ported via §8.2a and noted
- [ ] Derived-series approximations (local Renko / HTF / session anchors) declared
- [ ] Load-bearing CANNOT MAPs flagged bold at table top

**E. Determinism & runtime**
- [ ] Single thread, single poller, ≤250 ms tick; per-event compute well under 250 ms
- [ ] §8.2 determinism statement true of the code
- [ ] Logging per §8.3 with both version stamps
- [ ] SIGTERM: final hb `state:"shutdown"`, clean exit ≤ 2 s

**F. Honest close-out**
- [ ] Stated plainly: this proves **structural conformance**, not profitability, not runtime
      correctness. Runtime certification happens inside Nix (sim replay + debug tiers) and is not
      your claim to make.

**Declaration:** `STRATEGY BUILD SUCCESSFUL — contract 1.1.0, <n>/<n> checks, parity table
attached, CANNOT MAP count: <k> (load-bearing: <0|list>)` — otherwise `STRATEGY BUILD INCOMPLETE`
with the unchecked list. No third state.

---

## 11. Change control
This contract versions independently (`contract_rev`). The Nix side implements it verbatim; a
`contract_rev` mismatch is a registration rejection, not a negotiation. Amendments append here
with a version bump; banked strategy files are never silently re-interpreted.

## 12. v1.1.0 changelog (ULTRAREVIEW fixes over v1.0.0)
Time-of-day entry filters legalized via bar-timestamp `zoneinfo` derivation (§8.2a, §7.1) with
`datetime`/`zoneinfo` whitelisted; PENDING deadlock family closed (`go_timeout_s`, `cancelled`
reason, feedback-authoritative invariant 9, timeout invariant 10); REQ retry mechanics corrected
(socket recreation, LINGER=0); warmup depth negotiation (`warmup_request`/granted, prime-or-wait
rule, `max_warmup_wait_s` semantics); dynamic-stop + scale-out + limit/stop-entry translation rows
added under stop-immutability (§7.4); `ack` demoted to confirmation-only; exact-topic byte-match +
payload id verification; signed `position_qty` convention; snapshot-as-resync at any time;
`sys.session` promoted to guaranteed anchor with session-series rules; data-hygiene rules (sparse
M1, seq gaps, non-monotonic drops); `STRATEGY_VERSION` moved into the file (env vars now three);
integer-timestamp mandate; brick `dir` enum; one-exit_intent-per-position; reversal one-GO
clarification; new §9A Platform Guarantees consolidating the Nix-side obligations (idempotent
intake, snapshot re-broadcast, terminal outcome for every GO, guaranteed session events).
