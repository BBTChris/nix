"""Registry parsing per nix_check_contract.md §6."""

import json
import os
from pathlib import Path

import pytest  # pylint: disable=import-error
from nixverify.registry import RegistryError, load_registry


def _write(tmp_path: Path, payload: dict) -> Path:
    """Write a JSON registry file to a temporary path and return its path."""
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_loads_blocks_in_declared_order(tmp_path: Path) -> None:
    """Test that registry loads blocks preserving declared order."""
    path = _write(
        tmp_path,
        {
            "registry_version": "1.0.0",
            "blocks": [
                {"name": "floor", "on_fail": "halt", "checks": ["check_a"]},
                {"name": "rest", "parallel": True, "checks": ["check_b", "check_c"]},
            ],
        },
    )
    blocks = load_registry(path)
    assert [b.name for b in blocks] == ["floor", "rest"]
    assert blocks[0].on_fail == "halt"
    assert blocks[0].parallel is False
    assert blocks[1].parallel is True
    assert blocks[1].checks == ("check_b", "check_c")


def test_on_fail_defaults_to_continue(tmp_path: Path) -> None:
    """§6: default continue, so one failure does not blind the operator."""
    path = _write(
        tmp_path,
        {"registry_version": "1.0.0", "blocks": [{"name": "b", "checks": ["check_a"]}]},
    )
    assert load_registry(path)[0].on_fail == "continue"


def test_missing_file_raises(tmp_path: Path) -> None:
    """Test that missing registry file raises RegistryError."""
    with pytest.raises(RegistryError, match="not found"):
        load_registry(tmp_path / "absent.json")


def test_malformed_json_raises(tmp_path: Path) -> None:
    """Test that malformed JSON raises RegistryError."""
    path = tmp_path / "registry.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(RegistryError, match="invalid JSON"):
        load_registry(path)


def test_duplicate_check_across_blocks_raises(tmp_path: Path) -> None:
    """A check listed twice would run twice and report twice — reject it."""
    path = _write(
        tmp_path,
        {
            "registry_version": "1.0.0",
            "blocks": [
                {"name": "one", "checks": ["check_a"]},
                {"name": "two", "checks": ["check_a"]},
            ],
        },
    )
    with pytest.raises(RegistryError, match="check_a"):
        load_registry(path)


def test_block_without_checks_raises(tmp_path: Path) -> None:
    """Test that a block without checks raises RegistryError."""
    path = _write(
        tmp_path, {"registry_version": "1.0.0", "blocks": [{"name": "empty"}]}
    )
    with pytest.raises(RegistryError, match="empty"):
        load_registry(path)


def test_bad_on_fail_value_raises(tmp_path: Path) -> None:
    """Test that invalid on_fail value raises RegistryError."""
    path = _write(
        tmp_path,
        {
            "registry_version": "1.0.0",
            "blocks": [{"name": "b", "on_fail": "explode", "checks": ["check_a"]}],
        },
    )
    with pytest.raises(RegistryError, match="on_fail"):
        load_registry(path)


def test_non_dict_json_array_raises(tmp_path: Path) -> None:
    """Test that JSON array at top level raises RegistryError."""
    path = tmp_path / "registry.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(RegistryError, match="object"):
        load_registry(path)


def test_non_dict_json_null_raises(tmp_path: Path) -> None:
    """Test that JSON null at top level raises RegistryError."""
    path = tmp_path / "registry.json"
    path.write_text("null", encoding="utf-8")
    with pytest.raises(RegistryError, match="object"):
        load_registry(path)


def test_checks_not_list_raises(tmp_path: Path) -> None:
    """Test that checks field as string (not list) raises RegistryError."""
    path = _write(
        tmp_path,
        {
            "registry_version": "1.0.0",
            "blocks": [{"name": "b", "checks": "abc"}],
        },
    )
    with pytest.raises(RegistryError, match="list"):
        load_registry(path)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permission bits")
def test_unreadable_file_raises_registry_error_not_oserror(tmp_path: Path) -> None:
    """A permission-denied registry is unmeasurable (§4.1), not a crash."""
    path = _write(
        tmp_path,
        {"registry_version": "1.0.0", "blocks": [{"name": "b", "checks": ["check_a"]}]},
    )
    path.chmod(0o000)
    try:
        with pytest.raises(RegistryError, match="cannot read"):
            load_registry(path)
    finally:
        path.chmod(0o644)


def test_directory_in_place_of_file_raises_registry_error(tmp_path: Path) -> None:
    """A directory where a registry file is expected is unmeasurable, not a crash."""
    path = tmp_path / "registry.json"
    path.mkdir()
    with pytest.raises(RegistryError):
        load_registry(path)


def test_undecodable_bytes_raise_registry_error_not_unicodedecodeerror(
    tmp_path: Path,
) -> None:
    """Truncated or wrong-encoding bytes are unmeasurable (§4.1), not a crash."""
    path = tmp_path / "registry.json"
    path.write_bytes(b'{"a": "\xff\xfe"}')
    with pytest.raises(RegistryError, match="cannot read"):
        load_registry(path)
