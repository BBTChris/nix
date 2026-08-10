# ARC 011 — Xvfb + IB Gateway Boot Persistence (systemd units + check gate)

## Prerequisite

**Do not start this arc until ARC 010 is complete.** Part 3 below builds a check against
`VERIFY-AND-CHECKS.md`, which ARC 010 reconciles against the real source document. Building this
gate first would build it against a possibly-divergent spec.

## Context — the actual gap

IB Gateway and Xvfb are both running right now only because a human started them by hand in a
terminal session. Neither survives a reboot:

- `Xvfb :99 -screen 0 1440x900x24` — foreground process, started manually
- IB Gateway (install4j-launched JVM, currently PID 236482) — started manually, depends on `:99`

Gateway's **Auto restart at 03:00** setting does *not* address this. That is an internal
application cycle that only fires while the process is already alive. It does nothing after a
reboot, a crash, or an OOM kill.

**What this arc does and does not achieve:** it makes both processes come back automatically on
boot. It does **not** achieve unattended authentication — after a reboot Gateway will come up
sitting on its login screen, waiting for credentials and an IB Key 2FA tap. That is a separate,
deliberately deferred problem (see Out of Scope). The value here is narrow but real: a reboot
should not cost a VNC session just to get the process running again.

## Part 1 — `nix-xvfb.service`

A systemd unit owning the virtual display.

- Runs as user `bbt` (not root — a root-owned display would create the same
  ownership problem as running user checks as root).
- Display `:99`, screen `0 1440x900x24` — match the current live invocation exactly; verify it
  from the running process rather than trusting this arc's transcription of it.
- `Restart=` policy appropriate for a display server that should always be up.
- Enabled at boot.

**Do not** put this in `nix-trading.slice` — the trading slice is `AllowedCPUs=0-5` and is for
trading-path processes. Xvfb is dev-scaffold infrastructure; pinning it there would consume
trading-path core budget for a display server. If you disagree after reading elements_v2.md §1.4
and the slice's own definition, say so and explain rather than silently choosing either way.

## Part 2 — `nix-ibgateway.service`

A systemd unit owning the Gateway process.

- `After=` / `Requires=` (or `BindsTo=`, your call — justify it) `nix-xvfb.service`. Gateway
  cannot start without the display; the dependency must be real, not incidental ordering.
- Runs as user `bbt`, `Environment=DISPLAY=:99`.
- Launches the same binary currently running — derive the exact path and invocation from the live
  process (`/proc/<pid>/cmdline`), not from memory or from this arc.
- Restart policy that survives a crash but does not fight a deliberate operator shutdown.
- Enabled at boot.

**Same slice question as Part 1** — Gateway is Stage 0 dev plumbing, not a trading-path process.
Reason it out and state your choice.

### Verify it actually works
Do not stop at "unit file written and `systemctl enable` returned 0." Prove the units function:
- `systemctl start` both, confirm the display answers (`xdpyinfo -display :99`) and Gateway's JVM
  appears
- Stop Gateway, confirm the restart policy brings it back
- Report whether a real reboot test was performed or not — **do not reboot this box without
  explicit human authorization**, since that would drop the currently-authenticated Gateway
  session and cost a manual 2FA re-login. If you cannot test reboot, say so plainly rather than
  implying boot behavior was verified.

## Part 3 — `checks/check_ibgateway_service.py`

Per the standing check-script rule — these are environment changes and owe a gate. Build it
against the real `VERIFY-AND-CHECKS.md` (in `~/nix/docs/` after ARC 010), not a paraphrase.

- **Proves real effective state.** The failure mode this gate exists to catch is a unit that is
  enabled and "active" while the thing it manages is not actually usable. So: confirm the display
  genuinely answers, and that Gateway's socket is genuinely reachable. **`systemctl is-enabled`
  and process-alive are proxies, not proof** — the predecessor system's exact recorded mistake was
  computing broker connection state and never publishing it anywhere a check could read, so no
  instrument could distinguish connected from disconnected. Don't rebuild that gap.
- **Exit contract**: PASS when units enabled *and* display + Gateway genuinely reachable; FAIL
  when a unit is disabled/misconfigured (a real, named defect); CANNOT_MEASURE when it cannot be
  determined. Never let a subprocess exception collapse into FAIL.
- **Do not duplicate `check_ibgateway_config.py`** (built in ARC 010). That gate owns API
  *configuration*; this one owns *service persistence*. If the two would overlap on a property,
  extend the existing gate rather than creating a second one that could disagree with it — per
  the rule about never building a second gate for a property another already owns.
- **Non-vacuity before the plant**: assert the gate's scope actually contains its subject.
- **FAIL-with-CONTROL**: plant a real defect (e.g. `systemctl disable` one unit), confirm FAIL
  and that it *names the specific unit*, unplant, confirm PASS reproduces the original.
- Register it with `verify.py`.

## Definition of success

- [ ] `nix-xvfb.service` written, enabled, started, display confirmed answering live
- [ ] `nix-ibgateway.service` written with a real dependency on the display unit, enabled,
      started, Gateway confirmed running and socket reachable
- [ ] Slice-membership decision made and reasoned for both units, not silently defaulted
- [ ] Restart policy demonstrated (kill Gateway, confirm it returns)
- [ ] Reboot test either performed with human authorization, or explicitly reported as not
      performed — no implication that boot behavior was verified when it wasn't
- [ ] `check_ibgateway_service.py` built against the real spec, registered, non-overlapping with
      `check_ibgateway_config.py`, full FAIL-with-CONTROL cycle demonstrated verbatim
- [ ] `dev_and_services_plan.md` updated: both units documented, and the **explicit statement that
      boot persistence ≠ unattended auth** — after reboot, Gateway comes up needing a manual
      login and IB Key tap

## Out of scope — deliberately

- **No credential automation, no IBC, no TOTP, no browser-automation of the auth flow.** IBKR is
  permanently paper-only Stage 0 plumbing; Tradovate is the live broker at cutover. Auth
  automation built against IBKR is thrown away at that boundary, and one of the candidate
  approaches is terms-grey. The weekly manual IB Key tap is the accepted cost.
- No changes to Gateway's application settings (ARC 010 owns verifying those)
- No broker-order code
- No reboot without explicit human authorization

**Standing gate — do not skip:** append a summary to the end of `~/nix/sessions/SESSION.md`, and
**APPEND** this arc's full results to the end of `~/nix/downloads/RESULTS.md` — **do NOT
overwrite it.** This is a deliberate deviation from the normal overwrite convention (and from
`directory_structure.md`'s "overwritten per arc" description) for this arc specifically: ARC 010
runs immediately before this one, and overwriting would destroy its results before the human has
read them. Preserve ARC 010's section intact above your own, under a clear `## ARC 011` heading.
Then `cat` both files and paste their resulting state into the response before declaring
`**** ARC completed ****`.
