# RESULTS — ARC 012: systemd cutover, MES verification, entitlement clarification

**Status: ARC 012 complete.** Every success box checked. One is checked as *"D1.12 explicitly left
open"* — the arc's own alternative — because the reboot test was offered as a separate
authorization and declined.

**Headline: MES fixes margin. It does not fix data.** The entitlement is account-level; no
instrument choice and no code change reaches it.

---

## Definition of success

| Box | State |
|---|---|
| Pre-cutover state recorded (PIDs, listener, verify.py baseline) | ✅ |
| Both units started; Xvfb serving `:99`; Gateway under systemd, not a shell | ✅ — proven by cgroup, not unit status |
| Unreachable Gateway confirmed `CANNOT_MEASURE`, not `FAIL`, in the **real** case | ✅ |
| Human VNC re-login completed; `verify.py` green with unit-owned processes | ✅ — 6 passed, exit 0 |
| Reboot test performed under separate authorization, **or** D1.12 explicitly left open | ✅ — **offered, declined, D1.12 left open** |
| MES resolved; margin measured vs net liq; affordability stated as a number | ✅ — 3,503.59 vs 20,344.34 → **5 contracts** |
| `reqTickByTickData` attempted on MES; 10189 recurrence recorded | ✅ — **it recurs** |
| `reqHistoricalTicks` confirmed working for MES | ✅ — 25 ticks |
| `dev_and_services_plan.md` and `CHECK-DEBT.md` updated | ✅ |

**Ordering note.** Part 2 ran **before** Part 1. Part 2 needs an *authenticated* Gateway and Part 1
deliberately destroys that authentication, so written order would have parked the MES work behind
a human login. Nothing in Part 1 depends on Part 2. This banked the measurements before anything
was torn down and cut the operator's wait.

**Prerequisite not met, reported rather than assumed.** The arc requires `arc-009-verify-v2` to be
merged first. Measured fresh: `origin/main` is still `47ea580`, the branch is **57 ahead / 1
behind**, and `git merge-base --is-ancestor HEAD origin/main` says **not merged**. Repo hygiene
with no bearing on Parts 1–3, and console availability was the perishable resource, so the arc
proceeded. **The merge is still owed.**

---

## Part 1 — systemd cutover

### 1. Pre-cutover state

```
=== manual processes ===
 PID    PPID USER   ELAPSED  COMMAND
 236457    1 bbt    08:35:21 Xvfb :99 -screen 0 1440x900x24
 236482    1 bbt    08:35:19 .../java ... install4j.ibgateway.GWClient

=== who owned them ===
PID 236457 -> cgroup: 0::/user.slice/user-1000.slice/session-231.scope
PID 236482 -> cgroup: 0::/user.slice/user-1000.slice/session-231.scope

=== listener ===
LISTEN 0 50 *:4002 *:* users:(("java",pid=236482,fd=81))

=== units ===  enabled/enabled, inactive/inactive
=== verify.py === 6 passed | 0 failed | 0 cannot measure | 0 skipped   exit 0
```

`session-231.scope` is the load-bearing detail: a **login-session scope**, not a service unit. That
is the concrete evidence the processes were shell-owned, and it is exactly what the cutover changes.

### 2–3. Cutover, and the measurement the arc singled out

Manual Gateway stopped (SIGTERM, exited cleanly), then manual Xvfb; `:99` confirmed gone. Then:

```
$ systemctl start nix-xvfb.service
active
$ xdpyinfo -display :99
name of display:    :99
  dimensions:    1440x900 pixels (366x229 millimeters)
Xvfb MainPID=260814 cgroup: 0::/system.slice/nix-xvfb.service
```

**Display up, nothing on 4002 — the real unreachable case, nothing planted:**

```
--- check_ibgateway_config ---
cannot_measure: no API endpoint at 127.0.0.1:4002 — ConnectionRefusedError: [Errno 111]
Connection refused. Gateway down or not logged in; that is not a misconfiguration (§4.1)
exit=2                                    <-- 2 = CANNOT MEASURE, not 1 = FAIL

--- check_ibgateway_service ---
fail_needs_operator: ... 127.0.0.1:4002 handshake: unreachable (ConnectionRefusedError...)
  site: 127.0.0.1:4002 (nix-ibgateway.service)
exit=1
```

**This is the ARC 010/011 design meeting reality instead of a plant.** One observation yields
`CANNOT_MEASURE` in the gate that reads configuration *through* the connection and `FAIL` in the
gate asserting the connection should exist at all. Both correct; the distinction now rests on
real-world evidence rather than a planted wrong port.

### Gateway under systemd

```
● nix-ibgateway.service - IB Gateway (paper, Stage 0) — API endpoint on 127.0.0.1:4002
     Active: active (running)
    Process: 261042 ExecStartPre=/bin/sh -c for _ in $(seq 30); do xdpyinfo -display :99 ...
             (code=exited, status=0/SUCCESS)
   Main PID: 261046 (java)
     CGroup: /system.slice/nix-ibgateway.service
DISPLAY: DISPLAY=:99
```

