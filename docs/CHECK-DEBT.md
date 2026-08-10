# CHECK-DEBT — the ledger of owed-but-unwritten checks

**Home mandated by `VERIFY-AND-CHECKS.md` A.4.** Opened ARC 010 (2026-08-10).

Every environment change owes a check (`nix_check_contract.md` §1). The check system is built
late by deliberate sequencing (doctrine A.7), so that obligation is **recorded here rather than
blocking the arc**.

**Do not build a gate on "this ledger is empty."** Doctrine A.7 records the measured
counter-example: on the predecessor system this series rose monotonically — 95 → ~190 across
seventeen arcs — and never once fell. The target is per-arc movement, not zero.

**A debt names the arc that can actually discharge it, or names nobody.** Doctrine B.3: *an owner
that cannot pay is no owner wearing a name.* `owner: unassigned` is honest; an owner pointed at an
arc whose own scope forbids the fix is furniture.

## Series

| date | arc | open debts | delta |
|---|---|---|---|
| 2026-08-10 | ARC 010 | 22 | — (ledger opened) |
| 2026-08-10 | ARC 011 | 21 | **−1** — D1.8/D1.9 discharged by `check_ibgateway_service`; D1.12 opened |

---

## D1 — Environment changes made, no check written

Each is an environment change that has already happened on this node.

| # | subject | changed in | owner |
|---|---|---|---|
| D1.1 | sealed credentials (`systemd-creds` TPM2) | ARC 008 design | unassigned — blocked on the Fernet→systemd-creds migration arc |
| D1.2 | `nix-trading.slice` core pinning (`AllowedCPUs=0-5`) | ARC 006 | unassigned |
| D1.3 | systemd units exist, enabled, and `ExecStart` matches the spec'd interpreter | ARC 006/008 | unassigned — `scripts/tests/test_systemd_units.py` reads the unit *files*; nothing reads the running system |
| D1.4 | `trade_history` schema conformance vs `nix_db_schema_spec.docx` | ARC 006 | unassigned |
| D1.5 | Postgres cluster present, running, roles separated | ARC 006 | unassigned |
| D1.6 | `unattended-upgrades` enabled and healthy | ARC 006 | unassigned — §7 makes this the *only* owner of OS patching, so its health is load-bearing |
| D1.7 | `git` present (floor component, verify-only per §3) | ARC 006 | unassigned |
| D1.10 | pre-commit hook suite installed and each hook actually capable of failing | ARC 006 / ARC 010 | unassigned — see D3.2 |
| D1.12 | **Reboot behaviour of `nix-xvfb.service` / `nix-ibgateway.service`** — enablement is verified, boot is not | ARC 011 | unassigned. No reboot was performed (it would drop the authenticated Gateway session and cost a manual 2FA re-login). `systemctl is-enabled` is a *declaration* that the units will start at boot, not evidence that they do. Discharge by rebooting under human authorization and re-running `check_ibgateway_service` before any human touches the console |
| D1.11 | **ReadOnlyApi state** — no check covers it | ARC 010 | unassigned. Measured OFF in ARC 010, but only by sending a `whatIf` order and observing it reach IBKR's margin engine (err 201) instead of being refused. The setting is not in plaintext `jts.ini` (encrypted store) and the API exposes no read-only flag, so **the only known probe is order-shaped**. `check_ibgateway_config.py` deliberately does not carry it: a gate that must construct an order to run is the wrong instrument for a boot-time environment check. Revisit when broker-order code exists and can host the probe |

Discharged: `.venv` (`check_venv`), `python3` (`check_python_runtime`), node identity
(`check_node_identity`), `ib_async` pin (`check_python_deps`), IB Gateway API configuration
(`check_ibgateway_config`, ARC 010), Xvfb + IB Gateway boot persistence
(`check_ibgateway_service`, ARC 011).

## D2 — Doctrine rules Nix does not yet satisfy

From `nix_check_contract.md` §15.3.

| # | doctrine | gap | owner |
|---|---|---|---|
| D2.1 | A.3 | no `status` surface; when built it must be a view over `verify`, never a second program | unassigned |
| D2.2 | A.5 | the directory tree is prose in `directory_structure.md`, not a declared checkable state — `verify --correct` cannot move a stray file home | unassigned |
| D2.3 | A.6 | no release driver and no update driver, so `verify` gates no irreversible act | unassigned |
| D2.4 | B.1 | nothing runs `verify.py` at an arc boundary and banks its verdict. Nix has no `bank.sh`; pre-commit covers per-commit only | unassigned |
| D2.5 | B.3 | no `known-red` marker mechanism, so an unexpected RED cannot be discriminated from an expected one | unassigned |
| D2.6 | B.6 | no `prove_*` harnesses (determinism, live/replay byte-identity, clock purity, crash-safety) | unassigned — blocked until a trading core exists |
| D2.7 | B.6 | nothing is baselined on a pristine tree before an arc begins. **ARC 010 is the measured instance:** bandit had been scanning nothing since ARC 006 and no baseline existed to catch it | unassigned |
| D2.8 | B.7 | no harness parses a constant out of a document and asserts the code equals it. Nearest owed instance: §8's runner table vs `install.sh`'s real invocations | unassigned |
| D2.9 | C.5 | the stdlib-only scan is textual, not proof-by-absence over the import closure | unassigned |
| D2.10 | C.6 | no verdict-by-verdict comparison harness | unassigned — nothing to compare yet |
| D2.11 | C.10 | no named owner for shared global measurements (tree-wide complexity, lint state) | unassigned |
| D2.12 | D.6 | `test_runner_coverage.py` proves every registered check is *reachable*, not that a registered gate which should fail actually reddens a real run end to end. **A suite that silently skips a gate reports GREEN** | unassigned |

## D3 — Instruments whose can-fail has never been demonstrated

Doctrine C.2: a gate is guilty until shown able to say no.

| # | instrument | status | owner |
|---|---|---|---|
| D3.1 | `bandit` | **discharged ARC 010** — was scanning nothing (exit 0 over 27 skipped files) since ARC 006; repaired to 1.9.4 and proven to fail on a planted `shell=True` and name the site | — |
| D3.2 | `ruff`, `pylint`, `mypy`, `complexipy`, `pytest --testmon` | never demonstrated capable of failing on this repo. Doctrine B.5 records `complexipy` exiting 0 on zero files as exactly this class | unassigned |
