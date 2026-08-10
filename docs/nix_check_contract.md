# nix_check_contract — Nix provisioning engine and check contract — v1.1.0

**Status: derived implementation spec, subordinate to `VERIFY-AND-CHECKS.md`.** Governs
`bootstrap.sh`, `install.sh`, `scripts/verify.py`, and every `checks/check_*.py`.

**Authority order.** `VERIFY-AND-CHECKS.md` (verification doctrine, external, inherited) →
this file (Nix-side mechanics) → `elements_v2.md`. Where this file meets
`nics_risk_subsystem_spec_v1.3.md`, the risk spec wins — this layer provisions and inspects the
*environment*, never the trading path. `elements_v2.md` §1.2/§1.3 is superseded by this document
for provisioning mechanics (reconciliation table: §13). **This file may narrow or operationalise
the doctrine; it may never contradict it.** §15 is the conformance map and is the first thing to
read when the two appear to disagree.

**Provenance, stated plainly.** ARC 008 required following `VERIFY-AND-CHECKS.md` "exactly" while
that document was not on the machine. This file was authored in ARC 008 as a reconstruction and
was wrongly indexed as *the* authority. The real document arrived in ARC 010 and now holds that
name and that role; this file was renamed from `VERIFY-AND-CHECKS.md` to
`nix_check_contract.md` and demoted to derived status. Section numbers here are this file's own
and are what `checks/*.py` and `scripts/nixverify/*` cite; doctrine citations use the real
document's Part/section letters (A.2, B.4, C.3 …).

---

## 1. The standing rule — a ledger obligation, not a build gate

> **Every environment change owes a check.** Installing a package, writing a setting, wiring a
> unit, creating a file — each obligates a `checks/check_*.py` that can verify it, and, where
> possible, correct or install it.

**The obligation is recorded, not blocking** (doctrine A.7). An arc that makes an environment
change and does not write its check records the debt in `docs/CHECK-DEBT.md` and proceeds. The
check system is deliberately built late, because a check declares a desired state and most of
Nix's desired states do not exist yet.

**Do not build a gate on "CHECK-DEBT fully drained."** Doctrine A.7 records the measured
counter-example: on the predecessor system that ledger rose monotonically across seventeen arcs
and never once fell. A gate whose criterion the trend line says can never be met is furniture.
The drain target is per-arc movement, not zero.

§3 keeps the rule structural where it can be: a component's installation procedure lives *only*
in its check, so there is nowhere else to put it.

---

## 2. Core directives applied

1. **Prove real effective state, never a proxy.** A check confirms the thing works, not that a
   config file mentioning it exists.
2. **Fail closed and loud**, and distinguish *failed* from *unmeasurable* (§4).
3. **Enforce mechanically where possible** (§5) rather than relying on author diligence.
4. **Never anchor to a moving value.** Read expected values from their source at check time;
   never hardcode today's value as a literal.

---

## 3. Boundary: what `install.sh` owns vs what a check owns

> **`install.sh` installs only what `verify.py` needs in order to run at all.
> Everything else is a check.**

Mechanically decidable; no per-package debate. The resulting floor is two apt packages:

| Component | Owner | Reason |
|---|---|---|
| `git`, `python3-venv` | `install.sh` | not present on stock Ubuntu Server; needed before verify.py can run |
| `python3` | `install.sh` | present on stock Ubuntu Server; still explicitly ensured, never assumed |
| `.venv` | check | engine is stdlib-only (§9), so it can rebuild the venv it does not run from |
| everything else | check | Postgres, Xvfb, IB Gateway, systemd units, `nix-trading.slice`, DB schema, pinned Python deps |

`install.sh` runs `apt-get update` first: packages are ensured **present and current**, never
assumed present.

**Floor components still get checks — verify-only ones.** A check detects that `git` was removed
or `python3` was upgraded underneath us; it returns `FAIL_NEEDS_OPERATOR` ("re-run install.sh")
rather than attempting a self-repair it cannot perform. The floor is watched by checks that know
they cannot fix themselves.

---

## 4. Check contract

`checks/check_<name>.py`, stdlib-only at module scope.

```python
class Mode(StrEnum):          # install ⊇ correct ⊇ verify
    VERIFY  = "verify"        # detect and report only
    CORRECT = "correct"       # verify + repair what is broken
    INSTALL = "install"       # correct + install what is absent — idempotent

class Status(StrEnum):
    PASS                = "pass"
    FAIL_REPAIRABLE     = "fail_repairable"
    FAIL_NEEDS_OPERATOR = "fail_needs_operator"
    CANNOT_MEASURE      = "cannot_measure"
    SKIPPED             = "skipped"

@dataclass
class CheckResult:
    name:     str
    status:   Status
    site:     str = ""                # the SPECIFIC setting/path/port at fault
    evidence: str = ""                # what was actually measured
    detail:   str = ""
    action:   str = ""                # what correct/install actually did
    upstream_available: str = ""      # advisory only (§7)

def run(mode: Mode, ctx: Context) -> CheckResult: ...
```

