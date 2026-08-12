#!/usr/bin/env python3
"""Detect resource claims whose ATTRIBUTION moves when the plan is reordered.

ARC 027 / D1. Generalises ARC 026's `.pyc` finding from a site into a class.

## The finding this generalises

ARC 026 Stage 2.2: `check_capture_plane2` was reported FAILing for
`file-write:.../nixbus/__pycache__/*.pyc` against `RESOURCES = ("journal",)`.
The declaration was honest and the observation was real; **the attribution was
wrong.** A `.pyc` write is the interpreter caching a module. The cache is on
disk and shared, so the write is charged to whichever check imports the module
first on a cold tree — three sibling gates read clean purely because
`check_capture_plane2` was scheduled ahead of them and paid for all four. It was
fixed at the cause (`sys.dont_write_bytecode` in `checks/_preamble.py`).

**The rule:** *a resource claim that moves between checks when the plan is
reordered is an artefact of the instrument, not a property of the check.*

`check_observed_resource_claims` cannot see this class. It sweeps
`sorted(declarations)` — ONE fixed order, every run — so a claim that would land
on a different check under a different order lands on the same check every time
and reads as a stable, honest property of that check. This module is the second
order.

## Every order is run TWICE, and that is not belt-and-braces

The obvious detector runs the plan in two orders and diffs. **Measured on this
tree, that detector reports 12 findings out of 23 claims and every one of them
is false.** `check_state_bus` claims four paths under a `tempfile.mkdtemp()`
root and `check_verify_logging` claims a `secrets.token_hex(8)` control file:
those claim STRINGS differ between any two runs, in the same order or not.

So each order is swept twice and the pair is the nondeterminism baseline for
that order:

  * a claim's owners under order L are KNOWN only when L's two sweeps agree;
  * a claim is **ORDER-DEPENDENT** when its owners are known under every order
    and differ between two of them;
  * a claim whose owners disagree between two runs of the SAME order is
    **UNSTABLE** — reported in its own class, never folded into the finding and
    never silently dropped.

**Repeating only the reference order is not enough, and that was measured, not
reasoned.** The first version of this module ran A, A', B. A claim appearing
only in B then scored against an empty-but-"agreeing" A/A' baseline and was
reported as drift — `∅ == ∅` is not a stable attribution, it is the reference
order never having seen the claim. The lazy-import control produced exactly that
false positive on its first run. Sweeping every order twice removes the
asymmetry rather than special-casing it.

## Normalisation, and why the baseline alone will not do

The baseline classifies a volatile-named claim as unstable and excludes it. That
is correct for `/tmp/<random>` — and it would have MISSED THE MOTIVATING
DEFECT. `importlib` writes bytecode atomically as `<name>.pyc.<id(path)>` and
renames; the integer is per-process, so ARC 026's own claim is volatile-named
*and* order-dependent, and the baseline alone masks it.

So claims are compared on a NORMALISED key, by a table that is small, closed and
written out in `NORMALISERS` — the same discipline `observe.covers()` keeps, for
the same reason: a permissive rule here turns every finding into a pass. Each
rule names the generator it abstracts. Over-normalisation is not assumed away:
two raw claims from one check collapsing onto one key is COUNTED and reported.
Under-normalisation is loud by construction — the claim stays unstable within
its own order and is reported as such rather than as clean.

The table is `NORMALISERS` and each rule's label is a NAMED CONSTANT
(`PYC_RULE`, `TMPNAME_RULE`, `NONCE_RULE`) so a test can remove exactly one and
measure what is lost. That is not tidiness: the first version of the negative
test filtered the table by substring, matched no rule, removed nothing, and
passed its "rule 1 is load-bearing" measurement against the intact table.

## A HARNESS, not a registered check — and that was decided by measurement

`scripts/tests/independent_claims.py` and `scripts/tests/binding_census.py` are
the harness precedents; `checks/check_observed_resource_claims.py` is the
registered-check precedent. Two measurements chose the harness:

1. **Registration is a plan change, and the plan is not this agent's to write.**
   `optimize.derive_plan` over a copy of `checks/` with one extra file returns
   `plan.ok = False` — *"check_attribution_drift: present in checks/ but absent
   from registry.json — an ORPHAN check never runs and nothing says so"*. A
   registered spelling therefore requires `--optimize --commit`.
2. **A registered spelling would be permanently CANNOT_MEASURE.**
   `check_observed_resource_claims` sweeps every registered check except itself,
   so it would observe this one, whose child would run six further full sweeps —
   twenty child processes each — inside `observe.PER_CHECK_TIMEOUT_S = 60.0`.
   One sweep of this tree measures 11.2s, so `--orders 3` is 67.2s > 60.0s
   before the nesting is counted. The gate built to measure resource claims
   would report nothing about the gate built to measure their attribution.

So this runs from its own CLI and from `test_attribution_drift.py`, and the
registration question is handed up rather than answered here.

## What "a legal order" means here — checked, not assumed

`optimize._levels` emits dependency levels and orders each level with
`sorted(ready)`. That alphabetical order is a tiebreak, not a constraint:
members of one block are at the same dependency level, so none of them may
depend on another. This module PERMUTES WITHIN A BLOCK ONLY, keeps blocks in
registry order, and asserts the no-intra-block-dependency property from the
declarations before it shuffles anything. A block containing an intra-block
dependency is a refusal, not a shuffle.

## debug.md §7.12 — what would have to be true for this to report clean while
## measuring nothing?

1. **The two orders could be the same order.** A "reordering" detector that
    never reorders finds nothing and looks exactly like one that found nothing
    to find. *Closed:* `detect` compares the produced orders pairwise and a run
    where any two nominally distinct orders are equal is a REFUSAL (exit 2),
    naming both labels.
2. **The cache could be warm.** The class only exists on a cold shared cache;
    on a warm tree the first-runner already paid in a previous process and no
    claim is recorded at all. *Closed:* every sweep is preceded by a cold-state
    reset whose effect is COUNTED (`cleared` per sweep, printed per sweep), and
    a first sweep that cleared nothing is a reported NOTE rather than part of a
    clean sheet. The reset is also a PARAMETER — see the residual below.
3. **The observer could be disarmed.** Zero claims anywhere reads identically to
    a population that touches nothing. *Closed:* fewer than
    `MIN_CREDIBLE_CLAIMS` observed claims across a sweep is a refusal.
4. **The population could be trivial.** Two checks cannot be reordered
    informatively. *Closed:* `MIN_CREDIBLE_CHECKS`, a floor and not today's
    count.
5. **The detector could be incapable of firing at all.** A drift detector that
    has never been seen to fire is a green light. *Closed:* `plant_control()`
    plants two synthetic checks that share an on-disk cache, and
    `self_test()` — reachable from this module's own CLI as `--self-test`, not
    only from pytest — requires the detector to report them. A self-test that
    reports NO drift fails.

## The residual, named

**The detector sees only the caches its cold-state reset knows how to clear.**
Attribution drift through a cache this module does not cold (a `~/.cache`
directory, a database, a systemd unit's state) is invisible to it, and would
read as a stable property of whichever check happens to run first. That is the
same shape as the defect and it is a bound on the instrument, not on the class.
`--cold-extra` exists so a caller can widen it; nothing widens it automatically.

Second residual: a claim that is order-dependent **and** whose normalised key is
still volatile is classed UNSTABLE, not ORDER-DEPENDENT. It is reported, loudly,
in its own section — an unstable claim is an unanswered question, never a pass.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import random
import re
import shutil
import sys
import tempfile
import time
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

# pylint: disable=wrong-import-position
# The `sys.path` bootstrap above must run BEFORE these imports; that is the
# whole point of it, and it is the shape `checks/_preamble.py` uses for every
# check in this tree.
from nixverify.declarations import read_all
from nixverify.observe import observe_check

# pylint: enable=wrong-import-position

#: This gate re-executes every registered check; observing it would nest a full
#: sweep inside every sweep. Excluded for the same reason it excludes itself.
SELF_EXECUTING = ("check_observed_resource_claims",)

#: Floors, not today's counts (doctrine C.4 — never anchor to something that
#: moves). Below either of these the run is a refusal, not a clean sheet.
MIN_CREDIBLE_CHECKS = 5
MIN_CREDIBLE_CLAIMS = 5

#: Per-check observation ceiling. Below `observe.PER_CHECK_TIMEOUT_S`'s default
#: on purpose: three sweeps of the whole population is the unit of work here, so
#: one wedged check must cost seconds and not three minutes.
PER_CHECK_TIMEOUT_S = 45.0


# ---------------------------------------------------------------------------
# NORMALISATION — small, closed, and every rule names the generator it abstracts.
# ---------------------------------------------------------------------------
#
# A rule here may only abstract a token that is REGENERATED PER RUN by a named
# mechanism. Nothing in this table may generalise a path component that a check
# chose; that is the difference between "this claim is the same claim" and "these
# two claims are close enough", and only the first is honest.

_TMPROOT = re.escape(tempfile.gettempdir())

#: Rule labels are NAMED CONSTANTS so a test can remove exactly one rule and
#: measure what is lost. The first version of that test filtered the table by
#: substring, matched nothing, removed no rule, and passed its negative
#: measurement against the full table — a control that silently tested nothing.
PYC_RULE = "importlib atomic bytecode write suffix"
TMPNAME_RULE = "tempfile random name (first segment under the temp root)"
NONCE_RULE = "secrets.token_hex nonce"

NORMALISERS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        # importlib._bootstrap_external._write_atomic: '{}.{}'.format(path, id(path)).
        # MEASURED per-run-unique on this box: four sweeps of one planted module
        # produced .130495059485600 / .130349308486560 / .134660235420576 /
        # .137792692151200. This is EXACTLY ARC 026's claim shape.
        PYC_RULE,
        re.compile(r"(?P<keep>\.pyc)\.\d+$"),
        r"\g<keep>.<NONCE>",
    ),
    (
        # tempfile._RandomNameSequence: exactly 8 chars from [a-z0-9_], appended
        # to the caller's prefix, in the FIRST segment under the temp root only.
        # Anchored to the first segment so `/tmp/<dir>/svc.ipc` keeps `svc.ipc`
        # and two differently-prefixed temp roots stay distinct claims.
        TMPNAME_RULE,
        re.compile(rf"(?P<keep>{_TMPROOT}/[^/]*?)[a-z0-9_]{{8}}(?P<tail>/|$)"),
        r"\g<keep><R8>\g<tail>",
    ),
    (
        # secrets.token_hex(n>=8) nonces, as check_verify_logging's
        # `.plane2_control_ARC024CTL-<hex16>` and check_hook_suite's `ARC024-<hex>`.
        NONCE_RULE,
        re.compile(r"-(?P<hex>[0-9a-f]{16,})(?P<tail>/|$)"),
        r"-<HEX>\g<tail>",
    ),
)


def normalise(claim: str) -> str:
    """Apply every rule in `NORMALISERS`, in order. Total; never raises."""
    out = claim
    for _label, pattern, repl in NORMALISERS:
        out = pattern.sub(repl, out)
    return out


# ---------------------------------------------------------------------------
# ORDERS — permute WITHIN a block, never across blocks.
# ---------------------------------------------------------------------------


class RefusedError(Exception):
    """The run could not be made informative. Always names why."""


def registry_blocks(registry: Path) -> list[list[str]]:
    """The plan's blocks, in plan order, as lists of check names."""
    payload = json.loads(registry.read_text(encoding="utf-8"))
    return [list(block.get("checks", ())) for block in payload.get("blocks", ())]


