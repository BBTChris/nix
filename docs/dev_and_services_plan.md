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
Never trust strategy results from the IBKR phase — plumbing only.

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

**Market data: no tick-by-tick entitlement (ARC 010, measured).** `reqTickByTickData` on CME
futures returns **Err 10189** — "No market data permissions for CME FUT". `reqHistoricalTicks`
works and is the only path. Consequence for the broker-datafeed spec: the feed is **polled, not
streamed**, so **bar immutability is an obligation Nix must enforce itself**, not a property
inherited from the feed.

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
