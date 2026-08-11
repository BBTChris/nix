# TAP SESSION — D1.12 reboot · taxonomy confirmation · marketDataType sentinel · verify green
### Operator procedure, ~40 minutes. Not an arc. No write-back gate.

**Four discharges on one IB Key tap. The ordering is load-bearing — step 2's value is destroyed
by doing step 4 first.**

---

## Why the order matters

`nix-reboot-capture.service` is armed and validated. Its worth is not the verdict — it is the
**evidence that nobody was there**: `who`, `loginctl list-sessions`, and uptime measured against a
300 s ceiling. A verdict taken by hand ten minutes into a boot cannot distinguish "it came back on
its own" from "it came back because I was here", and it fails in the direction that looks like
success.

**So: do not SSH into node02 for five minutes after the reboot.** That single instruction is the
whole of D1.12's validity. The capture runs automatically at boot, before any login exists.

The Gateway has already expired on its own (03:00:04 UTC, 16 h after start — IBKR's daily session
expiry, `status=0/SUCCESS`, not a crash). **So the reboot costs no live session.** D1.12 rides in
front of the tap for free.

---

## Step 1 — pre-flight (2 min, from your current SSH session)

```bash
cd ~/nix
systemctl is-enabled nix-reboot-capture.service        # expect: enabled
systemctl show nix-reboot-capture.service --property=Id,LoadState
ls -la /var/lib/nix-reboot-capture/ 2>/dev/null || ls -la ~/nix/state/reboot-capture/ 2>/dev/null
```

**The capture directory must be empty.** ARC 020 deleted its validation capture deliberately so
that after the next boot, an empty directory is itself the finding. If something is in there, that
is a pre-existing capture and you want to know why before you reboot.

Confirm both unit names resolve `LoadState=loaded` — ARC 020 repaired the capture's references from
`ibgateway.service` (which does not exist on this box) to `nix-ibgateway.service` and
`nix-xvfb.service`. `systemctl show` on an unknown unit returns `inactive`/`dead` with no error, so
a stale name reports "did not come back" about nothing at all.

---

## Step 2 — reboot, then wait (7 min, mostly waiting)

```bash
sudo reboot
```

**Now do nothing for five minutes.** No SSH, no VNC, no console. The 300 s ceiling and the
`loginctl` precondition are both live during this window, and a login inside it converts a valid
capture into `"trustworthy": false`.

---

## Step 3 — read the capture (3 min)

SSH back in and read it **before** touching anything else:

```bash
cd ~/nix
cat /var/lib/nix-reboot-capture/*.json 2>/dev/null || cat ~/nix/state/reboot-capture/*.json
systemctl status nix-xvfb.service --no-pager | head -5
systemctl status nix-ibgateway.service --no-pager | head -5
```

**What you are looking for:**
- `"trustworthy": true` with no precondition failures
- Both units' `LoadState=loaded` and `ActiveState` recorded
- `systemctl_is_enabled_DECLARATION_ONLY` present but **not** treated as the verdict — the evidence
  is `ActiveState`, and the key is named that way so it can never be mistaken
- **An empty directory is a finding, not a null result.** If nothing was captured, the service did
  not run at boot and D1.12 is not discharged — it is refuted, which is more useful

The API-reachability field is named `check_ibgateway_service_NOT_THE_D1_12_VERDICT` on purpose. IB
Gateway serves no API until an IB Key login completes, so a boot capture shows it unreachable no
matter how correctly systemd started the process. That is expected and is not a failure.

---

## Step 4 — IB Key login via VNC (10 min)

Only now touch the console.

```bash
# on node02
x11vnc -display :99 -localhost -passwd temp1234 -rfbport 5902 -forever &

# on the Mac, separate terminal
ssh -L 5902:localhost:5902 bbt@node02
open vnc://localhost:5902
```

Port **5900 collides with macOS Screen Sharing** — use 5902. Screen Sharing.app requires a password
even against a `-nopw` server, hence `-passwd`. The `-L` flag is the one that gets omitted and fails
silently.

Complete the IB Key tap. Then:

```bash
pkill x11vnc
ss -tlnp | grep 4002        # expect a listener
```

---

## Step 5 — hand off to `cc` (15 min)

Paste this:

```
The Gateway is logged back in after a reboot. Four things to capture in one session,
read-only except where noted. No arc, no write-back gate, no SESSION.md append — bank the
output into ~/nix/downloads/TAP_SESSION.md and paste it into your response.

Use clientId 905 throughout. clientId 0 stays permanently excluded; 1 stays reserved.

1. verify.py — confirm it is back to exit 0 now the Gateway is up. If check_ibgateway_config
   or check_ibgateway_service still complain, that is a real finding, not leftover state.

2. The rejection-taxonomy confirmation owed since ARC 018. Place an order the venue will
   refuse — an unaffordable size is cleanest, and ARC 010 established a rejection carries
   err 201 with the margin number. Confirm BOTH halves in one observation:
     - reject_category == INSUFFICIENT_MARGIN (structured fact populated)
     - reason still carries the "201: ...MARGIN REQ..." text (human channel intact)
   This is the one thing offline tests cannot do: it re-validates the text anchor against
   IBKR's CURRENT wording. If the wording has drifted, say so — that is the finding.

3. The marketDataType sentinel, for D1.13. IBKR silently downgrades: mode 4 requested, mode 3
   granted. And ib_async's Ticker.marketDataType DEFAULTS TO 1, so an unset field is
   indistinguishable from a real-time grant. Sentinel it to 0 after subscribing, then read
   what was actually granted. Never infer the mode from the request.
     - reqMarketDataType(3) + reqMktData on MESU6 (conId 793356217)
     - report requested vs granted
     - also report what reqMarketDataType(1) grants, so the downgrade is observed, not assumed

4. Re-measure the delayed-feed lag. ARC 010 measured 600.3 s, spread 1.9 s over n=8 — not the
   documented 15-20 minutes. Take a handful of samples and report whether it still holds.
   This number is load-bearing for broker-datafeed's FeedLag, so a drift matters.

Then flatten anything open and confirm the account is flat. Decline if it is near the
16:00 CT close — ARC 017's precedent, evidence at a session boundary is ambiguous.
```

---

## What this discharges

| item | owed since | discharged by |
|---|---|---|
| **D1.12** reboot behaviour | ARC 013 | steps 2–3 |
| **Rejection taxonomy** live confirmation | ARC 018 | step 5.2 |
| **`verify.py` exit 0** | ARC 020 (Gateway expiry) | step 5.1 |
| **D1.13** input — granted vs declared | ARC 010 | step 5.3 |

Step 5.4 is not a discharge — it is the measurement ARC 021's `FeedLag` is built on, and taking it
now costs nothing once a session exists.

---

## The dispatch fix — 10 minutes, same sitting

ARC 020 finding 9: `state/` is gitignored (D1.16), so a fresh linked worktree has no
`state/node_identity.json` and no `.venv`. That fails `check_node_identity` and blocks the Stage 3
runtime gate at commit time. **Both sub-agents hit it independently and both solved it separately.**

That is a standing tax on every mega arc. Fix it once in worktree provisioning — gitignored symlinks
back to the primary tree, the same resolution both sub-agents reached, applied at dispatch instead
of discovered twice.

Worth doing before ARC 021 dispatches three agents into the same wall.
