# ARC 035 / Stage 1 / SUB-AGENT B — §0a self-audit

**Written BEFORE the code, committed BEFORE the code** (common brief §2; CHECK-DEBT D3.191: ARC 033
and ARC 034 both lost their sub-agents' reasoning to a session cap that killed them with complete
work staged and unbanked). Updated in place as the work proceeds; the update is a second commit, not
an mtime.

**Branch:** `arc-035-b` · **Worktree:** `/home/bbt/nix-wt-arc-035-b` · **Canonical tree:**
`/home/bbt/nix` (never edited from here).

**Mandate:** B1 the positions projection is rebuildable from the log (§9) · B2 cold-start
reconciliation vs broker truth (§4, §9, §12.1, §12.5) · B3 the crash gap at a real durability
boundary.

---

## THE QUESTION

> *What would have to be true for my deliverable to complete successfully while measuring nothing?*

Twelve conditions below. Each is something a reviewer could plant. Each says how it is closed, or
says plainly that it is **NOT** closed.

---

### B1 — the rebuild

**1. The log is EMPTY, so "drop and rebuild matches" compares nothing to nothing.**
The brief names this one itself: *"an empty-log rebuild proves nothing."* An empty log folds to an
empty projection, which trivially equals the empty projection that was dropped, and every assertion
passes.
*Closed.* **MEASURED, not planned: 39 events, 8 `trade_id`s, 13 of them position-moving, 6
positions, and all three projection states (`open` / `partial` / `closed`) present.** The history
covers an open-and-closed round trip, a partial fill whose remainder is IOC-cancelled, a two-step
scale-out, a still-open position, a denied signal that must yield nothing, a §12.1 sentinel flatten,
an unresolved partial, and a GO-timeout. Every count is asserted in
`test_the_seeded_history_is_REAL_and_its_size_is_asserted`, so a fixture that silently shrinks
reddens rather than passing quietly. The shipped gate carries a floor (`MIN_FOLDED_EVENTS = 8`)
below which its scratch arm is `CANNOT_MEASURE`, not `PASS`, and two can-fail drives exercise it: a
2-event log, and a history in which every trade CLOSES (which would leave two thirds of the fold's
state machine unmeasured).

**2. The comparison is `==` on two objects that are the SAME object**, or on a summary (a count, a
hash of a count) rather than the fields.
*Closed:* the pre-drop projection is read back out of Postgres as a list of tuples of **every column
of `plane1_positions`** plus `plane1_projection_meta.rebuilt_through_event_id`, held in Python, and
compared field by field with a per-field diff message after the rebuild. The comparison never touches
the fold's in-memory objects — both sides come from a `SELECT`, so a fold that never wrote would
produce an empty second side and fail.

**3. The "drop" is not a drop.** `DELETE FROM plane1_positions` leaves sequences, defaults and any
hidden state intact; a projection that secretly survives its own deletion proves nothing about being
*derived*.
*Closed in two strengths.* The shipped rebuild uses `TRUNCATE`, because `TRUNCATE` is the privilege
§9's "rebuildable" actually grants the Limiter (`plane1.sql` grants `TRUNCATE ON plane1_positions`
and nothing on the log). The test additionally does the strong version — `DROP TABLE
plane1_positions`, re-create it from the DDL text extracted out of the **shipped**
`databases/schema/plane1.sql` (with an anchor assertion, so a plant that matched nothing is a red and
not a silent no-op), re-grant, re-fold — and requires the same field-by-field match. If the
projection held state that is not in the log, the DROP variant is where it dies.

**4. The fold reads the projection while building the projection** — a fold seeded from the table it
is rebuilding is not a fold of the log.
*Closed:* `fold_events()` is a pure function `Sequence[LogEvent] -> dict[trade_id, ProjectedPosition]`
with no database access at all. The only reader of `plane1_positions` in the rebuild path is the
verification read that happens *after* the write.

