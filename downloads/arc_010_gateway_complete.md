# ARC 010 — Complete ARC 008 (Parts 1/3/5), VERIFY-AND-CHECKS Reconciliation, Bandit Repair

## Context — read before starting

Three things changed since your last session. **Verify each yourself rather than trusting this
summary**, but these are the expected states:

1. **The IB Gateway login is genuinely done now.** A human completed it over VNC: logged into
   paper account DUR250018, set the API config, restarted Gateway. `jts.ini` is populated and
   something is listening on **port 4002** (`ss` confirmed `LISTEN 0 50 *:4002` owned by the
   Gateway JVM). This unblocks ARC 008 Parts 1, 3, and 5, which you correctly refused to fake
   when nothing was listening. The specific settings the human applied:
   - Socket port **4002**
   - **Read Only API — unchecked** (broker-order must be able to place orders)
   - **Trusted IPs — `127.0.0.1`** present
   - **Allow connections from localhost only — checked**
   - **Lock and Exit — Auto restart at 03:00** (was Auto logoff at 23:45; changed because
     auto-logoff forces a full 2FA re-login daily rather than weekly)

   Verify every one of these against the real `jts.ini` / live socket. If any disagrees with the
   above, report the discrepancy rather than assuming the human's report or this arc is correct.

2. **PR #8 is merged.** The human ran `gh pr merge 8 --merge --admin` successfully. A prior
   handoff of yours claimed it was still open — that was stale. Re-verify `origin/main` fresh.

3. **The real `VERIFY-AND-CHECKS.md` now exists** at `~/nix/downloads/VERIFY-AND-CHECKS.md`. When
   ARC 008 told you to follow it "exactly," it genuinely was not on the machine — you searched
   correctly and found nothing. You then authored your own reconstruction (v1.0.1) and indexed it
   in CLAUDE.md as an authority. That was a reasonable recovery from an impossible instruction,
   but the real document was always external; it simply was never delivered. Part 2 reconciles
   the two.

---

## Part 1 — VERIFY-AND-CHECKS.md reconciliation (do this FIRST)

Everything in Part 3 gets built against this spec, so reconcile before building.

1. Copy `~/nix/downloads/VERIFY-AND-CHECKS.md` into `~/nix/docs/VERIFY-AND-CHECKS.md` — that is
   now the authoritative location.
2. Diff it against your self-authored v1.0.1 (find it wherever you wrote it on
   `arc-009-verify-v2`). Report every **semantic** divergence, not just wording.
3. Re-examine these specific decisions from your last handoff against the real text:
   - **Five-state results** (`PASS`/`FAIL_REPAIRABLE`/`FAIL_NEEDS_OPERATOR`/`CANNOT_MEASURE`/
     `SKIPPED`) — does the real doc specify this, or is it your addition beyond it? Either is
     fine; say which.
   - **"Disruptive gates the repair, not the inspection"** — you reported amending §8 to match
     this. Check the real §8. If it already says this, drop the "I amended it" framing. If it
     says something different, either change the implementation to match or flag it as a
     deliberate deviation with stated reasoning.
   - **Non-vacuity enforced mechanically**, **three runners instead of two** — spot-check both
     against the real doc.
4. Verdict per major component: matches-real-doc / diverges-and-corrected /
   diverges-and-flagged-for-review.
5. Correct CLAUDE.md's spec table if its authority entry points at the wrong file or version.

**Where the real doc and your reconstruction disagree, the real doc wins** — unless there's a
specific stated reason it can't apply to Nix's environment. Don't preserve a self-authored
deviation merely because it's already built and tested.

## Part 2 — Bandit repair

bandit 1.8.6 uses `ast.Str.s`, removed in Python 3.12; it `AttributeError`s mid-parse, marks the
file skipped, and exits 0. It has therefore scanned **nothing** repo-wide since ARC 006 — you
proved this by watching it pass a file containing `subprocess.run(..., shell=True)`.

Fix it (version bump, or replace it if no fixed release handles Python 3.14). Then apply the
§5.1 discipline to the gate itself: **plant a known-bad construct, prove bandit now fails on it
and names the site, remove the plant, prove it passes.** A commit gate that has never been proven
capable of failing is exactly the vacuous success §5 exists to prevent.

## Part 3 — Complete ARC 008 Parts 1, 3, 5

