# ARC 026 — Canonical Path, Reflexivity, and R1-C — RESULTS

**THE CANONICAL PATH IS `/home/bbt/nix` (absolute).** You are reading a live file at
`/home/bbt/nix/downloads/RESULTS.md`, written by this arc, in the tree every gate measures and the
Samba share `[nix]` serves. It has not been frozen since ARC 024 — it is current as of this arc.

**Predecessor:** ARC 025, merged at `0f9c5b9`. **This arc:** branch `arc-026-integration`.

---

## PHASE 0 — the brief's central instruction was refused, with a measurement

### 0.1 Provenance — CLEARS

`core.bare = true` was written to `/home/bbt/nix/.git/config` at **2026-08-12 01:23:25 UTC**, mid-ARC-025
(the only file under `.git/` modified in that window). The mechanism is recorded verbatim in this
project's own history at `sessions/SESSION.md:1514`:

> **`core.bare = true` was set on the shared repo config** by a sub-agent's `git init` running with
> `GIT_DIR` inherited from the pre-commit hook environment — hooks export `GIT_DIR`/`GIT_INDEX_FILE`
> and they outrank `cwd`.

**Accidental, not deliberate**, and a recurrence: ARC 020's brief §53 records the same conversion
mid-ARC-019, and briefs 021/022/023/025 all carry `core.bare != true` as a close-out item. **It is the
same root cause as D3.22**, the row sub-agent B was assigned this arc — one layer up in blast radius.

**Nothing "created" a shadow tree.** That framing is wrong and it mattered. `/home/bbt/nix` *is* the
original working tree, orphaned in place the instant `core.bare` flipped. Proven read-only, without
writing config:

```
$ git --git-dir=/home/bbt/nix/.git --work-tree=/home/bbt/nix -c core.bare=false status --short
?? downloads/arc_025_bulk_retrofit_and_observed_disjointness.md
?? downloads/arc_026_canonical_path_reflexivity_and_r1c.md
$ ... diff HEAD --stat
(empty — ZERO tracked files differed from HEAD)
```

### 0.2 Uniqueness — DOES NOT CLEAR. One finding.

- `arc_025_…md` — byte-identical (sha256) to its committed copy. Not unique.
- **`arc_026_canonical_path_reflexivity_and_r1c.md` — existed nowhere else on the machine.**
  `find /home/bbt -name 'arc_026*'` returned exactly one path: the one inside the tree 0.3 said to delete.

**Executing 0.3 as written would have deleted the only copy of the brief being executed.**

### 0.3 Delete — REFUSED

Blocked by 0.2's own rule, and independently by this:

```
$ smbstatus -S
Service   pid      Machine         Connected at
nix       145113   192.168.1.120   Sun Aug  9 05:35:36 PM 2026 UTC   [ACTIVE]
```