def assert_permutable(blocks: Sequence[Sequence[str]], checks_dir: Path) -> None:
    """Refuse to shuffle a block whose members constrain each other.

    `optimize._levels` guarantees this by construction — a block is one
    dependency level. It is asserted anyway rather than trusted, because the
    whole legitimacy of reordering rests on it and a hand-edited registry would
    silently take it away.
    """
    declarations = read_all(checks_dir)
    for block in blocks:
        members = set(block)
        for name in block:
            decl = declarations.get(name)
            if decl is None:
                continue
            inside = sorted(set(decl.depends_on) & members)
            if inside:
                raise RefusedError(
                    f"{name} declares DEPENDS_ON {inside}, which share its block — "
                    "the block is not a dependency level and its members may not "
                    "be permuted; reordering it would measure a plan the system "
                    "would never run"
                )


def orders(
    blocks: Sequence[Sequence[str]], exclude: Iterable[str], count: int = 2
) -> list[tuple[str, tuple[str, ...]]]:
    """`count` distinct legal run orders, as (label, order) pairs.

    Order 0 is the plan as written; order 1 reverses each block; further orders
    are seeded shuffles. Seeded, because an order nobody can reproduce turns a
    finding into an anecdote.
    """
    skip = set(exclude)
    kept = [[name for name in block if name not in skip] for block in blocks]
    out: list[tuple[str, tuple[str, ...]]] = [
        ("plan-order", tuple(name for block in kept for name in block))
    ]
    if count > 1:
        out.append(
            ("reversed-within-block", tuple(n for b in kept for n in reversed(b)))
        )
    for seed in range(count - 2):
        rng = random.Random(seed)  # nosec B311 - reproducible ordering, not crypto
        shuffled: list[str] = []
        for block in kept:
            members = list(block)
            rng.shuffle(members)
            shuffled.extend(members)
        out.append((f"shuffled-seed-{seed}", tuple(shuffled)))
    return out[:count]


