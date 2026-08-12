"""Registry: ordering, parallelism, failure policy only (§6)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

VALID_ON_FAIL = ("continue", "halt")


class RegistryError(Exception):
    """Registry is absent, unparseable, or structurally invalid."""


@dataclasses.dataclass(frozen=True)
class Block:
    """One ordered unit: a single check or a parallel group."""

    name: str
    checks: tuple[str, ...]
    parallel: bool = False
    on_fail: str = "continue"


def _parse_block(raw: Any, index: int) -> Block:
    """Validate one block entry."""
    if not isinstance(raw, dict):
        raise RegistryError(f"block {index}: not an object")
    name = str(raw.get("name", f"block-{index}"))
    checks = raw.get("checks", [])
    if not isinstance(checks, list):
        raise RegistryError(f"block {name!r}: checks must be a list")
    if not checks:
        raise RegistryError(f"block {name!r}: empty — a block must list checks")
    on_fail = raw.get("on_fail", "continue")
    if on_fail not in VALID_ON_FAIL:
        raise RegistryError(
            f"block {name!r}: on_fail {on_fail!r} not in {VALID_ON_FAIL}"
        )
    return Block(
        name=name,
        checks=tuple(checks),
        parallel=bool(raw.get("parallel", False)),
        on_fail=on_fail,
    )


def _reject_duplicates(blocks: tuple[Block, ...]) -> None:
    """A check listed twice would run and report twice."""
    seen: set[str] = set()
    for block in blocks:
        for check in block.checks:
            if check in seen:
                raise RegistryError(f"{check!r} listed in more than one block")
            seen.add(check)


def load_registry(path: Path) -> tuple[Block, ...]:
    """Load and validate the registry, preserving declared block order."""
    if not path.is_file():
        raise RegistryError(f"registry not found: {path}")
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RegistryError(f"cannot read {path}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RegistryError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RegistryError(
            f"{path}: top-level JSON must be an object, got {type(payload).__name__}"
        )
    raw_blocks = payload.get("blocks", [])
    if not raw_blocks:
        raise RegistryError(f"{path}: no blocks declared")
    blocks = tuple(_parse_block(raw, index) for index, raw in enumerate(raw_blocks))
    _reject_duplicates(blocks)
    return blocks
