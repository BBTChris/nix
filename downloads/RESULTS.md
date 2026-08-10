# RESULTS — ARC 008 (partial) + verify.py v2 build

**Status: ARC 008 NOT complete.** Three of its five success boxes remain blocked on human action.
A large adjacent body of work — the verify.py v2 provisioning engine — was designed, planned,
built, reviewed, and landed in full. Both are reported below.

---

## Part A — ARC 008 against its own definition of success

| Box | State |
|---|---|
| Real API config values (port, `ReadOnlyApi`, `TrustedIPs`) from `jts.ini` or live-inferred | ❌ **Blocked** |
| `ib_async` confirmed installed, version recorded | ✅ **`2.1.0`** |
| Live connect clientId=905; entitlement status (10189 or not) determined | ❌ **Blocked** |
| `clientId` scheme documented in `dev_and_services_plan.md` | ✅ |
| `check_ibgateway_config.py` built, registered, exit contract, FAIL-with-CONTROL demonstrated | ❌ **Blocked** |

### Why the three are blocked

The arc opens: *"Manual IBKR login (Arc 006 Step 7, previously blocked) is now done by the human."*
**It is not.** Measured twice, hours apart, not assumed:

- `find / -name jts.ini` → **no hits anywhere on the filesystem**
- `~/Jts/` → **empty** (only `.` and `..`)
- IB Gateway / install4j / Xvfb / java processes → **none running**
- Ports 4001, 4002, 7496, 7497 → **nothing listening**; `ib_async.connect(clientId=905)` returns
  `ConnectionRefusedError` on each

This is byte-for-byte the state Arc 006 recorded at Step 7. Per `dev_and_services_plan.md`,
first-auth requires a GUI login plus IB Key 2FA approval on the operator's phone — a vendor
constraint that cannot be scripted. The arc's own stated fallback (infer settings from Part 3's
live connection) is blocked by the same cause.

**Part 5 is blocked for a second, independent reason.** §5.1's acceptance cycle requires
PASS → plant → FAIL → unplant → PASS. Steps 1 and 6 are PASS legs. With nothing listening, every
path returns exit 2 (CANNOT MEASURE) — only the branch that proves nothing about the gate's
discriminating power could be demonstrated.

### Part 2 — `ib_async` (done)

Genuinely absent; the venv held only `cryptography` plus tooling. Installed **`ib_async==2.1.0`**
on Python 3.14.4. `import ib_async` succeeds; `reqTickByTickData` and `reqHistoricalTicks` both
present on `IB`. Pinned — now via `checks/pinned_deps.json`, read by both `install.sh` and
`check_python_deps`, so install and verify cannot disagree about a version.

### Part 4 — clientId scheme (done)

Recorded in `dev_and_services_plan.md`'s IBKR section, framed as a decision rather than a
discovery. One row added beyond the arc's specification:

| `clientId` | reserved for |
|---|---|
| `0` | **permanently excluded** — implicitly adopts manually-placed TWS orders, exactly the order-ownership ambiguity the mission scope forbids |
| `1` | live Risk Engine — reserved, not yet built |
| `905` | diagnostics / tooling |

### To unblock

One action, operator-side: GUI login to IB Gateway plus IB Key approval on your phone. Gateway
and Xvfb are installed; the login screen can be exposed over VNC or X forwarding on request. Once
`jts.ini` exists and a port answers, Parts 1 and 3 take minutes.

---

## Part B — `VERIFY-AND-CHECKS.md` and the verify.py v2 engine (complete)

Arc 008 Part 5 required following `VERIFY-AND-CHECKS.md` exactly. **That document did not exist** —
searched the whole filesystem, all of git history, and `~/.claude`; the only occurrence of the
string was the arc file's own citation. `checks/` was empty and no check had ever been written.

