#!/usr/bin/env python3
# C0302: the derivation argument, the §7.12 block and the per-finding reason
# strings ARE the deliverable, and check contract §4.2 requires a check be
# independently runnable as ONE file.
# pylint: disable=too-many-lines
"""Gate: §3's gate NEVER acts on a stale, out-of-order or half-built input — I12.

ARC 051. Subjects: `scripts/nixrisk/gate.py`, `scripts/nixrisk/freshness.py`,
`scripts/nixrisk/picture.py`, imported out of `ctx.nix_home` and DRIVEN.

Every `§` cites `docs/nics_risk_subsystem_spec_v1.3.md` — the frozen risk spec —
unless another document is named on the same line.

ONE gate, ONE property (`nix_check_contract.md` §5.5, doctrine C.9):

    **the set of inputs §3's gate ACTS ON equals the set whose freshness is
    CHECKED, and on each of the three bad-stamp conditions the gate refuses
    while on the good one it proceeds.**

------------------------------------------------------------------------------
DOCTRINE C.9 — THE OWNERSHIP CENSUS, TAKEN BEFORE A LINE OF THIS FILE
------------------------------------------------------------------------------
Four gates in this tree touch freshness. Every one of them owns ONE FILE, and
the census below is why a fifth instrument is a new property rather than a
second opinion:

* `check_staleness` owns `scripts/nixrisk/freshness.py` + `risks/staleness.config.json`
  — that the DETECTOR is right: age off the last arrival and not a session mean
  (the ARC 022 F17 defect), the retry ladder, `EMPTY` blocking, the UTC rule,
  `SourceMonotonicGuard`, the two Protocol connections. It never asks what the
  gate's OTHER inputs are.
* `check_picture_atomicity` owns `scripts/nixrisk/picture.py` — that the
  publisher's snapshot is atomic under a real race. Atomicity is not freshness:
  a perfectly atomic snapshot from 900 s ago is exactly what §6.4 forbids
  sizing on.
* `check_allocator_mirror` owns `scripts/nixalloc/mirror.py` — the CONSUMER's
  private mirror, four states and a per-key guard. Different side of the wire
  and a different object; that module's own docstring says so.
* `check_limiter_gate` owns `scripts/nixrisk/gate.py` — §3's DISPATCH ORDER and
  phase partition. `CHECK-DEBT` D3.392 is the standing proof that a gate scoped
  to one file is structurally blind to a relation that spans two: the Limiter's
  margin cap read no stop distance at all for three arcs while `check_allocator_caps`
  stayed green, *"because its `SUBJECTS` is `nixalloc/caps.py` ... `gate.py` is
  not in scope, so both facts were invisible to it by construction."*

What NONE of them owns is the RELATION: *an input added to the gate tomorrow
with no freshness check.* That input would be inside `gate.py` (so
`check_staleness` cannot see it), would not move dispatch order (so
`check_limiter_gate` stays green), and would touch neither mirror. That is the
defect this gate exists to catch, and it is why the derivation below is a
derivation and not a list.

------------------------------------------------------------------------------
THE INPUT SET, DERIVED BY SHAPE — never transcribed
------------------------------------------------------------------------------
A spelled list of the gate's inputs would go stale on the arc that adds the
seventh port, and would go stale SILENTLY, reporting full coverage of a set that
had grown. Everything below is read off the shipped AST:

1. **PORT TYPES** — every `class X(Protocol)` declared in `gate.py`, with each
   verb's RETURN ANNOTATION. That annotation is what classifies the port:
   `tuple[float, bool]` is a `(value, fresh)` pair the rule must branch on;
   `tuple[bool, str]` is §11.1's `(blocked, reason)` cache flag the rule must
   deny on.
2. **INPUTS** — every parameter of `default_manifest`, of `GatePass.__init__`
   and of every `evaluate`, taken with its annotation. Nine of them today; the
   count is measured, never asserted.
3. **STAMP FIELDS** — the attribute names that FRESHNESS-REFUSAL SITES read.
   A refusal site is derived, not named: a function that calls a clock and
   subtracts an attribute from it. Today that yields `as_of`, `observed_at` and
   `published_ts` among others, from `freshness.py`, `picture.py` and
   `nixalloc/mirror.py` — three modules, none of them written into this file.
4. **CLOCK-SOURCED FIELDS** — keyword names anywhere in shipped code whose value
   expression contains a clock call. `published_ts=self._clock()` puts
   `published_ts` here; `signal_ts=float(raw.get("signal_ts") or time.time())`
   in `limiterd.py` puts `signal_ts` here.

A dataclass field that is CLOCK-SOURCED but is NOT a STAMP FIELD is a time
quantity on a gate input that no refusal site in the tree reads — and that is
reported by name, against the ratchet below, rather than being quietly absorbed.

------------------------------------------------------------------------------
`ProposedOrder.signal_ts` — THE ONE ACCEPTED UNGATED TIME FIELD, AND WHY
------------------------------------------------------------------------------
The derivation finds exactly one today and it is stated here rather than
discovered by a reader of a red verdict. §6.4b's monotonic guard is scoped by
its own words to *"ALL venue-sourced state ... balance, per-symbol margin, and
position/quantity updates"*. A GO's `signal_ts` is STRATEGY-sourced: it does not
arrive from the venue, is not admitted through a guard, and has no `decode_*` in
this tree. §4:210-212 bounds the OTHER interval — admission to terminal feedback
— on the loop's own monotonic tick clock (`nixrisk/loop.py::GoTimeout`), not on
the signal instant. Whether a signal's own age should bound entry is a question
the frozen spec does not answer, so it is CHECK-DEBT (D3.463) and an architect's
ruling, not a decision this instrument makes by going red or by going quiet.

`_ACCEPTED_UNGATED` is a ONE-WAY RATCHET, in the shape
`checks/uncalled_entry_points_baseline.json` and `gate_coverage_baseline.json`
already use: a field in it is admitted BY NAME with its debt row; a field NOT in
it is a FAIL. Silent growth is the exact defect.

------------------------------------------------------------------------------
BOTH DIRECTIONS, ON REAL OBJECTS
------------------------------------------------------------------------------
Freshness achieved by denying everything is safe and useless, so every deny arm
is paired with an ACT arm on the same object:

* **ARM 2 STALE** — a price feed 900 s past a 2 000 ms threshold and past the
  3 750 ms retry/backoff deadline: the real `GatePass` DENIES at
  `data_staleness`. Paired: a 100 ms-old feed APPROVES.
* **ARM 3 OUT-OF-ORDER** — a reading older than the one held, a same-instant
  lower `source_seq`, and an exact duplicate: all three DISCARDED and the held
  stamp does not move (§6.4b / V27). Paired: a strictly newer reading is
  ADMITTED. Driven through the gate too — a late poll cannot un-stale a feed
  that has already gone silent.
* **ARM 4 HALF-BUILT** — a `statebus.Mirror` mid-rebuild and then delta-only:
  `PictureMirror.tradable()` is `False` both times, naming the missing topic
  (§12.7 / V31). Paired: once the SNAPSHOT lands it is `True`, and once that
  snapshot ages past the ceiling it is `False` again.
* **ARM 5 §6.5** — `(10_000_000.0, fresh=False)`: a comfortable NUMBER with a
  dead stamp is DENIED at `survival_headroom`. Paired: `fresh=True` approves.

------------------------------------------------------------------------------
NOT CLAIMED HERE
------------------------------------------------------------------------------
* The **flatten-open half** of §6.4 (*"stale ⇒ halt new entries AND flatten
  open"*). This gate proves the HALT half — stale ⇒ deny. The STALE_PRICE
  producer that flattens an already-open position is `CHECK-DEBT` D3.453,
  owned by the I1 daemon capstone.
* **V32 one-version cross-table coherence** — that a pass never reads fresh
  margin against stale balance. That is the ATOMIC-SNAPSHOT property and it
  belongs to `check_picture_atomicity`; it intersects here only in that both
  read `FinancialPicture.version`, and it is not re-litigated.

------------------------------------------------------------------------------
debug.md §7.12 — what would make this gate PASS while measuring nothing?
------------------------------------------------------------------------------
1. **The gate is never driven.** A census over a pass that denied at rule one
   says nothing about the rules after it. *Closed:* ARM 1 requires a real
   `Decision.APPROVE` with every rule in `evaluated` BEFORE any deny arm runs,
   and the approve is asserted on the rule count, not on the enum alone.
2. **The stamps driven are not the stamps the subject reads.** *Closed:* every
   threshold comes from `risks/staleness.config.json` through the subject's own
   `StalenessPolicy.from_values`; this file contains no threshold number, and
   the age driven is asserted against the policy's own `deadline_ms`.
3. **The derivation finds nothing and an empty set compares equal to an empty
   set.** *Closed:* `FLOORS` requires a measured minimum of ports, inputs, stamp
   fields and driven arms; below any of them the verdict is CANNOT_MEASURE
   naming the floor, never PASS.
4. **A new input is added with no freshness check.** *Closed:* ARM 1 classifies
   EVERY derived input and an input it cannot place is CANNOT_MEASURE naming it.
5. **The ratchet is widened until the defect fits.** *Closed:* `_ACCEPTED_UNGATED`
   is a two-entry map carrying its debt row, and every entry is printed in the
   evidence of a PASS so widening it is visible in the green.
6. **Denial by construction.** A detector that blocked every reading would pass
   all three deny arms. *Closed:* each is paired with an ACT arm on the same
   object (see above), and ARM 6 fails if the act side does not act.
7. **One stale drop is read as the invariant** (§0a — watch past the tick).
   *Closed:* ARM 3 drives the gate AFTER the stale verdict, with a late reading
   arriving, and requires the deny to hold.

------------------------------------------------------------------------------
CORRECTABLE = False
------------------------------------------------------------------------------
The subject is WHICH READINGS THE RISK GATE IS WILLING TO ACT ON. An instrument
empowered to edit `freshness.py`, `gate.py` or `picture.py` into agreement would
be authoring the code it certifies. The repair for a missing freshness check is
an architectural move against §6.4/§6.4b/§12.7 decided by a human.
"""

