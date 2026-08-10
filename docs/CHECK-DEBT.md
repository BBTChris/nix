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
| 2026-08-10 | ARC 010 | 24 | — (ledger opened) |
| 2026-08-10 | ARC 011 | 23 | **−1** — D1.8/D1.9 discharged by `check_ibgateway_service`; D1.12 opened |
| 2026-08-10 | ARC 012 | 24 | **+1** — D1.13 opened; D1.12 narrowed (cutover done, reboot still owed); nothing discharged |
| 2026-08-10 | ARC 013 | 25 | **+1** — D1.13 re-scoped (subscription decision closed, gate still owed); D1.14 split out |

> **Count corrected ARC 012.** The ARC 010 and ARC 011 rows originally read 22 and 21. Both were
> wrong: I hand-counted the rows and got it wrong twice in a row. Counted mechanically the figures
> are 24 and 23 (D1 ×11, D2 ×12, D3 ×1 today). The banked `SESSION.md` entries still say 22→21 and
> are deliberately left alone — history is appended, never rewritten — so this note is the
> correction of record.
>
> **This is the ledger being the instrument's own defect**, which is the failure class
> `VERIFY-AND-CHECKS.md` Part C opens with. The count is hand-maintained prose asserting a number
> the table already determines — precisely the `derive, never restate` violation doctrine **B.7**
> exists to catch, and it is already recorded as debt **D2.8**. Discharging D2.8 with a harness
> that counts the rows and asserts the latest series figure would have caught this on the first
> commit; until then, recount mechanically before editing this table.

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
| D1.11 | **ReadOnlyApi state** — no check covers it | ARC 010 | unassigned. Measured OFF in ARC 010, but only by sending a `whatIf` order and observing it reach IBKR's margin engine (err 201) instead of being refused. The setting is not in plaintext `jts.ini` (encrypted store) and the API exposes no read-only flag, so **the only known probe is order-shaped**. `check_ibgateway_config.py` deliberately does not carry it: a gate that must construct an order to run is the wrong instrument for a boot-time environment check. Revisit when broker-order code exists and can host the probe |
| D1.12 | **Reboot behaviour of `nix-xvfb.service` / `nix-ibgateway.service`** | ARC 011 | **still open, narrowed by ARC 012.** The cutover is done — both processes are systemd-owned (cgroup `/system.slice/nix-*.service`, API socket served by the unit's own MainPID) and `verify.py` is green. What remains unproven is only that systemd starts them **at boot**: `systemctl is-enabled` is a declaration, not evidence. A reboot was offered as a separate authorization in ARC 012 and declined (second IB Key tap). Discharge: reboot, then run `check_ibgateway_service` **before anyone touches the console** — a human logging in first creates the very state the check must observe independently |
| D1.13 | **No gate asserts the Stage 0 market-data path** | ARC 012, re-scoped ARC 013 | unassigned. **The subscription half of this debt is CLOSED** — ARC 013 settled it: Stage 0 runs on IBKR's free feed, no purchase (see `dev_and_services_plan.md`). What remains is a gate. ARC 013 measured the real path: **no real-time** (err 354, no grant callback), **delayed works** at a measured **10 min**, and a request for delayed-frozen (4) was **silently granted as delayed (3)**. So the owed gate is: assert the *granted* `marketDataType` is what Stage 0 declares, and FAIL on a silent downgrade — never infer the mode from the request. Build it with broker-datafeed, not before |
| D1.14 | **Bar immutability on a re-requestable feed** | ARC 012, split out ARC 013 | unassigned — blocked until broker-datafeed exists. Stage 0's feed is delayed **and** polled; polled history is re-requestable and can return revised values, so the bar builder needs its own seal-and-never-rewrite rule. Split from D1.13 because it discharges in a different arc, and it stays owed even after a real-time feed arrives at Tradovate |

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
