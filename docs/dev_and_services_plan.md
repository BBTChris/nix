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
is a hard vendor constraint, not a tooling gap, and cannot be scripted or worked around. After
that first login, Gateway auto-restarts **daily**, but each auto-restart still requires the
human's IB Key approval on their phone — this is not a one-time setup, it's a standing daily
operational dependency on the operator being reachable. Paper socket port is 4002 (live is 4001,
not used at Stage 0); "Enable ActiveX and Socket Clients" and trusted IP `127.0.0.1` must be set
in the GUI after first login, since these live in the per-user `Jts` profile that doesn't exist
until then. Auto-restart-vs-auto-logoff is likewise a post-login GUI setting — unreachable before
the first human login creates the profile.

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
