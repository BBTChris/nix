"""ONE `RankingReader`, and it keeps the half that was worth keeping.

ARC 037 / sub-agent F. CHECK-DEBT D3.271 (the duplicate class) and D3.240 (the
sub-millisecond `drain` that never polls).

## WHAT WAS COLLAPSED AND WHY A RENAME WAS REFUSED

ARC 036 ran five sub-agents in parallel worktrees that could not see each other,
and two of them invented a class called `RankingReader` — sub-agent B's in
`scripts/nixscore/publisher.py`, sub-agent C's in `scripts/nixscore/process.py`.
Two independent classes wrapping a `StateSubscriber` and the frozen
`RankingMirror`: the duplicate instrument doctrine C.9 forbids, on its own.

**The measured consequence was worse.** `check_uncalled_entry_points` resolves a
call site by ATTRIBUTE NAME (D3.234) and the two shared `arbitrate`, `close` and
`pump`. MEASURED on the pre-collapse tree: renaming `process.RankingReader.pump`
to a unique name made `scripts/nixscore/publisher.py::RankingReader.pump` appear
as a NEW `gate_only` finding — 229 findings became 230. That symbol had no
shipped caller for the whole of ARC 036 and the sweep said it did, because
`scripts/scoring_kill_drill.py`'s legitimate call to the OTHER class was being
credited to it.

Renaming one class would have repaired the MEASUREMENT and left the duplication,
so they were collapsed instead. **`publisher.RankingReader` survives** (it is the
richer one: sequence-gap accounting, the torn-free `RankingView`, and it can own
its subscriber) and it **took over sub-agent C's direct-poll `pump`**, because
the one thing the other class did better was not calling `StateSubscriber.drain`.

## §0a — WHAT WOULD HAVE TO BE TRUE FOR THIS FILE TO PASS WHILE MEASURING NOTHING?

1. **The structural assertions could scan a package that is not there**, and
   "zero duplicate classes" would be trivially true of an empty directory.
   *Closed:* `test_the_package_scan_can_see_a_duplicate` PLANTS a second class
   in a copy of the package and requires the scan to find two — the same scan,
   on the same inputs, proving it discriminates before its silence is read.
2. **The `drain` ban could be asserted against a docstring** rather than against
   the code, so a `pump` that called `drain` under a comment saying it does not
   would pass. *Closed:* the assertion is over the AST of the `pump` FunctionDef,
   and the plant re-inserts a real `self._subscriber.drain(...)` call.
3. **The sub-millisecond property could be asserted with a generous budget**, in
   which case both implementations pass and the test proves nothing about the
   defect it names. *Closed:* the drive uses a 1 ms budget — the exact figure at
   which `int((deadline - now) * 1000)` truncates to zero — and a CONTROL in the
   same test drives `StateSubscriber.drain(1)` against the same live socket and
   requires it to return NOTHING. The two halves together are the measurement;
   either alone is an assertion.
"""
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code
# pylint: disable=missing-function-docstring,use-implicit-booleaness-not-comparison

from __future__ import annotations

