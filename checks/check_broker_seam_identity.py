#!/usr/bin/env python3
"""SEAM IDENTITY — the broker-order port and sink are EXACTLY their rosters.

ONE gate, ONE property: Module 2 invariant **B1** (risk spec §2A:103-104
invariant 1). *"Every adapter claiming `BrokerOrderPort` exposes EXACTLY the
nine `ORDER_PORT_VERBS` — no fewer AND NO MORE — with matching signatures;
every sink exposes exactly the seven `ORDER_EVENTS`."*

WHY A NEW GATE IS OWED (ARC 059 recon, measured — not inferred):

  (a) `broker_seam.check_structural_conformance()` reports MISSING verbs only.
      It is **superset-blind**: a Protocol carrying ten verbs the roster never
      names passes it, so "identical" has never been provable on this tree.
  (b) It has **no empty-roster vacuity guard**. Its sibling
      `check_await_conformance()` grew one (debug.md §7.12 condition A); the
      structural one did not, so `verbs=()` returns `[]` — a clean-looking
      pass over nothing.
  (c) **No signature/arity comparison exists anywhere in the tree.** Verified:
      no `inspect` use compares a port verb's parameters against an adapter's.
      `callable()` is the whole of today's test, and `callable()` cannot tell
      `place_order(self, order)` from `place_order(self)`.

SCOPE FENCE — READ THIS BEFORE CITING THIS GATE. This discharges B1 **for the
IBKR signature only**. It proves that the ONE shipped adapter is set-identical
and shape-identical to the port it claims. It does **NOT** prove cross-vendor
identity: that property needs a second adapter (N=2) so the two can be held
against each other, and is explicitly OUT OF SCOPE here — a later arc, M2-F.
A green here is "the IBKR adapter is the port"; it is not "any vendor's
adapter is the port".

§7.12 — WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING?

 1. **AN EMPTY ROSTER** (condition A, failure mode #2). `set() == set()` is
    true, and every loop below would run zero times. This is the exact hole
    `check_structural_conformance` still has. CLOSED: ARM 1 refuses — an empty
    `ORDER_PORT_VERBS`, an empty `ORDER_EVENTS`, or a Protocol declaring no
    public members is a FAIL naming which one, and can never be a PASS.
 2. **INTROSPECTING A STUB INSTEAD OF THE ADAPTER** (§7.12 instance 7's
    cousin: the instrument measures a thing shaped like the subject). The seam
    file ships `StubBrokerOrder` and `HollowBrokerOrder`, both of which satisfy
    the roster by construction; a gate that reached for either would be green
    forever. CLOSED: ARM 1 asserts the loaded class's `__name__` is
    `IBKRBrokerOrder`, its `__module__` is the real `broker_order_ibkr`, and
    the module's `__file__` resolves inside `<home>/scripts/broker/`. If the
    real adapter cannot be loaded the verdict is CANNOT_MEASURE (§17), never
    a PASS on a stand-in.
 3. **A HARDCODED EXPECTED-MEMBER LIST.** A gate holding its own copy of "the
    nine verbs" measures its own literal, and goes stale the day the contract
    moves (debug.md §7.4, the moving anchor). CLOSED: ARM 2 derives the
    Protocol's members by INTROSPECTION (`__dict__` + `__annotations__` across
    the Protocol's own MRO), so the two sides of the comparison come from two
    independent places in the source and neither is typed here.
 4. **A HARDCODED EXPECTED-SIGNATURE TABLE** (D3.426, the same defect one
    level down). CLOSED: ARM 4 derives the expected parameter SHAPE from
    `inspect.signature(getattr(BrokerOrderPort, verb))` — the Protocol itself.
    No signature is spelled out in this file.
 5. **SUBSET-ONLY COMPARISON.** Checking only that every roster verb exists is
    what the tree already does, and it admits a superset. CLOSED: ARM 2 is a
    SET EQUALITY in both directions — MISSING and EXTRA are separate, separately
    named findings.
 6. **AN UNINSPECTABLE VERB SILENTLY SKIPPED.** `inspect.signature()` raises
    for C-implemented and some wrapped callables; a `try/except: continue`
    would convert the one verb that could not be checked into a PASS.
    CLOSED: ARM 5 escalates ANY such raise to CANNOT_MEASURE for the WHOLE
    gate, naming the verb and the exception (check-rule 10: a property proven
    while its subject is unavailable is not proven).
 7. **THE GATE MUTATING THE SUBJECT TO GO GREEN.** CLOSED: `CORRECTABLE =
    False`. This gate reads and never writes; see `NON_CORRECTABLE_REASON`.
 8. **IMPORT SIDE-EFFECTS LEAKING.** The adapter imports `broker_order_config`
    under a FLAT module name, so both `scripts/` and `scripts/broker/` go on
    `sys.path`. A gate that left them there would change what every later check
    in the run imports. CLOSED: `load()` saves and restores `sys.path` and the
    three module entries in a `finally`.
"""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path
from types import ModuleType
from typing import Generic, NamedTuple, Protocol

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = False
DEPENDS_ON: tuple[str, ...] = ()
RESOURCES: tuple[str, ...] = (
    "interpreter:sys.modules",
    "interpreter:sys.path",
)
#: NON-CORRECTABLE: the divergences this gate finds are contract edits — a verb
#: added to a port, a parameter renamed, an event dropped. Each is a decision
#: about what §2A's broker-order seam CONTAINS.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "every defect this gate can find is a disagreement about what the "
    "broker-order contract contains — a roster, a Protocol member, or a "
    "parameter list. An instrument that rewrote an adapter's signatures, or "
    "edited the roster, until the two sides matched would be REDEFINING the "
    "seam to make itself green: doctrine B.4's forbidden direction, and the "
    "one repair that destroys the evidence of the divergence it was hiding"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/broker/broker_seam.py",
    "scripts/broker/broker_order_ibkr.py",
)