`/etc/samba/smb.conf` defines `[nix] path = /home/bbt/nix`; `smbd`/`nmbd` active and enabled. The
operator's workstation has held that mount since 2026-08-09 and uploaded `arc_026` to it at 03:22 the
same morning (the AppleDouble `._*` sidecars are the macOS SMB client's signature). **The tree was
invisible to git, not unused.** That is the reason 0.1 suspected might exist.

### 0.4 Canonical path — the ARCHITECT RULING IS REFUSED (§0b), with the measurement

The ruling moved write-back to `<canonical>/downloads/RESULTS.md` where `<canonical>` was to be a
per-arc worktree. **That places RESULTS.md outside the Samba share entirely.** The operator, who reads
over `//node02/nix`, currently sees a *stale* file; under the ruling they would see **no file**.
Strictly worse than the defect it was written to fix.

**Substitution: repair, do not relocate.** `core.bare` unset; local `main` fast-forwarded
`509159d → 0f9c5b9` (it was stale at ARC 024 — the same stale-local-main pattern ARC 020 recorded for
ARC 019); the stale ARC 025 worktree removed after proving it fully merged with zero unique content.

**`/home/bbt/nix` is therefore the canonical path — the path every standing rule already names, the
path the share already serves, the path gates already resolve. Zero standing rules needed rewriting.**
The repair dissolved the problem rather than routing around it.

### 0.5 `check_canonical_tree.py` — the spelling was refused too

The brief spelled the gate *"no untracked working files beside the bare repo"*. **That predicate is
permanently vacuous under its own fix**: the correct repair un-bares the repository, after which no
bare repo exists for anything to sit beside and the gate passes forever measuring nothing.

Invariant implemented instead: **every filesystem tree holding `scripts/verify.py` is accounted for by
a REGISTERED git worktree, and the canonical path is one of them.** It survives the repair, permits the
Stage 1 worktrees, and fires on the real historical defect — verified against that instance, where
`git worktree list` reported `/home/bbt/nix (bare)` while its `scripts/verify.py` existed and ran.

Declared NON-CORRECTABLE, with this arc as the evidence: the only mechanical "correction" for an
orphan tree is deletion, and deletion at this path destroys the operator's live share and, in the
actual instance, the arc's own instructions.

**Demonstrated can-fail, live on the real tree:**

```
non-vacuity   pass  exit 0   "1 tree(s) holding scripts/verify.py"
PLANT         fail  exit 1   NAMING /home/bbt/nix-orphan-demo at its site
UNPLANT       pass  exit 0   population restored
```

### 0.6 Re-measure — ZERO DELTA from ARC 025's close

| measurement | expected | measured |
|---|---|---|
| verify.py | 11p/1f/2cm/0s/1g exit 1 | **identical** |
| pytest | 520 + 1 skipped + 2 xfailed | **identical** |
| pre-commit | 8/8 | **identical** |
| claims | 13/13, 2/2 demos | **identical** |
| CHECK-DEBT | 68 | **68** |
| census | 15 three ways | **15 == 15 == 15** |

---

## §0a DEFECTS FOUND IN THIS BRIEF (the standing question, applied)

1. **0.6 could not detect a wrong canonical path.** Had 0.4 made the canonical tree the ARC-025
   worktree, 0.6 would have re-measured the tree ARC 025 had just measured and reproduced its numbers
   *by construction* — full success while measuring nothing about its own subject.
2. **0.5's predicate is deleted by its own remedy** (above).
3. **A3's premise was false.** The brief said to *find* the §0c AST classifier in `scripts/nixverify/`.
   **It did not exist.** Success by "reading the classifier" was satisfiable while measuring nothing.
4. **The brief's "pre-commit 8/8" baseline was false**, measured red at `98106be` (R0801 introduced by
   Phase 0.5 itself, visible only under `--all-files`, not under commit-scoped hooks). Reported here
   because I asserted 8/8 in the Phase 0.5 commit message on the strength of a commit-time hook run —
   that claim was wrong, sub-agent A caught it, and I verified the correction independently.
5. **The brief's "10 of 13" reflexivity census is 9.** Restated in `SESSION.md`, the debt ledger and
   the brief; derived by none of them.
6. Sub-agents additionally found and closed §0a defects in their own work before shipping — B's B3
   repair would have made its own claim unfailable (two sources reading one authored column agree
   always); C's affinity arm initially computed `alive = not exists` and would have passed trivially.

---

## STAGE 1

### A — reflexivity

**The §0c AST classifier did not exist.** ARC 025's was ad-hoc and uncommitted, so **ten of fifteen
binding rulings rested on a program nobody can run.** Built and committed as
`scripts/nixverify/measurement_path.py` (+ 24-case suite). Re-run over ARC 025's own diff
(`45a37fa`→`0f9c5b9`): **0 of 15 classify as declaration-only**, against the 10 the ruling was taken
on — `contract.py`'s `validate_result` changed, and every check's verdict passes through it.

**Reflexivity, demonstrated not asserted.** Three shared-helper plants; **two were invisible** —
exit 0, `13/13 claim(s) compared`, while `broker_order_element_coverage_v1` collapsed 56% → 0%.

**One answer changed at Stage 2, and it is a genuine gain:** after B3's authored column, the
`_DISCHARGED` plant that used to redden one claim while silently moving two others now **reddens all
three**. B's structural repair closed part of the reflexivity hole; A pinned it with a test so a
revert reddens rather than quietly restoring the blindness.

**Honest marking:** census **9 of 13** both-sources-internal; a second source now covers 8 claims;
**three claims are marked NOT INDEPENDENT** rather than implied.

### B — the two rulings and the contaminated metric

**B4 — D3.22 named the wrong site.** `check_hook_suite`, the gate the row is filed against, has
stripped *every* `GIT_*` since ARC 019 — **the best-protected caller**. The live exposure was
`scripts/runtime_gate.py`: the program `pre-commit` runs on every commit, therefore the caller
*guaranteed* to run with those variables exported, deriving its whole gate scope from `git ls-files`,
with **no scrub at all**. Reading the row instead of sweeping would have repaired the safe caller and
left the dangerous one. Single helper `scripts/nixverify/gitenv.py` (prefix rule, not a name list);
hostile-`GIT_DIR` suite against real decoy repos; disabling the scrub fails 7 of 10 naming the
repository that answered. **D3.22 discharged.**