import ast
import shutil
import sys
import time
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parents[2]
for _extra in (str(REPO / "checks"), str(REPO / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

# pylint: disable=wrong-import-position
import scoring_kill_drill as drill  # pylint: disable=import-error
from nixbus.statebus import StateSubscriber  # pylint: disable=import-error
from nixscore import process as proc  # pylint: disable=import-error
from nixscore import publisher as pub  # pylint: disable=import-error
from nixscore import seam  # pylint: disable=import-error

PACKAGE = REPO / "scripts" / "nixscore"
READER = "RankingReader"

FIRST = ("alpha", "ES")
SECOND = ("bravo", "ES")


def _reader_definitions(package: Path) -> list[str]:
    """Every module in `package` defining a class called `RankingReader`."""
    found: list[str] = []
    for path in sorted(package.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == READER:
                found.append(path.name)
    return found


def _rows(generation: int = 3) -> dict:
    return {
        FIRST: seam.RankRow(FIRST[0], FIRST[1], 900.0, 1, generation),
        SECOND: seam.RankRow(SECOND[0], SECOND[1], 100.0, 2, generation),
    }


# ---------------------------------------------------------------------------
# D3.271 — ONE class, and the scan that says so can see two
# ---------------------------------------------------------------------------


def test_exactly_ONE_RankingReader_exists_in_the_package() -> None:
    """The property D3.271 records, asserted where it can be re-checked forever."""
    found = _reader_definitions(PACKAGE)
    assert found == ["publisher.py"], (
        f"{len(found)} classes named {READER} in scripts/nixscore/ ({found}). "
        "Two of them is the state ARC 036 shipped, and it makes "
        "check_uncalled_entry_points credit one's call sites to the other"
    )


def test_the_package_scan_can_see_a_duplicate(tmp_path: Path) -> None:
    """CAN-FAIL for the assertion above — silence is only worth what a plant proves."""
    staged = tmp_path / "nixscore"
    shutil.copytree(PACKAGE, staged, ignore=shutil.ignore_patterns("__pycache__"))
    assert _reader_definitions(staged) == ["publisher.py"]
    (staged / "process.py").write_text(
        (staged / "process.py").read_text(encoding="utf-8")
        + f"\n\nclass {READER}:  # planted duplicate\n    pass\n",
        encoding="utf-8",
    )
    assert sorted(_reader_definitions(staged)) == ["process.py", "publisher.py"], (
        "the scan cannot see a second class of the same name, so its silence on "
        "the real package proves nothing"
    )


def test_the_process_module_no_longer_defines_a_reader() -> None:
    """The collapse removed it; a re-export would keep two names for one class."""
    assert not hasattr(proc, READER)
    source = (PACKAGE / "process.py").read_text(encoding="utf-8")
    assert "D3.271" in source, (
        "the signpost where the class stood is how the next reader learns the "
        "class moved instead of vanishing"
    )


def test_the_kill_drill_drives_the_SURVIVING_class() -> None:
    """The caller that made the mis-attribution measurable now names the survivor."""
    assert drill.RankingReader is pub.RankingReader


# ---------------------------------------------------------------------------
# D3.240 — the half that was kept, and it is kept for a measured reason
# ---------------------------------------------------------------------------


def test_pump_does_NOT_call_StateSubscriber_drain() -> None:
    """Structural, over the AST — a docstring promising this would be worthless."""
    tree = ast.parse((PACKAGE / "publisher.py").read_text(encoding="utf-8"))
    pumps = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "pump"
    ]
    assert len(pumps) == 1, f"expected one `pump` definition, found {len(pumps)}"
    calls = [
        node.func.attr
        for node in ast.walk(pumps[0])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "drain" not in calls, (
        "`pump` calls `StateSubscriber.drain`, which polls the socket ZERO times "
        "for any budget under 2 ms (D3.240) and reports it as 'nothing arrived'. "
        "That is the shape the collapse existed to keep out"
    )
    assert "poll" in calls, (
        "`pump` no longer polls at all — the direct-poll behaviour is the half of "
        "the collapsed class that was worth keeping"
    )


def test_the_drain_detector_fires_on_a_planted_call() -> None:
    """CAN-FAIL for the structural assertion above."""
    planted = ast.parse(
        "class R:\n"
        "    def pump(self, timeout_ms=0):\n"
        "        return self._subscriber.drain(timeout_ms)\n"
    )
    pump = next(
        node
        for node in ast.walk(planted)
        if isinstance(node, ast.FunctionDef) and node.name == "pump"
    )
    calls = [
        node.func.attr
        for node in ast.walk(pump)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "drain" in calls, "the detector cannot see a `drain` call it was shown"


def test_a_ONE_MILLISECOND_pump_really_polls_and_drain_really_does_not(
    tmp_path: Path,
) -> None:
    """THE MEASUREMENT, over a real `ipc://` socket. Both halves, one run.

    1 ms is the exact budget at which `drain`'s `int((deadline - now) * 1000)`
    truncates to zero. The reader's `pump(1)` must carry the snapshot; a bare
    `StateSubscriber.drain(1)` on an equally-fed socket must carry nothing. The
    control is what makes the first half a measurement rather than a claim: a
    socket that simply had a message ready would satisfy either implementation.
    """
    endpoint = pub.ranking_endpoint(tmp_path)
    writer = pub.RankingWriter(endpoint)
    reader = pub.RankingReader(endpoint, stale_after_s=30.0)
    control = StateSubscriber(endpoint, [seam.RANKING_TOPIC])
    try:
        # Let both SUB sockets finish connecting before anything is published:
        # a message published into an unconnected subscriber is lost by libzmq,
        # and that loss would masquerade as the defect under test.
        time.sleep(0.3)
        writer.publish_rows(_rows(), 10)
        writer.publish_rows(_rows(4), 10)
        time.sleep(0.3)

        carried = reader.pump(1)
        assert carried.received >= 1, (
            f"a 1 ms pump carried {carried.received} message(s) off a socket "
            "holding two — this is D3.240 back on the consumer path, and it "
            "presents as a stale mirror rather than as an error"
        )
        assert carried.accepted >= 1
        assert reader.view() is not None
        assert str(reader.arbitrate(FIRST, SECOND).outcome) == "ranked"

        assert control.drain(1) == [], (
            "`StateSubscriber.drain(1)` returned messages — D3.240 has been "
            "repaired upstream, which is good news and means this control no "
            "longer discriminates. Re-point it (or discharge D3.240) rather "
            "than deleting it"
        )
    finally:
        control.close()
        reader.close()
        writer.close()


# ---------------------------------------------------------------------------
# The two ways in, and what `close` owns
# ---------------------------------------------------------------------------


def test_a_reader_built_from_an_ENDPOINT_owns_its_subscriber(tmp_path: Path) -> None:
    endpoint = pub.ranking_endpoint(tmp_path)
    writer = pub.RankingWriter(endpoint)
    reader = pub.RankingReader(endpoint, stale_after_s=30.0)
    try:
        assert reader.endpoint == endpoint
        time.sleep(0.3)
        writer.publish_rows(_rows(), 10)
        time.sleep(0.3)
        assert reader.pump(50).accepted == 1
        assert reader.applied == 1
    finally:
        reader.close()
        writer.close()


def test_a_reader_built_from_a_SUBSCRIBER_adopts_it(tmp_path: Path) -> None:
    """The kill drill's shape: a consumer that already owns its socket."""
    endpoint = pub.ranking_endpoint(tmp_path)
    writer = pub.RankingWriter(endpoint)
    subscriber = StateSubscriber(endpoint, [seam.RANKING_TOPIC])
    reader = pub.RankingReader(subscriber, stale_after_s=30.0)
    try:
        assert reader.endpoint == endpoint
        time.sleep(0.3)
        writer.publish_rows(_rows(), 10)
        time.sleep(0.3)
        assert reader.pump(50).accepted == 1
        assert reader.bytes_received > 0
    finally:
        reader.close()
        writer.close()


def test_close_releases_the_socket_whichever_way_it_came_in(tmp_path: Path) -> None:
    """A reader that half-owned its transport would be a leak wearing a contract."""
    endpoint = pub.ranking_endpoint(tmp_path)
    subscriber = StateSubscriber(endpoint, [seam.RANKING_TOPIC])
    reader = pub.RankingReader(subscriber, stale_after_s=30.0)
    reader.close()
    with pytest.raises(Exception):  # noqa: B017  pylint: disable=broad-exception-caught
        subscriber.poll(0)
