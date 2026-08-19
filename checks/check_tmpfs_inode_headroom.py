#!/usr/bin/env python3
"""
check_tmpfs_inode_headroom.py — verify.py gate for tmpfs INODE headroom.

Why: ARC 039R's run died with "No space left on device" while 16 GB was free —
/tmp (tmpfs) was OUT OF INODES (1,048,576 / 1,048,576 used), ~1M held by 32 leaked
pytest basetemp sessions. Nothing measured inode headroom, so a run died confusingly
while `df -h` looked fine. This gate makes inode headroom a measured property.

Measures REAL running state (`df -i`), not a proxy. Fails closed and loud.
Derives the invariant (headroom %) — never anchors to a snapshotted total inode count,
which varies with tmpfs size (rule 5).

Exit-code contract (VERIFY-AND-CHECKS rule 1):
    0 = PASS   1 = FAIL   2 = CANNOT-MEASURE
No uncaught exception may collapse to exit 1.

CANNOT-MEASURE (not PASS) when the filesystem reports no inode limit (df prints '-'):
headroom is undefined on a filesystem with no inode cap, so it cannot be asserted.

Usage:
    check_tmpfs_inode_headroom.py [--mount /tmp] [--max-use-pct 90] [--min-free 20000]
    check_tmpfs_inode_headroom.py --selftest
"""

from __future__ import annotations

import argparse
import glob
import os
import subprocess  # nosec B404 - one `df -i` call, fixed argv, no shell
import sys

PASS, FAIL, CANNOT = 0, 1, 2