**B3 — the metric stopped reading prose.** Owning-module column authored for all 93 rows.
**broker-order 13 → 9, broker-datafeed 13 → 7**, every differing row named — D1.38 was selected on the
single word `connect`; five rows were about *gates*, not the datafeed.

**B2 — `guard_owner` must name a dischargeable arc.** Source of truth `sessions/SESSION.md`; git
history rejected *on the facts* (commits naming an arc are made throughout it, so a git rule would
reject the one arc that can certainly pay). B's own cross-derivation reddened and revealed that the
series table legitimately runs one arc ahead of the session log. The live guard was re-pointed to
**ARC 027, not ARC 026** — refusing to name an arc that does not actually discharge the debt.

**B1 — manifest vocabulary purged** (file `registry.json` NOT renamed). The new gate found **4 live
survivors on its first real-tree run**, one of them inside the paragraph documenting the purge.

### C — R1-C, first product movement since ARC 021

All five items built: core map, `ipc://` PUB/SUB state bus with snapshot-on-subscribe, SPSC price
ring, four gates, per-channel Plane-2 emission from `capture.py`.

**§0b substitution, measured:** the spelling is `PUB`; the publisher socket is **`XPUB`**. §12.7 says
"plain PUB/SUB" *and* "publishers emit a full snapshot on subscribe" — a `zmq.PUB` socket cannot do
the second because subscriptions never reach the application. Measured on this node against a real SUB
peer: `PUB: pollin=0 frame=None` / `XPUB: pollin=1 frame=b'\x01tbl.'`. Same wire protocol, subscribers
unchanged. The literal spelling would have deleted the mechanism the same paragraph calls mandatory.

**Vacuous passes closed with real effective state:** affinity read from the kernel for a spawned PID
(`sched_getaffinity=1`, `Cpus_allowed_list=1`) with a `--no-pin` control returning `0-19` — and an AST
assertion that no literal in the gate names `systemctl`, `AllowedCPUs` or `.json`. Transport verdicts
require non-zero `bytes_received`, with a withheld-`service()` control proving arrival is attributable
to snapshot-on-subscribe. Shm sweep requires the detector to find its known subject or report
CANNOT_MEASURE.

**C under-declared once and the observer caught it** — and C fixed the *cause* (`shutil.rmtree`
unlinking by bare relative name) rather than declaring a stdlib implementation detail to go green.

---

## STAGE 2 — convergence

**2.1** Plan regenerated with `--optimize --commit`. 21 checks. C's four join level-2 behind
`check_venv`; the level-2 claim set gains `zmq-ipc` and `shm`.

**2.2 The observer bit — and the finding was about the observer.** `check_capture_plane2` FAILED for
`file-write:.../nixbus/__pycache__/*.pyc` against `RESOURCES = ("journal",)`. **The declaration was
honest and the observation was real; the attribution was wrong.** A `.pyc` write is the interpreter
caching a module, and because that cache is shared it is charged to whichever check imports first on a
cold tree — three sibling gates read clean purely because `check_capture_plane2` was scheduled ahead of
them and paid for all four. **A claim that moves between checks when the plan is reordered is an
artefact of the instrument.** Fixed at the cause (`sys.dont_write_bytecode` in `checks/_preamble.py`)
and **proven on a deliberately cold cache**, the only state where the defect exists. Declaring it
would have meant exact-string matching a path carrying a PID-derived suffix that never recurs.

**The canonical path paid a bill, and the gate was right.** `check_price_ring` went CANNOT_MEASURE on
5 unparseable files — macOS AppleDouble sidecars carrying `com.apple.quarantine`, which land in the
tree *because* `/home/bbt/nix` is the live share. 37 of them. Excluded by **filename class stated in
source**, never by `git check-ignore`: filtering gate scope on tracking state is this project's
most-repeated defect, and committing it inside the arc that exists to close it was not an option. C's
credibility floor still guards over-exclusion.

