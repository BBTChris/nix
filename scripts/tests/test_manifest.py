"""Manifest parsing per VERIFY-AND-CHECKS.md §6."""

import json
from pathlib import Path

import pytest  # pylint: disable=import-error
from nixverify.manifest import ManifestError, load_manifest


def _write(tmp_path: Path, payload: dict) -> Path:
    """Write a JSON manifest file to a temporary path and return its path."""
    path = tmp_path / "verify_manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_loads_blocks_in_declared_order(tmp_path: Path) -> None:
    """Test that manifest loads blocks preserving declared order."""
    path = _write(
        tmp_path,
        {
            "manifest_version": "1.0.0",
            "blocks": [
                {"name": "floor", "on_fail": "halt", "checks": ["check_a"]},
                {"name": "rest", "parallel": True, "checks": ["check_b", "check_c"]},
            ],
        },
    )
    blocks = load_manifest(path)
    assert [b.name for b in blocks] == ["floor", "rest"]
    assert blocks[0].on_fail == "halt"
    assert blocks[0].parallel is False
    assert blocks[1].parallel is True
    assert blocks[1].checks == ("check_b", "check_c")


def test_on_fail_defaults_to_continue(tmp_path: Path) -> None:
    """§6: default continue, so one failure does not blind the operator."""
    path = _write(
        tmp_path,
        {"manifest_version": "1.0.0", "blocks": [{"name": "b", "checks": ["check_a"]}]},
    )
    assert load_manifest(path)[0].on_fail == "continue"


def test_missing_file_raises(tmp_path: Path) -> None:
    """Test that missing manifest file raises ManifestError."""
    with pytest.raises(ManifestError, match="not found"):
        load_manifest(tmp_path / "absent.json")


def test_malformed_json_raises(tmp_path: Path) -> None:
    """Test that malformed JSON raises ManifestError."""
    path = tmp_path / "verify_manifest.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ManifestError, match="invalid JSON"):
        load_manifest(path)


def test_duplicate_check_across_blocks_raises(tmp_path: Path) -> None:
    """A check listed twice would run twice and report twice — reject it."""
    path = _write(
        tmp_path,
        {
            "manifest_version": "1.0.0",
            "blocks": [
                {"name": "one", "checks": ["check_a"]},
                {"name": "two", "checks": ["check_a"]},
            ],
        },
    )
    with pytest.raises(ManifestError, match="check_a"):
        load_manifest(path)


def test_block_without_checks_raises(tmp_path: Path) -> None:
    """Test that a block without checks raises ManifestError."""
    path = _write(
        tmp_path, {"manifest_version": "1.0.0", "blocks": [{"name": "empty"}]}
    )
    with pytest.raises(ManifestError, match="empty"):
        load_manifest(path)


def test_bad_on_fail_value_raises(tmp_path: Path) -> None:
    """Test that invalid on_fail value raises ManifestError."""
    path = _write(
        tmp_path,
        {
            "manifest_version": "1.0.0",
            "blocks": [{"name": "b", "on_fail": "explode", "checks": ["check_a"]}],
        },
    )
    with pytest.raises(ManifestError, match="on_fail"):
        load_manifest(path)


def test_non_dict_json_array_raises(tmp_path: Path) -> None:
    """Test that JSON array at top level raises ManifestError."""
    path = tmp_path / "verify_manifest.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ManifestError, match="object"):
        load_manifest(path)


def test_non_dict_json_null_raises(tmp_path: Path) -> None:
    """Test that JSON null at top level raises ManifestError."""
    path = tmp_path / "verify_manifest.json"
    path.write_text("null", encoding="utf-8")
    with pytest.raises(ManifestError, match="object"):
        load_manifest(path)


def test_checks_not_list_raises(tmp_path: Path) -> None:
    """Test that checks field as string (not list) raises ManifestError."""
    path = _write(
        tmp_path,
        {
            "manifest_version": "1.0.0",
            "blocks": [{"name": "b", "checks": "abc"}],
        },
    )
    with pytest.raises(ManifestError, match="list"):
        load_manifest(path)
