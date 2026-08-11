# ARC 022 — RESULTS

**Datafeed port sync/async split · gate binding and the UNBOUND census · Tier 3 on broker-datafeed**
Staged: Stage 1 (A) serial, then Stage 2 (B ‖ C). Not compressed.
Merged and confirmed on `origin/main`. 2026-08-11.

---

## 0. The headline, first, because it is a negative result

**Neither datafeed gate caught either of ARC 021's two real plants.**

Re-run against the settled adapter in a throwaway tree. Control pristine, both restores byte-identical
by sha256, `__pycache__` purged between every step. Verdict-by-verdict, never in aggregate (§7.7):

| | control | plant 1 — sentinel write deleted | plant 2 — requested-for-granted | discriminates? |
|---|---|---|---|---|
| `check_datafeed_granted_mode` | exit 2 | exit 2 | exit 2 | **no** |
| `check_datafeed_bar_seal` | exit 0 PASS | exit 0 PASS | exit 0 PASS | **no** |
| pytest | 321 passed, 0 failed | **3 failed** | **1 failed** | yes |

Identical gate verdicts either side of both plants is what *not discriminating* looks like.

**The two channels are reported separately on purpose.** ARC 021 closed the immediate hole with pytest
cases; D3.10 says the gates' own binding stays owed. Reading a pytest catch as a gate catch is the
exact conflation D3.10 exists to prevent. Two of the three catches on plant 1 were sub-agent B's
**brand-new Tier 3 traversals**, which discriminated where both gates did not.

**D3.10 stands, unnarrowed. Both datafeed gates remain UNBOUND.**

---

## 1. Baseline, confirmed not assumed (§0b)

| metric | measured | ARC 021 reported |
|---|---|---|
| HEAD | `08d9c56`, on `origin/main` | — |
| pytest | 293 passed | 293 |
| registered checks | 12 | 12 |
| derived claims | 13/13, exit 0 | 13/13 |
| CHECK-DEBT rows | 53 | 53 |
| pre-commit | 8/8 (after `git add -A`) | 8/8 |
| `verify.py` | exit 1 — **only** the two Gateway items | exit 1 |
| `TAP_SESSION.md` | absent | — |

No third verify failure at baseline. **§0a's tier map verified first-hand, not taken second-hand**:
`docs/debug.md` §2.1 overview · §3 TIER 1 · §4 TIER 2 · **§5 "TIER 3 — END-OF-MODULE CERTIFICATION"**.
The correction holds — the prior brief's §5 citation resolved cleanly and pointed at the banned tier.

---

## 2. Stage 1 (A) — D1.38 and two amendments

**The port split.** `connect`, `disconnect`, `subscribe`, `unsubscribe`, `poll_history` are coroutine
functions; `feed_lag` and `granted_mode` stay sync. `DATAFEED_PORT_VERBS` 5 → 7. Ruling recorded
verbatim and attributed as an operator ruling, never as spec text.

**`check_await_conformance()` extended, not duplicated** (check-rule 8), three both-directional
comparisons: adapter vs Protocol · Protocol vs the one declared partition constant per port · roster ⊆
Protocol. Can-fail demonstrated both directions, four outputs each, plus both drift directions of the
new comparison. Two permanent instruments banked beside `AwaitDivergentBrokerOrder`.

**The third comparison closed a hole open since ARC 014.** `if want is None: continue` silently skipped
any roster verb the Protocol did not declare — which is how `poll_history` and `granted_mode` sat
outside the datafeed contract for the whole of ARC 021 with the checker reporting clean.

**The architect's design sketch was refused, with measurement, and the refusal was correct.** The brief
asked for the roster to be derived by concatenating the partition constants. In a scratch tree that
spelling blinds **both** datafeed gates to CANNOT_MEASURE and reddens **four** claims: both gates
AST-read the roster and accept only a literal `Tuple`/`List`, and a `BinOp` yields nothing. Verified
independently at `check_datafeed_granted_mode.py:391` and `check_datafeed_bar_seal.py:370`. Roster
stays literal; the partition is the one declared constant per port.

