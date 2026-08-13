#!/usr/bin/env python3
"""No banned construct — and no hand-rolled retry — reaches the order path.

ONE gate, ONE property (`nix_check_contract.md` §5.5, doctrine C.9): *the order
path contains no retry machinery and no loop-blocking call.* All ban classes
live here rather than in two or three gates so they can never disagree about
what "the order path" IS — a second gate would carry a second file-set
derivation, and the two would drift the first time the tree moved. ARC 018
extended this gate rather than adding one for exactly that reason (doctrine
C.9: *extend an instrument that already owns a property; never build a second*).

WHAT IS BANNED, AND WHY (risk spec v1.3):

  retry libraries — `tenacity`, `backoff`, `retrying`
      `nics_risk_subsystem_spec_v1.3.md` §2A:71 —
      `query_order_status(client_order_id)`, pending-timeout resolution
      (**never auto-resend**); §4:241 — the Limiter "issues order-status query,
      **never auto-resends**"; §12A:830 — `PENDING_ACK_TIMEOUT_MS` … "status
      query, **never resend**". A retry decorator on `place_order` turns one
      intended order into two, at the venue, with real money.
      (ARC 019: the document is now named beside these coordinates rather than
      left to context, so `check_spec_citations` can resolve them and
      range-check the line numbers. Verified there on the frozen file.)

  loop-blocking calls — `asyncio.run`, `run_until_complete`, `run_forever`
      `nics_risk_subsystem_spec_v1.3.md` §2A:103-107, invariant 5: the send path
      is non-blocking regardless of vendor.
      `flatten()` is the protective path and MUST NOT BLOCK. Any of these on a
      sync verb parks the calling thread on the event loop.

  hand-rolled retry SHAPES — ARC 018 / CHECK-DEBT D2.14
      The same three spec lines. A PASS from the two arms above has never meant
      "nothing retries"; it meant "no retry LIBRARY and no loop-blocking CALL".
      `for _ in range(3): self.place_order(...)` passed both. Arm (iii) below
      detects the SHAPE structurally.

CITATION CORRECTION, ARC 018 — measured, not inherited. The ARC 017 gate text,
the ARC 018 brief, and CHECK-DEBT row D2.14 all cite "§2.1" of
`nics_risk_subsystem_spec_v1.3.md` as the authority for the retry ban. **There
is no §2.1 in that document.** Its headings run `## 2. Component Model &
Authority Split` -> `## 2A. Broker Abstraction Contract`; grep for `2.1` finds
only 12.1 / 12.10 / 12.11. "§2.1" is the ARC 017 *brief's* §2 prohibition 1,
which is a task document, not the frozen spec. The three real anchors are the
line numbers quoted above and they are what this gate cites. Failure mode #4
(stale literal anchor) found inside a gate's own docstring.

THE BAN LIST IS DATA (`BANNED_MODULES` / `BANNED_CALLS` below), not logic
threaded through the walker. Adding a ban is a one-line edit to a tuple.

THREE ARMS, ALL REQUIRED — none is sufficient alone:

  (i) STATIC BANS. `ast.parse` every `.py` in scope, walking `Import`,
      `ImportFrom`, `Attribute`, `Name`, and every `decorator_list`. Catches
      DORMANT code: a banned import that no current call path reaches is still
      one refactor away from reaching one, and arm (ii) cannot see it because
      nothing executes it.

  (ii) DYNAMIC. Import every order-path module in a SUBPROCESS and read that
      process's `sys.modules`. Catches a TRANSITIVE pull-in: a dependency of a
      dependency that drags `tenacity` in. Arm (i) cannot see that at all — the
      import statement is in a third-party file the scan never opens.

  (iii) RETRY SHAPES (ARC 018). Structural AST detection of the three shapes a
      hand-rolled retry takes. Not a regex over source text: a regex cannot
      tell `for` in a comment from `for` in code, cannot see which calls are
      inside a loop BODY versus its `else`, and cannot resolve an `except`
      handler back to the call it caught. See "ARM (iii)" below.

==============================================================================
SCOPE — DERIVED FROM THE TREE'S CONTENT, NOT FROM A PATH SOMEONE TYPED
==============================================================================
ARC 018 / CHECK-DEBT D2.15. Before ARC 018 the scope was
`ORDER_PATH_DIRS = ("scripts/broker",)` and nothing guarded that the order path
still lived there: a new *file* under `scripts/broker/` was covered
automatically, a new *directory* was not. That is `debug.md` §8 failure mode
#14 — the scope is a list a person edits — sitting inside the gate written to
avoid it.

The scope is now the union of two things, and the anchor is the FLOOR, not the
source:

  DERIVED — every directory holding a module that DECLARES THE ORDER PORT.
      A module declares the port if it defines the roster constant
      `ORDER_PORT_VERBS` itself, or if it defines a class carrying at least
      `PORT_QUORUM` methods named after roster verbs. Both facts are read out
      of the file's own AST, so an adapter added at `scripts/risk/`,
      `scripts/limiter/`, or anywhere else under `SCAN_ROOTS` joins the scan
      the moment it is written, with no edit to this file.

  ANCHOR (floor) — `ORDER_PATH_DIRS`, still `("scripts/broker",)`. Kept so the
      scan cannot collapse below its historical scope if the derivation ever
      misfires, and kept under its ORIGINAL NAME so CHECK-DEBT D2.15's citation
      does not go stale in the act of discharging it.

THE ROSTER ITSELF IS DERIVED. `SEND_PATH_VERBS` is not typed out. It is
`ORDER_PORT_VERBS` (read by AST out of whichever module declares it) MINUS two
exemption sets, each justified below. A verb ADDED to the port therefore lands
in `SEND_PATH_VERBS` automatically and is treated as send-path until somebody
argues otherwise — fail-closed, which is the correct default for a ban.

WHAT THE SCOPE DERIVATION DELIBERATELY EXCLUDES, and why it is load-bearing
rather than a cost saving: **the spec MANDATES retry/backoff outside the order
path.** §12A line 827 — `RETRY_BACKOFF`, "retry policy before declaring
stale"; §6.4 line 374 — "Stale (freshness stamp past threshold, **after
retry/backoff**) => halt new entries AND flatten open"; §13 line 900 —
"Staleness thresholds from measured round-trips; retry/backoff before
'stale'". A poller that retries before declaring a feed stale is implementing
the specification. If this gate's scope ever grows to cover poller code it will
start reddening spec-mandated behaviour, and the repair is then to the SCOPE
boundary (poller code does not declare the order port, so it should never have
been in scope), never to the ban. This is written down here because the
boundary between "banned" and "required" is one directory wide.

Test directories are excluded from the DERIVED half and the exclusion is
derived too: `testpaths` is read out of `pyproject.toml`, not hardcoded. A test
module that defines a fake adapter implementing the port is reported as an
ADVISORY on every run, named and counted, so the exclusion can never become
invisible.

==============================================================================
ARM (iii) — THE THREE RETRY SHAPES
==============================================================================
`SEND_PATH_VERBS` = `ORDER_PORT_VERBS` minus:

  IDEMPOTENT_READ_VERBS — `query_positions`, `query_balance`,
      `query_order_status`, `get_margin`. Retrying a read cannot double an
      order, and for two of them a retry is the SPECIFIED behaviour: §2A:71
      makes `query_order_status` the pending-timeout resolution mechanism, and
      §2A:78-79 declares `get_margin` a "**poll-fallback**". A gate that
      reddened a `query_order_status` poll loop would be reddening the correct
      implementation of its own subject — doctrine B.4 says that gate is
      BROKEN, not strict.

  SESSION_LIFECYCLE_VERBS — `connect`, `disconnect`. §2A: "Vendor specifics
      (auth, wire format, **reconnect**) live BELOW this line". A reconnect
      loop inside the adapter is the sanctioned implementation of the seam.

Everything else in the roster is send-path. Today that is `place_order`,
`cancel_order`, `flatten` — derived, not listed, and printed in `evidence` on
every run so the classification is visible rather than assumed.

  SHAPE 1 `loop_contains_send` — a `for` / `async for` / `while` whose BODY
      (not its `else`) reaches a send-path call. Nested `def`/`lambda`/`class`
      bodies are not descended into: defining a function inside a loop does not
      call it. One level of INDIRECTION is resolved (`INDIRECTION_DEPTH = 1`):
      if the loop body calls a function defined in the same module whose own
      body sends, that counts, because `for _ in range(3): self._do_send()` is
      the same defect with one more hop.

  SHAPE 2 `bounded_counter_send` — a send-path call whose execution is
      control-dependent on a comparison against a counter that is MUTATED in
      the same function (`n += 1`, or `n = n + 1`). This is the retry shape
      that is not a loop: `if self._tries < MAX: self._tries += 1;
      self.place_order(...)` driven by a re-entrant callback. Detected
      structurally from the mutation, NOT from the identifier's spelling — no
      `attempt|retry|tries` name heuristic exists here, because a name
      heuristic is a stale literal anchor waiting to happen.

  SHAPE 3 `except_reinvokes_send` — an `except` handler that calls a send-path
      verb the `try` body also called. That is a retry by definition: the call
      failed and the handler makes it again.

A shape hit inside a module-level `if __name__ == "__main__":` body is an
ADVISORY, not a violation, on the same measured reasoning as the loop-blocking
calibration recorded below: a `__main__` body is provably unreachable by
import.

FALSE POSITIVES ARE THE DESIGN, NOT A DEFECT. A flagged legitimate loop is
recoverable; a missed retry sends two orders. MEASURED against the tree at
ARC 018 (b8ba7ff), before any suppression: **1 hit, on 4 files, 1 of which is
a false positive** — `IBKRBrokerOrder.flatten`, whose `for sym in targets:`
fan-out calls `place_order` once per symbol. That is one order per symbol, not
two per order. It is reviewed and suppressed per-site; see below. The four
in-scope files hold 9 loop constructs and 8 of them produced nothing, which is
the number that matters: the detector is not "every loop", it is "a loop that
reaches a send verb". Those figures are DATED to b8ba7ff; re-derive by running
this gate, which prints every hit and every applied suppression on every run.

NEGATIVE TEST CASE, MEASURED, NOT REASONED. ARC 018 sub-agent B added the first
new loop this directory has seen since the detector was designed —
`ib_reject_category()`, a classification walk over an `IB_REJECT_RULES` table
whose body calls only `all(...)`. It was planted verbatim into a copy of the
tree and the gate returned PASS with no detail, while the shape walker
confirmed it had SEEN the loop (3 loops in the planted file, the new one among
them) and produced only the pre-existing `flatten` hit. It clears BY
CONSTRUCTION — no order verb in the body — not by suppression, and no
suppression row was added for it. That is the discrimination the gate is
supposed to make, tested on a loop nobody wrote for the test.

SUPPRESSION IS PER-SITE, JUSTIFIED, AND SELF-EXPIRING. `checks/
order_path_retry_reviewed.json` holds one entry per reviewed site, keyed by
`(file, qualname, shape, verb)`. Deliberately NOT keyed by line number —
`debug.md` §8 failure mode #4 is the stale literal anchor, and a line number is
one. There is no file-level exclusion, no directory exclusion, and no
`# noqa`-style blanket: those silence a scope, and silencing a scope is failure
mode #14. Three properties make the mechanism honest:

  * an entry with no `justification` or no `reviewed_in` is REJECTED, and its
    rejection is a VIOLATION — a suppression nobody signed is not a review;
  * an entry that matches NOTHING is a VIOLATION — the site moved, was renamed,
    or was deleted, and the review no longer applies to code that exists;
  * every entry is printed in `evidence` on every run, so a suppression can
    never become invisible.

Change the shape, the verb, or the function a suppressed site lives in, and the
suppression stops matching and the gate reddens.

------------------------------------------------------------------------------
ONE DISCRIMINATION, MEASURED WHEN THE GATE WAS BUILT, NOT ASSUMED (ARC 017).
------------------------------------------------------------------------------
The first clean run reddened on `seam_simulate.py:525`,
`sys.exit(asyncio.run(main()))`, inside `if __name__ == "__main__":`. That is
the correct implementation of a CLI driver: `asyncio.run` is the sanctioned way
to start a loop from a script entry point, and a `__main__` body is provably
not reachable by import — arm (ii) imports all four modules and executes none
of it. Doctrine B.4 says a gate that reddens the correct implementation of its
own subject is BROKEN, and the repair belongs to the gate's LOGIC, never to its
SCOPE, so `seam_simulate.py` is NOT excluded and never will be. Instead the
property is stated exactly: *no banned construct on order-path code reachable
by importing it*. A banned CALL inside a module-level `__main__` guard is
therefore recorded as an ADVISORY — counted, named, and printed in `evidence`
on every run, so it can never become invisible — while a banned MODULE import
stays a violation everywhere including inside a `__main__` guard, because the
dependency is then on the order path's requirements regardless of what executes.
`nix_check_contract.md` §5.2 permits calibrating a NEW instrument as it comes
online; it requires the calibration be measured, which is what the site above
is a record of.

------------------------------------------------------------------------------
§7.12 THE STANDING QUESTION — what would have to be true for this gate to PASS
while measuring nothing?
------------------------------------------------------------------------------
Ten conditions, each stated so it could be planted. Conditions 1-3 and 6 are
ARC 017's; 4 and 5 were ARC 017's UNGUARDED entries and are now guarded or
narrowed; 7-10 are new with arm (iii) and the derived scope.

 1. `scripts/broker/` is renamed or removed, so the walk returns an empty set
    and a scan of zero files reports "no violations".
    GUARDED: `_scope()` requires the set to be non-empty AND to contain every
    name in `REQUIRED_MEMBERS`; anything less is CANNOT_MEASURE, never PASS
    (`nix_check_contract.md` §5.3).

 2. The ban tuples are emptied — a data-driven gate whose data is gone scans
    every file and can find nothing.
    GUARDED: `run()` asserts both ban classes are non-empty before scanning and
    reports CANNOT_MEASURE otherwise. This is the vacuity mode unique to
    expressing rules as data, and it has no analogue in a hardcoded gate.

 3. Arm (ii)'s subprocess fails to import the seam at all (no `PYTHONPATH`, a
    syntax error, a missing venv) and its empty `sys.modules` answer is read as
    "clean".
    GUARDED: the probe reports which modules it actually imported; if that set
    is not the set requested, the arm is CANNOT_MEASURE, not PASS.

 4. The order path grows a SECOND home — an adapter under `scripts/risk/` or
    `scripts/limiter/` — while both required members stay present, so
    non-vacuity passes and the new file is simply outside the scan.
    NOW GUARDED, ARC 018, and this is D2.15's discharge: the scope DERIVES from
    port declaration, so the new home joins the scan by being written.
    RESIDUAL, stated because it is not zero: a module that CALLS the order port
    without DECLARING it — the future Limiter, which will hold `place_order`
    call sites and no port methods of its own — is still outside the scan. The
    Limiter does not exist yet; when it does, the shape that catches it is
    call-site derivation, and it will multiply the false-positive surface by
    the size of the Limiter. That trade is not made here, it is named here.
    SECOND RESIDUAL: `SCAN_ROOTS = ("scripts",)`. Order-path code written
    outside `scripts/` entirely is not walked at all.

 5. Evasion by indirection. `importlib.import_module("tenacity")`,
    `__import__(name)`, or `getattr(loop, "run_until_complete")()` produce no
    `Import` node and no resolvable dotted name, so arm (i) is blind. Arm (ii)
    sees them only if they execute at IMPORT time; inside a function body that
    the probe never calls, both arms miss it.
    STILL UNGUARDED, and ARC 018 assessed it and declined to close it. See
    NAMED GAP 4 immediately below this list — closing it means either flagging
    every `getattr` on the order path (its legitimate uses there outnumber any
    evasion, and `check_structural_conformance` is built on `getattr`) or
    executing order-path code to see what it imports, which on a module that
    can place orders is not a thing a gate may do.

 6. A HAND-ROLLED retry loop is present and undetected.
    NOW GUARDED, ARC 018, arm (iii) — this is D2.14's subject. What a PASS now
    means: no retry LIBRARY, no loop-blocking CALL, and none of the THREE named
    retry SHAPES on any in-scope module. It still does not mean "nothing
    retries" — see conditions 7 and 8.

 7. UNGUARDED — retry by RECURSION. `def _send(self, n): ... except: return
    self._send(n - 1)` is a bounded retry that is not a loop, and shape 3 does
    not fire because the handler calls `_send`, not `place_order`. Shape 1's
    one hop of indirection catches the LOOP form of this, not the recursive
    form. Closing it needs call-graph reachability with cycle detection, which
    is the "different and harder gate" CHECK-DEBT D2.14 named; arm (iii) is the
    cheap two-thirds of it, not the whole.

 8. UNGUARDED — indirection deeper than one hop. `INDIRECTION_DEPTH = 1`, so
    `for _ in range(3): self._a()` where `_a` calls `_b` which sends is not
    detected. Depth is a constant here and raising it is a one-line change; it
    was left at 1 because each additional hop multiplies the false-positive
    surface and depth 1 was enough to catch every shape this tree can express
    today. Plantable: add the second hop.

 9. UNGUARDED — retry across a PROCESS or THREAD boundary. A sender thread that
    re-reads a queue and re-submits, or a supervisor that restarts a worker
    which sends on start, is a retry in behaviour and nothing in any static
    arm can see it. §2A puts broker-order on a "non-blocking, low-priority
    sender thread", so this surface is real and is where the next instance will
    come from. It needs a runtime instrument, not a scanner.

10. UNGUARDED, NARROWED — a suppression entry that is wrong rather than stale.
    A reviewer can suppress a site whose `justification` is plausible and
    false; the gate checks that a justification EXISTS and that the site still
    exists, not that the reasoning is correct. Machine-checking the reasoning
    is not a thing a gate can do. The mitigation is that the key is
    `(file, qualname, shape, verb)` with no line number, so the suppression
    survives formatting and dies on refactoring, and that every entry is
    printed on every run.

NAMED GAP 4 (ARC 018) — DYNAMIC EVASION INSIDE A FUNCTION BODY, ASSESSED AND
NOT CLOSED. `importlib.import_module(name)` where `name` is computed, or
`getattr(obj, verb)()` where `verb` is computed, defeats arm (i) by construction
(no `Import` node, no resolvable dotted name) and defeats arm (ii) by never
running at import time. Three closures were considered and all three cost more
than the gap:
  (a) ban `importlib.import_module` / `__import__` on the order path outright.
      Cheap and enforceable — and it forbids a legitimate construct on the
      argument that it COULD be misused, which is the shape doctrine B.4 calls
      broken. There is no such call on the order path today, so the ban would
      be a rule with no subject, asserting nothing until the day it blocks
      something legitimate.
  (b) flag every `getattr` with a non-literal attribute name. The order path
      has `getattr` at `broker_seam.py:717` and `:747`
      (`check_structural_conformance` / `check_await_conformance`) where
      computed `getattr` IS the mechanism — the conformance checkers exist to
      look up verbs by name. Reddening them is reddening the correct
      implementation of the seam's own instrument.
  (c) execute the order path under an import hook or audit hook and observe
      what it really pulls in. This is the only closure that actually measures
      the property. It requires RUNNING code whose whole purpose is to place
      orders at a venue, inside a gate that runs at boot and every Saturday at
      03:00. Arm (ii) already goes as far as this is safe to go: it IMPORTS,
      and executes nothing.
  VERDICT: not closeable at acceptable cost. Recorded here rather than
  half-closed, because a half-measure would make the gap look addressed.

Conditions 5 and 7-10 are named rather than fixed because a gate whose limits
are undocumented is one refactor away from meeting them silently.
"""

