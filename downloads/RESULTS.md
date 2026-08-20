## ARC 046 — I1 SPIKE: the daemon dispatches a cancel completion to §3, and the I1 capstone is now a measured number instead of a guess (INTERIOR)

**Tip DERIVED, not taken from the brief.** `git rev-parse HEAD` at kickoff gave `7671847` (045's
final banked commit). Everything below is diffed against that tip. Banked at **`0ff3dd7`**, across
two sessions — the spike (S1–S5) in one, the commit itself and its own diagnostic tail in another.

### S1 — the gap, reproduced on the live loop, non-vacuously

A reservation really taken (Σ 0 → 2000), a cancel exec report really DRAINED by the loop, and
`on_cancel` never called — plus a real `limiterd` (pid) answering an `on_cancel` command with
`"unknown verb 'on_cancel'; this build serves ['register','go','status','resolve']"`. The
measurement the brief did not predict: the loop did not merely fail to dispatch completions, it
had none. The string `completion` appeared exactly ONCE in the whole Limiter surface — inside
§5:322's own quote in a docstring — and in zero of the 96 checks that existed at kickoff.

### S2 — the mechanism, built once, on cancel

`nixrisk/completions.py` (new) is the parse, §4:214's `(order_id, exec_id)` dedup, and the
dispatch. `limiterd.py` gains the completion ingress, a `LoopHandler` that routes one drained item
to the collaborator that owns it, the §11.3 ledger and §3's handlers as PROCESS state, and a
`reserve` verb — a daemon holding no reservations has nothing for a cancel to release.
`outcomes.py` and `reservations.py` are BYTE-IDENTICAL: `on_cancel` was callable as-is, which
answers D3.442's open half.

### S3 — proved out-of-process, against a real pid

committed 2000 → 0, `dispatched=1`, `released_margin=2000`, `last_source` equal to the file the
stub broker wrote, the report unlinked, and re-delivery of the IDENTICAL exec report leaving
`dispatched=1 duplicates=1` and committed unchanged — with the ledger booking **zero** refusals,
which is what proves the guard was the daemon's, not `reservations.py`'s dedup underneath it.

### S4 — the measurement (the spike's primary deliverable)

1. **Wiring cost:** `nixrisk/completions.py` new (~500 lines: parse, dedup, dispatch,
   `DispatchLedger`), `limiterd.py` +~430 lines (ingress, `LoopHandler`, ledger, `reserve` verb).
   `on_cancel` needed **no adaptation** — callable as-is, closing D3.442's open half.
2. **Reusability:** proven, not hoped — the dispatch/dedup mechanism is now generic over
   `CompletionDispatcher`; wiring a new §2A event is "parse THIS type → route to THIS handler,"
   no new mechanism per path.
