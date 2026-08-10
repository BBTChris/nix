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
# the one validated reader of that file (VERIFY-AND-CHECKS.md §7) — its
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
Documentation=file:///home/bbt/nix/docs/VERIFY-AND-CHECKS.md
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
Documentation=file:///home/bbt/nix/docs/VERIFY-AND-CHECKS.md

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /home/bbt/nix/scripts/verify.py \
    --mode correct --privilege root --maintenance --verbose
SuccessExitStatus=0 2
UNIT

sudo tee /etc/systemd/system/nix-verify-root.timer > /dev/null << 'UNIT'
[Unit]
Description=Weekly Nix privileged verification
Documentation=file:///home/bbt/nix/docs/VERIFY-AND-CHECKS.md

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
Documentation=file:///home/bbt/nix/docs/VERIFY-AND-CHECKS.md

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
Documentation=file:///home/bbt/nix/docs/VERIFY-AND-CHECKS.md

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
