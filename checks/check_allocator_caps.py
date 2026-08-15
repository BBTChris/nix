#!/usr/bin/env python3
"""The bucket cap SUMS its bucket, and contention falls back to FCFS with no writer.

ONE gate, ONE property (`nix_check_contract.md` §5.5, doctrine C.9): *the
Allocator's two consumer-side rules behave as the frozen spec locks them —
`nics_risk_subsystem_spec_v1.3.md` §7:497-515's correlation-bucket cap and
§6.6:465-468's FCFS fallback — measured by DRIVING the shipped modules, never by
reading their source.* Seven arms serve that one property.

It is the instrument for §13 V35:949, transcribed rather than paraphrased:
*"prove within-bucket dollar risk is summed correctly (micros at 1/10), a
proposal that would breach `bucket_cap_pct × balance` is sized down then denied,
and positions in different buckets do NOT constrain each other through this rule
(only via the portfolio layers)."*

  * **ARM 1 — the cap's config loads, and its buckets are the SPEC's.** The
    ceiling table's keys are compared against the bucket names parsed out of
    §7:498's own locked sentence in the frozen document at run time. **No
    bucket name and no symbol -> bucket mapping enters this gate's EXECUTABLE
    code** — the suite asserts that by AST, over the string constants and the
    identifiers rather than over the prose — so ARM 1's reference side cannot
    be a transcription that drifted. (The contention arms DO name three
    symbols; they are arbitrary labels for a race, chosen so arrival order
    disagrees with the alphabet, and nothing about a bucket is read from them.)

  * **ARM 2 — THE SUMMATION, and it is the arm that matters.** A cap driven
    with ONE position per bucket cannot distinguish `sum()` from `max()`,
    because for one element they are equal — so this arm drives TWO same-bucket
    positions and a THIRD proposal against them, and asserts three things: the
    reported `used` equals the SUM, the sum differs from the `max()` of the two,
    and the admitted contract count differs from the count a `max()`-shaped cap
    would have admitted. The falsifier is COMPUTED HERE and required to
    disagree; if a future edit made the two answers coincide, the arm reports
    that it can no longer discriminate rather than passing on a case that
    proves nothing.

  * **ARM 3 — SAME-BUCKET ONLY, as a positive control (§7:505-510).** The same
    equities proposal is run twice: once alone, once beside an energy position
    an order of magnitude larger than the equities ceiling. Identical answers,
    or the cap is reaching across buckets — which §7:508 gives to the
    portfolio-wide layers (§6.5) and not to this rule.

  * **ARM 4 — size down TOWARD the ceiling, then deny at zero (§7:514).** Two
    cases, because they are two behaviours: a proposal with room for some of it
    must come back partially admitted with the bucket cap named as the binding
    constraint, and a proposal with room for not one contract must come back at
    zero. A cap that only ever denies passes the second and fails the first.

  * **ARM 5 — the FCFS fallback FIRES, in the state the system is actually in
    (§6.6:465-468).** Scoring is R5 and no writer for the ranking table exists,
    so "table absent" is not an error path, it is the live configuration. Three
    absent-shaped ports are driven — no port at all, a port reporting itself
    unavailable, and a port that RAISES — and each must return a deterministic
    FCFS ordering by ARRIVAL, naming its own reason, with no exception escaping.
    The contenders are built so arrival order disagrees with alphabetical order,
    because an FCFS answer that coincides with the alphabet proves nothing.

  * **ARM 6 — the READ seam is real rather than decorative.** A port carrying
    DIFFERENT live scores must move the ordering off arrival order, and a port
    carrying EQUAL scores must fall back to FCFS. Without the first, a module
    that ignored the port entirely would pass ARM 5 perfectly.

  * **ARM 7 — the authority boundary, BY ATTEMPT (§2:40, §6.6:459-460).** The
    Allocator reads the ranking to weight sizing; the LIMITER arbitrates. So
    this arm reaches for every award-shaped verb on the shipped contention
    module and requires each reach to come back empty, and requires the module
    to be free of coroutines — an `async def` on this path is a place a scoring
    outage could stall order flow, which §6.6:468 forbids by name.

`debug.md` §7.12 — WHAT WOULD HAVE TO BE TRUE FOR THIS GATE TO PASS WHILE
MEASURING NOTHING? Seven routes, each closed by a mechanism rather than by care:

 1. **The modules could be missing or unimportable**, and every arm skipped.
    CLOSED: CANNOT_MEASURE naming the exception (§17), never a PASS.
 2. **ARM 1's spec sentence could be renamed or moved**, leaving the regex
    matching nothing and an empty expected set comparing equal to an empty
    measured one. CLOSED: fewer than `MIN_CREDIBLE_BUCKETS` parsed buckets is
    CANNOT_MEASURE naming the anchor.
 3. **ARM 2 could be run on a case where `sum()` and `max()` agree**, which is
    every case with one position per bucket. CLOSED: the arm asserts
    `contributors >= MIN_SUMMED_EXPOSURES` and asserts the `max()`-shaped
    answer DIFFERS from the measured one before comparing anything; if it does
    not, the arm reports a discriminator failure.
 4. **ARM 5 could pass because FCFS happens to equal the input order, the
    alphabetical order and the score order at once.** CLOSED: the contenders
    are constructed so arrival order disagrees with alphabetical order, and the
    arm asserts that disagreement before it asserts the answer.
 5. **The whole gate could be measuring MOCKS instead of the shipped code.**
    CLOSED: every arm calls functions on modules imported by dotted name out of
    `ctx.nix_home/scripts`, and each imported module's `__file__` is compared
    back against the expected path before any arm runs. The only fakes are the
    ranking-table PORTS, which is the seam's declared boundary and the one
    thing that provably cannot be real (its writer does not exist).
 6. **An arm could be skipped by an earlier arm's exception**, leaving a green
    over six. CLOSED: the arms run unconditionally, each returns its own
    findings, and the evidence line states the arm count and the measured
    figures each arm produced.
 7. **The config could be empty**, so the cap has no symbols and every arm
    iterates nothing. CLOSED: `MIN_CAP_SYMBOLS` must be reached or the verdict
    is CANNOT_MEASURE (§5.3 — an empty scope is never a PASS).

WHAT THIS GATE CANNOT PROVE, stated rather than implied, because §6.6 is only
half-built and a green here must not read as coverage of the other half:

  * **It cannot prove anything about the Scoring process, the realized-P&L EMA,
    or performance-weighted contention in production.** That process is R5, its
    ranking table has NO WRITER, and the ports driven in ARMS 5-6 are fakes
    standing in for a publisher that does not exist. ARM 6 proves the READ is
    wired; it proves nothing about what will one day be read.
  * **It cannot prove the score -> sizing-weight transform**, because there is
    not one: §6.6:459 gives it to the Allocator and the spec fixes no transform,
    so `contention.rank` returns a neutral weight under both policies and says
    so. Deferred to R5 (CHECK-DEBT D3.132).
  * **It cannot prove arbitration.** §6.6:459-460 gives that to the Limiter.
    ARM 7 proves this module declares no verb that awards a shared resource; it
    does not prove the Limiter arbitrates correctly, which is the Limiter's own
    instrument to build.
  * **It cannot prove the cap runs on a live order path.** No Allocator process
    exists. Every arm calls the module directly.
"""