# ---------------------------------------------------------------------------
# COLD STATE — the parameter that decides what this instrument can see at all.
# ---------------------------------------------------------------------------


def clear_pycache(roots: Iterable[Path]) -> int:
    """Remove every `__pycache__` under `roots`. Returns how many were removed.

    Symlinked directories are never followed and never removed: in a provisioned
    worktree `.venv` and `state/` are symlinks back to the canonical tree, and an
    instrument that deleted through them would damage the thing it measures.
    """
    removed = 0
    for root in roots:
        if not root.is_dir() or root.is_symlink():
            continue
        for path in sorted(root.rglob("__pycache__")):
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
    return removed


def default_cold(home: Path, extra: Sequence[Path] = ()) -> Callable[[], int]:
    """The production cold-state reset: repo-local bytecode caches, plus `extra`."""

    def reset() -> int:
        cleared = clear_pycache([home / "checks", home / "scripts"])
        for path in extra:
            if path.is_symlink() or not path.exists():
                continue
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink()
            cleared += 1
        return cleared

    return reset


# ---------------------------------------------------------------------------
# SWEEPS
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Sweep:
    """One pass over the population in one order, from one cold state.

    Eight fields because eight distinct facts are recorded per sweep, and
    collapsing any pair of them would lose a §7.12 closure: `cleared` is the
    cold-state evidence, `errors` is the unobserved set, and `collapsed` is the
    normalisation's own lossiness.
    """

    # pylint: disable=too-many-instance-attributes

    label: str
    order: tuple[str, ...]
    #: normalised claim -> the checks observed making it.
    owners: dict[str, set[str]]
    #: check -> raw claims, kept so a report can show what was actually seen.
    raw: dict[str, tuple[str, ...]]
    #: check -> (raw claim count, normalised key count). Unequal means this
    #: sweep's normalisation was lossy for that check; counted, never hidden.
    collapsed: dict[str, tuple[int, int]]
    errors: dict[str, str]
    cleared: int
    elapsed_s: float

    @property
    def claim_count(self) -> int:
        """Total raw claims recorded in this sweep."""
        return sum(len(claims) for claims in self.raw.values())