Module-level metadata — **the check declares what it needs; the manifest declares when it runs**
(§6). One source of truth per fact, so the two can never disagree:

```python
PRIVILEGE   = "user" | "root"
INTERACTIVE = False    # True → runnable only from install.sh, never headless
DISRUPTIVE  = False    # True → restarts a service / swaps a package (§8)
```

`INSTALL` is **idempotent**: it installs what is absent and corrects what is wrong. It never
force-reinstalls a correct component. The boot unit runs a repair mode on every boot; a
force-reinstall firing there would be destructive.

### 4.1 Status semantics

| Status | Meaning | `--correct` behaviour |
|---|---|---|
| `PASS` | verified correct against real state | nothing |
| `FAIL_REPAIRABLE` | wrong or absent, and fixable without a human | fix it |
| `FAIL_NEEDS_OPERATOR` | requires human input the engine cannot supply (e.g. an absent API key) | **refuse** — report, direct to `install.sh` |
| `CANNOT_MEASURE` | truth is unknowable right now (service down, host unreachable) | **not a failure** — report, continue |
| `SKIPPED` | did not run (halted block, wrong privilege, `INTERACTIVE` while headless) | n/a |

`CANNOT_MEASURE` must **never** collapse into a failure status. A connection exception means the
gate could not measure — not that the subject is misconfigured. Collapsing them makes a downed
service indistinguishable from a broken one and sends `--correct` into a repair loop against a
defect that does not exist.

`FAIL_NEEDS_OPERATOR` must **never** be auto-repaired. The engine cannot invent an account number.

### 4.2 Exit-code contract

Each check module carries a `__main__` block mapping status → exit code, so it is independently
runnable. `verify.py` imports `run()` and receives the full status. **One implementation, two
contracts, no duplicated logic.**

| Status | Exit |
|---|---|
| `PASS` | `0` — PASS |
| `FAIL_REPAIRABLE`, `FAIL_NEEDS_OPERATOR` | `1` — FAIL |
| `CANNOT_MEASURE`, `SKIPPED` | `2` — CANNOT MEASURE |

`SKIPPED → 2` deliberately: a check that never ran reporting exit `0` is vacuous success, the
exact failure this document exists to prevent.

**`verify.py` aggregate exit**, failure dominating: any `FAIL_*` → `1`; else any
`CANNOT_MEASURE`/`SKIPPED` → `2`; else `0`.

---

## 5. Non-vacuity — enforced, not asserted

A check that returns `PASS` without measuring anything is worse than no check: it converts an
unknown into a false assurance. Two `CheckResult` fields make this mechanical:

- **`evidence` is required for `PASS`.** It records what was actually measured
  (`"TCP connect 127.0.0.1:4002 ok, serverVersion=176"`). The engine **rejects** a `PASS` with
  empty `evidence`, converting it to `CANNOT_MEASURE`. A check that short-circuits therefore
  cannot report success.
- **`site` is required for any `FAIL_*`.** It names the specific setting, path, or port at fault
  (`"jts.ini:ReadOnlyApi"`), not a generic failure string. The engine rejects a `FAIL_*` with
  empty `site`.

### 5.1 Demonstrated FAIL-with-CONTROL

Before a check is accepted, its author demonstrates the full cycle and records it in the arc's
`RESULTS.md`:

1. **PASS** — clean run against correct state.
2. **Non-vacuity** — confirm the run genuinely exercised its measurement (non-empty `evidence`
   naming a real observation), not a skipped or short-circuited path.
3. **Plant a defect** — point the check at a wrong port, flip a flag it inspects, remove a file.
4. **FAIL, specifically** — confirm it fails *and* that `site` names the planted defect. A check
   that fails generically has not been shown to discriminate.
5. **Remove the plant.**
6. **PASS again** — the control. This is what proves the failure was caused by the plant and not
   by ambient conditions.

Steps 1 and 6 together are the CONTROL. A demonstration missing step 6 shows only that the check
can fail, not that it fails *for the right reason*.

### 5.2 How a standing RED is closed (doctrine B.4)

**A standing RED is closed by making the gate STRICTER, or by fixing the code — never by
weakening, unregistering, exempting, or re-scoping the gate.**

The tempting failure has a specific shape, and the doctrine records it: a gate went RED on a
*correct* implementation inside the very module it guards, and the obvious fix was to exempt that
file — which would have blinded the gate to the one module that can actually reach the field it
protects. **A gate that fails on the correct implementation of its own subject is not strict; it
is broken, and the repair belongs to the gate's logic, not to its scope.**

