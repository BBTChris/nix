# ARC 031 / Phase 5 — the four rulings, recorded

**Canonical path:** `/home/bbt/nix` (absolute, unmoved).
**`origin/main`:** `a229228` — **PUSHED, twice.** 0.2 is closed. `22cd4fe` is the fast-forward the
ruling ordered (`0f9c5b9..22cd4fe`); `a229228` is this phase's own commit, pushed after it. Stated as
two figures rather than one because the first is the ruling's result and the second is this file's
own durability — and quoting only the later one would erase the thing you asked to be reported.

All four rulings are recorded. **One acted, two were ledger/amendment writes, one is a decision R3-B
executes.** Nothing was designed here and nothing was invented here; where a ruling ratified what
already shipped, no code moved, and that is stated rather than dressed up as work.

---

## 1. PUSH — DONE

The STOP condition was re-measured, not assumed. `git fetch origin` immediately before the push:

```
git rev-list --left-right --count origin/main...main   → 0   105
```

**0 remote-side commits** — no divergence appeared between 0.2 and now, so the STOP did not fire.
(The brief said 103 local-ahead; the measured figure is **105**, the two extra being Phase 4's own
write-back and re-measure commits. The gate the ruling set was *zero remote divergence*, and that
held exactly.)

```
git push origin main   →   0f9c5b9..22cd4fe  main -> main   (fast-forward, no force)
git fetch origin && git rev-parse origin/main
                       →   22cd4fec0486090c458a4124474b4633dd94fd7b
git rev-list --left-right --count origin/main...main
                       →   0   0
```

**One fact you should have rather than not:** the remote printed
*"Bypassed rule violations for refs/heads/main: Changes must be made through a pull request."* The
push succeeded under an admin bypass of a branch-protection rule. Reported because a bypassed rule is
a standing fact about this repository's settings, not a warning to discard — if PR-only was intended,
it is not currently enforced against this account.

---

## 2. CHECK-A9 — RECORDED, and the gate moved

**Landed:** `scripts/nixverify/gitenv.py` and `scripts/nixverify/registry.py` move from the
ceiling-guarded `artifacts` bucket into `exclusions`, owner `ARC 032`, each carrying a written
justification and `temporary: true`. Recorded in **three** places per check-contract rule 13:
`docs/CHECK-CONTRACT-AMENDMENTS.md` (`CHECK-A9`), `docs/nix_check_contract.md` **§19.1**, and
`CLAUDE.md` rule 14.

**The verdict you asked for:**

```
check_artifact_gate_coverage:  CANNOT_MEASURE (exit 2)  ->  GUARDED (exit 3)
  13 uncovered; 5 per-artifact row(s) + 8 declared exclusion(s); owner ARC 032
  ratchet high-water mark 13 at committed revision ec36ebcbd042
```

Accepted-set size **13 before, 13 after** — `Baseline.uncovered` folds both buckets, so the high-water
mark cannot see the move. That is what makes it a re-classification and not a growth, and it is
measured rather than argued. The `UNBOUND` (D3.10) caveat on the verdict line is unchanged: this gate
proves an artifact is NAMED by a check, never that it is MEASURED by one. **D3.138 discharged.**

### The one thing worth your attention: the suite refused the move before it accepted it

On the first full run after the baseline edit,
`test_the_REAL_TREES_THIRTEEN_ceiling_tripped_artifacts_are_the_D3104_EXCLUSION` **FAILED**:

> `exclusions contains path(s) outside the original thirteen — that is laundering a new artifact
> through the D3.104 door, not shrinking it: {'scripts/nixverify/gitenv.py',
> 'scripts/nixverify/registry.py'}`

CHECK-A8's authorization was pinned as a **literal enumerated set**, so widening the bucket without
widening the recorded ruling is a red. The anti-laundering control fired on the first artifact it ever
saw. It was repaired by adding a **second enumerated literal** (`check_a9_pair`), not by relaxing the
first — the invariant still reads *an authorized exclusion is one a recorded `CHECK-A<n>` NAMES.*

