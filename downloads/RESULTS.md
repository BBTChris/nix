# RESULTS — ARC 010: VERIFY-AND-CHECKS reconciliation, bandit repair, ARC 008 Parts 1/3/5

**Status: ARC 010 complete.** Every success box checked. ARC 011 follows in the same session and
appends its own section below this one.

---

## Definition of success

| Box | State |
|---|---|
| Real VERIFY-AND-CHECKS.md in `~/nix/docs/`; diffed; every semantic divergence reported with a verdict; decisions re-examined | ✅ |
| CLAUDE.md spec table corrected | ✅ |
| bandit repaired and **proven capable of failing** via planted defect + control | ✅ |
| Real API config extracted from `jts.ini` and reported; mismatches flagged | ✅ — **and the arc's premise about `jts.ini` was wrong; see 3a** |
| Live connect clientId=905; entitlement status determined; clean disconnect | ✅ — **Err 10189 confirmed** |
| `check_ibgateway_config.py` built against the real spec, registered, full FAIL-with-CONTROL cycle | ✅ |
| `origin/main` and branch state re-verified fresh | ✅ |

---

## Part 1 — VERIFY-AND-CHECKS.md reconciliation

### 1.0 The headline finding: these are not two versions of one document

The real `VERIFY-AND-CHECKS.md` is **an external doctrine document about a different project's
verification machinery** — its paths are `~/luna/checks/`, `~/luna/docs/CHECK-DEBT.md`, and its
enforcement point is a `bank.sh` Nix does not have. My v1.0.1 was a Nix provisioning-engine
specification. They overlap on principles and share almost nothing else. A line-by-line diff would
be meaningless; the useful comparison is rule-by-rule, which is what follows.

**Actions taken:**

- Real doc → `docs/VERIFY-AND-CHECKS.md` (authoritative location, as instructed).
- My v1.0.1 → renamed `docs/nix_check_contract.md`, **demoted from "authority" to derived
  implementation spec**, bumped to v1.1.0. It could not simply be deleted: every `checks/*.py` and
  `scripts/nixverify/*` module cites its section numbers, and it is the only written definition of
  Nix's engine. 26 live references repointed; historical records (`sessions/`, `downloads/`,
  `CLAUDE-CHANGELOG.md`, banked arc copies) deliberately left untouched per CLAUDE.md directive 6.
- New `docs/nix_check_contract.md` **§15 is the full conformance map** — the durable artifact of
  this reconciliation, not just this report.
- `docs/CHECK-DEBT.md` created — the real doc's A.4 mandates that ledger and it did not exist.

### 1.1 Re-examination of the four decisions the arc named

**Five-state results — my addition, beyond the real doc.** The real doc specifies only a
three-value *exit-code* contract (B.2: `0` PASS / `1` FAIL / `2` CANNOT MEASURE) and no `Status`
type at all. `FAIL_REPAIRABLE` / `FAIL_NEEDS_OPERATOR` / `SKIPPED` are mine. **Retained**, because
§4.2 maps all five onto exactly `0`/`1`/`2` — B.2 is preserved, not replaced — and because Nix's
checks converge (real doc A.1), so `--correct` needs a way to say "I must not repair this" that
the doctrine gives no vocabulary for. Verdict: **addition, compatible, retained.**

**"Disruptive gates the repair, not the inspection" — the framing was wrong and is withdrawn.**
The real document **has no §8**. It has Parts A–D and says nothing whatsoever about disruptive
actions, privilege separation, or maintenance windows. My handoff's "I amended §8 to match" was
describing an amendment to *my own* document while implying it aligned me with the real one. The
claim is retracted in `nix_check_contract.md` §15.2. The **rule itself is retained** as a stated
Nix addition: a boot can occur mid-session, so a repair that restarts a service must not fire
there while the drift report still must. That reasoning is consistent with the real A.2's
read-only-by-default logic, extended to a second axis. Verdict: **diverges (no counterpart) —
flagged, framing corrected, rule kept with stated reasoning.**

