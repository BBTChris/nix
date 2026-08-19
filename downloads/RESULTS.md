## ARC 041 — ULTRAREVIEW: Limiter, slice 3 of many — commit-before-validate torn state (I7)

**Tier: INTERIOR.** Limiter badge **STAYS RED**. Not the greening slice.
**Canonical path: `/home/bbt/nix`** (absolute).
**Predecessor: the brief names `a70a2c4`; the ACTUAL tip was `f5f517c`** — ARC 040 banked a second
commit (its post-write-back re-measure) after `a70a2c4`. Both baselines are shown under FREEZE
below, because a diff against the wrong one would have attributed 040's write-back to this arc.
Interpreter for every measurement: `/home/bbt/nix/.venv/bin/python` → `/usr/bin/python3.14` (3.14.4).

### KICKOFF — the invariant count, DERIVED, and a correction to ARC 040

Read from the tree (`sessions/SESSION.md:4527-4645`, the ARC 038 pass-1 register), verdict token per
invariant — not from prose:

| | |
|---|---|
| CLEAN at 038 | **I6**, **I9*** , **I10**  (*I9 = "CLEAN as a property; its gate is not" — qualified) |
| CLEAN via 040 | **I5** (the GO-timeout) |
| clean at this arc's START | **{I5, I6, I10} = 3/12**, open = **9** |

**ARC 040 wrote "Eleven invariants remain open". That was never true.** It computed `12 − 1` — its
own discharge — and ignored that I6 and I10 were already CLEAN in the 038 register. The figure at
040's close was **nine**. A count of a moving set restated in prose instead of derived: directive 3,
on a line an arc wrote about its own result. Corrected here and in the CHECK-DEBT series row.

### S1 — REPRODUCE FIRST. One half would not reproduce, and that is the finding.

Bound to the real sites: `scripts/nixrisk/picture.py` — validation at **:403**, the `_current` store
at **:413**, the guard released at **:416**, `publish()` called at **:417**.

**ARM 1 — 038's original commit-before-validate: NOT REPRODUCIBLE. Already fixed.**
ARC 038 (sub-agent D, finding FD1) discharged it *inside the freeze*, and the code carries the fix
with its citation. Driven anyway, because a defect assumed absent is not a defect measured absent:

```
BEFORE  version=2 balance=10000.0 committed=0.0 deployable=7000.0 rows=1
commit(sum_reservations=-inf) RAISED TornPicture   <-- non-vacuity: validation DID fire
AFTER   version=2 balance=10000.0 committed=0.0 deployable=7000.0 rows=1
wire = [2] (unchanged)   refusals=1 commits=1 publishes=1
```

The refusal did not mutate what it refused. **Half 1 of I7 was already discharged before this arc
opened**, which the brief's premise did not know. Reported rather than re-fixed.

**ARM 2 — CHECK-DEBT D3.386: REPRODUCED EXACTLY.** `commit()` released `_writing` at :416 and only
then called `publish()` at :417, so the sink ran **outside** the single-writer guard:

```
book._current.version = 3
WIRE (order pictures reached the sink) = [3, 2]      <-- NON-MONOTONE
re-entrant commit refused by = None                  <-- not refused at all
```

A mirror applying wire order ends holding **v2 while the book holds v3**. Nothing detects it: the
transport `_seq` is monotone by construction so it rises across both sends, and `picture_defects()`
is empty on both because each picture is internally coherent. That is I7's half 2 — *publish emitted
a state `_current` does not hold* — and it was the arc's real work.

### S2 — the implementation, picture module only

1. **`publish()` moved INSIDE the `try` whose `finally` clears `_writing`.** A sink that re-enters
   `commit()` is now refused **by name** with `ConcurrentWriter`. §9/§12.10 make the Limiter the sole
   writer and §5 makes it single-threaded, so a re-entrant commit is a design violation and §17's
   answer is to refuse it loudly, not serialise it behind a lock.
2. **`publish()` refuses any picture that is not `self._current`, by IDENTITY.** A picture can pass
   every `picture_defects` test and still be the wrong one — an older version, or a foreign object —
   and §12.7's mirror has no defence against a snapshot that arrives complete and stale. The two
   refusals are ordered **defects-first** so every existing field-level reason string is unchanged.

**ARC 038's stated cost of repair (1) does not apply, and the reasoning is recorded rather than waved
past.** D3.386 warned that moving `publish` inside the guard makes a transport failure leave
`_current` advanced. But the STORE already preceded the PUBLISH before this change — that was already
the behaviour. Moving the call inside the guard changes **who may re-enter**, not the order of the two
operations. The genuine open question (should a transport failure roll `_current` back?) is an
architect ruling and is banked as **D3.428**, not taken here.

No new helper, so nothing built-but-uncalled. No retry, no auto-resend.

### S3 — both directions, with CONTINUOUS sampling by a real reader thread

A property about a *window* cannot be proven by one sample taken after it closed.

**(a) validation-failing commit ⇒ no advance, no torn read**
```
_current BEFORE = v2 balance=10000.0 rows=1     _current AFTER = v2 balance=10000.0 rows=1
rejecting publish fired: True
reader took 1,217,538 continuous samples across the window
DISTINCT pictures the reader ever observed: [(2, 10000.0, 1, 0.0)]     wire emits: 0
```
One distinct picture across 1.2M samples, and it was the old valid one.