`ExecStartPre` — the display-readiness gate — exited `0/SUCCESS`, so the Gateway→display
dependency behaved as a real precondition rather than incidental ordering. Both units
`NRestarts=0`.

Gateway came up on its login screen with no API listener, as predicted. Confirmed on `:99` via
`xwininfo`: `0x40000c "IBKR Gateway" 790x610+325+145`.

### 4. Handoff and post-login state

Stopped and handed off rather than working around the login. **No VNC server was running** — the
previous one died with the session torn down — and I deliberately did **not** start one: an
unauthenticated VNC exposing a live broker Gateway is an operator decision, not mine. The human
logged in and approved IB Key.

**The cutover's decisive proof:**

```
LISTEN 0 50 *:4002 *:* users:(("java",pid=261046,fd=78))
unit MainPID = 261046
listener PID = 261046
cgroup of listener: 0::/system.slice/nix-ibgateway.service
  --> MATCH: the API socket is served by the unit-owned process
```

The socket is served by the unit's own `MainPID`, inside the service cgroup — not by a shell orphan
that merely happens to be listening.

```
  [ok]   check_python_runtime    | sys.version_info=3.14.4 at /usr/bin/python3
  [ok]   check_venv              | /home/bbt/nix/.venv/bin/python3: Python 3.14.4
  [ok]   check_node_identity     | stored == live == 0a2fe0d5-5eb2-46ae-a9f9-013dc7097003
  [ok]   check_python_deps       | pins satisfied: ib_async==2.1.0
  [ok]   check_ibgateway_config  | IB API handshake on 127.0.0.1:4002 -> serverVersion=187; ...
  [ok]   check_ibgateway_service | nix-xvfb.service=enabled/active; nix-ibgateway.service=enabled/active;
                                   display :99: dimensions: 1440x900 ...; handshake: answered (187)

  6 passed | 0 failed | 0 cannot measure | 0 skipped          exit 0
```

The meaningful change from baseline is `enabled/`**`active`** where it read `enabled/inactive`.

**API configuration survived the restart** — `check_ibgateway_config` passed unchanged, so
TrustedIPs / AutoRestart / localhost-only live in the profile, not in process state. Live session
re-confirmed on `clientId=905`: `managedAccounts ['DUR250018']`, `NetLiquidation 20344.34`, clean
disconnect.

### 5. Reboot test — offered, declined, D1.12 left open

Put as an explicit separate authorization per the arc; the answer was no. **Boot behaviour is
therefore NOT verified**, and nothing in this report claims otherwise. `systemctl is-enabled` is a
*declaration* that these units start at boot, not evidence that they do.

**D1.12 remains open**, narrowed to exactly the reboot. Discharge condition unchanged: reboot, then
run `check_ibgateway_service` **before anyone touches the console** — a human logging in first
creates the very state the check must observe independently.

---

## Part 2 — MES: two problems, measured separately

Account **DUR250018**, net liquidation **20,344.34 USD**.

### Contract

```
MES front month : MESU6   conId=793356217   expiry=20260918   exchange=CME   secType=FUT
multiplier      : 5      (ES: 50 — MES is 1/10th notional, as expected)
```

### Margin — MES affordable, ES not

| | ES (`ESU6`) | MES (`MESU6`) |
|---|---|---|
| conId | 649180671 | 793356217 |
| multiplier | 50 | 5 |
| **initial margin** | **35,035.87** | **3,503.59** |
| maintenance margin | 25,029.29 | 2,502.93 |
| headroom vs 20,344.34 | **−14,691.53** | **+16,840.75** |
| contracts affordable | **0** | **5** |
| outcome | rejected, `Error 201` | margin returned normally |

Margin scales at exactly **10.0×**, tracking the multiplier. ES's rejection, verbatim:

```
Error 201: Order rejected - reason:YOUR ORDER IS NOT ACCEPTED. IN ORDER TO OBTAIN THE DESIRED
POSITION YOUR NET LIQ [20299.32 USD] MUST EXCEED THE MARGIN REQ [35035.87 USD]
```

**Method correction worth keeping.** The first pass reported *both* contracts UNDETERMINED:
`ib.whatIfOrder()` (sync) returned an empty `OrderState` with `initMarginChange=None`. That was not
a real result — its internal wait expires before IB answers, detectable because the ES rejection
surfaced a whole section *later* in the same run, attributed to an unrelated request. Re-measured
with `whatIfOrderAsync` awaited under an explicit 45s timeout, which is where every figure above
comes from.

**Correction to a claim made earlier in this arc:** I first wrote that ARC 010 "recorded ES margin
as UNDETERMINED where it was merely late." That is wrong, and unfair to it. ARC 010's `whatIf` did
also come back empty, but it recovered the correct figure from the **`err 201` rejection text** and
reported 35,067.37 against net liq 20,344.34 — a sound conclusion from a sound source.