**Two debt-ID collisions** between B and C (`D2.31`, `D3.23` each naming different findings) resolved
by reading both texts, not by trusting the numbers. C's renumbered to D2.32/D2.33/D3.24. **New
vocabulary token `capture`** added so C's product debt was not filed under `verify`, which would have
re-contaminated the very metric B3 decontaminated.

**One moving anchor removed, in the new control.** A's `_DISCHARGED` control asserted
`derived:ledger_rows=31` / `stated:...=69` as **literals** — both functions of ledger size, so it broke
the moment C's rows merged. Updating them to 36/76 would have re-armed the trap for ARC 027.
Re-expressed directionally with a non-vacuity floor.

**2.3 Census three ways: 21 == 21 == 21** (executed == planned == on disk).

---

## §2.4 BINDING TABLE — all 21 checks, built from measured evidence

An artifact column entry is a **committed, runnable** file. Rows marked BOUND from prior arcs cite the
arc that shipped the artifact; rows this arc bound cite ARC 026.

| # | check | status | committed artifact | owner (non-BOUND) |
|---|---|---|---|---|
| 1 | `check_canonical_tree` | **BOUND** | `test_check_canonical_tree.py` (14) — ARC 026 | — |
| 2 | `check_derived_claims` | **BOUND** | `test_check_derived_claims.py` (13) + `independent_claims.py` — ARC 026 | — |
| 3 | `check_datafeed_bar_seal` | **BOUND** | `test_check_datafeed_bar_seal.py` (4) — ARC 026 | — |
| 4 | `check_datafeed_granted_mode` | **BOUND** | `test_check_datafeed_granted_mode.py` (5) — ARC 026 | — |
| 5 | `check_name_coherence` | **BOUND** | `test_check_name_coherence.py` (11) — ARC 026 | — |
| 6 | `check_core_map` | **BOUND** | `test_check_core_map.py` (16) — ARC 026 | — |
| 7 | `check_state_bus` | **BOUND** | `test_check_state_bus.py` (14) — ARC 026 | — |
| 8 | `check_price_ring` | **BOUND** | `test_check_price_ring.py` (18) — ARC 026 | — |
| 9 | `check_capture_plane2` | **BOUND** | `test_check_capture_plane2.py` (16) — ARC 026 | — |
| 10 | `check_observed_resource_claims` | **BOUND** | `test_check_observed_resource_claims.py` (15) — ARC 025 | — |
| 11 | `check_node_identity` | **BOUND** | `test_check_node_identity.py` (18, 10 fail-asserts, 20 plants) — ARC 022/023 | — |
| 12 | `check_python_runtime` | **BOUND** | `test_check_python_runtime.py` (12, 41 plants) — ARC 025 | — |
| 13 | `check_spec_citations` | **BOUND** | `test_check_spec_citations.py` (30, 28 plants) — ARC 025 | — |
| 14 | `check_venv` | **BOUND** | `test_check_venv.py` (8) — ARC 023 B, per D3.12 (real scratch venv, not a plant) | — |
| 15 | `check_hook_suite` | **PARTIAL** | `test_check_hook_suite.py` (17) — arm 1 bound, ARC 019 | arms 2–4 UNBOUND, **D3.14, unassigned** |
| 16 | `check_order_path_bans` | **PARTIAL** | `test_actuation.py` binds the actuation REFUSAL only | detection can-fail **unassigned** |
| 17 | `check_python_deps` | **PARTIAL** | `test_check_python_deps.py` (11, 2 fail-asserts, **0 plants**) — drives fixture states, not the real subject | a plant into the real pin set, **unassigned** |
| 18 | `check_artifact_gate_coverage` | **GUARDED** | `test_check_artifact_gate_coverage.py` (21) | `guard_owner` = **ARC 027**; D3.19 UNBOUND BY CONSTRUCTION |
| 19 | `check_ibgateway_config` | **UNBOUND** | none reproducing a can-fail | **the tap session** (operator, ~40 min) |
| 20 | `check_ibgateway_service` | **UNBOUND** | none reproducing a can-fail | **the tap session** |
| 21 | `check_verify_logging` | **UNBOUND** | **none — D3.25, opened by this table** | **unassigned** |

**D3.25 is a finding of Stage 2.4 itself.** Building this table from measured evidence rather than
from the previous arc's table showed that `check_verify_logging` has **no can-fail artifact at all**,
and no ledger row said so. The only occurrence of its name under `scripts/tests/` is a *docstring
line* in `test_plane2.py`. `test_plane2.py` binds the Plane-2 **emitter** — a different subject. The
gate has been green in every arc since ARC 024 and its green has never been shown able to turn red.
ARC 026 caught four prose-only bindings ARC 025 *asserted*, then found a fifth **nobody had asserted**
— which is worse, because an unclaimed binding attracts no audit.