Two consequences for Nix:

- Narrowing a rule's *scope* (a path exclusion) is almost always the wrong repair. Retiring a
  *rule* that provably has no discriminating power in this codebase is a different act, and is
  legitimate only with the measurement that shows it, recorded at the point of change.
- A newly-repaired instrument has no standing RED to weaken. Calibrating it as it comes online is
  not the act B.4 prohibits — but it must still be measured, not asserted.

### 5.3 Non-vacuity has two halves

`validate_result()` enforces that a `PASS` recorded *some* measurement. It cannot enforce that the
gate's **scope contained its subject** — doctrine C.3's actual requirement, and the failure it
records: a rule was added to a scanner and inherited a scope that made it structurally unable to
see the file it was written about. It would have passed forever.

**Scope containment is proven per-gate, in that gate's test, before any plant** — by asserting
the gate's own file list or connection attempt genuinely reaches the subject. An empty scope must
be `CANNOT_MEASURE`, never `PASS`. Nix's measured instance of this class is bandit (ARC 010):
27 of 27 files "skipped (exception while scanning file)", zero findings, **exit 0** — a green
commit gate that had scanned nothing since ARC 006.

### 5.4 A plant never touches a production artifact (doctrine C.8)

The doctrine's incident: a synthetic row was planted into an **append-only** datastore to prove a
detector could fire. The detector worked; the row is permanent, unsupersedable, and still in the
canonical series. **The instrument was right; the method was wrong.**

For Nix a plant is legitimate only where it is provably reversible, and reversibility must be
*shown*, not assumed:

- **Version-controlled source** — plant, prove, `git checkout --`, then show a clean `git status`.
  This is the normal case and is why §5.1 step 6 exists.
- **A scratch copy of a config** — point the check at a temporary file rather than editing the
  live one.
- **Never** into `sessions/SESSION.md`, `logs/`, the `trade_history` database, or any other
  append-only or banked-evidence artifact. There is no unplant for those.

### 5.5 One instrument per property (doctrine C.9)

**Extend an instrument that already owns a property; never build a second.** Two instruments
measuring one property will disagree, and there will be no way to tell which is right. Before
writing a new `check_*.py`, name the property it owns and confirm no registered check already
claims it; if one does, extend that check. The split must be stated in both checks' docstrings so
the boundary survives the next author.

---

## 6. Registry — `checks/registry.json`

**The single source of what is registered** (doctrine D.5); every consumer derives from it and
none restates its contents. Beyond membership it owns **ordering, parallelism, and failure
policy only**. Named `registry.json` per doctrine A.4/D.5 — it was `verify_manifest.json` until
ARC 010.

```json
{
  "manifest_version": "1.0.0",
  "blocks": [
    { "name": "bootstrap-floor",
      "on_fail": "halt",
      "checks": ["check_python_runtime", "check_git", "check_venv"] },

    { "name": "credentials-and-identity",
      "checks": ["check_node_identity", "check_sealed_credentials"] },

    { "name": "system-services",
      "parallel": true,
      "checks": ["check_postgres", "check_unattended_upgrades",
                 "check_systemd_units", "check_trading_slice"] },

    { "name": "trading-stack",
      "parallel": true,
      "checks": ["check_python_deps", "check_ibgateway_config", "check_db_schema"] }
  ]
}
```

- Blocks run in listed order. A block is a single check or a parallel group; a manifest may mix
  both freely.
- `parallel: true` → threads. Checks are I/O-bound (subprocess, socket, apt); the GIL is
  irrelevant. Checks share no mutable state.
- `on_fail: "halt"` stops the run. Default is **continue**, so one unrelated failure does not
  blind the operator to everything downstream.
- **Results print in manifest order, never completion order.** Nondeterministic ordering makes
  runs undiffable, defeating drift detection.
- A check raising an exception is caught, becomes its own `CANNOT_MEASURE`, and never aborts the
  run — including at *import* time (§9).

---

## 7. Version policy

Two distinct things get called "up to date"; only one is safe to repair unattended.

| | Meaning | Auto-repair |
|---|---|---|
| **Conformance to pin** | manifest pins `ib_async==2.1.0`; box has `2.0.1` | **Yes** — drift; reinstall to pin |
| **Upstream newer exists** | `ib_async 2.2.0` released | **No** — a decision, not a defect |

Auto-chasing latest would let an unattended Saturday run swap the library that places orders — no
human, no test cycle, no review. That is the opposite of fail-closed. Upstream availability is
reported via `upstream_available` as advisory; bumping a pin is a human action.

**Three package classes:**

- **apt/system** (`python3`, `git`, Postgres) — patching is owned by `unattended-upgrades`, which
  exists for this and has its own reboot policy. The check verifies it is **enabled and healthy**;
  verify.py does not reimplement OS patching, so there are not two owners racing.