def sweep(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    checks_dir: Path,
    home: Path,
    label: str,
    order: Sequence[str],
    cold: Callable[[], int],
    timeout: float = PER_CHECK_TIMEOUT_S,
) -> Sweep:
    """Cold the shared caches, then observe every check once, in `order`."""
    cleared = cold()
    started = time.perf_counter()
    owners: dict[str, set[str]] = {}
    raw: dict[str, tuple[str, ...]] = {}
    collapsed: dict[str, tuple[int, int]] = {}
    errors: dict[str, str] = {}
    for name in order:
        run = observe_check(checks_dir, name, home, timeout=timeout)
        raw[name] = run.claims
        if run.error:
            errors[name] = run.error
        keys = {normalise(claim) for claim in run.claims}
        collapsed[name] = (len(run.claims), len(keys))
        for key in keys:
            owners.setdefault(key, set()).add(name)
    return Sweep(
        label=label,
        order=tuple(order),
        owners=owners,
        raw=raw,
        collapsed=collapsed,
        errors=errors,
        cleared=cleared,
        elapsed_s=round(time.perf_counter() - started, 2),
    )


@dataclasses.dataclass(frozen=True)
class Drift:
    """One claim whose owners were not the same under two orders."""

    claim: str
    per_order: dict[str, list[str]]

    def render(self) -> str:
        """One human-readable line per order."""
        body = "; ".join(
            f"{label}={owners or ['<nobody>']}"
            for label, owners in sorted(self.per_order.items())
        )
        return f"{self.claim}: {body}"


