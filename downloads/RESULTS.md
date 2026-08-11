# ARC 024 — RESULTS

**The check contract: Plane 2, actuation, orchestration**
Phase 0 reconciliation, then Stage 1 serial, Stages 2–6. 2026-08-11.

---

## HEADLINE

**A fourth status exists and is live on a real subject.** `verify.py` now reports

```
11 passed | 1 failed | 1 cannot measure | 0 skipped | 1 guarded          exit 1
```

The baseline is preserved exactly — `check_ibgateway_service` FAIL + `check_ibgateway_config`
cannot-measure, the Gateway's daily 03:00 session expiry. **No further FAILURE.** The one further
non-PASS is the new `GUARDED`, and its cause is named in its own verdict string.

---

## PHASE 0 — six reconciliations, three of which found the brief wrong

| # | subject | finding |
|---|---|---|
| 0.1 | ARC 023 close-out | **MERGED.** HEAD `2871bc6`. verify.py exit 1, 10/1/1. pytest 351 passed + 2 xfailed. pre-commit 8/8. CHECK-DEBT 61. `RESULTS.md` genuinely ARC 023's (`head -1` = `# ARC 023 — RESULTS`, mtime 2026-08-11 20:02:53, 7 hits) |
| 0.2 | `manifest.json` vs `registry.json` | **REPORTED, NOT RESOLVED — operator rules.** No `manifest.json` exists and never has. `manifest.json` occurs in exactly one file in the repo: the ARC 024 brief. They are ONE artifact whose file was renamed and whose vocabulary was not — ARC 010 renamed `verify_manifest.json` -> `checks/registry.json` under doctrine A.4/D.5, while every identifier one layer down still says manifest: `nixverify/manifest.py`, `ManifestError`, `load_manifest()`, the `--manifest` flag, and **the file's own first key, `"manifest_version"`**. Nothing renamed, merged, or created |
| 0.3 | TUI census | A colour surface exists; **a progress surface does not.** Measured: 0 ANSI piped, 13 under a pty. Output was **post-hoc** — all 13 result lines arrived within **32 ms** at the end of a multi-second run. Also: **yellow was already occupied by CANNOT_MEASURE**, so the ruling is a recolour of a live state, not an addition |
| 0.4 | check census | **12 checks, 0 orphans either direction** (12 = 12, itself the standing claim `registered_check_count`). The operator's "hundreds" estimate is not this tree. **`--mode verify\|correct\|install` already existed** and already defaulted to verify — the architect's measure-only ruling was already the policy on disk. Zero of 12 exposed it on their own CLI. No check declared any dependency, resource, or runtime. Checks are imported **in-process**, not subprocesses; multi-check blocks use threads; **no block set `parallel: true`** |
| 0.5 | authority documents | **THE BRIEF'S PREMISE IS FALSE.** All three governing docs are present in `CLAUDE.md`'s specs table (lines 35, 36, 37) with explicit authority columns. Separately: the amendment ledger the brief points at is the wrong one — `SPEC-AMENDMENTS.md` amends the **frozen risk spec**, its own header says *"Nothing in this file is spec text"*, and it holds **six** amendments, not five |
| 0.6 | `debug.md` drift | **NO DRIFT EXISTS.** On disk: v1.2.0. `CLAUDE.md:32`: v1.2.0, and the row itself records *"this table said v1.1.0 until ARC 018"* — the repair already happened. The second citation carries no version at all. `debugging.md` has never existed because `.claude/rules/` has never existed, and `CLAUDE.md:18` says so. **Stage 5.3 had no subject** |

---

## §0a — defects found in the brief, reported not silently satisfied

1. **Stage 3.2 disjointness could succeed while measuring nothing.** Two checks that both declare
   `RESOURCES = ()` are trivially disjoint. 3.5 makes *declaring nothing* loud and says nothing
   about *declaring empty* beside a neighbour that declared. **Closed:** an undeclared member makes
   its whole block ineligible for parallelism and is never optimistically read as claiming nothing.