**5. Ordering is taken from `event_id`,** which is assigned at INSERT and therefore is commit order,
not enqueue order — so a fold that "works" only because the fixture inserted rows in the same order
they happened would be measuring the fixture.
*Closed:* the fold orders by `(wal_seq, event_id)` per the schema spec §2.2 (*"the WAL is the only
place ordering is authoritative"*), and one test inserts a fixture whose `event_id` order is the
**reverse** of its `wal_seq` order and requires the same projection.

### B2 — reconciliation

**6. Both sides already agree,** so "reconciled" is the identity function.
The brief names this one too: *"prove reconciliation on a log that is genuinely BEHIND broker truth
(a crash gap), not one already in agreement."*
*Closed:* every reconciliation drive in `test_coldstart_reconcile.py` **starts from a stated
disagreement**, and the disagreement is asserted before the reconcile runs — the test computes the
projection's view and the broker's view, asserts they differ, and names the difference in the
assertion message. A drive whose two sides matched would fail at that pre-assert, before it could
report a green.

**7. The "unexpected position" branch never fires** because the fixture broker returns flat.
*Closed:* the unexpected-position drive returns a broker position for a `trade_id` the projection has
never seen, and asserts (a) the flatten fired, (b) it fired **before** `register()` was admitted —
proven by an attempted `register()` that raises `RegistrationRefused` at the point between — and (c)
the `cold_start_outcome` row names it.

**8. The market-tradable guard is bypassed** — an untradable market is reported as "flattened".
This is the hazard the mandate spells out and it is the FAIL-OPEN direction: reporting a flatten that
never fired.
*Closed:* the untradable drive asserts the outcome state is `HELD_IN_HALT`, `admitted is False`,
`flattened == ()`, and that the reason string names the market reason; and it asserts the **absence**
of any claim of a completed flatten. `flatten_to_flat` raises rather than returning empty on a shut
market, so a caller cannot mistake refusal for "nothing to do" — that guard is R2-B's and is reused,
not re-implemented.

**9. The retroactive HALT is booked by a SECOND writer.** §12.5's Limiter-down case books a `halt_set`
row at next boot; the tempting implementation is a boot-time HALT reader that writes it.
*Closed:* the retroactive booking is a method on `ColdStart` and rides the **same** injected
`Plane1Port` as every other row it books, exactly as §12.1's marker replay already does. Nothing new
authors a row. The mandate's §12.5 reading is checked against the spec text directly: §12.5 says the
system is *already fail-closed* while the Limiter is down (nothing reaches the broker without it), so
**no second flag is needed for safety** — the retroactive row is for Plane-1 *completeness*, not for
safety, and my code and my report say so rather than implying the row is what makes it safe.

**10. Rows are written by a fixture acting as a NEW AUTHOR.** §12.10: *"no new writers, ever"*, and
the common brief extends it explicitly to test fixtures.
*Closed as far as it can be, and NAMED where it cannot.* Every fixture row is inserted through
`SET ROLE nix_limiter` — the Limiter's own database identity, refused for any other role by the
`plane1.sql` grants that `check_plane1_schema` ARM 9 already proves by attempt. **What is NOT closed:**
the seam's `EventKind` cannot emit a `filled` row at all (its own docstring says so: *"STILL OMITTED …
`filled`"*), so there is no Limiter code path today that produces the event the projection is mostly a
fold **of**. My fixtures therefore synthesise `filled` rows at the role level rather than driving a
production fill path that does not exist. That is a real gap, it is reported to the integrator as a
gap, and it is the honest limit of B1's claim: *the fold is proven; the wiring that would feed it is
not built.*

### B3 — durability

**11. The crash is a process kill, so the kernel still owns every dirty page** and a `--no-sync` WAL
reads back intact. The common brief's headline trap.
*Closed — and the closing MEASUREMENT REFUTED THE PREDICTION IN THIS PARAGRAPH.* Postgres claims
are made on my **own ephemeral cluster** (`initdb`, private socket, `listen_addresses=''`) crashed
with `pg_ctl -m immediate`. The primary boundary is the *observed fsync*:
`strace -f -y -e trace=fsync,fdatasync` on the postmaster, requiring a line annotated with a path
under **this cluster's own** `pg_wal/`, with an `fsync=off` cluster as the both-halves control
requiring that line to be **ABSENT**. Same shape as `scripts/wal_kill_drill.py`'s existing arm,
which is reused unchanged for the local-WAL half rather than reinvented.

**THE PREDICTION, AND ITS REFUTATION.** I predicted `pg_ctl -m immediate` would be *vacuous* — that
because SIGQUIT leaves the page cache with a living kernel, an `fsync=off` cluster would recover the
committed rows too, and a crash-only test would be green over a cluster with no durability guarantee.
**Measured on PostgreSQL 18.4, two clusters differing in exactly one setting: the `fsync=off` cluster
came back with no `plane1_event_log` at all.** Redo runs, redo completes, and the schema and its rows
are gone; the `fsync=on` cluster kept all 24 committed rows. So the crash arm DOES discriminate, and
the prediction is **withdrawn and recorded beside its refutation** — `plane1_crash_drill.run_drill()`
returns `predicted` and `measured` fields and the test asserts both are present — rather than quietly
reworded to match the result. What the differential still does NOT license is a power-loss claim:
nothing in the drill drops a page cache.

**12. "The uncommitted tail does not survive" is dressed up as a durability claim.**
*NOT a durability claim, and stated as such rather than closed.* An uncommitted transaction's rows
are invisible and are discarded at recovery whether or not anything was ever fsynced; that arm would
pass under a bare `kill -9` of the postmaster, and it rests on the **transaction** boundary, not on
the durability boundary. It is reported that way. The claim that *does* rest on a real boundary is the
one either side of it: rows whose group-commit **committed** survive (fsync observed), and rows that
reached the local WAL but not Postgres are the crash gap B2 heals from broker truth.

---

## THE BRIEF'S OWN PLANTS — what I looked for

The common brief says to assume it contains **at least one durability claim a process-kill would pass
vacuously** and **at least one hazard stated backwards**. What I found is recorded here as I find it,
and in the final report:

- **Vacuous-under-process-kill:** my mandate's B3 bullet *"the uncommitted tail does NOT survive the
  crash"* is the one, and it survives the measurement above unchanged. It is true, worth asserting,
  and not evidence about durability — an uncommitted transaction's rows are discarded at recovery
  whether or not anything ever fsynced, so it rests on the TRANSACTION boundary and would pass under
  a bare `kill -9`. Reported rather than quietly strengthened, and the drill carries the disclaimer
  in its own `boundary` field so the JSON cannot be read without it.
- **Backwards hazard:** my mandate's B2 bullet reads *"an untradable market cannot be flattened and
  that must not be reported as if it were."* Stated that way the hazard is the report; the **dangerous
  direction** is the one underneath it — a reconciliation that treats "flatten refused" as "nothing to
  flatten" and **admits registration**, which is fail-OPEN into an inherited position. The refusal
  path must deny admission, not merely word its message carefully. Condition 8 is written against the
  fail-open direction, and the assertion is on `admitted is False`, not on the wording.
- Also recorded: the mandate calls `plane1_positions` grants an asymmetry *"that makes the rebuild
  possible"* — correct — but the same sentence could be read as licence to TRUNCATE the log. It is
  not: the Limiter holds no TRUNCATE on the log at all, and `check_plane1_schema` ARM 9 proves it by
  attempt.

---

## WHAT I AM DELIBERATELY NOT DOING

- Not building sub-agent A's Postgres commit sink. My fixtures need a conduit to get rows into a
  scratch log; that conduit is `SET ROLE nix_limiter` + `psql`, it is confined to my fixture and gate
  layer, it is labelled a **conduit** in the code, and the integrator should replace it with A's real
  sink. It is not a second author: it carries the Limiter's role identity and no other.
- Not editing `scripts/nixrisk/seam.py`. Three sibling branches are being merged blind into it and a
  frozen seam is the worst place to take a merge conflict. The consequence is that
  `EventKind` → `plane1_event_enum` needs a **mapping**, the mapping is not one-to-one, and the
  mismatches are findings I report rather than repair: `COLD_START` ↔ `cold_start_outcome`, no
  `SENTINEL_FLATTEN` member (sentinel rows ride `PROTECTIVE_EXIT` + `source=sentinel`), and no
  `FILLED`, `GO_TIMEOUT`, `DRIFT_AUDIT`, `OPERATOR_ACTION` at all.
- Not touching the system PostgreSQL cluster beyond reading it and creating/dropping my own `p1b_*`
  scratch databases.
- Not claiming anything about power loss. An observed `fsync` is a syscall that returned; a disk that
  lies about its write cache is outside every instrument in this tree, and `elements_v2.md` §4's
  backup/DR is a later arc.

---

## WHAT THE WORK CHANGED IN THIS AUDIT — appended, never rewritten (directive 6)

**1. A defect my own test found, in my own fold.**
`test_an_exit_before_any_fill_is_an_ANOMALY_not_a_silent_skip` was written for condition 1's anomaly
path. It failed — not because the anomaly was missed, but because the fold ALSO emitted a phantom
`ProjectedPosition` with `qty_filled = 0` for the trade that never opened. A phantom position in the
table reconciliation reads is exactly the class of failure this projection exists to prevent, and it
would have shipped green under any test that asserted only the anomaly list. Fixed: a trade becomes a
position only once something filled (§4 — *"Open is asserted ONLY on broker fill confirmation"*), and
the anomaly is still reported.

**2. The pre-commit gate corrupted this worktree's git index, and not only this one.**
My self-audit commit ran ~30 minutes against four concurrent gate runs and returned **exit 0 with
`HEAD` UNMOVED**. The index was left with every tracked path staged for deletion, plus a stray
`seed.txt` (content `x`) staged and absent from disk — the signature of a git-hostile test operating
on the real repository rather than a temp dir. `git status --short` showed the same 429-line damage
in worktrees **C and D** (A was clean). Recovered with a plain `git reset`; the working tree was
untouched and nothing was lost. This is CHECK-DEBT material for the integrator, and it is the
sharpest available illustration of the arc's own rule: **an exit code is not a commit, and staged is
not banked.** Every commit here is verified afterwards with `git log` / `git ls-tree`, never by exit
status.

**3. `MIN_FOLDED_EVENTS` was 12 before the fixture existed and is 8 after counting it.**
Stated because a floor tuned to whatever the fixture happens to produce is not a floor. 8 sits below
the shipped fixture's 13 and above every degenerate history the can-fail suite plants, and the two
`CANNOT_MEASURE` drives at the bottom end are what make it falsifiable rather than decorative.

**4. What I did NOT do.** No commit sink (sub-agent A's). No change to `scripts/nixrisk/seam.py` —
so `EventKind` still cannot emit `filled`, `go_timeout`, `drift_audit`, `operator_action` or
`sentinel_flatten`, and `COLD_START` still spells `cold_start` where the schema enum spells
`cold_start_outcome`. Those five mismatches are findings reported to the integrator, not repairs made
blind on a branch three siblings are merging into.
