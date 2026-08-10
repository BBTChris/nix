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
loaded by it, five checks pass against real machine state, and 142 tests exercise them.

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
Suite: **126 → 142, all green.** All eight pre-commit hooks pass.

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

---
---

# ARC 011 — Xvfb + IB Gateway boot persistence (systemd units + check gate)

**Status: 6 of 7 success boxes complete. One box is deliberately NOT performed** — the live
cutover, because it costs an authenticated Gateway session and a manual IB Key 2FA tap. That was
put to the human as an explicit choice and the answer was: do not cut over, report it plainly.
Nothing below implies boot behaviour was verified.

## Definition of success

| Box | State |
|---|---|
| `nix-xvfb.service` written, enabled, started, display confirmed answering live | ⚠️ **written + enabled + invocation and restart policy proven on a scratch display; NOT started on `:99`** |
| `nix-ibgateway.service` written with a real dependency, enabled, started, socket reachable | ⚠️ **written + enabled; NOT started** (socket *is* reachable — via the manual process, not the unit) |
| Slice-membership decision made and reasoned for both units | ✅ |
| Restart policy demonstrated (kill, confirm it returns) | ⚠️ **demonstrated for the Xvfb unit's exact `ExecStart` on a scratch display; not for Gateway** |
| Reboot test performed with authorization, **or** explicitly reported as not performed | ✅ — **NOT PERFORMED**, stated plainly |
| `check_ibgateway_service.py` built against the real spec, registered, non-overlapping, full FAIL-with-CONTROL | ✅ |
| `dev_and_services_plan.md` updated, incl. boot persistence ≠ unattended auth | ✅ |

---

## What was not done, and why

Xvfb and IB Gateway are running **right now** as manually-started foreground processes, and the
Gateway holds an authenticated paper session. `systemctl start` on either unit requires systemd to
take over from those processes, which means killing them. Killing the JVM drops the session:
Gateway comes back on its login screen and stays there — API socket down, both gateway checks
reporting FAIL — until a human logs in over VNC and approves IB Key on their phone.

That is the identical cost the arc attaches to a reboot. It was raised as an explicit decision
rather than absorbed silently; the human chose not to cut over now. So:

- **`systemctl is-enabled` says `enabled` for both units.** That is a *declaration* that they will
  start at boot. It is **not** evidence that they do. Recorded as **CHECK-DEBT D1.12**, discharged
  by rebooting under human authorization and re-running `check_ibgateway_service` *before* anyone
  touches the console.
- **No reboot was performed.** Boot behaviour is unverified.

---

## Part 1 — `nix-xvfb.service`

Invocation derived from the live process, not from the arc's transcription:

```
$ tr '\0' '\n' < /proc/236457/cmdline
Xvfb
:99
-screen
0
1440x900x24
```

```ini
[Service]
Type=simple
User=bbt
ExecStart=/usr/bin/Xvfb :99 -screen 0 1440x900x24
Restart=always
RestartSec=2
```

`Restart=always`, not `on-failure`: a display server has no legitimate "finished" state, so a
clean exit is as much a fault as a crash.

### Proven, without touching `:99`

The unit's `ExecStart` was read back **out of the installed unit** (never retyped) and run as a
transient unit on a scratch display with the same `Service` block:

```
installed  : /usr/bin/Xvfb :99 -screen 0 1440x900x24
scratch    : /usr/bin/Xvfb :98 -screen 0 1440x900x24

$ xdpyinfo -display :98
name of display:    :98
  dimensions:    1440x900 pixels (366x229 millimeters)

MainPID before kill: 257478
$ systemctl kill -s KILL arc011-xvfb-scratch.service
MainPID after kill : 257521   active=active
NRestarts          : 1
  dimensions:    1440x900 pixels (366x229 millimeters)
  -> display served again after the kill
```

So the ExecStart is correct, it serves a real X client, and `Restart=always` genuinely recovers
from a SIGKILL. What remains unproven is only that systemd starts it **at boot** on `:99`.

## Part 2 — `nix-ibgateway.service`

**ExecStart derived from `/proc/236482/cmdline`, and the derivation matters.** The live argv still
contains **unsubstituted install4j placeholders** — `-DjtsConfigDir=${installer:jtsConfigDir}`,
`install4j.ibgateway.GWClient ${installer:cmdLineArgs}` — and a JRE path carrying a generated hash
(`~/.local/share/i4j_jres/Oda-jK0QgTEmVssfllLP/17.0.16.0.101-zulu_64/bin/java`). Copying that argv
into a unit would be brittle and wrong. Reading the launcher shows why it is also unnecessary:

```
$ grep -c 'exec "$app_java_home/bin/java"' /home/bbt/ibgateway/ibgateway
2      # both branches exec — the launcher does not fork
```

The launcher **execs** the JVM, so `Type=simple` tracks the real process with
`ExecStart=/home/bbt/ibgateway/ibgateway`. (The JVM's `PPID 1` is reparenting after the invoking
VNC shell exited, not evidence of forking.)

