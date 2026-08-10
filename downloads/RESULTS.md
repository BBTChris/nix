# ARC 018 — RESULTS

**Runtime-gate truth · neutral rejection taxonomy · ban-gate hardening.** Mega arc, three
sub-agents in disjoint git worktrees, parent-owned Phase 4 integration.

Every number below is from a pasted command (prohibition 6). The brief stated no expected
values, so nothing here was reconciled toward a target.

---

## 0. Headline

**The runtime gate could report green having measured nothing, today, in the shipped config.
It can no longer do that.** That was the arc's primary objective and it is closed, along with
the second-order defect the repair itself created and the third-order defect that surfaced
when the repair became testable code.

| | baseline (ARC 017) | now | |
|---|---|---|---|
| `verify.py` | 8 passed, exit 0 | **8 passed, exit 0** | — |
| pytest | 159 | **180** | +21 runtime-gate tests |
| pre-commit | 8/8 Passed | **8/8 Passed** | — |
| per-hook can-fail | 7 of 8, 1 partial | **8 of 8, 0 partial** | D3.5 adopted |
| `check_derived_claims` | 7/7 claims | **9/9 claims** | +2 registered |
| open debt | 30 | **29** | −1 |

---

## 1. §0a baseline — and the one thing the brief got wrong

Four of five baseline values matched ARC 017 exactly: verify 8/exit 0, pytest 159,
pre-commit 8/8, `check_debt_open_items=30`, per-hook can-fail 7 of 8.

**PR #11 had NOT landed on main.**

```
11  ARC 017 — session-state integrity…  arc-017-session-integrity  OPEN
10  ARC 016: commit the broker package…  arc-016-broker-consolidate  MERGED
$ git rev-list --left-right --count main...HEAD
0	3
$ git merge-base --is-ancestor b8ba7ff main   ->  b8ba7ff is NOT an ancestor of main
```