So it was authored (v1.0.1, now indexed in CLAUDE.md's spec table and therefore an authority by
the project's own "nothing else is a source of truth" rule), a 13-task plan was written against
it, and the plan was executed task-by-task with an independent review after each.

### What now exists

`scripts/verify.py` (CLI) over `scripts/nixverify/` — `contract`, `manifest`, `loader`, `engine`,
`render`. Four checks, all passing against **real state on this machine**, not fixtures:

```
[ok]   check_python_runtime   | sys.version_info=3.14.4 at /usr/bin/python3
[ok]   check_venv             | /home/bbt/nix/.venv/bin/python3: Python 3.14.4
[ok]   check_node_identity    | stored == live == 0a2fe0d5-5eb2-46ae-a9f9-013dc7097003
[ok]   check_python_deps      | pins satisfied: ib_async==2.1.0

4 passed | 0 failed | 0 cannot measure | 0 skipped          exit 0
```

126 tests. Three systemd runners: boot (`User=bbt`, non-disruptive), weekly user
(`User=bbt`, maintenance), weekly root (Sat 03:00 America/Chicago, maintenance). `install.sh`
installs all of them.

### Demonstrated FAIL-with-CONTROL (§5.1), verbatim

```
1. PASS      pass: pins satisfied: ib_async==2.1.0                      exit 0
2. evidence  non-empty, names the pins actually measured
3. plant     checks/pinned_deps.json ib_async 2.1.0 → 2.0.1
4. FAIL      fail_repairable: ib_async: 2.1.0 (want 2.0.1)              exit 1
5. unplant   git checkout checks/pinned_deps.json
6. PASS      pass: pins satisfied: ib_async==2.1.0                      exit 0   ← the control
```

Step 4 names `ib_async` specifically. Step 6 reproduces step 1 exactly — that is what proves the
failure was caused by the plant and not by ambient conditions.

### Design decisions worth the architect's attention

- **Five states, not a boolean.** `PASS` / `FAIL_REPAIRABLE` / `FAIL_NEEDS_OPERATOR` /
  `CANNOT_MEASURE` / `SKIPPED`. A downed service and a misconfigured one are different facts.
- **Non-vacuity is mechanical.** A `PASS` with empty `evidence`, or a `FAIL_*` with empty `site`,
  is downgraded to `CANNOT_MEASURE` by the engine. A check cannot claim success without recording
  what it measured. Enforced on both the plugin and standalone paths.
- **Disruptive gates the repair, not the inspection.** A disruptive check outside the maintenance
  window is downgraded to inspect-only rather than skipped — drift is still reported at boot, the
  mutation is refused. Verified live: planted pin drift reported at boot with the installed
  version untouched.
- **Credentials: `systemd-creds` + TPM2 supersedes Fernet.** TPM 2.0 confirmed present. The Arc 006
  Fernet store cannot decrypt at boot without a human, contradicting the headless self-healing
  invariant. Decision recorded in §11; **migration not yet performed** — `install.sh` still
  contains the Fernet block.

### Two commit gates found silently non-functional

- **bandit has never scanned anything.** bandit 1.8.6 uses `ast.Str.s`, removed in Python 3.12; it
  `AttributeError`s mid-parse, marks the file skipped, and exits 0. Proven: it passes a file
  containing `subprocess.run("echo hi", shell=True)`. Repo-wide since Arc 006. **Still outstanding
  — needs a human call on timing.**
- **pylint could not resolve `nixverify`** for commits touching only `checks/`, and separately its
  `duplicate-code` pragma was silently ineffective. Both fixed and proven to fail on a planted
  defect before being trusted again.
- The pytest hook accepted exit 5 ("no tests collected") as a pass. Removed; proven it now fails.

### Honest accounting

Nearly every defect found was in the **plan**, not the implementations. Reviewers caught: a
`validate_result` that destroyed diagnostics; a manifest loader that crashed on non-object JSON; a
plugin loader leaking `sys.modules`; a halt diagnostic naming the wrong block; an ASCII fallback
that still emitted Unicode; a node-identity check reading a JSON key `install.sh` never writes
(which would have failed forever on every correctly-provisioned node); and a `pip install` of the
order-placing library that could fire unattended on any boot. The controller also made three
verification errors, all caught by reviewers.

**Recommendation to the architect:** the §5.1 FAIL-with-CONTROL discipline should apply to tooling,
not only to checks. Two of six commit gates were reporting success having examined nothing — the
exact vacuous-success failure §5 exists to prevent, sitting inside the gate meant to prevent it.
`debug.md`'s three-tier model arguably needs a clause requiring each gate be proven capable of
failing.

---

## Branch

`arc-009-verify-v2`, 52 commits off `arc-006-provisioning-v2` (so PR #8 is not enlarged).
Not merged — awaiting review.
