# ARC 012 — systemd Cutover, MES Verification, Entitlement Clarification

## Prerequisite — human actions first

Before running this arc, the human must have:
1. Merged `arc-009-verify-v2` (see the merge note the architect supplied alongside this arc).
2. Be **available at a VNC console with their phone**, because Part 1 deliberately drops the
   authenticated Gateway session and it cannot be restored without a manual login + IB Key tap.

Do not begin Part 1 unless the human has confirmed they are ready to re-authenticate.

## Part 1 — systemd cutover (discharges CHECK-DEBT D1.12)

ARC 011 wrote and enabled `nix-xvfb.service` and `nix-ibgateway.service` but never started them —
correctly, since the human had not authorized paying the 2FA cost. That authorization now exists.

1. **Record pre-cutover state** so the comparison is real: current manual PIDs for Xvfb and the
   Gateway JVM, the live listener on 4002, and a `verify.py` run (expected: 6 passed).
2. **Stop the manual processes** and hand ownership to systemd: `systemctl start nix-xvfb.service`,
   confirm `:99` answers via `xdpyinfo`, then `systemctl start nix-ibgateway.service`.
3. **Confirm the unit-owned Gateway comes up.** It will land on the login screen with no API
   listener — that is expected, not a failure. `check_ibgateway_config` should report
   `CANNOT_MEASURE` (unreachable), not `FAIL`. **Verify that distinction actually holds in
   practice** — it was demonstrated by a planted port in ARC 010, but this is the real thing.
4. **Hand off to the human for the VNC login.** State plainly what you need and stop. After they
   confirm login + IB Key approval, re-run `verify.py` and confirm all checks return to green with
   the Gateway now under systemd rather than a shell.
5. **Then the reboot test, if and only if the human authorizes it separately.** A reboot costs a
   second 2FA tap. Ask; do not assume the Part 1 authorization covers it. If performed, re-run
   `check_ibgateway_service` **before anyone touches the console** — that is the specific
   discharge condition D1.12 records. If not performed, D1.12 stays open and says so.

## Part 2 — MES and the entitlement question

The human has chosen to pursue a smaller instrument. **Two distinct problems are in play and they
have different fixes — do not conflate them:**

- **Margin:** the paper account cannot afford one ES contract (req 35,067.37 vs net liq
  20,344.34). MES (Micro E-mini S&P 500, 1/10th notional) plausibly fixes this.
- **Market data:** `Err 10189` was *"No market data permissions for CME FUT"*. **MES is also CME
  FUT.** Switching instruments very likely does **not** fix the entitlement — it is an account
  subscription, not a contract property. Do not assume otherwise.

Measure both, separately:

1. Resolve the front-month **MES** contract via `ib_async` (clientId=905). Record conId and expiry.
2. Query its margin requirement (`whatIfOrderAsync`, same technique that established ReadOnlyApi
   was off in ARC 010) and compare against the account's net liquidation. Report whether one
   contract is actually affordable.
3. Attempt `reqTickByTickData` on MES. **Record whether Err 10189 recurs.** This is the load-bearing
   measurement: if it does, the polled-`reqHistoricalTicks` path stands regardless of instrument,
   and the bar-immutability obligation on broker-datafeed is unchanged.
4. Confirm `reqHistoricalTicks` returns data for MES either way.
5. Clean disconnect.

**Report what is actually measured, not what would be convenient.** If MES fixes margin but not
data, say so plainly — that is a useful and likely result, not a failure of the arc.

## Part 3 — Record the findings

Update `dev_and_services_plan.md`'s IBKR section with:
- The cutover outcome and whether boot behaviour is now verified or still owed (D1.12 state).
- The MES margin figure vs ES, and the entitlement result.
- If 10189 persists on MES: state explicitly that **no CME futures tick stream is available on this
  account at all**, and that resolving it is a market-data subscription question in IBKR Account
  Management, not something instrument selection or code can work around. Do **not** recommend
  purchasing a subscription — IBKR is permanently paper-only Stage 0 and Tradovate is the live
  broker at cutover; whether it is worth paying for data on a throwaway broker is a human decision,
  so surface it as a decision rather than making it.

Update `docs/CHECK-DEBT.md` for any debt this arc discharges or opens.

## Definition of success

- [ ] Pre-cutover state recorded (PIDs, listener, verify.py baseline)
- [ ] Both units started; Xvfb serving `:99`; Gateway running under systemd, not a shell
- [ ] The unreachable-Gateway case confirmed to report `CANNOT_MEASURE`, not `FAIL`, in the real
      (not planted) case
- [ ] Human VNC re-login completed; `verify.py` returns green with unit-owned processes
- [ ] Reboot test either performed under separate explicit authorization (with
      `check_ibgateway_service` run before console contact), or D1.12 explicitly left open
- [ ] MES contract resolved; margin measured against net liq; affordability stated as a number
- [ ] `reqTickByTickData` attempted on MES; 10189 recurrence recorded either way
- [ ] `reqHistoricalTicks` confirmed working for MES
- [ ] `dev_and_services_plan.md` and `CHECK-DEBT.md` updated

## Out of scope

- No purchase of market-data subscriptions, and no recommendation to — surface it as a human
  decision
- No broker-order or broker-datafeed code
- No auth automation
- No Gateway settings changes

## Note

If any git action is refused by the permission classifier, report it plainly and move on — that
ceiling is known.

**Standing gate — do not skip:** append a summary to the end of `~/nix/sessions/SESSION.md`,
overwrite `~/nix/downloads/RESULTS.md` with this arc's results (ARC 010/011 are banked in
`SESSION.md`, so the append exception that applied to ARC 011 does not apply here), `cat` both
files, and paste their resulting state into the response before declaring `**** ARC completed ****`.
