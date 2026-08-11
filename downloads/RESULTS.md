# ARC 020 — RESULTS
### Closing the Five · session lifecycle · mirror ordering · protective-path observability
**2026-08-11 · 2 sub-agents, deliberately not 3 · every number below is pasted command output, not transcribed**

---

## 0. The answer to the arc's primary question

**All five defects are closed, the two rulings are implemented and recorded as pending
amendments, and the coverage scheme now carries its own limitation in its name.
`verify.py` is NOT exit 0, and the reason is a dead IB Gateway session, not code.**

Five `strict=True` xfails held ARC 019's Tier-3 findings open. All five are gone, each removed
in the same motion as the fix it marked. The remaining count is **derived, not asserted**:

```
$ grep -rn '@pytest.mark.xfail' scripts/
scripts/tests/test_broker_tier3.py:22:  1. `@pytest.mark.xfail(strict=True)` — the spec DOES determine the outcome and the
```

That single hit is prose inside a module docstring describing the three-encoding convention.
It is not a marker. pytest reports no `xfailed` and no `xpassed`.

---

## 1. The five commands, raw

```
$ .venv/bin/python scripts/verify.py
  [ok]   check_python_runtime
  [ok]   check_venv
  [ok]   check_node_identity
  [ok]   check_python_deps
  [??]   check_ibgateway_config no API endpoint at 127.0.0.1:4002 — ConnectionRefusedError: [Errno 111] Connection refused. Gateway down or not logged in; that is not a misconfiguration (§4.1)
  [FAIL] check_ibgateway_service 127.0.0.1:4002 (nix-ibgateway.service) - 127.0.0.1:4002 (nix-ibgateway.service): API endpoint not reachable — unreachable: ConnectionRefusedError: [Errno 111] Connection refused
  [ok]   check_order_path_bans
  [ok]   check_spec_citations
  [ok]   check_hook_suite
  [ok]   check_derived_claims

  8 passed | 1 failed | 1 cannot measure | 0 skipped          exit 1
exit=1
```

```
$ .venv/bin/python -m pytest scripts/tests -q
........................................................................ [ 29%]
........................................................................ [ 59%]
........................................................................ [ 89%]
..........................                                               [100%]
242 passed in 17.55s
```

```
$ .venv/bin/pre-commit run --all-files
ruff check...............................................................Passed
ruff format..............................................................Passed
pylint...................................................................Passed
mypy.....................................................................Passed
bandit (production)......................................................Passed
bandit (tests)...........................................................Passed
complexipy...............................................................Passed
Stage 3 — runtime pass...................................................Passed
```

```
$ .venv/bin/python checks/check_derived_claims.py
pass: 10/10 claim(s) compared — registered_check_count=10 [derived:checks_glob=10, derived:registry_json=10; 0 restatement(s) found] | pytest_collected_tests=242 [derived:pytest_collector=242, derived:source_ast=242; 0 restatement(s) found] | pinned_dependency_count=2 [derived:pins_json=2, derived:print_pins_cli=2; 0 restatement(s) found] | check_debt_open_items=40 [derived:ledger_rows=40, stated:series_table_latest_row=40; 0 restatement(s) found] | spec_2a_broker_order_elements=16 [derived:frozen_spec_identifiers=16, stated:seam_roster=16; 0 restatement(s) found] | arc014_broker_order_classification=16 [derived:findings_covering_roster=16, derived:grade_tally_sum=16, derived:spec_roster_size=16; 0 restatement(s) found] | seam_declared_elements=23 [derived:spec_plus_flagged_additions=23, stated:seam_code_total=23; 0 restatement(s) found] | order_path_scope_files=5 [derived:gate_derived_scope=5, stated:stated_anchor_dirs=5; 0 restatement(s) found] | broker_order_element_coverage_v1=56 [derived:spec_denominator=56, stated:seam_denominator=56; 0 restatement(s) found] | broker_order_open_debt_rows=11 [derived:spec_roster_vocabulary=11, stated:seam_roster_vocabulary=11; 0 restatement(s) found]
exit=0
```