NAME = "check_broker_seam_identity"

SEAM_MODULE = "broker_seam"
ADAPTER_MODULE = "broker_order_ibkr"
CONFIG_MODULE = "broker_order_config"
MODULES = (SEAM_MODULE, ADAPTER_MODULE, CONFIG_MODULE)
PACKAGE_DIRS = ("scripts", "scripts/broker")
ADAPTER_CLASS = "IBKRBrokerOrder"
SEAM_FILE = "scripts/broker/broker_seam.py"
ADAPTER_FILE = "scripts/broker/broker_order_ibkr.py"

#: Bases that contribute typing machinery rather than contract members.
_MACHINERY = (object, Protocol, Generic)

Finding = tuple[str, str]


class Loaded(NamedTuple):
    """The two real modules, imported from the tree under measurement."""

    seam: ModuleType
    adapter: ModuleType


def _purge(saved: dict[str, ModuleType]) -> None:
    for name in MODULES:
        sys.modules.pop(name, None)
    sys.modules.update(saved)


def load(home: Path) -> tuple[Loaded | None, str]:
    """Import the seam and the IBKR adapter from `home`, restoring the interpreter.

    `broker_order_ibkr` imports `broker_order_config` as a FLAT module name, so
    BOTH package dirs must be on `sys.path` (measured — one is not enough).
    """
    saved_path = list(sys.path)
    saved_modules = {key: value for key, value in sys.modules.items() if key in MODULES}
    for name in MODULES:
        sys.modules.pop(name, None)
    for rel in PACKAGE_DIRS:
        sys.path.insert(0, str((home / rel).resolve()))
    importlib.invalidate_caches()
    try:
        seam = importlib.import_module(SEAM_MODULE)
        adapter = importlib.import_module(ADAPTER_MODULE)
        return Loaded(seam=seam, adapter=adapter), ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{ADAPTER_FILE}: cannot import {SEAM_MODULE}/{ADAPTER_MODULE} from "
            f"{home} — {type(exc).__name__}: {exc}. The subject is unavailable, "
            "so nothing was measured (§17 / check-rule 10: never a PASS)"
        )
    finally:
        sys.path[:] = saved_path
        _purge(saved_modules)


def declared_members(proto: type) -> frozenset[str]:
    """The PUBLIC members a Protocol actually declares — BY INTROSPECTION.

    Walks the Protocol's own MRO, skipping the typing machinery, and unions each
    class's `__dict__` and `__annotations__`. Deliberately NOT
    `__protocol_attrs__`: that set is frozen when the class object is created,
    so a member attached afterwards is invisible to it — and "a member nobody
    declared in the class body" is precisely the superset case this gate exists
    to catch.
    """
    names: set[str] = set()
    for klass in proto.__mro__:
        if klass in _MACHINERY:
            continue
        names |= {name for name in vars(klass) if not name.startswith("_")}
        names |= {
            name
            for name in getattr(klass, "__annotations__", {})
            if not name.startswith("_")
        }
    return frozenset(names)


