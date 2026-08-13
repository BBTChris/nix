# ARC 029 — R2-B: The Exit Half — **STATUS: IN FLIGHT, PHASE 0 COMPLETE**

**This is not a close-out.** Phase 0 (serial, blocking) is finished and committed. Stage 1, Stage 2,
Stage 3 and Phase 4 have not started. `sessions/SESSION.md` is deliberately NOT appended and
`**** ARC completed ****` is deliberately NOT stated: the write-back gate proves an arc's work is
durable, and the arc's work is not done.

**Canonical path:** `/home/bbt/nix` · **Branch:** `arc-029-integration` · **HEAD:** `a4c2fb6`
**Tree:** clean · **Commits this arc:** 8, each passing all 8 pre-commit hooks.

---

## THE ONE ITEM THAT NEEDS AN ARCHITECT RULING BEFORE STAGE 1

**D3.104 — the guard re-owning ceiling has fired, and it refutes this arc's own 0.5 commit message.**

0.5 re-pointed all sixteen `gate_coverage_baseline.json` owners off the COMPLETED `ARC 027` to
`ARC 030`. That is exactly what `check_artifact_gate_coverage`'s own CANNOT_MEASURE verdict
instructed — *"re-point the marker at a live arc or take the red"* — and the commit message then
asserted that re-pointing is D2.31's marker walking forward and that *"nothing in this tree can stop
it"*.

**That was false, and the gate proved it in the same arc.** An operator ruling from ARC 027 caps
re-ownings at TWO; the lineage is derived from COMMITTED BLOBS; thirteen of the sixteen artifacts
were already at the ceiling. The fourth owner tripped it:

```
'the bulk check retrofit arc (ARC 025+), sized in ARC 024 Stage 6.4'
    -> 'ARC 025' -> 'ARC 027' -> 'ARC 030'

"the guard has been RE-OWNED 3 times, exceeding the ceiling of 2 ...
 GUARDED escalates to FAIL: discharge the guard, or take the red --
 it may not be walked forward again"
```

**The red is KEPT and that is the disposition, not an oversight.** Reverting to `ARC 027` restores
CANNOT_MEASURE — a completed arc wearing an owner's name (doctrine B.3) — which is the masking the
ledger exists to prevent. ARC 029 did not create this debt; it made four arcs of deferral legible by
removing the stale owner that had been hiding it.

**Three options, no default:**

1. **Discharge the thirteen** with real per-artifact coverage — a bulk retrofit of the size ARC 025
   attempted.
2. **Grant a fourth owner explicitly** — which sets the precedent the ceiling exists to refuse.
3. **Rule them permanently accepted** and move them out of a guard into a declared exclusion
   carrying its own justification.

The three artifacts BELOW the ceiling (`gitenv.py`, `registry.py`, `measurement_path.py`) remain
legitimately owned; the escalation names only the thirteen.

---

## MEASURED STATE

| measure | ARC 028 close | now | note |
|---|---|---|---|
| `verify.py` | 26 pass / 1 fail / 3 cannot-measure / 0 skip | **27 pass / 2 fail / 2 cannot-measure / 0 skip**, exit 1 | 31 checks (+1) |
| pytest | 1204 + 1 skipped + 2 xfailed | **1323 collected**, 0 failing under the commit gate | +119 |
| pre-commit | 8/8 | **8/8** on every commit | — |
| claims harness | 13/13, 2/2 demonstrations | **13/13, 2/2** | — |
| CHECK-DEBT | 142 | **145** derived == stated | Opened: D3.101, D3.102, D3.103, D3.104. Discharged: D3.55. Net **+3** |
| census | 30 three ways | 31 three ways | — |
| binding | 30 BOUND | 30 BOUND, 823 observations | the new check is UNBOUND pending Stage 3 |

**Phase 4's stated baseline moves, and the movement is explained rather than drifted:**
`check_artifact_gate_coverage` was CANNOT_MEASURE (stale owner), became GUARDED (live owner), then
FAIL (ceiling). `check_ibgateway_service` remains the tap session's FAIL. So the expected close-out
baseline is now **2 FAIL + 2 cannot-measure**, not 1 + 3.

---

## PHASE 0 — WHAT LANDED

### 0.1 — Baseline re-measured; three findings

