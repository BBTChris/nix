"""ARC 033 / 0.4 — the can-fail suite for `checks/check_calendar_schema.py`.

**THE REQUIREMENT THIS FILE EXISTS TO SATISFY:** prove the gate actually
reddens on a real defect in EACH declared arm, and that each red NAMES THE
REASON — the site and the condition — never the exit code or the status alone
(check contract v2 rule 11 / §18).

**No plant touches a production artifact** (doctrine C.8). Every control
builds a throwaway `nix_home` under `tmp_path` carrying every tracked `.py`
under `scripts/` and `checks/`, the whole `calendar_data/` directory and both
seams, `git init`s it (ARM B's scan set is `git ls-files`, so the throwaway
tree has to be a repository or the gate correctly refuses to measure),
perturbs its own private copy of one file, and drives the SHIPPED gate's own
bytes against it.

**THE HEADLINE PLANT is `test_runtime_module_reading_eth_open_ct_reddens`:**
the SUBJECT defect the whole gate exists to catch is a decision path reading a
stored local-time field, so the plant makes `scripts/crucible/calendar.py` —
the runtime query module every §6 consumer will call — read `eth_open_ct`, and
asserts the gate names that file, that line, and that field.

`test_a_NEWLY_INVENTED_local_column_is_discovered` is the one that proves the
detector is not a hardcoded list: it invents a column name that appears
NOWHERE in the gate, in this file's assertions, or in the tree, plants both
the column and a reader of it, and requires the gate to find it anyway.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.append(str(REPO / "checks"))

import check_calendar_schema as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)
from nixverify.gitenv import scrubbed_env  # pylint: disable=wrong-import-position

DATA = "scripts/crucible/calendar_data"
SESSIONS = f"{DATA}/cme_calendar_sessions.csv"
BREAKS = f"{DATA}/nix_break_windows.csv"
ROLLS = f"{DATA}/nix_roll_schedule.csv"
SYMBOLS = f"{DATA}/nix_symbol_map.csv"
EXT_PROV = f"{DATA}/nix_calendar_ext_provenance.json"
UP_PROV = f"{DATA}/cme_calendar_provenance.json"
RUNTIME = "scripts/crucible/calendar.py"
SEAM = "scripts/nixrisk/calendar_seam.py"
ALLOC_SEAM = "scripts/nixalloc/seam.py"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(  # nosec B603 B607 - fixed argv, no shell, throwaway repo
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        env=scrubbed_env(),
        timeout=120,
    )


@pytest.fixture(scope="session")
def base_home(tmp_path_factory) -> Path:
    """One throwaway repository, built once: every tracked `.py` under
    `scripts/` and `checks/` plus the whole `calendar_data/` directory.

    The full `.py` population is not decoration — ARM B refuses to certify a
    scan below `FLOORS["scanned_files"]`, so a fixture holding six files would
    make every control below CANNOT_MEASURE and prove nothing.
    """
    root = tmp_path_factory.mktemp("calendar-schema-base")
    listing = subprocess.run(  # nosec B603 B607 - fixed argv, no shell
        ["git", "ls-files", "--", "scripts", "checks"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_env(),
        timeout=120,
    ).stdout.splitlines()
    for rel in listing:
        src = REPO / rel
        if not src.is_file():
            continue
        if not (rel.endswith(".py") or rel.startswith(DATA)):
            continue
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dst)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    return root


@pytest.fixture
def home(base_home: Path, tmp_path: Path) -> Path:
    """A private view of the base repository, safe to perturb.

    HARDLINKED, not copied. The base tree carries the whole 9 MB vendored
    calendar plus 226 modules, and copying it per control filled /tmp during
    this arc — measured, and the reason this is not the obvious `copytree`.
    Every write below therefore goes through `_write`, which UNLINKS before
    writing so a perturbation breaks the link instead of editing the shared
    inode. `Path.write_text` alone truncates in place and would corrupt the
    base for every later control in the session.
    """
    target = tmp_path / "home"
    shutil.copytree(base_home, target, copy_function=os.link)
    return target


def _write(path: Path, text: str) -> None:
    """Replace a hardlinked file's CONTENT by replacing the file."""
    path.unlink(missing_ok=True)
    path.write_text(text, encoding="utf-8")


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _track(nix_home: Path) -> None:
    """Re-stage, so `git ls-files` sees a file the plant created."""
    _git(nix_home, "add", "-A")


