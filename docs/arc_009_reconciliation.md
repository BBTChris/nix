# ARC 009 — Security Teardown, VERIFY-AND-CHECKS.md Reconciliation, PR/Main State Re-verify

## Context

Three things surfaced from the last handoff that need closing before any further work builds on
top of Arc 009's verify-framework branch:

1. `x11vnc` is exposed on the LAN interface with a plaintext password file — real, live exposure
   on a box that will hold trading credentials.
2. The real `VERIFY-AND-CHECKS.md` (the actual source doc, authored outside this session) was
   never delivered into the repo. Arc 008 told you to read it "exactly," but it wasn't present, so
   you authored your own reconstruction (`v1.0.1`) from context and indexed it as canonical. That
   reconstruction may or may not match the real doc's intent — this arc finds out.
3. A prior handoff claimed PR #8 was still open/blocked on a human merge. It is not — it was
   merged via `gh pr merge 8 --merge --admin` and confirmed successful. Don't trust that claim;
   re-verify fresh.

## Part 1 — Security teardown (do this first, before anything else)

- Kill the `x11vnc` process bound to `192.168.1.25:5900`.
- Locate and securely delete the plaintext VNC password file (`shred -u`, not `rm`).
- Confirm via `ps`/`ss`/`netstat` that nothing is still listening on that port or any other
  X11-forwarding/VNC process is lingering.
- Report exactly what was found and removed — don't summarize as "handled," show the evidence
  (process list before/after, port scan before/after).

## Part 2 — Deliver and reconcile the real VERIFY-AND-CHECKS.md

The real source doc is attached to this arc at `~/nix/downloads/VERIFY-AND-CHECKS.md`.

1. Copy it into `~/nix/docs/VERIFY-AND-CHECKS.md` — this is now the authoritative location.
2. Diff it structurally against whatever you authored as `v1.0.1` during Arc 009 (check git
   history on the `arc-009-verify-v2` branch for wherever you wrote it). Identify every point of
   divergence — not just wording differences, but semantic ones: places where your reconstruction
   specified different behavior than the real doc.
3. **Specifically re-examine decisions 3 and 1 from your last handoff** against the real doc:
   - Decision 3 (disruptive gates the repair, not the inspection — "inspect but withhold" instead
     of §8's literal "skip"): does the real doc's actual §8 support this, contradict it, or leave
     it genuinely open? If the real doc already specifies this behavior, say so and drop the
     "I amended §8" framing — you didn't amend anything, you just hadn't read it. If the real doc
     says something different, this needs to change to match, or be flagged as a deliberate
     deviation with reasoning, not silently kept.
   - Decision 1 (five-state results): confirm this matches what the real doc specifies, or if it's
     a genuine addition beyond it, note that clearly.
4. For every other design choice made in Arc 009 (non-vacuity enforcement, three runners, the
   `check_*.py` contract shape) — spot-check against the real doc for drift. Report a verdict per
   major component: matches-real-doc / diverges-and-corrected / diverges-and-flagged-for-review.
5. Update `CLAUDE.md`'s spec table if the authority entry needs correcting (e.g. if it currently
   points at your reconstruction rather than the real file's actual location/version).

**Do not silently keep a self-authored deviation just because it's already built and tested.**
Where the real doc and your reconstruction disagree, the real doc wins unless there's a specific,
stated reason it shouldn't (e.g. it documents something Nix's environment makes impossible) — and
that reason needs to be written down, not assumed.

## Part 3 — Re-verify PR #8 and `main` state fresh

Do not trust the last handoff's claim. Run this yourself, now:
- `git fetch origin && git log --oneline -10 origin/main` — confirm the PR #8 merge commit is
  actually there.
- Confirm `arc-009-verify-v2`'s base is consistent with current `main` (it was branched off
  `arc-006-provisioning-v2`, which is now merged — confirm no rebase is needed before this branch
  can go up for its own PR cleanly).
- Report the actual current state — branch list, what's merged, what's open — rather than
  inheriting the prior session's assumption.

## Definition of success

- [ ] `x11vnc` and the plaintext password file confirmed removed, with before/after evidence
- [ ] Real `VERIFY-AND-CHECKS.md` delivered to `~/nix/docs/`
- [ ] Self-authored `v1.0.1` diffed against it; every divergence reported with a verdict
- [ ] Decisions 1 and 3 specifically re-examined and corrected or explicitly justified
- [ ] `CLAUDE.md` spec table corrected if needed
- [ ] `origin/main` and PR/branch state re-verified fresh, not inherited from the prior handoff

## Out of scope

- Bandit fix (separate arc, next)
- Fernet → systemd-creds migration (separate arc, needs its own design review)
- Arc 008 Parts 1/3/5 (blocked on Gateway login being genuinely complete)
- No new checks beyond what reconciliation requires — don't expand scope further this arc

**Standing gate — do not skip:** append a summary to the end of `~/nix/sessions/SESSION.md`,
overwrite `~/nix/downloads/RESULTS.md` with this arc's full results, `cat` both files, and paste
their resulting state into the response before declaring `**** ARC completed ****`.