- **Pinned Python deps** (`ib_async`) — conformance-to-pin enforced and repaired; upstream
  advisory only.
- **Vendor binaries** (IB Gateway) — advisory only. Its version determines API behaviour and it
  updates on the vendor's schedule regardless.

---

## 8. Privilege and disruptive actions

Two units, **one manifest**, privilege declared per check (§4). A second manifest file would
drift against the first; a per-check declaration cannot.

| Runner | Privilege | Runs | Disruptive actions |
|---|---|---|---|
| `nix-verify.service` (boot) | `User=bbt` | `PRIVILEGE == "user"` | **refused** |
| `nix-verify-weekly.service` (weekly timer) | `User=bbt` | `PRIVILEGE == "user"` | permitted |
| `nix-verify-root.service` (weekly timer) | root | `PRIVILEGE == "root"` | permitted |
| `install.sh` | sudo, human present | all, including `INTERACTIVE` | permitted |

**Three automated runners, not two.** The weekly *user* unit exists because a `user`-privilege
check that is also `DISRUPTIVE` would otherwise be reachable by no runner at all: the boot unit
refuses disruptive work and the root unit skips it on privilege. That gap was live — pin drift on
the order-placing library was detected at every boot and repaired never — and the fix is a
separate `User=bbt` unit rather than a second `ExecStart` on the root one, because running user
checks as root would let the venv be rebuilt root-owned and break the operating user. Privilege
separation is the point; widening the root unit would defeat it.

**Every check in the manifest must be reachable by some runner.** This is enforced by a test that
parses `install.sh`'s actual invocations and cross-checks them against each check's declared
`PRIVILEGE`/`DISRUPTIVE` — not by a restated matrix, which would drift.

**Disruptive repairs are gated on maintenance context, not on mode.** A boot can occur at any
time, including mid-session; a repair that restarts a service or swaps a package must not fire
there. The boot path repairs only non-disruptive drift (file modes, ownership, missing config).
`DISRUPTIVE` work is confined to the weekly window — Saturday 03:00 America/Chicago, which the
risk spec's no-new-entry window (30 min before Friday close through Sunday open) makes safe.
This reasoning is enforced in code, not merely documented.

Privilege separation is preferred over a sudoers allowlist for `bbt`: it keeps the blast radius
of a buggy check explicit and auditable rather than granting the whole engine a privilege set it
can grow into.

---

## 9. Engine invariants

`scripts/verify.py` is a thin runner. Non-negotiable:

1. **Stdlib-only.** It must run under system `python3` before `.venv` exists. A single
   convenience import of a third-party module silently breaks bootstrap.
2. **Never reads stdin.** All interactivity lives in `install.sh` (§10). One `input()` reaching a
   check hangs a boot unit indefinitely — surfacing at 03:00 on a Saturday.
3. **Plugin import is isolated.** Module import is wrapped per-plugin; an import failure becomes
   that check's `CANNOT_MEASURE`, never a crash of the run.
4. **A check never imports its subject at module scope.** Probing is indirect
   (`importlib.util.find_spec`, or a subprocess into the venv). Otherwise the check that installs
   a missing package is destroyed by that package being missing — the failure it exists to fix.
5. **Runs from `/usr/bin/python3`, not `.venv/bin/python3`.** A check rebuilding `.venv` while
   executing on `.venv`'s interpreter deletes the interpreter beneath itself. Invariant 1 makes
   the system interpreter sufficient.

---

## 10. Bootstrap and the interview

Target: fresh headless Ubuntu 26.04 LTS → one command → provisioned node.

```
curl -sSLO https://raw.githubusercontent.com/BBTChris/nix/main/bootstrap.sh
sha256sum bootstrap.sh          # compare against published value
bash bootstrap.sh
```

```
bootstrap.sh   — tiny, stable; the only thing the curl URL points at
   ├─ sudo apt-get update && apt-get install -y git python3-venv
   ├─ git clone https://github.com/BBTChris/nix ~/nix
   └─ exec ~/nix/install.sh
         ├─ interview operator → globals (§10.1)
         ├─ secrets      → systemd-creds, TPM2-sealed (§11)
         ├─ non-secrets  → plain config JSON
         ├─ node ID      → derived via blkid → state/node_identity.json
         ├─ python3 -m venv ~/nix/.venv
         ├─ install units: nix-verify.service (boot, user, non-disruptive)
         │                 nix-verify-weekly.service + timer (user, maintenance)
         │                 nix-verify-root.service + timer   (root, maintenance)
         └─ /usr/bin/python3 ~/nix/scripts/verify.py
              --mode install --privilege all --allow-interactive --verbose
```

