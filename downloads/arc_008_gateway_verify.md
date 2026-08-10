# ARC 008 — IB Gateway Config Verification, ib_async, Entitlement Check, check_ibgateway_config.py

## Context

Manual IBKR login (Arc 006 Step 7, previously blocked) is now done by the human. This arc closes
out that step with real verification instead of assumption, confirms the Python side is ready,
and builds the standing check gate this environment change owes per the check-script rule.

## Part 1 — Verify Gateway API config from jts.ini (no GUI, no assumption)

`~/Jts/jts.ini` should now exist and be populated (confirm via `find` first — do not assume).
Parse it directly (do not ask the human to read screens back) and extract:
- The configured API socket port
- `ReadOnlyApi` setting (must be disabled/false — broker-order needs to place orders)
- `TrustedIPs` (must include `127.0.0.1`)
- Whether ActiveX/Socket Clients access is enabled

If any setting is not readable from `jts.ini` directly, fall back to a live connection test in
Part 3 to infer it (e.g. a rejected order-placement call implies Read-Only is still on) — note
explicitly which method produced which fact.

**Report the actual values found — these are real config, not to be paraphrased or assumed.**

## Part 2 — Confirm `ib_async` installed

Arc 006's `install.sh` only confirmed `cryptography` in the venv — no evidence `ib_async` (the TWS
API client library broker-order will use) exists yet. Check the venv; if absent, install a pinned
version, confirm `import ib_async` succeeds, and record the exact version installed.

## Part 3 — Live connection + market-data entitlement check

Using `ib_async`, connect to Gateway on the port confirmed in Part 1 with **clientId=905**
(diagnostic — never 1, which is reserved for the future live engine per Part 4's decision). Confirm:
- Connection succeeds against the real, running Gateway (not a mock)
- Attempt `reqTickByTickData` on a liquid test symbol (e.g. front-month ES or a stock) — record
  whether it succeeds or returns **Err 10189** (no entitlement)
- If 10189, confirm `reqHistoricalTicks` works as the fallback path
- Disconnect cleanly — do not leave a dangling session

Report the actual entitlement status found. This determines whether broker-datafeed gets a real
stream or must poll — needed before that module's spec is drafted.

## Part 4 — Record the `clientId` scheme decision

Document in `dev_and_services_plan.md`'s IBKR section (same section as the existing weekly-auth
note): **clientId 1 is reserved for the live Risk Engine process (not yet built — do not connect
anything else on 1); clientId 905 is reserved for diagnostics/tooling** (as used in Part 3). This
is a decision being recorded, not inferred — state it as such.

## Part 5 — Build `checks/check_ibgateway_config.py`

New verify.py gate, per the standing check-script rule (see `VERIFY-AND-CHECKS.md`):
- **Proves real effective state**: attempts an actual socket connection to the confirmed port and
  confirms Gateway answers on it — never just checks `jts.ini` exists or parses without connecting.
- **Exit-code contract**: 0 = PASS (connects, correct config), 1 = FAIL (connects but
  misconfigured, e.g. Read-Only still on), 2 = CANNOT MEASURE (Gateway unreachable/down — this is
  not the same as FAIL, and must not collapse into exit 1 on a connection exception).
- **Non-vacuity check before any plant**: assert the gate actually exercises a live connection
  attempt (not skipped/short-circuited) before proceeding to the FAIL demonstration.
- **Demonstrated FAIL path with a CONTROL**: plant a defect (e.g. point the gate at a wrong port,
  or flip a config flag it checks), confirm the gate fails **and names the specific
  setting/site that's wrong** rather than a generic failure, remove the plant, confirm PASS again.
- **Never anchor to a moving value**: read the expected port from `jts.ini` itself at check time,
  don't hardcode today's port as a literal.
- Register the gate so it runs at the next `verify.py` invocation.

## Definition of success

- [ ] Real API config values (port, ReadOnlyApi, TrustedIPs) extracted and reported from `jts.ini`
      or live-inferred, not assumed
- [ ] `ib_async` confirmed installed (or installed + confirmed), version recorded
- [ ] Live connection to Gateway succeeds with clientId=905; market-data entitlement status
      (10189 or not) determined and reported
- [ ] `clientId` scheme (1=engine reserved, 905=diagnostic) documented in
      `dev_and_services_plan.md`
- [ ] `checks/check_ibgateway_config.py` built, registered with verify.py, exit-code contract
      correct, demonstrated FAIL-with-CONTROL cycle shown in the results

## Out of scope

- No broker-order code — this is environment verification only
- No changes to Gateway's own settings — read/verify, do not reconfigure
- No process/core map skeleton work (separate, earlier arc in the sequence)

**Standing gate — do not skip:** append a summary to the end of `~/nix/sessions/SESSION.md`,
overwrite `~/nix/downloads/RESULTS.md` with this arc's full results, `cat` both files, and paste
their resulting state into the response before declaring `**** ARC completed ****`.