3. **Remaining completion→handler paths, enumerated:** fill → open-margin conversion + release
   (central, likely-harder: trade_id mint, §4 two-phase), reject → release, pending-timeout →
   `resolve`, onset-cancel dispatch (I11's `_classify_for_onset`), protective-flatten completions.
   GO-timeout already wired (ARC 042). D3.443's enumeration source (`pending_entries()`) has **no
   production implementation** — blocks a clean count of the onset path specifically.
4. **`limiterd.py` coverage — S4.4, answered YES and APPLIED** (see below): brought under testmon,
   killing the per-arc ~43-minute full-escalated tax this file's `uncovered` status forced on
   every commit that touched it, including all four attempts before this one.
5. **The I1 estimate: NOT stated as a number in the banked record.** The brief asked for an
   explicit arc count; the banked commit message names five remaining paths and flags fill as the
   likely-hardest (trade_id mint, §4 two-phase) without committing to a count. Recorded here as an
   open gap rather than invented: **do not treat this arc as having produced an I1 arc-count
   estimate** — S4 point 5 is unanswered and should be the first thing the next I1-facing arc
   states explicitly, from the actual per-path cost once one more path (fill) is built and its
   real incremental cost is known, not projected from the cancel path alone.

### S5 — the gate: `check_limiter_daemon_dispatch` (new file, rule 8 — new property)

**DRIVEN arm:** a real `limiterd` loop consumes a cancel completion and the reservation releases,
asserted via the completion path, never a direct call. **PLANT A** (dispatch call removed): exits
1, names the loop site, `consumed=1 seen=0 dispatched=0`, committed still 2000.0 — the loop drained
the completion and never told §3. **PLANT B** (§4:214 dedup defeated): exits 1, names the missing
daemon guard AND the ledger refusal it fell through to (`reservations.py`'s own guard, I2's, still
held — the plant proves the DAEMON-level guard is missing, not that nothing stopped the second
release). Plants removed → exit 0. Non-vacuity: PLANT A itself broke the instrument before it
caught the defect on the first pass — the counter lived *inside* the dispatch, so "never arrived"
and "arrived and was dropped" collapsed to one reading; `consumed` was split from `seen`, and PLANT
C keeps that split honest.

### CLOSE-OUT

**(b)** By-detection backstop run per D3.444 (the AST import-graph closure is blind to
Protocol-dispatched callers). **(c)** Gate BOUND from both plants, each naming its own site.
**(d)** CHECK-DEBT reconciled: D3.442 SHRINKS (cancel is now daemon-invoked; `on_reject`,
`resolve_pending_timeouts`, fill, pending-timeout, onset, protective-flatten remain uncalled by any
daemon path), D3.446/447/448 filed. The eight CHECK-A8/A9 exclusions in
`checks/gate_coverage_baseline.json` are **already re-owned 046 → 047** in the committed tree
(verified directly: all eight rows read `"owner": "ARC 047"`) — the arc-boundary re-point the brief
asked to be named in advance is done, not merely promised.

The first commit attempt (escalated pass, 43m47s, `mode=full-escalated
(SCOPE-BLIND:changed-but-uncovered:scripts/limiterd.py)`) blocked with 9 failures, four causes, all
real: the gate's §5:322 citation resolved against the wrong doc by default (attribution line
added); a parametrize comprehension made `check_derived_claims`' AST test count unmeasurable (now a
literal, guarded by an equality assertion); the ARC-TOTAL series row was missing (395 derived vs
392 stated); and, found rather than caused, `test_check_order_path_bans`' module-count tripwire was
two arcs stale — `scripts/nixrisk/outcomes.py` landed in ARC 044 without bumping it, and ARC 044
and ARC 045 both committed on the testmon-SELECTED path that never ran the test
(`runtime_gate.py`'s own hazard #4, verbatim). Re-banked 36 → 38 with both bumps named.

### THE COMMIT THAT WOULD NOT LAND — diagnosed, not guessed at

Four subsequent attempts (all still full-escalated, ~44 min each, since S4.4 had not yet landed)
were reported as dying with no visible cause. Diagnosed from first principles, cheapest checks
first, before touching anything: `df -h`/`-i` on **both** `/tmp` and the filesystem that actually
holds `.git` (root fs, 728G free / 99% inodes free — never the cause); no stale `index.lock`, clean
`git fsck --connectivity-only`; no timeout wrapper around the commit in any script; no live
pytest/testmon process; a healthy `ulimit -n`. All clean. **The mystery dissolved on reading the
FOURTH attempt's own already-captured output** (`scratchpad/arc046/commit{1,2,3,4}.out`, never
previously read past the expensive pytest section): `ruff-check`, `ruff-format`, `pylint`, and
`bandit (tests)` failed **identically across all four attempts** on real, static, reproducible
findings that were simply never fixed between launches — 20× `ISC004` unparenthesized string
concatenation, unformatted files, missing docstrings / `too-many-lines` / `too-few-public-methods`
/ `too-many-instance-attributes`, and four Medium `B108` (hardcoded-tmp-directory) findings on test
provenance labels that are never actually written to disk. Every attempt failed loudly, with a
named reason, on disk the whole time. Never inode exhaustion, never OOM, never a timeout SIGKILL,
never object-store corruption. Fixed in place — parens, inline `# pylint: disable=...` matching
this tree's own established precedent (`capture.py`, `sentinel_kill_drill.py`,
`test_allocator_mirror.py`), `# nosec B108` on labels — with zero semantic change, re-verified by
running each hook with its **exact** configured args (`--fail-on=E,F`, `--skip B101,B404,B603`)
rather than bare defaults, and by running the affected pytest files directly (33 tests, all
passing) before re-running the hooks.