from __future__ import annotations

import ast
import importlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code
# R0801 pairs this file's DECLARATION BLOCK and its `standalone_main` footer
# against every other house-style check's. That shape is REQUIRED (§4.2).
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

#: Nothing must run first. Every subject is imported from the tree under test.
DEPENDS_ON: tuple[str, ...] = ()
#: The subjects are imported from `ctx.nix_home`, which mutates `sys.path` and
#: `sys.modules` for the duration of the load (both restored). Check contract
#: v2 rule 12: a declaration is checked against OBSERVATION, so the interpreter
#: mutation is DECLARED rather than hoped to be invisible. No port is bound, no
#: subprocess is spawned, nothing is written: every drive is arithmetic over
#: objects this process constructed, on an injected clock.
RESOURCES: tuple[str, ...] = ("interpreter:sys.path", "interpreter:sys.modules")
TIME_BOUND = False
#: NON-CORRECTABLE — see the module docstring's closing section.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is which readings the risk gate is willing to act on. An "
    "instrument that could edit freshness.py, gate.py or picture.py into "
    "agreement would be authoring the code it certifies, and choosing a stale "
    "threshold is an operator's decision under §12A, not an unattended gate's"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/nixrisk/gate.py",
    "scripts/nixrisk/freshness.py",
    "scripts/nixrisk/picture.py",
)

NAME = "check_input_freshness"

REL_GATE = "scripts/nixrisk/gate.py"
REL_FRESHNESS = "scripts/nixrisk/freshness.py"
REL_PICTURE = "scripts/nixrisk/picture.py"
REL_SEAM = "scripts/nixrisk/seam.py"
REL_CONFIG = "risks/staleness.config.json"

DRIVE_SYMBOL = "ES"
#: The ARC 022 F17 silence, reused so the stale drive is the real defect's
#: magnitude rather than a marginal overshoot. Asserted against the SUBJECT's
#: own `deadline_ms` before it is used, so it is a drive parameter and not a
#: second authority for the threshold.
SILENCE_MS = 900_000.0

FLOORS: dict[str, int] = {
    # §11's port set: HALT, per-symbol flag, global flag, in-flight, net-liq
    # mark. Below five the derivation has lost the shape it reads.
    "ports": 5,
    # blackout, tradability, staleness, clock_skew, in_flight, net_liq, halt,
    # order, picture — the nine readings and collaborators, before knobs.
    "inputs": 9,
    # `as_of`, `observed_at`, `published_ts` — three refusal sites in three
    # different modules. A derivation that finds fewer has stopped seeing them.
    "stamp_fields": 3,
    # Every arm this docstring enumerates must actually have run.
    "arms": 6,
    # §12A's four feeds. A config that quietly dropped one is CANNOT_MEASURE
    # rather than a smaller green.
    "feeds": 4,
    # ARM 1's non-vacuity: the whole manifest plus the halt pre-gate.
    "rules_evaluated": 9,
}

#: THE ONE-WAY RATCHET. A dataclass field on a gate input that is CLOCK-SOURCED
#: somewhere in shipped code but that NO freshness-refusal site reads. Admitted
#: BY NAME, with the debt row that owns it. A field NOT here is a FAIL — silent
#: growth is the defect. See the module docstring's `signal_ts` section.
_ACCEPTED_UNGATED: dict[str, str] = {
    "ProposedOrder.signal_ts": (
        "STRATEGY-sourced, not venue-sourced: §6.4b scopes the monotonic guard "
        "to 'ALL venue-sourced state — balance, per-symbol margin, and "
        "position/quantity updates', and a GO is none of those. §4:210-212 "
        "bounds admission -> terminal feedback on the loop's own monotonic tick "
        "clock (nixrisk/loop.py::GoTimeout), not the signal instant. Whether a "
        "signal's OWN age should bound entry is unanswered by the frozen spec "
        "— CHECK-DEBT D3.463, architect ruling"
    ),
}


class Finding(NamedTuple):
    """One divergence. `site` names WHERE, `why` names the reason (§18)."""

    site: str
    why: str


