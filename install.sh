#!/usr/bin/env bash
# ~/nix/install.sh — bootstrap per elements_v2.md §1.2
# Administrator downloads and runs this manually:
#   curl -sSLO https://raw.githubusercontent.com/BBTChris/nix/main/install.sh && bash install.sh
set -euo pipefail

NIX_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="$NIX_HOME/state"
mkdir -p "$STATE_DIR"

echo "== install.sh: base dependencies (before any interactive prompt) =="
sudo apt-get update -qq
sudo apt-get install -y python3 python3-venv python3-pip git libssl-dev libffi-dev python3-dev

echo "== install.sh: python venv + pinned deps =="
if [ ! -d "$NIX_HOME/.venv" ]; then
    python3 -m venv "$NIX_HOME/.venv"
fi
"$NIX_HOME/.venv/bin/pip" install --quiet --upgrade pip
"$NIX_HOME/.venv/bin/pip" install --quiet cryptography
# Pins live in checks/pinned_deps.json. check_python_deps.py --print-pins is
# the one validated reader of that file (nix_check_contract.md §7) — its
# token guard is what keeps a malformed entry from word-splitting or
# globbing here, so install.sh must consume its output rather than
# re-parsing the JSON itself (CLAUDE.md directive 3: one source of truth).
# Runs under the system interpreter: the venv above has pip but not yet the
# pins, and check_python_deps.py needs nothing beyond stdlib to print them.
# Plain `VAR=$(...)` (not `< <(...)` process substitution) so a validation
# failure aborts here under `set -e`, loud, instead of silently yielding an
# empty PINS and deferring the failure to pip's own "nothing to install"
# (CLAUDE.md directive 4: fail closed and loud).
PINS_RAW="$(python3 "$NIX_HOME/checks/check_python_deps.py" --print-pins)"
if [ -z "$PINS_RAW" ]; then
    echo "no pins declared in checks/pinned_deps.json — nothing to install"
else
    mapfile -t PINS <<< "$PINS_RAW"
    "$NIX_HOME/.venv/bin/pip" install --quiet "${PINS[@]}"
fi
# ARC CRUCIBLE-DEPSPLIT: general-purpose runtime dev-tooling (pytest-testmon,
# pre-commit, coverage — see checks/requirements-runtime.txt's own header for
# why these are a separate, unpinned tier from the two above). Deliberately
# plain pip, matching every other install in this bootstrap script — the
# runtime/dev VENV SPLIT is what this arc introduces; it does not convert
# install.sh's own tool choice, which stays consistent with itself. The
# Crucible calendar generator's dependency (pandas_market_calendars) is
# NEVER installed here — it lives only in .venv-dev, built by
# scripts/crucible/generator-requirements.txt via a separate, explicit `uv
# pip install` (its own header), never by this script.
"$NIX_HOME/.venv/bin/pip" install --quiet -r "$NIX_HOME/checks/requirements-runtime.txt"

echo "== install.sh: hardware identity (v4 full UUID, primary partition) =="
ROOT_DEV=$(findmnt -n -o SOURCE /)
ROOT_UUID=$(blkid -s UUID -o value "$ROOT_DEV")
python3 - "$ROOT_UUID" "$ROOT_DEV" "$STATE_DIR/node_identity.json" << 'PYEOF'
import json, sys, datetime
uuid, dev, path = sys.argv[1], sys.argv[2], sys.argv[3]
data = {
    "primary_partition_uuid": uuid,
    "primary_partition_device": dev,
    "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
json.dump(data, open(path, "w"), indent=2)
print(f"wrote {path}")
PYEOF
chmod 600 "$STATE_DIR/node_identity.json"

echo "== install.sh: credential-encryption mechanism (Fernet under master password) =="
cat > "$STATE_DIR/encrypt_credentials.py" << 'PYEOF'
#!/usr/bin/env python3
"""
Fernet-encrypt broker credentials under a master node password, per elements_v2.md §1.2.
Run interactively only: python3 encrypt_credentials.py
Refuses to run non-interactively; never accepts credentials via argv/env/pipe/stdin redirect.
"""
import json, getpass, base64, os
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet

CRED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")


def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600_000)
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def main():
    if not os.isatty(0):
        raise SystemExit(
            "refusing to run non-interactively — credentials must be entered by a human"
        )
    master_password = getpass.getpass("Master node password: ")
    confirm = getpass.getpass("Confirm master node password: ")
    if master_password != confirm:
        raise SystemExit("passwords did not match")
    salt = os.urandom(16)
    key = derive_key(master_password, salt)
    fernet = Fernet(key)

    creds = {}
    print("Enter broker credentials (blank name to finish):")
    while True:
        name = input("  credential name (e.g. ibkr_api_key): ").strip()
        if not name:
            break
        value = getpass.getpass(f"  value for {name}: ")
        creds[name] = base64.b64encode(fernet.encrypt(value.encode())).decode()

    out = {"salt": base64.b64encode(salt).decode(), "credentials": creds}
    with open(CRED_PATH, "w") as fh:
        json.dump(out, fh, indent=2)
    os.chmod(CRED_PATH, 0o600)
    print(f"wrote {CRED_PATH} (chmod 600)")