**`curl … | bash` is prohibited.** The interview reads stdin; if stdin is the pipe, `read` either
consumes the script or hits EOF and the prompts silently collapse. Download-then-execute is a
hard technical requirement, not a stylistic preference.

`bootstrap.sh` is split from `install.sh` so the curl URL stays permanently stable while all real
logic lives in the repo under branch protection and PR review. What gets pasted into a terminal on
a bare box is a few lines the operator can read in full first.

The repo is public (`elements_v2.md` §1.1a), so the clone needs no credentials — this is what
makes the single-command flow possible.

### 10.1 Global inputs

| Field | Storage | Verifiable by a check |
|---|---|---|
| Full name, Email, Mobile | plain config JSON | fully |
| Broker username, password, API key | TPM-sealed | presence + shape only |
| Data-source username, password | TPM-sealed | presence + shape only |
| **BlackBox Node ID** | **derived → `state/node_identity.json`** | **fully — stored vs live** |

**Node ID is derived, never prompted.** It is the v4 UUID of the primary volume, already computed
by `install.sh` via `findmnt` → `blkid`. Prompting invites a typo that would silently mismatch
real hardware. It is derived, displayed for confirmation, and thereafter verified stored-vs-live —
which detects a cloned VM, a swapped disk, or a restore onto different hardware.

**Secrets and non-secrets validate differently.** A check can prove a sealed secret exists, is
correctly permissioned, and is well-formed; it can never prove the value inside is *correct*.
Non-secret globals validate fully.

**Validation has two strengths, and the weaker one runs forever.** `install.sh` validates hard —
the operator is present, so a malformed value is rejected and re-prompted. `verify.py` validates
presence and shape only — it cannot re-prompt, so its job is detecting that a value went missing
or got corrupted. A check author must not assume verify-time validation is as strong as
install-time.

---

## 11. Credential storage

**`systemd-creds` with TPM2 sealing.** Measured on this node (ARC 008): TPM 2.0 present
(`/dev/tpm0`, `/dev/tpmrm0`), `systemd-analyze has-tpm2` → `yes`, systemd 259 built `+TPM2`.

GNOME Keyring / libsecret is the literal macOS Keychain analogue and is the **wrong** choice here:
it requires a D-Bus session and an interactive unlock tied to a login. This node is headless
(`XDG_SESSION_TYPE=tty`, no `DISPLAY`) and must restart unattended. A keyring would block every
reboot on a human typing a password.

Secrets are sealed to this TPM, decrypted automatically at unit start, and delivered into
`/run/credentials/<unit>` — tmpfs, mode `0400`, namespaced to one service, never on disk in
plaintext, never visible to other processes.

**This replaces the Fernet/PBKDF2 master-password mechanism from ARC 006** (`install.sh:40-72`).
That design derived a key from a password prompted at install time and never persisted, so nothing
could decrypt at boot without a human present — contradicting CLAUDE.md's invariant *"Daemons
headless and self-healing; no runtime operator input."* It is latent only because no daemon
consumes those credentials yet. Removing it also drops `cryptography` (its sole consumer,
confirmed by grep) and the `libssl-dev`/`libffi-dev`/`python3-dev` apt deps that existed solely to
build it.

**Sealing binds to the TPM storage root key with no PCR binding.** PCR-bound secrets become
undecryptable after a firmware or secure-boot change — a trading node that will not come up after
a vendor BIOS update. This trades some tamper-evidence for not being bricked; a documented re-seal
path is required.

---

## 12. Installer presentation

Zero external dependencies — `bootstrap.sh` runs before anything is installed. No `dialog`;
`whiptail` is also rejected: its full-screen TUI cannot be piped to a log, and a pasteable install
transcript is worth more than a modal box.

Plain ANSI, with `verify.py` reusing the **identical visual language** so installer and verifier
read as one product.

```
  ╭────────────────────────────────────────────────────────────╮
  │  BLACKBOX TRADING                                          │
  │  Nix Platform · Node Provisioning                   v1.0.0 │
  ╰────────────────────────────────────────────────────────────╯

     Host      ms-01 · Ubuntu 26.04 LTS · 20 cores · 61 GB
     TPM       2.0 present — hardware sealing available
     Node ID   3f9c1a7e-8b22-4d1e-9f03-7a5c2e114db6  (derived)

  ──  2 of 4 · Broker · Interactive Brokers  ──────────────────

     Username         › bbtchris
     Password         › ••••••••••••
     API key          › ••••••••••••••••••••
                        ✖  must be 32 characters — got 20
     API key          › ••••••••••••••••••••••••••••••••

  ──  4 of 4 · Confirm  ───────────────────────────────────────

     Operator         Chris Chapman · chris@example.com
     Broker           bbtchris · password set · API key set
     Node ID          3f9c1a7e-8b22-4d1e-9f03-7a5c2e114db6
     Secrets          4 values → TPM-sealed via systemd-creds

     Nothing has been written yet.

     Proceed?  [Y/n] ›

  ──  Checks  ─────────────────────────────────────────────────

     ✔  python_runtime     3.14.4
     ✔  ib_async           2.1.0 (pinned)
     ⚠  ibgateway_config   CANNOT MEASURE — no listener on 127.0.0.1:4002
     ✖  sealed_credentials FAIL — broker_api_key absent from credstore

     12 passed · 1 failed · 1 cannot measure · 0 skipped     exit 1
```