from __future__ import annotations

import ast
import importlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code
# §4.2 requires each checks/check_*.py be independently runnable and map
# status -> exit code identically, and doctrine B.2 requires the crash path
# return CANNOT_MEASURE in both. Those blocks are MANDATED to be the same text,
# as is the §7:498 bucket-sentence parse this gate shares with
# check_allocator_seam — both derive their reference side from the same locked
# sentence, and factoring it into a shared helper would make one gate's
# reference side depend on another gate's bytes.
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
DEPENDS_ON: tuple[str, ...] = ()
#: Imports first-party modules out of the tree under test and reads two files.
#: No socket, no subprocess, no write — the two entries are the interpreter
#: state this gate mutates and restores, declared so the mutation is visible.
RESOURCES: tuple[str, ...] = ("interpreter:sys.modules", "interpreter:sys.path")
#: A block halts on any member's failure; this gate's failure is a finding about
#: two modules, never a reason to stop measuring the rest of the tree.
ON_FAIL = "continue"
TIME_BOUND = False
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the reference side is the frozen risk spec -- §7:511's inequality and "
    "§6.6:465's locked fallback -- and the measured side is behaviour driven "
    "out of two shipped modules. There is no edit an instrument could make to "
    "either side that would not be manufacturing its own green: correcting the "
    "spec is forbidden outright, and correcting the modules is writing the "
    "implementation the gate exists to judge"
)
SUBJECTS: tuple[str, ...] = (
    "scripts/nixalloc/caps.py",
    "scripts/nixalloc/contention.py",
    "risks/allocator_caps.config.json",
)

NAME = "check_allocator_caps"

CAPS = "scripts/nixalloc/caps.py"
CONTENTION = "scripts/nixalloc/contention.py"
CAPS_CONFIG = "risks/allocator_caps.config.json"
SPEC = "docs/nics_risk_subsystem_spec_v1.3.md"

#: §7:498's locked bucket sentence, anchored on its bolded label so a renamed or
#: moved sentence is a loud CANNOT_MEASURE rather than an empty expected set
#: silently agreeing with an empty measured one (§7.12/2).
_BUCKET_SENTENCE = re.compile(r"\*\*Buckets:\*\*(?P<body>.*?)\(static", re.DOTALL)
#: One bucket inside that sentence: `equities {ES, NQ}`.
_BUCKET_ENTRY = re.compile(r"([A-Za-z]+)\s*\{([^}]*)\}")