def _plant(nix_home: Path, rel: str, old: str, new: str) -> None:
    """Rewrite a COPIED file. Fails loudly if the anchor moved or is ambiguous."""
    path = nix_home / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, (
        f"{rel}: anchor appears {text.count(old)} times, not once — the plant "
        "would measure something other than what it names"
    )
    _write(path, text.replace(old, new))


def _restamp_ext(nix_home: Path) -> None:
    """Re-issue the EXTENSION stamp over whatever the CSVs now say.

    Used by the controls that must isolate ONE arm: without it, any edit to an
    extension CSV also breaks ARM C, and a red naming two conditions does not
    prove the arm under test fired.
    """
    stamp_path = nix_home / EXT_PROV
    stamp = json.loads(stamp_path.read_text(encoding="utf-8"))
    h = hashlib.sha256()
    for name in gate.EXT_ARTIFACTS:
        h.update((nix_home / DATA / name).read_bytes())
    stamp["content_hash_sha256"] = h.hexdigest()
    _write(stamp_path, json.dumps(stamp, indent=2, sort_keys=True) + "\n")


def _red(result, *, site_contains: str, why_contains: str) -> None:
    assert result.status is Status.FAIL_NEEDS_OPERATOR, (
        f"expected FAIL_NEEDS_OPERATOR, got {result.status!r}: "
        f"{result.detail or result.evidence}"
    )
    assert site_contains in (result.site or ""), (
        f"site {result.site!r} does not name {site_contains!r}"
    )
    assert why_contains in (result.detail or ""), (
        f"detail does not name {why_contains!r}: {result.detail}"
    )


def _blue(result, *, why_contains: str) -> None:
    assert result.status is Status.CANNOT_MEASURE, (
        f"expected CANNOT_MEASURE, got {result.status!r}: {result.detail}"
    )
    assert why_contains in (result.detail or ""), (
        f"detail does not name {why_contains!r}: {result.detail}"
    )


# ---------------------------------------------------------------------------
# The pristine tree
# ---------------------------------------------------------------------------


def test_pristine_tree_passes(home: Path) -> None:
    """Without a control that PASSES on the shipped bytes, every red below
    could be the gate failing for an unrelated reason."""
    result = _run(home)
    assert result.status is Status.PASS, f"{result.status}: {result.detail}"
    assert "ARM A" in result.evidence and "ARM E" in result.evidence


# ---------------------------------------------------------------------------
# ARM A — UTC canonicity (§12.3)
# ---------------------------------------------------------------------------


def test_non_zulu_instant_in_a_decision_column_reddens(home: Path) -> None:
    """A single break-window row rewritten to a local-offset instant."""
    path = home / BREAKS
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    lines[1] = lines[1].replace("Z,", "-0600,", 1)
    _write(path, "".join(lines))
    _restamp_ext(home)
    _red(
        _run(home),
        site_contains="nix_break_windows.csv:2:break_start_utc",
        why_contains="is not a Zulu UTC instant",
    )


def test_a_local_offset_column_in_an_extension_artifact_reddens(home: Path) -> None:
    """§12.3: the artifacts THIS arc owns carry no exchange-local column."""
    path = home / SYMBOLS
    rows = path.read_text(encoding="utf-8").splitlines()
    rows[0] += ",listed_ct"
    for i in range(1, len(rows)):
        rows[i] += ",2025-07-14T08:30:00-0500"
    _write(path, "\n".join(rows) + "\n")
    _restamp_ext(home)
    _red(
        _run(home),
        site_contains="nix_symbol_map.csv:listed_ct",
        why_contains="carries a local UTC offset",
    )


# ---------------------------------------------------------------------------
# ARM B — no decision path reads a stored local-time field
# ---------------------------------------------------------------------------


def test_runtime_module_reading_eth_open_ct_reddens(home: Path) -> None:
    """**THE HEADLINE PLANT.** The runtime query module every §6 consumer will
    call is made to read the stored Central-time column, and the gate must
    name the file, the line, and the field."""
    # A REAL, executable read on the loader's hot path — not a string in a
    # comment, which the AST discards and which would prove nothing. This is
    # exactly the shape the hazard takes in the wild: a later arc wants
    # "exchange local", sees the column sitting in the CSV, and reads it.
    _plant(
        home,
        RUNTIME,
        'is_early_close=row["is_early_close"] == "1",',
        'is_early_close=row["eth_open_ct"].endswith("-0600"),',
    )
    result = _run(home)
    _red(
        result,
        site_contains=f"{RUNTIME}:",
        why_contains="reads stored local-time field 'eth_open_ct'",
    )
    assert "cme_calendar_sessions.csv" in result.detail, (
        "the red must say WHICH artifact the field belongs to, or an operator "
        f"cannot act on it: {result.detail}"
    )