**S4.4 applied in the same pass:** `scripts/tests/test_limiterd_cli.py` (new) imports `limiterd`
in-process and exercises `_parser()` — the out-of-process gate's own documented "FIXED CONTRACT" —
and `pending_ack_timeout_from_config()`, non-vacuously. Verified by direct query of
`.testmondata`'s `file_fp` table (not inferred): `scripts/limiterd.py` now carries a real
fingerprint row, the exact table `runtime_gate.py`'s `read_db()` builds its `uncovered=` report
from. Noted forward in `scratchpad/arc046_freeze_baseline.txt`.

**A repo-wide `ruff check --fix . && ruff format .`, run once per the closing brief's own
instruction, caused real collateral damage** and was caught before staging: it reformatted
`scripts/{harness,monitor,pty_test}.py` (deliberately excluded from these hooks since ARC 035) and
— unexpectedly — reformatted Python code fenced *inside* `databases/schema/nix_db_schema_spec.md`
(the DB schema source-of-truth, byte-identity enforced by `validate_schemas.sh`) and a downloads
brief. All five reverted via `git checkout --` before staging; the final `git add -A` was scoped by
hand afterward, and a stale, already-landed draft (`downloads/CLAUDE_md_STATUS_EMIT_block.md` — its
content is already inside this very file's STATUS EMIT section) was excluded rather than
double-committed. A stale `.git/index.lock` from one of the four earlier dead attempts was also
found and removed, only after confirming via `pgrep`/`lsof` that no live git process held it.

**The real commit: `0ff3dd7`, exit 0, 15 files changed.** All 8 hooks passed — ruff-check,
ruff-format, pylint, mypy, bandit×2, complexipy, and **Stage 3** — in roughly 20 seconds total,
against 43m47s for the first (pre-S4.4) attempt. S4.4's fix is not theoretical; this commit is the
proof.

**Unresolved, reported rather than guessed at:** attempt 4's `pre-commit` line
`- files were modified by this hook` (a genuine tracked-file diff-before/after mismatch, confirmed
from `pre_commit/commands/run.py`'s own source — never mtime-based, never printed as a diff by
pre-commit itself) could not be pinned to a specific file from static evidence. The four tracked
files whose mtimes fell inside that attempt's Stage 3 window (`broker_order_config.py`,
`broker_order_ibkr.py`, `seam_simulate.py`, `capture.py`) were traced to every test that writes to
them and all write into isolated `tmp_path`/`shutil.copytree` fixtures, never the real tracked
file — ruling them out rather than confirming them. Did not recur in the real commit.

### RESIDUAL — explicitly NOT claimed

* **I1 is NOT discharged.** One completion path (cancel) is wired; fill, reject, pending-timeout,
  onset, and protective-flatten are not. The count stays 7/12.
* **D3.442 shrinks, it does not close** — the cancel handler is daemon-invoked now; the other five
  handlers remain uncalled by any production daemon path.
* **S4 point 5 (the I1 arc-count estimate) is unanswered** — see S4 above. Do not restate a number
  for it that this arc did not produce.
* D3.443 (enumeration source, no production `pending_entries()`), D3.446, D3.447, D3.448 (all newly
  filed this arc), D3.428, D3.434, D3.438–D3.441, D3.359/360/361/363 — standing named debt, not
  this slice.

### BADGE

**Limiter STAYS RED. Count STAYS 7/12** — clean = `{I2, I5, I6, I7, I8, I10, I11}`, open = `{I1
(daemon-wiring capstone, this arc's own subject, partially wired), I3, I4, I9, I12}`. This spike
wires one path and (partially) sizes I1; it does not flip an invariant. No board redraw.

### POST-WRITE-BACK RE-MEASURE — predict, then measure, and one self-caught defect before either