All four counts always print, including zeros. A stable column set is what makes
consecutive runs diffable — the same reason §6 fixes result ordering. Decorative
punctuation degrades with everything else: the `·` separator becomes `|` and the
`—` before a detail becomes `-` under an ASCII theme, so piped output is genuinely
ASCII rather than merely glyph-free.

Requirements:

- **Degrades cleanly.** No TTY, `NO_COLOR` set, or non-UTF-8 `LANG` → ASCII glyphs
  (`[ok] [FAIL] [??]`) and no escape codes, so piping to a log yields clean text.
- **Secrets never echo.** Masked at entry (`read -rs`), shown as "set"/"not set" in the summary,
  never written to the transcript.
- **Validation is inline and re-prompts** with the specific reason; the operator corrects in place
  rather than restarting the run.
- **Nothing is written until the confirm step.** The interview is fully reversible until then.
- **Glyphs map 1:1 to `Status`:** `✔` PASS · `✖` FAIL_* · `⚠` CANNOT_MEASURE · `·` SKIPPED.

---

## 13. Reconciliation required

This document contradicts current on-disk state and two docs of record. All must be reconciled in
the arc that implements it — a derived artifact may never be left contradicting its source.

**Resolved (ARC 008, Task 13).** Every row below is now verified against disk: the engine runs at
`scripts/verify.py` with no root copy, both systemd units exist on the system interpreter,
`elements_v2.md` §1.2/§1.3 were reconciled, `Status` is five-state, `checks/` is populated. The
table is retained as the record of what was reconciled, not as a live claim.

| Item | Current | Required |
|---|---|---|
| `verify.py` location | `~/nix/verify.py` (repo root) | `~/nix/scripts/verify.py` — per `directory_structure.md` v1.2.0 ("scripts: All Python and shell scripts"); root placement is the deviation |
| `nix-verify.service` `ExecStart` | `.venv/bin/python3 /home/bbt/nix/verify.py` | `/usr/bin/python3 /home/bbt/nix/scripts/verify.py` — §9 invariants 1 and 5 |
| Root unit | none | `nix-verify-root.service` + weekly timer (§8) |
| `elements_v2.md` §1.3 modes | "Quick Summary, Verbose, Verify+Repair" | `verify` / `correct` / `install` (§4); verbosity becomes an orthogonal flag |
| `elements_v2.md` §1.2 credentials | Fernet under master password | `systemd-creds` TPM2 (§11) |
| `CheckResult.ok` | boolean | five-state `Status` (§4) |
| `load_plugins()` | unprotected `exec_module()` | per-plugin isolation (§9.3) |
| `checks/` | empty (`.gitkeep` only) | manifest + checks |

### 13.1 Checks owed under §1

**Moved to `docs/CHECK-DEBT.md`** (ARC 010), which is where doctrine A.4 puts the ledger of
owed-but-unwritten checks. Keeping the list here as well would be two homes for one fact.

---

## 14. Open items

- **`bootstrap.sh` signing.** A SHA256 fetched from the same origin as the script proves nothing
  against a compromised repo. Real verification requires a GPG signature whose fingerprint the
  operator holds out-of-band. Deciding to accept TLS-only is defensible for a public repo holding
  no secrets — but it must be a recorded decision, not an oversight.
- **`install.sh` location.** `directory_structure.md` assigns all shell scripts to `scripts/`, but
  `install.sh` is an entry point and is currently at root. Resolve explicitly rather than by
  drift.

---

## 15. Doctrine conformance map (ARC 010)

Every binding statement in `VERIFY-AND-CHECKS.md`, and where it lives in Nix. **`owed` entries
are debts recorded in `docs/CHECK-DEBT.md`, not silent omissions.**

### 15.1 Rules this file implements