`main` was at `92f9f17` (PR #10). ARC 017's three commits existed only on their branch — the
ARC 013 stranding shape recurring. The brief's §0a instruction *"ARC 017 landed on PR #11 —
confirm it is on main"* was false. ARC 018 was based on `b8ba7ff` anyway, so **landing this
arc lands ARC 017 with it**, which resolves the stranding rather than deepening it.

---

## 2. D2.13 — DISCHARGED. Zero collection can no longer report success.

The failure was never that testmon selects nothing; selecting nothing is correct when nothing
changed. The failure was that **a run which measured nothing was indistinguishable from a run
that measured everything and passed.**

`entry:` is now `./.venv/bin/python scripts/runtime_gate.py` — a verdict taxonomy that reads
`.testmondata` before the run, makes its state an input, and prints its own scope every time.

```
MEASURED-PASS     exit 0   SELECTED > 0 and every selected test passed
FAIL              exit 1   pytest failed; pytest named the site
SELECTOR-BROKEN   exit 1   nothing selected, yet the record disagrees with the tree
SCOPE-BLIND       exit 2   a changed file the database has no fingerprint for
NOTHING-SELECTED  exit 2   legitimate "nothing changed" — CANNOT-MEASURE, never PASS
CANNOT-MEASURE    exit 2   database unreadable, or pytest wrote no parsable report
```

Exit 2 kept distinct from exit 1 (`VERIFY-AND-CHECKS` B.2, failure mode #10). `SELECTED`
comes from pytest's own JUnit XML, not scraped stdout. Corroboration is **independent of
testmon**: git-blob SHA-1 recomputed with `hashlib`, both of testmon's spellings accepted so
non-ASCII sources cannot produce false drift.

**Two designs rejected, and the rejections are the argument.** A full sweep every commit
trades silent-green for a slow gate people route around — worse by §7.12's own logic. A floor
on collected count is a literal anchor that *still* cannot tell "nothing changed" from "the
selector is broken".

### Defect reproduced pre-fix, verbatim

```
Stage 3 — runtime pass...................................................Passed
testmon: changed files: 0, unchanged files: 38, environment: default
collected 0 items
============================ no tests ran in 0.01s ============================
HOOK_EXIT=0
```

### Post-fix, identical conditions

```
RUNTIME-GATE scope: db=present known_files=38 in_scope_files=39 uncovered=1 drift=0
  recorded_tests=159 recorded_failures=0 env=default@3.14.4 alien_env=0
  mode=incremental SELECTED=0
RUNTIME-GATE verdict: NOTHING-SELECTED — this run measured 0 test(s)      exit 2
```

Default path escalates instead of terminating: `SELECTED=159 MEASURED-PASS`, **11.6 s**, and
only on commits that touch no Python.

### Two findings the D2.13 row did not know about

**A2-i — a tracked source file could change and select nothing.**
`scripts/nixverify/__init__.py` is in every other hook's scope and had **no fingerprint at
all** in testmon's graph. Changing it, the old gate printed `collected 0 items` / exit 0 —
green over a real, tracked, changed file. Now `SCOPE-BLIND`, and `uncovered=` names such
files on every run.

**A2-ii — testmon does not notice its own corrupted record.** One `file_fp.fsha` overwritten
with zeroes: old gate `collected 0` / exit 0. New gate:
`SELECTOR-BROKEN — 1 in-scope file(s) differ from the db record yet nothing was selected`,
exit 1.

### `.testmondata` — what changed and what did not

Not fixed by tracking it (binary SQLite + WAL sidecars is a second source of truth that goes
stale on write; ARC 016 rejected the same shape for `downloads/*.py`). Its **state** is now a
printed, load-bearing input: `db=`, `known_files=`, `uncovered=`, `drift=`, `recorded_tests=`,
`recorded_failures=`, `env=`, `alien_env=`, `SELECTED=`.

**Stated plainly: it became visible, not reviewable.** It is still untracked and still
per-machine. Two people on the same commit can still get different scopes — they can now both
*see* that they did. Four further residuals are written beside the gate rather than left to be
found: an unchanged test in an unfingerprinted file; method-level checksums not re-verified;
and the gate cannot prove the suite is *adequate*, only what ran.

---

## 3. D2.16 — opened by the repair, discharged by it, and it paid for itself

Sub-agent A's write scope forced the gate program into a YAML `entry:` string — outside every
static gate and every test. A opened D2.16 and did **not** reach across into `scripts/`, which
was the correct call under §3. Phase 4 lifted it to `scripts/runtime_gate.py` with
`scripts/tests/test_runtime_gate.py` (21 tests, first assertion a non-vacuity check that
derives the invoked path **out of `.pre-commit-config.yaml`** so the suite cannot drift onto an
orphan module).

**The lift paid for itself within the hour**, which is the whole argument for doing it:

* Static analysis of the now-visible code produced bandit **B405 / B314 / B607**, pylint
  **C0209 / R0913 / W0212 / C1803**, ruff **EXE001 / FURB192**. Every one invisible while the
  program was a string.
* **And a behavioural false positive that made the gate unusable** — see below.

### The false positive, and why the first design was wrong

`SELECTOR-BROKEN` originally *terminated* on `drift and selected == 0`. Reproduction is one
line: append a comment to any test file and run the gate twice.

```
RUNTIME-GATE drift (db record does not match tree content): scripts/tests/test_check_venv.py
RUNTIME-GATE verdict: SELECTOR-BROKEN - 2 in-scope file(s) differ ... yet nothing was selected
exit=1
```

Both runs identical — **it does not self-clear**. A commit touching only comments or
docstrings was permanently red, with a verdict naming a selector that was working perfectly.

The cause is a genuine asymmetry rather than a bug in either tool: this gate's corroboration
is **content-based** (a git blob hash) while testmon's selection is **semantic** (per-method
checksums). A behaviour-neutral edit legitimately changes one and not the other. **Content
drift is evidence the record is *stale*. That is not the same claim as "the selector is
broken", and the original arm conflated them.**

Repaired by escalating rather than terminating: the full run measures everything, so a later
pass is honest; `drift=` still names every affected file; and the arm stays terminal under
`NIX_RUNTIME_GATE=noescalate`, which is how the A2-ii corrupted-`fsha` demonstration was taken
in the first place, so that evidence is unaffected. Re-proved:

```
comment-only edit, default path:
  mode=full-escalated(SELECTOR-BROKEN:1 in-scope file(s) differ ...) SELECTED=180
  RUNTIME-GATE verdict: MEASURED-PASS       exit=0
next run:  drift=0    ->  self-clears
```

### Can-fail re-proved on the final gate

```
sha before:   fd5d4992188ebffc
sha planted:  361b325beac3788d
FAILED scripts/tests/test_check_venv.py::test_arc018_phase4_plant - assert 1 == 2
RUNTIME-GATE ... mode=incremental SELECTED=9
RUNTIME-GATE verdict: FAIL - 1 of 9 selected test(s) failed        exit=1
sha restored: fd5d4992188ebffc
RUNTIME-GATE ... SELECTED=8   verdict: MEASURED-PASS               exit=0
```

`SELECTED=9` — neither 0 nor 181. Real selection, exactly ARC 017's figure. `__pycache__`
purged between every step (prohibition 7).

---

## 4. D3.5 — ADOPTED. Per-hook can-fail 7/8 → 8/8.

```
=== CONTROL ===  ruff format...Passed   39 files already formatted   exit 0
=== PLANT ===    fd5d4992188ebffc -> b75177e09e80b1d6
--- CAN-FAIL ---
ruff format..............................................................Failed
unformatted: File would be reformatted
   --> scripts/tests/test_check_venv.py:1:1
    - def test_arc018_ruff_format_plant(  ) -> None :
    + def test_arc018_ruff_format_plant() -> None:
1 file would be reformatted, 38 files already formatted
--- sha256 AFTER the hook ran ---
b75177e09e80b1d648383a6611c7504226c7d26f0ce12074bf35a3ddbf25916b   <-- UNCHANGED
=== second run over the same defect ===  HOOK_EXIT_2ND=1
=== RESTORE + CONTROL ===  fd5d4992188ebffc  ruff format...Passed
```

It reports instead of repairing, and the second run over the same defect still fails — the
gate no longer consumes its own subject (failure mode #7).

**Site naming, honestly:** the *file* is named exactly and offending lines 211–214 appear in
the diff gutter; the header coordinate is the nominal `:1:1`. **Ergonomic cost accepted and
written into the config:** commits are no longer auto-formatted; the fix is
`.venv/bin/ruff format <file>`. **Nothing was relaxed elsewhere** — `ruff-check` keeps `--fix`
deliberately, and §7.12 answer 5 is left standing for that hook rather than quietly dropped.

---

## 5. D1.18 — the provisional ruling is RATIFIED, on evidence that also corrects the ledger

The brief invited the argument that the ack `reason` field is never consumed programmatically
and structurally cannot be. **That argument does not survive contact with the tree.**

```
scripts/tests/test_broker_order.py:626 : "35035.87" in (sink2.acks[0][2] or "")
scripts/tests/test_broker_order.py:1773: "synthesised" in (sinkR.acks[0][2] or "")
scripts/tests/test_broker_order.py:1813: "synthesised" not in (sinkY.acks[0][2] or "")
```

Three live consumers. Two of them substring-match `reason` to derive a **fact** — whether an
ack was synthesised by §2c — and that is the adapter's *designed* discriminator, endorsed in
its own comment. On the structural question: `reason: str | None` is a plain optional field on
a `Protocol`; no `NewType`, no opaque wrapper, no `@final`, no §9A guarantee (the strategy
contract has no `on_ack` at all). **Not a structural guarantee, and not even an absence — it is
present consumption.**

**More consequential: D1.18's own deferral rationale was factually wrong, and that error was
the entire basis for deferring.** The row said discharge should wait for "the Limiter, which is
the first component that will actually consume an ack reason." Three consumers precede it. The
row's other two claims stand and are honoured — the tension is genuine, and 201's margin figure
has real diagnostic value, which is why `reason` keeps the code and full text unchanged.

### The taxonomy

Enum is **spec-derived** from §4 Limiter behaviours; the map is **evidence-derived** and is
currently one entry. That split is stated rather than blurred.

| category | the distinct consumer behaviour that earns it | codes |
|---|---|---|
| `INSUFFICIENT_MARGIN` | our projection disagrees with venue truth → poll balance/positions and correct it; specifically do **not** re-size against the projection that just proved wrong | **201**, *only with the measured money wording* |
| `NOT_TRADABLE` | money is not the problem; re-polling changes nothing and time will not fix it → deny the symbol, escalate; expired contract → §7.5 roll | none measured |
| `VENUE_UNAVAILABLE` | time-varying, not a statement about the account → hold in HALT and act when tradable. Explicitly **not** a licence to resend | none measured |
| `UNKNOWN` | the floor — no specific response is licensed; §4 uncertainty resolves toward flat | everything else, always |

**201 is deliberately not mapped on the integer alone.** IBKR's 201 is a wrapper —
`"Order rejected - reason:<text>"` — so keying the category on the bare code would make *every*
201 read as a money problem: an unknown wearing a known's clothes. The rule carries two
substrings from the measured sample, kept **below** the seam, and degrades to `UNKNOWN` if IBKR
rewords rather than to a confident wrong answer. A mechanical evidence gate requires every
mapped code to carry a written citation in `IB_REJECT_EVIDENCE` — no mappings from memory of
IBKR's published error list.

`on_ack` gains a **keyword-only** `reject_category`, so §2A's positional shape
`(client_order_id, accepted|rejected, reason?)` is untouched and the addition is visibly an
addition. **Frozen spec not edited.**

### Proof

44 assertions, 0 failed. Invariant 2 asserted **two independent ways per rejection**: the
driving venue code appears in no structured field; and the payload contains **no digit at all**,
which catches a code the case does not happen to drive. Plus a whole-enum assertion that no
member name or value contains a digit. Emission-site coverage is **AST-derived, not restated**:

```
REJECTED-ack emission sites found in scripts/broker/: ['broker_order_ibkr.py::_on_ib_error']
sites this suite drives                             : ['broker_order_ibkr.py::_on_ib_error']
```

Can-fail (collapse the taxonomy), `__pycache__` purged between every step, sha256
`d53a019b…6269` → `5dc30c03…1b96e` → `d53a019b…6269`:

```
1 failed, 158 passed in 10.91s     canfail exit=1
E  NON-VACUITY: the taxonomy is not collapsed — observed=['UNKNOWN'] over 5 driven rejections
   — SITE: .../broker_order_ibkr.py:208 ib_reject_category() + IB_REJECT_RULES
```

The site string is **derived** via `inspect.getsourcefile`/`getsourcelines`, never typed.

**All three controls still behave as controls** after the port change (ARC 016 §2a precedent):
Hollow 9 behavioural failures *and* separately asserted structurally + await conformant, so it
fails for the behavioural reason and not a shape reason; Stub 0; Divergent 1
(`query_positions: port declares async, adapter is sync`). `RecordingSink.acks` was widened by
**appending**, so every existing `acks[i][1]`/`[2]` index still means what it meant.

---

## 6. D2.14 / D2.15 — NARROWED, not discharged. And their shared citation was phantom.

**There is no §2.1 in `nics_risk_subsystem_spec_v1.3.md`.** Headings run
`## 2. Component Model & Authority Split` → `## 2A. Broker Abstraction Contract`; the only
`x.1` headings in the file are 12.1 / 12.10 / 12.11. "§2.1" was the ARC 017 *brief's*
prohibition 1 — a task document, not the frozen spec — propagated into the CHECK-DEBT **D2.14
row** and into `check_order_path_bans.py`'s own docstring. **The ban is real; the anchor was
not.** Corrected in both places to the verified anchors: §2A:71 *"never auto-resend"*, §4:241
*"never auto-resends"*, §12A:830 *"status query, never resend"*.

This is the "derivation pointed at the wrong place" shape, found inside a gate's own docstring.

### D2.14 — hand-rolled retry detection, and the false-positive question answered

Three shapes, all AST, no regex over source text, extended **inside** the existing gate
(doctrine C.9 — not a second gate that could disagree): `loop_contains_send`,
`bounded_counter_send` (detected from the counter *mutation*, never from `attempt|retry|tries`
naming, which would be a stale literal anchor), `except_reinvokes_send`. `SEND_PATH_VERBS` is
**derived** from the port roster by AST minus two spec-cited exemption sets, so a verb added to
the port becomes send-path automatically — fail-closed.

**Measured false-positive rate, pasted rather than estimated:**

```
  broker_order_ibkr.py: 2 loop(s)   broker_seam.py: 3 loop(s)
  ibkr_mapping.py: 3 loop(s)        seam_simulate.py: 1 loop(s)
TOTAL loops in scope = 9; files = 4
1 hit / 9 loops / 4 files.  8 of 9 loops cleared with no suppression and no row.
```

The single hit is `IBKRBrokerOrder.flatten`'s per-symbol fan-out — one market close per
*symbol*, `client_order_id = flat-{sym}-{seq}`, handler collects-and-continues. Genuinely not a
retry, and genuinely a site a reviewer should have to look at.

**Usability verdict: usable, comfortably.** One review owed per four order-path files; the one
new loop this arc produced (B's `ib_reject_category`) cleared **by construction, not by
suppression** — the walker saw the loop and produced no hit because its body calls no send verb.
No suppression row was added for it and none is owed. **Nothing was widened to get quiet:** the
only tuning was the two exemption sets, each a spec citation rather than a noise reduction.

**Suppression is narrow by construction**, keyed `(file, qualname, shape, verb)`: never
file-level or glob (a missing key is itself a violation); never line-keyed (a line number is
failure mode #4); self-expiring (an entry matching nothing is a violation); unsigned entries are
violations; cannot silence the retry-library or loop-blocking arms at all; and every applied
suppression prints on every run. **It proved itself at merge** — `flatten` moved from line 493
to 583 under B's changes and the suppression still matched, because it is keyed on structure
rather than position.

**Honest caveat for the next arc:** the rate is low *because the order path is 4 files*. The
Limiter will be the real test, and if call-site derivation is ever added the rate is not
predictable from this measurement and must be re-measured before that change is accepted.

**Residuals keeping the row open**, each named beside the gate: retry by **recursion**
(`except: return self._send(n-1)` — fires no shape); indirection deeper than one hop
(`INDIRECTION_DEPTH = 1`); retry across a thread or process boundary, which no scanner can see;
and a suppression that is *wrong* rather than stale — the gate checks a justification exists,
not that the reasoning is sound.

### D2.15 — scope now derives from the tree

Every directory holding a module that **declares** the order port (defines `ORDER_PORT_VERBS`,
or a class carrying ≥ 4 roster-verb methods), read from each file's own AST, union'd with
`ORDER_PATH_DIRS` as a **floor** so the scan can never collapse below its historical scope. The
constant keeps its name deliberately, so D2.15's own citation does not go stale in the act of
discharging it. Test exclusion derives from `pyproject.toml` `testpaths` via `tomllib`; an
excluded port implementor prints as a `SCOPE-ADVISORY` rather than vanishing.

```
CONTROL                pass  [scanned 4 files over 1 dirs: scripts/broker]  exit=0
PLANT — second home at scripts/limiter/limiter_order_adapter.py
fail_needs_operator    [scanned 5 files over 2 dirs: scripts/broker, scripts/limiter]
  detail: limiter_order_adapter.py:22 ... [loop_contains_send] place_order()
RESTORE                pass  [scanned 4 files over 1 dirs: scripts/broker]  exit=0
```

Found **and** judged. Registered as claim `order_path_scope_files=4` with the "stated" probe
reading `ORDER_PATH_DIRS` **out of the gate by AST** rather than retyping it, so the probe is
not itself a restatement. Claim-level can-fail: planting the second home moves derived to 5
against stated 4 → claim RED. **The gate self-heals its scope while the claim makes the change
visible.**

**Open residual — a module that CALLS the order port without DECLARING it.** The future Limiter
is exactly that shape and is the likeliest home of a real hand-rolled retry. Closing it needs
call-site derivation, which multiplies the false-positive surface by the size of the Limiter.
**That trade is named here, not made.**

### The boundary that is one directory wide

Written into the gate: the spec **mandates** retry/backoff *outside* the order path —
§12A:827 `RETRY_BACKOFF` "retry policy before declaring stale", also §6.4:374 and §13:900, for
poller staleness. So "retry loop" is banned on the order path and *required* for pollers. If
this gate's scope ever grows to cover poller code it will start reddening spec-mandated
behaviour, and **the repair is then to the scope boundary, never to the ban.**

### C3 / named gap 4 — NOT CLOSEABLE AT ACCEPTABLE COST

Assessed honestly, with all three candidate closures rejected in writing rather than a
half-measure built to have something to show. (a) Banning `importlib.import_module` outright
forbids a legitimate construct on the argument that it *could* be misused, and with no such call
on the order path today it would be a rule with no subject. (b) Flagging every computed `getattr`
reddens `check_structural_conformance` / `check_await_conformance` at `broker_seam.py:717,747` —
the seam's own conformance instrument, whose mechanism *is* computed `getattr`. (c) Executing the
order path under an import hook is the only closure that measures the property, and it means
running code whose purpose is to place orders at a venue, inside a gate that runs at boot and
every Saturday 03:00.

---

## 7. The harness was not implementing its own documented rule

`CHECK-DEBT`'s note states the rule of record: *a row is discharged iff some **bold** span in it
matches `discharged ARC <n>`*, and explicitly that *"the bold-span restriction is load-bearing,
not cosmetic."*

`check_derived_claims.py` was testing `"discharged" not in ln.lower()` — the naive scan the note
warns against — and had been since ARC 017. It went unnoticed because no open row happened to
contain that exact word: D3.5 says *"discharges"*, missing by one letter.

**ARC 018 broke it for real.** Rows reading **"NARROWED ARC 018, NOT DISCHARGED"** counted as
paid, as did D1.19's body citing "discharged D1.18".

```
BEFORE FIX:  check_debt_open_items: DISAGREEMENT derived:ledger_rows=26, stated:...=30
             hand-derived: 29.  Gap = exactly D2.14, D2.15, D1.19.
AFTER FIX:   check_debt_open_items=29 [derived:ledger_rows=29, stated:series_table_latest_row=29]
```

Harness corrected to the documented regex. **A ledger that cannot say "not discharged" without
marking itself paid is the instrument being its own defect** — `VERIFY-AND-CHECKS` Part C's
opening failure class, caught by the reconciliation loop the brief asked for.

---

## 8. Ledger: 30 → 29

**Discharged (4):** D2.13 · D3.5 · D1.18 · D2.16 (opened and discharged in-arc).
**Opened (3):** D2.16 · D1.19 · D1.20.
**Narrowed, still open (2):** D2.14 · D2.15.

* **D1.19** — ack *provenance* (venue vs synthesised) is carried only by matching the English
  word `synthesised` in free text. §7.4's stale-literal-anchor shape, but **not** an invariant-2
  breach: `synthesised` is a Nix word, not a vendor spelling. Split out rather than folded into
  D1.18, and named rather than silently fixed, because fixing it would have widened B's scope.
* **D1.20** — `_mirror_stale` **latches** across a successful reconnect: `connect()` discards
  `_rebuild_mirror()`'s verdict, so a re-read that failed once stays `True` even after a
  reconnect that did rebuild. It fails toward "suspect" (the safe direction), but a consumer
  gating entries on it would never resume trading — a one-way door whoever builds the consumer
  must fix in the same motion.

---

## 9. Other corrections

* **`CLAUDE.md` indexed `debug.md` as v1.1.0**; disk reads **"Version 1.2.0. Supersedes v1.1.0,
  which lacked §7.12."** §7.12 and failure mode #14 are precisely what this arc turns on, so the
  index pointed at a doctrine that did not contain the section. Corrected, with a
  `CLAUDE-CHANGELOG.md` entry.
* **`.pre-commit-config.yaml`'s §7.12 scope table went stale *inside* ARC 017**, broken by ARC
  017's own commits. It said 87 tracked files / 37 per hook / 38 `.py`; derived today: **91 / 39
  / 40**. Every figure was correct at `92f9f17`. Second D2.8 instance living inside a gate's own
  configuration. Replaced by the command that derives it, with ARC 017's figures kept only as
  dated evidence bearing their commit.
* **ARC 016's restore evidence: SOUND, closed.** Structurally, its plant was caught by ruff,
  pylint and mypy — three *static* readers that never import the module, so bytecode cannot
  reach that evidence. Empirically on this interpreter, prohibition 7's hazard was **reproduced
  and confirmed** (`CASE A: PURE LINE SWAP → AAA — STALE BYTECODE RAN`) and is strictly *same
  byte size **and** same integer-second mtime*; ARC 016's plant changed size, so invalidation was
  forced on both edges.
* **The pre-ARC-010 bandit environment re-measured, not accepted.** Rev `2d0b675` still reports
  `Files skipped (20)`, every one "exception while scanning file", `High: 0`, exit 0, while 1.9.4
  catches the same plant (`Low: 1 High: 1`, exit 1). Classified **owed, not acceptable standing
  risk**, recorded under D1.10 rather than as a new row (Part C rule 9, one owner per property).
* **Named gap 5 re-confirmed accurate and still visible**, and deliberately **not** repaired.
  Tested the only way it can be: three claims were added and nothing in the gate asked for them,
  noticed they were missing, or would have reddened had they never been added. The gap is not
  shrinking as the registry grows; it is exactly as large as the set of numbers nobody thought of.

---

## 10. C4 — one scheme registered, the other retired as a rule

```
broker_order_percent_sec2a_element_v1=56
  [derived:spec_denominator=56, stated:seam_denominator=56; 0 restatement(s) found]
```

**Scheme identifier `sec2a-element-v1`**, carried in the claim `id` and `property`, so a future
change of scheme appears as a *new claim* rather than a silent discontinuity in a series that
kept its name. Derivation: `100 × |§2A elements graded CLEAN| / |§2A roster|` = **9/16**, both
terms re-derived every run from two independent denominators (frozen-spec markdown parse vs
`broker_seam.py` AST). Where independence stops is stated rather than overclaimed: the
*numerators* share `FINDINGS`, so this is a third assertion on top of two existing claims, not a
replacement for either.

**The ~42% figure exists nowhere on disk and never has.** `grep -rIn "42%"` over the worktree,
`git log --all -S"42%"`, and XML extraction over both `.docx` all come back empty; its only
occurrence in the entire project is the ARC 018 brief itself. **So there was nothing to retire
mechanically — the retirement is a RULE, not a repair**, enforced by a `restatement_scans`
tripwire on `RESULTS.md` matching the canonical form. It deliberately does not match a per-arc
*delta*, and it scans only `RESULTS.md`: `SESSION.md` and the series table are append-only
history, where a dated historical percent is correct forever.

**A defect in the scheme that could not be fixed, reported rather than reconciled:** ARC 017's
`~13%` is `2/16`, where 16 is machine-derived but **2 is an arc-local hand count of defects
closed**. No gate can make an arc's own count of what it closed machine-derivable. It is also not
the level — the ARC 014 grades did not flip in ARC 017 — so `~13%` and `56%` are a **delta and a
level**, not two versions of one number.

---

## 11. Verification — merged tree, all raw

```
$ .venv/bin/python scripts/verify.py
  [ok]   check_python_runtime      [ok]   check_python_deps        [ok]   check_order_path_bans
  [ok]   check_venv                [ok]   check_ibgateway_config   [ok]   check_derived_claims
  [ok]   check_node_identity       [ok]   check_ibgateway_service
  8 passed | 0 failed | 0 cannot measure | 0 skipped          exit 0
verify exit=0

$ .venv/bin/python -m pytest scripts/tests -q
180 passed in 11.80s

$ .venv/bin/pre-commit run --all-files
ruff check....Passed   ruff format....Passed   pylint....Passed   mypy....Passed
bandit (production)....Passed   bandit (tests)....Passed   complexipy....Passed
Stage 3 — runtime pass....Passed

$ .venv/bin/python checks/check_derived_claims.py
pass: 9/9 claim(s) compared — registered_check_count=8 | pytest_collected_tests=180 |
pinned_dependency_count=2 | check_debt_open_items=29 | spec_2a_broker_order_elements=16 |
arc014_broker_order_classification=16 | seam_declared_elements=23 | order_path_scope_files=4 |
broker_order_percent_sec2a_element_v1=56       derived_claims exit=0
```

**pytest 159 → 180, delta explained:** +21 from `test_runtime_gate.py`, which discharges D2.16.
Sub-agent B's 44 new taxonomy assertions moved the *test* count by zero because they live inside
the existing `test_ibkr_broker_order_adapter` entry point — the number that moved there is the
driver's assertion count, derived: 108 → 152.

**Which hooks are now proven and which are not.** All 8 have a demonstrated can-fail (7/8 → 8/8,
D3.5 closing the gap). Two — `ruff-check` and `pylint` — still **cannot report their own scope**;
§7.12 answer 6 stays live for them by measurement, not assumption. The other six self-report
(`ruff format 39 files`, `mypy 39 source files`, bandit LOC + `Files skipped (0)`, `complexipy 39
files analyzed`, `RUNTIME-GATE ... SELECTED=`).

**Integration hygiene:** zero merge conflicts across the three worktrees — the disjoint write
sets held. `git status --porcelain` clean, no plants, `scratch/` absent, `__pycache__` purged,
worktrees removed.

---

## 12. §8 live confirmation — DECLINED. Known-red **R1-A**.

Only sub-agent B's work is live-observable, and only on the rejection path. Not attempted: it
would require a 2FA tap, which the brief forbids requesting. **RED withholds certification, not
durability.**

What is owed is one observation on `clientId=905`: an unaffordable-size order returning
`reject_category=INSUFFICIENT_MARGIN` with `reason` still carrying `201: …MARGIN REQ […]`. That
single observation confirms both halves — structured fact populated, human channel intact — and
re-validates the text anchor against IBKR's current wording, which is the one thing offline tests
cannot do. ARC 017's precedent stands: decline near the 16:00 CT close, because evidence taken at
a session boundary is ambiguous.

**Nothing measured on IBKR at Stage 0 means anything about latency, fill realism, slippage, or
strategy performance — the feed is delayed ~600 s.**

---

## 13. Defects found in this brief (§0a applied to the brief itself)

The brief asked for this rather than for reconciliation. Ten found.

1. **§0a: "ARC 017 landed on PR #11 — confirm it is on main" — FALSE.** PR #11 was open; main
   was at `92f9f17`.
2. **§2 prohibition 1 and §6/C1 cite "§2.1" of the frozen spec. There is no §2.1.** The ban is
   real; the anchor is not. Also wrong in the CHECK-DEBT D2.14 row and in the gate's own
   docstring — both corrected.
3. **§0 cites "§2A, §4, §14" and the tasks reference "invariant 2" and "invariant 5" — those are
   not in §14.** §14 exists (`:965`, "Locked Invariants") but is an **unnumbered** list with
   different content. The numbered invariants 1–5 are in **§2A at `:103`–`:108`**. Load-bearing,
   since invariant 2 is this arc's subject.
4. **§1's claim about the hook comment is stale.** The brief says the comment "claims removing
   exit-5 tolerance closed this". It did not — ARC 017 had already replaced that with a
   `MEASURED CORRECTION` block saying the opposite.
5. **§6/C4's ~42% figure exists nowhere on disk**, so "both call themselves broker-order percent"
   overstates the situation. There was nothing to retire mechanically.
6. **§8 mis-attributes `err 201` to ARC 012.** ARC **010** established it (`SESSION.md:457`,
   D1.11); ARC 012 established the margin figure readable out of the rejection text (`:594`).
7. **§5 B2's "following A1(a)'s pattern *exactly*" is not achievable.** A1(a) extended an existing
   type on an existing field; `on_ack` has no field to extend and folding cause into `AckStatus`
   would conflate two facts. Principle followed exactly; mechanism necessarily different.
8. **§5's premise that the reason field might be unconsumed is contradicted by three sites.**
9. **§6/C2 offers "a declared marker the seam itself owns"** without noting it requires a write to
   `scripts/broker/**`, which the same brief forbids sub-agent C in §3.
10. **§6/C4 asks to "register the scheme identifier alongside the value"** while
    `derived_claims.json`'s own scope statement reads *"v1: numeric claims only"*. Resolved by
    carrying the identifier in the claim `id`/`property`, but it is a tension in the brief.

Plus one defect not in the brief but in the tree: **`CLAUDE.md`'s `debug.md` version** (§9).

---

## 14. Percent moved — scheme `sec2a-element-v1`, named per §9.5

* **broker-order: 56%** — `100 × 9 CLEAN / 16 §2A roster elements`, machine-derived every run
  from two independent denominators and registered as
  `broker_order_percent_sec2a_element_v1`. **Unchanged by this arc**, and that is the honest
  reading: ARC 018 changed no ARC 014 grade. It hardened *how the order path is proven*, not how
  much of it exists. Readiness commentary is deliberately not expressed as a percent (C4).
* **apparatus (the check/gate system): ~+18 points, and this is an estimate, not a derived
  number** — there is no registered scheme for it, and inventing one would be the anchor these
  gates exist to remove. What it derives from, all pasted above: per-hook can-fail 7/8 → **8/8**;
  registered claims 7 → **9**; the runtime gate moving from "green on zero tests" to a six-verdict
  taxonomy with its own tests; and the ban gate gaining three AST retry shapes plus
  content-derived scope.
* **whole project: ~+3 points, estimate on the same basis.** The apparatus is not the product. No
  strategy, Limiter, capture, bus, or datafeed work happened, and the live confirmation that would
  certify the one user-visible change is still owed as R1-A.

---

## 15. What is owed next

1. **R1-A live confirmation** of the rejection taxonomy on `clientId=905` (§12).
2. **D2.14's three residuals** — recursion, indirection past one hop, cross-thread retry.
3. **D2.15's call-site case** — the Limiter, which is both the likeliest home of a real retry and
   the thing that will re-test C1's false-positive rate.
4. **D1.19 / D1.20** — structured `AckProvenance`, and the `_mirror_stale` latch, both of which
   discharge with the Limiter.
5. **D1.10** — nothing asserts the hook suite is *installed* or its hook set intact; the cached
   pre-ARC-010 bandit environment is recorded there as owed.