def _fail(findings: list[Finding]) -> CheckResult:
    return CheckResult(
        name=NAME,
        status=Status.FAIL_NEEDS_OPERATOR,
        site="; ".join(f.site for f in findings),
        evidence=f"{len(findings)} violation(s): " + "; ".join(f.why for f in findings),
        detail=" | ".join(f"{f.site}: {f.why}" for f in findings),
    )


def _cannot(detail: str, site: str = "") -> CheckResult:
    return CheckResult(
        name=NAME, status=Status.CANNOT_MEASURE, site=site, detail=detail
    )


# ---------------------------------------------------------------------------
# Subject loading — imported FROM `home`, never from whichever tree imported first
# ---------------------------------------------------------------------------

_PREFIXES = ("nixrisk", "nixbus")


class _Subject(NamedTuple):
    gate: Any
    freshness: Any
    picture: Any
    calendar_seam: Any
    seam: Any
    statebus: Any


def _purged() -> dict[str, Any]:
    saved = {
        key: value
        for key, value in sys.modules.items()
        if any(key == p or key.startswith(f"{p}.") for p in _PREFIXES)
    }
    for key in saved:
        del sys.modules[key]
    return saved


def _restore(saved: dict[str, Any]) -> None:
    for key in [
        key
        for key in list(sys.modules)
        if any(key == p or key.startswith(f"{p}.") for p in _PREFIXES)
    ]:
        del sys.modules[key]
    sys.modules.update(saved)


def load_subject(home: Path) -> tuple[_Subject | None, str]:
    """Import every subject FROM `home`. Returns `(subject, complaint)`.

    `sys.modules` is purged of `nixrisk*`/`nixbus*` before and restored after:
    a check that ran once against the repo would otherwise hand back the repo's
    module for every subsequent tree, and a plant that is never loaded is a
    plant that cannot fail (`check_limiter_gate.load_subject`'s reason).
    """
    scripts = home / "scripts"
    if not (scripts / "nixrisk" / "gate.py").is_file():
        return None, f"{REL_GATE} is not on disk under {home} — nothing to drive"
    saved_path = list(sys.path)
    saved_mods = _purged()
    sys.path.insert(0, str(scripts.resolve()))
    try:
        mods = _Subject(
            gate=importlib.import_module("nixrisk.gate"),
            freshness=importlib.import_module("nixrisk.freshness"),
            picture=importlib.import_module("nixrisk.picture"),
            calendar_seam=importlib.import_module("nixrisk.calendar_seam"),
            seam=importlib.import_module("nixrisk.seam"),
            statebus=importlib.import_module("nixbus.statebus"),
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"the subjects would not import from {home}: {type(exc).__name__}: {exc}"
        )
    finally:
        _restore(saved_mods)
        sys.path[:] = saved_path
    return mods, ""


def _absent(home: Path) -> CheckResult | None:
    """CANNOT_MEASURE naming every absent subject (§17)."""
    missing = [
        rel
        for rel in (REL_GATE, REL_FRESHNESS, REL_PICTURE, REL_SEAM, REL_CONFIG)
        if not (home / rel).is_file()
    ]
    if not missing:
        return None
    return _cannot(
        f"absent subject(s) under {home}: {', '.join(missing)} — a property "
        "proven while its subject is unavailable is not proven (§17)",
        site=str(home),
    )