#: Non-vacuity floors. Each is a FLOOR, anchored below today's figures on
#: purpose: a threshold equal to the current count is a moving anchor that
#: reddens the moment a symbol or a bucket lands (`debug.md` §7.4).
MIN_CREDIBLE_BUCKETS = 3
MIN_CAP_SYMBOLS = 4
#: ARM 2's discriminator floor. TWO is the whole point: at one exposure a sum
#: and a maximum are the same number, so an arm that summed one thing measured
#: nothing about summation.
MIN_SUMMED_EXPOSURES = 2

#: ARM 7. Verb stems whose presence on the Allocator's contention module would
#: be it awarding a shared resource — the authority §6.6:459-460 gives to the
#: Limiter. Spelled here because the reference side is the authority split
#: itself, which is prose in §2 rather than a parsable table; the can-fail suite
#: plants each one in turn and requires a finding naming it.
_AWARD_VERBS = (
    "award",
    "winner",
    "win",
    "grant",
    "allocate",
    "assign",
    "arbitrate",
    "settle",
    "reserve",
    "commit",
    "claim",
)

#: The dotted names imported out of the tree under test, with the path each one
#: must resolve to. A name-based import against a `sys.path` the preamble has
#: already seeded with the REAL repository would measure the live tree whatever
#: `ctx.nix_home` said — the defect `check_d1_12_reboot_capture`'s first draft
#: shipped, and the reason each `__file__` is compared back.
_MODULES = (
    ("nixalloc.seam", "scripts/nixalloc/seam.py"),
    ("nixalloc.caps", CAPS),
    ("nixalloc.contention", CONTENTION),
)


class Finding(NamedTuple):
    """One divergence. `site` names WHERE, `why` names the reason (§18)."""

    site: str
    why: str


@dataclass(frozen=True)
class Driven:
    """Everything an arm needs, imported and loaded out of the tree under test."""

    seam: ModuleType
    caps: ModuleType
    contention: ModuleType
    #: `nixalloc.caps.CapConfig` from the tree under test. Typed `Any` because
    #: the class is imported at RUN TIME out of `ctx.nix_home`, so no static
    #: name in this file can refer to it — the whole point of driving the
    #: shipped bytes rather than the ones this gate was linted against.
    config: Any
    home: Path


# ---------------------------------------------------------------------------
# Fake ranking-table ports. The ONE thing in this gate that is not the shipped
# code, and it is the one thing that provably cannot be: §6.6's writer is the
# Scoring process, which is R5 and does not exist.
# ---------------------------------------------------------------------------


class _AbsentTable:
    """A port that reports itself unavailable. The R3-A steady state."""

    def available(self) -> bool:
        """§6.6:465 — the Scoring process is down or its table is stale."""
        return False

    def row(self, strategy_id: str, symbol: str) -> None:
        """Never reached when `available()` is honoured, and that is the point."""
        raise AssertionError(
            f"rank() read row({strategy_id!r}, {symbol!r}) after available() "
            "returned False — the fallback consulted a table it was told was "
            "absent"
        )


class _RaisingTable:
    """A port that throws. §6.6:467-468: an outage must never halt order flow."""

    def available(self) -> bool:
        """The failure mode a just-died publisher actually presents."""
        raise RuntimeError("scoring shared-memory segment is gone")

    def row(self, strategy_id: str, symbol: str) -> None:
        """Unreachable; declared so the port satisfies the seam's shape."""
        raise RuntimeError(f"unreachable: {strategy_id}/{symbol}")


class _ScoredTable:
    """A port carrying live rows. Built per test from an explicit score map."""

    def __init__(self, rows: dict[tuple[str, str], object]) -> None:
        self._rows = rows

    def available(self) -> bool:
        """Live."""
        return True

    def row(self, strategy_id: str, symbol: str) -> object | None:
        """§6.6:463's O(1) lookup, never math."""
        return self._rows.get((strategy_id, symbol))


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _purge(prefixes: tuple[str, ...]) -> None:
    """Drop already-imported first-party modules so `home` wins the import."""
    for name in [k for k in sys.modules if k.split(".")[0] in prefixes]:
        del sys.modules[name]


