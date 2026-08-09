# ARC 006 — Dev Box Provisioning (MS-01 / node02)

**Task:** Bring the MS-01 dev box up to the state `elements_v2.md` and `debug.md` describe as
baseline before any code work (R1) begins. This arc is infrastructure only — no `scripts/`
content, no strategy/risk code.

**Preconditions — split by who can actually do them:**
- **Human-only, cannot be scripted:** IBKR paper account API access enabled in Client Portal
  (Settings → API → Settings, read-only OFF); the first interactive Gateway login (GUI + IB Key
  2FA approval) — IBKR does not support headless first-auth, this is a hard vendor constraint,
  not a tooling gap.
- **cc-doable, per step 1 below:** downloading and silently installing IB Gateway itself (offline
  standalone build), installing `Xvfb` so Gateway has somewhere to render its login screen on a
  headless box, and configuring auto-restart-not-auto-logoff *if* that setting is reachable
  without a prior human login. If it isn't, stop after the install and report exactly what's
  blocking and why — don't attempt a workaround for the 2FA step itself.

## Steps

1. **Install IB Gateway.** Check first whether it's already present — do not reinstall over a
   working instance. If absent:
   - `wget https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh`
   - Verify the download isn't corrupted/truncated before executing (size sanity check at minimum;
     checksum if IBKR publishes one for this build).
   - `chmod a+x ibgateway-stable-standalone-linux-x64.sh && ./ibgateway-stable-standalone-linux-x64.sh -c`
     (console/silent install — do NOT let it auto-launch Gateway at the end of install if that's
     an option in the installer's prompts).
   - Install `Xvfb` (`sudo apt install xvfb`) so Gateway has a virtual display to render its login
     screen against, since this box is headless and Gateway does not support running without one.
   - **Stop here and report.** The first login requires the human operator physically present for
     GUI credential entry and IB Key 2FA approval on their phone — this cannot be scripted or
     worked around. Report installed version, confirm Xvfb is ready, and hand back for the human
     step before continuing to step 7's verification.

2. **`install.sh` per `elements_v2.md` §1.2:**
   - Base deps: `python3`, `git`, `python3-venv`, cryptography libs
   - Hardware identity: capture the v4 full UUID of the primary partition
   - Secure credential storage: set up the Fernet-encryption-under-master-password flow for
     broker accounts/API keys, local JSON, `chmod 600`. Do NOT populate real IBKR credentials in
     this step unless the human operator is present to enter them interactively — do not prompt
     for or accept credentials via a non-interactive channel.

3. **Core pinning.** Per `dev_and_services_plan.md`: the risk spec's core map (cores 0–5) is
   pinned identically on this box; remaining 14 cores stay outside the trading core-set. Verify
   and document how this is enforced (cgroups / taskset / systemd `CPUAffinity` — pick one,
   document why, make it consistent with how prod (QuantVPS, 6-core box) would need to express the
   same constraint despite different total core counts).

4. **`verify.py` per `elements_v2.md` §1.3.** Idempotent, plugin-based inspection/remediation
   engine. Wire it to run: end of `install.sh`, every boot, weekly (Saturday 03:00
   America/Chicago). Confirm the weekly cron/systemd-timer actually lands outside any trading
   session window — cross-check against session calendar assumptions in the risk spec if that
   detail exists; if it doesn't yet exist, note the gap rather than guessing.

5. **PostgreSQL cluster.** System-level install (OS default location, per `directory_structure.md`
   — explicitly NOT inside `~/nix`). Apply the schema from `docs/nix_db_schema_spec.docx`: roles
   (`nix_bt_writer`, `nix_paper_writer`, `nix_live_writer`, `nix_reader`), partitions, grants, the
   `check_default_partitions()` function. Verify role separation actually holds — attempt (and
   expect to fail) an INSERT to `trades_live` as `nix_paper_writer` as a live check, not just a
   read of the GRANT statements.

6. **`pre-commit` install** per `debug.md` §6: `pip install pre-commit`, `pre-commit install`,
   the full hook config (ruff, pylint, mypy, bandit, complexipy, pytest-testmon local hook). Pin
   every `rev`. Run `pre-commit run --all-files` once against the current repo state and report
   the result — expect it to be clean since there's no code yet, but confirm rather than assume.

7. **IB Gateway verification (not setup — see preconditions).** If Gateway is already installed
   and authenticated per step 1: confirm socket port is 4002 (paper), "Enable ActiveX and Socket
   Clients" is checked, trusted IP includes 127.0.0.1. Attempt a bare socket connection test
   (no order placement) to confirm the API is actually reachable. Document the weekly-auth
   expectation (IB Key approval on human's phone, auto-restart daily in between) as a note in
   `dev_and_services_plan.md` under the IBKR section, so it's not tribal knowledge.

## Definition of success

- [ ] Precondition state (IB Gateway) accurately reported, not assumed
- [ ] `install.sh` run; base deps present; hardware UUID captured; credential-encryption mechanism
      in place (empty/unpopulated is fine if no human was present to enter real creds)
- [ ] Core pinning mechanism chosen, documented, verified active (cores 0–5 only)
- [ ] `verify.py` runs at all three trigger points; weekly timing confirmed outside trading hours
- [ ] PostgreSQL installed at OS-default location (not under `~/nix`); schema applied; role
      separation verified with a live negative test, not just GRANT inspection
- [ ] `pre-commit` installed, hooks configured with pinned revs, `--all-files` run clean
- [ ] IB Gateway config verified (port, socket clients enabled, trusted IP) IF already installed;
      otherwise clearly reported as blocked on human action
- [ ] `dev_and_services_plan.md` updated with the weekly-auth note

## Out of scope

- No `scripts/` code — R1 seams & skeleton is a separate arc
- No real IBKR credentials entered non-interactively
- No CI/CD, no GitHub Actions
- No DataBento/Tradovate/QuantVPS work — Stage 1+ only

**Standing gate — do not skip:** append a summary to the end of `~/nix/sessions/SESSION.md`,
overwrite `~/nix/downloads/RESULTS.md` with this arc's full results, `cat` both files, and paste
their resulting state into the response before declaring `**** ARC completed ****`.