from __future__ import annotations

import ast
import json
import subprocess  # nosec B404 - fixed argv, shell=False, no user input
import sys
import tomllib
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# R0801 (duplicate-code) is disabled at module scope for the two ARC 017 gates.
# nix_check_contract.md §4.2 requires every checks/check_*.py be independently
# runnable and map status -> exit code identically, and doctrine B.2 requires the
# crash path return CANNOT_MEASURE in both. Those blocks are therefore MANDATED to
# be the same text; the only way to deduplicate them is a shared helper, which
# §4.2 is precisely what forbids. Same reasoning as the tail pragma every other
# check carries, hoisted to module scope because R0801 is reported at line 1.
# pylint: disable=duplicate-code
#
# C0302 (too-many-lines) disabled, ARC 018. The split was MEASURED, and the
# measurement is deliberately NOT restated here — doctrine B.7 / CHECK-DEBT
# D2.8, and .pre-commit-config.yaml carries the same refusal for the same
# reason. Derive it, do not read it:
#   .venv/bin/python -c "import ast,pathlib;s=pathlib.Path(
#     'checks/check_order_path_bans.py').read_text();d=ast.get_docstring(
#     ast.parse(s),clean=False);print(len(s.splitlines()),
#     len(d.splitlines())+2)"
# What that command showed when this pragma was added: the module is over
# pylint's 1000-line default even with EVERY line of the module docstring
# removed, so trimming prose cannot fix it.
# Two doctrine rules put it there and neither is negotiable: debug.md
# §7.12 requires the standing question be answered IN WRITING BESIDE THE GATE
# (ten conditions here, each stated so it could be planted), and doctrine C.9
# requires this property be owned by ONE instrument, so all three arms and one
# scope derivation live in one file by design. Splitting the file to satisfy a
# line count would either move the §7.12 answer away from the gate or create the
# second instrument C.9 forbids. Recorded here rather than silently suppressed.
# pylint: disable=too-many-lines
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- ARC 024 orchestration declarations (read statically, never imported) ---
#: ARC 025: the ORDERING half of the same repair the RESOURCES comment below
#: describes. Declaring `venv` stops this check being co-scheduled with
#: `check_venv`; it does not stop it being ordered BEFORE it. `_probe_python()`
#: prefers `.venv/bin/python3`, so running ahead of the check that proves that
#: interpreter answers means the AST sub-probe can fall back silently and this
#: gate's scope shrinks without anything saying so — the project's recurring
#: tracking-state-sets-gate-scope class, reached through execution order.
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: Opens no socket and restarts no service, but it DOES spawn the venv
#: interpreter (`_probe_python()` at line ~1151 prefers `.venv/bin/python3` for
#: the AST sub-probe). This declaration read `()` with the comment *"reads source
#: files only ... writes nothing"* until ARC 025, when
#: `check_observed_resource_claims` OBSERVED `subprocess:.venv/bin/python3` and
#: reported the declaration as false. It matters: `check_venv` claims `venv` and
#: rebuilds it under `--correct`, so an `--optimize` run that believed `()` could
#: put this check in a parallel block with the check deleting its interpreter.
RESOURCES: tuple[str, ...] = ("venv",)
TIME_BOUND = False
#: §2.3 — NON-CORRECTABLE, and this is the class's charter member. The subject is
#: the order path. Risk spec §4 prohibits auto-resend there for exactly this
#: reason: automatic remediation on the order path converts one intended action
#: into two. A gate that could rewrite the order path to satisfy itself is a
#: strictly worse object than a gate that reports and stops.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is the order path; risk spec §4 forbids automatic remediation "
    "there, because a repair that edits the order path to satisfy its own gate "
    "is the same class of action as an auto-resend"
)
#: Derived at runtime from the tree; the reviewed-suppression registry is the
#: one static artifact this gate reads and is answerable for.
#: ARC 027 (B1). The three order-path modules below are DRIVEN by this gate, not
#: merely named by it: each is opened, `ast.parse`d, and walked by arms (i) and
#: (iii) on every run, each is printed by name in the evidence line, and each is
#: in `REQUIRED_MEMBERS` so a file leaving the derived scope is CANNOT_MEASURE
#: rather than a silent shrink.
#:
#: **The drive was PROVEN, not asserted** (§0e): a banned import was planted in
#: each of the three in turn; the gate went `pass` (exit 0) -> `fail_needs_operator`
#: (exit 1) naming `<file>:<line> <module>: banned retry library '<module>'` — the
#: REASON, not the exit code — and each control was restored byte-identical.
#: `scripts/tests/test_check_order_path_bans_drive.py` re-runs that plant.
#:
#: **What this coverage claim does NOT say.** It says these files are measured
#: for ONE property — no banned construct, no hand-rolled retry on the order
#: path. It does not say `broker_order_ibkr.py` places orders correctly. A
#: SUBJECTS entry is a claim about a property, never a certificate for a module,
#: and `check_artifact_gate_coverage` cannot tell the two apart (D3.19).
#:
#: `broker_seam.py`, `broker_datafeed_ibkr.py` and `ibkr_mapping.py` are scanned
#: too and are deliberately NOT listed: the two datafeed gates already declare
#: them, and two gates claiming one artifact is the ownership ambiguity the
#: coverage ratchet's stale arm would then have to arbitrate.
SUBJECTS: tuple[str, ...] = (
    "checks/order_path_retry_reviewed.json",
    "scripts/broker/broker_order_config.py",
    "scripts/broker/broker_order_ibkr.py",
    "scripts/broker/seam_simulate.py",
)