def _config_values(home: Path) -> tuple[dict[str, Any], str]:
    """`risks/staleness.config.json`'s VALUE keys. `_`-prefixed keys are prose."""
    try:
        raw = json.loads((home / REL_CONFIG).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, f"{REL_CONFIG} could not be read or parsed: {exc}"
    if not isinstance(raw, dict):
        return {}, f"{REL_CONFIG}: top level is {type(raw).__name__}, expected object"
    return {k: v for k, v in raw.items() if not k.startswith("_")}, ""


# ---------------------------------------------------------------------------
# ARM 1 — THE CENSUS. Every figure below is read off the shipped AST.
# ---------------------------------------------------------------------------

#: Names a clock call can wear. Matched on the CALLEE, so `self._clock()`,
#: `time.time()`, `time.monotonic()` and an injected `clock()` all count. Kept
#: as a shape rather than a module list because the detector modules inject
#: their clock precisely so they can be tested without waiting.
_CLOCK_NAMES = frozenset(
    {"time", "monotonic", "perf_counter", "clock", "_clock", "utcnow"}
)


def _is_clock_call(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        name = (
            func.attr
            if isinstance(func, ast.Attribute)
            else (func.id if isinstance(func, ast.Name) else "")
        )
        if name in _CLOCK_NAMES or name.endswith("_clock"):
            return True
    return False


class _Census(NamedTuple):
    ports: dict[str, dict[str, str]]
    inputs: dict[str, list[tuple[str, str]]]
    stamp_fields: dict[str, list[str]]
    clock_sourced: dict[str, list[str]]
    dataclass_fields: dict[str, list[tuple[str, str]]]


def _protocol_ports(tree: ast.AST) -> dict[str, dict[str, str]]:
    """Every `class X(Protocol)` in `gate.py`, verb -> return annotation."""
    ports: dict[str, dict[str, str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not any(isinstance(b, ast.Name) and b.id == "Protocol" for b in node.bases):
            continue
        ports[node.name] = {
            item.name: (ast.unparse(item.returns) if item.returns else "")
            for item in node.body
            if isinstance(item, ast.FunctionDef)
        }
    return ports


def _params(fn: ast.FunctionDef) -> list[tuple[str, str]]:
    args = fn.args
    out: list[tuple[str, str]] = []
    for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
        if arg.arg == "self":
            continue
        out.append((arg.arg, ast.unparse(arg.annotation) if arg.annotation else ""))
    return out


def _site_of(cls: ast.ClassDef, fn: ast.FunctionDef) -> str:
    """The SITE label a parameter is recorded under, or `""` if it is not an input.

    The executor contributes its constructor and its per-pass verb; every other
    class contributes its `evaluate`, because that is the surface a `RulePort`
    reads an order and a picture through.
    """
    if cls.name == "GatePass":
        if fn.name in ("__init__", "evaluate"):
            return f"GatePass.{fn.name}"
        return ""
    if fn.name == "evaluate":
        return f"{cls.name}.evaluate"
    return ""


def _gate_inputs(tree: ast.AST) -> dict[str, list[tuple[str, str]]]:
    """Every parameter of the manifest builder, the executor, and every rule."""
    found: dict[str, list[tuple[str, str]]] = {}

    def record(site: str, fn: ast.FunctionDef) -> None:
        for name, ann in _params(fn):
            found.setdefault(name, []).append((site, ann))

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "default_manifest":
            record("default_manifest", node)
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and (site := _site_of(node, item)):
                record(site, item)
    return found


def _subtracted_attrs(fn: ast.FunctionDef) -> list[str]:
    """Attribute names this function subtracts from something. `now - x.stamp`.

    Called only for functions that already CALL a clock, so the pair of
    conditions is one predicate: a clock read, and a difference taken against an
    attribute. Either half alone matches things that are not freshness refusals.
    """
    names: list[str] = []
    for sub in ast.walk(fn):
        if not isinstance(sub, ast.BinOp) or not isinstance(sub.op, ast.Sub):
            continue
        names.extend(
            side.attr
            for side in (sub.left, sub.right)
            if isinstance(side, ast.Attribute)
        )
    return names


def _fold_stamp_sites(node: ast.AST, rel: str, stamps: dict[str, list[str]]) -> None:
    """One node: if it is a freshness-refusal site, record every attribute it reads."""
    if not isinstance(node, ast.FunctionDef) or not _is_clock_call(node):
        return
    for attr in _subtracted_attrs(node):
        stamps.setdefault(attr, []).append(f"{rel}:{node.lineno}:{node.name}")


def _fold_clock_sourced(node: ast.AST, rel: str, sourced: dict[str, list[str]]) -> None:
    """One node: if it is a call, record every keyword born from a clock read."""
    if not isinstance(node, ast.Call):
        return
    for kw in node.keywords:
        if kw.arg and _is_clock_call(kw.value):
            sourced.setdefault(kw.arg, []).append(f"{rel}:{kw.value.lineno}")


def _module_derivations(
    tree: ast.AST, rel: str, stamps: dict[str, list[str]], sourced: dict[str, list[str]]
) -> None:
    """Fold ONE module's two derivations into the accumulators."""
    for node in ast.walk(tree):
        _fold_stamp_sites(node, rel, stamps)
        _fold_clock_sourced(node, rel, sourced)


def _tree_derivations(home: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """`(stamp_fields, clock_sourced)` — derived over every shipped module.

    * A **stamp field** is an attribute a FRESHNESS-REFUSAL SITE reads: a
      function that calls a clock and subtracts an attribute from it. That is
      §3's *"fast-drop reads own staleness stamps"* as a shape.
    * A **clock-sourced field** is a keyword whose value expression contains a
      clock call — where a time quantity is BORN.
    """
    stamps: dict[str, list[str]] = {}
    sourced: dict[str, list[str]] = {}
    for py in sorted((home / "scripts").rglob("*.py")):
        if "/tests/" in str(py):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except OSError, SyntaxError:
            continue
        _module_derivations(tree, py.relative_to(home).as_posix(), stamps, sourced)
    return stamps, sourced


def _dataclass_fields(home: Path) -> dict[str, list[tuple[str, str]]]:
    """Field name + annotation for every dataclass in `nixrisk/seam.py`."""
    out: dict[str, list[tuple[str, str]]] = {}
    try:
        tree = ast.parse((home / REL_SEAM).read_text(encoding="utf-8"))
    except OSError, SyntaxError:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        fields = [
            (item.target.id, ast.unparse(item.annotation))
            for item in node.body
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
        ]
        if fields:
            out[node.name] = fields
    return out


def _census(home: Path) -> tuple[_Census | None, str]:
    try:
        gtree = ast.parse((home / REL_GATE).read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        return None, f"{REL_GATE} would not parse: {exc}"
    stamps, sourced = _tree_derivations(home)
    return (
        _Census(
            ports=_protocol_ports(gtree),
            inputs=_gate_inputs(gtree),
            stamp_fields=stamps,
            clock_sourced=sourced,
            dataclass_fields=_dataclass_fields(home),
        ),
        "",
    )


# --- classification ---------------------------------------------------------

#: The verdict buckets. A gate input lands in exactly one, or in none — and
#: NONE is CANNOT_MEASURE naming it, never a PASS.
FRESH_PAIR = "port:(value,fresh) — the rule must branch on the flag"
FLAG_PORT = "port:(blocked,reason) — §11.1 cache flag, the rule must deny on it"
SNAPSHOT = "snapshot — carries a stamp field a refusal site reads"
IN_PROCESS = "in-process proposal — no stamp field, no shipped decoder"
KNOB = "§12A knob — boot-loaded, restart-only (§12.11); not a per-pass reading"
CLOCK_READ = "per-pass clock read — covered by the clock_skew port in the same pass"
STRUCTURAL = "structural collaborator — a manifest or a ledger, not a reading"


# R0911 (too-many-return-statements): each return IS a bucket, and the buckets are
# the classification. Collapsing them into one exit through a variable would hide
# the one property that matters — that every path either NAMES a bucket or falls
# through to unclassifiable — behind an accumulator a reader has to simulate.
# pylint: disable=too-many-return-statements
def _classify_port(name: str, base: str, verbs: dict[str, str]) -> tuple[str, str]:
    """A port's bucket, read off its verbs' RETURN ANNOTATIONS and nothing else."""
    returns = " ".join(sorted(verbs.values()))
    if "tuple[float, bool]" in returns:
        return FRESH_PAIR, f"{base}.{min(verbs)} -> {returns}"
    if "tuple[bool, str]" in returns:
        return FLAG_PORT, f"{base}.{min(verbs)} -> {returns}"
    return "", (
        f"{name}: port {base} declares verbs {verbs} — no return shape this "
        "census can classify as carrying a freshness signal"
    )


def _classify_dataclass(base: str, census: _Census) -> tuple[str, str]:
    """A seam dataclass's bucket: STAMPED iff a refusal site reads one of its fields."""
    fields = {f for f, _ in census.dataclass_fields[base]}
    stamped = sorted(fields & set(census.stamp_fields))
    if not stamped:
        return IN_PROCESS, f"{base}: no field is read by any freshness-refusal site"
    sites = sorted({s for f in stamped for s in census.stamp_fields[f]})
    return SNAPSHOT, f"{base}: stamp field(s) {stamped} read at {sites[:3]}"


def _classify(name: str, annotations: list[str], census: _Census) -> tuple[str, str]:
    """`(bucket, detail)`; bucket `""` means UNCLASSIFIABLE — never a PASS."""
    anns = {a for a in annotations if a}
    if not anns:
        return "", f"{name}: carries NO annotation, so its shape cannot be read"
    ann = min(anns)
    base = ann.replace(" | None", "").strip()

    if base in census.ports:
        return _classify_port(name, base, census.ports[base])

    if base in census.dataclass_fields:
        return _classify_dataclass(base, census)

    if base in ("float", "int"):
        # A scalar on the MANIFEST is a §12A knob (§12.11 boot-loaded); a scalar
        # on the per-pass `evaluate` is a clock read, whose integrity is the
        # `clock_skew` GlobalFlagPort's job in the SAME pass.
        found_at = {s for s, _ in _SITES.get(name, [])}
        if any(s.startswith("GatePass.evaluate") for s in found_at):
            return CLOCK_READ, f"{name}: {ann} on GatePass.evaluate"
        return KNOB, f"{name}: {ann} on the manifest builder"

    # STRUCTURAL is deliberately NARROW. A `Sequence[...]` is the manifest, and
    # an OPTIONAL port is a collaborator the executor may be built without
    # (`ledger: ReservationLedgerPort | None`). A NEW, MANDATORY port type that
    # `gate.py` does not declare falls through to unclassifiable on purpose:
    # widening this branch to every name ending in `Port` would let exactly the
    # defect this gate exists to catch — an input added with no freshness check
    # — classify itself as "not a reading" and disappear.
    if base.startswith("Sequence["):
        return STRUCTURAL, f"{name}: {ann}"
    if base.endswith("Port") and " | None" in ann:
        return STRUCTURAL, f"{name}: {ann} (optional collaborator)"

    return "", f"{name}: annotation {ann!r} matches no shape this census reads"


#: Filled by `_arm_census` before `_classify` runs. Module-level because the
#: classifier needs the SITE a parameter was found at (manifest vs per-pass) and
#: threading it through every call would obscure the one place it is used.
_SITES: dict[str, list[tuple[str, str]]] = {}


def _ungated_time_fields(census: _Census) -> tuple[list[Finding], list[str]]:
    """The completeness obligation, as a POSITIVE observation.

    Every clock-sourced field on a gate-input dataclass must be either a STAMP
    field (some refusal site reads it) or in `_ACCEPTED_UNGATED` (admitted by
    name, with its debt row). Anything else is a time quantity the gate acts on
    without ever asking how old it is.
    """
    findings: list[Finding] = []
    accepted: list[str] = []
    for key in sorted(_ungated_keys(census)):
        if key in _ACCEPTED_UNGATED:
            accepted.append(f"{key} [accepted: {_ACCEPTED_UNGATED[key]}]")
        else:
            findings.append(Finding(f"{REL_SEAM}:{key}", _ungated_why(key, census)))
    return findings, accepted


def _ungated_keys(census: _Census) -> set[str]:
    """`<Dataclass>.<field>` for every clock-sourced field NO refusal site reads."""
    keys: set[str] = set()
    for name in sorted(census.inputs):
        for ann in {a for _, a in census.inputs[name] if a}:
            base = ann.replace(" | None", "").strip()
            keys.update(
                f"{base}.{field}"
                for field, _ftype in census.dataclass_fields.get(base, [])
                if field in census.clock_sourced and field not in census.stamp_fields
            )
    return keys


def _ungated_why(key: str, census: _Census) -> str:
    """The sentence an operator reads out of an UNGATED TIME FIELD verdict (§18)."""
    field = key.split(".", 1)[1]
    return (
        f"UNGATED TIME FIELD: {key} is CLOCK-SOURCED at "
        f"{census.clock_sourced[field][:2]} and is read by NO freshness-refusal "
        "site in the tree, so the gate acts on it without ever asking how old it "
        "is. §6.4 puts a reading past its threshold behind a refusal; a reading "
        "with no threshold has no refusal to be behind. Admit it by name in "
        "_ACCEPTED_UNGATED with a CHECK-DEBT row, gate it, or remove it"
    )


def _arm_census(census: _Census) -> tuple[list[Finding], list[str], dict[str, Any]]:
    """`(findings, unclassifiable, stats)`. Rule 4: unclassifiable is judged LAST."""
    _SITES.clear()
    _SITES.update(census.inputs)
    unclassifiable: list[str] = []
    buckets: dict[str, list[str]] = {}
    for name in sorted(census.inputs):
        bucket, detail = _classify(name, [a for _, a in census.inputs[name]], census)
        if bucket:
            buckets.setdefault(bucket, []).append(f"{name} ({detail})")
        else:
            unclassifiable.append(detail)
    findings, accepted = _ungated_time_fields(census)
    stats = {
        "ports": len(census.ports),
        "inputs": len(census.inputs),
        "stamp_fields": len(census.stamp_fields),
        "buckets": {k: sorted(v) for k, v in sorted(buckets.items())},
        "ungated_accepted": sorted(accepted),
    }
    return findings, unclassifiable, stats


# ---------------------------------------------------------------------------
# The drives — real objects, injected clocks, the subject's own thresholds
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 1, 2, 15, 0, 0, tzinfo=UTC)


class _Clear:
    """Every §11.1-shaped port in one object, all clear. In-memory BY SPEC (§11)."""

    def read(self, symbol: str | None = None) -> tuple[bool, str]:
        """`(blocked, reason)`."""
        del symbol
        return False, ""

    def is_set(self) -> tuple[bool, str]:
        """`(halted, why)`."""
        return False, ""

    def in_flight(self, strategy_id: str) -> tuple[bool, str]:
        """`(locked, reason)`."""
        del strategy_id
        return False, ""

    def mark(self) -> tuple[float, bool]:
        """§6.5's net-liq mark, fresh."""
        return 10_000_000.0, True


class _StaleMark(_Clear):
    """A comfortable NUMBER with a dead stamp — §6.5's fail-closed arm."""

    def mark(self) -> tuple[float, bool]:
        """`fresh=False`, and the number is deliberately generous."""
        return 10_000_000.0, False


# R0903 (too-few-public-methods): a test double for a Protocol with one verb. A
# second method would be a double doing a job the subject never asks of it.
class _Sub:  # pylint: disable=too-few-public-methods
    """The one verb `PictureMirror` reads off a subscriber."""

    def __init__(self, mirror: Any) -> None:
        self.mirror = mirror

    def drain(self, timeout_ms: int) -> list[Any]:
        """Nothing to take: this drive feeds the mirror directly."""
        del timeout_ms
        return []


def _order(subject: _Subject, qty: int = 4) -> Any:
    seam = subject.seam
    return seam.ProposedOrder(
        client_order_id="freshness-1",
        strategy_id="s1",
        symbol=DRIVE_SYMBOL,
        side=seam.Side.LONG,
        qty=qty,
        margin_per_contract=1000.0,
        stop_ticks=40,
        stop_mode=seam.StopMode.FIXED,
        signal_ts=1.0,
    )


def _picture(subject: _Subject, version: int = 1, published_ts: float = 1000.0) -> Any:
    return subject.seam.FinancialPicture(
        version=version,
        published_ts=published_ts,
        balance=1_000_000.0,
        positions=(),
        margin_per_contract={DRIVE_SYMBOL: 1000.0},
        sum_open_margin=0.0,
        sum_reservations=0.0,
        committed=0.0,
        # 0.70 x 1_000_000 - 0 — self-consistent, so `picture_defects` has
        # nothing to say and ARM 4's verdict is about FRESHNESS alone.
        deployable=700_000.0,
    )


def _gate_with(subject: _Subject, **ports: Any) -> Any:
    clear = _Clear()
    slots = {
        "blackout": clear,
        "tradability": clear,
        "staleness": clear,
        "clock_skew": clear,
        "in_flight": clear,
        "net_liq": clear,
    }
    slots.update(ports)
    rules = subject.gate.default_manifest(
        deployable_fraction=0.70,
        survival_safety_pad=0.25,
        coherence_tolerance=0.01,
        **slots,
    )
    return subject.gate.GatePass(clear, list(rules))


def _tracker(subject: _Subject, values: dict, now: datetime) -> Any:
    policy = subject.freshness.StalenessPolicy.from_values(values)
    return subject.freshness.FreshnessTracker(policy, clock=lambda: now)


def _observe(subject: _Subject, tracker: Any, ages_ms: dict[str, float]) -> None:
    """Stamp every configured feed at `now - age`. `ages_ms` overrides per feed."""
    stamp = subject.calendar_seam.FreshnessStamp
    for index, feed in enumerate(tracker.policy.feeds):
        age = ages_ms.get(feed, 100.0)
        tracker.observe(
            stamp(
                feed=feed,
                as_of=_NOW - timedelta(milliseconds=age),
                source_seq=index + 1,
            ),
            DRIVE_SYMBOL,
        )


def _arm_act(subject: _Subject, values: dict) -> tuple[list[Finding], dict[str, Any]]:
    """ARM 1's non-vacuity, run FIRST: a FRESH input, and the gate ACTS on it."""
    tracker = _tracker(subject, values, _NOW)
    _observe(subject, tracker, {})
    port = subject.freshness.StalenessFlagPort(tracker)
    blocked, _why = port.read(DRIVE_SYMBOL)
    outcome = _gate_with(subject, staleness=port).evaluate(
        _order(subject), _picture(subject), 1000.0
    )
    stats = {
        "feeds": len(tracker.policy.feeds),
        "decision": outcome.decision.value,
        "evaluated": len(outcome.evaluated),
        "rules": list(outcome.evaluated),
    }
    if blocked or outcome.decision is not subject.seam.Decision.APPROVE:
        return [
            Finding(
                f"{REL_GATE}:GatePass.evaluate",
                "NON-VACUITY FAILED: with every configured feed stamped 100 ms "
                f"ago the gate answered {outcome.decision.value} at "
                f"{outcome.rule!r} (staleness port blocked={blocked}). A gate "
                "that refuses a FRESH input proves nothing by refusing a stale "
                "one — freshness achieved by denying everything is safe and "
                f"useless. reason: {outcome.reason[:200]}",
            )
        ], stats
    return [], stats


def _arm_stale(subject: _Subject, values: dict) -> tuple[list[Finding], dict[str, Any]]:
    """MODE 1 — a feed past threshold AND past the retry/backoff deadline."""
    tracker = _tracker(subject, values, _NOW)
    policy = tracker.policy
    # The tightest feed, DERIVED from the policy rather than named here.
    feed = min(policy.feeds, key=policy.threshold_ms)
    deadline = policy.deadline_ms(feed)
    _observe(subject, tracker, {feed: SILENCE_MS})
    port = subject.freshness.StalenessFlagPort(tracker)
    reading = next(r for r in port.readings(DRIVE_SYMBOL) if r.feed == feed)
    blocked, why = port.read(DRIVE_SYMBOL)
    outcome = _gate_with(subject, staleness=port).evaluate(
        _order(subject), _picture(subject), 1000.0
    )
    stats = {
        "feed": feed,
        "age_ms": reading.age_ms,
        "threshold_ms": reading.threshold_ms,
        "deadline_ms": deadline,
        "state": reading.state.value,
        "decision": outcome.decision.value,
        "rule": outcome.rule,
    }
    findings: list[Finding] = []
    if SILENCE_MS <= deadline:
        # Not a violation — the drive is no longer past the subject's own
        # deadline, so it is not measuring what it claims to.
        return [], {**stats, "drive_invalid": True}
    if not blocked:
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:StalenessFlagPort.read",
                f"STALE INPUT NOT REFUSED: feed {feed!r} was last stamped "
                f"{reading.age_ms:.0f} ms ago, past its §12A threshold of "
                f"{reading.threshold_ms:.0f} ms and past the "
                f"{deadline:.0f} ms retry/backoff deadline, and the port "
                "reported CLEAR. §6.4: 'stale (freshness stamp past threshold, "
                "after retry/backoff) => halt new entries'",
            )
        )
    if outcome.decision is not subject.seam.Decision.DENY:
        findings.append(
            Finding(
                f"{REL_GATE}:GatePass.evaluate",
                f"THE GATE SIZED ON A STALE INPUT: feed {feed!r} was "
                f"{reading.age_ms:.0f} ms old against a {reading.threshold_ms:.0f} "
                f"ms threshold / {deadline:.0f} ms deadline (state="
                f"{reading.state.value}) and the pass answered "
                f"{outcome.decision.value} at {outcome.rule!r} with "
                f"sized_qty={outcome.sized_qty!r}. The stamp it ignored is the "
                f"one the port reads: {reading.key!r}. §3's fast-drop reads its "
                "own staleness stamps BEFORE sizing or wire",
            )
        )
    elif outcome.rule != "data_staleness":
        findings.append(
            Finding(
                f"{REL_GATE}:GatePass.evaluate",
                f"the stale feed {feed!r} was refused, but by {outcome.rule!r} "
                "and not by the staleness rule — a denial attributed to the "
                "wrong cause sends an operator to the wrong subsystem (§3: "
                "'deny (rule named)')",
            )
        )
    stats["reason"] = why[:160]
    return findings, stats


# R0914 (too-many-locals): each local is one DRIVEN condition (three
# discards, the strictly-newer admit,
# the per-key isolation, the before/after gate outcomes). Collapsing them would
# mean asserting on a value nobody can name in the failure text.
# pylint: disable=too-many-locals
def _arm_order(subject: _Subject, values: dict) -> tuple[list[Finding], dict[str, Any]]:
    """MODE 2 — §6.4b / V27. A reading older than the one held is DISCARDED."""
    fresh = subject.freshness
    stamp = subject.calendar_seam.FreshnessStamp
    guard = fresh.SourceMonotonicGuard()
    key = f"margin:{DRIVE_SYMBOL}"
    newest = stamp(
        feed="margin", as_of=_NOW - timedelta(milliseconds=50), source_seq=10
    )
    admitted_new = guard.admit(key, newest)
    trials = {
        "older instant": stamp(
            feed="margin", as_of=_NOW - timedelta(seconds=900), source_seq=9
        ),
        "same instant, lower seq": stamp(
            feed="margin", as_of=_NOW - timedelta(milliseconds=50), source_seq=4
        ),
        "exact duplicate": stamp(
            feed="margin", as_of=_NOW - timedelta(milliseconds=50), source_seq=10
        ),
    }
    findings: list[Finding] = []
    for label, candidate in trials.items():
        accepted = guard.admit(key, candidate)
        held = guard.held(key)
        if accepted:
            findings.append(
                Finding(
                    f"{REL_FRESHNESS}:SourceMonotonicGuard.admit",
                    f"OUT-OF-ORDER READING ADMITTED ({label}): a stamp "
                    f"as_of={candidate.as_of.isoformat()} seq="
                    f"{candidate.source_seq} was accepted over a held "
                    f"as_of={newest.as_of.isoformat()} seq={newest.source_seq}. "
                    "§6.4b accepts a reading ONLY if it is newer than the one "
                    "held, so balance/margin never regresses on a late or "
                    "duplicate poll (V27)",
                )
            )
        if held.as_of != newest.as_of or held.source_seq != newest.source_seq:
            findings.append(
                Finding(
                    f"{REL_FRESHNESS}:SourceMonotonicGuard.held",
                    f"THE HELD VALUE REGRESSED ({label}): it now reads "
                    f"as_of={held.as_of.isoformat()} seq={held.source_seq}, "
                    f"where it held as_of={newest.as_of.isoformat()} seq="
                    f"{newest.source_seq}. §6.4b's guard exists so a late "
                    "reading can never move the held value backwards (V27)",
                )
            )

    # Paired ACT side, on the SAME guard: a strictly newer reading is admitted.
    strictly_newer = stamp(feed="margin", as_of=_NOW, source_seq=11)
    admitted_newer = guard.admit(key, strictly_newer)
    if not (admitted_new and admitted_newer):
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:SourceMonotonicGuard.admit",
                "THE GUARD DISCARDS EVERYTHING: the first reading "
                f"(admitted={admitted_new}) and a strictly newer one "
                f"(admitted={admitted_newer}) were not both accepted. A guard "
                "that admits nothing never regresses and never updates, which "
                "is the useless half of safe",
            )
        )

    # Per-key isolation (§6.4b: 'a late update on one key can never regress
    # another'), and then the same property THROUGH the gate, past the tick.
    guard.admit("margin:NQ", stamp(feed="margin", as_of=_NOW - timedelta(seconds=900)))
    if guard.held(key).as_of != strictly_newer.as_of:
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:SourceMonotonicGuard",
                "A LATE UPDATE ON ONE KEY REGRESSED ANOTHER: after admitting a "
                "900 s-old stamp under 'margin:NQ', the held stamp for "
                f"{key!r} moved. §6.4b keys the guard per symbol for exactly "
                "this reason",
            )
        )

    tracker = _tracker(subject, values, _NOW)
    _observe(subject, tracker, {})
    feed = min(tracker.policy.feeds, key=tracker.policy.threshold_ms)
    later = _NOW + timedelta(milliseconds=SILENCE_MS)
    # Driving the INJECTED clock forward, which is the seam this detector
    # exposes precisely so 900 s of staleness needs no 900 s run.
    tracker._clock = lambda: later  # pylint: disable=protected-access
    port = subject.freshness.StalenessFlagPort(tracker)
    before = _gate_with(subject, staleness=port).evaluate(
        _order(subject), _picture(subject), 1000.0
    )
    late = tracker.observe(
        stamp(feed=feed, as_of=_NOW - timedelta(milliseconds=100), source_seq=0),
        DRIVE_SYMBOL,
    )
    after = _gate_with(subject, staleness=port).evaluate(
        _order(subject), _picture(subject), 1000.0
    )
    if late or after.decision is not subject.seam.Decision.DENY:
        findings.append(
            Finding(
                f"{REL_FRESHNESS}:FreshnessTracker.observe",
                f"A LATE READING UN-STALED A DEAD FEED: feed {feed!r} had been "
                f"silent {SILENCE_MS:.0f} ms (gate: {before.decision.value}); a "
                "reading carrying an OLD source instant then arrived, was "
                f"admitted={late}, and the gate answered "
                f"{after.decision.value} at {after.rule!r}. §6.4b orders by "
                "source-of-truth time, never by arrival time — a late packet "
                "must not refresh its own age",
            )
        )
    return findings, {
        "admitted": guard.admitted,
        "discarded_older": guard.discarded_older,
        "keys": list(guard.keys()),
        "deny_before_late_reading": before.decision.value,
        "deny_after_late_reading": after.decision.value,
    }