```ini
[Unit]
BindsTo=nix-xvfb.service
After=nix-xvfb.service
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User=bbt
Environment=DISPLAY=:99
WorkingDirectory=/home/bbt/ibgateway
ExecStartPre=/bin/sh -c 'for _ in $(seq 30); do xdpyinfo -display :99 >/dev/null 2>&1 && exit 0; sleep 1; done; exit 1'
ExecStart=/home/bbt/ibgateway/ibgateway
Restart=on-failure
RestartSec=15
```

### Dependency type — `BindsTo=`, reasoned rather than defaulted

`Requires=` propagates a failed *start* and an explicit stop, but it **leaves this unit running
when `nix-xvfb.service` dies on its own.** A Gateway whose X server vanished is precisely the
"unit is active, the thing is unusable" state that Part 3's gate exists to catch — and an AWT
application that loses its display can sit there holding port 4002 in a broken state rather than
exiting cleanly. `BindsTo=` makes that state impossible instead of merely detectable. `After=`
orders the two on the way up.

**Ordering alone would not have been a real dependency**, which the arc explicitly warned about:
`nix-xvfb.service` reaches `active` the moment Xvfb forks, milliseconds before the display accepts
clients, and Gateway aborts on a display it cannot open. Hence the `ExecStartPre` that polls
`xdpyinfo` until the display genuinely answers — a readiness gate, not an ordering hint.

`Restart=on-failure`, not `always`: a crash or OOM kill must bring it back, but an operator who
deliberately shuts Gateway down must not have to fight systemd.

### A real defect the tooling caught

`systemd-analyze verify` rejected the first draft:

```
/etc/systemd/system/nix-ibgateway.service:31: Unknown key 'StartLimitIntervalSec' in section [Service], ignoring.
```

Rate limiting is a **unit**-level property. In `[Service]` it is *silently ignored* — a restart
loop with no brake, in a config that otherwise looks correct and reports no error. Moved to
`[Unit]` and confirmed effective:

```
$ systemctl show nix-ibgateway.service -p StartLimitIntervalUSec -p StartLimitBurst -p Restart -p BindsTo -p Slice
BindsTo=nix-xvfb.service
StartLimitIntervalUSec=5min
StartLimitBurst=5
Restart=on-failure
Slice=system.slice
```

## Slice membership — decided, not defaulted

**Neither unit joins `nix-trading.slice`.** I agree with the arc, and the reasoning is stronger
than "Xvfb is scaffolding".

First, a correction: **the arc cites `elements_v2.md` §1.4, which does not exist.** That document
has §1.1–§1.3, §2, §3, §4. The governing authorities are `nix-trading.slice`'s own definition
(`AllowedCPUs=0-5`) and **risk spec §10, the locked process/core map**:

| Core | Assignment |
|---|---|
| 0 | OS/kernel + interrupts |
| 1 | capture.py (hosts broker-datafeed) |
| 2 | Risk Engine (Limiter + broker-order) |
| 3 | Allocator + strategy processes |
| 4–5 | shared pool: Postgres, pollers, backfill, logging, ZMQ proxy, dashboards, health, Sentinel, Scoring |

1. **Neither process appears in that map.** The trading path's broker contact is the
   `broker-datafeed` and `broker-order` *libraries* (cores 1 and 2), not this JVM. The map is
   locked; adding an unlisted member to the slice it encodes is a change to the map, and this arc
   has no authority to make one.
2. **On QuantVPS the slice is the whole 6-core box, so membership is a no-op there.** On this
   20-core dev box it is a real restriction. So including them would create a dev/prod behavioural
   difference — exactly what `dev_and_services_plan.md`'s core discipline forbids.
3. **The decisive one, measured from the live argv:** the Gateway JVM runs `-Xmx768m` with
   `-XX:+UseG1GC -XX:ParallelGCThreads=20 -XX:ConcGCThreads=5`. Those thread counts are sized for
   this 20-core box. Confining that JVM to cores 0–5 while it still spawns 20 parallel GC threads
   would land its GC pauses directly on the cores risk spec §11's hot-path discipline exists to
   keep clear — worse than leaving it out, not merely different.
4. **IBKR is permanently paper-only Stage 0**, with Tradovate the live broker at cutover. Pinning
   throwaway scaffolding into the locked core map encodes a Stage 0 artifact as a production
   constraint.

Both run in `system.slice` (confirmed above). **Stated for the next author:** when Tradovate
becomes trading-path, its membership is decided against §10 on its own merits — not inherited
from this decision.

## Part 3 — `checks/check_ibgateway_service.py`

Registered in `checks/registry.json`. **Owns service persistence only**;
`check_ibgateway_config.py` owns API configuration. The boundary is stated in both docstrings.

**It does not build a second instrument for "reachable" (doctrine C.9 / §5.5).** It *imports*
`api_handshake` from `check_ibgateway_config` rather than reimplementing it, so the two gates can
never disagree about what reachable means. Asserted by a test:

```python
assert "from check_ibgateway_config import" in source
assert "def api_handshake" not in source
```