def load(home: Path) -> tuple[Driven | None, str]:
    """Import both modules out of `home` and load the cap config, or say why not."""
    for rel in (CAPS, CONTENTION, CAPS_CONFIG, SPEC):
        if not (home / rel).is_file():
            return None, (
                f"{rel}: no such file under {home} — the subject is "
                "unavailable, so nothing was measured (§17: never a PASS)"
            )
    saved_path = list(sys.path)
    saved_modules = dict(sys.modules)
    try:
        sys.path.insert(0, str((home / "scripts").resolve()))
        _purge(("nixalloc", "nixrisk", "risk_config"))
        loaded: dict[str, ModuleType] = {}
        for dotted, rel in _MODULES:
            module = importlib.import_module(dotted)
            got = Path(getattr(module, "__file__", "") or "").resolve()
            want = (home / rel).resolve()
            if got != want:
                return None, f"{dotted} resolved to {got}, not {want}"
            loaded[dotted] = module
        caps = loaded["nixalloc.caps"]
        return (
            Driven(
                seam=loaded["nixalloc.seam"],
                caps=caps,
                contention=loaded["nixalloc.contention"],
                config=caps.load_cap_config(home),
                home=home,
            ),
            "",
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{CAPS}/{CONTENTION}: cannot load out of {home} — "
            f"{type(exc).__name__}: {exc}. Nothing was measured (§17)"
        )
    finally:
        sys.path[:] = saved_path
        for key in [k for k in sys.modules if k not in saved_modules]:
            del sys.modules[key]
        sys.modules.update(saved_modules)


def spec_buckets(home: Path) -> tuple[dict[str, str], str]:
    """`({symbol: bucket_name}, complaint)` parsed from §7:498's locked sentence."""
    match = _BUCKET_SENTENCE.search((home / SPEC).read_text(encoding="utf-8"))
    if match is None:
        return {}, (
            f"{SPEC}: the §7 '**Buckets:**' sentence did not match its anchor — "
            "an unmatched anchor yields an EMPTY expected set, which would "
            "compare equal to an empty measured one and report agreement"
        )
    found: dict[str, str] = {}
    for bucket, members in _BUCKET_ENTRY.findall(match.group("body")):
        for symbol in (part.strip() for part in members.split(",")):
            if symbol:
                found[symbol] = bucket.lower()
    if len(set(found.values())) < MIN_CREDIBLE_BUCKETS:
        return {}, (
            f"{SPEC}: parsed {len(set(found.values()))} bucket(s) from the §7 "
            f"sentence, below the credibility floor of {MIN_CREDIBLE_BUCKETS}"
        )
    return found, ""


# ---------------------------------------------------------------------------
# ARM 1 — the config loads and its buckets are the spec's
# ---------------------------------------------------------------------------


def _arm_config(driven: Driven) -> tuple[list[Finding], str]:
    """The ceiling table covers exactly §7:498's buckets, parsed from the spec."""
    expected, complaint = spec_buckets(driven.home)
    if complaint:
        return [], complaint
    config = driven.config
    declared = set(getattr(config, "bucket_cap_pct", {}))
    symbols = set(getattr(config, "tick_value_usd", {}))
    if len(symbols) < MIN_CAP_SYMBOLS:
        return [], (
            f"{CAPS_CONFIG}: tick_value_usd carries {len(symbols)} symbol(s), "
            f"below the floor of {MIN_CAP_SYMBOLS} — a cap over a nearly empty "
            "symbol table passes trivially (§5.3)"
        )
    findings: list[Finding] = []
    if declared != set(expected.values()):
        findings.append(
            Finding(
                "risks/allocator.config.json:bucket_cap_pct",
                f"the ceiling table's buckets disagree with §7:498's locked "
                f"sentence. spec={sorted(set(expected.values()))} "
                f"config={sorted(declared)}",
            )
        )
    uncovered = sorted(set(expected) - symbols)
    if uncovered:
        findings.append(
            Finding(
                f"{CAPS_CONFIG}:tick_value_usd",
                f"§7:498 buckets {uncovered} and this table has no tick value "
                "for them — the cap over those symbols would be computed "
                "against a number that does not exist",
            )
        )
    return findings, ""


# ---------------------------------------------------------------------------
# ARM 2 — THE SUMMATION (§7:511, §13 V35:949)
# ---------------------------------------------------------------------------


def _shared_bucket_pair(driven: Driven) -> tuple[str, str] | None:
    """Two DIFFERENT symbols the spec puts in ONE bucket, derived not typed."""
    expected, _ = spec_buckets(driven.home)
    by_bucket: dict[str, list[str]] = {}
    for symbol, bucket in sorted(expected.items()):
        by_bucket.setdefault(bucket, []).append(symbol)
    for members in by_bucket.values():
        if len(members) >= MIN_SUMMED_EXPOSURES:
            return members[0], members[1]
    return None