@dataclasses.dataclass(frozen=True)
class Report:
    """The verdict over every order, each swept twice."""

    #: (first sweep, repeat sweep) per order, in the order they were run.
    pairs: tuple[tuple[Sweep, Sweep], ...]
    #: Owners known under every order and different between two. THE FINDING.
    order_dependent: tuple[Drift, ...]
    #: Owners disagreed between two runs of ONE order. Never counted as drift.
    unstable: tuple[Drift, ...]
    notes: tuple[str, ...]

    @property
    def clean(self) -> bool:
        """True when no claim's attribution moved with the order."""
        return not self.order_dependent

    @property
    def sweeps(self) -> tuple[Sweep, ...]:
        """Every sweep run, flattened."""
        return tuple(one for pair in self.pairs for one in pair)


def _classify(
    key: str, pairs: Sequence[tuple[Sweep, Sweep]]
) -> tuple[str, dict[str, list[str]]]:
    """One claim's verdict: ("unstable" | "order-dependent" | "stable", evidence)."""
    known: dict[str, list[str]] = {}
    disagreed: dict[str, list[str]] = {}
    for first, repeat in pairs:
        left = first.owners.get(key, set())
        right = repeat.owners.get(key, set())
        if left != right:
            disagreed[f"{first.label}#1"] = sorted(left)
            disagreed[f"{first.label}#2"] = sorted(right)
        else:
            known[first.label] = sorted(left)
    if disagreed:
        return "unstable", {**known, **disagreed}
    if len({tuple(owners) for owners in known.values()}) > 1:
        return "order-dependent", known
    return "stable", known


def _notes(pairs: Sequence[tuple[Sweep, Sweep]]) -> list[str]:
    """Everything the verdict does not carry but a reader must not miss."""
    notes: list[str] = []
    for one in (one for pair in pairs for one in pair):
        lossy = {
            name: pair for name, pair in one.collapsed.items() if pair[0] != pair[1]
        }
        if lossy:
            notes.append(
                f"{one.label}: normalisation was LOSSY for "
                + ", ".join(f"{n} ({a} raw -> {b} keys)" for n, (a, b) in lossy.items())
                + " — collapsed claims of one check cannot produce a cross-check "
                "finding, but they can MASK one"
            )
        if one.errors:
            notes.append(
                f"{one.label}: {len(one.errors)} check(s) UNOBSERVED — "
                + "; ".join(f"{n}: {e[:120]}" for n, e in sorted(one.errors.items()))
            )
    if pairs and pairs[0][0].cleared == 0:
        notes.append(
            "the cold-state reset cleared NOTHING before the first sweep — the "
            "tree was already cold or the reset does not reach this tree's caches; "
            "either way a warm cache cannot exhibit this defect class"
        )
    return notes


def compare(pairs: Sequence[tuple[Sweep, Sweep]]) -> Report:
    """Classify every observed claim as ORDER-DEPENDENT, UNSTABLE, or stable.

    `∅ == ∅` is deliberately NOT read as a stable attribution when neither run of
    an order saw the claim — that is the asymmetry the module docstring records
    measuring. A key unknown to one order is unstable, full stop, because the
    only evidence available about it comes from orders that did see it.
    """
    keys = {key for pair in pairs for one in pair for key in one.owners}
    unstable: list[Drift] = []
    order_dependent: list[Drift] = []
    for key in sorted(keys):
        verdict, evidence = _classify(key, pairs)
        if verdict == "unstable":
            unstable.append(Drift(claim=key, per_order=evidence))
        elif verdict == "order-dependent":
            order_dependent.append(Drift(claim=key, per_order=evidence))
    return Report(
        pairs=tuple(pairs),
        order_dependent=tuple(order_dependent),
        unstable=tuple(unstable),
        notes=tuple(_notes(pairs)),
    )