NAME = "check_order_path_bans"

# --------------------------------------------------------------------------
# THE BANS — data, not logic.
# --------------------------------------------------------------------------
# Root package names. A match on the root bans every submodule with it:
# `tenacity` bans `tenacity.retry`, and `import backoff.types` is caught by the
# same rule that catches `import backoff`.
BANNED_MODULES: tuple[str, ...] = ("tenacity", "backoff", "retrying")

# Call/attribute names. A pattern containing a dot must match the TAIL of the
# resolved dotted name, so `asyncio.run` fires on `asyncio.run(...)` and on
# `aio.run(...)` only if the object is literally spelled `asyncio`. A pattern
# without a dot matches the final segment alone, so `run_until_complete` fires
# on any receiver — `loop.`, `self._loop.`, or bare.
#
# `asyncio.run` is deliberately dotted: a bare `run` would fire on
# `subprocess.run`, which is legitimate everywhere, and a gate that reddens
# correct code is broken rather than strict (doctrine B.4).
BANNED_CALLS: tuple[str, ...] = ("asyncio.run", "run_until_complete", "run_forever")

# --------------------------------------------------------------------------
# SCOPE — the anchor is a FLOOR. The live scope is derived (D2.15).
# --------------------------------------------------------------------------
# Kept under its original name so CHECK-DEBT D2.15's citation of
# `ORDER_PATH_DIRS` does not go stale in the act of discharging the row.
#
# ARC 029 (exit half): `scripts/nixrisk` is CONFIRMED as the order path's second
# home and added to the floor. The Limiter's protective-exit modules fire broker
# orders in-process (flatten.py's zero-wire flatten, coldstart.py's flatten-to-
# flat), so they are order-path code and must be scanned for the same banned
# retry libraries and broker-native stop order-types. The derived scope self-
# healed to include the directory the moment those modules were written (the
# `order_path_scope_files` claim went 6 -> 16 and named the second home); this
# constant is the human confirmation that claim asks for, per its own note.
ORDER_PATH_DIRS: tuple[str, ...] = ("scripts/broker", "scripts/nixrisk")