def test_the_seam_reading_a_local_field_reddens(home: Path) -> None:
    """The scan is not runtime-module-specific: any tracked file counts."""
    _plant(
        home,
        SEAM,
        "READ_ONLY_PORTS: tuple[str, ...] = (",
        'LOCAL_FALLBACK = "eth_close_ct"\n\nREAD_ONLY_PORTS: tuple[str, ...] = (',
    )
    _red(
        _run(home),
        site_contains=f"{SEAM}:",
        why_contains="reads stored local-time field 'eth_close_ct'",
    )


def test_a_NEWLY_INVENTED_local_column_is_discovered(home: Path) -> None:
    """The detector DISCOVERS local columns; it does not carry a list.

    The column name below appears nowhere in the gate and nowhere in the tree.
    If ARM B were a hardcoded `{"eth_open_ct", "eth_close_ct"}` this control
    would pass green and the arm would be decorative from the first new
    column onward.
    """
    invented = "settlement_local_stamp"
    assert invented not in (REPO / "checks/check_calendar_schema.py").read_text(
        encoding="utf-8"
    ), "the invented column must not appear in the gate, or this proves nothing"

    path = home / SESSIONS
    rows = path.read_text(encoding="utf-8").splitlines()
    rows[0] += f",{invented}"
    for i in range(1, len(rows)):
        rows[i] += ",2025-07-14T08:30:00-0500"
    _write(path, "\n".join(rows) + "\n")
    # The upstream stamp is not the subject here; re-issue both so ARM C stays
    # quiet and only ARM B can speak.
    up = json.loads((home / UP_PROV).read_text(encoding="utf-8"))
    h = hashlib.sha256()
    for name in gate.UPSTREAM_ARTIFACTS:
        h.update((home / DATA / name).read_bytes())
    up["content_hash_sha256"] = h.hexdigest()
    _write(home / UP_PROV, json.dumps(up, indent=2, sort_keys=True) + "\n")
    ext = json.loads((home / EXT_PROV).read_text(encoding="utf-8"))
    ext["upstream_content_hash_sha256"] = h.hexdigest()
    ext["upstream_stamped_hash_sha256"] = h.hexdigest()
    _write(home / EXT_PROV, json.dumps(ext, indent=2, sort_keys=True) + "\n")

    _plant(
        home,
        SEAM,
        "READ_ONLY_PORTS: tuple[str, ...] = (",
        f'LOCAL_FALLBACK = "{invented}"\n\nREAD_ONLY_PORTS: tuple[str, ...] = (',
    )
    _red(
        _run(home),
        site_contains=f"{SEAM}:",
        why_contains=f"reads stored local-time field '{invented}'",
    )


def test_an_exemption_whose_path_moved_reddens(home: Path) -> None:
    """A renamed exemption is a hole nobody scans; the gate must say so."""
    (home / "scripts/crucible/calendar_gen.py").unlink()
    _track(home)
    _red(
        _run(home),
        site_contains="SCAN_EXEMPTIONS:scripts/crucible/calendar_gen.py",
        why_contains="silently widens the set of files nobody scans",
    )


def test_the_generator_becoming_importable_from_the_runtime_module_reddens(
    home: Path,
) -> None:
    """The generator's exemption is only safe while it is not a decision path."""
    _plant(
        home,
        RUNTIME,
        "import csv\n",
        "import csv\n\nfrom crucible import calendar_gen  # noqa: F401\n",
    )
    _red(
        _run(home),
        site_contains=f"import-closure:{RUNTIME}",
        why_contains="would exempt a decision path",
    )


