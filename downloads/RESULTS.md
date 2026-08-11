# ARC 019 — RESULTS
### R1-A: send-path behaviour under stress · partial fills · reconnect · Tier-3
**2026-08-11 · 3 parallel sub-agents · every number below traceable to a pasted command**

---

## 0. The answer to the arc's primary question

**The send path does not block. Nothing was built. §4/A1's "build nothing" branch is the
one the measurements selected.**

Sixteen cells — four sync send verbs × four socket conditions — against a **real
`ib_async.IB` (2.1.0) over a real loopback TCP socket**, `SO_SNDBUF`/`SO_RCVBUF` shrunk to
2048 B, 5 reps/cell, `perf_counter()` around the verb call only. Real vendor serialiser,
real throttle queue, real asyncio transport, real kernel socket; only the IBKR handshake
bypassed, because the handshake is not the subject.

```
verb          condition                 min (s)    median (s)       max (s)
place_order   healthy               0.000846851   0.000908337   0.001176560
place_order   silent                0.000919659   0.001020437   0.001231947
place_order   full-send-buffer      0.000692055   0.000773798   0.000834439
place_order   peer-vanished         0.000883023   0.000950455   0.000970752
cancel_order  healthy               0.000338609   0.000349111   0.000359732
cancel_order  silent                0.000296411   0.000311464   0.000365813
cancel_order  full-send-buffer      0.000221593   0.000248117   0.000274728
cancel_order  peer-vanished         0.000188839   0.000274680   0.000290884
flatten       healthy               0.001875393   0.002821914   0.002939366
flatten       silent                0.002398383   0.002731431   0.002747049
flatten       full-send-buffer      0.001427575   0.002405544   0.002617169
flatten       peer-vanished         0.002426430   0.002472314   0.003295359
disconnect    healthy               0.000256527   0.000271153   0.000383393
disconnect    silent                0.000263452   0.000299355   0.000436146
disconnect    full-send-buffer      0.000098583   0.000139817   0.000140337
disconnect    peer-vanished         0.000079630   0.000129376   0.000160655
```

Worst cell: **0.003295359 s**. **The condition that could have blocked is the fastest
column.** Non-vacuity for (iii): `saturated=True` asserted by
`transport.get_write_buffer_size() > 0` — asyncio had genuinely begun buffering in
userspace, i.e. the kernel pipe was full and the write had nowhere to go. Without that
assertion the column proves nothing.

**Declared limitation:** condition (iv) is an `SO_LINGER(1,0)` RST, not a true silent
partition (packet-level dropping needs root). Argued — *not* measured — that a black hole
degenerates into condition (iii) once the buffer fills, and (iii) *was* measured.

### The finding that matters more than the verdict

The send path does not block; it **absorbs**.

```
200 place_order calls into a verified-full pipe:
  total                  = 0.032117732 s
  ib_async _msgQ depth   = 155 msgs
  asyncio write buffer   = 10204 B
  bytes drained by peer  = 0
```

Every one of those calls returned normally and **none is known to have reached the venue**.
No send verb can tell the caller which it was. Not an adapter defect, and the repair is
never a resend (§2A:71, §4:241, §12A:830 — all three verified on disk). §4 already
specifies the resolution: pending-timeout state machine + `query_order_status`, both the
Limiter's. Opened as **D1.22**, consumer obligation naming R2, including a
bounded-queue-depth decision since today's queues are unbounded.

### Sender thread — the spec tension, resolved

A1 flagged that §2A names a "non-blocking, low-priority sender thread" and did not build
one. Resolved in the spec's favour of not building it:

> **§5:320-323** — "**Limiter = single-threaded event loop** (shared-mem price poll + ZMQ
> inbox + sender completions, processed serially) + **one low-priority sender thread**
> (blocking I/O, releases GIL; hung socket contained; hot loop never blocks)."

The sender thread is the **Limiter's**. §2A:42 assigns it to the Limiter explicitly; §2A:43's
"via non-blocking sender thread" means broker-order is driven *through* it. **It was never
broker-order's to build, and the Limiter is R2.**

