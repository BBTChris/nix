"""Crucible calendar GENERATOR test suite.

Unlike test_crucible_calendar.py, this file legitimately imports the
generator and therefore needs `pandas_market_calendars` installed (a
build/dev dependency, see scripts/crucible/generator-requirements.txt) --
that is expected and is exactly the two-layer split the arc requires.
Exercises Success #2 (determinism), #7 (reconciliation gate), #8 (provenance).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json

import pytest  # pylint: disable=import-error

pytest.importorskip(
    "pandas_market_calendars",
    reason="generator dependency -- see scripts/crucible/generator-requirements.txt",
)

from crucible import calendar_gen as gen  # pylint: disable=wrong-import-position


def test_generate_is_deterministic_across_two_calls():
    """Two independent generate() calls produce byte-identical row sets."""
    first = gen.generate()
    second = gen.generate()
    assert first["sessions"] == second["sessions"]
    assert first["reconciliation"] == second["reconciliation"]


def test_generate_output_is_sorted():
    """Both row sets are pre-sorted by their natural key -- required for
    the determinism/hash-stability guarantee."""
    data = gen.generate()
    session_keys = [(r["product_group"], r["date"]) for r in data["sessions"]]
    assert session_keys == sorted(session_keys)
    recon_keys = [
        (r["product_group"], r["date"], r["event_type"]) for r in data["reconciliation"]
    ]
    assert recon_keys == sorted(recon_keys)


def test_every_reconciliation_row_has_a_valid_source():
    """Reconciliation gate (Success #7): no row is ever left unclassified."""
    data = gen.generate()
    for row in data["reconciliation"]:
        assert row["source"] in ("LIBRARY", "CME-VERIFIED", "MANUAL"), row


def test_pre2010_non_equity_rows_flagged_high_risk_unless_verified():
    """Every pre-2010 non-equity row is HIGH-RISK unless individually
    upgraded to CME-VERIFIED, and a verified row never still reads high-risk."""
    data = gen.generate()
    for row in data["reconciliation"]:
        year = int(row["date"][:4])
        if row["product_group"] != "equity_index" and year < 2010:
            if row["source"] == "CME-VERIFIED":
                assert row["high_risk"] == "0", (
                    "verified rows must not still read high-risk"
                )
            else:
                assert row["high_risk"] == "1", row


def test_equity_index_never_flagged_high_risk():
    """Equity index has no pre-2010 coverage risk by definition (locked span
    starts 2008, and the library's equity coverage is the deepest)."""
    data = gen.generate()
    for row in data["reconciliation"]:
        if row["product_group"] == "equity_index":
            assert row["high_risk"] == "0"


def test_cme_verified_overrides_present_with_citation():
    """The real, cited 2008 NYMEX override rows are present and non-empty."""
    data = gen.generate()
    verified = {
        (r["product_group"], r["date"]): r
        for r in data["reconciliation"]
        if r["source"] == "CME-VERIFIED"
    }
    assert ("energy", "2008-01-01") in verified
    assert verified[("energy", "2008-01-01")]["notes"], (
        "CME-VERIFIED row must carry a citation"
    )


def test_no_early_close_row_has_close_after_static_rth_and_before_eth_close():
    """Regression guard for the inverted-window bug found and fixed this
    arc: an early-close day's rth_close must never exceed eth_close."""
    data = gen.generate()
    for row in data["sessions"]:
        assert row["rth_open_utc"] <= row["rth_close_utc"] <= row["eth_close_utc"]
        assert row["eth_open_utc"] <= row["eth_close_utc"]


def test_committed_artifact_hash_matches_provenance_stamp():
    """Success #8 PROOF: a downstream stamp can resolve to exact calendar
    bytes. Reads the actually-committed files on disk (not a fresh
    regeneration) so this catches a hand-edited or stale artifact."""
    sessions_bytes = gen.SESSIONS_FILE.read_bytes()
    reconciliation_bytes = gen.RECONCILIATION_FILE.read_bytes()
    recomputed = hashlib.sha256(sessions_bytes + reconciliation_bytes).hexdigest()
    provenance = json.loads(gen.PROVENANCE_FILE.read_text())
    assert provenance["content_hash_sha256"] == recomputed
    assert provenance["content_hash_excludes"] == ["generated_utc"]
    assert provenance["generator_library"] == "pandas_market_calendars"
    assert provenance["span"] == {"start": gen.SPAN_START, "end": gen.SPAN_END}


def test_regenerating_does_not_change_the_committed_hash():
    """The artifact committed to the repo must be reproducible from the
    pinned generator inputs -- regenerating in-process must match what's on
    disk byte-for-byte (content hash), proving the committed file wasn't
    hand-edited after generation."""
    provenance = json.loads(gen.PROVENANCE_FILE.read_text())
    data = gen.generate()
    # Recompute via the real writer path for byte-fidelity rather than
    # hand-building CSV text here.
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=gen.SESSION_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(data["sessions"])
    regenerated_sessions_bytes = buf.getvalue().encode()

    buf2 = io.StringIO()
    writer2 = csv.DictWriter(
        buf2, fieldnames=gen.RECONCILIATION_FIELDS, lineterminator="\n"
    )
    writer2.writeheader()
    writer2.writerows(data["reconciliation"])
    regenerated_reconciliation_bytes = buf2.getvalue().encode()

    recomputed = hashlib.sha256(
        regenerated_sessions_bytes + regenerated_reconciliation_bytes
    ).hexdigest()
    assert recomputed == provenance["content_hash_sha256"]
