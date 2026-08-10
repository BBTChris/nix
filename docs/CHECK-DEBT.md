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
| 2026-08-10 | ARC 014 | 25 | **0** — *row reconstructed ARC 016; ARC 014 recorded none.* Landed `scripts/broker/` and the adapter suite; opened no debt and discharged none |
| 2026-08-10 | ARC 015 | 26 | **+1** — *row reconstructed ARC 016; ARC 015 recorded none.* D1.15 opened; D3.2 split into D3.2/D3.3/D3.4 with D3.2 and D3.3 **discharged**, leaving D3 at one open row either side, so the split is net zero |
| 2026-08-10 | ARC 016 | 27 | **+1** — D1.15 **discharged** (seam simulation now in the pytest suite); D1.16 and D1.17 opened (`state/encrypt_credentials.py` invisible to every gate; one `disconnect()` emits two `on_session(DOWN)`, measured live). The vacuous-pass class was **promoted to `debug.md` §7.12**, which removes no row: a doctrine principle is not a discharged debt |
| 2026-08-10 | ARC 017 | 30 | **+3** — six opened, three discharged. D2.8 **discharged** (the derive-never-restate harness, open since ARC 010); D3.4 `pytest --testmon` **discharged**; D3.6 `bandit (tests)` **opened and discharged** in the same arc (split out of D3.1, which had wrongly claimed its coverage since ARC 010); D3.5 `ruff-format` **opened and left open** — caught but did not name the site, so a formatter rather than a gate; D2.13 opened (the runtime hook reports GREEN having selected zero tests, exit 0 not 5). Phase 4 then added the rows sub-agents A and C owed but were forbidden to write: D1.18 (an IBKR error integer still crosses the seam inside `on_ack(reason)`), D2.14 (a hand-rolled retry loop is banned by §2.1 and undetected by the new gate), D2.15 (the new gate scans one directory and nothing guards that the order path still lives there). Net +4: five opened, one discharged, one opened-and-discharged. **This row was itself corrected by the harness it belongs to** — see below |

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
>
> **ARC 016 recounted mechanically** (regex over the `D1.`/`D2.`/`D3.` rows, classifying each by
> whether its owner cell says *discharged*) and got **27 open — D1 ×14, D2 ×12, D3 ×1**. The ARC 014
> and ARC 015 rows above were **reconstructed by that same count**, not remembered: neither arc added
> a row at all, so the series silently skipped two arcs. **A ledger that stops being written is
> indistinguishable from a ledger with nothing to report** — which is instance #2's failure in a
> different costume, and the reason D2.8 (once discharged) should assert the row exists as well as
> that its number is right.
>
> **ARC 017 recounted mechanically** and got **28 open — D1 ×14, D2 ×13, D3 ×1** over **34 rows**
> (6 discharged). Two corrections to the procedure itself, both found by running it:
>
> 1. **The classification rule stated above is not the rule that produces these numbers.** "Classify
>    by whether its *owner cell* says discharged" cannot be what ARC 016 ran: in the **D3** table the
>    columns are `# | instrument | status | owner`, so every D3 discharge is recorded in the *status*
>    cell and the owner cell reads `—`. Applied literally the stated rule returns D3 ×4 open, not the
>    D3 ×1 that ARC 016 reported. The description of the anti-restatement procedure was itself a
>    restatement that did not match what was run. **The rule of record, from here on:** a row is
>    discharged iff some **bold** span in it matches `discharged ARC <n>` —
>    `re.compile(r"\*\*[^*]*\bdischarged ARC \d+", re.I)` over lines matching
>    `^\|\s*D[123]\.\d+\s*\|`. The bold-span restriction is load-bearing, not cosmetic: D3.5's body
>    contains the words *"discharges in whichever arc…"* and a naive `/discharg/` scan counts it as
>    paid. **The harness that discharges D2.8 must use this rule, and this ledger is the wrong
>    authority if the harness disagrees — the harness wins** (ARC 017 §7.3).
> 2. **The series has no gaps.** Every arc 010–017 now has a row; the ARC 014/015 holes the ARC 017
>    brief expected to find were already closed by ARC 016's reconstruction. Verified mechanically by
>    extracting `ARC (\d+)` from the series rows and diffing against the closed range. Reported rather
>    than silently accepted, because the brief and the disk disagreed and **the disk wins**.
>
> **D2.8 is discharged, and its first act was to correct this table.** `checks/check_derived_claims.py`
> (ARC 017) implements the rule of record above and cross-checks it against this series row. In Phase 4
> the ledger was edited to add D1.18, D2.14 and D2.15 and the series row was **deliberately left stale**
> at 28 to see whether the harness would notice. It did, unprompted, naming both sides:
>
> ```
> detail: derived_claims.json:check_debt_open_items: sources disagree
>         — derived:ledger_rows=31, stated:series_table_latest_row=28
> GATE_EXIT=1
> ```
>
> It then caught the *correction* too. Discharging D2.8 itself removed a row, so the freshly-written
> 31 was stale the moment it was written — and the gate said so on the next run
> (`derived:ledger_rows=30, stated:series_table_latest_row=31`) rather than accepting a number that had
> been correct sixty seconds earlier. The row reads **30** because the harness derived 30, not because
> anyone counted. This is the first
> time in the series that the number in this table was produced by a machine rather than asserted by a
> person, and it closes the loop the ARC 012 note above opened: *"discharging D2.8 with a harness that
> counts the rows and asserts the latest series figure would have caught this on the first commit."*
> It would have, and now it does. **The harness is the authority; this prose is not** (ARC 017 §7.3).
>
> **ARC 018, sub-agent A: the series row above is KNOWINGLY STALE as this branch stands, and that is
> not an oversight.** Three sub-agents edited in parallel; only the parent can see all three ledgers at
> once, so only the parent may write the row. A recounted mechanically after its own edits (D2.13 and
> D3.5 discharged, D2.16 opened) and the harness returned `derived:ledger_rows=29,
> stated:series_table_latest_row=30`, `GATE_EXIT=1` — i.e. `verify` is RED on this branch by
> construction, on exactly one claim, and the RED is the instrument working. **Phase 4 writes the row
> from whatever the harness derives after all three branches are merged; nobody types the number.**

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
| D1.10 | pre-commit hook suite installed and each hook actually capable of failing | ARC 006 / ARC 010 | **still open, narrowed again by ARC 018.** Per-hook can-fail now stands at **8 of 8 demonstrated, 0 partial**: `ruff-check`/`pylint`/`mypy`/`complexipy` D3.2 (ARC 015), `bandit (production)` D3.1 (ARC 010), `bandit (tests)` D3.6 (ARC 017), `pytest-affected` D3.4 (ARC 017, re-run ARC 018 after the gate was rebuilt), `ruff-format` D3.5 (ARC 018, adopted `--check`). What remains owed for D1.10 itself is different from any D3 row: nothing *asserts* the suite is installed or that its hook set is intact. `pre-commit run` is invoked by a human or by the git hook; there is no gate that fails when `.pre-commit-config.yaml` loses a hook, when `core.hooksPath` is unset, or when the pinned `rev:` moves to an environment that scans nothing. **ARC 018 re-measured that last condition rather than repeating the claim, and it is NOT acceptable standing risk — it is owed, and this row owns it.** The pre-ARC-010 bandit environment (repo rev `2d0b675`) is still in `~/.cache/pre-commit` and still reproduces the ARC 006 vacuum verbatim: run against this tree's production Python it reported `exception while scanning file` for **every** file, zero findings, **exit 0**; handed a file containing `subprocess.run(cmd, shell=True)` it skipped that too and still exited 0, while the pinned `1.9.4` environment flags it High and exits 1. A `rev:` pin is a declaration; the declaration is currently the only thing standing between this repo and a silent green, and no instrument checks it. Non-vacuity per hook was captured by hand (ARC 017, re-derived ARC 018) — capturing it by hand is not a gate |
| D1.11 | **ReadOnlyApi state** — no check covers it | ARC 010 | unassigned. Measured OFF in ARC 010, but only by sending a `whatIf` order and observing it reach IBKR's margin engine (err 201) instead of being refused. The setting is not in plaintext `jts.ini` (encrypted store) and the API exposes no read-only flag, so **the only known probe is order-shaped**. `check_ibgateway_config.py` deliberately does not carry it: a gate that must construct an order to run is the wrong instrument for a boot-time environment check. Revisit when broker-order code exists and can host the probe |
| D1.12 | **Reboot behaviour of `nix-xvfb.service` / `nix-ibgateway.service`** | ARC 011 | **still open, narrowed by ARC 012.** The cutover is done — both processes are systemd-owned (cgroup `/system.slice/nix-*.service`, API socket served by the unit's own MainPID) and `verify.py` is green. What remains unproven is only that systemd starts them **at boot**: `systemctl is-enabled` is a declaration, not evidence. A reboot was offered as a separate authorization in ARC 012 and declined (second IB Key tap). Discharge: reboot, then run `check_ibgateway_service` **before anyone touches the console** — a human logging in first creates the very state the check must observe independently |
| D1.13 | **No gate asserts the Stage 0 market-data path** | ARC 012, re-scoped ARC 013 | unassigned. **The subscription half of this debt is CLOSED** — ARC 013 settled it: Stage 0 runs on IBKR's free feed, no purchase (see `dev_and_services_plan.md`). What remains is a gate. ARC 013 measured the real path: **no real-time** (err 354, no grant callback), **delayed works** at a measured **10 min**, and a request for delayed-frozen (4) was **silently granted as delayed (3)**. So the owed gate is: assert the *granted* `marketDataType` is what Stage 0 declares, and FAIL on a silent downgrade — never infer the mode from the request. Build it with broker-datafeed, not before |
| D1.14 | **Bar immutability on a re-requestable feed** | ARC 012, split out ARC 013 | unassigned — blocked until broker-datafeed exists. Stage 0's feed is delayed **and** polled; polled history is re-requestable and can return revised values, so the bar builder needs its own seal-and-never-rewrite rule. Split from D1.13 because it discharges in a different arc, and it stays owed even after a real-time feed arrives at Tradovate |
| D1.15 | **No gate runs the seam simulation** | ARC 015 | **discharged ARC 016** — `scripts/tests/test_seam_simulate.py` gives the driver a collectable pytest entry point, so the project suite now carries all 33 assertions. The entry point lives under `scripts/tests/` rather than inside `seam_simulate.py`, because `testpaths` points at `scripts/tests/` and a `test_*` function added to `scripts/broker/` would have looked converted and been collected never. Both controls additionally driven verdict-by-verdict rather than inferred from a green aggregate (§7.7): Hollow returns 9 behavioural failures, the working Stub returns 0, and the await checker reports exactly one divergence naming `query_positions`. Can-fail demonstrated on all four |
| D1.17 | **One requested `disconnect()` emits TWO `on_session(DOWN)` events** | ARC 014 code, measured live ARC 016 | unassigned. Measured on clientId=905: a single `IBKRBrokerOrder.disconnect()` produces `(DOWN, "transport disconnected")` from `_on_ib_disconnected` — fired by ib_async's `disconnectedEvent` — and then `(DOWN, "requested")` from `disconnect()` itself. Acks are deduped through `_ack_once`; **session events are not deduped at all**. Benign if the Limiter treats DOWN as an idempotent state transition, a defect if it ever counts transitions, reconnect-attempts, or drives a state machine off the edge rather than the level. Note the two carry *different* reasons, so the provenance channel is intact and the fix is not simply "drop one" — §4 wants an unrequested drop distinguishable from a requested one. Not fixed in ARC 016: the arc explicitly forbade behaviour changes beyond §2a's entry point and §2b's comment. Discharge with the Limiter, which is the component that decides whether edge or level is the contract |
| D1.16 | **`state/encrypt_credentials.py` is real Python that no gate can see** | pre-existing, found ARC 016 | unassigned. Surfaced by ARC 016's untracked-file audit. `.gitignore` excludes `state/` wholesale — deliberately, and for a good reason (it holds the hardware UUID and credential JSON, and the exclusion is defense in depth beyond `*credentials*.json`) — but the directory also contains **executable credential-encryption code**, which is therefore untracked and outside `pre-commit run --all-files` for exactly the reason D3.2 records. This is failure mode #14 (`debug.md` §8) sitting in the tree today. Discharge: move the script out of `state/` to a tracked location, leaving only data behind; do **not** un-ignore `state/`. Not fixed in ARC 016 because the arc forbade new features and behaviour changes, and moving credential tooling is neither trivial nor in scope |

Discharged: `.venv` (`check_venv`), `python3` (`check_python_runtime`), node identity
(`check_node_identity`), `ib_async` pin (`check_python_deps`), IB Gateway API configuration
(`check_ibgateway_config`, ARC 010), Xvfb + IB Gateway boot persistence
(`check_ibgateway_service`, ARC 011).
| D1.18 | **The order-rejection ack carries an IBKR numeric error code across the seam** | ARC 014 code, found ARC 017 | unassigned. `_on_ib_error` calls `self._ack_once(cid, REJECTED, reason=f"{errorCode}: {errorString}")`, so a vendor integer reaches the seam inside `on_ack(reason)`. Invariant 2 says no IBKR code crosses the seam; ARC 017 enforced that on the **session** event (1100/1101/1102 removed from every session `reason` and moved to adapter-internal logging) but deliberately did **not** extend it to acks, because the parent scoped the change to the session path and because `on_ack(reason)` is the declared human-readable provenance channel where error 201's margin figure has real diagnostic value. So this is a genuine tension between invariant 2 and the provenance channel, not an oversight. Discharge alongside the Limiter, which is the first component that will actually consume an ack reason and can settle whether a structured rejection cause is owed the way `UP_DATA_LOSS` was owed for sessions. **Reported rather than substituting a decision** |

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
| D2.8 | B.7 | **discharged ARC 017** — `checks/check_derived_claims.py` + `checks/derived_claims.json`. Seven claims, each a set of **commands that compute a number at run time**; the registry stores **no integer anywhere**, because banking "16" beside the claim that §2A has 16 elements would rebuild the defect the instrument exists to catch. Every claim needs ≥2 sources and the gate is CANNOT-MEASURE (exit 2) if a claim has one source or two sources that are the same computation. Can-fail demonstrated three ways, each naming claim/stated/derived: a wrong series figure, a spec-vs-code drift firing two claims at once in both B.7 directions, and a missing file (**FAIL, not skip**). Its first live act was to correct this ledger's own series row — see the note above. **Known limit, stated beside the gate rather than papered over:** it proves every *registered* number is right and cannot prove the registry covers the numbers that matter (failure mode #14, inherent to a registry-driven instrument). The ARC 016 note below remains correct — D2.8 was never the item promoted to §7.12 | — |
| D2.9 | C.5 | the stdlib-only scan is textual, not proof-by-absence over the import closure | unassigned |
| D2.10 | C.6 | no verdict-by-verdict comparison harness | unassigned — nothing to compare yet |
| D2.11 | C.10 | no named owner for shared global measurements (tree-wide complexity, lint state) | unassigned |
| D2.12 | D.6 | `test_runner_coverage.py` proves every registered check is *reachable*, not that a registered gate which should fail actually reddens a real run end to end. **A suite that silently skips a gate reports GREEN** | unassigned |
| D2.13 | §7.12 / D.6 | **discharged ARC 018** — the `pytest-affected` entry is no longer bare `pytest --testmon`; it is a runtime-gate program that makes the state of `.testmondata` an input to the verdict and prints `SELECTED=` on every run. Zero selection is no longer terminal: it is named (`NOTHING-SELECTED`, `SCOPE-BLIND`, `SELECTOR-BROKEN`, all non-zero exits, exit 2 kept distinct from exit 1 per B.2) and then escalated to a non-incremental run so the commit is measured rather than waved through. Proven in order on this tree: **non-vacuity** (cold database → `collected 159 items`); **defect reproduced pre-fix** (warm, no change → `changed files: 0` / `collected 0 items` / `no tests ran` / hook **Passed** / exit 0); **fix under identical conditions** (hook **Failed**, exit code 2, `RUNTIME-GATE verdict: NOTHING-SELECTED`; with escalation on, `mode=full-escalated(zero-selection) SELECTED=159 MEASURED-PASS` in 11.6 s); **D3.4's selection proof re-run intact** (plant `assert 1 == 2` → `collected 9 items`, neither 0 nor the whole suite, `FAILED …test_arc018_plant_testmon` naming `scripts/tests/test_check_venv.py:214`, exit 1 → restored to sha256 `fd5d4992…877b5` → `collected 8 items`, pass). `__pycache__` purged between every step. **Two findings came out of building it, and both are worse than the row as written.** (i) A tracked source file can change and select **nothing**: `scripts/nixverify/__init__.py` is in scope for every other hook and has **no fingerprint at all** in testmon's graph, so appending a line to it produced `changed files: 0` / `collected 0 items` / exit 0 — the old gate was green over a real, staged, tracked change. (ii) testmon does not notice its own corrupted record: overwriting one `file_fp.fsha` with zeroes still produced `changed files: 0` / `collected 0 items` / exit 0. The new gate catches both, the second by recomputing the git-blob hashes testmon stores rather than by asking testmon what changed. **Residual, stated rather than discovered later:** `.testmondata` is still untracked and still per-machine — tracking it was rejected (binary SQLite plus WAL sidecars is a second source of truth that goes stale on write; ARC 016 rejected the same shape for `downloads/*.py`), so what changed is that its state is now visible and load-bearing, not that it became reviewable. See **D2.16** for the debt this repair itself opened | — |
| D2.14 | §2.1 / B.4 | **A hand-rolled retry loop on the order path is banned and undetected.** `checks/check_order_path_bans.py` (ARC 017) proves *no retry **library*** (`tenacity`/`backoff`/`retrying`) and *no loop-blocking **call***; it does **not** prove nothing retries. `for _ in range(3): self.place_order(...)` passes both arms. §2.1 exists because a retry on the order path turns one intended order into two, and that is a semantic property, not an import. A PASS from that gate must be read as exactly what it measures — the gate's own docstring says so under §7.12 condition 6, and this row is the ledger half of that admission. Discharge needs a semantic instrument (call-graph reachability from `place_order` back to itself, or an AST loop-containing-a-send analysis), which is a different and harder gate | unassigned |
| D2.16 | C.10 / §7.12 / #14 | **The runtime gate's own program is outside every gate.** Opened by ARC 018's own repair, stated rather than left to be found. The `pytest-affected` verdict logic — database audit, independent hash recomputation, verdict taxonomy, escalation — is a Python program living inside the `entry:` string of `.pre-commit-config.yaml`. `ruff`, `pylint`, `mypy`, `bandit` and `complexipy` all see a YAML file; none of them see that Python, and no pytest test drives it. So the instrument that decides whether the runtime was measured is the one artifact in the tree with no static check and no test over it, which is failure mode #14 aimed at the gate itself. It is there because ARC 018 scoped sub-agent A's writes to `.pre-commit-config.yaml`, `pyproject.toml`, `scratch/**` and this ledger — `scripts/` was forbidden, and a gate that must exist somewhere ends up wherever it is allowed. Discharge: lift the program verbatim into a tracked `scripts/runtime_gate.py`, point `entry:` at it, and give it tests — at which point every hook covers it and the §7.12 answer 7 in the config header can be deleted rather than reworded | unassigned — discharges in whichever arc may write under `scripts/` |
| D2.15 | C.10 / §7.4 | **`check_order_path_bans` scans one directory, and nothing guards that the order path still lives there.** Scope derives at run time from `ORDER_PATH_DIRS = ("scripts/broker",)` via `rglob`, so a *new file* under `scripts/broker/` is covered automatically — the moving-value trap the gate was written to avoid. But a new *home* is not: an adapter added at `scripts/risk/` or `scripts/limiter/` is silently outside the scan while both required members remain present and non-vacuity still passes, so the gate stays green having never looked. §7.12 condition 4 beside the gate, unguarded and named there. This is the same shape as D2.11 (no owner for shared global measurements) but concrete. Discharge with whichever arc first puts order-path code outside `scripts/broker/`, which is also the moment it becomes discoverable | unassigned |

### Promoted to doctrine — ARC 016

The recurring failure class **"a green light that measured nothing"** was promoted out of this ledger
into `debug.md` **§7.12** (doctrine v1.2.0), as a standing question required of every new gate —
***what would have to be true for this to pass while measuring nothing?*** — answered **in writing, at
the point the gate is built**. Failure mode **#14** (*scope set by an external mutable list*) was added
to the §8 catalogue. The seven-instance evidence base is tabulated in §7.12 and is not restated here.

> **Citation correction.** The ARC 016 brief directed this promotion at debt item **D2.8**. D2.8 is
> doctrine **B.7** — *no harness parses a constant out of a document and asserts the code equals it* —
> which is the **derive-never-restate** class, not the vacuous-pass class, and it remains **open and
> unassigned**. Nothing about it was discharged by the promotion. The items in this ledger that
> actually carry the promoted class are **D1.10** (each hook actually capable of failing), **D2.7**
> (nothing baselined on a pristine tree — bandit scanning nothing is its measured instance), **D2.12**
> (a suite that silently skips a gate reports GREEN) and the whole of **D3**, whose header states the
> principle outright. Those are the items §7.12 now stands over.
>
> Recorded rather than silently redirected, because a pointer that reads as authoritative while
> naming the wrong target is a **stale literal anchor** — `debug.md` §7.4, and the same class the
> ledger's own miscounted series row (instance #2 in §7.12) belongs to. Left uncorrected it would
> have produced a future arc "discharging D2.8" by writing a doctrine section that has nothing to do
> with parsing constants out of documents.

## D3 — Instruments whose can-fail has never been demonstrated

Doctrine C.2: a gate is guilty until shown able to say no.

| # | instrument | status | owner |
|---|---|---|---|
| D3.1 | `bandit (production)` — the hook with `exclude: ^(databases/schema/\|scripts/tests/)` | **discharged ARC 010, for this hook only.** Was scanning nothing (exit 0 over 27 skipped files) since ARC 006; repaired to 1.9.4 and proven to fail on a planted `shell=True` and name the site. **Scope correction, ARC 017:** the entry read `bandit` unqualified, but ARC 010 split bandit into **two** hook entries in the same arc, and the ARC 010 plant landed in `checks/check_venv.py` — a path the second entry's `files: ^scripts/tests/` **excludes**. So one discharge was recorded against two instruments and the second was never demonstrated. It is now **D3.6**, opened and discharged ARC 017. This is the ledger overstating its own coverage for the third time, and it is why B.7's *derive, never restate* applies to coverage claims and not only to numbers | — |
| D3.2 | `ruff`, `pylint`, `mypy`, `complexipy` | **discharged ARC 015** — all four were observed failing on real code in this repo, not on a contrived plant. Bringing `scripts/broker/` into the gate's file list surfaced: ruff BLE001/RUF059 (11 findings), pylint 229 findings across 20 codes, mypy 7 type errors in 3 files, and complexipy on two drivers over the 15 ceiling (37 and 25). Each named its file and line; each went green only after the code changed. **Note what this also measured:** those files had been in the tree since ARC 014 and were passing `pre-commit run --all-files` — because they are UNTRACKED, and `--all-files` means all *git-tracked* files. A gate whose scope is set by what has been `git add`ed can be silenced by not adding | — |
| D3.3 | `check_await_conformance` | **discharged ARC 015** — planted one plausible divergence in the real IBKR adapter (`query_positions` served from the mirror with `async` dropped, which compiles and passes structural conformance), confirmed the checker reported exactly `['query_positions: port declares async, adapter is sync']`, then removed the plant and confirmed the file byte-identical. The plant is also kept permanently as `AwaitDivergentBrokerOrder` so the demonstration does not have to be taken on trust | — |
| D3.4 | `pytest --testmon` (hook `pytest-affected`, "Stage 3 — runtime pass") | **discharged ARC 017.** Plant: `assert 1 == 2` appended to `scripts/tests/test_check_venv.py`, driven **through the hook**, not bare pytest. Selection proven rather than assumed — testmon reported `changed files: scripts/tests/test_check_venv.py, unchanged files: 35` and `collected 9 items`, i.e. neither 0 (skipped) nor 159 (swept), and the planted test was among the 9: `FAILED …::test_arc017_plant_testmon` naming `scripts/tests/test_check_venv.py:214`, hook exit 1. Restored to sha256 `fd5d4992…877b5`, control re-ran 8 selected tests green. **The can-fail is discharged; the vacuity hole it exposed is not — see D2.13** | — |
| D3.5 | `ruff-format` | **discharged ARC 018** — `args: [--check]` adopted, which converts the hook from a repairer into a reporter and closes every one of the three consequences below. FAIL-with-CONTROL run inside the hook's own scope, `__pycache__` purged between steps: **CONTROL** `Passed`, self-reporting its scope as `39 files already formatted` (non-vacuity, and 39 is what pre-commit's own Classifier selects for this hook); **PLANT** a misformatted function appended to `scripts/tests/test_check_venv.py`, sha256 `fd5d4992…877b5` → `b75177e0…916b`; **CAN-FAIL** `Failed`, exit 1, `unformatted: File would be reformatted` naming `--> scripts/tests/test_check_venv.py:1:1` and printing a diff whose gutter carries the real offending lines 211–214; **sha256 after the hook ran is `b75177e0…916b`, unchanged — it reported and did not repair**; run a **second time over the same defect it still fails**, so failure mode #7 is closed; **RESTORE** back to `fd5d4992…877b5` and **CONTROL** `Passed`, `39 files already formatted`. Honest residual: the header coordinate is the nominal `:1:1` rather than the first bad line, so the *file* is named exactly and the *lines* are named in the diff body, not in the location. **The ergonomic cost is accepted, not hidden:** commits are no longer auto-formatted and a developer must run `.venv/bin/ruff format <file>` themselves. That is the intended trade — doctrine C.2 wants a gate that says no, and a hook that silently rewrites the tree destroys the evidence that it fired. `ruff-check` keeps `--fix`; nothing was relaxed anywhere to pay for this | — |
| D3.6 | `bandit (tests)` — the hook aliased `bandit-tests`, `files: ^scripts/tests/` | **opened and discharged ARC 017.** Split out of D3.1, which had claimed its coverage since ARC 010. Plant landed **inside this hook's own scope** — `subprocess.run(cmd, shell=True)` appended to `scripts/tests/test_systemd_units.py`, chosen precisely because `checks/` (where the ARC 010 plant went) is outside `^scripts/tests/`. **CAUGHT**, naming the site: `[B602:subprocess_popen_with_shell_equals_true]`, Severity High / Confidence High, `Location: ./scripts/tests/test_systemd_units.py:77:4`, with the offending line printed. Restored byte-identical, sha256 `85d2b8d0…bee9a` before and after; control re-passed. Non-vacuity asserted first: bandit's own JSON metrics report **19 files / 3109 LOC / 0 errors** for this hook, against pre-commit's Classifier selecting exactly 19 | — |
