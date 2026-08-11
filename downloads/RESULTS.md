# ARC 023 — RESULTS

**Binding · the four product defects · per-channel freshness**
Stage 1 (A ‖ B) parallel, then Stage 2 serial. Merged and confirmed on `origin/main`. 2026-08-11.

---

## 0. The headline — D3.10's discrimination gap closed, first time in three arcs

**Both of ARC 021's real plants are now CAUGHT, with the site named.**

Throwaway tree, pristine control, both restores byte-identical by sha256, `__pycache__` purged between
every step, verdict-by-verdict never in aggregate (§7.7).

| | control | plant 1 · sentinel write deleted | plant 2 · requested-for-granted |
|---|---|---|---|
| ARC 021 | — | gate passed | gate passed |
| ARC 022 | exit 2 | exit 2 | exit 2 |
| **ARC 023** | **exit 0** | **exit 1 — CAUGHT** | **exit 1 — CAUGHT** |

Sites named: plant 1 at `granted_mode(GATE-PROBE-A)@re-subscribed-after-1` — *"a RE-SUBSCRIPTION
inherited the previous subscription's grant"*; plant 2 at `granted_mode()@subscribed-ungranted` — *"the
adapter-wide answer names a mode while nothing has been granted"*.

`check_datafeed_bar_seal` stayed exit 0 on both plants. **That is correct, not a miss** — these are
granted-mode defects, and reddening a gate outside its subject is doctrine B.4's forbidden direction.
The brief's "both gates must FAIL" is read as **both plants** must fail and name the site; requiring the
seal gate to redden on a grant defect would demand the failure mode B.4 forbids. Stated as an
interpretation because the phrasing admits both readings.

**Not tuned to the acceptance test.** Four further plants, each restored byte-identical: a defect
*neither* ARC 021 plant is (the grant callback inferring from the request) → caught; the mapping
collapsing sentinel onto real-time → caught via arm B0; an enum aliasing `UNKNOWN = 1` → caught via A1;
and **D3.16's own shape re-planted** (`granted_mode` given a required positional) → **exit 2
CANNOT_MEASURE** naming the `TypeError`, with `including 'granted_mode': False`.

---

## 1. Phase 0 — three reconciliations, two of which found errors ARC 022 shipped

### 0.1 The contradiction resolved — the **delta** was wrong, not the level
Re-derived by applying today's rule to all three trees rather than re-reading the report:

```
ARC 020 = 11   ARC 021 = 13   ARC 022 = 13
```

Level 13 is correct. **ARC 022's Δ is 0, not +2** — the "+2 real" was annotating the ARC 020→ARC 021
transition while sitting in the ARC 022 column. A real level and a real delta paired to the wrong
interval: §7.4's stale anchor in its subtlest form, because both halves are individually true.

### 0.2 Opened and closed with row IDs — and a worse error underneath
Derived with the harness's own `_DISCHARGED` predicate, reproducing its 53 and 62 exactly:

- **Opened (10):** D1.39, D1.40, D2.23, D2.24, D3.11, D3.12, D3.13, D3.14, D3.15, D3.16
- **Closed (1):** D2.21 — D2.19 was *narrowed*, not discharged
- 53 + 10 − 1 = **62** ✓

The 5-vs-4 discrepancy resolves as **six** subjects, four new rows — and exposes that the census tally
ARC 022 shipped, **7 BOUND / 5 UNBOUND**, is wrong. The ledger's own verdict column gives **6 / 6**.
Sub-agent C reported it; the parent propagated it into RESULTS, SESSION and the series row without
re-deriving. Corrected in both places it was stated, original preserved per directive 6.

### 0.3 Security — positive confirmation, and it clears

The blob exists: `daed7b5f`, **19 bytes**, content exactly `/home/bbt/nix/state`, hexdumped in full. A
path string, not credential contents — but confirmed, not reasoned:

| probe | result |
|---|---|
| reachable from any of **56** refs | **0** |
| present in any of **139** commits | **0** |
| `state/` or `.venv/` paths on **25** remote refs incl. `origin/main` | **0** |
| mode-`120000` entries in reachable history, two independent methods | **0 / 0** |

**Nothing reached pushed history.** Clone transfers only reachable objects, so there is no exposure. No
`.venv` blob was ever hashed at all.

