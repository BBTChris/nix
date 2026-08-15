# ARC 032 — R3-B: The Widened Picture, the Closed Cap, and Recovery Reflection

**Module:** Allocator (Core 3) + the Limiter's published seam (Core 2, the write side of the widening)
**Predecessor:** ARC 031 (merged; `origin/main` pushed @ `22cd4fe`)
**Canonical path:** `/home/bbt/nix` (absolute). Do not relocate it.
**Shape:** Phase 0 serial and blocking · Stage 1 three parallel sub-agents · Stage 2 serial
integration (the cap closes here) · Stage 3 convergence · Phase 4 close-out.

**Verifies:** discharges D3.136 (the fail-open bucket cap) by wiring, D3.140 (the interpreter-split
false declaration). Advances the Allocator toward its §4 recovery-reflection objectives.

---

## WHAT CHANGES WITH THIS ARC

ARC 031 built the Allocator's permissive side and found the safety hole underneath it: the
correlation-bucket cap **fails open** because the published `PositionRow` carries no stop distance, so
held positions price as zero risk and buckets admit more than they should. You ruled **Option A** —
put `stop_distance` on the published row, on the same versioned snapshot, never a stop-book read.

This arc executes that ruling and closes the cap. That means widening the frozen seam
(`SEAM_REV 1.0.0 → 1.1.0`), and the widening is the dangerous part: **the one-versioned-row atomicity
identity that ARC 031 proved on the narrow row does not automatically survive the widening.** It is
re-proven here, by the same race harness, on the wider row — not assumed.

Then the Allocator learns to reflect recovery states: a strategy mid-recovery must read as
**in-flight-closing, never normal-and-available**, so it is never counted eligible for capital while
dying (§4). The machinery that *produces* those states — heartbeat detection, orphan recovery,
crash-loop cap, quarantine — is **R5 and does not exist yet**; this arc builds the Allocator's
*reflection* of states published to it, proven against simulated published lifecycle, and says so in
the gates.

---

## §0a — Self-audit, this brief first

*What would have to be true for this step to complete successfully while measuring nothing?*

**Precedent, ARC 031:** three gates were green while the bucket cap could not run — C drove `admit`
with rows it constructed, B drove the port with `None`, and the contradiction between them was never
made until Stage 2 composed them. **A unit that passes on inputs it manufactures is the vacuous case;
the integration that composes real producers is where it dies.** Assume this brief contains at least
one more manufactured-input pass, and at least one hazard stated backwards (four of mine measured
backwards across 027–029; ARC 031 added the fail-open direction as a fifth caught-by-measurement).

## §0b spellings non-binding · §0c withdrawn · §0d HEAD-advanced · §0e committed-artifact-drives-shipped-bytes-red · §0f explicit-status-or-owner, table-rebuilt · §0g owner-names-future-arc · §0h forward-only · §0i mirror-stale-until-proven-fresh (standing)

Resolve any rule named by label to its ledger id before acting (D3.81).

---

## PHASE 0 — Corrections and the widening freeze (SERIAL, BLOCKING)