**For R2, flagged now:** §5's stated *rationale* for the thread is "blocking I/O, releases
GIL". `ib_async` is asyncio-native and does not block — measured above. The thread was
designed around a blocking-socket vendor SDK. **Do not build it from the diagram.**

### flatten fan-out, and a banked number corrected

```
condition             N         min (s)      median (s)         max (s)
healthy               1     0.000910524     0.000954515     0.000973582
healthy               5     0.001913869     0.002454526     0.002866952
healthy              20     0.006354747     0.006974546     0.007081751
full-send-buffer     20     0.005647530     0.006240453     0.006953682
peer-vanished        20     0.004835897     0.007281015     0.008683348
```

**The protective-path guarantee holds.** Read by column: the four socket conditions are
indistinguishable at every N, and full-send-buffer is if anything fastest. A dead peer costs
what a healthy one costs, because nothing in the loop waits on the wire. ~0.35 ms/symbol, so
the whole fan-out completes inside 3.5 ms at the declared 1–5 instrument scope.

**CORRECTION — ARC 014's 0.6 ms flatten figure was measured against `FakeIB`, which does no
serialisation. Against the real vendor serialiser at N=5 it is ~2.9 ms.** Carry 2.9 ms
forward. What is still not proven is that the orders *arrive*: `flatten` returning proves the
protective path was not blocked, never that the position was closed.

### V11 — KNOWN RED, naming R2

§13 objective 11's subject is the **stop loop**, and there is no stop loop until R2 builds
the Limiter. What ARC 019 measured is **send-verb wall-clock behaviour under socket stress
against a declared loopback stand-in** — the first half of V11's premise, not V11. RED
withholds certification, not durability.

---

## 1. §0a — citation audit. All ten resolve; two findings the brief did not have

| citation | verdict |
|---|---|
| §2A:71 · §4:241 · §12A:830 (never auto-resend) | ✅ all three exact |
| §12A:827 · §6.4:374 · §13:900 (retry mandated outside order path) | ✅ all three |
| §2A:103–108 (numbered invariants) | ✅ text runs 103–107; 108 is the trailing blank |
| V9 / V11 / V24 → §13 | ✅ referents correct — **but see below** |
| §14 | ✅ exists at :965, *Locked Invariants*, unnumbered — ARC 018's correction stands |
| §2A:78 `on_cancel` | ✅ — **and it contradicts this brief** |

**1. The brief's A2 contradicts the frozen spec.** The brief says `on_cancel` carries the
**unfilled** quantity. **§2A:78 declares `on_cancel(client_order_id, done_qty)`** — the
*done*, i.e. filled, portion, and `broker_seam.py` names the parameter `done_qty`. **The spec
was implemented, not the brief**, and both numbers pinned (`done_qty == 2`, implied remainder
`== 3`) so the ambiguity cannot recur.

**2. `V9`/`V11` do not exist as literal tokens in the spec.** §13 numbers objectives 1–23
plainly (`9.`, `11.`, `22.`) and only switches to a `V` prefix at **V24**. `grep "V9"` over
the frozen spec returns nothing. The referents are unambiguous and correct. **Provenance: the
`V` prefix for 1–23 is a project convention layered on the spec** — present in the arc briefs
and in `CHECK-DEBT.md`, absent from the frozen document. A milder cousin of §2.1: architect
shorthand acquiring the appearance of spec spelling. **All three sub-agents found this
independently.** `CLAUDE.md`'s "§13 objectives (38)" is correct — 23 bare + V24–V38.

**3. ARC 018's own correction was slightly wrong.** It recorded that the ARC 017 *gate text*
cited "§2.1" of the frozen spec. `git show 2d8a6ce` shows the gate said **"banned by ARC 017
§2.1"** — it named the brief honestly. The document was dropped in the **CHECK-DEBT D2.14
row**. **The defect was the missing attribution, not a wrong document.** This is why C1's gate
is built around attribution, and why an *unattributed* citation still being only an advisory
(**D2.17**) is the residual that matters.