def _arm_summation(driven: Driven) -> tuple[list[Finding], str]:
    """TWO same-bucket positions, and the third proposal capped against their SUM.

    The falsifier is computed here: `max()` of the two exposures is the classic
    wrong implementation, and this arm requires the two answers to DISAGREE
    before it reports on either. A case where they agree is a case that proves
    nothing, and it is reported as an instrument failure rather than a pass.
    """
    pair = _shared_bucket_pair(driven)
    if pair is None:
        return [], (
            f"{SPEC}: no bucket holds {MIN_SUMMED_EXPOSURES} symbols, so a "
            "same-bucket SUM cannot be driven at all — with one exposure per "
            "bucket, sum() and max() are the same number"
        )
    first, second = pair
    caps = driven.caps
    exposures = [
        caps.Exposure(symbol=first, contracts=2, stop_ticks=20),
        caps.Exposure(symbol=second, contracts=3, stop_ticks=20),
    ]
    each = [caps.dollar_risk(exposure, driven.config) for exposure in exposures]
    decision = caps.admit(first, 5, 20, exposures, 100_000.0, driven.config)
    findings = _summation_findings(decision, each)
    return findings, ""


def _summation_findings(decision: Any, each: list[float]) -> list[Finding]:
    """The three assertions ARM 2 makes, each naming its own reason."""
    site = f"{CAPS}:admit"
    total, largest = sum(each), max(each)
    used = float(getattr(decision, "used_dollar_risk", -1.0))
    contributors = int(getattr(decision, "contributors", 0))
    per = float(getattr(decision, "per_contract_dollar_risk", 0.0))
    ceiling = float(getattr(decision, "ceiling_dollar_risk", 0.0))
    if contributors < MIN_SUMMED_EXPOSURES:
        return [
            Finding(
                site,
                f"summed {contributors} exposure(s), below the discriminator "
                f"floor of {MIN_SUMMED_EXPOSURES} — at one exposure sum() and "
                "max() are equal and this arm measures nothing about summation",
            )
        ]
    if _fits(ceiling, largest, per) == _fits(ceiling, total, per):
        return [
            Finding(
                site,
                f"the case no longer DISCRIMINATES: a sum-based cap and a "
                f"max-based cap both admit {_fits(ceiling, total, per)} "
                f"contract(s) here (per-contract {per}, ceiling {ceiling}, sum "
                f"{total}, max {largest}). The arm is reporting an instrument "
                "failure rather than a pass over a case that proves nothing",
            )
        ]
    findings: list[Finding] = []
    if abs(used - total) > 1e-9:
        findings.append(
            Finding(
                site,
                f"reported same-bucket used dollar risk {used}, and the SUM of "
                f"its {contributors} same-bucket exposures is {total} "
                f"(individually {each}). §7:511 sums the bucket; the largest "
                f"single member is {largest}",
            )
        )
    admitted = int(getattr(decision, "admitted_contracts", -1))
    if admitted != _fits(ceiling, total, per):
        findings.append(
            Finding(
                site,
                f"admitted {admitted} contract(s); §7:511 applied to the SUM "
                f"admits {_fits(ceiling, total, per)}. A max()-shaped cap would "
                f"have admitted {_fits(ceiling, largest, per)} — the two "
                "disagree here, which is what makes this case a measurement",
            )
        )
    return findings