```
$ .venv/bin/python checks/check_spec_citations.py
pass: scanned 1843 §-citation(s) across the tree against 5 indexed document(s) of 12 in docs/; attributed 230, unattributed 1524, cited-but-unindexable 89; 8 line coordinate(s) range-checked; governed roots ['checks', 'scripts/broker', 'docs/CHECK-DEBT.md'] over 17 citing file(s); resolved into ['debug.md', 'elements_v2.md', 'nics_risk_subsystem_spec_v1.3.md', 'nix_check_contract.md', 'nix_strategy_contract_v1.1.md']; SURVEY .superpowers/sdd/2026-08-09-verify-py-v2/final-fix-report.md:390 §7 -> §7 is not a heading in elements_v2.md (that document's labels include: 1, 1.1, 1.1a, 1.2, 1.3, 2, 3, 4…); SURVEY .superpowers/sdd/2026-08-09-verify-py-v2/task-13-report.md:112 §11 -> §11 is not a heading in elements_v2.md (that document's labels include: 1, 1.1, 1.1a, 1.2, 1.3, 2, 3, 4…); SURVEY CLAUDE-CHANGELOG.md:12 §13 -> §13 is not a heading in debug.md (that document's labels include: 0, 1, 10, 11, 2, 2.1, 2.2, 3, 3.1, 3.2, 3.3, 3.4…); SURVEY CLAUDE-CHANGELOG.md:13 §12A -> §12A is not a heading in debug.md (that document's labels include: 0, 1, 10, 11, 2, 2.1, 2.2, 3, 3.1, 3.2, 3.3, 3.4…); SURVEY CLAUDE-CHANGELOG.md:13 §12.10 -> §12.10 is not a heading in debug.md (that document's labels include: 0, 1, 10, 11, 2, 2.1, 2.2, 3, 3.1, 3.2, 3.3, 3.4…); SURVEY CLAUDE-CHANGELOG.md:13 §9A -> §9A is not a heading in debug.md (that document's labels include: 0, 1, 10, 11, 2, 2.1, 2.2, 3, 3.1, 3.2, 3.3, 3.4…); REVIEWED SUPPRESSION checks/check_order_path_bans.py:40 §2.1 — THE TEXT'S SUBJECT IS THE PHANTOM ITSELF. This is ARC 018's CITATION CORRECTION block, whose whole content is the finding that the frozen spec has no §2.1 — it names the document and then says, in the next sentence, that the section does not exist in it. Deleting the citation would delete the record of the correction, and the record is what stops the phantom being re-derived by a future arc reading the ban and wondering what authorises it. The three REAL anchors are stated in the same docstring and all three resolve under this gate: §2A:71, §4:241, §12A:830.; SURVEY docs/nix_check_contract.md:10 §13 -> §13 is not a heading in elements_v2.md (that document's labels include: 1, 1.1, 1.1a, 1.2, 1.3, 2, 3, 4…); SURVEY docs/nix_check_contract.md:549 §11 -> §11 is not a heading in elements_v2.md (that document's labels include: 1, 1.1, 1.1a, 1.2, 1.3, 2, 3, 4…); SURVEY downloads/RESULTS.md:331 §99.9 -> §99.9 is not a heading in nics_risk_subsystem_spec_v1.3.md (that document's labels include: 1, 10, 11, 12, 12.1, 12.10, 12.11, 12.2, 12.3, 12.4, 12.5, 12.6…); SURVEY downloads/RESULTS.md:331 §99.9 -> §99.9 is not a heading in nics_risk_subsystem_spec_v1.3.md (that document's labels include: 1, 10, 11, 12, 12.1, 12.10, 12.11, 12.2, 12.3, 12.4, 12.5, 12.6…); SURVEY downloads/RESULTS.md:332 §12A:99999 -> line coordinate [99999] falls outside §12A's span 797-842 in nics_risk_subsystem_spec_v1.3.md; SURVEY downloads/arc_011_gateway_persistence.md:40 §1.4 -> §1.4 is not a heading in elements_v2.md (that document's labels include: 1, 1.1, 1.1a, 1.2, 1.3, 2, 3, 4…); SURVEY install.sh:286 §9.5 -> §9.5 is not a heading in elements_v2.md (that document's labels include: 1, 1.1, 1.1a, 1.2, 1.3, 2, 3, 4…); SURVEY install.sh:286 §13 -> §13 is not a heading in elements_v2.md (that document's labels include: 1, 1.1, 1.1a, 1.2, 1.3, 2, 3, 4…); SURVEY scripts/nixverify/__init__.py:1 §9.1 -> §9.1 is not a heading in nix_check_contract.md (that document's labels include: 1, 10, 10.1, 11, 12, 13, 13.1, 14, 15, 15.1, 15.2, 15.3…); SURVEY scripts/tests/test_broker_tier3.py:34 §0a -> §0a is not a heading in nics_risk_subsystem_spec_v1.3.md (that document's labels include: 1, 10, 11, 12, 12.1, 12.10, 12.11, 12.2, 12.3, 12.4, 12.5, 12.6…); SURVEY scripts/tests/test_broker_tier3.py:43 §14 -> §14 is not a heading in debug.md (that document's labels include: 0, 1, 10, 11, 2, 2.1, 2.2, 3, 3.1, 3.2, 3.3, 3.4…); SURVEY scripts/tests/test_loader.py:1 §9.3 -> §9.3 is not a heading in nix_check_contract.md (that document's labels include: 1, 10, 10.1, 11, 12, 13, 13.1, 14, 15, 15.1, 15.2, 15.3…); SURVEY scripts/tests/test_loader.py:1 §9.4 -> §9.4 is not a heading in nix_check_contract.md (that document's labels include: 1, 10, 10.1, 11, 12, 13, 13.1, 14, 15, 15.1, 15.2, 15.3…); SURVEY scripts/tests/test_systemd_units.py:1 §9.5 -> §9.5 is not a heading in nix_check_contract.md (that document's labels include: 1, 10, 10.1, 11, 12, 13, 13.1, 14, 15, 15.1, 15.2, 15.3…); SURVEY sessions/SESSION.md:509 §1.4 -> §1.4 is not a heading in elements_v2.md (that document's labels include: 1, 1.1, 1.1a, 1.2, 1.3, 2, 3, 4…); SURVEY sessions/SESSION.md:511 §10 -> §10 is not a heading in elements_v2.md (that document's labels include: 1, 1.1, 1.1a, 1.2, 1.3, 2, 3, 4…)
exit=0
```