The sharper point is *when the trap actually bites*: a **rejected** order leaves an error carrying
the margin number, so the empty `OrderState` costs nothing. An **affordable** one does not — there
is no error, so an empty `OrderState` reads as "undetermined" with nothing to correct it. That is
precisely the MES case, and precisely why round one produced no MES figure. Anyone repeating this
must use the async form.

(ARC 010 measured ES at 35,067.37; today it measured 35,035.87. Both are correct — IBKR margin
moves intraday. Neither contradicts the other.)

### Market data — Err 10189 RECURS on MES

```
Error 10189, reqId 23: Failed to request tick-by-tick data.
  No market data permissions for CME FUT,
  contract: Future(conId=793356217, symbol='MES', lastTradeDateOrContractMonth='20260918',
                   multiplier='5', exchange='CME', currency='USD', localSymbol='MESU6')

  tick-by-tick received : 0
  --> Err 10189 on MES  : True
```

**MES does not dodge the entitlement — measured, not assumed.** The error names the **product
class**, `CME FUT`, not the contract. MES is CME FUT exactly as ES is. This is an **account-level
market-data subscription**, so no instrument selection and no code change reaches it.

**Fallback confirmed working on MES:**

```
reqHistoricalTicks -> 25 ticks
  2026-08-10 10:43:31+00:00  price=7785.00  size=5.0
  2026-08-10 10:43:31+00:00  price=7784.75  size=3.0
  2026-08-10 10:43:31+00:00  price=7784.75  size=1.0
```

Clean disconnect on every probe run.

### What this settles

- **No CME futures tick stream is available on this account at all** — confirmed across two
  instruments, not inferred from one.
- The **polled `reqHistoricalTicks` path stands regardless of instrument.**
- **Bar immutability remains an obligation Nix's broker-datafeed must enforce itself**, unchanged
  by ARC 012 and now confirmed twice over. Polled history is re-requestable and can return revised
  values, so the bar builder needs its own seal-and-never-rewrite rule.
- **MES is the instrument to develop against at Stage 0** — but it fixes *margin only*. The two
  problems were independent and exactly one is solved.

**Surfaced as a decision, not a recommendation.** Whether to buy CME market data in IBKR Account
Management is a human call. IBKR is permanently paper-only Stage 0 and Tradovate is the live broker
at cutover, so a subscription bought here is discarded at that boundary — but so is the ability to
exercise any streaming code path before then. Per the arc's out-of-scope: no purchase made, none
recommended.

---

## Part 3 — Records updated

**`docs/dev_and_services_plan.md`** — IBKR section now carries the cutover before/after table
(cgroups, not unit status), the `ExecStartPre` result, the **D1.12-still-open** warning box, the
real-case `CANNOT_MEASURE` vs `FAIL` confirmation, the ES/MES margin table, the entitlement finding
with the explicit statement that no CME futures tick stream exists on this account and that it is a
subscription question rather than an instrument or code question, and the `whatIfOrder` async
method note.

**`docs/CHECK-DEBT.md`** — **D1.12 narrowed** (cutover done; only boot behaviour outstanding, with
the discharge condition restated). **D1.13 opened**: no CME tick stream on the account, carrying
both the pending human subscription decision and the owed bar-immutability gate for the polled path
once broker-datafeed exists.

### A defect in the ledger itself

The series column previously read **22** for ARC 010 and **21** for ARC 011. **Both were wrong.** I
hand-counted the rows and got it wrong twice. Counted mechanically: **24** and **23**, and **24**
today (D1 ×11, D2 ×12, D3 ×1).

Corrected in the doc with the error named. The banked `SESSION.md` entries still say 22→21 and are
deliberately left alone — history is appended, never rewritten.

Worth stating plainly: **this is the ledger being its own instrument's defect** — the failure class
`VERIFY-AND-CHECKS.md` Part C opens with (*roughly one defect in three was found inside the
instrument doing the measuring*). The count is hand-maintained prose asserting a number the table
already determines: a `derive, never restate` violation, which is precisely what doctrine **B.7**
exists to catch and is already recorded as debt **D2.8**. A harness counting the rows and asserting
the latest series figure would have caught it on the first commit. Not built this arc (out of
scope), but D2.8 now has a concrete measured instance rather than a hypothetical.

---

## State at close

- `verify.py`: **6 passed, 0 failed, 0 cannot measure, 0 skipped — exit 0**
- Test suite: **153 passed**
- Xvfb `PID 260814` → `/system.slice/nix-xvfb.service`; Gateway `PID 261046` →
  `/system.slice/nix-ibgateway.service`, serving 4002
- Both units `NRestarts=0`, `enabled` and `active`
- CHECK-DEBT: **24 open** (was 23; D1.13 opened)

## Still owed

1. **Merge `arc-009-verify-v2`** — the arc's own prerequisite, unmet. 57 ahead / 1 behind, no
   conflict; nothing pushed this arc.
2. **D1.12** — reboot test; boot behaviour unverified.
3. **D1.13** — the CME market-data subscription decision.