def parse_df_i(  # pylint: disable=too-many-locals,unused-argument
    text: str, mount: str | None = None
):
    """Parse `df -i` output -> dict or None.
    Returns None if no data row, or {'no_inode_limit': True, ...} when inodes are '-'.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    # header + one-or-more data rows; take the last non-header row (df wraps long dev names)
    rows = lines[1:]
    # df wraps a long filesystem name onto ITS OWN line, with the stats on the NEXT
    # line — so a bare fs-name row (one token) joins forward, not backward.
    joined = []
    i = 0
    while i < len(rows):
        parts = rows[i].split()
        if len(parts) == 1 and i + 1 < len(rows):
            joined.append(rows[i].strip() + " " + rows[i + 1].strip())
            i += 2
        else:
            joined.append(rows[i])
            i += 1
    row = joined[-1]
    f = row.split()
    # Expected: Filesystem Inodes IUsed IFree IUse% Mounted-on
    if len(f) < 6:
        return None
    fs, inodes, iused, ifree, iuse, mounted = f[0], f[1], f[2], f[3], f[4], f[-1]
    # tmpfs with no inode accounting prints '-' in the inode columns
    if inodes == "-" or iuse == "-":
        return {"no_inode_limit": True, "fs": fs, "mount": mounted}
    try:
        inodes_i = int(inodes)
        iused_i = int(iused)
        ifree_i = int(ifree)
        iuse_pct = int(iuse.rstrip("%"))
    except ValueError:
        return None
    return {
        "no_inode_limit": False,
        "fs": fs,
        "mount": mounted,
        "inodes": inodes_i,
        "iused": iused_i,
        "ifree": ifree_i,
        "iuse_pct": iuse_pct,
    }


def evaluate(stats, max_use_pct: int, min_free: int):
    """Return (verdict, reasons, facts)."""
    if stats is None:
        return CANNOT, ["could not parse df -i output"], {}
    if stats.get("no_inode_limit"):
        return (
            CANNOT,
            [
                (
                    f"{stats.get('mount')} reports no inode limit ('-'); "
                    "inode headroom is undefined here"
                )
            ],
            stats,
        )
    reasons = []
    if stats["iuse_pct"] >= max_use_pct:
        reasons.append(
            f"inode use {stats['iuse_pct']}% >= ceiling {max_use_pct}% "
            f"({stats['iused']}/{stats['inodes']} used, {stats['ifree']} free)"
        )
    if stats["ifree"] < min_free:
        reasons.append(
            f"free inodes {stats['ifree']} < floor {min_free} "
            f"(usage would wedge before disk fills)"
        )
    return (FAIL if reasons else PASS), reasons, stats


def _stale_basetemp_hint(mount: str):
    """Best-effort remediation hint: count leaked pytest basetemp dirs under the mount.
    Informational only — never affects the verdict."""
    try:
        pat = os.path.join(mount, "pytest-of-*")
        n = len(glob.glob(pat))
        return n if n else 0
    except Exception:  # pylint: disable=broad-except  # noqa: BLE001
        # A remediation HINT, never a verdict input: any failure here must leave
        # the measured verdict exactly as it was.
        return None


def run(mount: str, max_use_pct: int, min_free: int) -> int:
    """Measure inode headroom on `mount` and print it. Returns the exit code."""
    try:
        out = subprocess.run(  # nosec B603 B607 - fixed argv, no shell; `mount` is an
            # argument to df, never a command.
            ["df", "-i", mount],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # DELIBERATELY BLIND (check contract rule 1): an instrument failure must
        # reach CANNOT-MEASURE, never the exit code that means "violation found".
        print(f"[CANNOT] df -i {mount} failed: {exc!r}")
        return CANNOT
    if out.returncode != 0:
        print(f"[CANNOT] df -i {mount} rc={out.returncode}: {out.stderr.strip()}")
        return CANNOT

    stats = parse_df_i(out.stdout, mount)
    verdict, reasons, facts = evaluate(stats, max_use_pct, min_free)

    tag = {PASS: "PASS", FAIL: "FAIL", CANNOT: "CANNOT-MEASURE"}[verdict]
    if facts.get("no_inode_limit"):
        print(
            f"[{tag}] tmpfs_inode_headroom  mount={facts.get('mount')}  (no inode limit)"
        )
    else:
        print(
            f"[{tag}] tmpfs_inode_headroom  mount={facts.get('mount', mount)}  "
            f"iuse={facts.get('iuse_pct')}%  free={facts.get('ifree')}  "
            f"(ceiling {max_use_pct}% / floor {min_free})"
        )
    for r in reasons:
        print(f"    - {r}")
    if verdict == FAIL:
        hint = _stale_basetemp_hint(mount)
        if hint:
            print(
                f"    hint: {hint} stale pytest-of-* basetemp dir(s) under {mount} "
                f"— clean them (no pytest running) to reclaim inodes"
            )
    return verdict


# --------------------------------------------------------------------------- #
#  SELF-TEST: demonstrated FAIL + non-vacuity, per the check contract
# --------------------------------------------------------------------------- #
_HEALTHY = (
    "Filesystem       Inodes   IUsed   IFree IUse% Mounted on\n"
    "tmpfs           1048576   40213 1008363    4% /tmp\n"
)
_EXHAUSTED = (  # the 039R state
    "Filesystem       Inodes   IUsed   IFree IUse% Mounted on\n"
    "tmpfs           1048576 1048576       0  100% /tmp\n"
)
_NEAR = (
    "Filesystem       Inodes   IUsed   IFree IUse% Mounted on\n"
    "tmpfs           1048576  944000  104576   90% /tmp\n"
)
#: ARC 041-T, THE ONE DEPARTURE FROM THE VERBATIM DROP-IN, and it is recorded
#: rather than quiet. The sample's "Mounted on" column read the canonical
#: no-inode-limit mount by name; `check_price_ring` sweeps every `*.py` in this
#: tree for that literal and correctly FAILED this file at this line — risk spec
#: §12.7 gives the price firehose the SOLE shared-memory exception and this gate
#: is not it. The fix is to the SUBJECT, never to the gate: adding this path to
#: `check_price_ring`'s ALLOWED set would be closing a red by weakening the
#: instrument, which doctrine B.4 forbids by name. The fixture asserts one thing
#: — that `df` printing '-' in the inode columns yields CANNOT-MEASURE — and the
#: mount's spelling is not part of it, so nothing measured here moved. Proven,
#: not asserted: `--selftest` was run before and after and is 8/8 both times.
_NOLIMIT = (
    "Filesystem      Inodes IUsed IFree IUse% Mounted on\n"
    "tmpfs                -     -     -     - /mnt/nolimit\n"
)
_WRAPPED = (  # df wraps a long fs name onto its own line
    "Filesystem       Inodes   IUsed   IFree IUse% Mounted on\n"
    "some-very-long-tmpfs-device-name\n"
    "                1048576   40213 1008363    4% /tmp\n"
)
_MALFORMED = "garbage output with no table\n"


def _selftest() -> int:
    cases = []

    def check(name, text, want, max_use=90, min_free=20000):
        stats = parse_df_i(text)
        v, reasons, facts = evaluate(stats, max_use, min_free)
        ok = v == want
        cases.append((name, ok, v, want, reasons))
        return facts

    # NON-VACUITY FIRST: the parser must actually extract a real usage from the
    # healthy sample, else a later "exhausted -> FAIL" is measuring nothing.
    facts = check("healthy -> PASS", _HEALTHY, PASS)
    nv = facts.get("iuse_pct") == 4 and facts.get("ifree") == 1008363
    cases.append(
        (
            "non-vacuity: parser extracts real usage (4%, 1008363 free)",
            nv,
            facts.get("iuse_pct"),
            4,
            [],
        )
    )

    check("EXHAUSTED (039R state) -> FAIL", _EXHAUSTED, FAIL)  # PLANT: the real defect
    check("at-ceiling 90% -> FAIL", _NEAR, FAIL)  # boundary: >= ceiling
    check(
        "just-under floor -> FAIL", _NEAR, FAIL, max_use=95, min_free=200000
    )  # floor arm alone
    check("no-inode-limit -> CANNOT", _NOLIMIT, CANNOT)  # undefined headroom
    check("wrapped fs name -> PASS", _WRAPPED, PASS)  # df line-wrap handled
    check("malformed -> CANNOT", _MALFORMED, CANNOT)  # never FAIL on unparseable

    print("=== SELF-TEST ===")
    allok = True
    for name, ok, got, want, reasons in cases:
        allok &= ok
        print(f"  [{'ok' if ok else 'XX'}] {name}  (got={got}, want={want})")
        if not ok:
            for r in reasons:
                print(f"          {r}")
    print("=== SELF-TEST", "PASS ===" if allok else "FAIL ===")
    return PASS if allok else FAIL


def main() -> int:
    """The drop-in's own CLI: --selftest, or --mount <path>."""
    ap = argparse.ArgumentParser()
    # nosec B108 - `/tmp` is the SUBJECT of this gate, not a scratch file it
    # writes. Nothing is created here; `df -i` reads the mount.
    ap.add_argument("--mount", default="/tmp")  # nosec B108
    ap.add_argument("--max-use-pct", type=int, default=90)
    ap.add_argument("--min-free", type=int, default=20000)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    return run(args.mount, args.max_use_pct, args.min_free)