**Merged and confirmed on `main`:** `d377ed6 Merge pull request #14 from BBTChris/arc-020-integration`

---

## 2. Why `verify.py` is exit 1, stated plainly rather than explained away

`check_ibgateway_service` fails and `check_ibgateway_config` cannot measure. Both have one
cause, and it is not this arc's code:

```
nix-ibgateway.service: inactive (dead) since Tue 2026-08-11 03:00:04 UTC
Duration: 16h 4min 860ms
ExecStart=/home/bbt/ibgateway/ibgateway (code=exited, status=0/SUCCESS)
ss -ltnp | grep 4002  ->  NOTHING LISTENING
```

`status=0/SUCCESS` after a 16-hour run is IBKR's **daily session expiry**, not a crash. The
Gateway needs an IB Key tap to log back in. `nix-xvfb.service` is still up.

**The §0b baseline for this arc was measured BEFORE that expiry and was `10 passed | 0 failed
| exit 0`.** The degradation happened mid-arc, at 03:00:04 UTC, while sub-agents were running.
Sub-agent C observed the degraded state and reported it as "identical to the parent repo's
baseline" — that attribution is wrong and is corrected here: it is a mid-arc environment
change, not a pre-existing condition.

**This makes §8's tap ask blocking rather than optional.** `verify.py` cannot reach exit 0
until the Gateway is logged back in.

---

## 3. Counts — every one derived, none typed