**Predicted `91 | 3 | 2 | 0 | 1`** (S5 created `check_limiter_daemon_dispatch` as a genuinely new
gate file, not an extension — the brief's `passed+1` branch). Three standing fails unchanged:
`check_ibgateway_service`, `check_monitor_tui`, `check_uncalled_entry_points` (its row count
shrinks by the now-called cancel-handler symbols, confirmed below). Two cannot-measure, the §17
ECONNREFUSED chain: `check_ibgateway_config`, `check_observed_resource_claims`.

**A diagnostic pass taken BEFORE the formal write-back sequence (not the official post-write-back
measurement, but worth banking as evidence)** read `89 | 4 | 3 | 0 | 1`, exit 1 — short of the
prediction by exactly the two things this arc's own write-back process caught and fixed:

* **A fourth, unpredicted FAIL: `check_untracked_attribution`**, naming
  `downloads/CLAUDE_md_STATUS_EMIT_block.md` — *"work exists in the canonical tree that no commit
  on any branch contains ... if a dispatched agent wrote this, worktree isolation was requested and
  not enforced. Rule on provenance before adopting it."* This file was left over from earlier
  session housekeeping (excluded from `git add -A` as a suspected stale duplicate) and never
  resolved one way or the other. Diffed directly against `CLAUDE.md`'s live STATUS EMIT section:
  same core content, and `CLAUDE.md`'s version is the *more* complete one (it carries the later
  "ARC 041-T" section this draft predates) — confirmed stale, not unique. **Deleted**, not
  committed; the check's own message names the correct fix (don't adopt provenance-less content),
  and this arc does not want a second, decaying copy of already-landed prose in the tree.
* **`check_arc_status_contract` read cannot-measure** — *"no ARC-completed marker in log: run did
  not reach close-out"* — because this session had never once called `scripts/arc_heartbeat.sh`
  before this write-back stage, so the arc's own run log carried no fresh self-verify / teardown /
  marker evidence for THIS session's work (only the earlier session's pre-commit pulses). Not an
  instrument bug and not the ARC 045 ordering artifact exactly — a genuine process gap: this
  session ran the standing heartbeat protocol zero times before now. Closed properly, not
  papered over: `arc_heartbeat.sh selfcheck`, `banner`, and `pulse` run for real into
  `scratchpad/arc_logs/arc_046.log`; a live-watchdog check (`pgrep -af arc_heartbeat`, 0 matches)
  before writing an honest `WATCHDOG TEARDOWN: confirmed dead` line (no watchdog was spawned this
  session — nothing to tear down, stated as such rather than fabricating a pid); **then** the
  log-file completion marker, only once pulses + self-verify + teardown all preceded it.

Corrected in place, not re-fitted after the fact — the miss stands here. Per the fixed order
(write back and commit → re-measure the merged tree → record that re-measurement forward-only into
both files and commit it), this write-back commit records the prediction and the diagnostic pass
above; the official post-write-back measurement — taken against THIS commit, with the log-file
marker now correctly in place before it runs — is recorded in the very next commit, appended below
this line rather than replacing it, and the durability obligations are shown against that final
commit, not this one.

**FINAL — banked forward-only in the next commit.**

`check_uncalled_entry_points`, measured directly rather than restated: **55 uncalled-type findings
measured, 25 rendered** (the check truncates its own evidence and says so —
`checks/uncalled_entry_points_baseline.json:regression:truncated: 30 further finding(s) NOT
SHOWN`), of which `scripts/nixrisk/outcomes.py` contributes **4** rows this arc
(`OrderOutcomes.history`, `OrderOutcomes.on_reject`, `OrderOutcomes.resolve_pending_timeouts`,
`OutcomeRecord.released_margin`) — **`on_cancel` is no longer among them**, exactly the shrink the
brief predicted watching for, now confirmed by name rather than by count alone. A new, unrelated
drift is also named on this same check: `scripts/nixrisk/gate.py::GatePass.manifest` is recorded
`uncalled` in the baseline but measures `gate_only` now — standing debt, not this arc's own defect,
noted forward rather than silently absorbed.

**No count moved beyond the +1 predicted**: 97 registered checks (96 at kickoff + 1 for the new
gate), matching the `passed+1` branch exactly.