**Amendment 4 — enforced, not documented.** `BarSource.TICK_AGGREGATED` exists only to be refused;
`Bar.__post_init__` refuses via an **allowlist**, so a future member added without an argument fails
closed. Proof-by-absence half (§7.6): an AST test asserts exactly one `Bar(...)` construction in the
adapter and that it sits inside `_ingest_history`.

**Amendment 3's refinement — applied, including where it meant removing optionality.**
`Bar.open/high/low/close` lost `| None`: a venue with no open has no bar, absence is a malformed row,
now refused by `MalformedBarRow`. Survivors each carry a stated observable absence — the `on_tick` trio
rests on ARC 013's **measured** 18 delayed ticks in 40 s on MESU6, a contract that does not print 18
trades in that window. One survivor honestly downgraded: `Bar.volume` rests on IBKR's *documented* `-1`
sentinel at **VENDOR_DECLARED** grade, never measured on this system, and the `-1` is not translated at
the vendor boundary. **D1.39 and D1.40.** Sub-agent B reached the same finding independently (F20).

---

## 3. D1.38 currently buys nothing behaviourally — stated, not glossed

All five async verbs contain **zero `await` expressions** (verified by AST at integration):

```
connect 0 · disconnect 0 · subscribe 0 · unsubscribe 0 · poll_history 0
```

So `asyncio.gather` cannot interleave them and a `Task` cannot be cancelled mid-flight. The atomicity
B's traversals observe is a property of the current bodies, **not of the contract**.

Two agents reached this from opposite directions: A left `connect()` still driving the injected
client's sync `connect(...)` as explicitly owed; B could not satisfy the concurrency half of its brief.
**B proved the absence three ways with a working interleave-detector control rather than manufacturing
an overlap**, and left an AST guard that reddens when `connectAsync` lands, so six traversals are
re-read rather than re-run.

The split's value is that the future swap is local and a sync signature can no longer conceal a round
trip — the ruling's own rationale. It is not yet a concurrency change.

---

## 4. Stage 2 (B) — Tier 3: RUN with findings, NOT PASSED

The verdict is `debug.md` §5.8's own criterion, not an opinion: PASS requires *bounds defined and
enforced at every edge*, and `Bar` validates provenance and nothing else — `period_s=0` collides seal
keys, `high<low` and infinities admitted. 27 tests over 22 sequences (the ten tabled plus ten added
with reasoning). No production code written; no writes into `scripts/broker/`.

Sharpest findings:

- **F21 — fit-for-purpose failure (§5.2).** `evaluate_freshness` reads `last_tick_venue_ts` only. At
  Stage 0 the tick stream does not exist, so a symbol fed entirely by **successful, current polls** is
  permanently STALE → §6.4 halt + flatten. The module fail-closes on the only margin-class path it has.
  **Spec gap, section named, answer not invented.**
- **F13.** A sink that raises leaves a bar sealed-but-unpublished; every later poll drops it as an
  identical re-poll. Permanently lost, no revision, no error — while the attempt record says
  `ok=True, rows=4`.
- **F17.** `lag_samples` unbounded; the session-wide mean reads `AGREES` at 602.97 s while the last 100
  packets sit at 900 s — 60 tolerances out. Measured at 10,100 ticks.
- **F12.** `poll_history` calls `setdefault`, so polling manufactures a subscription record and a later
  `unsubscribe` sends a real `cancelMktData` for a symbol never subscribed.

**Non-vacuity held.** Two of B's own traversals were caught vacuous during construction — one whose
first spelling would have **inverted** its finding.

§5.6 and §5.7 land across the arc's own gate runs and C's census rather than inside B's file.

---

## 5. Stage 2 (C) — the census, and what re-taking it corrected

**7 BOUND, 5 UNBOUND.** Gate list derived from `registry.json` ∪ `checks/*.py` — they agree at 12.
**Five of the seven BOUND verdicts were re-taken as live four-output plants rather than read off the
record.** "I believe so" was not accepted, and re-taking corrected the record twice:

- `check_order_path_bans` — the `import tenacity` plant is **ARC 017's**, not ARC 020's, and its target
  file is recorded nowhere. Re-planted today against **both** real subjects instead.
- `check_derived_claims` — it never edited a banked number. It **left one stale**, which proves
  detection while skipping the unplant/restore leg entirely. A genuine plant/unplant cycle was taken.