def _shape(sig: inspect.Signature) -> tuple[tuple[str, str, bool], ...]:
    """Parameter shape: ordered (name, kind, has_default), `self` excluded."""
    return tuple(
        (param.name, param.kind.name, param.default is not inspect.Parameter.empty)
        for param in sig.parameters.values()
        if param.name != "self"
    )


# --------------------------------------------------------------------------
# ARM 1 — VACUITY + REAL-SUBJECT GUARD
# --------------------------------------------------------------------------


def _vacuity_rosters(seam: object) -> list[Finding]:
    """STEP of `arm_vacuity`, NOT A SECOND GATE. The two rosters are non-empty.

    Split out for the same reason `broker_seam._partition_divergences` was: the
    arm crossed the tree's cognitive-complexity ceiling, and decomposition
    changes no verdict on any input while raising a ceiling to admit code is
    doctrine B.4's forbidden direction. Nothing calls this and reports a
    result; it has no exit code and no independent meaning.
    """
    findings: list[Finding] = []
    if not tuple(getattr(seam, "ORDER_PORT_VERBS", ()) or ()):
        findings.append(
            (
                f"{SEAM_FILE}:ORDER_PORT_VERBS",
                (
                    "VACUOUS: the order-port roster is EMPTY — every set comparison "
                    "below would compare nothing and report agreement (debug.md "
                    "§7.12 condition A, failure mode #2)"
                ),
            )
        )
    if not tuple(getattr(seam, "ORDER_EVENTS", ()) or ()):
        findings.append(
            (
                f"{SEAM_FILE}:ORDER_EVENTS",
                (
                    "VACUOUS: the order-event roster is EMPTY — the sink's identity "
                    "would be proven against nothing (debug.md §7.12 condition A)"
                ),
            )
        )
    return findings


def _vacuity_protocols(seam: object) -> list[Finding]:
    """STEP of `arm_vacuity`, NOT A SECOND GATE. Both Protocols declare members."""
    findings: list[Finding] = []
    for attr in ("BrokerOrderPort", "OrderEventSink"):
        proto = getattr(seam, attr, None)
        if proto is None:
            findings.append(
                (
                    f"{SEAM_FILE}:{attr}",
                    (
                        f"{attr} is not declared by the seam module — the port this "
                        "gate measures against does not exist"
                    ),
                )
            )
            continue
        if not declared_members(proto):
            findings.append(
                (
                    f"{SEAM_FILE}:{attr}",
                    (
                        f"VACUOUS: {attr} declares NO public members — a roster "
                        "compared against an empty Protocol agrees with it about "
                        "nothing (debug.md §7.12 condition A)"
                    ),
                )
            )
    return findings


def _vacuity_real_subject(loaded: Loaded, home: Path) -> list[Finding]:
    """STEP of `arm_vacuity`, NOT A SECOND GATE. The subject is the REAL class.

    Returns UNMEASURABLE findings: a stub, a proxy, or a class imported from
    outside the tree the gate was pointed at is §17's *subject unavailable*,
    which is CANNOT_MEASURE and never a PASS.
    """
    unmeasurable: list[Finding] = []
    klass = getattr(loaded.adapter, ADAPTER_CLASS, None)
    if klass is None:
        unmeasurable.append(
            (
                f"{ADAPTER_FILE}:{ADAPTER_CLASS}",
                (
                    f"the real adapter class {ADAPTER_CLASS} is absent from "
                    f"{ADAPTER_MODULE} — there is no subject to introspect (§17)"
                ),
            )
        )
        return unmeasurable
    if klass.__name__ != ADAPTER_CLASS or not klass.__module__.endswith(ADAPTER_MODULE):
        unmeasurable.append(
            (
                f"{ADAPTER_FILE}:{ADAPTER_CLASS}",
                (
                    f"the class bound to {ADAPTER_CLASS} reports "
                    f"{klass.__module__}.{klass.__name__} — this is NOT the real "
                    "adapter, and a stub or proxy satisfies the roster by "
                    "construction (§7.12 answer 2)"
                ),
            )
        )
    origin = Path(getattr(loaded.adapter, "__file__", "") or "")
    expected = (home / "scripts" / "broker").resolve()
    if not origin or origin.resolve().parent != expected:
        unmeasurable.append(
            (
                f"{ADAPTER_FILE}:__file__",
                (
                    f"{ADAPTER_MODULE} was imported from {origin or '<unknown>'}, "
                    f"not from {expected} — the gate cannot show it introspected "
                    "the tree it was pointed at (§17)"
                ),
            )
        )
    return unmeasurable