def _fits(ceiling: float, used: float, per: float) -> int:
    """How many contracts §7:511 leaves room for. The gate's own arithmetic.

    Written out here rather than called out of the module under test: an arm
    that asked the subject how many contracts fit and then checked the subject
    against that answer would be the subject agreeing with itself.
    """
    headroom = ceiling - used
    return int(headroom // per) if headroom > 0 and per > 0 else 0


# ---------------------------------------------------------------------------
# ARM 3 — SAME-BUCKET ONLY, as a positive control (§7:505-510)
# ---------------------------------------------------------------------------


def _other_bucket_symbol(driven: Driven, avoid: str) -> str | None:
    """A symbol the spec puts in a DIFFERENT bucket from `avoid`."""
    expected, _ = spec_buckets(driven.home)
    home_bucket = expected.get(avoid)
    for symbol, bucket in sorted(expected.items()):
        if bucket != home_bucket:
            return symbol
    return None


def _arm_cross_bucket(driven: Driven) -> tuple[list[Finding], str]:
    """A huge position in another bucket must not shrink this proposal."""
    pair = _shared_bucket_pair(driven)
    if pair is None:
        return [], f"{SPEC}: no multi-symbol bucket, so ARM 3 has no subject"
    first, _ = pair
    foreign = _other_bucket_symbol(driven, first)
    if foreign is None:
        return [], f"{SPEC}: every symbol is in one bucket, so ARM 3 has no control"
    caps = driven.caps
    alone = caps.admit(first, 3, 20, [], 100_000.0, driven.config)
    huge = [caps.Exposure(symbol=foreign, contracts=500, stop_ticks=200)]
    beside = caps.admit(first, 3, 20, huge, 100_000.0, driven.config)
    if int(alone.admitted_contracts) != int(beside.admitted_contracts):
        return [
            Finding(
                f"{CAPS}:admit",
                f"a {foreign} position of {caps.dollar_risk(huge[0], driven.config)} "
                f"dollars of risk changed the {first} answer from "
                f"{alone.admitted_contracts} to {beside.admitted_contracts} "
                "contract(s). §7:505-510 makes the cap SAME-BUCKET ONLY: "
                "cross-bucket exposure is bounded by the §6.5 portfolio layers, "
                "not by this rule",
            )
        ], ""
    if int(beside.contributors) != 0:
        return [
            Finding(
                f"{CAPS}:bucket_dollar_risk",
                f"summed {beside.contributors} exposure(s) into bucket "
                f"{beside.bucket.value} while the only position on the book is "
                f"{foreign} — the bucket filter is not filtering",
            )
        ], ""
    return [], ""


# ---------------------------------------------------------------------------
# ARM 4 — size down toward the ceiling, then deny at zero (§7:514)
# ---------------------------------------------------------------------------


def _arm_size_down(driven: Driven) -> tuple[list[Finding], str]:
    """A partial fit is admitted partially; a no-fit is denied at zero."""
    pair = _shared_bucket_pair(driven)
    if pair is None:
        return [], f"{SPEC}: no multi-symbol bucket, so ARM 4 has no subject"
    first, _ = pair
    caps = driven.caps
    config = driven.config
    per = caps.per_contract_dollar_risk(first, 20, config)
    bucket = caps.bucket_for(first)
    if bucket is None:
        return [], f"{SPEC}: §7:498 gives {first} no bucket, so ARM 4 has no ceiling"
    ceiling_pct = float(dict(config.bucket_cap_pct)[bucket.value])
    findings: list[Finding] = []
    # Balance chosen so the ceiling carries exactly 3 contracts of a 5-lot ask.
    balance = (per * 3.5) / ceiling_pct
    partial = caps.admit(first, 5, 20, [], balance, config)
    findings += _partial_findings(partial, first)
    # Balance chosen so the ceiling cannot carry even one contract.
    denied = caps.admit(first, 5, 20, [], (per * 0.5) / ceiling_pct, config)
    if int(denied.admitted_contracts) != 0:
        findings.append(
            Finding(
                f"{CAPS}:admit",
                f"admitted {denied.admitted_contracts} contract(s) against a "
                f"ceiling of {denied.ceiling_dollar_risk} that will not carry "
                f"one contract at {denied.per_contract_dollar_risk} — §7:514 "
                "denies at zero rather than rounding up to the smallest "
                "tradeable size",
            )
        )
    return findings, ""


def _partial_findings(partial: Any, symbol: str) -> list[Finding]:
    """§7:514's 'size-down toward the ceiling' half, asserted on its own."""
    admitted = int(getattr(partial, "admitted_contracts", -1))
    proposed = int(getattr(partial, "proposed_contracts", -1))
    binding = getattr(getattr(partial, "binding", None), "value", "?")
    if not 0 < admitted < proposed:
        return [
            Finding(
                f"{CAPS}:admit",
                f"{symbol}: proposed {proposed} against a ceiling with room for "
                f"part of it and got {admitted} — §7:514 sizes DOWN toward the "
                "ceiling and only then denies at zero, so an all-or-nothing cap "
                "is the wrong rule even when it is the safe one",
            )
        ]
    if binding != "bucket_cap":
        return [
            Finding(
                f"{CAPS}:admit",
                f"{symbol}: the cap shrank {proposed} to {admitted} and named "
                f"binding constraint {binding!r} — §16 U5 requires the sizing "
                "rationale to name WHICH term bound, and a rationale that does "
                "not name the cap makes the audit trail wrong about the reason",
            )
        ]
    return []


# ---------------------------------------------------------------------------
# ARM 5 — the FCFS fallback fires (§6.6:465-468)
# ---------------------------------------------------------------------------


def _contenders(driven: Driven) -> list[Any]:
    """Three contenders whose ARRIVAL order disagrees with their alphabet.

    §7.12/4: an FCFS answer that coincides with alphabetical order proves
    nothing, so the arrival sequence is deliberately the reverse of the
    symbols' sort order and the arm asserts that disagreement before it
    asserts the answer.
    """
    contender = driven.contention.Contender
    return [
        contender(strategy_id="s2", symbol="GC", arrival_seq=1),
        contender(strategy_id="s3", symbol="ZN", arrival_seq=2),
        contender(strategy_id="s1", symbol="CL", arrival_seq=3),
    ]


def _arm_fcfs(driven: Driven) -> tuple[list[Finding], str]:
    """Absent, unavailable and raising ports all reach ONE deterministic answer."""
    contenders = _contenders(driven)
    arrival = tuple(c.symbol for c in contenders)
    if arrival in (tuple(sorted(arrival)), tuple(sorted(arrival, reverse=True))):
        return [], (
            "the ARM 5 contenders arrive in alphabetical order (ascending or "
            "descending), so an FCFS answer would be indistinguishable from an "
            "alphabetical one (§7.12/4) — the arm refuses rather than "
            "measuring nothing"
        )
    findings: list[Finding] = []
    for label, table in (
        ("no port at all (Scoring is R5 and does not exist)", None),
        ("a port reporting itself unavailable", _AbsentTable()),
        ("a port that RAISES from its availability probe", _RaisingTable()),
    ):
        findings += _fcfs_case(driven, contenders, arrival, label, table)
    return findings, ""


def _fcfs_case(
    driven: Driven,
    contenders: list[Any],
    arrival: tuple[str, ...],
    label: str,
    table: Any,
) -> list[Finding]:
    """One absent-shaped port, driven. Never an exception, never a stall."""
    site = f"{CONTENTION}:rank"
    try:
        ranking = driven.contention.rank(contenders, table)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return [
            Finding(
                site,
                f"raised {type(exc).__name__}: {exc} with {label}. §6.6:467-468 "
                "makes ranking an optimization and never a safety gate: a "
                "scoring outage must NEVER halt order flow, and an exception "
                "escaping onto the order path is exactly that halt",
            )
        ]
    got = tuple(c.symbol for c in ranking.ordering)
    if ranking.policy is not driven.seam.ContentionPolicy.FCFS:
        return [
            Finding(
                site,
                f"chose policy {ranking.policy.value!r} with {label} — "
                "§6.6:465's fallback is LOCKED for an absent or stale table",
            )
        ]
    if got != arrival:
        return [
            Finding(
                site,
                f"ordered {got} with {label}; arrival order is {arrival}. "
                "§6.6:466 makes the fallback first-come-first-served and "
                "structurally neutral — it favours no symbol",
            )
        ]
    if not (ranking.reason or "").strip():
        return [
            Finding(
                site,
                f"fell back with {label} and named no reason — §18 requires the "
                "REASON, and three different outages reaching one ordering are "
                "distinguishable only by it",
            )
        ]
    return []


# ---------------------------------------------------------------------------
# ARM 6 — the READ seam is real rather than decorative (§6.6:453-455)
# ---------------------------------------------------------------------------


def _rows(driven: Driven, contenders: list[Any], scores: list[float]) -> Any:
    """A live ranking table over the given contenders."""
    row = driven.seam.RankingRow
    return _ScoredTable(
        {
            c.pair: row(
                strategy_id=c.strategy_id, symbol=c.symbol, score=score, as_of=0.0
            )
            for c, score in zip(contenders, scores, strict=True)
        }
    )


def _arm_read_seam(driven: Driven) -> tuple[list[Finding], str]:
    """DIFFERENT scores must move the ordering; EQUAL scores must fall back."""
    contenders = _contenders(driven)
    arrival = tuple(c.symbol for c in contenders)
    site = f"{CONTENTION}:rank"
    findings: list[Finding] = []
    # Scores chosen so the resulting order is none of the arrival order, the
    # alphabetical order, or its reverse — an ordering that coincides with any
    # of those would be reachable without ever reading the port.
    live = driven.contention.rank(
        contenders, _rows(driven, contenders, [1.0, 3.0, 2.0])
    )
    got = tuple(c.symbol for c in live.ordering)
    if got == arrival:
        findings.append(
            Finding(
                site,
                f"a table with DISTINCT scores {[1.0, 3.0, 2.0]} produced the "
                f"arrival ordering {got} unchanged — the READ seam is "
                "decorative, and a module that never called the port at all "
                "would be indistinguishable from this one",
            )
        )
    if live.policy is not driven.seam.ContentionPolicy.PERFORMANCE_WEIGHTED:
        findings.append(
            Finding(
                site,
                f"a table with distinct live scores produced policy "
                f"{live.policy.value!r} — §6.6:433 chooses by recent realized "
                "productivity when the table is there to choose from",
            )
        )
    equal = driven.contention.rank(contenders, _rows(driven, contenders, [1.5] * 3))
    if equal.policy is not driven.seam.ContentionPolicy.FCFS:
        findings.append(
            Finding(
                site,
                f"a table whose scores are all equal produced policy "
                f"{equal.policy.value!r} — §6.6:455 makes EQUAL scores an FCFS "
                "case, which is the cold-start state by construction",
            )
        )
    elif tuple(c.symbol for c in equal.ordering) != arrival:
        findings.append(
            Finding(
                site,
                f"equal scores fell back to FCFS and ordered "
                f"{tuple(c.symbol for c in equal.ordering)} rather than the "
                f"arrival order {arrival}",
            )
        )
    return findings, ""


# ---------------------------------------------------------------------------
# ARM 7 — the authority boundary, BY ATTEMPT (§2:40, §6.6:459-460)
# ---------------------------------------------------------------------------


def _arm_boundary(driven: Driven) -> tuple[list[Finding], str]:
    """No award verb on the module, and no coroutine anywhere in it."""
    findings = [
        Finding(
            f"{CONTENTION}:{name}",
            f"the Allocator's contention module exposes {name!r}, whose stem "
            f"is the award verb {stem!r}. §6.6:459-460 gives the Allocator the "
            "READ ('to weight sizing') and the LIMITER the arbitration ('when "
            "a shared resource can't satisfy every proposal'); §2:40 makes the "
            "Allocator permissive. A verb that awards a shared resource here is "
            "the authority split crossed in the one direction it may not be",
        )
        for name in dir(driven.contention)
        if not name.startswith("__")
        for stem in _AWARD_VERBS
        if _carries(name, stem)
    ]
    source = (driven.home / CONTENTION).read_text(encoding="utf-8")
    findings += [
        Finding(
            f"{CONTENTION}:{node.name}",
            "declared `async def` — §6.6:468 forbids a scoring outage halting "
            "order flow, and a coroutine on this path is a declared suspension "
            "point between a GO and its proposal",
        )
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.AsyncFunctionDef)
    ]
    return findings, ""