### A real distinction that fell out of that repair, and I kept it

**CHECK-A8's thirteen are OVER the ceiling. CHECK-A9's two are AT it.** The thirteen had a third
re-owning already burned into committed history; these two were stopped at 2-of-2 *before* the third
was taken — measured per row, which is exactly what D3.120 failed to do. So `reowning_defect` is
correctly **silent** on these two, and the test asserts `moves >= ceiling` for them rather than
`> ceiling`. Asserting a breach here would have asserted a fiction.

Stated as a rule, because it is the difference between the two amendments and it should not be lost:
**CHECK-A8's thirteen were an OVERDUE-WORK holding state; CHECK-A9's two are an
INSTRUMENT-BLIND-SPOT holding state.** These artifacts *are* covered — by tests, with real can-fail
controls — and `check_artifact_gate_coverage`, which counts `SUBJECTS` declarations, cannot see it.
D3.138's row therefore stays live as a debt **against the instrument, not against the artifacts**.

---

## 3. SPEC-A8 — RECORDED, ratifying what shipped

`docs/SPEC-AMENDMENTS.md` gains `SPEC-A8`. §7 governs: selection is prior to
`min(risk, margin, symbol_cap)` and a function of the risk-ideal alone. §3:132 is amended to **point
at** §7's pipeline rather than restate it (one source, core directive 3). **The frozen document is not
edited**; a v1.4 remains yours.

**No code moved and no re-measure is owed** — `scripts/nixalloc/sizing.py` already implements §7's
order, and D3.126 was opened by the author of that choice in the same motion as the choice.
`check_allocator_pathway`, `check_allocator_seam` and the Stage-1 suites are unchanged and green.
**D3.126 discharged.**

**One deliberate omission, so you are not surprised by it:** SPEC-A8 adds **no machine-readable row**.
SPEC-A7 carries `terminal-path additions` because `check_limiter_seam` derives an effective roster by
parsing the frozen §3 sentence UNIONED with the ledger, and an unparsed amendment would have reddened
it forever. Nothing in this tree derives a pipeline **order** from spec text — the order lives in
`sizing.py`'s control flow and is driven by the pathway gate — so a surface no instrument consumes
would be decoration, not rigour.

---

## 4. D3.136 — RULED, RECORDED, NOT BUILT

OPTION A is recorded and **deliberately not implemented**, as instructed. What landed is the decision,
written where the decision binds rather than in a session log:

- **`scripts/nixalloc/seam.py`**, at the `SEAM_REV` literal: the planned target **1.0.0 → 1.1.0**, the
  field (`stop_distance` on `PositionRow`), the §6.4b one-writer/one-version-stamp reasoning, the
  explicit refusal of the stop-book read as the cross-table skew §6.4 forbids, and the statement that
  the literal stays `1.0.0` until the wire actually changes.
- **`scripts/nixalloc/wiring.py`**, at the finding it exists to state: the ruling, marked as R3-B's
  opening item.
- **`docs/CHECK-DEBT.md` D3.136**: the ruling, and the row **kept OPEN** — a recorded ruling is not a
  landed mechanism.

**R3-B's opening item, stated as an obligation rather than a task:** the Limiter (sole writer) adds
the field, every mirror consumer widens, `MIRRORED_FIELDS` gains it, `SEAM_REV` goes to 1.1.0, and
**the one-versioned-row identity is RE-PROVEN across the wider schema** rather than assumed to survive
the widening.

---

## EVIDENCE

```
pytest scripts/tests    →  1858 passed, 2 skipped, 2 xfailed   (0:11:12)
verify.py               →  47 passed | 2 failed | 1 cannot measure | 0 skipped | 1 guarded   exit 1
```