**0.1 — Re-measure on trunk.** Expect ARC 031's close: `verify.py` `47 passed | 2 failed |
1 cannot measure | 0 skipped | 1 guarded`, exit 1, 51 checks; pytest 1858 + 2 skipped + 2 xfailed;
claims green; CHECK-DEBT 172 derived; binding 49 BOUND / 2 ENR / 0 UNBOUND. **Any delta is a finding.**
Name every FAIL and the guard's owner.

**Note the interpreter caveat from ARC 031 directly:** the baseline differs under system-python vs
venv (`check_observed_resource_claims` FAILs under system-python3 via D3.140, CANNOT_MEASURE under
venv). **State which interpreter each measurement was taken under.** A baseline that doesn't say which
launch mode it used is under-specified now that we know two modes disagree.

**0.2 — D3.140 ruling (architect).** `check_observed_resource_claims` reports a real undeclared claim
(`subprocess:/usr/bin/python3` vs declared `subprocess:python`) under system-python and hides it under
venv — same tree, same commit, only the interpreter changed, and both are documented launch modes.
**[ARCHITECT RULING — revocable]**: (a) apply the one-token fix (`subprocess:python3` added to the
declaration), AND (b) the gate must run under **both documented interpreters** before it may report
PASS — a claim verified under only one of two supported launch modes is unmeasured in the other.
Sub-agent B owns both halves. **§0a:** a "both interpreters" gate that runs the same interpreter twice
measures nothing — prove the two runs use genuinely different interpreters, and that the gate reddens
when a declaration is true under one and false under the other.

**0.3 — Branch protection: report the current state AND draft the replacement rule (do NOT apply it).**
ARC 031's push succeeded under an admin bypass of a *"changes must be made through a pull request"*
rule on `main`. The current shape is the ARC 019 deadlock waiting to recur: PR-only + sole maintainer
+ self-approval-forbidden strands every PR, which is why the workflow became direct-push, which is why
the rule is bypassed — a rule that is always overridden is dishonest state, not protection.

**[ARCHITECT RULING — revocable] Replace human review with green status checks.** The thing that
should guard `main` is not a reviewer the sole maintainer cannot supply — it is `verify.py` green. The
proposed rule: require a PR, **require passing status checks** (`verify.py`, `pytest`, `pre-commit`)
before merge, and **allow self-merge once checks pass**. This is enforceable by a solo maintainer,
cannot deadlock, and puts the check subsystem in the actual merge path instead of running after the
fact.

**Report** the repo's current protection settings, and **draft the exact replacement config** (the
GitHub ruleset / branch-protection JSON or the `gh api` calls that would set it) so the operator can
review and apply it with one action. **Do NOT apply it** — branch protection is outward-facing
GitHub settings and the operator's alone; cc produces the config, the operator clicks. State plainly
whether the current PR-only rule is configured-but-bypassable or not configured, and note that making
status checks *required* only bites once those checks run in CI — if `verify.py`/`pytest` do not run
as GitHub status checks yet, that CI wiring is a named prerequisite (own it as a debt row, do not
pretend the rule protects anything until the checks actually gate the merge).

**0.4 — Freeze the widened seam.** `PositionRow` gains `stop_distance`. Declare it on the seam, bump
the **planned** `SEAM_REV` target to `1.1.0`, and — per ARC 031's own seam-gate finding — **prove the
seam gate reddens on the widening itself**: a renamed or dropped `stop_distance` must redden the gate,
and `MIRRORED_FIELDS` must be pinned to a literal at `SEAM_REV`, not derived from the dataclass (the
derivation is what made ARC 031's first seam gate pass on eight of nine renames).

---

## STAGE 1 — Three parallel sub-agents

### SUB-AGENT A — The widening and the atomicity re-proof (§3, §6.4b, §12.7)

**A1 — The Limiter (sole writer) adds `stop_distance` to the published `PositionRow`.** One more field
under the one writer and one version stamp — never a second table, never a stop-book read (that is the
cross-table skew §6.4 forbids, and it is the rejected Option B). §9 sole-writer holds.

**A2 — The atomicity identity is RE-PROVEN across the wider row.** ARC 031 proved 0 torn reads across
13,924 races on the narrow row, with the falsifier catching 83,971 tears on a broken mirror. **Run
that same harness on the wider row.** The `stop_distance` field must be shown to publish and mirror
atomically *with* balance and the rest — a race that reads a fresh `stop_distance` against a stale
size is a torn read and must be caught. **§0a, the sharp point:** a re-proof that races the old fields
and ignores the new one proves the old row still works and says nothing about the field this arc
added. The new field must be *in* the torn-read assertion.

**A3 — SEAM_REV goes to 1.1.0 only when the wire actually changes** (ARC 031 pinned it at 1.0.0 with
the target planned). Every mirror consumer widens; `MIRRORED_FIELDS` gains `stop_distance` at the
pinned literal. Prove the cross-process codec (`picture.py`) carries the new field both directions —
D3.122's "nothing drives both ends together" is the standing gap and this is where the wider row makes
it concrete.

### SUB-AGENT B — D3.140, the interpreter split (0.2)

**B1 — The token fix and the both-interpreters gate.** Per 0.2: add `subprocess:python3` to
`check_extract_sources`'s declaration; make `check_observed_resource_claims` run under both documented
interpreters before PASS. Prove the two runs use different interpreters (assert the resolved
`sys.executable` paths differ), and that the gate reddens when a declaration is true under one and
false under the other.

**B2 — Sweep every `RESOURCES` declaration for the same latent split.** ARC 031's finding was general:
every declaration is verified against one interpreter per run, so any other with a system-vs-venv
basename split is currently unmeasured in one mode. Enumerate them; report which declarations differ
in truth across the two interpreters. Each one found is a finding, fixed or owned.

**B3 — §0e on the retrofit.** `RESOURCES` is read statically and derived into the plan's disjointness,
so widening a declaration changes the optimizer's input. After B1/B2, re-run `--optimize` and prove
the plan's disjointness is still sound — a declaration widened to pass the observer must not silently
create a false parallel-block claim (the D2.27 class).

### SUB-AGENT C — Recovery-state reflection (§4)

**C1 — The mirror carries lifecycle state, and the Allocator honours it.** The published per-position
row already carries `state` (reserved / pending / open / closing / closed). A strategy mid-recovery
reads as **in-flight-closing**, and the Allocator must treat that as **not eligible for new capital** —
never counted normal-and-available while dying (§4, the reason the table carries per-position lifecycle
state and not just aggregates).

**§0a, the distinction that must not blur:** the Allocator *reflects* recovery; it does not *drive* it.
Flatten, force-deregister, kill, relaunch, quarantine are the Limiter's / supervisor's, and the
supervisor is R5. Prove C reflects a published in-flight-closing state correctly; do NOT build the
machinery that produces it, and say in the gate that the producer is R5.

**C2 — Capital eligibility excludes the dying (§4, §6.6).** Prove by measurement: a strategy in
in-flight-closing state is refused new capital in a contention pass, and a strategy that returns to
flat becomes eligible again. **Hypothesis:** a test where no strategy is ever mid-recovery proves
nothing — drive the transition and prove eligibility changes with it.

**C3 — Score persistence is NOT this arc (§6.6, R5).** The score-across-death rule (a crash writes
nothing to the EMA; quarantine archives not destroys) belongs to the Scoring process, R5. If C touches
the ranking-table READ seam, it reads only; it does not implement persistence. State the boundary.

---

## STAGE 2 — Integration: the cap closes (SERIAL)

**2.1 — The correlation-bucket cap now runs on the COMPLETE bucket.** With `stop_distance` on every
published row, the cap can price held positions: `Σ dollar_risk(open + pending in bucket) + proposed ≤
bucket_cap_pct × balance`, every term real. **This is D3.136's discharge and the payoff of the whole
arc.**

**Prove the fail-open condition is CLOSED, in the direction ARC 031 measured:** an unpriced position
valued at zero made the bucket look emptier and admitted more. Compose the real snapshot with two
held same-bucket positions carrying real stop distances, and prove a third proposal is now capped
against their true summed dollar-risk — and that the *same* scenario admitted the third before the
widening. The before/after is the measurement; the after alone proves nothing.

**§0a:** a cap test that constructs its own `Exposure` rows (ARC 031's three green-while-blind gates)
is the manufactured-input pass. This must run over the mirror consumer's *actual* widened rows, end to
end.

**2.2 — The rationale carries the real cap (§16 U5).** Every proposal's sizing rationale now names the
bucket-cap term as a real binding constraint where it binds, not a placeholder. The Limiter's event log
audits sizing off it.

**2.3 — Nothing the Allocator emits reaches the broker without the Limiter's pass** (§2 authority,
re-proven at the wider seam). The widening must not have opened a write path — the Allocator still
reads the mirror and proposes only.

---

## STAGE 3 — Convergence

**3.1** Regenerate the plan (`--optimize --commit`); report the diff, including B's declaration
changes.
**3.2** Observer in ≥3 orders on a cold cache, each swept twice, **under both documented interpreters**
per D3.140 — the observer sweep itself is now subject to the interpreter-split finding.
**3.3** Census three ways.
**3.4** Binding table rebuilt from measured observations (§0f), not carried forward. BOUND floor 49;
any new check landing UNBOUND or ENR is a finding named with its reason.

---

## PHASE 4 — Close-out

1. `verify.py` on trunk, **stating the interpreter**. Baseline: `check_ibgateway_service` FAIL (tap
   session) + the standing cannot-measure, and D3.140 resolved so `check_observed_resource_claims` is
   no longer interpreter-dependent. A further FAILURE is a finding; any further NON-PASS whose cause is
   not named is a finding. Name every GUARDED check and print its owner verbatim.
2. Full pytest, pre-commit, claims harness, CHECK-DEBT.
3. The §3.4 binding table.
4. `git add -A` before every gate measurement; per D2.24 prove ignore rules resolve per target first;
   per D3.22 use the `gitenv.py` scrub for every subprocess `git` call.
5. Write-back to `/home/bbt/nix`: append to the END of `sessions/SESSION.md`; **overwrite**
   `downloads/RESULTS.md`; `cat` both as the final action; **prove HEAD advanced** (§0d); state the
   absolute canonical path. **If the push ruling from 0.3 is to push, do NOT push unilaterally —
   report and leave it to the operator.**
6. Clean up temp files and any worktrees/branches this arc created.
7. Only then: `**** ARC completed ****`

**Required:**

`===RUN SUMMARY: <Arc name>, Estimated run time: <time>, completes <% this moves the current stage forward (parenthetical)>===`

---

## Explicitly NOT in this arc

The supervisor / heartbeat / orphan-recovery / crash-loop / quarantine machinery (R5 — C reflects
published states, does not produce them) · the Scoring process and score-across-death persistence
(R5) · performance-weighted contention (R5 — FCFS remains the only live policy) · blackout/calendar
pollers (R4) · the strategy FSM (separate module) · the tap session · changing branch protection
(operator/GitHub, 0.3 reports only). Say the deferrals in the verdicts.

---

## Open items returned to the operator / architect

1. **Branch protection** — 0.3 reports the current settings; whether to enforce PR-only on `main` is
   the operator's, outward-facing.
2. **The tap session** — operator task at the console, ~40 min, owed by seventeen arcs. Discharges
   D1.12 reboot capture (ARMED, unfired — do not SSH within 5 min of reboot or the `loginctl`
   precondition invalidates), D1.33, the live rejection taxonomy, feed-lag re-measurement,
   D1.39/D1.40, SPEC-A6's poll-channel lag figure, D1.50, the two Gateway gates' green. Only
   code-independent FAIL.
3. **`registry.json` vs `manifest.json`** — still an open operator ruling, untouched since ARC 030.
4. **v1.4 fold + D3.33** — `SPEC-A8` is the eighth amendment; the v1.4 file holds seven; re-pointing
   every `§x:line` citation below the first insertion is still owed. Architect debt.
5. **After this arc: R4** — blackouts, calendar/margin pollers, the non-stop degrade paths. Then R5
   (Scoring, feedback recovery, observability) lights up performance-weighted contention and the
   recovery machinery C reflected here.