# R0914 (too-many-locals): four mirror states plus the transport replay,
# each held as its own reading so
# the finding can say WHICH one answered wrongly.
# pylint: disable=too-many-locals
def _arm_half_built(subject: _Subject) -> tuple[list[Finding], dict[str, Any]]:
    """MODE 3 — §12.7 / V31. A mirror mid-rebuild is STALE until the snapshot lands."""
    pic = subject.picture
    bus = subject.statebus
    mirror = bus.Mirror(required=(pic.TOPIC,))
    lens = pic.PictureMirror(_Sub(mirror), max_age_s=5.0, clock=lambda: 1000.0)
    findings: list[Finding] = []

    half_ok, half_why = lens.tradable()
    if half_ok:
        findings.append(
            Finding(
                f"{REL_PICTURE}:PictureMirror.tradable",
                "THE GATE SIZED ON A HALF-BUILT MIRROR: with NO snapshot yet "
                f"landed (missing={mirror.missing}, complete={mirror.complete}) "
                f"tradable() answered True ({half_why[:120]}). §12.7: 'mirror "
                "incomplete => treated as stale => fast-drop/deny until the "
                "snapshot lands', and it never sizes on a half-built mirror (V31)",
            )
        )

    # Traffic arrives that is NOT a snapshot. A delta applied to nothing
    # produces a table that looks whole and is not.
    mirror.apply(
        bus.StateMessage(
            topic=pic.TOPIC,
            seq=1,
            stamp=1000.0,
            payload=pic.encode_picture(_picture(subject, version=7)),
            snapshot=False,
        )
    )
    delta_ok, delta_why = lens.tradable()
    if delta_ok:
        findings.append(
            Finding(
                f"{REL_PICTURE}:PictureMirror.tradable",
                "A DELTA COMPLETED THE MIRROR: after one non-snapshot message "
                f"(applied={mirror.applied}, complete={mirror.complete}) "
                f"tradable() answered True ({delta_why[:120]}). A delta is a "
                "change to a table this consumer may never have seen; §12.7 "
                "completes a mirror on a SNAPSHOT and on nothing else",
            )
        )

    # The snapshot lands — the ACT side of this arm.
    mirror.apply(
        bus.StateMessage(
            topic=pic.TOPIC,
            seq=2,
            stamp=1000.0,
            payload=pic.encode_picture(_picture(subject, version=8)),
            snapshot=True,
        )
    )
    full_ok, full_why = lens.tradable()
    if not full_ok:
        findings.append(
            Finding(
                f"{REL_PICTURE}:PictureMirror.tradable",
                "THE MIRROR NEVER BECOMES SIZEABLE: a complete, in-date, "
                f"self-consistent snapshot (complete={mirror.complete}, "
                f"missing={mirror.missing}) still answered False — "
                f"{full_why[:200]}. A mirror that fast-drops forever is the "
                "denial-by-construction §7.12 asks about",
            )
        )

    # And it goes stale again once its own §12.7 stamp ages past the ceiling.
    aged = pic.PictureMirror(_Sub(mirror), max_age_s=5.0, clock=lambda: 1000.0 + 900.0)
    aged_ok, aged_why = aged.tradable()
    if aged_ok:
        findings.append(
            Finding(
                f"{REL_PICTURE}:PictureMirror.tradable",
                "A STALE MIRROR STAYED SIZEABLE: the held snapshot's own "
                "published_ts was 900 s behind the clock against a 5 s ceiling "
                f"and tradable() answered True ({aged_why[:120]}). §6.4's rule "
                "for a stale cache is refuse, never 'carry on with the last "
                "value'",
            )
        )

    # The transport's own no-regress guard, past the tick.
    applied_before = mirror.applied
    mirror.apply(
        bus.StateMessage(
            topic=pic.TOPIC,
            seq=1,
            stamp=1.0,
            payload=pic.encode_picture(_picture(subject, version=1, published_ts=1.0)),
            snapshot=True,
        )
    )
    replayed = lens.picture()
    if mirror.applied != applied_before or replayed is None or replayed.version != 8:
        findings.append(
            Finding(
                "scripts/nixbus/statebus.py:Mirror.apply",
                "THE MIRROR REGRESSED ON A REPLAYED SEQUENCE: a message at "
                f"seq=1 arriving after seq=2 was applied (applied "
                f"{applied_before} -> {mirror.applied}) and the mirrored "
                f"version is now {getattr(replayed, 'version', None)!r}, not 8. "
                "§6.4b's no-regress rule holds on the wire as well as at the "
                "poller",
            )
        )
    return findings, {
        "half_built": half_ok,
        "delta_only": delta_ok,
        "snapshot_landed": full_ok,
        "aged_past_ceiling": aged_ok,
        "out_of_order": mirror.out_of_order,
        "missing_named": half_why[:80],
    }


