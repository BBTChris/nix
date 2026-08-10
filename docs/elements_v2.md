# Nix Platform & Ops Elements (v2.1)

**Status: non-authoritative ops-layer input.** For anything touching the risk/execution pipeline,
`~/nix/docs/nics_risk_subsystem_spec_v1.3.md` is the sole authority and supersedes this file
wherever they meet. The frozen spec predates the Nix naming and spells the project **NICS** —
read NICS as Nix; spec references to node02 mean the Nix dev node. v2 scrubs the superseded content from the original `elements.md` (Project IO era): the stale
pipeline order, the separate heartbeated Broker Library, and the LOCKDOWN state are **removed**,
not merely flagged. What remains is the platform/ops layer the risk spec deliberately does not own
— provisioning, state maintenance, versioning, and backup/DR — plus implementation notes that
support (never redefine) the locked design.

**Supersession rules (binding on every future arc):**
- Pipeline order, gating, sizing, stops, HALT, reconciliation, logging planes: **v1.3 only.**
- Session-liveness machinery: v1.3 `on_session` events + fail-closed + reconcile-before-resume.
  There is no PING/PONG loop to the broker library and **no LOCKDOWN state** — its jobs are covered
  by HALT + flatten-on-uncertainty + cold-start reconciliation.
- Tunables: v1.3 §12A is the sole config authority (boot-loaded, restart-only). The version file
  below stores **version metadata only**, never tunables.
- Timestamps: trading path is **UTC** with venue-sourced sequence (v1.3 §12.3). `America/Chicago`
  appears below **only** for ops scheduling and settlement-aligned backup boundaries.

---

## 1. System Versioning & Provisioning

### 1.1 Version Control Schema
Strict `x.y.z` semantic versioning (Major.Minor.Patch). The authoritative version number lives in a
master version file (initialized `1.0.0`) — **metadata only; tunables live exclusively in the risk
spec's §12A semantics, physically laid out as per-module JSON per CLAUDE.md**. The active version is appended to every operational log line (Plane 2) and is
stamped into the Plane-1 boot event per v1.3 §12.11 — the two mechanisms are complementary: the
boot event anchors the audit trail, the per-line stamp makes any grep self-identifying.

### 1.1a Repository & Branch Policy
- **Remote:** `github.com/BBTChris/nix`, public (required for free branch protection; no proprietary edge is assumed to live in the code itself — see SESSION.md Arc 001/002 for the decision record).
- **Branching:** trunk-based, `main` only. No `develop` or long-lived feature branches while this remains single-dev + cc. Revisit only if concurrent arcs genuinely need isolation.
- **Protection on `main`:** PR review required before merge; no direct pushes; no force-push.
- **Commit gate:** governed by `debug.md`'s three-tier model — Tier 2 (all 5 stages) is wired into `pre-commit` and blocks `git commit` on failure. `git commit --no-verify` is permitted only with the bypass disclosed in the commit message and a follow-up opened; an undisclosed bypass is treated as the gate never having run.
- **CI/CD:** not yet implemented — explicitly out of scope until R1 (seams & skeleton) lands.

### 1.2 Bootstrapping & Installation
Fresh headless Ubuntu node, secure download-verify-execute:
- Administrator downloads and runs the `install.sh` bootstrap manually (`curl -sSLO`).
- Pre-installs base dependencies (`python3`, `git`, `python3-venv`, cryptography libs) before any
  interactive prompt.
- **Hardware identity:** the node is identified by the v4 full UUID of the primary partition.
- **Secure storage:** operator-supplied secrets are sealed with `systemd-creds`
  to this node's TPM 2.0 and delivered to units via `LoadCredentialEncrypted=`.
  **Supersedes the Fernet-under-master-password mechanism** — that design could
  not decrypt at boot without a human present, contradicting the headless
  self-healing invariant. See `VERIFY-AND-CHECKS.md` §11. This documents the
  decision; the migration itself is a separate plan, and until it lands,
  `install.sh` still contains the Fernet block.

### 1.3 State Maintenance (verify.py)
Idempotent, plugin-based inspection and remediation engine enforcing known-good node state.
- **Execution:** end of `install.sh`, every boot, and weekly (Saturday 03:00 America/Chicago —
  ops schedule, outside trading sessions).