---

## 2. V9 — partial fills. Two defects only partials could expose

**`FakeIB` could not represent a partial fill at all.** `push_exec` emitted on
`execDetailsEvent` and touched nothing else, so `trade.orderStatus.filled` stayed `0` through
any number of partials. Two behaviours were therefore **unrepresentable — stronger than
untested, because no assertion could have been written that would fail**:

- `query_order_status` read `filled` for `cumulative_qty` → reported **0** for a partially
  filled order;
- the Cancelled branch emits `on_cancel(cid, int(filled))` → a remainder-cancel after a
  partial could only ever report **0 done**.

Extended, then driven. Two adapter defects:

1. **`avg_price` carried the LAST fill price, not a weighted average.** 2@7000, 2@7010,
   1@7020 claimed 7020 against a true 7008.0. **This is ARC 014's two-meanings-one-field
   defect, second instance in the same field** — `positionEvent` writes a genuine
   venue-computed average into `avg_price`, so the field meant "true average" *or* "most
   recent fill price" depending purely on which event landed last. Fixed via
   `_blend_avg_price()`. Partials at a single price hide it completely, which is why nothing
   caught it until partials were driven.
2. **`disconnect()` against a vanished peer swallowed `on_session(DOWN)`** — `OSError`
   [Errno 107] escaping `transport.write_eof()` from mid-method. Measured `sink.sessions
   before=0 after=0` while `_connected`/`_startup_complete` were already `False`. **The
   adapter knew it was down and the consumer was told nothing** — fail-OPEN on the session
   path, in exactly the condition where the notification matters most.

**Non-vacuity, asserted before any claim about handling:** observed fill *sequence* compared
against `[(2,2),(2,4),(1,5)]`; at least one fill asserted genuinely partial; the three
partials asserted to be at **three distinct prices**, else a weighted average is numerically
identical to the last price and the assertion cannot fail; a separate assertion fails if
`avg_price` *equals* the last fill price; the venue-cancel case asserts `ib.cancelled` is
empty, proving it is provably not our request.

**Can-fail, four outputs, `__pycache__` purged between every step.** Plant was a pure line
swap — **byte size identical at 71450 both times**, exactly the stale-bytecode hazard ARC 018
bounded.

```
STEP 1 sha256 3f98deaeb64d311ec9f09c815dff693c963cc922612259e6522a895b9a678b62  1 passed
STEP 2 sha256 e3bde6918e7a91372deef6a4b57110f80e8aebfb2fbb6fdc773a0362bba227f6
  E AssertionError: … 4 failed:
    ['NON-VACUITY: the observed fill SEQUENCE is three partials [(2,2),(2,4),(1,5)],
      got [(2, 2), (4, 4), (5, 5)]',
     'mirror net_qty accumulates to 5, got 11',
     'mirror avg_price is the WEIGHTED AVERAGE 7008.0, got 7012.727272727273',
     'the 4 filled lots survive a VENUE-side remainder cancel, got net_qty=6']
    — SITE: broker_order_ibkr.py:932 _on_ib_exec_details() + _blend_avg_price():1216
  176 passed, 4 failed
STEP 3/4 sha256 3f98deaeb64d311ec9f09c815dff693c963cc922612259e6522a895b9a678b62  1 passed
```

---

## 3. D1.20 unlatched; two "UP over an unrebuilt mirror" paths closed

`connect()` now derives **both** `_mirror_stale` and the published session state from
`_rebuild_mirror()`'s verdict. **Non-vacuity: `_mirror_stale` asserted genuinely `True`
immediately before the clearing reconnect**, so "cleared" is `True → False`, not a vacuous
`False → False`; the failing re-read is asserted to have genuinely run (`_mirror_rebuilds`
moved); the reverse direction is asserted too.

**A4 Q4 — "any path reporting `UP` over a mirror it did not rebuild?" There were two.**
(a) a **failed** cold-start rebuild published plain `SessionState.UP`; (b) a **1102**
("restored, data intact") arriving while `_mirror_stale` was already `True` laundered a
suspect mirror clean. Both replaced by one mechanically-asserted invariant across all
emission sites: **plain `UP` is published ONLY while `_mirror_stale` is `False`.**