def _arm_mark(subject: _Subject) -> tuple[list[Finding], dict[str, Any]]:
    """§6.5's `(value, fresh)` pair — the one gate input carrying its own flag."""
    stale = _gate_with(subject, net_liq=_StaleMark()).evaluate(
        _order(subject), _picture(subject), 1000.0
    )
    fresh = _gate_with(subject).evaluate(_order(subject), _picture(subject), 1000.0)
    findings: list[Finding] = []
    if stale.decision is not subject.seam.Decision.DENY:
        findings.append(
            Finding(
                f"{REL_GATE}:SurvivalHeadroomRule.evaluate",
                "A STALE NET-LIQ MARK WAS ACTED ON: the port answered "
                f"(10_000_000.0, fresh=False) and the pass returned "
                f"{stale.decision.value} at {stale.rule!r}. §6.5 marks net-liq "
                "per tick off the price cache, so a mark whose feed stopped is "
                "a stale number that still reads as a comfortable figure; §17 "
                "— a safety property proven while its subject is unavailable "
                "is not proven",
            )
        )
    elif stale.rule != "survival_headroom":
        findings.append(
            Finding(
                f"{REL_GATE}:GatePass.evaluate",
                f"the stale net-liq mark was refused by {stale.rule!r}, not by "
                "the survival rule that reads it — a denial attributed to the "
                "wrong cause (§3: 'deny (rule named)')",
            )
        )
    if fresh.decision is not subject.seam.Decision.APPROVE:
        findings.append(
            Finding(
                f"{REL_GATE}:SurvivalHeadroomRule.evaluate",
                "THE FRESH MARK WAS ALSO REFUSED: (10_000_000.0, fresh=True) "
                f"produced {fresh.decision.value} at {fresh.rule!r}, so the "
                "stale arm above measures a rule that denies either way",
            )
        )
    return findings, {
        "stale_mark": f"{stale.decision.value}/{stale.rule}",
        "fresh_mark": f"{fresh.decision.value}/{fresh.rule}",
    }


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------