def detect(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    checks_dir: Path,
    home: Path,
    plan: Sequence[Sequence[str]],
    cold: Callable[[], int],
    order_count: int = 2,
    exclude: Iterable[str] = SELF_EXECUTING,
    timeout: float = PER_CHECK_TIMEOUT_S,
) -> Report:
    """The whole instrument: `order_count` legal orders, each swept twice."""
    assert_permutable(plan, checks_dir)
    plan_orders = orders(plan, exclude, count=order_count)
    if len(plan_orders) < 2:
        raise RefusedError("fewer than two orders requested — nothing to compare")
    seen: dict[tuple[str, ...], str] = {}
    for label, order in plan_orders:
        if order in seen:
            raise RefusedError(
                f"orders {seen[order]!r} and {label!r} are THE SAME ORDER — a "
                "reordering detector that does not reorder finds nothing and "
                "reads identically to one that found nothing to find"
            )
        seen[order] = label
    population = len(plan_orders[0][1])
    if population < MIN_CREDIBLE_CHECKS:
        raise RefusedError(
            f"{population} observable check(s), below the credibility floor of "
            f"{MIN_CREDIBLE_CHECKS} — a population this small cannot be reordered "
            "informatively"
        )

    pairs: list[tuple[Sweep, Sweep]] = []
    for label, order in plan_orders:
        first = sweep(checks_dir, home, label, order, cold, timeout)
        if not pairs and first.claim_count < MIN_CREDIBLE_CLAIMS:
            raise RefusedError(
                f"the observer recorded {first.claim_count} claim(s) across "
                f"{population} checks, below the floor of {MIN_CREDIBLE_CLAIMS} — "
                "that is the signature of a disarmed observer, not of a population "
                "that touches nothing"
            )
        pairs.append((first, sweep(checks_dir, home, label, order, cold, timeout)))
    return compare(pairs)


# ---------------------------------------------------------------------------
# THE CONTROL — a detector that has never been seen to fire is a green light.
# ---------------------------------------------------------------------------
#
# Two planted checks share ONE on-disk cache and the first to run pays for it.
# That is the `.pyc` mechanism with the interpreter taken out of it, so the
# control tests the detector rather than CPython's import machinery.
#
# `CONTROL_LAZY_*` is the historical shape itself: neither planted check imports
# `checks/_preamble.py`, so `sys.dont_write_bytecode` is NOT set in the observed
# child, and a lazy import inside `run()` writes a bytecode cache INSIDE the
# armed window — exactly what ARC 026 measured. It exists to prove that the
# `.pyc` normalisation rule earns its place: without rule 1 this control's claim
# is volatile-named and the detector demotes ARC 026's own defect to UNSTABLE.

_CONTROL_HEAD = '''\
"""Planted by scripts/tests/attribution_drift.py. Not a real check."""

import sys
from pathlib import Path

sys.path.insert(0, {scripts!r})

from nixverify.contract import CheckResult, Status  # noqa: E402

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
DEPENDS_ON = ()
RESOURCES = ("planted-control",)
CORRECTABLE = False
SUBJECTS = ()
'''

#: Every planted check makes this claim UNCONDITIONALLY, so the control clears
#: the production credibility floor on honest claims rather than by lowering it.
#: A control that only works with the floor turned down is not testing the
#: instrument that ships.
_CONTROL_OWN = '''

def _own(ctx):
    """A deterministic per-check claim. Stable under every order, by construction."""
    mine = Path(ctx.nix_home) / "control-state" / "own"
    mine.mkdir(parents=True, exist_ok=True)
    (mine / "{name}").write_text("{name}", encoding="utf-8")
'''

CONTROL_SHARED_CACHE = (
    _CONTROL_HEAD
    + _CONTROL_OWN
    + '''

def run(mode, ctx):
    """Write the shared cache if and only if nobody has written it yet.

    The `.pyc` mechanism with the interpreter taken out of it: one cache, on
    disk, shared, and whoever runs first pays for it.
    """
    _own(ctx)
    cache = Path(ctx.nix_home) / "control-state" / "shared" / "entry"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text("paid for by {name}", encoding="utf-8")
    return CheckResult(name="{name}", status=Status.PASS)
'''
)

CONTROL_LAZY_IMPORT = (
    _CONTROL_HEAD
    + _CONTROL_OWN
    + '''

def run(mode, ctx):
    """Import a shared module LAZILY, inside the observed window (ARC 026)."""
    _own(ctx)
    sys.path.insert(0, str(Path(ctx.nix_home) / "control-state" / "shared-lib"))
    import ctl_shared_module  # noqa: F401  pylint: disable=C0415,W0611

    return CheckResult(name="{name}", status=Status.PASS)
'''
)