def test_no_local_column_at_all_is_CANNOT_MEASURE_not_PASS(home: Path) -> None:
    """§17: the read-ban's subject is absent, so the ban was not measured."""
    path = home / SESSIONS
    # Drop the two trailing local-time columns from every row, header included.
    rows = [
        ",".join(line.split(",")[:-2])
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    _write(path, "\n".join(rows) + "\n")
    up = json.loads((home / UP_PROV).read_text(encoding="utf-8"))
    h = hashlib.sha256()
    for name in gate.UPSTREAM_ARTIFACTS:
        h.update((home / DATA / name).read_bytes())
    up["content_hash_sha256"] = h.hexdigest()
    _write(home / UP_PROV, json.dumps(up, indent=2, sort_keys=True) + "\n")
    ext = json.loads((home / EXT_PROV).read_text(encoding="utf-8"))
    ext["upstream_content_hash_sha256"] = h.hexdigest()
    ext["upstream_stamped_hash_sha256"] = h.hexdigest()
    _write(home / EXT_PROV, json.dumps(ext, indent=2, sort_keys=True) + "\n")
    _blue(_run(home), why_contains="no stored local-time column was discovered")


def test_a_tree_that_is_not_a_git_repository_is_CANNOT_MEASURE(home: Path) -> None:
    """ARM B derives its scan set from git. No git, no scan, no verdict."""
    shutil.rmtree(home / ".git")
    _blue(_run(home), why_contains="cannot enumerate the scan set")


# ---------------------------------------------------------------------------
# ARM C — the provenance chain
# ---------------------------------------------------------------------------


def test_an_edited_extension_artifact_reddens(home: Path) -> None:
    """A hand-edited calendar with a stale stamp — the whole point of §6.5."""
    path = home / ROLLS
    text = path.read_text(encoding="utf-8")
    _write(path, text + text.splitlines(keepends=True)[-1])
    _red(
        _run(home),
        site_contains="nix_calendar_ext_provenance.json:content_hash_sha256",
        why_contains="HASH MISMATCH",
    )


def test_a_RESTAMPED_upstream_edit_breaks_the_chain(home: Path) -> None:
    """The property `check_crucible_calendar` structurally cannot make (C.9).

    Editing the upstream calendar and re-running its OWN generator leaves the
    upstream artifact internally consistent — bytes and stamp agree — and that
    gate stays green. The extension's chained copy of the upstream hash is
    written by a generator the upstream one does not run, so it does not.
    """
    path = home / SESSIONS
    text = path.read_text(encoding="utf-8")
    _write(path, text + text.splitlines(keepends=True)[-1])
    up = json.loads((home / UP_PROV).read_text(encoding="utf-8"))
    h = hashlib.sha256()
    for name in gate.UPSTREAM_ARTIFACTS:
        h.update((home / DATA / name).read_bytes())
    up["content_hash_sha256"] = h.hexdigest()
    _write(home / UP_PROV, json.dumps(up, indent=2, sort_keys=True) + "\n")
    _red(
        _run(home),
        site_contains="upstream_content_hash_sha256",
        why_contains="CHAIN BROKEN",
    )


def test_a_stamp_that_lies_about_what_it_covers_reddens(home: Path) -> None:
    """debug.md §7.12 hazard 4: a digest over an unknown set proves nothing."""
    stamp_path = home / EXT_PROV
    stamp = json.loads(stamp_path.read_text(encoding="utf-8"))
    stamp["content_hash_covers"] = [gate.EXT_PROVENANCE]
    _write(stamp_path, json.dumps(stamp, indent=2, sort_keys=True) + "\n")
    _red(
        _run(home),
        site_contains="content_hash_covers",
        why_contains="the two must name the same files",
    )


def test_an_unparseable_provenance_stamp_is_CANNOT_MEASURE(home: Path) -> None:
    """A stamp that cannot be read cannot be compared against (§17)."""
    _write(home / EXT_PROV, "{ not json")
    _blue(_run(home), why_contains="provenance stamp unparseable")


# ---------------------------------------------------------------------------
# ARM D — per-symbol keying, derived from BUCKET_OF
# ---------------------------------------------------------------------------


def test_a_symbol_added_to_BUCKET_OF_and_not_to_the_calendar_reddens(
    home: Path,
) -> None:
    """The live symbol set is BUCKET_OF's, and the calendar must track it."""
    _plant(
        home,
        ALLOC_SEAM,
        '    "ZN": CorrelationBucket.RATES,\n',
        '    "ZN": CorrelationBucket.RATES,\n    "ZB": CorrelationBucket.RATES,\n',
    )
    result = _run(home)
    _red(
        result,
        site_contains="nix_symbol_map.csv:symbol",
        why_contains="missing ['ZB']",
    )
    assert "nix_roll_schedule.csv" in result.detail, (
        "§7.5 gives every live symbol a roll schedule too; the red must name "
        f"both artifacts: {result.detail}"
    )


def test_a_symbol_mapped_to_an_unknown_product_group_reddens(home: Path) -> None:
    """A symbol with no session calendar has no §6.1 window."""
    path = home / SYMBOLS
    _write(
        path,
        path.read_text(encoding="utf-8").replace("equity_index", "equities", 1),
    )
    _restamp_ext(home)
    _red(
        _run(home),
        site_contains="nix_symbol_map.csv:ES",
        why_contains="the session artifact does not carry",
    )


def test_a_BUCKET_OF_that_cannot_be_found_is_CANNOT_MEASURE(home: Path) -> None:
    """debug.md §7.12 hazard 6: no source for the expected set means nothing was compared."""
    _plant(
        home,
        ALLOC_SEAM,
        "BUCKET_OF: Mapping[str, CorrelationBucket] = {",
        "BUCKET_OF_RENAMED: Mapping[str, CorrelationBucket] = {",
    )
    _blue(_run(home), why_contains="no `BUCKET_OF` dict literal found")


# ---------------------------------------------------------------------------
# ARM E — the read ports declare no mutating verb (§6.4)
# ---------------------------------------------------------------------------


def test_a_mutating_verb_on_a_read_port_reddens(home: Path) -> None:
    """§6.4: Allocator/Limiter READ CACHES ONLY."""
    _plant(
        home,
        SEAM,
        "    def state(self) -> CacheState:\n"
        '        """EMPTY / FRESH / STALE for the cache as a whole."""\n\n'
        "    def freshness(self) -> FreshnessStamp | None:\n"
        '        """The stamp a §6.4 staleness rule reads. `None` before first '
        'publish."""\n\n\n@runtime_checkable\nclass MarginBaselineReadPort',
        "    def state(self) -> CacheState:\n"
        '        """EMPTY / FRESH / STALE for the cache as a whole."""\n\n'
        "    def publish(self, sets: tuple[WindowSet, ...]) -> None:\n"
        '        """PLANTED SUBJECT DEFECT (doctrine C.8)."""\n\n'
        "    def freshness(self) -> FreshnessStamp | None:\n"
        '        """The stamp a §6.4 staleness rule reads. `None` before first '
        'publish."""\n\n\n@runtime_checkable\nclass MarginBaselineReadPort',
    )
    _red(
        _run(home),
        site_contains="WindowSetReadPort.publish",
        why_contains="Allocator/Limiter READ CACHES ONLY",
    )


def test_an_async_read_verb_reddens(home: Path) -> None:
    """The seam declares every read synchronous; the gate measures it."""
    _plant(
        home,
        SEAM,
        "    def front_contract(self, symbol: str, at: datetime)",
        "    async def front_contract(self, symbol: str, at: datetime)",
    )
    _red(
        _run(home),
        site_contains="RollScheduleReadPort.front_contract",
        why_contains="declared `async def`",
    )


def test_a_read_port_named_but_absent_reddens(home: Path) -> None:
    """A declaration over a subject that is not there certifies nothing."""
    _plant(
        home,
        SEAM,
        "class RollScheduleReadPort(Protocol):",
        "class RollScheduleReadPortRenamed(Protocol):",
    )
    _red(
        _run(home),
        site_contains="READ_ONLY_PORTS",
        why_contains="a declaration over an absent subject",
    )


# ---------------------------------------------------------------------------
# Non-vacuity floors and absent subjects (§17, doctrine C.4)
# ---------------------------------------------------------------------------


def test_a_collapsed_row_population_is_CANNOT_MEASURE_not_PASS(home: Path) -> None:
    """A scan over three rows finds no violation and would report PASS."""
    path = home / BREAKS
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    _write(path, "".join(lines[:4]))
    _restamp_ext(home)
    _blue(_run(home), why_contains="below the non-vacuity floor")


def test_an_absent_artifact_is_CANNOT_MEASURE_naming_it(home: Path) -> None:
    """§17: an absent subject is named, and the red says never-a-PASS."""
    (home / ROLLS).unlink()
    result = _run(home)
    _blue(result, why_contains="nix_roll_schedule.csv")
    assert "never a PASS" in result.detail


def test_an_unparseable_scanned_module_is_CANNOT_MEASURE(home: Path) -> None:
    """An incomplete scan proves nothing, so it must not report PASS."""
    _write(home / SEAM, "def broken(:\n")
    _blue(_run(home), why_contains="the scan is incomplete")