2. **Stage 4.3's expected-duration rule is self-contradictory.** A bar needs a denominator; 4.3
   forbids the moving anchor (last run's timing) and the only alternative is a hand-typed constant,
   which is a restated mutable fact under directive 3. **Resolved by anchoring the two indicators
   differently** — see Stage 4 below.
3. **Stage 2.7's coverage gate is admitted-vacuous by the brief itself.** It ships UNBOUND and says
   so in the evidence of every verdict it emits. Row **D3.19**.

---

## §0b — THE REFUSAL, WITH ITS MEASUREMENT

**Stage 3.1 as written would have degraded an instrument.** The ruling is *a block containing
multiple checks runs those in parallel, and by definition they have no dependency on one another.*

A `socket.connect` spy over a real run of both Gateway gates recorded:

```
check_ibgateway_config : [('127.0.0.1', 4002)]
check_ibgateway_service: [('127.0.0.1', 4002)]
SHARED ENDPOINTS: [('127.0.0.1', 4002)]
```

They sit in the **same registry block** (`trading-stack`), and the service gate imports the config
gate's handshake. clientId **1**/**2**/**905** are distinct precisely because IBKR sessions collide.

**The hazard is currently MASKED, and that is what makes it dangerous.** The Gateway is down, so
both gates get ECONNREFUSED — a parallel promotion would look harmless *today* and fail
intermittently once the Gateway is up, reading as a network problem rather than a tooling one.

**Refused. Existing multi-check blocks were not promoted.** The invariant is implemented instead as
proven-disjointness, and the refusal is banked as a test
(`test_the_two_gateway_gates_share_an_endpoint_and_must_not_go_parallel`). Row **D1.41**.

---

## STAGE 1 — Plane 2 (serial, first)

**1.1 Transport chosen by measurement, not preference.** Four candidates measured on node02:

| transport | measurement | verdict |
|---|---|---|
| `systemd.journal.JournalHandler` | imports under `/usr/bin/python3`, **`ModuleNotFoundError` under `.venv/bin/python3`** | **REFUSED** |
| stdlib `SysLogHandler` -> `/dev/log` | round-tripped to `journalctl` under **both** interpreters | **CHOSEN** |
| `systemd-cat` | present; one fork+exec per event | rejected on cost |
| stdout -> journald | no unit in the interactive case | unavailable |

**`JournalHandler` was refused on a measurement.** `verify.py` runs under both interpreters. A
handler chosen on the strength of the system interpreter would attach cleanly, log nothing, and
raise nothing under the venv — **a handler attached to a logger that never emits**, which is
precisely the vacuity 1.2's gate exists to fail, built in at the transport layer where the gate
could not see it.

**1.2 `checks/check_verify_logging.py`** — six arms, each answering one way the gate could pass
while measuring nothing. Verdict comes from `journalctl` reading the journal **back**, keyed on a
per-run **nonce** so history cannot satisfy it. **CAN-FAIL DEMONSTRATED:** emission disabled ⇒
exit 1 naming the site; live ⇒ exit 0. A `Plane2` pointed at a regular file reported
`available=True delivered=0`, which was weak, so `available` was tightened to mean *the destination
is a socket* — the control made the instrument better.

**1.3 Presentation never enters the journal — PROVEN, not asserted:**

| surface | ANSI escapes | spinner frames |
|---|---|---|
| pty stdout | **14** | **46** |
| same run's Plane 2 | **0** | **0** |
| piped stdout | 0 | 0 |

---

## STAGE 2 — the contract amendment

Recorded in **`docs/CHECK-CONTRACT-AMENDMENTS.md`** (new), implemented in `nix_check_contract.md`
**v1.2.0**. `VERIFY-AND-CHECKS.md` was **not edited** — it is external, inherited, unversioned, and
has no amendment mechanism.

- **AMENDMENT 1 — `GUARDED` -> exit 3.** Measured subject + known-red marker naming the discharging
  arc. Withholds certification, never durability. **Strictly additive**: 0/1/2 keep their §B.2
  meanings and exit 2 is untouched. Both properties are **mechanically enforced** in
  `validate_result` — a GUARDED verdict with no evidence, or no `guard_owner`, degrades to
  CANNOT_MEASURE. Dominance: **FAIL > CANNOT-MEASURE > GUARDED > PASS**, because cannot-measure
  carries no information about its subject while GUARDED carries a measurement and an owner.
- **AMENDMENT 2 — actuation.** `--correct`/`--install` on every check's own CLI; default
  measure-only. **The verdict after a mutation is the RE-VERIFY's, not the correction's** — a fresh
  subprocess in verify-only mode. Non-correctable class implemented (3 members). Session interlock
  has **three** states; UNKNOWN refuses and names what it could not determine.
- **AMENDMENT 3 — coverage trigger broadened**, enforced by `check_artifact_gate_coverage`.

**§2.2's control is the load-bearing test.** A planted check returns PASS in CORRECT mode and FAIL
when re-measured. `standalone_main` returns **1**, not 0, and prints `RE-VERIFY DID NOT CONFIRM`.
The first version of that test passed for the wrong reason — the subprocess crashed and also
returned 1 — caught only because the test asserted the message too.

---

## STAGE 3 — orchestration

**§3.3 — both mechanisms built and measured against the real population before choosing:**

| | AST parse | import-to-read |
|---|---|---|
| coverage | 13/13 | 13/13 *(1/13 before the comparison was made fair)* |
| wall clock | **27.8 ms** | 29.7 ms |
| `sys.modules` growth | **0** | **+76 across 7 modules** |
| executes module-level code | **no** | yes |

**Cost is not the discriminator** — the first import measurement showed 1/13 against a strawman
(it omitted `loader.py`'s `sys.path` step) and was **re-taken before being used**. The
discriminators are structural: import cannot promise not to execute measurement logic, it
permanently mutates the process, and it fails closed in the wrong direction. **The failure mode of
the mechanism NOT chosen is demonstrated** — a planted check whose module level writes a file:
import creates it, `read_declaration` does not.

**§3.5 — all four loud failures fire, each with its own test:** cycles (naming participants),
orphans (**both directions**), undeclared dependencies, non-disjoint parallel blocks. A failed
derivation writes **nothing — not even a `.proposed` file**, because a `.proposed` on disk is an
invitation to commit it.

**§3.4 [ARCHITECT RULING — revocable, implemented as written and flagged]:** `--optimize` proposes
`<manifest>.proposed` and requires `--commit`. Say the word and the default flips.

---

## STAGE 4 — TUI

Colours per the ruling: red=Failed, **yellow=Guarded**, green=Passed, light blue=Cannot run or
check. **Yellow was a recolour** — CANNOT_MEASURE held it until now and moves to light blue, which
also absorbs SKIPPED's grey. **No information lost, and that was checked:** the two already share
exit code 2 and keep distinct glyphs in both glyph sets, and the glyph survives a pipe.

**§0a resolution for 4.2/4.3, stated plainly:** the run-level indicator (`n/total`) is **derived**
from the manifest and is a real measurement. The per-check indicator is a spinner with a count-up
clock measuring **elapsed time only, never predicted remaining time**. `EXPECTED_S` is a hint
rendered beside a real count and must derive from a constant already in the check's own code.
Nothing on the surface is a prediction dressed as a measurement.

---

## STAGE 6 — pilots, and §0c re-binding

**§0c: a retrofitted check is a new check.** All three pilots re-established can-fail against their
**real** subjects, `__pycache__` purged between steps, every control restored byte-identical:

| pilot | shape | control | plant | restore |
|---|---|---|---|---|
| `check_python_deps` | **installable** | sha `db23631d` exit 0 — **matches ARC 022's banked figure exactly** | `ib_async` `2.1.0`->`2.0.1` ⇒ exit 1 naming the site | sha identical, exit 0 |
| `check_order_path_bans` | **non-correctable** (order path) | sha `7bb4b539` — **matches ARC 022's banked figure** | `import tenacity` into the real `broker_order_ibkr.py` ⇒ exit 1 naming `broker_order_ibkr.py:146` | sha identical, exit 0 |
| `check_venv` | **correctable** | real home, genuinely absent `.venv` ⇒ exit 1 | `--correct` built it ⇒ **independent fresh-process re-verify exit 0** | removed ⇒ exit 1 again |

The shared `.venv` was never touched.

### 6.4 — SIZED PLAN FOR THE BULK RETROFIT

**Population 14. Declared 5. Remaining 9.** (Not "hundreds" — that is the denominator.)

| wave | checks | why grouped | risk |
|---|---|---|---|
| **A — no shared resource, static subjects** | `check_python_runtime`, `check_node_identity`, `check_spec_citations` | read-only, no socket, no service | low; can-fail re-take is cheap |
| **B — code-invariant gates** | `check_datafeed_bar_seal`, `check_datafeed_granted_mode`, `check_derived_claims`, `check_hook_suite` | all four were bound or re-bound in ARC 022/023; retrofit **unbinds them**, so each needs its banked plant re-taken in the same arc | **highest** — this is where §0c costs most |
| **C — Gateway pair** | `check_ibgateway_config`, `check_ibgateway_service` | must declare `port:127.0.0.1:4002` **together**, which then keeps them sequential automatically (D1.41) | needs a live authenticated Gateway to re-confirm |

**Non-correctable so far (3):** `check_order_path_bans`, `check_verify_logging`,
`check_artifact_gate_coverage`. **Proposed additions in the bulk retrofit:** `check_node_identity`
(credential/`state/` 0600 adjacent) and both Gateway gates (broker session state). **Operator to
ratify or narrow.**

`--optimize` is **INERT until wave A+B+C land** — 9 undeclared checks make it exit 1 with one named
error each. That is the designed behaviour, and it is row **D2.26** so nobody discovers it by
surprise.

---

## A LATENT DEFECT FOUND AND REPAIRED

`loader._import_module` registered a module in `sys.modules` **after** `exec_module`. Several stdlib
decorators resolve their defining module during class creation; with the module unregistered that
lookup returns `None`, so any check carrying a module-level `@dataclasses.dataclass` failed to
import with `AttributeError: 'NoneType' object has no attribute '__dict__'` — a message naming
neither the decorator nor the loader. **Found by the first check that used the construct**, not by
reading. Registration now precedes exec and is rolled back if exec raises.

---

## CLOSE-OUT MEASUREMENTS

| gate | result |
|---|---|
| `verify.py` | **exit 1** — `11 passed \| 1 failed \| 1 cannot measure \| 0 skipped \| 1 guarded` |
| pytest | **438 passed, 1 skipped, 2 xfailed** (was 351+2) |
| pre-commit | **8/8 hooks Passed** |
| derived-claims harness | **exit 0**, 13/13 claims, 2/2 demonstrations re-executed |
| CHECK-DEBT | **66**, `derived:ledger_rows` — the gate caught derived 66 vs stated 61 before the series row existed |

**Debt movement +5:** D1.41, D2.26, D2.27, D3.19, D3.20 — four of the five are limits this arc's own
instruments created, stated at the moment they were created. **Order-side contamination disclosed:**
`broker_order_open_debt_rows` moved 13 -> 15 while nothing touched broker-order, because D1.41 and
D3.20 legitimately name `broker_order_ibkr.py`. That is the D2.19 class recurring; do not read it as
order-side work.

---

## SIX ITEMS RETURNED TO THE OPERATOR

1. **`manifest.json` vs `registry.json`** — the name. Nothing renamed. **Your ruling.**
2. **Does `--correct` default on or off?** Architect says **off**; implemented off — and it was
   already off on disk since ARC 009.
3. **Ratify or narrow the non-correctable class.** 3 implemented, 3 proposed (above).
4. **Ratify the safety interlock.** Implemented fail-closed with a third UNKNOWN state.
5. **Confirm GUARDED's meaning.** Implemented as measured-subject + named discharging arc, exit 3,
   ranked below cannot-measure.
6. **Does `--optimize` overwrite, or propose-then-commit?** Implemented **propose**; `--commit`
   restores your ruling exactly.

All five architect rulings are implemented as written and flagged **[ARCHITECT RULING — revocable]**
in code and in the amendment ledger. None waited on ratification.