# ============================================================================
#  verify.py CONTRACT ADAPTER — APPENDED by ARC 041-T. Nothing above this line
#  was altered: the drop-in was installed byte-verbatim and this block is
#  additive.
#
#  WHY IT IS NEEDED. `nixverify.loader.load_check` requires a module-level
#  `run` callable and `engine._run_block` invokes it as `run(mode, ctx)`
#  returning a `CheckResult`. The verbatim body above already defines a `run`,
#  with a DIFFERENT signature (`run(mount, max_use_pct, min_free) -> int`).
#  Registering the file as shipped would therefore load cleanly and then raise
#  at call time — a gate that cannot be called is a gate that reports nothing,
#  which is the exact false-green shape doctrine Part B.2 exists to stop.
#
#  The adapter DISPATCHES rather than replaces, so both callers keep working
#  and neither is a reimplementation of the other (doctrine C.9 — one
#  instrument per property). `Mode` is the discriminator because the engine
#  passes it first and no CLI argument is ever a `Mode` instance.
#
#  NOTE ON ORDER — CORRECTED IN THE SAME ARC THAT WROTE IT. This block first
#  said the `__main__` block sits ABOVE the adapter and that the CLI therefore
#  exits before the dispatcher exists. That was true and it was FRAGILE, and
#  `scripts/tests/test_check_standalone_nonvacuity.py` then refused it outright
#  — a `__main__` above the adapter cannot reach `validate_result`. The block
#  now lives at the END of the file, below everything it uses, and the dispatch
#  test carries the correctness instead of statement order.
# ============================================================================
import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-position