# Where the derivation looks for a second home. Named in §7.12 condition 4 as a
# residual: code outside these roots is not walked.
SCAN_ROOTS: tuple[str, ...] = ("scripts",)

# Directory names never walked, whatever they contain.
SKIP_DIRS: frozenset[str] = frozenset({".venv", "__pycache__", ".git", "graphify-out"})

# The module-level constant that identifies the seam's own roster declaration.
ROSTER_CONST = "ORDER_PORT_VERBS"

# How many roster verbs a class must define as methods before the module
# counts as an order-port implementation. Four is measured, not guessed: the
# smallest real adapter in this tree (`HollowBrokerOrder`) defines all nine,
# and the highest incidental overlap outside the order path is zero.
PORT_QUORUM = 4

# Non-vacuity floor: the scan is only believable if it reached these.
#
# ARC 027 (B1) added the last two. They were ALREADY scanned — the derived scope
# has held all six `scripts/broker/*.py` since D2.15 — but nothing ASSERTED that
# they were, so a file could leave the derived scope and the gate would go quiet
# about it rather than red. That gap does not matter while nobody is relying on
# the scan of a particular file; it matters the moment this gate is named as the
# thing that COVERS one. `SUBJECTS` now names them, so their scope membership is
# a claim this gate makes, and a claim has to be enforced where it is made.
REQUIRED_MEMBERS: tuple[str, ...] = (
    "broker_seam.py",
    "broker_order_ibkr.py",
    "broker_order_config.py",
    "seam_simulate.py",
)

# --------------------------------------------------------------------------
# ARM (iii) — retry shapes. SEND_PATH_VERBS is DERIVED as
# ORDER_PORT_VERBS minus these two exemption sets. See the module docstring
# for the spec line behind each exemption.
# --------------------------------------------------------------------------
IDEMPOTENT_READ_VERBS: frozenset[str] = frozenset(
    {"query_positions", "query_balance", "query_order_status", "get_margin"}
)
SESSION_LIFECYCLE_VERBS: frozenset[str] = frozenset({"connect", "disconnect"})

# One hop. §7.12 condition 8 records what raising it would buy and cost.
INDIRECTION_DEPTH = 1

SHAPE_LOOP = "loop_contains_send"
SHAPE_COUNTER = "bounded_counter_send"
SHAPE_EXCEPT = "except_reinvokes_send"
RETRY_SHAPES: tuple[str, ...] = (SHAPE_LOOP, SHAPE_COUNTER, SHAPE_EXCEPT)

SUPPRESSIONS_FILE = "order_path_retry_reviewed.json"
SUPPRESSION_KEYS = ("file", "qualname", "shape", "verb")
SUPPRESSION_REQUIRED = ("justification", "reviewed_in")

# Definition nodes the shape walkers do not descend into: defining a function
# inside a loop is not calling it.
_DEF_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
_FUNC_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)
_LOOP_NODES = (ast.For, ast.AsyncFor, ast.While)

MODULE_QUALNAME = "<module>"

# Arm (ii)'s probe. Imports each named module and reports what the interpreter
# actually ended up holding. Printed as JSON so the gate parses a structure
# rather than scraping prose.
_IMPORT_PROBE = """
import importlib, json, sys
wanted = json.loads(sys.argv[1])
banned = set(json.loads(sys.argv[2]))
imported, failures = [], {}
for name in wanted:
    try:
        importlib.import_module(name)
        imported.append(name)
    except BaseException as exc:            # any failure, including SystemExit
        failures[name] = f"{type(exc).__name__}: {exc}"
present = sorted(m for m in sys.modules if m.split(".")[0] in banned)
print(json.dumps({
    "imported": imported,
    "failures": failures,
    "banned_present": present,
    "sys_modules_total": len(sys.modules),
}))
"""