---

## PHASE 3 — CLOSE-OUT MEASUREMENTS

All taken on this tree, with `__pycache__` purged first (cold cache).

```
verify.py    17 passed | 1 failed | 2 cannot measure | 0 skipped | 1 guarded    exit 1
pytest       761 passed, 1 skipped, 2 xfailed
pre-commit   8/8 Passed                                                          exit 0
claims       13/13 compared, 2/2 demonstrations re-executed                       exit 0
CHECK-DEBT   77 open  (derived:ledger_rows=77 == stated:series_table_latest_row=77)
census       21 == 21 == 21   (executed == planned == on disk)
```

**Every non-pass, named.** They are exactly the three the brief specified as baseline, and nothing else:

| verdict | check | cause |
|---|---|---|
| FAIL | `check_ibgateway_service` | `127.0.0.1:4002` ECONNREFUSED — Gateway down (baseline) |
| cannot-measure | `check_ibgateway_config` | no API endpoint at `127.0.0.1:4002`; not a misconfiguration (§4.1) |
| cannot-measure | `check_observed_resource_claims` | masked hazard — downstream of the two gates above did not execute, so remaining resource use is UNOBSERVED. §17: never PASS |
| **GUARDED** | `check_artifact_gate_coverage` | `guard_owner` verbatim: **`ARC 027`** — "19 artifact(s) accepted as uncovered by checks/gate_coverage_baseline.json, discharged by ARC 027" |

**No further FAILURE. No further non-PASS whose cause is not named.**

### CHECK-DEBT, old series beside new (B3's owning-module column)

| metric | old (prose selection) | new (authored column) |
|---|---|---|
| `broker_order_open_debt_rows` | 13 | **9** |
| `broker_datafeed_open_debt_rows` | 13 | **7** |
| total open | 68 (ARC 025) | **77** |

Ten opened, one discharged (**D3.22**). Opened: D2.31, D3.23 (B); D1.42–D1.45, D2.32, D2.33, D3.24
(C, renumbered at integration); **D3.25** (Stage 2.4).

---

## OPEN ITEMS RETURNED TO THE OPERATOR

1. **The tap session** — operator task at the console, ~40 min, now owed by eight arcs. It discharges
   D1.12, D1.33, the live rejection taxonomy, feed-lag re-measurement, D1.39/D1.40, and **binding rows
   19 and 20 above**. Plausibly the first `verify.py` exit 0. The runbook is written and unrun.
2. **`check_verify_logging` is UNBOUND (D3.25)** — new, and unassigned.
3. **`check_hook_suite` arms 2–4** remain UNBOUND (D3.14), unassigned.
4. **D3.21** — evidence contradicting its own verdict. Needs an owner.
5. **D2.31's ceiling** — the guard-owner rule now rejects an owner naming a *closed* arc but cannot
   stop one being walked forward arc by arc. The ceiling (N re-ownings, then escalate to FAIL) is an
   **operator ruling**, not an implementation detail.
6. **D1.44** — §10 assigns cores 0–5; this node has 20. Cores 6–19 are assigned by nothing. **Architect
   ruling.**
7. **Spec v1.4** folding the amendments into the frozen document — architect debt, still owed.
8. **Naming:** the brief calls per-channel freshness "Amendment 5"; on disk it is **AMENDMENT 6**.

---

## WHAT THE OPERATOR SHOULD TAKE FROM THIS ARC

The instruction that would have done the most damage was the one that looked like housekeeping.
**Deleting the "shadow tree" would have destroyed the arc's own brief and the operator's live file
exchange.** It was stopped by the brief's own 0.1/0.2 gating — which is the gating working, and the
reason those two steps are ordered before 0.3.

The second-order lesson is the same shape one layer down: **five of this arc's most valuable findings
were defects in instruments, not in code.** The classifier that did not exist; the debt row that named
the safest caller instead of the dangerous one; the resource claim that moved between checks when the
plan was reordered; the census figure restated three times and derived never; the gate whose green had
never been shown able to turn red. None of those is visible from a passing run.

**ARC 026 closes with `verify.py` at exit 1 and says so.** The only FAIL is a Gateway that is switched
off, and it is one operator task from being switched on.