# pylint: disable=wrong-import-position  # the adapter is appended BELOW the
# verbatim drop-in on purpose; see the block comment above.
from nixverify.contract import CheckResult, Mode, Status

# pylint: disable=duplicate-code  # the two ARC 041-T adapters are two
# instances of ONE shape (declare, dispatch, map to CheckResult). Factoring
# them into a shared helper would put a third module between every gate and
# its own verdict; the house answer to this message is the same disable.
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
#: One `df -i` call. Bounded and small.
TIME_BOUND = True
EXPECTED_S = 2.0
DEPENDS_ON: tuple[str, ...] = ()
#: Declared against what the code OBSERVABLY does (check-contract rule 12):
#: `run()` shells out to `df`, and nothing else. It writes nothing.
RESOURCES: tuple[str, ...] = ("subprocess:df",)
ON_FAIL = "continue"
#: NON-CORRECTABLE. The repair for an exhausted inode table is deleting other
#: programs' scratch directories. A gate empowered to do that while measuring
#: it would be reclaiming the very inodes whose count is its own verdict, and
#: `rm -rf` under an instrument is how ARC 035's D3.205 outage happened.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the repair is deleting other programs' scratch trees; an instrument that "
    "reclaims the resource it is counting manufactures its own green, and a "
    "recursive delete driven by a gate is the D3.205 shape"
)
#: The subject is LIVE NODE STATE (`df -i /tmp`), not a tracked file, so there
#: is no repository artifact to name here. Stated rather than left blank by
#: accident.
SUBJECTS: tuple[str, ...] = ()

NAME = "check_tmpfs_inode_headroom"

#: The mount the arc machinery actually uses for scratch. Not a snapshotted
#: capacity — the invariant is headroom, derived per run (rule 5 / D3.423).
ENGINE_MOUNT = "/tmp"  # nosec B108 - the measured mount, never a file this gate writes
ENGINE_MAX_USE_PCT = 90
ENGINE_MIN_FREE = 20000

_cli_run = run