**The same observation carries a different verdict in each gate, deliberately.** An unreachable
Gateway is `CANNOT_MEASURE` for the config gate (it reads settings *through* the connection) and
`FAIL` for this one (persistence that does not persist). Both are correct; the docstrings say so
explicitly so it does not read as a contradiction.

**No proxies.** `systemctl is-enabled` and `is-active` are recorded as *evidence*; the verdict
comes from `xdpyinfo` opening the display and a real IB handshake completing.

**A second duplication the gates caught on the way in.** pylint's `R0801` flagged that both gates
rendered a `[(site, why)]` defect list into a `CheckResult` with identical code. Rather than
suppress it, the rendering moved to `nixverify.contract.result_from_defects()` — the same C.9
reasoning as the shared handshake, applied to a smaller thing. Both gates were re-run afterwards
and reproduce every verdict above verbatim, including the planted FAIL.

### FAIL-with-CONTROL — verbatim

**Step 1 — PASS:**
```
pass: nix-xvfb.service=enabled/inactive; nix-ibgateway.service=enabled/inactive; display :99:
dimensions:    1440x900 pixels (366x229 millimeters); 127.0.0.1:4002 handshake: answered (187)
exit=0
```

**Step 2 — NON-VACUITY, before the plant.** Unit state must not be able to carry a verdict alone:
```
-- the gate's own scope assertion --
test_run_probes_the_display_and_the_socket_not_just_unit_state  1 passed
-- independent: strace the real run --
connect(3, {sa_family=AF_UNIX, sun_path=@"/tmp/.X11-unix/X99"}, 21) = 0
connect(3, {sin_port=htons(4002), sin_addr=inet_addr("127.0.0.1")}, 16) = -1 EINPROGRESS
```

**Step 3/4 — PLANT `systemctl disable nix-xvfb.service` → FAIL naming the unit:**
```
Removed '/etc/systemd/system/multi-user.target.wants/nix-xvfb.service'.
nix-xvfb.service: disabled     nix-ibgateway.service: enabled

fail_needs_operator: nix-xvfb.service=disabled/inactive; nix-ibgateway.service=enabled/inactive;
display :99: dimensions: 1440x900 pixels ...; 127.0.0.1:4002 handshake: answered (187)
  site: nix-xvfb.service
  detail: nix-xvfb.service: is-enabled reports 'disabled' — will not come back after a reboot
exit=1
```

Worth noting what that output demonstrates beyond "it failed": it names **only** the disabled
unit, and it fails **while reporting the display still answering**. The gate is discriminating
between "will come back after a reboot" and "works right now" — two different properties that a
proxy check would have collapsed.

**Step 5 — UNPLANT / Step 6 — CONTROL:**
```
Created symlink '/etc/systemd/system/multi-user.target.wants/nix-xvfb.service' → ...
enabled / enabled

pass: nix-xvfb.service=enabled/inactive; ... handshake: answered (187)
exit=0
```

**Plant hygiene (C.8 / §5.4):** the plant was `systemctl disable`/`enable` — fully reversible and
touching no running process. The authenticated Gateway session survived the entire arc
(`LISTEN *:4002 pid=236482` held throughout).

### Full suite through `verify.py`, the real runner

```
  [ok]   check_python_runtime   | sys.version_info=3.14.4 at /usr/bin/python3
  [ok]   check_venv             | /home/bbt/nix/.venv/bin/python3: Python 3.14.4
  [ok]   check_node_identity    | stored == live == 0a2fe0d5-5eb2-46ae-a9f9-013dc7097003
  [ok]   check_python_deps      | pins satisfied: ib_async==2.1.0
  [ok]   check_ibgateway_config | IB API handshake on 127.0.0.1:4002 -> serverVersion=187; ...
  [ok]   check_ibgateway_service| nix-xvfb.service=enabled/inactive; ...; handshake: answered (187)

  6 passed | 0 failed | 0 cannot measure | 0 skipped          exit 0
```

**142 → 153 tests, all eight pre-commit hooks green.**

## Part 4 — `dev_and_services_plan.md`

New **Boot persistence** section carrying the units, the `BindsTo` reasoning, the slice decision,
and — as a call-out box, not a footnote — **boot persistence ≠ unattended auth**: after a reboot
Gateway comes up on its login screen needing credentials and an IB Key tap, and auth automation is
out of scope because anything built against IBKR's flow is discarded at the Tradovate cutover.

Also corrected there from ARC 010's measurements: the Lock-and-Exit change (auto-logoff → auto
restart, daily 2FA → weekly), where the API settings actually live (and the
`LocalServerPort=4000` trap), and the Err 10189 entitlement finding with its bar-immutability
consequence.

## CHECK-DEBT movement

**22 → 21.** D1.8/D1.9 (Xvfb and Gateway persistence) discharged by `check_ibgateway_service`;
**D1.12 opened** for the unverified reboot behaviour. First recorded fall in the series — which,
per doctrine A.7, is the thing that never once happened on the predecessor system across
seventeen arcs.