def _carries(name: str, stem: str) -> bool:
    """Whole word or leading stem, so `award` and `award_capital` both hit."""
    lowered = name.lstrip("_").lower()
    return lowered == stem or lowered.startswith(f"{stem}_")


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------

ARMS = 7

_ARMS = (
    _arm_config,
    _arm_summation,
    _arm_cross_bucket,
    _arm_size_down,
    _arm_fcfs,
    _arm_read_seam,
    _arm_boundary,
)


def _evidence(driven: Driven) -> str:
    """What was actually driven, in figures rather than adjectives."""
    config = driven.config
    return (
        f"{ARMS} arms driving the SHIPPED {CAPS} and {CONTENTION} out of "
        f"{driven.home}: §7:511's cap summed over "
        f"{MIN_SUMMED_EXPOSURES}+ same-bucket exposures with the max()-shaped "
        "falsifier computed here and required to DISAGREE; a cross-bucket "
        "positive control; size-down and deny-at-zero as two separate cases; "
        "§6.6:465's FCFS fallback fired against three absent-shaped ports "
        "(none, unavailable, raising) on contenders whose arrival order "
        "disagrees with their alphabet; the read seam proven non-decorative by "
        "distinct scores moving the ordering and equal scores falling back; "
        f"{len(_AWARD_VERBS)} award verbs reached for BY ATTEMPT and all "
        f"absent; buckets parsed from {SPEC} §7:498 at run time with none "
        f"spelled in this gate; {len(dict(config.tick_value_usd))} symbol(s) "
        f"and {len(dict(config.bucket_cap_pct))} bucket ceiling(s) loaded"
    )


