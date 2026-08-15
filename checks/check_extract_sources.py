#!/usr/bin/env python3
"""`databases/schema/extract_sources.py`, DRIVEN — the schema-extraction program.

ONE gate, ONE property: given a spec containing `filename=`-tagged fenced code
blocks, the program extracts EXACTLY those blocks, byte-for-byte, to the named
files, and marks a `.sh` extraction executable (`0o755`) while leaving a
non-`.sh` extraction NOT executable. This is the whole of what the 17-line
program claims to do (its own docstring: *"Extract every filename=-tagged
fenced block from the spec into files"*), and it had never been reachable
from any instrument (D3.104's "NAMED BY NOTHING" — CHECK-DEBT, this arc).

WHY DRIVEN VIA SUBPROCESS, IN AN ISOLATED CWD. The program writes to `name` —
a bare relative path taken directly from the spec's own `filename=` tag —
resolved against whatever the CURRENT WORKING DIRECTORY happens to be when it
runs (there is no `os.chdir` and no output-directory argument). Driving it
in-process would write into THIS process's cwd; every invocation here passes
`cwd=<tmp dir>` so every write this gate causes lands in a throwaway
directory and never touches the working tree (doctrine C.8, generalised from
"never touch a production artifact" to "never touch the production cwd").

§7.12 — WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING?

 1. The subject could be absent. CLOSED: CANNOT_MEASURE naming the missing
    path (§17, never a PASS).
 2. A spec with no matching blocks could report a clean run (`extracted`
    printed 0 times) and look identical to "the extraction is broken".
    CLOSED: the drive's fixture spec has TWO real blocks (one `.sh`, one
    plain), and the assertion is that BOTH files exist with the EXACT
    expected content — never merely that the process exited 0.
 3. The `.sh` executable-bit claim could be checked only on a `.sh` file,
    which is silent about whether the program marks EVERYTHING executable
    (in which case the check would pass by coincidence on the one file it
    looks at). CLOSED: the fixture also extracts a NON-`.sh` file and asserts
    it is NOT executable — the two assertions together prove the `.sh`
    branch is discriminating, not blanket.
 4. A plant that breaks extraction could be judged only by "the process
    exited non-zero", which conflates a program that CRASHES with one that
    runs and produces WRONG output. CLOSED: every plant here still exits 0
    (the program has no error handling to trip) and the gate's assertion is
    always over the FILESYSTEM STATE the run produced, read back — not the
    exit code.

This gate is NON-CORRECTABLE and has no `.sh`/no-`.sh` proxy: a defect found
here is in program logic that decides how a database-schema source lands on
disk, which is a human's call, not an unattended rewrite.
"""

from __future__ import annotations

import subprocess  # nosec B404 - fixed argv, shell=False, no untrusted input
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code,too-few-public-methods,too-many-locals
# missing-function-docstring,missing-class-docstring: the test doubles'
# verbs are named after the ports they stand in for, and each arm function's
# name states its own property (§7.12 answer per arm) — a docstring would
# restate the name. too-few-public-methods: several doubles are one-verb
# stand-ins for a frozen port's single relevant method. too-many-locals: an
# arm's local count is the drive's own inputs/outputs, not incidental state.
# pylint: disable=missing-function-docstring,missing-class-docstring
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = True
EXPECTED_S = 5.0
DEPENDS_ON: tuple[str, ...] = ()
#: Spawns `sys.executable` with a tempdir cwd; writes land only there.
#: `subprocess:python` matches by BASENAME (`nixverify.observe.covers`), and
#: **basename matching is what makes this declaration launch-mode dependent, not
#: what makes it safe** (CHECK-DEBT D3.140). One token covers every venv on this
#: box, because a venv interpreter is named `python` — and it covers NONE of the
#: one documented interpreter that is not in a venv, `/usr/bin/python3`, whose
#: basename is `python3`. `verify.py` documents itself as running under system
#: python3 and every `nix-verify*.service` unit pins it, so this gate really is
#: launched both ways and BOTH basenames are spawned in production. Both are
#: therefore declared; dropping either makes this declaration false under the
#: launch mode it dropped.
RESOURCES: tuple[str, ...] = (
    "file-write:/tmp",
    "subprocess:python",
    "subprocess:python3",
)
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "a defect here is in the logic that decides WHAT lands on disk from a "
    "database-schema spec and whether it is made executable — a human's call "
    "about program correctness, not a value an unattended rewrite should "
    "silently settle"
)
SUBJECTS: tuple[str, ...] = ("databases/schema/extract_sources.py",)