if __name__ == "__main__":
    main()
PYEOF
chmod 700 "$STATE_DIR/encrypt_credentials.py"
echo "credential-encryption mechanism ready at $STATE_DIR/encrypt_credentials.py"
echo "NOT run — no human present for interactive master-password/credential entry."

echo "== install.sh: systemd units (boot, weekly-root, weekly-user) =="
# Idempotent: sudo tee deterministically overwrites each unit file, and
# daemon-reload/enable are no-ops when already applied — safe to re-run.
sudo tee /etc/systemd/system/nix-verify.service > /dev/null << 'UNIT'
[Unit]
Description=Nix verify.py — boot-time inspection and non-disruptive repair
Documentation=file:///home/bbt/nix/docs/nix_check_contract.md
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=bbt
# System interpreter, not .venv: the engine is stdlib-only (§9.1) and a check
# that rebuilds .venv must not be running on .venv's interpreter (§9.5).
ExecStart=/usr/bin/python3 /home/bbt/nix/scripts/verify.py \
    --mode correct --privilege user --verbose
# Maintenance mode is deliberately omitted: a boot can occur mid-session, so
# disruptive repairs are refused here and deferred to the weekly runs (§8).
SuccessExitStatus=0 2

[Install]
WantedBy=multi-user.target
UNIT

sudo tee /etc/systemd/system/nix-verify-root.service > /dev/null << 'UNIT'
[Unit]
Description=Nix verify.py — weekly privileged verification and repair
Documentation=file:///home/bbt/nix/docs/nix_check_contract.md

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /home/bbt/nix/scripts/verify.py \
    --mode correct --privilege root --maintenance --verbose
SuccessExitStatus=0 2
UNIT

sudo tee /etc/systemd/system/nix-verify-root.timer > /dev/null << 'UNIT'
[Unit]
Description=Weekly Nix privileged verification
Documentation=file:///home/bbt/nix/docs/nix_check_contract.md

[Timer]
# Saturday 03:00 America/Chicago — no session at all, comfortably outside the
# risk spec's no-new-entry window (Friday close -30min through Sunday open).
OnCalendar=Sat *-*-* 03:00:00 America/Chicago
Persistent=true

[Install]
WantedBy=timers.target
UNIT

# §8 gap fix (final whole-branch review, I1): check_python_deps is
# PRIVILEGE=user and DISRUPTIVE=True. The boot unit above never repairs
# (disruptive refused) and nix-verify-root.service runs only PRIVILEGE=root
# checks — so a user-privilege disruptive check was detected at every boot
# and repaired never. This third unit gives user-privilege disruptive
# checks a weekly window of their own, mirroring the root pair exactly.
sudo tee /etc/systemd/system/nix-verify-weekly.service > /dev/null << 'UNIT'
[Unit]
Description=Nix verify.py — weekly user-privilege disruptive repair (e.g. pin drift)
Documentation=file:///home/bbt/nix/docs/nix_check_contract.md

[Service]
Type=oneshot
User=bbt
ExecStart=/usr/bin/python3 /home/bbt/nix/scripts/verify.py \
    --mode correct --privilege user --maintenance --verbose
SuccessExitStatus=0 2
UNIT

sudo tee /etc/systemd/system/nix-verify-weekly.timer > /dev/null << 'UNIT'
[Unit]
Description=Weekly Nix user-privilege disruptive repair
Documentation=file:///home/bbt/nix/docs/nix_check_contract.md

[Timer]
# Same window as nix-verify-root.timer (§8): Saturday 03:00 America/Chicago.
OnCalendar=Sat *-*-* 03:00:00 America/Chicago
Persistent=true

[Install]
WantedBy=timers.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable nix-verify.service
sudo systemctl enable --now nix-verify-root.timer
sudo systemctl enable --now nix-verify-weekly.timer