def _drive(driven: Driven) -> tuple[list[Finding], list[str]]:
    """Run EVERY arm unconditionally and collect both halves of each answer.

    Unconditionally, and each arm returning its own pair, is §7.12/6: an arm
    that could be skipped by an earlier arm's exception would leave a green
    standing over six measurements while the evidence line claimed seven.
    """
    findings: list[Finding] = []
    unmeasured: list[str] = []
    for arm in _ARMS:
        try:
            arm_findings, complaint = arm(driven)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            # MEASURED, not defensive: a `bucket_cap_pct` key renamed in
            # `risks/` makes the cap raise, and without this the FIRST arm to
            # touch it would abort the other six and the gate would report
            # CANNOT_MEASURE over a real, nameable defect. An arm that throws
            # IS a finding about its subject, and it names which arm.
            findings.append(
                Finding(
                    f"{CAPS}:{arm.__name__}",
                    f"the arm raised {type(exc).__name__}: {exc} — a rule that "
                    "cannot be driven at all is a finding about the rule, and "
                    "the remaining arms still ran",
                )
            )
            continue
        findings += arm_findings
        if complaint:
            unmeasured.append(complaint)
    return findings, unmeasured


def _verdict(
    driven: Driven, findings: list[Finding], unmeasured: list[str]
) -> CheckResult:
    """Turn the arms' answers into one status. §5.3: an empty scope never passes."""
    if unmeasured and not findings:
        return CheckResult(
            name=NAME, status=Status.CANNOT_MEASURE, detail="; ".join(unmeasured)
        )
    evidence = _evidence(driven)
    if not findings:
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    detail = "; ".join(f"{site}: {why}" for site, why in findings)
    if unmeasured:
        detail = f"{detail}. ALSO UNMEASURED: {'; '.join(unmeasured)}"
    return CheckResult(
        name=NAME,
        status=Status.FAIL_NEEDS_OPERATOR,
        site="; ".join(site for site, _ in findings),
        evidence=evidence,
        detail=detail,
    )


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Drive all seven arms against the modules under `ctx.nix_home`."""
    try:
        driven, error = load(ctx.nix_home)
        if driven is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        findings, unmeasured = _drive(driven)
        return _verdict(driven, findings, unmeasured)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        # Doctrine B.2: a gate that crashed measured nothing. Exit 2, never 1.
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