def _dotted(node: ast.AST) -> str | None:
    """Resolve `a.b.c` to 'a.b.c'. Returns None for a computed receiver.

    A subscript or call in the chain (`handlers[0].run_forever`) is
    unresolvable by design — reported as None so the caller does not invent a
    name it did not read. §7.12 condition 5 records that this is a blind spot.
    """
    parts: list[str] = []
    cursor: ast.AST = node
    while isinstance(cursor, ast.Attribute):
        parts.append(cursor.attr)
        cursor = cursor.value
    if not isinstance(cursor, ast.Name):
        return None
    parts.append(cursor.id)
    return ".".join(reversed(parts))


def _call_violation(dotted: str) -> str | None:
    """Match a resolved dotted name against BANNED_CALLS. None if clean."""
    for pattern in BANNED_CALLS:
        if "." in pattern:
            if dotted == pattern or dotted.endswith("." + pattern):
                return pattern
        elif dotted.rsplit(".", 1)[-1] == pattern:
            return pattern
    return None


def _module_violation(dotted: str) -> str | None:
    """Match a module path (or a bare receiver) against BANNED_MODULES."""
    root = dotted.split(".", 1)[0]
    return root if root in BANNED_MODULES else None


def _main_guard_ranges(tree: ast.Module) -> list[tuple[int, int]]:
    """Line ranges of module-level `if __name__ == "__main__":` bodies.

    Provably unreachable by import, which is what makes a loop-blocking call
    legal there and nowhere else. Computed from the AST, never from a filename.
    """
    ranges: list[tuple[int, int]] = []
    for node in tree.body:
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        left = node.test.left
        rights = node.test.comparators
        is_name = isinstance(left, ast.Name) and left.id == "__name__"
        is_main = any(
            isinstance(c, ast.Constant) and c.value == "__main__" for c in rights
        )
        if is_name and is_main and node.body:
            first, last = node.body[0], node.body[-1]
            ranges.append((first.lineno, getattr(last, "end_lineno", last.lineno)))
    return ranges


# A hit is (line, name, why, is_callsite). Kept as a flat tuple so the three
# collectors below stay independent of how a hit is later classified.
Hit = tuple[int, str, str, bool]


def _import_hits(tree: ast.Module) -> list[Hit]:
    """`import tenacity` / `from backoff import x` anywhere in the file."""
    hits: list[Hit] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                hit = _module_violation(alias.name)
                if hit:
                    hits.append(
                        (
                            node.lineno,
                            alias.name,
                            f"banned retry library {hit!r}",
                            False,
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            hit = _module_violation(node.module or "")
            if hit:
                hits.append(
                    (
                        node.lineno,
                        node.module or "",
                        f"banned retry library {hit!r}",
                        False,
                    )
                )
    return hits


def _reference_hits(tree: ast.Module) -> list[Hit]:
    """Any resolvable name or dotted attribute matching a ban."""
    hits: list[Hit] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Attribute, ast.Name)):
            continue
        dotted = node.id if isinstance(node, ast.Name) else _dotted(node)
        if not dotted:
            continue
        call_hit = _call_violation(dotted)
        if call_hit:
            hits.append(
                (node.lineno, dotted, f"banned loop-blocking call {call_hit!r}", True)
            )
        mod_hit = _module_violation(dotted)
        if mod_hit and isinstance(node, ast.Attribute):
            hits.append(
                (node.lineno, dotted, f"banned retry library {mod_hit!r}", False)
            )
    return hits


def _decorator_name(deco: ast.expr) -> str | None:
    """The dotted name a decorator resolves to, with or without a call."""
    target = deco.func if isinstance(deco, ast.Call) else deco
    return target.id if isinstance(target, ast.Name) else _dotted(target)


def _node_decorator_hits(node: ast.AST) -> list[Hit]:
    """Bans among one definition's decorators. Never advisory: applied at import."""
    hits: list[Hit] = []
    for deco in getattr(node, "decorator_list", []):
        dotted = _decorator_name(deco)
        if not dotted:
            continue
        if _module_violation(dotted) or _call_violation(dotted):
            hits.append(
                (
                    getattr(deco, "lineno", getattr(node, "lineno", 0)),
                    f"@{dotted}",
                    f"banned decorator on {getattr(node, 'name', '?')!r}",
                    False,
                )
            )
    return hits


def _decorator_hits(tree: ast.Module) -> list[Hit]:
    """Decorators re-read so a decorated site is reported AS a decorator.

    `@backoff.on_exception` on `place_order` is a different fact from a stray
    reference to the module, and the operator reading the FAIL needs to know
    which one it is.
    """
    hits: list[Hit] = []
    defs = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in ast.walk(tree):
        if isinstance(node, defs):
            hits.extend(_node_decorator_hits(node))
    return hits


# ===========================================================================
# ARM (iii) — RETRY SHAPES
# ===========================================================================


class RetryHit(NamedTuple):
    """One structural retry-shape detection, before suppression is applied."""

    line: int
    qualname: str
    shape: str
    verb: str
    why: str

    def key(self, filename: str) -> SuppressionKey:
        """The suppression key. NO LINE NUMBER — failure mode #4."""
        return (filename, self.qualname, self.shape, self.verb)

    def site(self, filename: str) -> str:
        """The human-readable site string, as doctrine C.2 requires it be named."""
        return f"{filename}:{self.line} {self.qualname} [{self.shape}] {self.verb}()"


def _executed_nodes(bodies: Iterable[ast.AST]) -> Iterator[ast.AST]:
    """Every node reachable from `bodies` without entering a nested definition."""
    stack: list[ast.AST] = list(bodies)
    while stack:
        current = stack.pop()
        yield current
        for child in ast.iter_child_nodes(current):
            if not isinstance(child, _DEF_NODES):
                stack.append(child)


def _called_names(bodies: Iterable[ast.AST]) -> list[tuple[str, int]]:
    """(callee tail name, line) for every call executed by `bodies`.

    Tail-only resolution is deliberate and aggressive: `self.place_order(...)`,
    `adapter.place_order(...)` and a bare `place_order(...)` all resolve to
    `place_order`. A receiver this gate cannot resolve is not an excuse to miss
    the verb.
    """
    out: list[tuple[str, int]] = []
    for node in _executed_nodes(bodies):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            out.append((func.attr, node.lineno))
        elif isinstance(func, ast.Name):
            out.append((func.id, node.lineno))
    return out


def _sending_helpers(tree: ast.Module, send_verbs: frozenset[str]) -> frozenset[str]:
    """Same-module functions whose own body reaches a send-path call.

    This is `INDIRECTION_DEPTH = 1`. A function that IS a send verb is excluded
    — it is the verb, not a wrapper for it, and including it would make every
    call to `flatten` look like an indirection.
    """
    helpers: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, _FUNC_NODES) or node.name in send_verbs:
            continue
        if any(name in send_verbs for name, _ in _called_names(node.body)):
            helpers.add(node.name)
    return frozenset(helpers)


def _loop_hits(
    node: ast.AST, qual: str, send_verbs: frozenset[str], helpers: frozenset[str]
) -> list[RetryHit]:
    """SHAPE 1. Loop BODY (never its `else`) reaching a send-path call."""
    hits: list[RetryHit] = []
    kind = type(node).__name__.lower()
    for name, line in _called_names(getattr(node, "body", [])):
        if name in send_verbs:
            hits.append(
                RetryHit(
                    line,
                    qual,
                    SHAPE_LOOP,
                    name,
                    f"send-path verb called inside a `{kind}` body "
                    f"opened at line {node.lineno}",  # type: ignore[attr-defined]
                )
            )
        elif INDIRECTION_DEPTH >= 1 and name in helpers:
            hits.append(
                RetryHit(
                    line,
                    qual,
                    SHAPE_LOOP,
                    name,
                    f"`{kind}` body at line "
                    f"{node.lineno} calls {name}(), which sends "  # type: ignore[attr-defined]
                    f"(indirection depth 1)",
                )
            )
    return hits


