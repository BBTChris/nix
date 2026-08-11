"""Derive the execution plan from the checks FOLDER (ARC 024 §3.4, §3.5).

`verify.py --optimize` reads `checks/` — not the registry — and derives an
ordered block plan from each check's declarations. Deriving from the folder is
the structural point, not an implementation convenience: this project has now
been bitten four times by a tracking state silently setting a gate's scope
(bandit scanning nothing, pre-commit skipping untracked files, `--all-files`
missing untracked, D2.24's ignore spellings). A registry that enumerates its own
scope cannot report an orphan, because an orphan is precisely a file the
registry does not know about.

## The block model (§3.1)

Blocks are emitted **least-dependent to most-dependent**. Each block is one
level of the dependency graph: everything at level *n* depends only on things at
levels < *n*. A level with one member is a sequential block; a level with several
is a candidate parallel block.

## "By definition no dependency" is a claim, and it is checked (§3.2)

The operator ruling says members of a multi-check block have no dependency on one
another **by definition**. That is true of *ordering* dependencies — they are at
the same level, so neither waits on the other — and it is NOT true of *resource*
contention, which the graph cannot see. Two checks with no ordering relation can
still both want port 4002.

**The hazard is live on this tree, not hypothetical.** `check_ibgateway_config`
and `check_ibgateway_service` sit in the same registry block today; the service
gate *imports the config gate's handshake* and both dial `127.0.0.1:4002`. clientId
**1** (Risk Engine), **2** (datafeed) and **905** (diagnostics) are distinct
precisely because IBKR sessions collide. A block promoted to parallel on the
strength of "by definition" would produce an intermittent failure that reads as a
network problem.

So a level is emitted `parallel: true` **only** when every member has declared
its resource claims and those claims are pairwise disjoint. Otherwise the level
is emitted as sequential blocks, and the reason is reported.

## The bound on what this can prove — stated, not buried

Disjointness is checked over **declarations**. Two checks that both dial port
4002 and both declare `RESOURCES = ()` will pass this check and collide at
runtime. No static mechanism can close that gap, and this module does not
pretend to: it makes the *undeclared* case loud (a check with no `RESOURCES` is
ineligible for a parallel block, never quietly assumed empty), and the
declaration-vs-reality gap is recorded as a debt rather than papered over. A
false declaration is the residual, and it is named.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from nixverify.declarations import Declaration, read_all
from nixverify.manifest import Block


class OptimizeError(Exception):
    """The plan could not be derived. Always names the participating checks."""


@dataclasses.dataclass(frozen=True)
class Plan:
    """A derived execution plan plus everything that was wrong with it."""

    blocks: tuple[Block, ...]
    errors: tuple[str, ...]
    notes: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """True when the plan is installable."""
        return not self.errors


def _levels(
    declarations: dict[str, Declaration],
) -> tuple[list[list[str]], list[str]]:
    """Kahn topological sort into dependency levels, with cycle detection.

    Returns (levels, errors). A cycle is an ERROR NAMING THE PARTICIPANTS and
    never a silently chosen order — §3.5. The checks left unplaced when the sort
    stalls are exactly the cycle's members plus anything downstream of it, so
    they are reported together rather than guessed apart.
    """
    errors: list[str] = []
    names = set(declarations)
    remaining = {name: set(decl.depends_on) for name, decl in declarations.items()}

    # A dependency on something that does not exist is its own loud error.
    for name, deps in remaining.items():
        for dep in sorted(deps - names):
            errors.append(
                f"{name}: declares a dependency on {dep!r}, which is not a check "
                f"in this folder"
            )
    remaining = {name: deps & names for name, deps in remaining.items()}

    levels: list[list[str]] = []
    placed: set[str] = set()
    while remaining:
        ready = sorted(name for name, deps in remaining.items() if not deps - placed)
        if not ready:
            stuck = sorted(remaining)
            errors.append(
                "dependency CYCLE — no check in this set can run first: "
                + ", ".join(
                    f"{name} -> [{', '.join(sorted(remaining[name] - placed))}]"
                    for name in stuck
                )
            )
            break
        levels.append(ready)
        placed.update(ready)
        for name in ready:
            remaining.pop(name)
    return levels, errors


def _disjointness(
    members: list[str], declarations: dict[str, Declaration]
) -> tuple[bool, list[str]]:
    """May these checks share a parallel block? Returns (ok, reasons-if-not)."""
    reasons: list[str] = []
    for name in members:
        if not declarations[name].declares_resources:
            reasons.append(
                f"{name} declares no RESOURCES, so its claims are unknown — an "
                "undeclared check is never assumed to claim nothing (§3.3)"
            )
    if reasons:
        return False, reasons
    for i, left in enumerate(members):
        for right in members[i + 1 :]:
            shared = set(declarations[left].resources) & set(
                declarations[right].resources
            )
            if shared:
                reasons.append(
                    f"{left} and {right} both claim {sorted(shared)} — not disjoint"
                )
    return not reasons, reasons


def derive_plan(  # pylint: disable=too-many-locals
    checks_dir: Path, registry_path: Path
) -> Plan:
    """Derive the plan from the folder and validate it against §3.5's four rules."""
    declarations = read_all(checks_dir)
    errors: list[str] = []
    notes: list[str] = []

    if not declarations:
        raise OptimizeError(f"no check_*.py found under {checks_dir}")

    # -- Rule: unreadable declaration. Loud, never a silent default. ---------
    for name in sorted(declarations):
        errors.extend(declarations[name].errors)

    # -- Rule: undeclared dependency. ---------------------------------------
    undeclared = [
        name
        for name in sorted(declarations)
        if "DEPENDS_ON" not in declarations[name].declared
    ]
    for name in undeclared:
        errors.append(
            f"{name}: declares no DEPENDS_ON. Every check declares its dependency "
            "to verify.py (operator ruling 6); a check that declares nothing "
            "cannot be placed."
        )

    # -- Rule: orphans, in BOTH directions. ---------------------------------
    # The folder is the scope, so a registry entry with no file is as much a
    # defect as a file with no registry entry — and only the folder-derived
    # direction can see the second one.
    registered: set[str] = set()
    if registry_path.is_file():
        try:
            payload = json.loads(registry_path.read_text(encoding="utf-8"))
            registered = {
                check
                for block in payload.get("blocks", [])
                for check in block.get("checks", [])
            }
        except (OSError, json.JSONDecodeError, AttributeError, TypeError) as exc:
            errors.append(f"{registry_path.name}: unreadable for orphan check: {exc!r}")
    for orphan in sorted(set(declarations) - registered):
        errors.append(
            f"{orphan}: present in {checks_dir.name}/ but absent from "
            f"{registry_path.name} — an ORPHAN check never runs and nothing says so"
        )
    for ghost in sorted(registered - set(declarations)):
        errors.append(
            f"{ghost}: listed in {registry_path.name} with no file in "
            f"{checks_dir.name}/"
        )

    # -- Order: least-dependent to most-dependent, cycles named. ------------
    levels, level_errors = _levels(declarations)
    errors.extend(level_errors)

    blocks: list[Block] = []
    for index, members in enumerate(levels):
        if len(members) == 1:
            blocks.append(Block(name=f"level-{index}", checks=(members[0],)))
            continue
        ok, reasons = _disjointness(members, declarations)
        if ok:
            blocks.append(
                Block(name=f"level-{index}", checks=tuple(members), parallel=True)
            )
        else:
            # NOT an error: a level that cannot go parallel is still perfectly
            # runnable sequentially, and refusing to emit a plan over it would
            # make the safe outcome the unavailable one. It IS reported.
            notes.extend(
                f"level-{index} runs SEQUENTIALLY rather than parallel: {reason}"
                for reason in reasons
            )
            blocks.append(
                Block(name=f"level-{index}", checks=tuple(members), parallel=False)
            )
    return Plan(blocks=tuple(blocks), errors=tuple(errors), notes=tuple(notes))


def plan_to_payload(plan: Plan, declarations: dict[str, Declaration]) -> dict:
    """Render a Plan as a registry.json-shaped payload."""
    return {
        "manifest_version": "1.0.0",
        "comment": (
            "DERIVED by `verify.py --optimize` (ARC 024 §3.4) from the checks "
            "folder, not hand-maintained. Blocks are dependency levels, ordered "
            "least-dependent to most-dependent. A block is `parallel` only where "
            "every member declared its RESOURCES and those claims are pairwise "
            "disjoint (§3.2) — 'by definition no dependency' is checked, not "
            "taken. Re-derive rather than editing this file by hand."
        ),
        "blocks": [
            {
                "name": block.name,
                "parallel": block.parallel,
                "on_fail": block.on_fail,
                "checks": list(block.checks),
                "claims": sorted(
                    {
                        resource
                        for check in block.checks
                        for resource in declarations[check].resources
                    }
                ),
            }
            for block in plan.blocks
        ],
    }