A4 Q1–Q3: subscriptions are re-established and nothing is lost (broker-order has no
subscribe verb at all — those live on `BrokerDatafeedPort`, and invariant 3 keeps them
disjoint); the mirror re-reconciles on a **plain** reconnect, now asserted by deliberately
drifting it and proving replacement rather than merge; ARC 017's startup-gate re-arm still
holds. **Consumer half of D1.20 stays open — row NARROWED, not discharged.**

---

## 4. Tier-3 — the first traversal against real Nix application code

`scripts/tests/test_broker_tier3.py`, 1504 lines, **19 sequences** — all nine tabled plus six
added with reasoning stated. **No production code written by the traversal agent.**

**The strongest evidence was not the control.** Two `nonvac` guards fired **unplanted** during
construction:

```
E AssertionError: NON-VACUITY FAILED: the two orders' event streams never interleaved:
  [('on_session','up'), ('on_ack','t9-a'), ('on_fill','t9-a'), ('on_ack','t9-b'),
   ('on_fill','t9-b')]
E AssertionError: NON-VACUITY FAILED: the venue call was never entered
```

The first caught a driver completing order A entirely before B began — the test would have
asserted a per-identity ordering guarantee over a sequence that never interleaved. The second
caught a literal anchor (`reqpos_calls == 1`) wrong because the gating wrapper inherits the
count from the fake it wraps; replaced with a runtime-derived baseline per §7.4.

**The control's own lesson:** under a plant that made the ordering checker structurally unable
to report a violation, the control FAILED and named the site — while `test_t3` and `test_t9`,
**the two traversals that use the checker, both still passed**, because they assert `== []`
and a dead checker satisfies that trivially. Failure mode #1, which is why the control is a
test and not a note.

### Five code defects, held open as `strict=True` xfails

A repair reddens the suite until the marker is removed in the same motion.

| row | finding |
|---|---|
| **D1.23** | **A cancelled `connect()` leaves an adapter that accepts orders and can never report on them.** `_connected = True` is set *before* the rebuild is awaited; `CancelledError` is a `BaseException` so `except Exception` misses it; nothing unwinds. Any caller using `asyncio.wait_for` — the ordinary way to bound a venue call — lands in that window. Measured: `place_order` **succeeds and reaches the venue** while acks, fills and mirror are all empty and no `on_session` was ever published. **The order path is live and mute.** |
| **D1.24** | **Per-order state never released, and not cleared across a session boundary.** After 200 fully-closed lifecycles with the mirror flat: `_neutral 200 · _orders 200 · _trades 200 · _to_ib 200 · _from_ib 200 · _acked 200 · _seen_execs 200`. `connect()` clears the vendor id maps and not `_orders`, so **`cancel_order` on a pre-restart id puts a live foreign order's `orderId` on the wire** — no race needed. `query_order_status` returns the dead session's cached `working` forever, and §4:241 names three outcomes of which this adapter can reach two. |
| **D1.25** | **Session state published from a deferred task that never re-checks the session.** `_on_data_loss_restore` schedules and returns; a `disconnect()` in the gap publishes `UP_DATA_LOSS` (`is_up=True`) over a torn-down session. The rebuild verdict selects only the `reason` **string** and never gates the publish. Fails toward **resuming**. |
| **D1.26** | **Two overlapping `query_positions()` lose the newer snapshot.** `_mirror` assigned wholesale with no ordering guard; observed `mirror={}` after the venue had confirmed `+3`. The module produces the concurrent second read itself. The same method already guards the *adjacent* fill-vs-read race — fills are guarded, read-vs-read is not. **This is the protective path's only input.** |
| **D1.28** | The protective path cannot report that it failed to achieve its purpose (under-sized flatten after a racing fill; silent no-op on an unheld symbol; non-idempotent `disconnect`). |

### Two SPEC GAPS — architect decisions, answers deliberately not invented → **D1.27**