def plant_control(checks_dir: Path, home: Path, template: str, names: Sequence[str]):
    """Plant `names` copies of `template` and return the matching cold-state reset."""
    checks_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        (checks_dir / f"{name}.py").write_text(
            template.format(name=name, scripts=str(REPO / "scripts")), encoding="utf-8"
        )
    lib = home / "control-state" / "shared-lib"
    lib.mkdir(parents=True, exist_ok=True)
    (lib / "ctl_shared_module.py").write_text(
        "VALUE = 1  # planted shared module\n", encoding="utf-8"
    )
    # The planted MODULE SOURCE survives the reset; its bytecode cache does not.
    # Deleting the source would make the lazy-import control fail to import
    # rather than fail to be cached — a control that broke instead of firing.
    state = home / "control-state"
    return default_cold(
        home, extra=(state / "own", state / "shared", lib / "__pycache__")
    )


def self_test(workdir: Path, template: str = CONTROL_SHARED_CACHE) -> Report:
    """Plant an order-dependent claim and REQUIRE the detector to report it."""
    checks_dir = workdir / "checks"
    names = [f"check_ctl_drift_{i}" for i in range(MIN_CREDIBLE_CHECKS + 1)]
    cold = plant_control(checks_dir, workdir, template, names)
    report = detect(
        checks_dir,
        workdir,
        plan=[names],
        cold=cold,
        order_count=2,
        exclude=(),
        timeout=30.0,
    )
    if report.clean:
        raise RefusedError(
            "SELF-TEST FAILED: a planted, genuinely order-dependent claim was NOT "
            "reported. The detector cannot fire, and a detector that cannot fire "
            "is a green light. Unstable claims seen instead: "
            + ("; ".join(d.render() for d in report.unstable) or "<none>")
        )
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def render(report: Report) -> None:
    """Print the report. Orders are printed in full — they ARE the evidence."""
    print("\nORDERS RUN (blocks in plan order; permuted within a block only)")
    for one in report.sweeps:
        print(
            f"  {one.label:<24} cleared={one.cleared:<3} {one.elapsed_s:>6}s "
            f"{one.claim_count:>3} raw claim(s)"
        )
        print(f"      {' -> '.join(one.order)}")

    print(f"\nORDER-DEPENDENT ATTRIBUTION ({len(report.order_dependent)})")
    for drift in report.order_dependent or ():
        print(f"  FAIL {drift.render()}")
    if not report.order_dependent:
        print("  none — no claim changed owner when the plan was reordered")

    print(f"\nUNSTABLE BETWEEN IDENTICAL ORDERS ({len(report.unstable)})")
    for drift in report.unstable or ():
        print(f"  ?    {drift.render()}")
    if not report.unstable:
        print("  none")

    for note in report.notes:
        print(f"\nNOTE {note}")


def main(argv: list[str] | None = None) -> int:
    """`--self-test` proves the detector fires; the default run sweeps this tree."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--home", default=str(REPO))
    parser.add_argument("--orders", type=int, default=2)
    parser.add_argument("--json", dest="json_out", default="")
    parser.add_argument(
        "--cold-extra",
        action="append",
        default=[],
        help="an additional path to remove before every sweep (see the residual)",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.self_test:
            with tempfile.TemporaryDirectory(prefix="nix-drift-selftest-") as tmp:
                report = self_test(Path(tmp))
                print("SELF-TEST PASSED: the planted claim was reported.")
                render(report)
            return 0

        home = Path(args.home).resolve()
        report = detect(
            checks_dir=home / "checks",
            home=home,
            plan=registry_blocks(home / "checks" / "registry.json"),
            cold=default_cold(home, [Path(p) for p in args.cold_extra]),
            order_count=args.orders,
        )
    except RefusedError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    render(report)
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(
                {
                    "order_dependent": [
                        {"claim": d.claim, "owners": d.per_order}
                        for d in report.order_dependent
                    ],
                    "unstable": [
                        {"claim": d.claim, "owners": d.per_order}
                        for d in report.unstable
                    ],
                    "orders": {
                        first.label: list(first.order) for first, _ in report.pairs
                    },
                    "cleared": [
                        {"order": one.label, "cleared": one.cleared}
                        for one in report.sweeps
                    ],
                    "notes": list(report.notes),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return 0 if report.clean else 1


if __name__ == "__main__":
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "")
    sys.exit(main())