| quantity | §0b baseline | now | source |
|---|---|---|---|
| pytest | 233 passed, 5 xfailed | **242 passed, 0 xfailed** | pasted above |
| remaining `strict=True` xfails | 5 | **0** | `grep`, pasted above |
| pre-commit hooks | 8/8 | **8/8** | pasted above |
| derived claims | 9/9 | **10/10** | `check_derived_claims` |
| CHECK-DEBT open rows | 41 | **40** | `derived:ledger_rows` |
| broker-order depth rows | 12 (registered this arc) | **11** | `broker_order_open_debt_rows` |
| verify.py | 10 passed, exit 0 | 8 passed, 1 failed, 1 cannot measure | Gateway expiry |

Depth claim selection, printed by the probe itself:

```
D1.17, D1.19, D1.20, D1.22, D1.27, D1.28, D1.29, D1.30, D1.31, D2.14, D3.8
```

---

## 4. Element coverage did not move, and that is the point

`broker_order_element_coverage_v1` = **56**, unchanged. **This arc added no §2A elements — it
repaired existing ones.** The brief predicted exactly this, and it is the scheme limitation
ARC 019's §10 raised: an arc that closed four defects, discovered five more, corrected a
banked performance figure fivefold and produced the module's first Tier-3 traversal registered
as zero movement.

The rename is the correction. `broker_order_percent_sec2a_element_v1` →
**`broker_order_element_coverage_v1`**, with the "percent moved" framing dropped from the
harness. The name now carries the limitation. The scheme identifier and the cross-derivation
are unchanged — a rename plus a framing correction, not a new measurement.

**No confidence dimension was invented.** A per-element confidence score is a hand-maintained
rubric, which is the anchor the harness exists to remove.

---

## 5. Percent moved — level and delta kept distinguishable

**Element coverage (breadth).** LEVEL **56** (`broker_order_element_coverage_v1`, derived from
the frozen spec denominator on one side and the seam roster on the other). DELTA **0**.
Derived from §2A element identifiers versus the seam's declared roster. It measures breadth and
is blind to depth; that blindness is now in its name.

**Depth (broker-order).** LEVEL **11** open ledger rows naming an order-path artefact. DELTA
**−1** (12 → 11). Derived from the ledger's own bold-span rule intersected with a scoping
vocabulary read independently from the frozen spec and from `broker_seam.py`'s AST.
**Deliberately not a percent** — the denominator would be "how much do we trust this module",
which is unknowable. It is a **floor, never a fraction**.

**Apparatus.** Registered claims 9 → **10**; registered checks **10**, unchanged — a claim is
not a check. CHECK-DEBT 41 → **40**.

**Whole project.** The honest statement is that this arc moved **correctness of one module**,
not project scope. No new §2A elements, no new subsystem, no vendor integration, no Limiter.
Against the current stage the brief estimated 12–14%; the defensible claim is that the five
landmines R2 would have hit are cleared, which is a precondition for R2 rather than progress
through it. **Element coverage was expected not to move and did not; that is stated rather
than replaced with a number that does.**

---

## 6. The two rulings — implemented, recorded, NOT spec

The frozen spec is **not edited**. Both rulings land as **declared Nix additions** following the
`feed_lag()` / `UP_DATA_LOSS` precedent, plus `docs/SPEC-AMENDMENTS.md`, which carries for each:
the verbatim ruling text, the section of `nics_risk_subsystem_spec_v1.3.md` that would have to
say it, the arc that implemented it, and the fact that it is **pending a v1.4 the architect
owns**. Each entry names its origin as an **operator ruling issued in ARC 020**, never as spec
text — the D2.17 attribution rule, applied at the point the record was created.

**Amendment 1 — ownership over elapsed time** (§4 "Boot / known-state discipline"). Recorded
with its soundness condition **as a condition**: it holds only while D1.24's session-boundary
clearing holds, and regresses with it. They are one property, not two.

**Amendment 2 — bounded flatten idempotency** (§4 "Exits (dual authority)"). Window =
`flatten_idempotency_window_ms` = **2000 ms**, derived as `= PENDING_ACK_TIMEOUT_MS`
(`nics_risk_subsystem_spec_v1.3.md` §12A:830, "~1–2s", upper end taken). The reasoning is the
handoff: the window suppresses a repeat protective flatten for exactly as long as the Limiter
is still waiting for the first flatten's ack, and at that instant §4's pending-timeout
machinery takes the question over. Suppressing past it would let the adapter refuse to protect
while nothing else was protecting either — which D1.22 proves is a real state. **Not a bare
literal**: it lives in `risks/broker_order.config.json` with four cross-knob boot-validation
rules, all can-fail demonstrated, and a missing or invalid config raises rather than defaulting.