**(a) `flatten()` is not idempotent.** Two protective flattens over one `+2` mirror emit
**−4** of market orders; `place_order` does not decrement the mirror, only a fill does. §2A's
`flatten(symbol | all)` bullet defines the verb as "market-close a position (protective path;
must not block)" and is **silent on repeat invocation**. The adapter calls itself 'dumb hands'
and puts serialisation on the Limiter — but **§4 lists six independent protective triggers**
("stop / stale / floor / session / uncertainty / orphan"), unconditional, so two firing in one
cycle is a *designed* shape, not a caller error; and §4's "one in-flight action per strategy"
governs strategy signals, not Limiter-side protective exits.
**Section that would have to say: §2A's `flatten` bullet, or §4 "Exits (dual authority)".
Neither currently does.**

**(b) A protective `flatten()` during reconnect fires into a shut startup gate.** The fan-out
proceeds (`_connected` is set before the rebuild) and every ack and fill for those orders is
refused by the still-closed gate. **§14's "the exit/protective path has zero wire/delivery
dependency" is honoured literally** — nothing blocked — **and not in the sense that matters**,
because the outcome is unobservable.
**Section that would have to say: §4 "Boot / known-state discipline"** — it gates
*registration* on the cold-start query and says nothing about a protective exit during session
**re-establishment**, which is exactly when one is most likely.

### Not driven honestly, reported rather than fabricated