def _try_hits(node: ast.Try, qual: str, send_verbs: frozenset[str]) -> list[RetryHit]:
    """SHAPE 3. An `except` handler re-invoking a verb the `try` body called."""
    tried = {name for name, _ in _called_names(node.body) if name in send_verbs}
    if not tried:
        return []
    hits: list[RetryHit] = []
    for handler in node.handlers:
        for name, line in _called_names(handler.body):
            if name in tried:
                hits.append(
                    RetryHit(
                        line,
                        qual,
                        SHAPE_EXCEPT,
                        name,
                        f"`except` handler re-invokes {name}(), which the `try` "
                        f"body at line {node.lineno} already called",
                    )
                )
    return hits


def _mutated_counters(func: ast.AST) -> set[str]:
    """Names mutated by `n += 1` / `n -= 1` / `n = n + 1` inside `func`.

    Structural, not nominal: no `attempt|retry|tries` spelling heuristic is
    used anywhere, because an identifier pattern is a stale literal anchor.
    """
    names: set[str] = set()
    for node in _executed_nodes(getattr(func, "body", [])):
        target: ast.AST | None = None
        if isinstance(node, ast.AugAssign) and isinstance(node.op, (ast.Add, ast.Sub)):
            target = node.target
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.value, ast.BinOp)
            and isinstance(node.value.op, (ast.Add, ast.Sub))
        ):
            target = node.targets[0]
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def _compared_names(test: ast.AST) -> set[str]:
    """Every name or attribute tail appearing in a comparison inside `test`."""
    names: set[str] = set()
    for node in ast.walk(test):
        if not isinstance(node, ast.Compare):
            continue
        for operand in [node.left, *node.comparators]:
            if isinstance(operand, ast.Name):
                names.add(operand.id)
            elif isinstance(operand, ast.Attribute):
                names.add(operand.attr)
    return names


def _counter_hits(
    func: ast.AST, qual: str, send_verbs: frozenset[str]
) -> list[RetryHit]:
    """SHAPE 2. A send guarded by a comparison against a counter this function mutates."""
    counters = _mutated_counters(func)
    if not counters:
        return []
    hits: list[RetryHit] = []
    for node in _executed_nodes(getattr(func, "body", [])):
        if not isinstance(node, ast.If):
            continue
        guards = _compared_names(node.test) & counters
        if not guards:
            continue
        for name, line in _called_names(node.body + node.orelse):
            if name in send_verbs:
                hits.append(
                    RetryHit(
                        line,
                        qual,
                        SHAPE_COUNTER,
                        name,
                        f"send-path verb guarded by a comparison on "
                        f"{sorted(guards)}, mutated in the same function "
                        f"(bounded retry counter)",
                    )
                )
    return hits


def _scopes(tree: ast.Module) -> Iterator[tuple[ast.AST, str]]:
    """Yield (node, enclosing-definition qualname) for every node in the module."""

    def walk(parent: ast.AST, prefix: str) -> Iterator[tuple[ast.AST, str]]:
        for child in ast.iter_child_nodes(parent):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                nested = f"{prefix}.{child.name}" if prefix else child.name
                yield child, nested
                yield from walk(child, nested)
            else:
                yield child, prefix
                yield from walk(child, prefix)

    yield from walk(tree, "")


def retry_hits(tree: ast.Module, send_verbs: frozenset[str]) -> list[RetryHit]:
    """Arm (iii) over one module. All three shapes, qualname-tagged."""
    helpers = _sending_helpers(tree, send_verbs)
    hits: list[RetryHit] = []
    for node, prefix in _scopes(tree):
        qual = prefix or MODULE_QUALNAME
        if isinstance(node, _LOOP_NODES):
            hits.extend(_loop_hits(node, qual, send_verbs, helpers))
        elif isinstance(node, ast.Try):
            hits.extend(_try_hits(node, qual, send_verbs))
        elif isinstance(node, _FUNC_NODES):
            hits.extend(_counter_hits(node, qual, send_verbs))
    return sorted(set(hits))


# ===========================================================================
# SUPPRESSIONS — per-site, justified, self-expiring. Never file-level.
# ===========================================================================


SuppressionKey = tuple[str, str, str, str]


class Suppressions(NamedTuple):
    """Loaded review registry: usable keys and rejected entries."""

    keys: dict[SuppressionKey, dict]
    defects: list[tuple[str, str]]


def load_suppressions(path: Path) -> Suppressions:
    """Read and VALIDATE the review registry. A malformed entry is a defect."""
    if not path.is_file():
        return Suppressions({}, [])
    payload = json.loads(path.read_text(encoding="utf-8"))
    keys: dict[SuppressionKey, dict] = {}
    defects: list[tuple[str, str]] = []
    for index, entry in enumerate(payload.get("reviewed", [])):
        where = f"{path.name}[{index}]"
        missing = [k for k in SUPPRESSION_KEYS if not entry.get(k)]
        unsigned = [
            k for k in SUPPRESSION_REQUIRED if not str(entry.get(k, "")).strip()
        ]
        if missing:
            defects.append((where, f"suppression missing key(s): {', '.join(missing)}"))
            continue
        if unsigned:
            defects.append(
                (
                    where,
                    (
                        f"suppression for {entry['file']}:{entry['qualname']} is "
                        f"unsigned — missing {', '.join(unsigned)}; an unsigned "
                        f"suppression is not a review"
                    ),
                )
            )
            continue
        if entry["shape"] not in RETRY_SHAPES:
            defects.append(
                (
                    where,
                    (
                        f"suppression names shape {entry['shape']!r}, not one of "
                        f"{', '.join(RETRY_SHAPES)} — suppression covers arm (iii) only"
                    ),
                )
            )
            continue
        keys[tuple(entry[k] for k in SUPPRESSION_KEYS)] = entry  # type: ignore[index]
    return Suppressions(keys, defects)


# ===========================================================================
# SCOPE DERIVATION (D2.15)
# ===========================================================================


class Scope(NamedTuple):
    """What the gate will read, how it decided, and why it may not be believable."""

    files: list[Path]
    dirs: list[str]
    derived_dirs: list[str]
    roster: list[str]
    send_verbs: frozenset[str]
    advisories: list[str]
    complaint: str


def _testpath_dirs(nix_home: Path) -> list[Path]:
    """pytest's own `testpaths`, read from pyproject.toml — never hardcoded."""
    path = nix_home / "pyproject.toml"
    if not path.is_file():
        return []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    paths = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
    return [nix_home / rel for rel in paths.get("testpaths", [])]


def _candidate_files(nix_home: Path) -> list[Path]:
    """Every `.py` under SCAN_ROOTS, minus never-walked directories."""
    out: list[Path] = []
    for root in SCAN_ROOTS:
        base = nix_home / root
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if SKIP_DIRS.isdisjoint(part for part in path.parts):
                out.append(path)
    return sorted(set(out))


def _module_str_tuple(tree: ast.Module, name: str) -> list[str] | None:
    """A module-level `NAME: tuple = ("a", "b")` read by AST, never by import."""
    for node in tree.body:
        target: ast.AST | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        if not isinstance(target, ast.Name) or target.id != name:
            continue
        if not isinstance(value, ast.Tuple):
            continue
        return [
            elt.value
            for elt in value.elts
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        ]
    return None