NAME = "check_extract_sources"

SCRIPT_FILE = "databases/schema/extract_sources.py"

#: The fixture spec: one `.sh` block and one plain-text block, each with
#: distinguishable content so a truncated or mangled extraction is visible.
_FIXTURE_SPEC = (
    "# Fixture schema spec\n\n"
    "Some prose before the first block.\n\n"
    "```bash filename=setup.sh\n"
    "#!/usr/bin/env bash\n"
    "echo hello from setup\n"
    "```\n\n"
    "More prose between blocks.\n\n"
    "```sql filename=schema.sql\n"
    "CREATE TABLE t (id INTEGER);\n"
    "```\n"
)

_EXPECTED = {
    "setup.sh": "#!/usr/bin/env bash\necho hello from setup\n",
    "schema.sql": "CREATE TABLE t (id INTEGER);\n",
}


class Finding(NamedTuple):
    site: str
    why: str


def drive(script: Path, python: str) -> tuple[Path, list[Finding]]:
    """Run `script` against the fixture spec in an isolated tmp cwd.

    Returns (workdir, findings). `workdir` is returned so the caller can read
    back filesystem state that a plant may have altered beyond what this
    function itself checks (kept minimal and shared between the real drive
    and each plant's drive).
    """
    tmp = Path(tempfile.mkdtemp(prefix="check_extract_sources_"))
    spec = tmp / "spec.md"
    spec.write_text(_FIXTURE_SPEC, encoding="utf-8")
    findings: list[Finding] = []
    site = f"{SCRIPT_FILE}:subprocess"
    try:
        proc = subprocess.run(  # nosec B603 - literal argv, python interpreter + script path
            [python, str(script), "spec.md"],
            cwd=tmp,
            capture_output=True,
            text=True,
            timeout=EXPECTED_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        findings.append(Finding(site, f"did not complete within {EXPECTED_S}s"))
        return tmp, findings
    if proc.returncode != 0:
        findings.append(
            Finding(site, f"exited {proc.returncode}, stderr={proc.stderr[:300]!r}")
        )
        return tmp, findings

    for name, expected_content in _EXPECTED.items():
        path = tmp / name
        if not path.is_file():
            findings.append(Finding(f"{SCRIPT_FILE}:{name}", "was not extracted"))
            continue
        got = path.read_text(encoding="utf-8")
        if got != expected_content:
            findings.append(
                Finding(
                    f"{SCRIPT_FILE}:{name}",
                    f"content is {got!r}, expected {expected_content!r}",
                )
            )
        mode = path.stat().st_mode & 0o777
        is_exec = bool(mode & 0o111)
        if name.endswith(".sh") and not is_exec:
            findings.append(
                Finding(
                    f"{SCRIPT_FILE}:{name}",
                    f"mode {oct(mode)} is NOT executable — .sh must be 0o755",
                )
            )
        if not name.endswith(".sh") and is_exec:
            findings.append(
                Finding(
                    f"{SCRIPT_FILE}:{name}",
                    f"mode {oct(mode)} IS executable — only .sh extractions "
                    "should be marked executable",
                )
            )
    return tmp, findings


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    try:
        script = ctx.nix_home / SCRIPT_FILE
        if not script.is_file():
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                detail=f"{SCRIPT_FILE} is absent — nothing to measure (§17)",
            )
        _workdir, findings = drive(script, sys.executable)
        evidence = (
            f"{SCRIPT_FILE}: ran as a subprocess (cwd=isolated tmp dir) against a "
            f"2-block fixture spec ({', '.join(sorted(_EXPECTED))}), read back "
            "extracted content byte-for-byte and the executable bit on both a "
            ".sh and a non-.sh extraction"
        )
        if findings:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(f.site for f in findings),
                evidence=evidence,
                detail="; ".join(f"{f.site}: {f.why}" for f in findings),
            )
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