def _all_arms(
    subject: _Subject, values: dict, census: _Census
) -> tuple[list[Finding], list[str], dict[str, Any]]:
    findings: list[Finding] = []
    stats: dict[str, Any] = {}

    census_findings, unclassifiable, census_stats = _arm_census(census)
    findings.extend(census_findings)
    stats["ARM 1 census"] = census_stats

    # NON-VACUITY BEFORE EVERY DENY ARM. If the gate cannot act on a fresh
    # input, nothing below it means anything.
    act_findings, act_stats = _arm_act(subject, values)
    findings.extend(act_findings)
    stats["ARM 2 act-on-fresh"] = act_stats

    for label, fn in (
        ("ARM 3 stale", lambda: _arm_stale(subject, values)),
        ("ARM 4 out-of-order", lambda: _arm_order(subject, values)),
        ("ARM 5 half-built", lambda: _arm_half_built(subject)),
        ("ARM 6 net-liq mark", lambda: _arm_mark(subject)),
    ):
        arm_findings, arm_stats = fn()
        findings.extend(arm_findings)
        stats[label] = arm_stats
    stats["arms"] = 6
    return findings, unclassifiable, stats


def _floor_complaint(stats: dict[str, Any]) -> str:
    """Every FLOORS entry, checked against what was MEASURED. C.4."""
    census = stats.get("ARM 1 census", {})
    act = stats.get("ARM 2 act-on-fresh", {})
    measured = {
        "ports": census.get("ports", 0),
        "inputs": census.get("inputs", 0),
        "stamp_fields": census.get("stamp_fields", 0),
        "arms": stats.get("arms", 0),
        "feeds": act.get("feeds", 0),
        "rules_evaluated": act.get("evaluated", 0),
    }
    short = [
        f"{key}={measured[key]} < floor {floor}"
        for key, floor in FLOORS.items()
        if measured.get(key, 0) < floor
    ]
    if not short:
        return ""
    return (
        "the derivation found less than the shape it reads: "
        + "; ".join(short)
        + " — an empty derived set compares equal to an empty drive, so this is "
        "CANNOT_MEASURE and never a smaller PASS"
    )