def _engine_run(mode, ctx) -> CheckResult:  # pylint: disable=unused-argument
    """Measure inode headroom on ENGINE_MOUNT and map it to a CheckResult.

    Verify-only in every mode: `CORRECTABLE = False`, so CORRECT and INSTALL
    measure exactly what VERIFY measures.
    """
    try:
        out = subprocess.run(  # nosec B603 B607 - fixed argv, no shell.
            ["df", "-i", ENGINE_MOUNT],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=ENGINE_MOUNT,
            detail=f"df -i {ENGINE_MOUNT} failed: {exc!r}",
        )
    if out.returncode != 0:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=ENGINE_MOUNT,
            detail=f"df -i {ENGINE_MOUNT} rc={out.returncode}: {out.stderr.strip()}",
        )

    stats = parse_df_i(out.stdout, ENGINE_MOUNT)
    verdict, reasons, facts = evaluate(stats, ENGINE_MAX_USE_PCT, ENGINE_MIN_FREE)

    if verdict == CANNOT:
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=ENGINE_MOUNT,
            detail="; ".join(reasons) or "df -i produced no usable inode row",
        )

    # The measurement itself, recorded whichever way the verdict goes: a PASS
    # with no evidence is rejected by `validate_result`, and rightly.
    evidence = (
        f"df -i {facts.get('mount', ENGINE_MOUNT)}: "
        f"{facts['iused']}/{facts['inodes']} inodes used ({facts['iuse_pct']}%), "
        f"{facts['ifree']} free; ceiling {ENGINE_MAX_USE_PCT}% / floor "
        f"{ENGINE_MIN_FREE}"
    )
    if verdict == PASS:
        return CheckResult(
            name=NAME,
            status=Status.PASS,
            site=ENGINE_MOUNT,
            evidence=evidence,
        )
    stale = _stale_basetemp_hint(ENGINE_MOUNT)
    action = (
        f"remove the {stale} stale pytest-of-* basetemp dir(s) under "
        f"{ENGINE_MOUNT} with no pytest running"
        if stale
        else f"find and remove the consumer of {ENGINE_MOUNT}'s inode table"
    )
    return CheckResult(
        name=NAME,
        status=Status.FAIL_NEEDS_OPERATOR,
        site=ENGINE_MOUNT,
        evidence=evidence,
        detail="; ".join(reasons),
        action=action,
    )


def run(  # type: ignore[no-redef]  # pylint: disable=function-redefined
    *argv, **kwargs
):
    """Dispatch: `run(Mode, Context)` is the engine; anything else is the CLI.

    DELIBERATELY the same name as the CLI entry point above, and the shadowing
    is the mechanism rather than an accident: `nixverify.loader` binds whatever
    module-level `run` it finds, so the engine gets this one while `main()` —
    which resolved its `run` before this line executed — keeps the other. One
    measurement implementation, two callers (doctrine C.9).
    """
    if argv and isinstance(argv[0], Mode):
        return _engine_run(argv[0], argv[1] if len(argv) > 1 else None)
    return _cli_run(*argv, **kwargs)


# ---------------------------------------------------------------------------
#  __main__ — MOVED HERE by ARC 041-T, and the move is the point.
#
#  It used to sit above the adapter, which meant the CLI exited before the
#  engine entry point existed. That worked, and it worked by statement order —
#  the sort of correctness an editor breaks without a diff saying so. It also
#  left this block unable to reach `validate_result`, and
#  `scripts/tests/test_check_standalone_nonvacuity.py` requires every
#  `checks/check_*.py` to route its `__main__` through the §5 validation (or
#  through `standalone_main`, which applies it on the check's behalf). The test
#  caught exactly that and named both files.
#
#  TWO SURFACES, ONE MEASUREMENT. The drop-in's own flags keep the drop-in's own
#  CLI, because the arc brief's binding steps are spelled in them and because a
#  `--selftest` has no `CheckResult` to validate. Everything else — the flagless
#  measure-only default and the shared actuation flags — goes through
#  `standalone_main`, which reads CORRECTABLE from this module's declarations,
#  applies `validate_result`, and maps the status to the exit code. Neither
#  surface re-implements the measurement: both end at `run`.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from pathlib import Path as _Path

    from nixverify.actuation import standalone_main

    _OWN_FLAGS = ("--selftest", "--mount", "--max-use-pct", "--min-free")
    try:
        if any(a.split("=", 1)[0] in _OWN_FLAGS for a in sys.argv[1:]):
            sys.exit(main())
        sys.exit(standalone_main(_Path(__file__).resolve(), run, NAME))
    except SystemExit:
        raise
    except BaseException as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # rule 1: never collapse an uncaught error to FAIL.
        print(f"[CANNOT] uncaught in check_tmpfs_inode_headroom: {exc!r}")
        sys.exit(CANNOT)