| doctrine | Nix home | verdict |
|---|---|---|
| A.1 declarative · idempotent · assess-and-converge in one unit | §4 `Mode`, `run(mode, ctx)` | matches |
| A.2 one library, drivers are postures | §4 `Mode` verify/correct/install over one `checks/` library | matches |
| A.2 `verify` **read-only by default** | `scripts/verify.py:50` `--mode` defaults to `verify` | matches |
| A.2 correction may not be a separate verb that skips assessment | `run()` assesses first; `repair()` is reached only through it | matches |
| A.4 owed-check ledger at `docs/CHECK-DEBT.md` | created ARC 010 | corrected |
| A.4 / D.5 `registry.json` is the single source of what is registered | `checks/registry.json` (renamed ARC 010) | corrected |
| A.7 check coverage is a **ledger obligation, not a build gate** | §1 restated ARC 010 | corrected |
| B.2 exit `0`/`1`/`2`, and exit `2` must survive | §4.2 | matches |
| B.2 rationale: a gate that measured nothing must not report `1` | §4.1 `CANNOT_MEASURE` never collapses into failure | matches |
| B.4 a standing RED closes by a **stricter** gate or fixed code — never by weakening, unregistering, exempting, or re-scoping | §5.2 (new) | corrected |
| C.1 prove effective running state, never file-presence / import-success / process-alive | §2.1 | matches |
| C.2 demonstrate FAIL **with a CONTROL**, and the gate must name the site | §5.1 | matches |
| C.3 prove non-vacuity **before** the plant — assert the gate's scope contains its subject | §5.1 step 2, §5.3 (new) | matches + strengthened |
| C.4 never anchor to something that moves | §2.4 | matches |
| C.7 fail closed and loud | §2.2 | matches |
| C.8 a plant never touches a production artifact | §5.4 (new) | corrected |
| C.9 extend an instrument that owns a property; never build a second | §5.5 (new) | corrected |
| D.2 keep the exit-code contract including exit 2 | §4.2 | matches |
| D.7 write about unbuilt things in the future tense | §13 table reframed ARC 008; enforced by review | matches |

### 15.2 Nix additions beyond the doctrine — compatible, retained

These have **no counterpart in the doctrine**; it neither requires nor forbids them. Recorded
here so no future reader mistakes them for quotations from it.

| addition | why Nix needs it | doctrine compatibility |
|---|---|---|
| **Five-state `Status`** (§4) — `PASS` / `FAIL_REPAIRABLE` / `FAIL_NEEDS_OPERATOR` / `CANNOT_MEASURE` / `SKIPPED` | the doctrine gives three *exit codes*, no vocabulary for "broken and I may not fix it myself". Nix checks converge (A.1), so `--correct` must distinguish "reinstall the pin" from "the engine cannot invent an account number" | strict refinement: §4.2 maps all five onto exactly `0`/`1`/`2`, preserving B.2 |
| **Mechanically-enforced non-vacuity** (§5) — engine rejects a `PASS` with empty `evidence` and a `FAIL_*` with empty `site` | C.2/C.3 are authoring disciplines; an author can forget one. `validate_result()` cannot | strengthens C.2/C.3; enforces what they require |
| **Three automated runners** (§8) — boot-user, weekly-user, weekly-root | Nix-specific systemd topology. A `user`-privilege check that is also `DISRUPTIVE` was reachable by no runner at all; pin drift on the order-placing library was detected at every boot and repaired never | doctrine is silent on runners |
| **`DISRUPTIVE` gates the repair, not the inspection** (§8) | a boot can occur mid-session; a repair that restarts a service must not fire there, but the *drift report* must still be produced | consistent with A.2's read-only-by-default reasoning, extended to a second axis |
| **`PRIVILEGE` / `INTERACTIVE` module metadata** (§4) | headless daemons; a check that reads stdin hangs a boot unit | doctrine is silent |
| **`upstream_available` / pin-conformance split** (§7) | an unattended run must never swap the library that places orders | doctrine is silent |

**Correction to the ARC 008 handoff.** That handoff reported "amending §8 to say disruptive gates
the repair, not the inspection." The §8 amended was **this file's** §8. The real document has no
§8 and says nothing about disruptive actions, privilege, or maintenance windows. The
"I amended it to match" framing is withdrawn; the rule is a Nix addition, retained on the
reasoning above.

### 15.3 Doctrine rules Nix does not yet satisfy — owed

Recorded in `docs/CHECK-DEBT.md`.