**(b) valid commit ⇒ one advance, published == committed, atomic**
```
advanced exactly once: True (v1 -> v2)
published == committed field-for-field: True    published=(2,25000.0,2,0.0) committed=(2,25000.0,2,0.0)
balance+table moved TOGETHER (no half-advanced sample): True   [4,719,020 samples]
no delayed second emit after watching 0.30s PAST the op: True
```
Watching past the operation is the §0a trap closed: stopping at success proves only *not diverged
yet*.

**(c) the D3.386 arm** — re-entrant sink refused by name (`ConcurrentWriter`), wire `[2]` monotone,
last emit == book version. **(d)** a clean-but-foreign picture is refused.

### S4 — the gate. A DELIBERATE DEVIATION FROM THE BRIEF, and why.

**The brief named a new file `checks/check_commit_publish_atomicity.py`. I did not create it.**
`VERIFY-AND-CHECKS.md` Part C.9 — which the brief itself instructs be read directly — states:
*"Extend an instrument that already owns a property; never build a second. Two instruments measuring
one property will disagree, and you will not know which is right."* `checks/check_picture_atomicity.py`
already declares `scripts/nixrisk/picture.py` its subject and already owns the property *"the
financial picture is observable only as one self-consistent snapshot under one version stamp"* —
which is the sentence both halves of I7 live inside. The arms landed **in that gate**.

Two arms, each closing the other's escape (the `debug.md` Tier-2 Stage 2 answer, recorded as required):
* **`_arm_order` (STATIC)** — AST proof that validation dominates the `_current` store and that
  `publish` sits inside the guarded `try`. **Structural, not a spelling match**: it identifies the
  validate step by SHAPE — a bound call whose result is tested by an `if` that raises — so renaming
  `picture_defects` cannot defeat it. Its escape is a decoy validator returning `[]`.
* **`_arm_emit_identity` (LIVE)** — drives a refused commit, a re-entrant sink, and a foreign publish,
  with non-vacuity asserted in front of each verdict. Kills the decoy. Its escape is timing.

**Demonstrated FAIL, three plants, each exit 1 naming the site:**

| plant | verdict | what it reported |
|---|---|---|
| **A** store before validate | `fail_needs_operator`, exit 1 | static: `['store','validate','publish','unguard']`; live: *a REFUSED commit advanced `_current` from version 2 to 3* |
| **B** publish outside the guard | `fail_needs_operator`, exit 1 | static: `['validate','store','unguard','publish_OUTSIDE']`; live: *answered with `None`, not ConcurrentWriter … the wire received `[3, 2]` for a book holding version 3* |
| **B2** identity refusal removed | `fail_needs_operator`, exit 1 | live: *publish() emitted version 1 while the book holds 2* |

Plants removed ⇒ `pass`, exit 0. Every verdict carries its measured reason, not a constructed code.

### FREEZE — held, and tighter than allowed

`git diff --stat f5f517c` is **four paths**: `scripts/nixrisk/picture.py` (the fix),
`checks/check_picture_atomicity.py` (the two arms), `docs/CHECK-DEBT.md`, and this arc's own brief.
**Nothing in `limiterd.py`, `projection.py`, `loop.py`, `recovery.py`, or the WAL** — I8 and D3.425
are untouched and remain ARC 042. **No test file changed**: the fix invalidated none, and the
existing `test_check_picture_atomicity.py` exercises the new arms (it goes RED against the pre-041
module — see the closure's non-vacuity below).

### CLOSE-OUT — INTERIOR tier (a STATED decision, not a silent skip)

Full ~3400-test pytest and the full binding census **DEFERRED to the greening slice**.

* **(b) DERIVED reverse-dependency closure** — 13 test modules grepped as importers of the picture
  module: **239 passed, 0 failed**. **Non-vacuity proven before trusting green**: run against the
  PRE-041 module the closure goes **RED (2 failed)**, so it genuinely contains the changed file's
  dependents. **Cost-aware exclusion, and its own correction:** the mandated shell-out scan excluded
  `test_arc038_c_exit_brake.py` on one hit that proved to be **the phrase "binding census" inside a
  comment** — a false positive, caught by re-reading the exclusion before trusting it. The test was
  put back and passed. Recorded as **D3.429**.
* **(c) BINDING re-established.** Check contract v2 **rule 9** is the governing rule and it applies
  squarely: *a retrofitted check is a NEW check; its can-fail binding does not survive the retrofit.*
  Re-established from three observed real FAILs above.
* **(d) CHECK-DEBT reconciled.** **D3.386 DISCHARGED** with the ruling written down. **D3.428** and
  **D3.429** opened. Series row re-derived whole: 378 → **379** (+2 opened, −1 discharged).

### Residual — explicitly NOT claimed as done

* **D3.428** — a sink/transport failure still leaves `_current` advanced with nothing on the wire.
  Not new, not introduced here, and now written down as the choice it is. **Architect ruling, not a
  cc fix.**
* **I8 (sole-writer enforcement) and D3.425 (the Plane-1 `go_timeout` row) remain open** — ARC 042.
* I7's other 038 residuals — no writer identity on `tbl.financial_picture`, freshness keyed on age
  alone, the §12.7 restart rebuild reaching no connected consumer — are the MIRROR seam, not the
  commit/publish seam, and are untouched by this slice.

### BADGE VERDICT — Limiter STAYS RED

**I7 discharged** (both halves: one already fixed at 038 and re-measured here, one fixed and gated
here). **clean = {I5, I6, I7, I10} = 4/12, open = 8.**
Next: **ARC 042 = I8 (sole-writer enforcement) + D3.425 (the Plane-1 `go_timeout` row)**.