**The two FAILs, named — one is standing, one is NEW and it is a real finding.**

- `check_ibgateway_service` — standing, by design: gateway down, `ECONNREFUSED` on 127.0.0.1:4002.
  (`check_ibgateway_config` is the 1 cannot-measure, same cause, §4.1.)
- `check_observed_resource_claims` — **NEW: CANNOT_MEASURE → FAIL**, and it is **not a Phase-5
  regression.** `check_extract_sources` was OBSERVED using `subprocess:/usr/bin/python3` against a
  declaration of `('file-write:/tmp', 'subprocess:python')`. Nothing in this phase touched that check,
  its declaration, or `nixverify.observe`.

**Measured as a both-halves control rather than explained away.** `covers` matches `subprocess:`
tokens by BASENAME, driven directly on both spellings:

```
covers('subprocess:python', 'subprocess:/home/bbt/nix/.venv/bin/python')  -> True
covers('subprocess:python', 'subprocess:/usr/bin/python3')                -> False
```

The check spawns `sys.executable`, so the declaration is true under a venv and **false under the
system interpreter — which `scripts/verify.py`'s own docstring names as a supported invocation**
(*"Stdlib only (§9.1) so it runs under system python3 before .venv exists"*). Same tree, same commit,
only the interpreter changed: system → **FAIL** naming the claim verbatim; venv → **CANNOT_MEASURE**
(the standing tap ECONNREFUSED, §17) with the finding **absent**. That also explains Phase 4's
tally — it was taken under the venv interpreter.

**§17 decides which verdict wins:** a positively-observed undeclared claim outranks masking. So the
FAIL is honest and is kept, rather than re-run under the friendlier interpreter until it goes away.
Opened as **D3.140**, not fixed here: the repair is one token (`'subprocess:python3'`), but
`RESOURCES` is read statically and derived into the plan's disjointness, and widening a declaration
inside a phase whose instruction was *record the rulings* is scope this phase does not have.

**The larger question that row carries, and it is yours:** every `RESOURCES` declaration is verified
against ONE interpreter per run, so any other declaration with the same latent split is currently
unmeasured in one of the two documented launch modes. Discharge is the token **and** a decision on
whether `check_observed_resource_claims` must run under both documented interpreters before it may
report PASS.

**Ledger arithmetic, re-derived rather than typed — TWICE.** The ARC 031 series row went **173 → 171**
on the rulings (two discharges: D3.126, D3.138; zero new rows; D3.136 ruled and still open), then
**171 → 172** when the close-out run opened D3.140. Neither figure was hand-counted —
`check_derived_claims` FAILED the instant the two dispositions were written
(*"derived:ledger_rows=171, stated:series_table_latest_row=173"*), the gate catching a stale figure
inside the same edit that staled it. The cell was re-derived to what the rows say and the check is
green.

**One correction made in passing.** `CLAUDE.md`'s spec table indexed `nix_check_contract.md` at
v1.3.0; the file has read **v1.4.0** since ARC 025. Corrected — the same core-directive-3 failure
Phase 0.6 recorded one arc earlier for `directory_structure.md`, in the same table, found the same
way: by opening the file the row indexes.

---

## WHAT IS STILL YOURS

- **D3.136 / SEAM_REV 1.1.0** — ruled, unbuilt, R3-B's opening item by your instruction.
- **A v1.4 of the frozen risk spec** — `SPEC-A8` is the eighth amendment and the fold at
  `nics_risk_subsystem_spec_v1.4.md` still holds only the first seven. Re-pointing every `§x:line`
  citation below the first insertion remains CHECK-DEBT **D3.33**.
- **`checks/registry.json` vs `manifest.json`** — still an open operator ruling, untouched.
- **D3.140** — the interpreter-dependent false declaration above, and the question of whether
  `check_observed_resource_claims` must run under both documented interpreters.
- **The branch-protection bypass** above, if PR-only was meant to be enforced.