def arm_vacuity(loaded: Loaded, home: Path) -> tuple[list[Finding], list[Finding]]:
    """(findings, unmeasurable). An empty roster is NEVER a pass.

    Composed of three STEPS above, each of which is a step and not a verdict.
    """
    findings = _vacuity_rosters(loaded.seam) + _vacuity_protocols(loaded.seam)
    return findings, _vacuity_real_subject(loaded, home)


def arm_set_equality(loaded: Loaded) -> list[Finding]:
    """Roster == Protocol members, BOTH directions. Missing AND extra."""
    findings: list[Finding] = []
    pairs = (
        ("ORDER_PORT_VERBS", "BrokerOrderPort", "verb"),
        ("ORDER_EVENTS", "OrderEventSink", "event"),
    )
    for roster_name, proto_name, noun in pairs:
        proto = getattr(loaded.seam, proto_name, None)
        if proto is None:
            continue
        roster = frozenset(getattr(loaded.seam, roster_name, ()) or ())
        members = declared_members(proto)
        for name in sorted(roster - members):
            findings.append(
                (
                    f"{SEAM_FILE}:{proto_name}",
                    (
                        f"MISSING {noun} {name!r}: {roster_name} names it but "
                        f"{proto_name} does not declare it — the roster and the "
                        "Protocol disagree about what the contract contains"
                    ),
                )
            )
        for name in sorted(members - roster):
            findings.append(
                (
                    f"{SEAM_FILE}:{proto_name}",
                    (
                        f"EXTRA {noun} {name!r}: {proto_name} declares it but "
                        f"{roster_name} does not name it — the port is a STRICT "
                        "SUPERSET of its roster, so 'exactly these' is false "
                        "(§2A:103-104 invariant 1)"
                    ),
                )
            )
    return findings


# --------------------------------------------------------------------------
# ARM 3 — IMPLEMENTED
# --------------------------------------------------------------------------


def arm_implemented(loaded: Loaded) -> list[Finding]:
    """Every roster verb is present and callable on the REAL adapter class."""
    findings: list[Finding] = []
    klass = getattr(loaded.adapter, ADAPTER_CLASS, None)
    if klass is None:
        return findings
    for verb in getattr(loaded.seam, "ORDER_PORT_VERBS", ()) or ():
        attr = getattr(klass, verb, None)
        if attr is None:
            findings.append(
                (
                    f"{ADAPTER_FILE}:{ADAPTER_CLASS}",
                    (
                        f"MISSING verb {verb!r}: ORDER_PORT_VERBS names it but "
                        f"{ADAPTER_CLASS} does not implement it — the adapter "
                        "claims a port it does not satisfy"
                    ),
                )
            )
        elif not callable(attr):
            findings.append(
                (
                    f"{ADAPTER_FILE}:{ADAPTER_CLASS}",
                    (
                        f"NON-CALLABLE verb {verb!r}: {ADAPTER_CLASS}.{verb} is "
                        f"{type(attr).__name__}, not a callable"
                    ),
                )
            )
    return findings


# --------------------------------------------------------------------------
# ARM 4 + ARM 5 — SIGNATURE SHAPE, DERIVED; UNINSPECTABLE => CANNOT_MEASURE
# --------------------------------------------------------------------------