Opened per UNBOUND gate: **D3.11–D3.14**, plus **D3.15**, **D3.16**, **D2.23**.

**D3.15 changes another row's meaning.** `check_datafeed_bar_seal` arm 4 — named by *both* D2.20 and
D2.21 as their compensating control — reports `not synthesisable from annotations` for **all five**
published types and measures nothing. One-line root cause: `_synth_value` cannot resolve a union, and
`Bar.volume` is `float | None`. Already true on the ARC 021 merged tree, so D1.14's banked claim that
`FeedLag` "is constructed twice … and is proven to refuse a field write" became untrue at merge and no
instrument said so.

### D2.19 — fixed; the root cause was worse than the row said

The order-side basename vocabulary held **three** shared-host modules, including
`broker_datafeed_ibkr.py` itself. Clause (i) now subtracts modules implementing the datafeed port, read
from the seam's own roster.

| tree | old rule | new rule |
|---|---|---|
| ARC 020 (`436933e`) | 11 | **11** — identical eleven-row selection |
| ARC 021 (`842edb5`) | 16 | **13** |

**The ARC 021 rise of 11 → 16 was +3 contamination and +2 work. The corrected series is 11 → 13.** The
ARC 020 anchor re-derives identical, so the repair does not rewrite banked history.

**Residual named:** the roster half is still not distinctive. Measured false positive — **D1.38, a row
whose entire subject is the datafeed port, is still counted as broker-order depth on the single word
`connect`.** Disclosed, not papered over.

### D2.20 refused · D2.21 discharged · neither gate weakened

**D2.20 REFUSED** on the ARC 020 D3.7 standard, and the assessment made the refusal stronger than the
row: on its real subject arm B3's granted-side name set is **empty**, so the arm is not approximate
there — it is **vacuous**.

**D2.21 DISCHARGED**, proven in both directions over eight guard spellings: three correct spellings
still pass, both pre-existing detections still fail and still name their sites, and three
inverted-or-disjunctive spellings that used to pass now fail. The disjunctive escape was **not** in
D2.21 and was found by building the table rather than by reasoning.

**Not a weakening, and not asserted as one:** the change is strictness-only *by construction* — every
branch receives a strict subset of the guards it received before, so nothing that failed can now pass.
B.4's other edge was checked too: the real adapter's output is **byte-identical** across the change.

---

## 6. D3.16 — attribution corrected by measurement, and the correction makes it worse

C2 attributed the broken B1 drive to A's port split. **That is wrong.** `_observers()` discovers
subjects **by return annotation** (`-> MarketDataMode`), explicitly not from the roster. Running the
repaired gate against the ARC 021 tree — where `granted_mode` is **absent** from `DATAFEED_PORT_VERBS`
— reproduces the identical three `AttributeError` legs.

**This gate has never once driven `IBKRBrokerDatafeed.granted_mode` since the adapter landed in ARC
021, and reported PASS across two arcs over a subject it never executed.** That is exactly why it
passed ARC 021's plant 2, whose target is that method. A citation that resolves, pointing at a cause
that is not the cause.

**Half-repaired at integration.** A leg raising anything other than `NotImplementedError` is now
returned as `broken` and the verdict is **CANNOT_MEASURE, never PASS** (`nix_check_contract.md` §5.3).
`NotImplementedError` stays a note deliberately — `ibkr_mapping.IBKRDatafeedAdapter` is a refusing
skeleton, and reddening it for honouring its own contract is doctrine **B.4's forbidden direction**;
verified absent from `broken`. Strictness-only. Control: the gate still passes a tree where its subject
is drivable.

**The gate is now HONEST but still NOT BOUND** — exit 2 on the control and exit 2 on both plants.

---

## 7. A fourth instance of git's tracking state setting gate scope

`.gitignore` spelled `state/` and `.venv/` with **trailing slashes** — directories only. In a
provisioned worktree both are **symlinks**, so `git check-ignore` exited 1: untracked but **not
ignored**. Because this project mandates `git add -A` before every gate measurement, the first
measurement any sub-agent took staged a symlink pointing at `~/nix/state`, the 0600 directory holding
the hardware UUID and credential JSON.

`provision_worktree.sh`'s own docstring asserted these *"cannot be committed and cannot reach a diff."*
The claim was false, and it survived because **the guarantee lived in prose**. Both slashless spellings
added; the script now *proves* the ignore per target and exits 1 with the cause named:

```
verified     : state and .venv are IGNORED inside the worktree, not just untracked
```

Same defect class as the `.testmondata` sidecars ten lines away in the same file (ARC 016). Fourth
instance overall: ARC 016 untracked broker package · ARC 020 stale local `main` · ARC 021 pre-commit
not scanning untracked · now this. **D2.24.**

---

## 8. Close-out — all five raw, `git add -A` first

```
verify.py                 exit 1   9 passed | 1 failed | 2 cannot measure | 0 skipped
pytest                             338 passed, 2 xfailed
pre-commit                         8/8 Passed
check_derived_claims      exit 0   13/13
check_spec_citations      exit 0   2286 §-citations scanned
```

**`verify.py`'s decomposition, because the count changed and it is not a regression.**
`check_ibgateway_service` FAIL and `check_ibgateway_config` cannot-measure are the Gateway's daily
session expiry, unchanged from baseline. **The second cannot-measure is new and deliberate**:
`check_datafeed_granted_mode` was reporting PASS over a subject it could not drive, and now says so.
A third *failure* would have been a finding; this is a third *non-pass* that is a repair, and it is
named rather than absorbed.

No plants survive · `__pycache__` purged (0) · `core.bare = false` · `git fsck` clean but for two
dangling blobs · scratch trees deleted · adapter sha `0e1897028e7f4617…` identical to the plant-run
control.

### Coverage — level and delta distinguishable, each naming its derivation

| figure | level | Δ this arc | derives from |
|---|---|---|---|
| `spec_2a_broker_order_elements` | 16 | 0 | frozen-spec identifiers ∥ seam roster |
| `broker_order_element_coverage_v1` | 56 | 0 | spec denominator ∥ seam denominator |
| `arc014_broker_order_classification` | 16 | 0 | findings ∥ grade tally ∥ spec roster |
| **`broker_order_open_debt_rows`** | **13** | **+2 real** | order vocabulary, **D2.19-corrected** |
| `spec_2a_broker_datafeed_elements` | 11 | +2 | frozen spec + flagged additions ∥ seam roster |
| `seam_declared_elements` | 27 | +2 | spec + flagged additions ∥ seam code total |
| `broker_datafeed_open_debt_rows` | 13 | +3 | datafeed roster vocabulary |
| `check_debt_open_items` | 62 | +9 | ledger rows ∥ series row |
| `pytest_collected_tests` | 340 | +47 | pytest collector ∥ source AST |
| `registered_check_count` | 12 | 0 | checks glob ∥ registry.json |

**The corrected broker-order depth series, with the prior value named as contamination:**

```
ARC 020: 11  →  ARC 021: 13  →  ARC 022: 13
                   ^^ the previously reported 16 was CONTAMINATION, not work:
                      +3 contamination (rows naming a shared-host module,
                      attributed to broker-order by basename alone) and +2 work.
```

Nothing in this document was hand-typed; every count is read back from a command.

---

## 9. Findings the architect owns

1. **Both datafeed gates are unbound and did not catch either real plant.** The arc's stated outcome.
2. **`check_datafeed_granted_mode` never drove its subject across two arcs** (D3.16). Half-repaired to
   honest; binding still owed.
3. **`check_datafeed_bar_seal` arm 4 measures nothing** (D3.15), and two other rows lean on it as their
   compensating control.
4. **Tier 3 is RUN, not PASSED**, by §5.8's own criterion.
5. **F21**: the module fail-closes on the only data path Stage 0 has. Spec gap — §6.4:371-374 and
   §2A's absent freshness-stamp declaration. **No answer invented.**
6. **D1.38 is declarative only** until `connectAsync` binds.
7. **`Bar.volume`'s justification is unmeasured** (D1.39/D1.40).
8. **D2.19's residual**: D1.38 is still miscounted as broker-order depth on the word `connect`.

**Not in this arc, as scoped:** V24's kill-under-load drill · `capture.py` wiring, ZMQ, the
shared-memory ring · the Limiter and every consumer · D1.22 · D1.19 · D1.20's consumer half · D1.35
config JSON · a v1.4 of the frozen spec · the tap itself. No tap was requested.