---

## 7. The in-flight-at-session-drop answer

The case the brief singled out as owing a real answer. Stated as a rule:

> An order **non-terminal when the session ended** is neither deleted nor kept. Its per-order
> state is released and a `_Tombstone` retained holding `{client_order_id, last_known_state,
> cumulative_qty, session_seq}`. `query_order_status` returns `state="indeterminate"`,
> `terminal=False`, and the `cumulative_qty` floor this adapter observed. The id is **neither
> re-mintable nor cancellable** while the answer is outstanding.

That is **§4:241's own third outcome** — "Resolves confirmed / cancelled / **indeterminate**" —
which D1.24 recorded this adapter could not reach at all, because the only branch able to
express uncertainty was reachable only when the trade was absent. It is not a lie in either
direction: not `working`, which is a claim about a venue we can no longer see; not `unknown`,
which is this adapter's spelling of "never heard of it" and would invite the Limiter to
re-mint the id of an order that may still be live at the venue.

Clearing a closed order and clearing a live one are now genuinely different operations.

---

## 8. Findings — reported, not reconciled

**In the brief.**
1. **"ARC 017's phantom-fill traversal still passes" is not satisfiable alongside the ruling.**
   That traversal drives a *genuinely owned* live order's execution and asserts it is refused;
   ownership admission inverts it. The assertions were inverted in the same motion with the
   reasoning recorded at the site. The traversal that drives **true replayed history** is
   untouched and green — and that is the one whose survival the criterion was reaching for.
2. **A3's instruction was necessary but not sufficient.** "Assert the invariant once across all
   emission sites, reusing ARC 019's form" cannot see a publish scheduled in session N landing
   in session N+1 while N+1 is up. The first can-fail proved this **by not perturbing**.
3. **C1's "wherever it appears in the ledger" is a no-op** — `docs/CHECK-DEBT.md` contains zero
   occurrences of "percent" and zero `%`. The framing never lived there.
4. **C1 versus §9.5.** C1 retires "percent moved"; §9.5 then asks for "percent moved" by name.
   §5 above writes level and delta as coverage figures instead.
5. **§6 named no owner.** `docs/SPEC-AMENDMENTS.md` was in neither sub-agent's write scope; the
   parent took it explicitly.
6. **The brief's own §-anchors were audited and are clean** — §2A:68, §2A:71, §4:208, §4:217,
   §4:222, §4:241, §12A:830 all verify on disk. Unlike its two predecessors, this brief carried
   no phantom citation.

**In the environment.**
7. **`core.bare` is not unset.** It reads `false`, from `.git/config` line 5; global unset. The
   ARC 019 hazard value was `true` and it is **not** `true`, but "unset" is not what is on disk —
   `bare = false` is the line stock `git init` writes. Phase 4 asserted `!= true`.
8. **ARC 019 was not an ancestor of `main` until `git fetch`.** Local `main` was stale at the
   ARC 018 merge. The reported value held against `origin/main`; the local ref was behind.
9. **A worktree dispatch defect that hits every sub-agent.** `state/` is gitignored (D1.16), so a
   fresh linked worktree has no `state/node_identity.json` and no `.venv`, which fails
   `check_node_identity` and blocks the Stage 3 runtime gate at commit time. Both sub-agents hit
   it independently and both resolved it with gitignored symlinks rather than bypassing hooks.

**In the ledger.**
10. **D1.27's disposition was stale** ("architect, not ARC 020") — written before the operator
    ruled. Re-disposed, still open.
11. **D3.8's row assigned work this arc's own brief forbids.** Ledger and brief were both live
    and contradictory. Rule of record written into the row: **a ledger row may record an
    expectation but may not create an assignment.**