echo "== install.sh: Stage 0 dev scaffolding (Xvfb + IB Gateway) =="
# ARC 011. Both processes existed only as manually-started foreground jobs and
# did not survive a reboot. These units fix that, and nothing more:
# BOOT PERSISTENCE IS NOT UNATTENDED AUTH. After a reboot Gateway comes back
# up sitting on its login screen, waiting for credentials and an IB Key 2FA
# tap. Auth automation is deliberately out of scope — IBKR is permanently
# paper-only Stage 0 plumbing and Tradovate is the live broker at cutover, so
# anything built against IBKR's auth flow is thrown away at that boundary.
#
# NEITHER UNIT JOINS nix-trading.slice, deliberately. That slice is
# AllowedCPUs=0-5 and exists to mirror the risk spec §10 core map (0 OS,
# 1 capture, 2 Risk Engine, 3 Allocator, 4-5 pool). Neither Xvfb nor the
# Gateway JVM appears anywhere in that map, and the JVM runs G1GC with
# -XX:ParallelGCThreads=20 — sized for this 20-core dev box. Confining it to
# six cores while it still spawns 20 GC threads would put GC pauses directly
# on the cores §11's hot-path discipline exists to keep clear. Dev scaffold
# stays in system.slice; when Tradovate becomes trading-path at cutover, that
# membership gets decided against the core map on its own merits.
sudo tee /etc/systemd/system/nix-xvfb.service > /dev/null << 'UNIT'
[Unit]
Description=Nix virtual display :99 — headless X server for IB Gateway
Documentation=file:///home/bbt/nix/docs/dev_and_services_plan.md

[Service]
Type=simple
User=bbt
# Matches the invocation measured on the live process (ARC 011, /proc/<pid>/cmdline).
ExecStart=/usr/bin/Xvfb :99 -screen 0 1440x900x24
# A display server has no legitimate "finished" state: anything that stops it
# is a fault, including a clean exit.
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT

sudo tee /etc/systemd/system/nix-ibgateway.service > /dev/null << 'UNIT'
[Unit]
Description=IB Gateway (paper, Stage 0) — API endpoint on 127.0.0.1:4002
Documentation=file:///home/bbt/nix/docs/dev_and_services_plan.md
# BindsTo, not Requires. Requires propagates a failed *start* and an explicit
# stop, but leaves this unit running when nix-xvfb.service dies on its own. A
# Gateway whose X server vanished is the exact "unit active, thing unusable"
# state check_ibgateway_service.py exists to catch — better to make it
# impossible than to detect it. BindsTo stops this unit whenever the display
# goes away for any reason; After orders the two on the way up.
BindsTo=nix-xvfb.service
After=nix-xvfb.service
# systemd-analyze verify (ARC 011) rejected these in [Service]: rate-limiting
# is a unit-level property, and a misplaced key here is silently ignored — a
# restart loop with no brake, reported as a working config.
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User=bbt
Environment=DISPLAY=:99
WorkingDirectory=/home/bbt/ibgateway
# Ordering alone is not a real dependency: Xvfb's unit is "active" the moment
# it forks, milliseconds before the display accepts clients, and Gateway
# aborts on a display it cannot open. Wait for the display to actually answer.
ExecStartPre=/bin/sh -c 'for _ in $(seq 30); do xdpyinfo -display :99 >/dev/null 2>&1 && exit 0; sleep 1; done; exit 1'
# The install4j launcher, not the raw java argv: the live process's argv still
# contains unsubstituted ${installer:jtsConfigDir} / ${installer:cmdLineArgs}
# placeholders, and its JRE path carries a generated hash. The launcher execs
# the JVM (it does not fork), so Type=simple tracks the real process.
ExecStart=/home/bbt/ibgateway/ibgateway
# on-failure, not always: a crash or an OOM kill must bring it back, but an
# operator who deliberately shuts Gateway down must not have to fight systemd.
Restart=on-failure
RestartSec=15

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable nix-xvfb.service
sudo systemctl enable nix-ibgateway.service

echo "== install.sh: verify.py (end-of-install run, per elements_v2.md §1.3) =="
# System interpreter (§9.5), scripts/verify.py (§13 — no root copy exists),
# --mode install so absent components get installed, --privilege all so this
# human-present, sudo-capable run covers both user- and root-privilege
# checks in one pass (§8), --allow-interactive since only install.sh may run
# INTERACTIVE checks (§9.2).
VERIFY_EXIT=0
/usr/bin/python3 "$NIX_HOME/scripts/verify.py" \
    --mode install --privilege all --allow-interactive --verbose || VERIFY_EXIT=$?
case "$VERIFY_EXIT" in
    0)
        echo "verify.py: all checks PASS"
        ;;
    2)
        # §4.2: exit 2 is CANNOT_MEASURE/SKIPPED — not a failure. Reported
        # clearly but must not abort the install (CLAUDE.md directive 4:
        # fail closed and loud, not fail closed and silent).
        echo "verify.py: exit 2 — one or more checks could not be measured; review the output above"
        ;;
    *)
        # Exit 1: a real FAIL_REPAIRABLE/FAIL_NEEDS_OPERATOR. Surfaced loudly
        # and install.sh stops here rather than printing "done" over a node
        # that is not actually provisioned.
        echo "verify.py: exit $VERIFY_EXIT — FAILURE; node is NOT fully provisioned; review the output above" >&2
        exit "$VERIFY_EXIT"
        ;;
esac

echo "== install.sh: done =="