### Part 3a — Real API config from jts.ini
Parse `~/Jts/jts.ini` directly. Extract and report the actual values: socket port, ReadOnlyApi
state, TrustedIPs, localhost-only setting, and the Lock-and-Exit auto-restart configuration.
Compare against the six expected values listed in the Context section above and report any
mismatch explicitly.

### Part 3b — Live connection + market-data entitlement
Connect via `ib_async` to port 4002 with **clientId=905** (never 1 — reserved for the future Risk
Engine; never 0 — permanently excluded, it implicitly adopts manually-placed TWS orders).
- Confirm the connection succeeds against the real running Gateway
- Attempt `reqTickByTickData` on a liquid instrument; record whether it succeeds or returns
  **Err 10189** (entitlement absent)
- If 10189, confirm `reqHistoricalTicks` works as the fallback
- Disconnect cleanly — leave no dangling session

**Err 10189 is an expected finding, not a failure to fix.** It has precedent: a predecessor system
on a comparable IBKR account hit exactly this and had to use polled `reqHistoricalTicks` instead
of a true stream — which made bar immutability a design obligation rather than a property of the
feed. Report accurately either way; this result shapes the broker-datafeed spec.

### Part 3c — `checks/check_ibgateway_config.py`
Build it against the **real** VERIFY-AND-CHECKS.md (per Part 1), not a paraphrase.
- **Proves real effective state**: opens an actual socket to the configured port and confirms
  Gateway answers. Never "jts.ini exists" or "the process is alive" as a proxy.
- **Exit contract**: PASS when connected and correctly configured; FAIL when connected but
  misconfigured (e.g. Read-Only back on); CANNOT_MEASURE when Gateway is unreachable — a downed
  Gateway is a different fact from a misconfigured one and must not collapse into FAIL.
- **Never anchor to a moving value**: read the expected port from `jts.ini` at check time; don't
  hardcode 4002.
- **Non-vacuity before the plant**: assert the check actually exercises a live connection attempt.
- **FAIL-with-CONTROL**: plant a defect, confirm FAIL and that it *names the specific site*,
  unplant, confirm PASS reproduces the original. You could not demonstrate this before — with
  nothing listening, every path returned CANNOT_MEASURE, which proves nothing about the gate's
  discriminating power. Now there is something listening, so the full cycle is demonstrable.
- Register it so it runs at the next `verify.py` invocation.

## Part 4 — Branch/merge state

Re-verify fresh: `git fetch origin && git log --oneline -10 origin/main`. Confirm the PR #8 merge
commit is present. Confirm whether `arc-009-verify-v2` (branched off `arc-006-provisioning-v2`,
now merged) needs a rebase before it can go up as its own PR. Report actual current state —
branches, what's merged, what's open — rather than inheriting any prior session's assumption.

## Definition of success

- [ ] Real VERIFY-AND-CHECKS.md in `~/nix/docs/`; diffed against v1.0.1; every semantic divergence
      reported with a verdict; decisions re-examined and corrected or explicitly justified
- [ ] CLAUDE.md spec table corrected if needed
- [ ] bandit repaired and **proven capable of failing** via planted defect + control
- [ ] Real API config values extracted from `jts.ini` and reported; any mismatch against the six
      expected values flagged
- [ ] Live connection on clientId=905 succeeds; entitlement status (10189 or not) determined and
      reported; clean disconnect
- [ ] `check_ibgateway_config.py` built against the real spec, registered, full FAIL-with-CONTROL
      cycle demonstrated verbatim in the results
- [ ] `origin/main` and branch state re-verified fresh

## Out of scope

- No broker-order code — environment and tooling only
- No changes to Gateway's settings — read and verify, do not reconfigure
- Fernet → systemd-creds migration (§11) — separate arc, needs its own design review
- The 8 other owed checks from §13.1 — separate arc
- No process/core map skeleton work

## Note on harness limits

If a git action (merge, push, branch delete) is refused by the permission classifier, report it
plainly and move on — that ceiling is known and expected. Don't attempt workarounds; flag it for
the human.

**Standing gate — do not skip:** append a summary to the end of `~/nix/sessions/SESSION.md`,
overwrite `~/nix/downloads/RESULTS.md` with this arc's full results, `cat` both files, and paste
their resulting state into the response before declaring `**** ARC completed ****`.