def _implements_port(tree: ast.Module, roster: frozenset[str]) -> bool:
    """True when some class in the module defines >= PORT_QUORUM roster verbs."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        methods = {m.name for m in node.body if isinstance(m, _FUNC_NODES)}
        if len(methods & roster) >= PORT_QUORUM:
            return True
    return False


def _parse_all(paths: list[Path]) -> dict[Path, ast.Module]:
    trees: dict[Path, ast.Module] = {}
    for path in paths:
        try:
            trees[path] = ast.parse(
                path.read_text(encoding="utf-8"), filename=str(path)
            )
        except SyntaxError, UnicodeDecodeError:
            continue
    return trees


def _relative(nix_home: Path, path: Path) -> str:
    try:
        return str(path.relative_to(nix_home))
    except ValueError:
        return str(path)


def _find_roster(trees: dict[Path, ast.Module]) -> tuple[list[str], list[Path]]:
    """The order-port roster and every module that declares it."""
    roster: list[str] = []
    declarers: list[Path] = []
    for path, tree in sorted(trees.items()):
        found = _module_str_tuple(tree, ROSTER_CONST)
        if found:
            declarers.append(path)
            for verb in found:
                if verb not in roster:
                    roster.append(verb)
    return roster, declarers


def _classify_dirs(
    nix_home: Path, trees: dict[Path, ast.Module], roster: frozenset[str]
) -> tuple[set[str], list[str]]:
    """(derived dirs holding a port declaration, advisories for excluded dirs)."""
    test_dirs = _testpath_dirs(nix_home)
    derived: set[str] = set()
    advisories: list[str] = []
    for path, tree in sorted(trees.items()):
        if not (
            _module_str_tuple(tree, ROSTER_CONST) or _implements_port(tree, roster)
        ):
            continue
        rel_dir = _relative(nix_home, path.parent)
        if any(path.is_relative_to(t) for t in test_dirs):
            advisories.append(
                f"{_relative(nix_home, path)} declares the order port but is inside "
                f"pytest testpaths — excluded from scope, named here so the exclusion "
                f"is visible"
            )
            continue
        derived.add(rel_dir)
    return derived, sorted(set(advisories))


def _blocked(roster: list[str], complaint: str) -> Scope:
    """A scope that measured nothing, carrying the reason it could not."""
    return Scope([], [], [], roster, frozenset(), [], complaint)


def _send_path_verbs(roster: list[str]) -> tuple[frozenset[str], str]:
    """Derive the send-path subset, or say why the derivation is not believable."""
    exempt = IDEMPOTENT_READ_VERBS | SESSION_LIFECYCLE_VERBS
    stale = sorted(exempt - set(roster))
    if stale:
        return frozenset(), (
            f"exemption(s) {', '.join(stale)} name verbs absent from {ROSTER_CONST} "
            f"— a stale exemption silently widens what is allowed to retry"
        )
    send_verbs = frozenset(set(roster) - exempt)
    if not send_verbs:
        return send_verbs, "every roster verb is exempt — arm (iii) would scan nothing"
    return send_verbs, ""


def _files_under(nix_home: Path, dirs: list[str]) -> list[Path]:
    files: list[Path] = []
    for rel in dirs:
        root = nix_home / rel
        if root.is_dir():
            files.extend(p for p in root.rglob("*.py") if p.is_file())
    return sorted(set(files))


def _vacuity_complaint(files: list[Path], dirs: list[str], declared: bool) -> str:
    """§5.3: an empty or incomplete scope is CANNOT_MEASURE, never a PASS."""
    if not files:
        return f"no .py files under {', '.join(dirs)}"
    names = {p.name for p in files}
    missing = [m for m in REQUIRED_MEMBERS if m not in names]
    if missing:
        return f"scope missing required member(s): {', '.join(missing)}"
    if not declared:
        return f"no module declares {ROSTER_CONST}"
    return ""


def derive_scope(nix_home: Path) -> Scope:
    """Derive the file set, the roster, and the send-path verbs at run time."""
    trees = _parse_all(_candidate_files(nix_home))
    roster, declarers = _find_roster(trees)
    if not roster:
        return _blocked([], f"no {ROSTER_CONST} declared under {', '.join(SCAN_ROOTS)}")

    send_verbs, complaint = _send_path_verbs(roster)
    if complaint:
        return _blocked(roster, complaint)

    derived, advisories = _classify_dirs(nix_home, trees, frozenset(roster))
    dirs = sorted(derived | set(ORDER_PATH_DIRS))
    files = _files_under(nix_home, dirs)
    return Scope(
        files,
        dirs,
        sorted(derived),
        roster,
        send_verbs,
        advisories,
        _vacuity_complaint(files, dirs, bool(declarers)),
    )


def _probe_interpreter(nix_home: Path) -> Path:
    """Prefer the venv: its sys.modules is the one the trading code will hold."""
    venv = nix_home / ".venv" / "bin" / "python3"
    return venv if venv.is_file() else Path(sys.executable)


Verdict = tuple[list[tuple[str, str]], list[tuple[str, str]]]


def _guarded_by_main(guards: list[tuple[int, int]], line: int) -> bool:
    return any(start <= line <= end for start, end in guards)


def _ban_verdicts(
    tree: ast.Module, name: str, guards: list[tuple[int, int]]
) -> Verdict:
    """Arm (i) over one parsed module. Returns (violations, advisories)."""
    found: list[tuple[str, str]] = []
    advisories: list[tuple[str, str]] = []
    for line, ident, why, is_callsite in (
        _import_hits(tree) + _reference_hits(tree) + _decorator_hits(tree)
    ):
        site = f"{name}:{line} {ident}"
        if is_callsite and _guarded_by_main(guards, line):
            advisories.append((site, f"{why} — inside __main__ guard, not imported"))
        else:
            found.append((site, why))
    return found, advisories


def _retry_verdicts(
    tree: ast.Module,
    name: str,
    guards: list[tuple[int, int]],
    send_verbs: frozenset[str],
    suppressions: Suppressions,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], set[SuppressionKey]]:
    """Arm (iii) over one parsed module, with per-site suppression applied."""
    found: list[tuple[str, str]] = []
    advisories: list[tuple[str, str]] = []
    used: set[SuppressionKey] = set()
    for hit in retry_hits(tree, send_verbs):
        key = hit.key(name)
        site = hit.site(name)
        if key in suppressions.keys:
            used.add(key)
            reason = suppressions.keys[key]["justification"]
            advisories.append((site, f"REVIEWED SUPPRESSION — {reason}"))
        elif _guarded_by_main(guards, hit.line):
            advisories.append(
                (site, f"{hit.why} — inside __main__ guard, not imported")
            )
        else:
            found.append((site, f"hand-rolled retry shape: {hit.why}"))
    return found, advisories, used


def scan_source(
    path: Path, source: str, send_verbs: frozenset[str], suppressions: Suppressions
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], set[SuppressionKey]]:
    """Arms (i) and (iii) over one file.

    Returns (violations, advisories, suppression keys actually used).
    `site` is `<file>:<line> <name>` — doctrine C.2 requires the gate name the
    specific site, not "a violation was found". An advisory is a banned CALL or
    a retry shape inside a module-level `__main__` guard: named and counted on
    every run, but not a violation, because nothing importing the order path
    can reach it.
    """
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [(f"{path}:{exc.lineno or 0}", f"unparseable: {exc.msg}")], [], set()

    guards = _main_guard_ranges(tree)
    bans, ban_notes = _ban_verdicts(tree, path.name, guards)
    shapes, shape_notes, used = _retry_verdicts(
        tree, path.name, guards, send_verbs, suppressions
    )
    return bans + shapes, ban_notes + shape_notes, used


def _probe_targets(files: list[Path]) -> tuple[list[str], list[str]]:
    """(import names, PYTHONPATH dirs) for arm (ii), package-aware.

    ARC 029: the order path acquired a PACKAGE home (`scripts/nixrisk`, the exit
    half) alongside the FLAT `scripts/broker`. A file in a package imports as
    `<pkg>.<stem>` with the package's OWN parent on the path — importing it by
    bare stem is `No module named 'nixrisk'` the instant it runs a package-
    relative `from nixrisk.seam import`. Walk up while each directory holds an
    `__init__.py` so nested packages resolve; a flat directory keeps the bare-stem
    form it always had. `_`-prefixed stems are excluded as before.
    """
    module_names: set[str] = set()
    path_dirs: set[str] = set()
    for src in files:
        if src.stem.startswith("_"):
            continue
        parts = [src.stem]
        root = src.parent
        while (root / "__init__.py").is_file():
            parts.append(root.name)
            root = root.parent
        module_names.add(".".join(reversed(parts)))
        path_dirs.add(str(root))
    return sorted(module_names), sorted(path_dirs)


def import_arm(nix_home: Path, scope: Scope) -> tuple[list[tuple[str, str]], str]:
    """Arm (ii). Returns ([(site, why)], evidence-or-complaint).

    The second element is evidence on success and a CANNOT_MEASURE complaint
    prefixed 'cannot measure:' on failure — the two are never collapsed (§4.1).
    """
    modules, path_dirs = _probe_targets(scope.files)
    if not modules:
        return [], "cannot measure: no importable module names in scope"
    interpreter = _probe_interpreter(nix_home)
    env_paths = ":".join(path_dirs)
    try:
        proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
            [
                str(interpreter),
                "-c",
                _IMPORT_PROBE,
                json.dumps(modules),
                json.dumps(list(BANNED_MODULES)),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            cwd=str(nix_home),
            env={
                "PYTHONPATH": env_paths,
                "PATH": "/usr/bin:/bin",
                "HOME": str(nix_home),
            },
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [], f"cannot measure: probe did not run ({exc!r})"
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        tail = (proc.stderr or proc.stdout or "").strip()[-300:]
        return [], f"cannot measure: probe output unparseable — {tail}"

    if payload["failures"] or sorted(payload["imported"]) != modules:
        detail = "; ".join(f"{k}: {v}" for k, v in payload["failures"].items())
        return [], (
            f"cannot measure: probe imported {payload['imported']} of {modules}"
            f" — {detail or 'no reason reported'}"
        )
    defects = [
        (
            f"{interpreter.name}:sys.modules[{mod!r}]",
            "banned module reachable by import",
        )
        for mod in payload["banned_present"]
    ]
    evidence = (
        f"imported {len(payload['imported'])} order-path module(s) under "
        f"{interpreter} -> {payload['sys_modules_total']} modules resident, "
        f"0 banned"
        if not defects
        else f"imported {payload['imported']} under {interpreter}"
    )
    return defects, evidence


def _scope_evidence(scope: Scope) -> str:
    """What the scan looked at, and how it decided to. Printed on every run."""
    return (
        f"arm(i)+arm(iii) AST-scanned {len(scope.files)} file(s) over "
        f"{len(scope.dirs)} dir(s) [{', '.join(scope.dirs)}] "
        f"(derived {scope.derived_dirs or '[]'} + anchor {list(ORDER_PATH_DIRS)}): "
        f"{', '.join(sorted(p.name for p in scope.files))}; "
        f"roster {len(scope.roster)} verb(s), send-path "
        f"{sorted(scope.send_verbs)}, exempt "
        f"{sorted(IDEMPOTENT_READ_VERBS | SESSION_LIFECYCLE_VERBS)}; "
        f"{len(BANNED_MODULES)} banned module(s), {len(BANNED_CALLS)} banned call(s), "
        f"{len(RETRY_SHAPES)} retry shape(s)"
    )


def _static_arms(
    scope: Scope, suppressions: Suppressions
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], str]:
    """Arms (i) and (iii) over the whole derived file set."""
    defects: list[tuple[str, str]] = []
    advisories: list[tuple[str, str]] = []
    used: set[SuppressionKey] = set()
    for path in scope.files:
        hits, notes, hit_used = scan_source(
            path, path.read_text(encoding="utf-8"), scope.send_verbs, suppressions
        )
        defects.extend(hits)
        advisories.extend(notes)
        used |= hit_used

    for key in sorted(set(suppressions.keys) - used):
        defects.append(
            (
                f"{SUPPRESSIONS_FILE}:{'/'.join(key)}",
                (
                    "STALE SUPPRESSION — matches no site in the current tree; the "
                    "code moved or was removed and the review no longer applies"
                ),
            )
        )

    rendered = [f"ADVISORY {site} ({why})" for site, why in advisories]
    rendered += [f"SCOPE-ADVISORY {note}" for note in scope.advisories]
    advisory_note = "; ".join(rendered) if rendered else "0 advisories"
    return defects, advisories, f"{_scope_evidence(scope)}; {advisory_note}"


def _cannot_measure(detail: str) -> CheckResult:
    return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=detail)


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Three arms over a run-time-derived file set. Never repairs: source code
    on the order path is not something an unattended engine may edit."""
    try:
        if not BANNED_MODULES or not BANNED_CALLS or not RETRY_SHAPES:
            return _cannot_measure(
                "ban list empty — a data-driven gate with no data "
                "scans everything and finds nothing (§7.12 condition 2)"
            )
        scope = derive_scope(ctx.nix_home)
        if scope.complaint:
            return _cannot_measure(
                f"{scope.complaint} (§5.3: an empty scope is never a PASS)"
            )

        suppressions = load_suppressions(
            Path(__file__).resolve().parent / SUPPRESSIONS_FILE
        )
        defects, _advisories, static_evidence = _static_arms(scope, suppressions)
        defects.extend(suppressions.defects)
        dyn_defects, dyn_note = import_arm(ctx.nix_home, scope)
        defects.extend(dyn_defects)

        if defects:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(site for site, _ in defects),
                evidence=f"{static_evidence}; arm(ii) {dyn_note}",
                detail="; ".join(f"{site}: {why}" for site, why in defects),
            )
        if dyn_note.startswith("cannot measure:"):
            result = _cannot_measure(
                f"arms(i,iii) clean but arm(ii) {dyn_note} — one arm is not the gate"
            )
            result.evidence = static_evidence
            return result
        return CheckResult(
            name=NAME,
            status=Status.PASS,
            evidence=f"{static_evidence}; arm(ii) {dyn_note}",
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1 —
        # exit 1 would report a violation the gate never observed.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


def _print_scope(nix_home: Path) -> int:
    """`--print-scope-count`: the number of .py files the gate will read.

    Consumed by `checks/derived_claims.json` claim `order_path_scope_files` as
    the DERIVED source. The claim's other source counts the same thing from the
    STATED anchor path, so the two diverge exactly when the order path acquires
    a second home — which is the D2.15 event, made visible instead of silent.
    Detail goes to stderr; stdout is one integer, matching the probe contract.
    """
    scope = derive_scope(nix_home)
    if scope.complaint:
        print(f"cannot measure: {scope.complaint}", file=sys.stderr)
        return 2
    print(_scope_evidence(scope), file=sys.stderr)
    print(len(scope.files))
    return 0


# Deliberately duplicated across every checks/check_*.py: the check
# contract (§4.2) requires each module be independently runnable, so this
# block cannot be factored into a shared helper without breaking that.
# The disable pragma must be on its own line, not trailing on the `if` —
# pylint's Similarities checker (R0801) does not honour a same-line
# trailing disable comment here (verified empirically, pylint v4.0.6).
# pylint: disable=duplicate-code
if __name__ == "__main__":
    HOME = (
        Path(sys.argv[2])
        if len(sys.argv) > 2
        else Path(__file__).resolve().parent.parent
    )
    if "--print-scope-count" in sys.argv[1:]:
        sys.exit(_print_scope(HOME))

    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            "check_order_path_bans",
            argv=[a for a in sys.argv[1:] if a != str(HOME)],
        )
    )