Every ARC 028 figure held. The 1204 -> 1251 pytest delta at the time was fully attributed (+22 the
operator's own `nix_status.sh` v1.2.0 commit, +25 this session). Findings:

1. **The census control read the AMBIENT process.** It asked `_runs_tree_venv(os.getpid())`, but that
   predicate is defined on `VIRTUAL_ENV` while the test's precondition was `sys.executable`. Same
   commit, same bytes: `source .venv/bin/activate && python -m pytest` PASSES,
   `./.venv/bin/python -m pytest` FAILS. That is the ARC 028 defect this very predicate was written
   to remove — a verdict that is a function of the invocation spelling — reintroduced in the
   CONTROL. Repaired to drive a CONSTRUCTED child. The two predicates are complementary, measured:

   | spelling | `_mentions_home` | `_runs_tree_venv` | census sees itself |
   |---|---|---|---|
   | absolute path, unactivated | True | False | yes |
   | activated, bare `python` | False | True | yes |
   | venv on `PATH`, unactivated | False | False | **no** |

2. **`_await_exec` cannot observe an exec when the child's image equals the parent's** — found because
   the new control was flaky (cmdline read back `''` in 4 of 5 full-file runs). The same window made a
   neighbouring premise pass VACUOUSLY. Replaced with a readiness handshake.
3. **D3.101** — the third row above: the tree's own venv interpreter is invisible to all four census
   predicates in that spelling. Recorded, not repaired: no `/proc` fact distinguishes it, and
   attributing on the shared system image would sweep every unrelated system-Python process into a
   §10 core census. Owner ARC 030 per architect ruling.

### 0.2 — The restated-figure auditor can now see its own named blind spot

D3.82 recorded that the extractor is blind to counts spelled in WORDS, and the class recurred twice
more inside the documents reporting it. Two arms:

* **Worded numerals**, normalised to their VALUE, so `thirty-seven opened` in one document and
  `37 rows` in another land in ONE cross-document group instead of passing each other unseen.
* **Intra-sentence arithmetic** — a stated total reconciled against an enumeration in the SAME
  passage. `cross_document` needs a figure restated in ANOTHER FILE and is structurally blind to a
  row that contradicts itself.

**The measured defect:** the ARC 028 series row enumerates 41 opened and discharges 3, and narrated
`+36` and `thirty-six`. `41 - 3 = 38`. Both corrected in place and ANNOTATED; `SESSION.md` untouched.

Most of the work was killing false positives: a loose window read *"three opened"* as one; the
`Opened:` segment ran past its sentence (ARC 020's three read as seven); reading only enumerated
discharges turned *"one discharged"* into zero, producing three false positives against one true.
**Final result over 21 series rows: 2 findings, both true, zero false positives.** Can-fail proven on
the shipped instrument.

**Left visibly underived (architect ruling):** the subset numerator "twenty-nine" is marked
`[UNDERIVED — see D3.102]` AT THE SITE. Only the denominator was corrected.

### 0.3 — Untracked appearances in the canonical tree are ATTRIBUTED

`checks/check_untracked_attribution.py`, check 31. Reports the brief's triple — path, mtime, and
whether ANY commit on ANY branch contains it. Bound per §0e: the shipped gate observed going
`pass -> fail_needs_operator -> pass` on a real plant, in both the untracked and staged states.

Two design points carry it: it names `/home/bbt/nix` and measures it WHEREVER IT RUNS (a gate
measuring "the tree I am in" is blind in exactly the configuration the defect occurs in), and
`git log --all` separates a sub-agent's unmerged branch from bytes on a disk.

**The gate silenced itself, and that was the fourth §7.12 answer.** Keyed on `??` alone, staging the
new check turned it GREEN — and the close-out rule runs `git add -A` BEFORE every gate measurement.
Worse, `A ` is ARC 024's exact failure state (30 paths staged, never committed). It now counts `??`,
`A ` and `AM`.

**D3.103** opened by the gate's own author: it is blind to an escape into an IGNORED path — failure
mode #14 at the canonical tree. `--ignored` was considered and REFUSED as the wrong trade.

### 0.4 — SPEC-A7: HALT onset is a distinct terminal path

**The ruling was unobeyable as written, and that was the substance of the item.**
`spec_terminal_paths` read only the frozen spec, so `HALT_ONSET` was trapped: adding the member
reddens ARM 1 forever, and the only green available would have been to edit the frozen document. A
gate satisfiable only by breaking a standing rule gets broken instead. The reference side is now the
EFFECTIVE roster — frozen §3 sentence UNIONED with the ledger's `terminal-path additions` rows,
parsed and never typed.

**The ordering was measured in both directions, as the brief required:**

| state | verdict |
|---|---|
| amendment recorded, member absent | seam gate FAIL naming `HALT_ONSET`; lifecycle gate CANNOT_MEASURE, *"refuses to report over a set it silently shrank"* |
| member added | both PASS; the lifecycle gate DRIVES the sixth path |
| ruling stripped, member present | unspecced again, verdict says *"FINDING ABOUT THE SPEC"* |

Three reporting defects fixed en route: the seam gate printed `6 == TerminalPath members 5` on a run
that was RED for that inequality; both gates claimed a single-source provenance after acquiring a
second; and a test pinned four literals all derived from a five-member roster. **D3.55 discharged.**

### 0.5 — Real coverage for four zero-coverage artifacts

**The brief said four and named a different four.** The measured set was
`checks/_preamble.py`, `scripts/nixverify/__init__.py`, `scripts/tests/binding_tracer.py`,
`scripts/d1_12_reboot_capture.py`. Behavioural controls, not import smoke tests — an "executed by
every import" file changes the environment underneath all thirty-one gates at once.

**Re-pointing the stale owner let the gate measure again, and the first thing it reported was a
finding the unmeasurable state had been hiding** (one baseline row named by nothing). That is the
argument for treating CANNOT_MEASURE as a debt rather than a resting state — and it is also what led
directly to D3.104 above.

Two controls in the gate's own suite were broken BY the repair, both for the same reason: they
asserted properties of the AMBIENT tree. One required the live baseline to contain a row named by
nothing — so covering the last one made the suite punish the repair. One compared the WORKING
baseline's owner against the last COMMITTED one, which makes any re-owning UNLANDABLE.

### 0.6 — The exit seam frozen, every declared property proven able to redden the gate

Declarations only; ARM 2 confirms 25 callables classified, 0 carrying behaviour. `FlattenTrigger`
(§3:169, transcribed and closed), `StopState` (distances in ticks, one price, `anchor`, `activated`
as a latch), `SurvivalReading` (`net_liq` and `cash` as SEPARATE fields — conflating them is the
defect), `BrokerTruth` (positions AND balance from ONE poll), `ColdStartPort` (synchronous because
the property is an ORDERING one). Synthetic stops are named as synthetic at the top of the section:
§12.1 stands, the Sentinel is R4, and until it exists a killed Risk Engine is an unprotected
position.

**Seventeen plants, one per declared property**, each asserting the gate NAMES what moved — because
ARC 028's seam gate passed on all four ledger verbs rewritten `async def` AND on a deleted field. Two
new arms were needed, and **ARM 5's first version was caught by its own plant matrix**: the plant
aimed at `BrokerTruth.positions` hit `FinancialPicture.positions` first and NOTHING reddened, because
§3's atomic-snapshot fields had never been in the required set. That is ARC 028's deleted-field gap
living in the type the seam has carried since it was written. Six of §3's picture fields are now held.

The gate holds: 6 release paths · 25 callables · 17 verbs · 7 exit triggers · 14 required fields.

---

## WHAT REMAINS

**Stage 1** — four parallel sub-agents: A synthetic stops (§4, V33) · B protective flatten and the
trigger set (§3, §14) · C net-liq survival watch (§6.5, §15 C2) · D cold-start reconciliation
(§4, V34). **Stage 2** — integration, every protective path fired in simulation, Plane-1 rows,
idempotent execution handling. **Stage 3** — convergence: regenerate the plan, observer in three
orders, census three ways, binding table rebuilt. **Phase 4** — close-out and write-back.

The seam those four build against is frozen and gated, which is what Phase 0 existed to deliver.

---

## ALSO LANDED THIS SESSION (operator request, not arc scope)

`nix_status.sh` v1.3.0 and `verify.py --stream`: verdicts print as they land rather than after a
~70s silence (first verdict at 1.19s vs 4.32s batched, measured), and warning/error text names its
own colour in three derived tiers after a 24-bit sequence made those messages VANISH on this node's
256-colour terminal. This is the work D3.99 could not attribute and the operator has since claimed.

---

## OPEN TO THE OPERATOR / ARCHITECT

1. **D3.104** — the ruling above. Blocking nothing mechanically, but Stage 1 dispatches four more
   sub-agents and the arc will close against a 2-FAIL baseline either way.
2. **The tap session** — operator task at the console, ~40 min, owed by thirteen arcs. Still the
   other FAIL in `verify.py`, and it is a switch.
3. **D3.102** — the underived numerator, owner ARC 030, marked at the site.
4. **v1.4 remains deliberately not authority** (D3.33), now carrying SPEC-A7.