**In this arc's own work — the two that matter most.**
12. **A3's first plant did not perturb.** Two mechanisms guarded one observable and the weaker
    sufficed for everything being driven. Failure mode #1, about a gate built in this arc.
    Reported by the sub-agent against itself, and a traversal added for the sequence only the
    stronger mechanism survives.
13. **Two gates caught the parent's own Phase 4 edits.** D1.30 and D1.31 as first written were
    **invisible** to the depth claim registered one file over — the scoping rule reads prose and
    neither row named a module basename or a roster identifier on a word boundary. That is C's
    own named ambiguity (c), biting the first rows written after the rule landed. Then
    `check_spec_citations` reddened on a `§12A` written too near a `debug.md` mention and
    resolved by proximity to the wrong document — D2.18 exactly. Both repaired the D2.17 way, by
    naming the artefact and naming the document.

---

## 9. What was deliberately NOT built

The Limiter and every consumer · D1.22's bounding policy · the intent-versus-outcome reconciler ·
D1.19 · D1.20's consumer half · D2.14 residuals · D2.15 · D3.8 · a v1.4 of the frozen spec ·
a per-hook canary (**D3.7 refused, with the cost measured rather than estimated**) · any
eleventh gate.

**D3.7's refusal is a product, not an absence.** The runtime-cost argument was tested and
**failed** — 1.55 s against `check_hook_suite`'s ~1.5 s, so cheapness is settled in the canary's
favour and is not why it was refused. It was refused because two generic fixtures caught only
five of seven pinned hooks, so the fixture set is a hand-authored rubric of believed tool
behaviour; because `ruff-check --fix` **edited the planted evidence mid-run**; because an
in-tree fixture needs an `exclude:` indistinguishable from failure mode #14; and because a
throwaway proves the tool under a *reconstructed* configuration. Its main product is a
dependency nobody had recorded: **D3.7 is downstream of D2.4**, because the missing piece is the
bump-time trigger, not the canary.

---

## 10. Consumer obligations recorded for R2

1. The §4 pending-timeout state machine and its `query_order_status` resolution, **including the
   new `indeterminate` branch**, whose correct response is §4's flatten-on-uncertainty, and after
   which the neutral id becomes re-mintable.
2. Any consumer of `FlattenAttempt`: `suppressed` means *a protective action was requested and
   deliberately not sent* — **not** that it was sent. `is_silent_no_op` together with
   `mirror_stale` is the flatten-on-uncertainty trigger.
3. Re-invocation after a flatten window expires. **The adapter never auto-refires**; expiry
   escalates.
4. A bounded-queue policy over `send_backlog()`.
5. `_mirror_stale`'s consumer obligations, unchanged and re-confirmed.
6. **D1.29** — decide whether the seam distinguishes "not reported" from "zero" on `Balance`.

---

## 11. Stage 0 caveat, in the words the brief requires

**Nothing measured on IBKR at Stage 0 means anything about latency, fill realism, slippage, or
strategy performance — the feed is delayed ~600 s.**

---

## 12. Phase 5 — the tap bundle, still owed

Not discharged. `nix-reboot-capture.service` exists at `scripts/nix-reboot-capture.service`
with `scripts/d1_12_reboot_capture.py` beside it, **built ARC 019 and still not armed**. Arming
needs root; the reboot is the operator's call.

**The sequence is D1.12 first, before anyone touches the console** — the capture's value is that
it records evidence nobody was there (`who`, `loginctl`, uptime against a 300 s ceiling), and a
console touch first wastes the tap. Then the rejection-taxonomy confirmation owed since ARC 018
(`clientId=905`, unaffordable size, `reject_category=INSUFFICIENT_MARGIN` with `reason` still
carrying the `201` text), then anything A2/A4/A6 can corroborate live.

**One thing changed in this arc's favour:** the Gateway has already expired on its own, so a
reboot no longer costs a live session. The tap that logs it back in is owed regardless, and
D1.12 can now be taken in front of it for free.

**Known-red, named:** R1-A and D1.12 remain owed. `verify.py` is exit 1 until the tap.