def _verdict(
    findings: list[Finding], unclassifiable: list[str], stats: dict[str, Any]
) -> CheckResult:
    """Check contract rule 4: Fail > Cannot-measure > Pass. FAIL IS JUDGED FIRST.

    A positively-observed violation outranks a limit of the census, always. The
    ladder is written in this order and not in the order the arms ran, because
    a gate that answered CANNOT_MEASURE while holding a real finding would have
    withheld certification over a defect it had already seen — the exact
    inversion `check_hot_path_purity`, `check_two_phase_entry` and two more
    first-drafts got wrong before it was tested for.
    """
    if findings:
        return _fail(findings)
    complaint = _floor_complaint(stats)
    if complaint:
        return _cannot(complaint, site=REL_GATE)
    if unclassifiable:
        return _cannot(
            "UNCLASSIFIABLE GATE INPUT(S): "
            + "; ".join(unclassifiable)
            + ". §3's gate acts on this and the freshness census cannot say "
            "whether it carries a stamp, so no statement about 'every input' "
            "can be made. Classify it or give its port a return shape this "
            "census reads (§7.12: never guess in the permissive direction)",
            site=REL_GATE,
        )
    return CheckResult(
        name=NAME,
        status=Status.PASS,
        evidence=json.dumps(stats, default=str, sort_keys=True),
    )


def _measure(home: Path) -> CheckResult:
    absent = _absent(home)
    if absent is not None:
        return absent
    values, complaint = _config_values(home)
    if complaint:
        return _cannot(complaint, site=REL_CONFIG)
    census, census_complaint = _census(home)
    if census is None:
        return _cannot(census_complaint, site=REL_GATE)
    subject, load_complaint = load_subject(home)
    if subject is None:
        return _cannot(load_complaint, site=REL_GATE)
    findings, unclassifiable, stats = _all_arms(subject, values, census)
    return _verdict(findings, unclassifiable, stats)


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Prove the gate never acts on a bad input, and does act on a good one."""
    try:
        return _measure(Path(ctx.nix_home))
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1 —
        # exit 1 would report a violation this gate never observed.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# Deliberately duplicated across every checks/check_*.py: the check contract
# (§4.2) requires each module be independently runnable, so this block cannot be
# factored into a shared helper without breaking that.
# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(
        standalone_main(
            Path(__file__).resolve(),
            run,
            NAME,
        )
    )