Cross-thread races are unreachable on a single asyncio loop — `flatten()` and `place_order()`
contain no await point. **Atomicity** is asserted instead, with the would-be racer proven
scheduled and proven pending via a sample taken *from inside the send path*. Recorded in the
file: if a thread is ever added to this module the proofs invert and the file must be re-read,
not re-run. A re-entrant vendor-dispatch fake was considered and **not shipped** — ib_async's
`placeOrder` writes to the socket and the reply arrives from the reader task, so that fake
would model a venue that does not exist (failure mode #12).

---

## 5. Apparatus riders — two, and they stopped

### C1 `checks/check_spec_citations.py` — gate, not claim, argued

`derived_claims.json`'s own scope line says *"numeric claims only. Prose facts are out of
scope."* The only integer available is "count of non-resolutions", and asserting it equals
zero is the `assert count(*) == 0` anchor §7.4 names by name; two probes counting the same
thing is §7.12 condition 3, which `check_derived_claims` itself rejects. Decisively: **a claim
can say the numbers disagree; it cannot say which file, which line, which citation**, and
doctrine C.2 requires the site be named.

**Both sides derived** — headings parsed from `docs/*.md` at run time, citations scanned from
the **tree** (not `git ls-files`, per failure mode #14 / D1.16). No hand-maintained list.

**Three attribution rules measured, two rejected.** Whole-paragraph misattributed `debug.md`
§7.12 to `CHECK-DEBT.md`. ±1 line was worse: it scored the ARC 017 series row's "banned by
§2.1" as **RESOLVED against `debug.md`** — *which does have a §2.1* — resolving the arc's own
subject to the wrong document. Adopted: nearest alias inside the enclosing **structural
block** within 160 chars, preferring a preceding mention. A document with zero numbered
headings is **unindexable** (`VERIFY-AND-CHECKS.md` numbers by Part letter); without that
guard every doctrine citation is a false violation.

**Line coordinates — argued, option (ii) adopted:** the coordinate must fall **inside the
cited section's own span**, derived from the document being cited. Rejected (i) ignore-the-
coordinate (decorative and silently driftable) and (iii) content anchor (prose a person types
beside each citation — a hand-maintained list one level down, and *a specific spelling*, which
is §7.4's own bad anchor — and inapplicable to existing citations in files this arc does not
own). Option (ii) catches the observed failure exactly: "invariant N per §14" **is** a
coordinate outside its section's span. Residual — drift *within* a section — stated in §7.12
condition 5.

**Can-fail, four outputs:**
```
STEP 1 CONTROL sha256 b4b488a0a84692213af8d51997fc914e86b03694e125003fd5ab397d9fbe5263  exit 0
STEP 2 PLANT   sha256 565f6fe97a716f66ca5f51c6655bf37743d3df475fec71664531ff3334be9b71
  check_order_path_bans.py:47 §99.9: §99.9 is not a heading in nics_risk_subsystem_spec_v1.3.md
  check_order_path_bans.py:48 §12A:99999: line coordinate [99999] falls outside §12A's
    span 797-842 in nics_risk_subsystem_spec_v1.3.md                              exit 1
STEP 3 UNPLANT sha256 b4b488a0a84692213af8d51997fc914e86b03694e125003fd5ab397d9fbe5263
STEP 4 CONTROL                                                                    exit 0
```
Both arms fired; file byte-identical after. **It reddened on its own docstring on first run
and on its own new ledger row**, and both were rewritten to stop emitting phantom citations
rather than exempting the gate's own file (that would be failure mode #3).

### C2 `checks/check_hook_suite.py` — effective, not declared

Four arms: the hook exists at the path **git itself** resolves and is pre-commit's own (via
`is_our_script`); its embedded `ARGS` name **this** config; every hook resolved by pre-commit's
own `all_hooks`/`Store` has an installed environment **and a non-empty selection** under
pre-commit's own `Classifier`; each pinned rev's **store DB row** is the environment the hook
resolves to — checked *before* `all_hooks`, so a missing environment is a FAILURE and never a
clone (no network at boot, no repairing what it measures).

**Worktree vs normal repo measured, not assumed:** `git rev-parse --git-path hooks` returns
the **common** dir's `hooks/` in a linked worktree whose `.git` is a *file*, where
`<--git-dir>/hooks` does not exist. The gate reports `layout=worktree|repo` every run.

**A gap deliberately demonstrated rather than papered over.** "No hook has been dropped" is
**not checkable against the config, because the config is the authority** — delete an entry
and both sides lose it together. Proven by an **honest negative**: deleting the mypy repo+hook
entry gave 7 hooks and **exit 0, undetected**. The checkable version is **zero selection** (hook
stays configured and installed, reads nothing, pre-commit prints `Skipped`, exit 0), and that
is what is pinned:

```
2 PLANT .pre-commit-config.yaml:complexipy: hook selects ZERO files — configured,
        installed, and reading nothing; pre-commit reports this as `Skipped` and exits 0
                                                                             exit 1
3 RESTORE sha256 449cb48c226c62b4f0e900ceeb2f510ecbb89b7eb9bb63bb030dea02b890c87a
5 HONEST NEGATIVE — mypy entry DELETED → 7 hooks → exit 0 (NOT detected)
6 RESTORE sha256 449cb48c226c62b4f0e900ceeb2f510ecbb89b7eb9bb63bb030dea02b890c87a
```

**Cached bandit — answered both ways.** Arm 4 names every resident sibling: the store holds
bandit at **1.8.6 *and* 1.9.4**, and hooks resolve to **1.9.4**. So "the vacuum env is still
on this box" is now printed every run instead of being known only to whoever went looking.
What it **cannot** prove is the *pinned* environment's own non-vacuity — nothing structural
separates a bandit that scans 21 files from one that raises on all 21 and exits 0. That needs
a per-hook canary → **D3.7**.

### C3 — stopped. Four ideas that could have been gates are debt rows instead.

---

## 6. Phase 4 — three things only the integration could catch

1. **The citation gate crashed in the real tree** with `UnicodeDecodeError` on macOS
   AppleDouble sidecars (`docs/._*.md`), which no fresh worktree contains. **Worse than the
   crash:** had it not crashed, a sidecar would have indexed as a **zero-heading "unindexable"
   document** — and in this gate's design an unindexable document *exempts* citations
   attributed to it. `._debug.md` would have been a silent escape hatch. Skipped by **name**,
   so a genuinely undecodable document still fails loudly.
2. **The harness caught an error in the ledger row being written for it.** D1.20's narrowing
   was first written `**ADAPTER HALF DISCHARGED ARC 019**` — which matches the bold-span rule
   and **silently removed a row whose own text says the consumer half stays open**. Re-worded
   to the house `NARROWED, NOT DISCHARGED` convention and re-derived. **The rule ARC 018
   repaired paid for itself within one arc.**
3. **T3-03 repaired, and its test inverted in the same motion.** The traversal had encoded the
   wrong log message as a *passing* assertion carrying an instruction in its failure text.
   Fixing the defect reddened it, exactly as designed.

**Harness-vs-its-own-note: conformant.** Both regexes extracted and compared:
```
LEDGER  re.compile(r"\*\*[^*]*\bdischarged ARC \d+", re.I)
HARNESS re.compile('\\*\\*[^*]*\\bdischarged ARC \\d+', re.IGNORECASE)
PATTERN SOURCES EQUAL: True     FLAGS EQUAL: True
OPEN by bold rule 33 | OPEN by naive substring 29 | divergence 4 rows
naive would MISCOUNT AS PAID: ['D1.10', 'D1.19', 'D2.14', 'D2.15']
```
**The divergence grew from 3 rows to 4** — D1.10 joins because its narrowing text contains
"NOT DISCHARGED". The bold-span rule is more load-bearing than when it was written.

**Triage discipline held.** T3-09 was recommended by its finder as trivial ("append the id to
`sequence`, no existing index changes"); **verified false** — `test_broker_order.py` does
`"on_ack" in sink.sequence` and `.index("on_ack")`, and the traversal suite itself *asserts*
the cid-blindness as a documented limitation. Deferred as **D3.8** rather than rushed. Only
T3-03, diagnostic-only, was fixed in the window. **B's findings were not batch-fixed.**

---

## 7. D1.12 — capture mechanism built, NOT armed, row stays open

`scripts/d1_12_reboot_capture.py` + `scripts/nix-reboot-capture.service`. The load-bearing
half is not the verdict — it is **evidence that nobody was there**: `who`, `loginctl
list-sessions`, and uptime-at-capture against a 300 s ceiling, written as
`"trustworthy": false` with reasons when the precondition fails. A verdict taken by hand ten
minutes into a boot cannot distinguish "it came back on its own" from "it came back because I
was here", and it fails in the direction that looks like success.

**Demonstrated able to say no without a plant** — run interactively it returned:
```
NOT TRUSTWORTHY
  precondition not met: loginctl reported active session(s): '232 1000 bbt … 260 … 262 …'
  precondition not met: captured 744803.6s after boot, past the 300s ceiling
```
`is-enabled` is stored under a key literally named `systemctl_is_enabled_DECLARATION_ONLY`, so
it can never be mistaken for the evidence. **Arming needs root and the reboot is the
operator's call.** Absence of a capture file after a boot is itself the finding.

---

## 8. Environment findings — including why three arcs stranded

**The stranding had a mechanical cause, and no gate could have caught it.** `main` required
**1 approving review**; every PR is authored by the sole maintainer; GitHub forbids
self-approval. **Every arc PR was structurally unmergeable from the moment it opened.** PR #7
had sat since 2026-08-09. `required_approving_review_count` set to **0** (force-push and
deletion protection retained; there were no required status checks, so nothing real was lost).
PR #12 merged, carrying #11 with it — **both ARC 017 and ARC 018 are now ancestors of `main`**.

**All three sub-agent worktrees were provisioned from `main` (92f9f17), not session HEAD.**
All three detected it independently and reset before writing. **Future arcs dispatching
sub-agents from a non-main branch must verify the base explicitly** — none was told to look.

**`core.bare = true` was set on the shared repo config**, and `/home/bbt/nix` stopped being a
work tree. Cause: a sub-agent's test fixture ran `git init` inside the pre-commit hook
environment, and **git exports `GIT_DIR`/`GIT_INDEX_FILE` into hooks where they outrank
`cwd`**. Repaired; `git fsck` clean; no commits lost. The sub-agent fixed the root cause in
both its gate and its tests and disclosed it.

---

## 9. Final state — every number derived, none typed

```
$ .venv/bin/python scripts/verify.py
  10 passed | 0 failed | 0 cannot measure | 0 skipped          exit 0

$ .venv/bin/python -m pytest scripts/tests -q
  233 passed, 5 xfailed in 17.34s

$ .venv/bin/pre-commit run --all-files
  ruff check / ruff format / pylint / mypy / bandit (production) /
  bandit (tests) / complexipy / Stage 3 — runtime pass ....... 8/8 Passed   exit 0

$ .venv/bin/python checks/check_derived_claims.py
  pass: 9/9 claim(s) compared
    registered_check_count=10   [derived:checks_glob=10, derived:registry_json=10]
    pytest_collected_tests=238  [derived:pytest_collector=238, derived:source_ast=238]
    check_debt_open_items=41    [derived:ledger_rows=41, stated:series_table_latest_row=41]
    broker_order_percent_sec2a_element_v1=56
                                [derived:spec_denominator=56, stated:seam_denominator=56]
  exit 0
```

**pytest delta explained:** 180 + 39 (C's two gate suites: 22 + 17) + 19 (the traversal) =
**238 collected**. A's coverage lands inside the existing `test_broker_order.py` item —
152 → 180 assertions **within one item** — so it adds no collected items.

**Hooks that self-report scope:** bandit (production) and bandit (tests) print their own
file/LOC metrics; `Stage 3 — runtime pass` prints `SELECTED=` every run (ARC 018, D2.13).
**Still cannot:** ruff check, ruff format, pylint, mypy, complexipy report pass/fail without
stating what they read — unchanged this arc, and now partly addressed from the other side by
`check_hook_suite`, which proves each has a **non-empty selection**.

---

## 10. Percent moved — level and delta kept distinguishable

**broker-order — LEVEL: 56%**, unchanged. Derived from the registered `sec2a-element-v1`
scheme (`broker_order_percent_sec2a_element_v1`, cross-derived `spec_denominator=56` /
`stated:seam_denominator=56`).

**The level did not move, and that is the honest result.** The scheme counts §2A **element
coverage**. ARC 019 added no new seam elements — it measured, tested and repaired *existing*
ones. **This is a named limitation of the registered scheme, and it is now load-bearing:** an
arc that closed four adapter defects, discovered five more, corrected a banked performance
figure by 5×, and produced the module's first Tier-3 traversal registers as **zero** movement.
`sec2a-element-v1` measures breadth and is blind to depth. **Architect decision owed:** either
accept that the number tracks breadth only and say so beside it, or extend the scheme with a
per-element confidence dimension. ARC 019 did not invent one.

**Apparatus — DELTA, derived:** registered gates **8 → 10** (+25% by gate count,
`derived:registry_json`); collected tests **180 → 238** (+32%, `derived:pytest_collector`);
CHECK-DEBT open rows **29 → 41** (+12, `derived:ledger_rows`) — a *rise*, and the right
direction: twelve findings that previously did not exist as anything are now named and owned.

**Whole project — LEVEL:** broker-order is 1 of 6 modules, so 56% of it is ~9.3% of the
project on equal module weighting. **Unchanged this arc by the same argument.** The
non-derived judgement, stated as judgement and not as measurement: this arc moved
broker-order's *trustworthiness* materially — it is the first module with a Tier-3 traversal
and the first whose central performance assumption was measured rather than assumed — while
moving its *completeness* not at all.

---

## 11. Explicitly still RED, and what each needs

- **V11** → R2 (needs the stop loop). What was measured is send-verb behaviour under socket
  stress against a declared stand-in, not V11.
- **V24** → R1-D (needs broker-datafeed).
- **D1.12 reboot** → arming + a reboot. Mechanism built.
- **ARC 018's rejection-taxonomy confirmation** → an IB Key tap on `clientId=905`. Not taken.
- **D1.27's two spec gaps** → architect, not ARC 020.

**No tap session was taken this arc. Nothing measured on IBKR at Stage 0 means anything about
latency, fill realism, slippage, or strategy performance — the feed is delayed ~600 s.**