- **Modes:** `verify` (detect and report), `correct` (verify + repair), `install`
  (correct + install what is absent, idempotent). `--verbose` is orthogonal to mode.
  **Superseded by `VERIFY-AND-CHECKS.md` §4 — that file is the authority for the
  check contract; this section is a summary only.**
- **Location:** `scripts/verify.py` per `directory_structure.md`.
- **Correct/Install actions:** resolves missing dependencies, configures systemd units, returns the
  node to known-good state. No unattended `git pull` — verify.py never updates its own code; an
  autonomous update to a trading node's codebase with no human review would be a §7-class hazard
  (auto-chasing latest without a decision or test cycle). Note v1.3 §12.11: config changes take
  effect only through restart — verify.py repairs the *environment*; it never hot-edits live
  tunables.

## 2. Data Ingestion — implementation notes for the v1.3 price firehose
v1.3 locks the design: the **sole** raw-shared-memory path is the per-tick price firehose,
`capture.py → Risk Engine`, single-writer ring buffer. These notes specify the *how*:
- **Lock-free IPC:** POSIX shared memory segment structured as a Single-Producer, Single-Consumer
  (SPSC) ring buffer — producer `capture.py`, sole consumer the Risk Engine.
- **Atomic operations:** hardware-level atomics govern `head`/`tail`; no OS mutexes, no tearing,
  no blocking of the consumer. Strategies never touch this ring — they consume built bars/bricks
  (Renko + M1) from capture.py per v1.3.

## 3. Execution-layer implementation notes (pipeline itself: see v1.3)
The pipeline, its order (`Strategy → Allocator → Risk Engine → broker`), gating, and feedback
contracts are defined **only** in v1.3. Retained here are the OS-level mechanisms that realize it:
- **Real-time pinning:** the Risk Engine process is pinned to its dedicated core (`taskset`) with
  real-time priority under `SCHED_FIFO` (`chrt`) — the concrete mechanism for v1.3's "Core 2,
  isolated, highest priority; cannot be preempted by background tasks."
- **Transport substrate:** ZeroMQ over local Unix domain sockets (`ipc://`), bypassing TCP/IP —
  the substrate beneath v1.3 §12.7's locked PUB/SUB + snapshot-on-subscribe pattern. State changes
  (working / filled / rejected) publish on the bus exactly as v1.3's feedback contracts specify.
- **Charts:** strategy ingestion natively supports Renko bricks alongside time-based bars,
  matching the locked platform decision.

## 4. Backup & Disaster Recovery Policy
Balances compliance, storage efficiency, and deterministic recovery. (Postgres event-log semantics,
WAL, group-commit: v1.3 §9/§12.4. This section owns everything after durability: copies, offsite,
retention, and proof of restorability.)
- **Timezone:** daily snapshot boundaries and settlement alignment use `America/Chicago`
  (CME/CBOT settlements) — ops boundary only; trading-path timestamps remain UTC per v1.3.
- **Rotation:** weekly full `pg_dump` base backups (Saturdays) + daily Close-of-Day differentials
  (Sunday–Friday).
- **Cryptographic verification:** every backup SHA-256 hashed locally, uploaded to Backblaze B2
  via `b2sdk`, integrity cryptographically verified remote-side.
- **Retention buffer (N-2):** the node retains current + previous Saturday base before pruning —
  no deletion race.
- **Recovery auditing (monthly, automated dry-run):** restore remote base, apply differentials,
  poll the active broker API for intraday gap recovery, validate total ledger parity — the
  broker-is-truth reconciliation philosophy of v1.3 applied to DR.

---

*Superseded and removed from the original elements.md: the Strategy→Risk→Allocator pipeline order
(v1.3 locks Strategy→Allocator→Risk Engine→broker); the Broker Library as a separate heartbeated
endpoint with Paranoid-Pirate PING/PONG; the LOCKDOWN state (jobs now owned by HALT,
flatten-on-uncertainty, and reconciliation); "Project IO" naming (now **Nix**; the frozen spec retains its historical NICS spelling).*

*v2.1: Nix canonical naming; spec path + NICS/node02 alias notes; §12A-semantics/JSON-physical
config reconciliation. No behavioral content changed.*