**Non-vacuity enforced mechanically — matches and strengthens.** Real C.2 requires a gate to
"name the site"; my §5 makes `site` mandatory for any `FAIL_*` and `evidence` mandatory for any
`PASS`, rejected by the engine rather than trusted to the author. That is C.2 enforced rather than
documented. **But I had missed half of C.3**: its actual requirement is that *the gate's scope
contains its subject* — a different property from "evidence is non-empty", and the one that
catches a scanner structurally unable to see the file it was written about. Added as §5.3.
Verdict: **matches + strengthened, with a real gap found and closed.**

**Three runners instead of two — my addition.** The real doc is silent on runners. Retained; the
reasoning (a `user`-privilege `DISRUPTIVE` check was reachable by no runner at all, so pin drift on
the order-placing library was detected every boot and repaired never) stands on its own.
Verdict: **addition, compatible, retained.**

### 1.2 Verdict per major component

| Component | Verdict |
|---|---|
| Exit-code contract `0`/`1`/`2` incl. exit 2 | **matches** |
| `CANNOT_MEASURE` never collapsing into failure | **matches** (real doc B.2's own rationale) |
| Prove effective state, never a proxy | **matches** (C.1) |
| FAIL-with-CONTROL + naming the site | **matches** (C.2) |
| Never anchor to a moving value | **matches** (C.4) |
| `verify` read-only by default | **matches** — verified: `scripts/verify.py:50` defaults `--mode` to `verify` |
| Owed-check ledger location | **diverges → corrected** — `docs/CHECK-DEBT.md` created (A.4) |
| `registry.json` as the single source of what is registered | **diverges → corrected** — `checks/verify_manifest.json` renamed `checks/registry.json` (A.4/D.5); 8 files repointed, 126 tests still green |
| Check coverage = build gate | **diverges → corrected** — A.7 is explicit that it is a *ledger obligation*, and warns against a "fully drained" gate against a series that rose 95→190 over seventeen arcs and never fell. §1 restated |
| B.4 (close a RED by a stricter gate or fixed code, never by exempting) | **diverges → corrected** — absent from v1.0.1, added as §5.2. It directly governed this arc's bandit decisions |
| C.8 (a plant never touches a production artifact) | **diverges → corrected** — added as §5.4 |
| C.9 (extend an instrument, never build a second) | **diverges → corrected** — added as §5.5 |
| Five-state `Status` | **addition beyond the doc — flagged, retained** |
| `DISRUPTIVE` / `PRIVILEGE` / `INTERACTIVE` metadata, three runners | **addition beyond the doc — flagged, retained** |
| A.3 `status` view · A.5 layout-as-check · A.6 release/update gating · B.3 known-red markers · B.6 `prove_*` + baselining · B.7 spec-parsing harness · C.5 import-closure absence · C.6 verdict-by-verdict · C.10 measurement ownership · D.6 suite self-can-fail | **diverges → owed**, all 12 recorded in `CHECK-DEBT.md` §D2 |

### 1.3 Where the real doc does *not* win, stated explicitly

Only one class, and it is an inventory question rather than a rule question. The real document
opens by measuring that **`verify.py`, `registry.json`, `strategy.py`, `bump_version.py` and
`risk_engine` are all absent and `checks/` holds only `.gitkeep`.** That is a measurement of
**`~/luna/`**. On this tree, measured today: `scripts/verify.py` runs, `checks/registry.json` is
loaded by it, five checks pass against real machine state, and 140 tests exercise them.

The rule that warning carries — *"this file names desired state, never inventory; the tree is the
authority on what exists"* — **is inherited and binding**. Its inventory is not. This is CLAUDE.md's
mission clause (inherit lessons, never unverified behavioural assumptions) and core directive 5
(verified on-disk state outranks documentation) doing exactly the work they exist for. Recorded in
`nix_check_contract.md` §15.4 along with the other four non-transferable statements (`bank.sh`,
Part A's "not built", B.5's nine Luna gates, A.7's Luna debt series).

---

## Part 2 — bandit repair

### 2.1 The defect, measured precisely

The arc's diagnosis was right; one detail differs and it matters for how the failure hid:

```
File "bandit/core/node_visitor.py", line 171, in visit_Str
    self.context["str"] = node.s
AttributeError: 'Constant' object has no attribute 's'
```

Python 3.14 removed the `.s` alias from `ast.Constant`. **Any file containing a string literal**
therefore aborts mid-parse. Bandit catches that per file, records *"exception while scanning
file"*, and **exits 0**.

Repo-wide, before the fix:

```
Files skipped (27):
	./checks/_preamble.py (exception while scanning file)
	./checks/check_node_identity.py (exception while scanning file)
	...   [all 27]
	Total issues (by severity):  Undefined: 0  Low: 0  Medium: 0  High: 0
repo-wide exit=0
```

**27 of 27 files skipped, zero lines scanned, green.** Since ARC 006.

### 2.2 Repair

bandit `1.8.6` → **`1.9.4`** in `.pre-commit-config.yaml`. Split into two hook entries so the
strict rule set stays whole over production code, with a scoped `--skip B101,B404,B603` for
`scripts/tests/` only — three *rules* narrowed over the test tree with a measured reason each,
never a *scope* exemption (`nix_check_contract.md` §5.2 / doctrine B.4). One targeted
`# nosec B105` on `Status.PASS = "pass"` in `contract.py`, which is an enum value and not a
credential.

### 2.3 §5.1 discipline applied to the gate itself — verbatim

**Step 1 — PASS:**
```
bandit (production)......................................................Passed
bandit (tests)...........................................................Passed
```

**Step 2 — NON-VACUITY.** The critical step: "Passed" was exactly the old vacuous state.
```
production:  Total lines of code: 1003     Files skipped (0):
tests:       Total lines of code: 1664     Files skipped (0):
```
2667 lines actually scanned, zero files skipped — against 0 and 27 before.

**Step 3 — PLANT** into a real production file, `checks/check_venv.py` (git-tracked, reversible;
§5.4 forbids planting into anything that is not):
```python
def _arc010_planted_defect(cmd):
    """PLANTED DEFECT (ARC 010 bandit can-fail proof). Removed immediately."""
    return subprocess.run(cmd, shell=True, check=False)
```

**Step 4 — FAIL, naming the site:**
```
bandit (production)......................................................Failed
- exit code: 1
>> Issue: [B602:subprocess_popen_with_shell_equals_true] subprocess call with shell=True identified, security issue.
   Severity: High   Confidence: High
   Location: ./checks/check_venv.py:204:11
203	    """PLANTED DEFECT (ARC 010 bandit can-fail proof). Removed immediately."""
204	    return subprocess.run(cmd, shell=True, check=False)
```

**CONTRAST — the old version on the identical planted file:**
```
	No issues identified.
Files skipped (1):
	./checks/check_venv.py (exception while scanning file)
1.8.6 exit=0  <-- green on a planted shell=True
```

**Step 5 — UNPLANT:** `sha256` before `792d2d1e…4227`, after `792d2d1e…4227`; `git diff` empty.

**Step 6 — CONTROL:** `Passed`, `Files skipped (0)`, `Total lines of code: 1003` — the original
verdict reproduces, so the failure was caused by the plant and not by ambient conditions.

### 2.4 Method note

My first bait file was self-suppressing: the comment `# nosec-free: should be flagged B602` was
parsed by bandit as a `nosec` directive, and "B602" among the trailing words is a valid test id, so
the bait silenced the very rule it was testing. It was caught by `Total potential issues skipped
due to specifically being disabled: 1` in the output. **The instrument used to test the instrument
was itself defective** — the real doc's Part C opener ("roughly one defect in three in this project
was found inside the instrument doing the measuring") earning its place immediately.

---

## Part 3a — Real API config from `jts.ini`

### The arc's premise is incorrect, and this changes Part 3c

**`~/Jts/jts.ini` does not contain the socket port, `ReadOnlyApi`, or the localhost-only flag.**
Its complete plaintext content is 20 keys; the API settings are not among them. This Gateway build
(10.45, `s3store=true`) keeps them in an **`IBGZENC`-encrypted** settings store —
`~/Jts/<userdir>/ibgateway.*.ibgzenc` and `ibg.tmp.xml`, both with the `IBGZENC` magic. A
whole-`~/Jts`/`~/ibgateway` grep for `ReadOnlyApi|SocketPort|AllowLocalhostOnly|LocalServerPort`
returns exactly one file: `jts.ini`, and only for `LocalServerPort`.

**A trap worth naming:** `jts.ini` `[IBGateway] LocalServerPort=4000` is **not** the API port — it
is the SSL tunnel to `ndc1.ibllc.com`. A check that "reads the expected port from `jts.ini`" as the
arc instructed would read **4000** and be confidently wrong.

### The six expected values, each against how it was actually established

| # | Expected | Measured | How | Verdict |
|---|---|---|---|---|
| 1 | Socket port **4002** | 4002 answers the IB v100+ handshake, `serverVersion=187` | live socket handshake — **not** in `jts.ini` | ✅ match |
| 2 | **Read Only API — unchecked** | **OFF** | `whatIf` order reached IBKR's margin engine (`Error 201: NET LIQ [20336.82] MUST EXCEED MARGIN REQ [35067.37]`) instead of being refused. A read-only API rejects before margin evaluation | ✅ match |
| 3 | **Trusted IPs `127.0.0.1`** | `TrustedIPs=127.0.0.1` | `jts.ini` `[IBGateway]` — plaintext | ✅ match |
| 4 | **localhost only — checked** | **enforced** | listener binds `*:4002`, but connections sourced from `192.168.1.25` and `100.109.241.65` are accepted at TCP then **closed without answering the prologue**. Enforcement is app-layer, not bind-layer | ✅ match |
| 5 | **Lock and Exit — auto restart at 03:00** | `AutoRestart=1` present | `jts.ini` `[u:diieodccik…]` | ⚠️ **partial** — auto-restart is *enabled*; the **03:00 time is not in plaintext** and could not be verified |
| 6 | paper account **DUR250018** | `managedAccounts: ['DUR250018']`, `tradingMode=p` | live API + `jts.ini` | ✅ match |

**No mismatch against the human's report.** The only gap is #5's time-of-day, which is
unverifiable from outside the encrypted store, and it is reported as unverified rather than
assumed.

Also on disk and worth recording: `ApiOnly=true`, `UseSSL=true`, `WriteDebug=false`,
`TimeZone=Etc/UTC`.

---

## Part 3b — Live connection and market-data entitlement

Connected on **clientId=905** (never 0 — implicitly adopts manually-placed TWS orders; never 1 —
reserved for the future Risk Engine).

```
connected            : True
serverVersion        : 178
connectionTime       : 2026-08-10 09:39:54+00:00
managedAccounts      : ['DUR250018']
  DUR250018    AccountType        INDIVIDUAL
  DUR250018    NetLiquidation     20344.34 USD
```

**Entitlement — Err 10189 confirmed:**
```
Error 10189, reqId 4: Failed to request tick-by-tick data.
  No market data permissions for CME FUT, contract: ESU6 (conId=649180671, expiry 20260918)
  --> Err 10189 seen : True     ticks received: 0
```

**Fallback works:**
```
reqHistoricalTicks -> 20 ticks returned
  HistoricalTickLast(time=2026-08-10 09:29:30+00:00, price=7792.5, size=1.0)
  HistoricalTickLast(time=2026-08-10 09:29:30+00:00, price=7792.5, size=3.0)
```

**Clean disconnect:** `connected after disconnect: False`, on every one of the three probe runs.

**This reproduces the predecessor's outcome exactly.** No true tick stream is available on this
account; polled `reqHistoricalTicks` is the only path. The consequence for the broker-datafeed spec
is the one already on record: **bar immutability becomes a design obligation Nix must enforce
itself, not a property inherited from the feed.** Polled history is re-requestable and can return
revised values, so the bar builder needs its own seal-and-never-rewrite rule.

**Incidental finding worth keeping:** the paper account cannot afford one ES contract — margin
requirement 35,067.37 USD against net liq 20,344.34 USD. Any sizing or paper-trading work on ES
will hit this immediately.

---

## Part 3c — `checks/check_ibgateway_config.py`

Built against the real doctrine. Registered in `checks/registry.json` under `trading-stack`.

**Proves effective state (C.1).** Completes the real IB v100+ wire handshake in **stdlib
`socket`** — 20 lines, no `ib_async` — and reads back the negotiated server version. Stdlib-only
matters: §9.1/§9.4 require a check to run under `/usr/bin/python3` before `.venv` exists and to
never import its subject. "`jts.ini` exists" and "the JVM is alive" are both true of a Gateway
sitting on its login screen with no API listener; only the handshake distinguishes them.

**Anchoring — a stated deviation from the arc's instruction.** The arc said *"read the expected
port from `jts.ini` at check time; don't hardcode 4002."* The port is not in `jts.ini` (3a), so
that is impossible, and the nearest thing there — `LocalServerPort=4000` — is the wrong port. The
expected values instead live in **`checks/ibgateway_expected.json`**, a single-source declared-state
file the check derives everything from; a test asserts the literal `4002` appears nowhere in the
check's source. This satisfies what C.4 actually forbids (an assertion pinned to a moving value
baked into code) and matches A.1's "a check declares a desired state and assesses reality against
it" better than parsing the subject for its own expectations would.

**Exit contract, as demonstrated below:** PASS connected + conformant · FAIL_NEEDS_OPERATOR
connected + misconfigured (never `FAIL_REPAIRABLE` — Gateway settings are changed by a human at a
VNC console, so the engine must not claim it can repair them) · CANNOT_MEASURE unreachable, *or*
TCP-open-but-not-the-IB-protocol.

**Does not overlap `check_ibgateway_service.py`** (ARC 011): this gate owns API *configuration*,
that one owns *service persistence*. Boundary stated in both docstrings per §5.5 / C.9.

### FAIL-with-CONTROL — verbatim

**Step 1 — PASS:**
```
pass: IB API handshake on 127.0.0.1:4002 -> serverVersion=187; jts.ini sections=['Communication',
'IBGateway', 'Logon', 'u:diieodccikbcjmmgamiaegaiifoabmijoabjdfoh']; localhost-only probe:
192.168.1.25 refused (no-reply: peer closed before replying to the prologue)
exit=0
```

**Step 2 — NON-VACUITY, before any plant.** Two independent confirmations that the gate's scope
contains its subject:
```
-- the gate's own scope assertion --
scripts/tests/test_check_ibgateway_config.py::test_run_actually_attempts_a_live_connection  1 passed
-- independent: strace the real run --
connect(3, {sin_port=htons(4002), sin_addr=inet_addr("127.0.0.1")}, 16) = -1 EINPROGRESS
connect(3, {sin_port=htons(4002), sin_addr=inet_addr("192.168.1.25")}, 16) = -1 EINPROGRESS
```

**Step 3/4 — PLANT A (declared-vs-actual drift) → FAIL naming the site:**
```
planted: trusted_ips -> ['10.0.0.9']

fail_needs_operator: IB API handshake on 127.0.0.1:4002 -> serverVersion=187; ...
  site: jts.ini:[IBGateway]TrustedIPs
  detail: jts.ini:[IBGateway]TrustedIPs: ['127.0.0.1'] (declared ['10.0.0.9'])
exit=1

--- and through verify.py, the real runner ---
  [FAIL] check_ibgateway_config jts.ini:[IBGateway]TrustedIPs - ...
  4 passed | 1 failed | 0 cannot measure | 0 skipped          exit 1
```

**PLANT B — the discrimination the arc asked for: unreachable must not collapse into FAIL:**
```
planted: api_port -> 4003 (nothing listening there)
cannot_measure: no API endpoint at 127.0.0.1:4003 — ConnectionRefusedError: [Errno 111] Connection
refused. Gateway down or not logged in; that is not a misconfiguration (§4.1)
exit=2  <-- 2 = CANNOT MEASURE, not 1
```

**Step 5 — UNPLANT:** restored byte-identical.

**Step 6 — CONTROL:**
```
pass: IB API handshake on 127.0.0.1:4002 -> serverVersion=187; ... exit=0
  5 passed | 0 failed | 0 cannot measure | 0 skipped          exit 0
```

**Plant hygiene (C.8/§5.4):** every plant was into a git-tracked Nix artifact. `~/Jts/jts.ini` was
never written — `sha256 64165609…a7e7` identical before and after the entire cycle — and the
authenticated Gateway session survived intact (`LISTEN *:4002 pid=236482` still held), so no 2FA
re-login was spent.

**Tests:** 14 new, covering non-vacuity, the unreachable/misconfigured split, site-naming on both
defect classes, and the `jts.ini` parse (`configparser` is deliberately not used: the first section
header is `[u:<hash>]` and values contain `:` and `;`, which its default delimiters mangle).
Suite: **126 → 140, all green.** All eight pre-commit hooks pass.

---

## Part 4 — Branch and merge state, re-verified fresh

`git fetch origin` then measured:

```
origin/main:  47ea580 Merge pull request #8 from BBTChris/arc-006-provisioning-v2
              a758d5f ARC 007: doc-conversion corruption audit ...
```

- **PR #8 is merged.** Merge commit `47ea580` is present on `origin/main`. The prior handoff
  claiming it was still open was stale, as the arc said.
- **`arc-009-verify-v2`: 55 ahead, 1 behind `origin/main`.** The single commit behind *is* the
  merge commit `47ea580`; `git log origin/main ^HEAD` returns only it, so the branch already
  contains all of main's content and there is **no conflict to resolve**.
- **A rebase is not required.** The branch is mergeable as-is; `git merge origin/main` would be a
  trivial no-content merge. Left undone deliberately — no push or merge was attempted this arc.
- Other local branches (`arc-006-provisioning-v2`, `arc-006-writeback`, seven `docs/*`) are all
  merged or stale; none block.

**No git action was refused by the permission classifier this arc** — nothing beyond `fetch` was
attempted.

---

## Owed work recorded, not silently dropped

`docs/CHECK-DEBT.md` opened with **22 debts**: 11 environment changes with no check (Postgres,
schema, slice pinning, sealed credentials, `unattended-upgrades`, the running-system view of the
systemd units, …), 12 doctrine rules Nix does not yet satisfy, and the other five commit-gate
hooks whose can-fail has never been demonstrated — bandit was the one that turned out to be
scanning nothing, and `ruff`/`pylint`/`mypy`/`complexipy`/`pytest` have had no equivalent proof.

**D1.11 deserves attention:** `ReadOnlyApi` has no check and deliberately gets none from this gate.
The setting is not in plaintext and the API exposes no read-only flag, so the only probe I could
find is order-shaped (send a `whatIf`, see whether it reaches margin evaluation). A gate that must
construct an order to run is the wrong instrument for a boot-time environment check. It should be
revisited when broker-order code exists and can host the probe.

---

## Files changed

**New:** `docs/VERIFY-AND-CHECKS.md` (the real doctrine) · `docs/CHECK-DEBT.md` ·
`checks/check_ibgateway_config.py` · `checks/ibgateway_expected.json` ·
`scripts/tests/test_check_ibgateway_config.py`

**Renamed:** `docs/VERIFY-AND-CHECKS.md`→`docs/nix_check_contract.md` ·
`checks/verify_manifest.json`→`checks/registry.json`

**Modified:** `CLAUDE.md` (spec table: doctrine added above the derived spec, ledger added,
correction note) · `.pre-commit-config.yaml` (bandit 1.8.6→1.9.4, split hooks) ·
`scripts/nixverify/contract.py` · `scripts/verify.py` · `install.sh` · `checks/*.py`,
`checks/pinned_deps.json`, `scripts/tests/*` (reference repointing) · `docs/elements_v2.md`