| doctrine | gap |
|---|---|
| A.3 `status` is a filtered view *over* `verify`, never a second program | Nix has no `status` surface at all. When one is built it must derive from `verify` |
| A.5 the directory layout is itself a checkable desired state | `directory_structure.md` is prose; no check declares the tree, so `verify --correct` cannot move a stray file home |
| A.6 `verify` is the predicate authorising release and update | Nix has neither a release driver nor an update driver |
| B.3 the `known-red` marker, and a runner that discriminates expected REDs from new ones | no marker mechanism exists |
| B.6 `prove_*` harnesses — determinism, byte-identical live/replay, clock purity, crash-safety | none exist; there is no trading core to prove yet |
| B.6 baseline **everything that can be RED** on a pristine tree before an arc begins | Nix baselines nothing; ARC 010 is the measured instance — bandit had been RED-blind since ARC 006 and no baseline would have caught it |
| B.7 the self-enforcing pattern: a harness parses a constant out of the spec and asserts the code equals it | `pinned_deps.json` is single-source but no harness reads a *document*. Nearest owed instance: §8's runner table vs `install.sh`'s real invocations (`test_runner_coverage.py` does this for the registry, not for the doc) |
| C.5 prove by absence over the import closure | the stdlib-only scan is textual, not closure-based |
| C.6 compare verdict-by-verdict, never in aggregate | no comparison harness exists yet |
| C.10 one owner per shared global measurement | undeclared; complexity and lint state have no named owner |
| D.6 the gate suite needs its own can-fail: prove a registered gate that *should* fail is actually run and reported end to end | `test_runner_coverage.py` proves reachability, not that a failing gate reddens a real run |

### 15.4 Doctrine statements that are **not** transferable — stated, not silently dropped

CLAUDE.md's mission clause governs here: Nix may inherit *lessons* from prior systems, never
code, resources, or unverified behavioural assumptions. Core directive 5 adds that verified
on-disk state outranks documentation.

- **The top-of-document warning that `verify.py`, `registry.json`, `strategy.py`,
  `bump_version.py` and `risk_engine` "are all absent," and that `checks/` holds only
  `.gitkeep`.** That is an inventory measurement of **`~/luna/`**, not `~/nix/`. Measured on this
  tree, ARC 010: `scripts/verify.py`, `checks/registry.json`, and four `checks/check_*.py` exist
  and 126 tests exercise them. **The doctrine's *rule* — "this file names desired state, never
  inventory; the tree is the authority on what exists" — is inherited and binding. Its
  *inventory* is not.**
- **Part A is labelled DESIGN, not built.** True of Luna. Nix built its `verify` in ARC 008/009
  under Part D's brief. Nix therefore writes about `scripts/verify.py` in the present tense
  *because it was measured on disk*, which is what D.7 actually asks for.
- **B.1 `bank.sh` runs the registered gates at STEP 2 of every arc bank.** Nix has no `bank.sh`.
  Its enforcement points are `.pre-commit-config.yaml` (per commit) and `verify.py` (per boot and
  weekly). The *property* B.1 protects — the gate suite runs unconditionally at the arc boundary
  and its verdict is banked — is **owed**, not met: nothing runs `verify.py` at an arc boundary.
  Recorded in `CHECK-DEBT.md`.
- **B.5's representative gate table** names nine Luna gates (`anchor-derivation`,
  `check_readonly_boundary`, `check_mid_overlap` …). None exist in Nix and none should be
  recreated speculatively — they guard subsystems Nix has not built. The **lessons** attached to
  them are inherited; `check_complexity.py`'s in particular ("wraps `complexipy` because the tool
  exits 0 on zero files") is the exact failure class ARC 010 found in bandit.
- **A.7's "95 → ~190 across seventeen arcs" CHECK-DEBT series.** Luna's measurement. Nix's ledger
  starts at ARC 010 and its own series must be measured, not assumed to follow Luna's.

---

## Changelog

**v1.1.0 (ARC 010)** — reconciled against the real `VERIFY-AND-CHECKS.md`, which arrived on disk
this arc. Renamed from `VERIFY-AND-CHECKS.md` to `nix_check_contract.md` and demoted from
"authority" to derived implementation spec. §15 added: full doctrine conformance map, including
the additions this file makes beyond the doctrine and the doctrine rules Nix does not yet
satisfy. §1 restated as a ledger obligation per doctrine A.7 (was implicitly a build gate).
§6 registry renamed `verify_manifest.json` → `checks/registry.json` per A.4/D.5. §13.1 backlog
moved to `docs/CHECK-DEBT.md` per A.4. §5.2–§5.5 added from doctrine B.4, C.3, C.8, C.9. The ARC
008 claim of "amending §8 to match the doctrine" is withdrawn — the doctrine has no §8; see
§15.2.

**v1.0.1 (ARC 008)** — §14 `Context` resolved: implemented as a frozen dataclass
carrying `nix_home`, `mode`, `privilege`, `maintenance`, `allow_interactive`
(`scripts/nixverify/contract.py`). `bootstrap.sh` signing and `install.sh` location
remain open.

**v1.0.0 (2026-08-09, ARC 008)** — first authoring. Establishes the standing check rule, the
install.sh/check boundary criterion, the five-state check contract with mechanically-enforced
non-vacuity, the exit-code contract (`0`/`1`/`2`), the manifest block model, the two-unit
privilege split, pin-conformance version policy, TPM2 credential sealing replacing Fernet, engine
invariants, and the single-command bootstrap flow.