def arm_signatures(loaded: Loaded) -> tuple[list[Finding], list[Finding]]:
    """(findings, unmeasurable). The expected shape comes from the PROTOCOL."""
    findings: list[Finding] = []
    unmeasurable: list[Finding] = []
    proto = getattr(loaded.seam, "BrokerOrderPort", None)
    klass = getattr(loaded.adapter, ADAPTER_CLASS, None)
    if proto is None or klass is None:
        return findings, unmeasurable
    for verb in getattr(loaded.seam, "ORDER_PORT_VERBS", ()) or ():
        want = getattr(proto, verb, None)
        got = getattr(klass, verb, None)
        if want is None or got is None:
            # Already reported by ARM 2 / ARM 3 with the name; not re-reported.
            continue
        shapes: list[tuple[str, inspect.Signature]] = []
        for side, target in (("BrokerOrderPort", want), (ADAPTER_CLASS, got)):
            try:
                shapes.append((side, inspect.signature(target)))
            except (ValueError, TypeError) as exc:
                unmeasurable.append(
                    (
                        f"{SEAM_FILE}:{verb}",
                        (
                            f"inspect.signature({side}.{verb}) raised "
                            f"{type(exc).__name__}: {exc} — the verb "
                            f"{verb!r} is UNINSPECTABLE (a C-implemented or "
                            "otherwise opaque callable), so its shape was not "
                            "compared. Skipping it would turn one unmeasured verb "
                            "into a PASS (check-rule 10)"
                        ),
                    )
                )
        if len(shapes) != 2:
            continue
        # Indexed rather than destructured: the `len(...) != 2` guard above is
        # invisible to static analysis, which reads the unpack as unbalanced.
        want_sig = shapes[0][1]
        got_sig = shapes[1][1]
        if _shape(want_sig) != _shape(got_sig):
            findings.append(
                (
                    f"{ADAPTER_FILE}:{ADAPTER_CLASS}.{verb}",
                    (
                        f"SIGNATURE MISMATCH on verb {verb!r}: BrokerOrderPort "
                        f"declares {verb}{want_sig}, {ADAPTER_CLASS} implements "
                        f"{verb}{got_sig} — the parameter shape (name, kind, "
                        "default) differs, so a caller written against the port "
                        "does not call the adapter"
                    ),
                )
            )
    return findings, unmeasurable


# --------------------------------------------------------------------------


def _evidence(loaded: Loaded) -> str:
    seam = loaded.seam
    verbs = tuple(getattr(seam, "ORDER_PORT_VERBS", ()) or ())
    events = tuple(getattr(seam, "ORDER_EVENTS", ()) or ())
    port_members = declared_members(getattr(seam, "BrokerOrderPort", object))
    sink_members = declared_members(getattr(seam, "OrderEventSink", object))
    return (
        f"B1/IBKR: introspected the REAL {ADAPTER_MODULE}.{ADAPTER_CLASS} against "
        f"{SEAM_FILE}'s Protocols. ORDER_PORT_VERBS={len(verbs)} vs "
        f"BrokerOrderPort's {len(port_members)} declared members (set equality, "
        f"both directions); ORDER_EVENTS={len(events)} vs OrderEventSink's "
        f"{len(sink_members)}; {len(verbs)} verbs present and callable on the "
        f"adapter; {len(verbs)} parameter shapes derived from the Protocol and "
        "compared. Cross-vendor identity is OUT OF SCOPE (needs N=2 adapters, "
        "arc M2-F)"
    )


def _verdict(
    loaded: Loaded, findings: list[Finding], unmeasurable: list[Finding]
) -> CheckResult:
    """STEP of `run`, NOT A SECOND GATE — it renders, it does not measure.

    Aggregation order is the check contract's: Cannot-measure outranks Fail
    outranks Pass, so an unmeasurable subject withholds the verdict even when
    findings were also collected — and those findings are still NARRATED, so a
    CANNOT_MEASURE never silently swallows what was seen.
    """
    evidence = _evidence(loaded)
    if unmeasurable:
        detail = "; ".join(f"{site}: {why}" for site, why in unmeasurable)
        if findings:
            detail += "; ALSO (measured, but the verdict is unmeasurable): "
            detail += "; ".join(f"{site}: {why}" for site, why in findings)
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site="; ".join(site for site, _ in unmeasurable),
            detail=detail,
        )
    if findings:
        return CheckResult(
            name=NAME,
            status=Status.FAIL_NEEDS_OPERATOR,
            site="; ".join(site for site, _ in findings),
            evidence=evidence,
            detail="; ".join(f"{site}: {why}" for site, why in findings),
        )
    return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Measure B1 for the IBKR signature. Never corrects."""
    try:
        for rel in (SEAM_FILE, ADAPTER_FILE):
            if not (ctx.nix_home / rel).is_file():
                return CheckResult(
                    name=NAME,
                    status=Status.CANNOT_MEASURE,
                    site=rel,
                    detail=f"{rel} is absent — nothing to introspect (§17)",
                )
        loaded, error = load(ctx.nix_home)
        if loaded is None:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site=ADAPTER_FILE,
                detail=error,
            )

        findings, unmeasurable = arm_vacuity(loaded, ctx.nix_home)
        findings += arm_set_equality(loaded)
        findings += arm_implemented(loaded)
        sig_findings, sig_unmeasurable = arm_signatures(loaded)
        findings += sig_findings
        unmeasurable += sig_unmeasurable

        return _verdict(loaded, findings, unmeasurable)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            site=SEAM_FILE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