**Correcting ARC 022's own report:** it said *"`git fsck` clean but for two dangling blobs."* That was
`git fsck | tail -2` read as a total. The real figure is **120 dangling objects**, and neither blob
named was the symlink — so the symlink was never actually seen last arc.

---

## 2. Stage 1 A — the four product defects

**F21 — AMENDMENT 6** (not 5; ARC 022 already used 5 for D1.38 — a **brief/tree contradiction**, flagged
in the file, and the architect owns whether to renumber ARC 022's instead).

`FeedChannel`, `ChannelState` (FRESH/STALE/**CANNOT_MEASURE**), `ChannelFreshness`, `FreshnessReport` —
which **deliberately carries no `is_fresh`, `is_stale` or `state`**. The absence is the enforcement and a
test asserts it by name. `FeedState` was **not** extended: §2A:92's vocabulary is frozen and a fourth
member would silently redefine a locked event.

**The poll channel's lag was not invented, and the refusal is structural.** `Stage0LagRecord` carries a
channel; `_require_channel` raises if a record is installed on a slot it did not measure, with a plant
proving the refusal fires. **A refused the architect's spelling under §0b**: grade and known-red marker
implemented as directed, but a *default figure* refused — the tick constant measures the tick stream,
and ARC 010's 624 s measures `reqHistoricalTicks` on a different call and a different quantity, which
that module's own docstring already warns against merging.

**Consequence stated, not hidden:** a poll-only symbol **still summarises STALE today**. What changed is
that the report says `cannot_measure=['tick','poll']` rather than `stale=[…]`, so an unanswerable
question is distinguishable from a failed feed — which is the whole of F21. Both directions proven:
inject a VENDOR_DECLARED poll figure and the channel reads FRESH, summary UP.

**F17 — both of the architect's numbers survived measurement.**

| rate | n in 60 s | time to floor 5 | catches the 600→900 s degradation? |
|---|---|---|---|
| 18 ticks / 40 s (ARC 013, **measured**) | **27.0** | 11.1 s | **after 1 packet (2.2 s)** |
| session-wide mean (the F17 defect) | — | — | **never** |

Time-not-count confirmed: a 100-sample window spans **222 s** at ARC 013's rate and **0.000028 s** at
this box's measured ingest ceiling. The invariant *"memory bounded regardless of rate"* needed more than
the stated spelling — a pure 60 s window at the ceiling retains **20.5 GB** — so a **derived** count cap
(1 MiB ÷ measured 96 B/sample = **10,922**) is the backstop, and which bound applied is observable.

**F13** — a **publication debt**, not a re-derivation. The key is owed in the same breath as the seal and
before the sink is called; the retry re-publishes **the same sealed object**, asserted by **identity, not
equality**, so a re-derivation cannot pass and D1.14 is intact. `ok=True` over a lost bar is now
unconstructible. **F12** — the poll path has its own map of its own type; `unsubscribe` on a
never-subscribed symbol puts nothing on the wire, with a control in the same test proving unsubscribe
still cancels.

**A gate reddened on correct code mid-flight and the repair went to the code, not the gate.**

---

## 3. Stage 1 B — dispositions, the sweep, and the harness arm

Two gates bound by **re-framing the subject** rather than perturbing a shared resource: `check_venv`
(a venv of its own — the row's own stated discharge condition met literally) and `check_node_identity`
(it measures **divergence**, so perturbing the stored side against the real live UUID yields the
observable a swapped disk yields). The latter produced a **third verdict never before shown for this
gate**: `findmnt`/`blkid` off `PATH` → cannot_measure, not exit 1.

**`check_python_runtime` REFUSED**, and the refusal is stronger than a defer: `MINIMUM` equals the only
interpreter version on the box, so the gate is **unfailable** against this inventory. The obvious plant
was refused under §0b as the ARC 022 monkeypatch re-spelled as a file edit.

**A new RULE OF RECORD: a compensating control must be AIMED before it is checked for existence.** D3.15
showed arm 4 measured nothing while two rows cited it. The sweep asked the prior question and found arm
4 was **mis-aimed** for D2.21 — that row's subject is guard polarity in the source; arm 4 drives published
types' immutability, a path an inverted guard never reaches. **Confirmed after Stage 2 repaired it.** The
corollary is recorded too: D2.20's control *is* aimed. The rule disqualifies mis-aimed controls, not controls.

**B refused the reopen instruction and it was endorsed.** D2.21's *discharge* rests on the `_absent_proofs`
strict-subset repair and its eight-spelling table, not on arm 4; reopening would assert an unrepaired
residual the measurement says is repaired.

**The claims harness can now see a demonstration go untrue.** Registered in the state it is actually in,
so it reddens in **both** directions — and **it fired during Stage 2 before the ledger was touched**:
*"registered as 'does-not-perform'; the re-execution observed 'performs'."*

---

## 4. Stage 2 — the rebuild

**D3.16's root cause was a citation used to justify its own inverse.** `_observers()` discovered subjects
by RETURN ANNOTATION, citing *"`debug.md` §7.4's requirement applied to a scope."* §7.4 is about never
anchoring to something that **moves** — and here the roster was the stable contract while the annotation
was the moving thing. It returned `['granted_mode', 'resolve_granted_mode']`, the second a module-level
helper lifted in ARC 021 Phase 4 *precisely so arm B1 could drive it*; its three green legs plus
`legs = max(...)` masked the accessor's three `AttributeError`s for two arcs.

Now: discovery from the **settled roster**; the helper survives as arm B0 contributing **no leg**; the
subject is a **constructed adapter driven through a lifecycle**, not a call with an integer; and
non-vacuity is asserted **every run** under `sys.settrace` — with arm C deliberately outside the trace,
because it would have satisfied the assertion without the lifecycle running at all.

**Arm 4 repaired (D3.15).** The union fix alone was a half-repair and the measurement caught it: `FeedLag`
moved from `not synthesisable` to `not constructible`, because its `__post_init__` correctly refuses
`observed_lag_s` beside a non-`OBSERVED` provenance. Arm 4 drove **zero** published types before and
drives **two** now.

**Arm 3's one-hop repair was BUILT, MEASURED and REFUSED.** It removed a false positive by admitting a
false negative: the plant arm 3 exists to fail **stopped failing**, because `_ingest_history` also calls
`_maybe_revise`, so the hop finds `on_bar_revision` and goes green over a swallowed publication. Reverted;
opened as **D3.18** with both measurements as its acceptance test.

---

## 5. Reinstatement plants — each caught, catching channel named

| plant | gate | pytest |
|---|---|---|
| F12 · polling manufactures a subscription | no catch | **2 failed** |
| F13 · publication debt discarded | no catch | **18 failed** |
| F17 · windowed mean → session mean | no catch | **5 failed** |
| F21 · poll channel removed from the report | no catch | **3 failed** |

**All four are caught by pytest and by no gate.** Reported separately on purpose — reading a pytest catch
as a gate catch is the conflation D3.10 exists to prevent.

---

## 6. Gate disposition — all 12

| gate | disposition | evidence / owed |
|---|---|---|
| `check_python_runtime` | **DEFERRED** | Unfailable: `MINIMUM` == the only interpreter on the box. D3.11; discharges when `MINIMUM` rises above a retained interpreter |
| `check_venv` | **BOUND** | ARC 023, own venv, two distinct plants. D3.12 discharged |
| `check_node_identity` | **BOUND** | ARC 023, divergence perturbed against the real live UUID; third verdict shown. D3.13 discharged |
| `check_python_deps` | **BOUND** | ARC 022, re-taken against the real `.venv` |
| `check_ibgateway_config` | **BOUND** | ARC 010, live authenticated Gateway |
| `check_ibgateway_service` | **BOUND** | ARC 011, `systemctl disable` on the live box |
| `check_order_path_bans` | **BOUND** | ARC 022, re-taken against **both** real subjects |
| `check_spec_citations` | **BOUND** | ARC 022, re-taken; plus two real unplanted reds |
| `check_hook_suite` | **PARTIAL** | Arms 1+2 bound via global `core.hooksPath`; arms 3+4 owed. D3.14 |
| `check_datafeed_granted_mode` | **BOUND** | ARC 023 rebuild; both ARC 021 plants caught + 4 more |
| `check_datafeed_bar_seal` | **BOUND** | ARC 023; arm 4 drives 2 types, arm 2 polarity re-taken against the real adapter |
| `check_derived_claims` | **BOUND** | ARC 022 re-taken; new demonstration arm with 7 plants |

**10 BOUND · 1 PARTIAL · 1 DEFERRED.**

**Binding is PER SUBJECT** (rule of record). Every BOUND above means bound against the subject in its
row. `ibkr_mapping.IBKRDatafeedAdapter` is unbound and unbindable while it refuses, and the next adapter
presents a third shape — **which is why D3.9 and D3.10 stay open on a green tree.**

---

## 7. Close-out — all five raw, `git add -A` first

```
verify.py                 exit 1   10 passed | 1 failed | 1 cannot measure | 0 skipped
pytest                             351 passed, 2 xfailed          (353 collected)
pre-commit                         8/8 Passed
check_derived_claims      exit 0   13/13 + 2/2 demonstrations
check_spec_citations      exit 0
```

**`verify.py` decomposed.** The cannot-measure count fell **2 → 1** exactly as predicted, because the
rebuilt `check_datafeed_granted_mode` now passes. The remaining non-passes are `check_ibgateway_service`
FAIL and `check_ibgateway_config` cannot-measure — the Gateway's daily session expiry, both pre-existing
and both named. **No unnamed non-pass.**

No plants survive · `__pycache__` 0 · `core.bare = false` · adapter sha `9eb19c2cb3a7fb2f…` identical to
the plant-run control · scratch trees deleted · 120 dangling objects, none reachable.

### Coverage — level and delta, each naming its derivation and its column

| figure | level | Δ **this arc (ARC 022→023)** | derives from |
|---|---|---|---|
| `check_debt_open_items` | **61** | **−1** | ledger rows ∥ series row |
| `broker_order_open_debt_rows` | 13 | **0** | order vocabulary, D2.19-corrected |
| `broker_datafeed_open_debt_rows` | 13 | 0 | datafeed roster vocabulary |
| `pytest_collected_tests` | **353** | **+13** | pytest collector ∥ source AST |
| `registered_check_count` | 12 | 0 | checks glob ∥ registry.json |
| `spec_2a_broker_datafeed_elements` | 11 | 0 | frozen spec + flagged additions |
| `seam_declared_elements` | 27 | 0 | spec + flagged additions ∥ seam total |
| `broker_order_element_coverage_v1` | 56 | 0 | spec ∥ seam denominator |

**Column stated explicitly per §7.5:** every Δ above is ARC 022 → ARC 023. The corrected broker-order
depth series remains **11 → 13 → 13 → 13**, with ARC 022's previously reported "+2" identified as an
ARC 020→021 delta mis-filed into the ARC 022 column.

Nothing in this document was hand-typed; every count is read back from a command.

---

## 8. Findings the architect owns

1. **AMENDMENT 5 was already taken** by ARC 022's D1.38. Recorded as 6; you own whether to renumber.
2. **The brief cites `nics_risk_subsystem_spec_v1.3.md` §7.6 and §7.7 — neither exists.** That document's
   §7 is *Sizing Physics* and ends at §7.5. Read as `debug.md` §7.6/§7.7, which is what the surrounding
   items mean. The §0a class exactly: resolves to a plausible place, points at nothing.
3. **D3.9/D3.10 stay open on a green tree** — binding is per subject, and neither datafeed gate has a
   `test_check_*.py` companion, so its binding evidence lives in arc reports rather than in anything that
   re-runs it. The D3.15 shape one level up.
4. **The ARC 022 census table's verdict column is stale in four rows.** Left unrewritten per directive 6
   and flagged. **The next census belongs in a gate, not in prose** — this file has now been its own
   instrument's subject five times.
5. **F21 is structurally fixed but behaviourally unchanged on this system** until the poll-channel lag is
   measured. D1.39/D1.40 and the tap.
6. **D3.18** — arm 3's false positive is left standing rather than traded for a false negative.
7. **`check_python_runtime` is unfailable**, not merely unbound, against this node's inventory.

**Not in this arc, as scoped:** V24's kill-under-load drill · `capture.py` wiring, ZMQ, the shared-memory
ring · the Limiter and every consumer · a new Tier 3 · Tier-3 findings beyond the four named · D1.22 ·
D1.19 · D1.20's consumer half · D1.35 · a v1.4 of the frozen spec · the tap itself. No tap was requested.
