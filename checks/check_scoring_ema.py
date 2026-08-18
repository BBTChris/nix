#!/usr/bin/env python3
"""§6.6's realized-P&L EMA: realized only, per DAY, smoothed on a DERIVED span.

Seven arms, and each exists because it has a way of failing that leaves every
other arm green. The subject is `scripts/nixscore/ema.py`.

## 1. THE SPAN IS DERIVED FROM CONFIG, NOT CARVED

§6.6:442-445: *"EMA span = variable `SCORE_EMA_SPAN_DAYS`, default 10 trading
days, tunable — calibrated on the box once real realized data exists; NOT a
carved constant."* A scorer with `span = 10` in its source computes the RIGHT
NUMBER TODAY, because 10 is also what the config says. It is only wrong the day
an operator tunes the knob, and on that day nothing complains: the config
changes, the smoothing does not, and the operator concludes the span does not
matter. So the arm reads the module's AST for a numeric literal bound to a
span-shaped name, AND drives the engine from two written configs to prove the
value on disk actually reaches the arithmetic. Either half alone is passable by
the defect: a carved constant survives a driven test that never changes the
config, and a config-driven test passes over a module that reads the config and
then ignores it.

## 2. UNREALIZED CANNOT REACH THE NUMBER

§6.6:433-436: *"Realized P&L only — closed trades. Unrealized/paper gains never
steer capital."* Two doors — the event TYPE (a `filled` row is an open position)
and the FIELD NAME (a payload carrying a mark alongside a realization). Both are
driven, and both are driven again through a module whose ban has been PLANTED
OUT, so the arm demonstrates the defect rather than asserting its absence.

## 3. IT RANKS COMPLETED DECISIONS, NOT ACTIVITY

§6.6:438-439: *"Advances per DAY — one realized number per symbol per day (keeps
symbols comparable; a hyperactive symbol can't dominate purely by trading more
often)."* This is a claim about a COMPARISON, so one pair cannot test it. Two
contrasts are driven:

  * few-large against many-tiny, where the close COUNTS disagree with the
    ranking by twenty to one — and the arm asserts that disagreement, because a
    ranking that happens to agree with activity proves nothing about which axis
    produced it;
  * spike-then-silence against steady, with IDENTICAL total realized P&L and
    IDENTICAL close counts, which a sum cannot separate and a per-day EMA must.

## 4. AN ABSENT DAY IS A ZERO ADVANCE, AND THE EMA APPLIES IT

The engine's documented choice. It is checked as ARITHMETIC — a pair silent for
N grid days must equal `advance × (1-α)^N` to the bit — and not as "the number
went down", because a number that goes down is also what a rounding bug does.

The DAY GRID is checked in the same arm: Friday to Monday is ONE step, and a
calendar grid over the same closes gives a measurably different answer. §6.6
says *trading* days, and a calendar walk folds two extra zeros every weekend.

## 5. THE CLASSIFICATION IS TOTAL OVER THE SCHEMA'S OWN ENUM

`REALIZING_EVENT_TYPES | NON_REALIZING_EVENT_TYPES` is compared against
`plane1_event_enum` in `databases/schema/plane1.sql`, in both directions. A type
added to the schema by a later arc must be a loud miss here, not a silent
default — the defect `nixrisk.plane1_sink`'s totality test caught across two
branches in ARC 035.

## 6. THIN DATA CLAIMS NOTHING IT HAS NOT MEASURED

§6.6:445-447's own caution. `days_observed` must count REAL realized days and
not the calendar span, because the calendar span counts silence as evidence —
and a consumer reading a rank has no other defence against a one-sample score.

## Non-vacuity and both halves

Every arm that scans asserts it had a subject. Every arm that judges is driven
against a PLANTED copy of the module, exec'd in memory from mutated source, and
an arm that cannot show itself reddening is reported CANNOT_MEASURE rather than
PASS. Nothing is ever planted on the shipped file (doctrine C.8).

## What this gate does NOT prove

That any score is computed in production. Nothing constructs a
`RealizedEmaEngine`, no Scoring daemon exists, and — measured, not assumed —
**nothing in this tree writes `realized_pnl` into a Plane-1 payload**, so the
engine's input is empty on the real box. See `scripts/nixscore/ema.py`'s
docstring and the CHECK-DEBT rows this arc filed.
"""

# C0302 (too-many-lines) disabled for the reason `check_limiter_gate`,
# `check_blackout_windows` and `check_calendar_schema` already state at this
# site: a check is a STANDALONE executable (§4.2), so its arms, its plants and
# its non-vacuity floors live in one file by contract. Splitting this one across
# modules would move the can-fail controls away from the arms they bind and make
# `verify.py`'s static declaration reader (§4.4) unable to see the whole gate.
# pylint: disable=too-many-lines
# pylint: disable=duplicate-code
# R0801 pairs this module's §4.4 declaration preamble with every other check.
# THE DUPLICATION CANNOT BE FACTORED OUT AND THAT IS THE DESIGN: `PRIVILEGE`,
# `DEPENDS_ON`, `RESOURCES` and the rest are read STATICALLY, by AST, without
# importing the check (check contract §4.4), so a shared base module would be
# invisible to that reader.
from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import json
import re
import shutil
import sys
import tempfile
import types
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code

PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: Nothing must run first. This gate imports the engine and drives it in-process.
DEPENDS_ON: tuple[str, ...] = ()
#: A temp directory (the two written configs the span arm drives), plus the
#: interpreter surfaces every importing check touches. Declared rather than
#: minimised: `check_observed_resource_claims` compares declarations against
#: OBSERVED claims and the observer is right (§17).
RESOURCES: tuple[str, ...] = (
    "file-write:/tmp",
    "interpreter:sys.modules",
    "interpreter:sys.path",
)
#: The artifacts this gate MEASURES, for `check_artifact_gate_coverage`.
#: `ema.py` alone: it is parsed, exec'd in mutated copies, and driven here.
#: `scripts/nixscore/__init__.py` is NOT claimed — `check_scoring_seam` already
#: owns it, and a second claim would be the duplicate instrument doctrine C.9
#: forbids rather than a second measurement.
SUBJECTS: tuple[str, ...] = ("scripts/nixscore/ema.py",)
#: FALSE on the facts: one AST parse, a handful of in-memory module compiles and
#: a few thousand float operations.
TIME_BOUND = False
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "Every finding here is a judgement about what the score MEANS — a span that "
    "ignores its config, a mark that steers capital, a ranking that measures "
    "activity, a decay that does not decay. There is no mechanical edit that "
    "repairs any of them without deciding what the arithmetic was FOR, and an "
    "automated rewrite of the function that decides which strategy gets the "
    "last of the liquidity is not a repair. A human edits it."
)
INSTALLABLE = False
ON_FAIL = "continue"

NAME = "check_scoring_ema"

EMA_MODULE = "scripts/nixscore/ema.py"
SCHEMA_FILE = "databases/schema/plane1.sql"
SCORING_CONFIG = "risks/scoring.config.json"

#: Names that MEAN "the EMA span". A numeric literal bound to one of these in
#: the engine is §6.6's carved constant, whatever the config says.
SPAN_NAMES = frozenset(
    {"span", "span_days", "score_ema_span_days", "ema_span", "default_span"}
)

#: The two spans arm 1 writes and drives. Both are whole and positive, so
#: `risk_config`'s own boot rules accept them, and they are far enough apart
#: that a single day of decay separates them well outside float noise.
SPAN_A = 3
SPAN_B = 20

#: Float tolerance for a closed-form comparison. The arm asserts an arithmetic
#: identity, so the tolerance is for representation and nothing else.
TOL = 1e-9


class PlantFailed(RuntimeError):
    """A plant's anchor was not found. The arm is blind, never quietly green."""


@dataclasses.dataclass(frozen=True)
class Finding:
    """One defect, anchored to the site that carries it and the reason (§18)."""

    site: str
    why: str


# ---------------------------------------------------------------------------
# Loading the subject, and planting copies of it
# ---------------------------------------------------------------------------


def _load_ema(home: Path) -> tuple[Any, str]:
    """Import the engine from `home`, or return (None, error)."""
    scripts = str(home / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    try:
        from nixscore import ema  # pylint: disable=import-outside-toplevel

        return ema, ""
    except ImportError as exc:
        return None, f"cannot import nixscore.ema from {scripts}: {exc!r}"


def plant(source: str, edits: Sequence[tuple[str, str]], name: str) -> Any:
    """A MUTATED COPY of the engine, compiled in memory. Never on disk.

    Raises `PlantFailed` when any anchor is absent, which is the whole reason
    this is a function: a plant whose `str.replace` matched nothing produces a
    pristine module, the arm finds no defect, and the arm's silence is read as
    proof it can fail. That is the exact shape of a blind control.
    """
    for old, _new in edits:
        if old not in source:
            raise PlantFailed(
                f"plant anchor {old[:60]!r} is not in {EMA_MODULE} — the "
                "mutation did not apply, so the 'broken' subject is the shipped "
                "one and the control would be measuring nothing"
            )
    for old, new in edits:
        source = source.replace(old, new, 1)
    module = types.ModuleType(name)
    module.__dict__["__file__"] = f"<plant {name}>"
    code = compile(source, f"<plant {name}>", "exec")
    # REGISTERED FOR THE DURATION OF THE EXEC AND REMOVED AGAIN. `dataclasses`
    # resolves a field's annotation through `sys.modules[cls.__module__]`, so a
    # module that is not there raises while the FIRST `@dataclass` in the plant
    # is being built — the plant would fail for a reason that has nothing to do
    # with the defect it carries. Removed in `finally` so the interpreter is
    # left as it was found and no later import can pick up a mutated engine.
    sys.modules[name] = module
    try:
        # pylint: disable=exec-used
        exec(code, module.__dict__)  # noqa: S102  # nosec B102 - see below
    finally:
        sys.modules.pop(name, None)
    # B102: this IS the both-halves control. The source is the repository's own
    # `scripts/nixscore/ema.py`, read from disk, with ONE documented textual
    # substitution applied in memory. It is never written to disk, never entered
    # into `sys.modules`, and the anchor's presence is asserted above. The
    # alternative — planting the defect on the shipped file — is what doctrine
    # C.8 forbids.
    return module


# ---------------------------------------------------------------------------
# ARM 1a — the span is not a carved constant (AST)
# ---------------------------------------------------------------------------


def _numeric(node: ast.AST | None) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    )


def _binding_names(node: ast.AST) -> list[str]:
    """Every plain name a statement binds, for the span-shape test."""
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    return []


def carved_span_defects(source: str) -> tuple[list[Finding], int]:
    """A numeric literal bound to a span-shaped name. Returns (findings, seen).

    `seen` counts the span-shaped bindings inspected — a scan that found no
    span-shaped name at all judged nothing, and the caller treats that as
    vacuous rather than clean.
    """
    findings: list[Finding] = []
    seen = 0
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [Finding(EMA_MODULE, f"cannot parse: {exc}")], 0
    for node in ast.walk(tree):
        findings += _default_defects(node)
        seen += len([n for n in _binding_names(node) if n.lower() in SPAN_NAMES])
        findings += _assign_defects(node)
    seen += _span_arg_count(tree)
    return findings, seen


def _assign_defects(node: ast.AST) -> list[Finding]:
    """A span-shaped assignment whose value is a number."""
    value = getattr(node, "value", None)
    if not _numeric(value):
        return []
    literal = getattr(value, "value", None)
    return [
        Finding(
            f"{EMA_MODULE}:{name}",
            f"binds the literal {literal!r} to a span-shaped name. §6.6:445: "
            "the span is 'calibrated on the box once real realized data exists; "
            "NOT a carved constant'. A carved span computes the right number "
            f"until the day {SCORING_CONFIG} is tuned, and then it computes the "
            "old one in silence",
        )
        for name in _binding_names(node)
        if name.lower() in SPAN_NAMES
    ]


def _default_defects(node: ast.AST) -> list[Finding]:
    """A span-shaped PARAMETER with a numeric default — a carved span with a door."""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return []
    args = node.args
    names = [a.arg for a in (*args.posonlyargs, *args.args)]
    paired = list(zip(names[len(names) - len(args.defaults) :], args.defaults))
    paired += [
        (a.arg, d) for a, d in zip(args.kwonlyargs, args.kw_defaults) if d is not None
    ]
    return [
        Finding(
            f"{EMA_MODULE}:{node.name}({arg}=)",
            f"defaults a span-shaped parameter to {getattr(default, 'value', None)!r}. "
            "A default is a carved constant every caller that omits the "
            "argument gets, and the caller that omits it is the one nobody "
            "reviewed",
        )
        for arg, default in paired
        if arg.lower() in SPAN_NAMES and _numeric(default)
    ]


def _span_arg_count(tree: ast.AST) -> int:
    """Span-shaped PARAMETERS in the module — the other half of non-vacuity."""
    total = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            every = (*args.posonlyargs, *args.args, *args.kwonlyargs)
            total += len([a for a in every if a.arg.lower() in SPAN_NAMES])
    return total


def span_ast_arm_can_fail() -> tuple[bool, str]:
    """Drive the AST arm over a carved span and a clean one. Both halves."""
    carved, seen = carved_span_defects("span_days = 10\n")
    if not carved or seen != 1:
        return False, (
            f"`span_days = 10` produced {len(carved)} finding(s) over {seen} "
            "span-shaped binding(s) — the arm cannot see a carved span"
        )
    clean, clean_seen = carved_span_defects("span: int\ndef f(span: int) -> int: ...\n")
    if clean or clean_seen != 2:
        return False, (
            f"an un-valued annotation and a bare parameter produced "
            f"{[f.why for f in clean]} over {clean_seen} binding(s) — the arm "
            "flags everything, which is the same blindness pointed the other way"
        )
    defaulted, _ = carved_span_defects("def f(*, span: int = 10) -> int: ...\n")
    if not defaulted:
        return False, "a `span: int = 10` default produced no finding"
    return True, ""


# ---------------------------------------------------------------------------
# ARM 1b — the config on disk actually reaches the arithmetic
# ---------------------------------------------------------------------------


def _write_root(home: Path, base: Path, span: int) -> Path:
    """A complete `risks/` tree under `base`, with `scoring`'s span set."""
    root = base / f"root-{span}"
    shutil.copytree(home / "risks", root / "risks")
    path = root / SCORING_CONFIG
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["score_ema_span_days"] = span
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return root


def _demo_closes(ema: Any, days: int = 6) -> list[Any]:
    """One pair, `days` grid days, a realized close on the FIRST day only.

    First day only on purpose: the whole difference between two spans is how
    fast the silence that follows erodes the number, so a history that keeps
    topping the pair up would shrink the very gap this arm measures.
    """
    grid = grid_days(dt.date(2026, 8, 3), days)
    return [
        ema.RealizedClose(
            strategy_id="s1",
            symbol="ES",
            day=grid[0],
            realized=1000.0,
            event_type="closed",
            trade_id="t1",
        )
    ]


def span_config_defects(ema: Any, home: Path) -> list[Finding]:
    """Two written configs, two engines, and the numbers they actually produce."""
    findings: list[Finding] = []
    closes = _demo_closes(ema)
    through = grid_days(dt.date(2026, 8, 3), 6)[-1]
    scores: dict[int, float] = {}
    with tempfile.TemporaryDirectory(prefix="check-scoring-ema-") as tmp:
        for span in (SPAN_A, SPAN_B):
            root = _write_root(home, Path(tmp), span)
            engine = ema.RealizedEmaEngine.from_config(root)
            if engine.span != span:
                findings.append(
                    Finding(
                        f"{EMA_MODULE}:RealizedEmaEngine.from_config",
                        f"{SCORING_CONFIG} declared score_ema_span_days={span} and "
                        f"the engine built from it reports span={engine.span}. The "
                        "knob is not the span",
                    )
                )
            scores[span] = engine.score(closes, through)[("s1", "ES")].realized_ema
    findings += _span_effect_defects(scores, len(closes))
    return findings


def _span_effect_defects(scores: dict[int, float], subjects: int) -> list[Finding]:
    """The two spans must produce DIFFERENT smoothing over the same history."""
    if subjects == 0:
        return [
            Finding(
                f"{NAME}:non-vacuity",
                "the span arm smoothed an EMPTY close set — two spans agree "
                "trivially over no history, and the comparison proves nothing",
            )
        ]
    short, long = scores.get(SPAN_A), scores.get(SPAN_B)
    if short is None or long is None:
        return [Finding(f"{NAME}:non-vacuity", "a span drive produced no score")]
    if abs(short - long) <= TOL:
        return [
            Finding(
                f"{EMA_MODULE}:ema_over_days",
                f"spans {SPAN_A} and {SPAN_B} produced the SAME score "
                f"({short!r}) over the same realized history. The span is being "
                "read and then ignored — which is what a carved constant looks "
                "like from outside, and the AST arm alone would miss it because "
                "the number is genuinely loaded from config",
            )
        ]
    if short >= long:
        return [
            Finding(
                f"{EMA_MODULE}:alpha_for",
                f"a {SPAN_A}-day span left MORE of a one-off advance "
                f"({short!r}) after silence than a {SPAN_B}-day span "
                f"({long!r}). A shorter span must fade faster; this ordering "
                "means alpha and span are inverted, and every operator tuning "
                "the knob would move the smoothing the wrong way",
            )
        ]
    return []


# ---------------------------------------------------------------------------
# ARM 2 — unrealized cannot reach the number
# ---------------------------------------------------------------------------


def _row(day: dt.date, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """One synthetic `plane1_event_log` row."""
    return {
        "event_id": 1,
        "event_type": event_type,
        "strategy_id": "s1",
        "symbol": "ES",
        "trade_id": "t1",
        "occurred_at": f"{day.isoformat()} 15:00:00+00",
        "payload": payload,
    }


def _refusal(ema: Any, row: dict[str, Any]) -> tuple[str, str]:
    """Drive one row through the fold. Returns `(exception name, message)`."""
    try:
        ema.realized_closes([row])
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return type(exc).__name__, str(exc)
    return "", ""


def leak_defects(ema: Any) -> list[Finding]:
    """Every door an unrealized figure could come through, driven."""
    day = grid_days(dt.date(2026, 8, 3), 1)[0]
    findings = _open_position_defects(ema, day)
    findings += _mark_field_defects(ema, day)
    findings += _absent_figure_defects(ema, day)
    findings += _clean_fold_defects(ema, day)
    return findings


def _open_position_defects(ema: Any, day: dt.date) -> list[Finding]:
    """A `filled` row is an OPEN position and must never book a realization."""
    row = _row(day, "filled", {"realized_pnl": 999.0, "qty": 1})
    kind, _message = _refusal(ema, row)
    if kind not in ("", "UnrealizedLeak"):
        return [
            Finding(
                f"{EMA_MODULE}:realized_closes",
                f"a whole-log fold containing one `filled` row raised {kind}. A "
                "log full of fills is the NORMAL case and must fold to an empty "
                "realized set, not to a crash",
            )
        ]
    if kind == "" and ema.realized_closes([row]):
        return [
            Finding(
                f"{EMA_MODULE}:realized_closes",
                "a `filled` row was folded into the realized set. §6.6: "
                "'Unrealized/paper gains never steer capital (a green open "
                "position can reverse before it closes)'. A fill is an ENTRY; "
                "its P&L is a mark",
            )
        ]
    return _direct_refusal_defects(ema, day)


def _direct_refusal_defects(ema: Any, day: dt.date) -> list[Finding]:
    """A caller asserting a `filled` row REALIZES must be refused by NAME."""
    try:
        # pylint: disable=protected-access
        ema._one_close(_row(day, "filled", {"realized_pnl": 5.0}), ema.is_trading_day)
    except ema.UnrealizedLeak as exc:
        if "filled" not in str(exc):
            return [
                Finding(
                    f"{EMA_MODULE}:_one_close",
                    f"refused a `filled` row without naming it: {str(exc)[:120]!r}. "
                    "Check contract §18: a control asserts the REASON, and an "
                    "operator reading this must learn WHICH door was tried",
                )
            ]
        return []
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return [
            Finding(
                f"{EMA_MODULE}:_one_close",
                f"refused a `filled` row with {type(exc).__name__}, not "
                "UnrealizedLeak — the refusal does not say that an OPEN mark was "
                "what it caught",
            )
        ]
    return [
        Finding(
            f"{EMA_MODULE}:_one_close",
            "ACCEPTED a `filled` row as a realization. §6.6 ranks completed "
            "strategy decisions: entered, managed, AND exited",
        )
    ]


def _mark_field_defects(ema: Any, day: dt.date) -> list[Finding]:
    """A realizing row carrying a mark alongside the realization is refused whole."""
    row = _row(day, "closed", {"realized_pnl": 100.0, "unrealized_pnl": 5000.0})
    kind, message = _refusal(ema, row)
    if kind != "UnrealizedLeak":
        return [
            Finding(
                f"{EMA_MODULE}:_realized_amount",
                f"a `closed` payload carrying BOTH realized_pnl and "
                f"unrealized_pnl was handled with {kind or 'no refusal at all'}. "
                "A payload with both figures is one field name away from "
                "steering capital on the mark",
            )
        ]
    if "unrealized_pnl" not in message:
        return [
            Finding(
                f"{EMA_MODULE}:_realized_amount",
                f"refused without naming the offending field: {message[:120]!r} "
                "(check contract §18)",
            )
        ]
    return []


def _absent_figure_defects(ema: Any, day: dt.date) -> list[Finding]:
    """A realizing row with NO realized figure is refused, never defaulted to 0."""
    kind, message = _refusal(ema, _row(day, "closed", {"qty": 1}))
    if kind != "MissingRealized":
        return [
            Finding(
                f"{EMA_MODULE}:_realized_amount",
                f"a `closed` row with no {ema.REALIZED_FIELD!r} produced "
                f"{kind or 'no refusal'}. Nothing in this tree writes that field "
                "yet, so a zero default would score EVERY pair 0.0, tie every "
                "comparison, and make a totally blind engine look exactly like a "
                "healthy cold start",
            )
        ]
    if ema.REALIZED_FIELD not in message:
        return [
            Finding(
                f"{EMA_MODULE}:_realized_amount",
                f"refused without naming the missing field: {message[:120]!r}",
            )
        ]
    return []


def _clean_fold_defects(ema: Any, day: dt.date) -> list[Finding]:
    """The POSITIVE half: an honest `closed` row folds, with its own number."""
    closes = ema.realized_closes([_row(day, "closed", {"realized_pnl": 250.0})])
    if len(closes) != 1 or closes[0].realized != 250.0:
        return [
            Finding(
                f"{EMA_MODULE}:realized_closes",
                f"an honest `closed` row carrying realized_pnl=250.0 folded to "
                f"{[c.realized for c in closes]!r}. Without this half the gate "
                "would pass an engine that refuses everything",
            )
        ]
    return []


#: The two bans, and what removing each looks like in the source. The type ban
#: needs TWO edits because the classification is a partition: moving `filled`
#: into the realizing half without removing it from the other leaves the
#: original refusal standing, and the "broken" module would still be correct.
_LEAK_PLANTS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "event-type ban",
        (
            (
                '{"closed", "protective_exit", "sentinel_flatten"}',
                '{"closed", "protective_exit", "sentinel_flatten", "filled"}',
            ),
            ('        "filled",\n        "signal",', '        "signal",'),
        ),
    ),
    (
        "field-name ban",
        (('"unrealized_pnl",', '"__never_a_real_key__",'),),
    ),
)


def leak_arm_can_fail(source: str) -> tuple[bool, str]:
    """Plant BOTH bans out and require the arm to catch BOTH."""
    for label, edits in _LEAK_PLANTS:
        try:
            broken = plant(source, edits, f"ema_leak_{len(label)}")
        except PlantFailed as exc:
            return False, str(exc)
        if not leak_defects(broken):
            return False, (
                f"an engine with its {label} planted out produced NO finding — "
                "the leak arm cannot see unrealized reaching the number, so its "
                "silence is blind, not green"
            )
    return True, ""


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


def grid_days(start: dt.date, count: int) -> list[dt.date]:
    """`count` consecutive Monday-to-Friday days from `start`. Weekends skipped."""
    out: list[dt.date] = []
    cursor = start
    while len(out) < count:
        if cursor.weekday() < 5:
            out.append(cursor)
        cursor += dt.timedelta(days=1)
    return out


def _closes(ema: Any, pair: tuple[str, str], day: dt.date, each: float, count: int):
    """`count` realized closes of `each` for `pair` on `day`."""
    return [
        ema.RealizedClose(
            strategy_id=pair[0],
            symbol=pair[1],
            day=day,
            realized=each,
            event_type="closed",
            trade_id=f"{pair[0]}-{day}-{index}",
        )
        for index in range(count)
    ]


# ---------------------------------------------------------------------------
# ARM 3 — completed decisions, not activity
# ---------------------------------------------------------------------------

FEW = ("s_few", "ES")
MANY = ("s_many", "NQ")
SPIKE = ("s_spike", "CL")
STEADY = ("s_steady", "GC")


def _activity_history(ema: Any, days: list[dt.date]) -> list[Any]:
    """Few-large against many-tiny. 1000/day on 2 closes, 400/day on 40."""
    rows: list[Any] = []
    for day in days:
        rows += _closes(ema, FEW, day, 500.0, 2)
        rows += _closes(ema, MANY, day, 10.0, 40)
    return rows


def _spread_history(ema: Any, days: list[dt.date]) -> list[Any]:
    """Identical TOTAL realized and identical close counts, different spread.

    Both pairs realize 250.0 exactly `len(days)` times. The spike pair does all
    of it on the FIRST day of the window; the steady pair does one a day. A sum
    cannot tell them apart and neither can a trade count — only the per-day EMA
    can, which is what makes this the controlled version of the arm above.
    """
    rows: list[Any] = _closes(ema, SPIKE, days[0], 250.0, len(days))
    for day in days:
        rows += _closes(ema, STEADY, day, 250.0, 1)
    return rows


def activity_defects(ema: Any, span: int) -> list[Finding]:
    """§6.6:438 — a hyperactive pair must not dominate by trading more often."""
    days = grid_days(dt.date(2026, 8, 3), 20)
    closes = _activity_history(ema, days)
    scored = ema.score_pairs(closes, span, days[-1])
    counts = ema.close_counts(closes)
    findings = _activity_ordering_defects(scored, counts)
    findings += _spread_defects(ema, span, days)
    return findings


def _activity_ordering_defects(scored: Any, counts: Any) -> list[Finding]:
    """The ranking must follow realized-per-day and CONTRADICT the trade count."""
    if not scored or FEW not in scored or MANY not in scored:
        return [
            Finding(
                f"{NAME}:non-vacuity",
                f"the activity arm scored {sorted(scored)} — it needs BOTH "
                "contenders, because a rank is a comparison and one pair cannot "
                "be compared to anything",
            )
        ]
    if counts.get(MANY, 0) < 10 * counts.get(FEW, 1):
        return [
            Finding(
                f"{NAME}:non-vacuity",
                f"the hyperactive pair made {counts.get(MANY)} closes against "
                f"{counts.get(FEW)} — the two axes barely disagree, so a "
                "ranking that follows activity would pass this arm anyway",
            )
        ]
    if scored[FEW].realized_ema <= scored[MANY].realized_ema:
        return [
            Finding(
                f"{EMA_MODULE}:daily_advances",
                f"the pair realizing 1000/day on {counts.get(FEW)} closes scored "
                f"{scored[FEW].realized_ema:.4f}, at or below the pair realizing "
                f"400/day on {counts.get(MANY)} closes "
                f"({scored[MANY].realized_ema:.4f}). §6.6:438: one realized "
                "number per symbol per DAY, so 'a hyperactive symbol can't "
                "dominate purely by trading more often'",
            )
        ]
    return []


def _spread_defects(ema: Any, span: int, days: list[dt.date]) -> list[Finding]:
    """Same total, same count, different spread — a SUM cannot tell them apart."""
    closes = _spread_history(ema, days)
    scored = ema.score_pairs(closes, span, days[-1])
    counts = ema.close_counts(closes)
    totals = {
        key: sum(c.realized for c in closes if c.key == key) for key in (SPIKE, STEADY)
    }
    if abs(totals[SPIKE] - totals[STEADY]) > TOL or counts[SPIKE] != counts[STEADY]:
        return [
            Finding(
                f"{NAME}:non-vacuity",
                f"the spread fixture is not controlled: totals {totals}, counts "
                f"{ {k: counts[k] for k in (SPIKE, STEADY)} }. Unless BOTH are "
                "equal, a sum could separate these pairs and the arm would not "
                "be testing the per-day EMA at all",
            )
        ]
    if scored[STEADY].realized_ema <= scored[SPIKE].realized_ema:
        return [
            Finding(
                f"{EMA_MODULE}:ema_over_days",
                f"a pair that realized {totals[STEADY]:.0f} steadily scored "
                f"{scored[STEADY].realized_ema:.4f}, at or below a pair that "
                f"realized the same {totals[SPIKE]:.0f} in ONE day at the start "
                f"of the window ({scored[SPIKE].realized_ema:.4f}). §6.6: "
                "'recent days weighted more, older days fade continuously'",
            )
        ]
    return []


# ---------------------------------------------------------------------------
# ARM 4 — an absent day is a ZERO advance, on a TRADING-day grid
# ---------------------------------------------------------------------------


def decay_defects(ema: Any, span: int) -> list[Finding]:
    """The silence between closes must decay the score, by exactly (1-alpha)^N."""
    days = grid_days(dt.date(2026, 8, 3), 6)
    advances = {days[0]: 1000.0}
    weight = ema.alpha_for(span)
    steps = 5
    got = ema.ema_over_days(advances, span, days[steps]).realized_ema
    want = 1000.0 * (1.0 - weight) ** steps
    findings: list[Finding] = []
    if abs(got - want) > TOL:
        findings.append(
            Finding(
                f"{EMA_MODULE}:ema_over_days",
                f"a pair that realized 1000 and then closed nothing for {steps} "
                f"grid days scored {got!r}; folding a ZERO on each silent day "
                f"gives {want!r}. The engine documents the absent day as a zero "
                "advance — if it is skipping those days instead, recency is "
                "measured in TRADES and a pair that stopped trading a month ago "
                "keeps steering capital",
            )
        )
    findings += _grid_defects(ema, span, weight)
    return findings


def _grid_defects(ema: Any, span: int, weight: float) -> list[Finding]:
    """Friday to Monday is ONE step on a trading grid and THREE on a calendar."""
    friday, monday = dt.date(2026, 8, 7), dt.date(2026, 8, 10)
    advances = {friday: 1000.0}
    trading = ema.ema_over_days(advances, span, monday).realized_ema
    calendar = ema.ema_over_days(
        advances, span, monday, grid=lambda day: True
    ).realized_ema
    findings: list[Finding] = []
    if abs(trading - 1000.0 * (1.0 - weight)) > TOL:
        findings.append(
            Finding(
                f"{EMA_MODULE}:is_trading_day",
                f"Friday to Monday decayed a 1000 advance to {trading!r}; ONE "
                f"trading-day step gives {1000.0 * (1.0 - weight)!r}. §6.6:442 "
                "says the span is in TRADING days, and a calendar walk folds two "
                "extra zeros every weekend — a 10-trading-day span would behave "
                "like about seven",
            )
        )
    if abs(calendar - 1000.0 * (1.0 - weight) ** 3) > TOL:
        findings.append(
            Finding(
                f"{EMA_MODULE}:ema_over_days",
                f"an injected all-days grid decayed the same advance to "
                f"{calendar!r} rather than {1000.0 * (1.0 - weight) ** 3!r} — the "
                "grid parameter is not the thing that decides which days step, "
                "so the session calendar could not replace it when one is written",
            )
        )
    if abs(calendar - trading) <= TOL:
        findings.append(
            Finding(
                f"{EMA_MODULE}:ema_over_days",
                "the trading-day grid and an all-days grid produced the same "
                "number over a weekend — the grid is inert, and the choice "
                "between calendar and trading days is not being made at all",
            )
        )
    return findings


def decay_arm_can_fail(source: str, span: int) -> tuple[bool, str]:
    """Plant the zero-fold out and require the decay arm to catch it."""
    try:
        broken = plant(
            source,
            (
                (
                    "value += weight * (advances.get(day, 0.0) - value)",
                    "value += weight * (advances.get(day, value) - value)",
                ),
            ),
            "ema_decay_plant",
        )
    except PlantFailed as exc:
        return False, str(exc)
    if not decay_defects(broken, span):
        return False, (
            "an engine in which a silent day leaves the score UNCHANGED "
            "(`advances.get(day, value)`) produced no finding — the decay arm "
            "cannot see a score that never fades, so its silence is blind"
        )
    return True, ""


# ---------------------------------------------------------------------------
# ARM 5 — the classification is TOTAL over the schema's enum
# ---------------------------------------------------------------------------

_ENUM_RE = re.compile(
    r"CREATE\s+TYPE\s+plane1_event_enum\s+AS\s+ENUM\s*\((?P<body>.*?)\)\s*;",
    re.IGNORECASE | re.DOTALL,
)

#: Below this the enum parse is not credible and its silence is not evidence.
MIN_ENUM_MEMBERS = 10


def schema_enum_members(sql: str) -> frozenset[str]:
    """`plane1_event_enum`'s members, from the frozen DDL text.

    Parsed from the FILE and not from a live catalog on purpose: §17 says a
    property proven while its subject is unreachable is not proven, and a
    database this gate cannot reach would make this arm Cannot-measure on a box
    where the DDL — the thing the classification must agree with — is right
    there in the tree.
    """
    match = _ENUM_RE.search(sql)
    if match is None:
        return frozenset()
    return frozenset(re.findall(r"'([a-z_]+)'", match.group("body")))


def totality_defects(ema: Any, sql: str) -> list[Finding]:
    """The engine's two sets must partition the schema's enum, both directions."""
    members = schema_enum_members(sql)
    if len(members) < MIN_ENUM_MEMBERS:
        return [
            Finding(
                f"{NAME}:non-vacuity",
                f"parsed {len(members)} member(s) from plane1_event_enum in "
                f"{SCHEMA_FILE} — below the {MIN_ENUM_MEMBERS} floor, so a "
                "'classification is total' verdict would be a statement about "
                "an empty comparison",
            )
        ]
    findings: list[Finding] = []
    unclassified = sorted(members - ema.CLASSIFIED_EVENT_TYPES)
    invented = sorted(ema.CLASSIFIED_EVENT_TYPES - members)
    if unclassified:
        findings.append(
            Finding(
                f"{EMA_MODULE}:CLASSIFIED_EVENT_TYPES",
                f"{SCHEMA_FILE} can record {', '.join(unclassified)}, which this "
                "engine classifies as neither realizing nor non-realizing. A "
                "type added to the schema by a later arc must redden HERE, not "
                "be defaulted into the silent half — the defect the Plane-1 "
                "sink's totality test caught across two branches in ARC 035",
            )
        )
    if invented:
        findings.append(
            Finding(
                f"{EMA_MODULE}:CLASSIFIED_EVENT_TYPES",
                f"classifies {', '.join(invented)}, which {SCHEMA_FILE} cannot "
                "record. A rule for an event that cannot exist is coverage of "
                "nothing",
            )
        )
    overlap = sorted(ema.REALIZING_EVENT_TYPES & ema.NON_REALIZING_EVENT_TYPES)
    if overlap:
        findings.append(
            Finding(
                f"{EMA_MODULE}:REALIZING_EVENT_TYPES",
                f"{', '.join(overlap)} is in BOTH halves — the set that decides "
                "whether a mark can steer capital is not a partition",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# ARM 6 — thin data claims nothing
# ---------------------------------------------------------------------------


def thin_data_defects(ema: Any, span: int) -> list[Finding]:
    """`days_observed` counts REAL realized days, never the calendar span."""
    days = grid_days(dt.date(2026, 8, 3), 11)
    lonely = _closes(ema, FEW, days[0], 1000.0, 1)
    scored = ema.score_pairs(lonely, span, days[10])[FEW]
    findings: list[Finding] = []
    if scored.days_observed != 1:
        findings.append(
            Finding(
                f"{EMA_MODULE}:PairScore.days_observed",
                f"one realized close, ten silent grid days later, reported "
                f"days_observed={scored.days_observed}. §6.6:445-447 warns that "
                "early realized samples are thin; a field that counts SILENCE as "
                "history tells a consumer this one-sample score has eleven days "
                "behind it, which is the confidence the caution says nobody has",
            )
        )
    if scored.closes_observed != 1:
        findings.append(
            Finding(
                f"{EMA_MODULE}:PairScore.closes_observed",
                f"one close reported closes_observed={scored.closes_observed}",
            )
        )
    findings += _seed_defects(ema, span, days)
    return findings


def _seed_defects(ema: Any, span: int, days: list[dt.date]) -> list[Finding]:
    """A one-day EMA IS that day's advance. No bias correction, no convergence."""
    same_day = ema.ema_over_days({days[0]: 777.0}, span, days[0])
    findings: list[Finding] = []
    if abs(same_day.realized_ema - 777.0) > TOL:
        findings.append(
            Finding(
                f"{EMA_MODULE}:ema_over_days",
                f"a single day's advance of 777.0, read on that same day, scored "
                f"{same_day.realized_ema!r}. A zero-seeded EMA would report "
                f"{777.0 * ema.alpha_for(span)!r} — it would put a day the pair "
                "did not exist into its history and halve a genuine first result",
            )
        )
    ten = _closes(ema, MANY, days[0], 1.0, 1)
    for day in days[1:10]:
        ten += _closes(ema, MANY, day, 1.0, 1)
    scored = ema.score_pairs(ten, span, days[9])[MANY]
    if scored.days_observed != 10:
        findings.append(
            Finding(
                f"{EMA_MODULE}:PairScore.days_observed",
                f"ten closes on ten distinct days reported "
                f"days_observed={scored.days_observed}. Without this half the "
                "field could be hard-wired to 1 and the arm above would pass",
            )
        )
    return findings


def thin_arm_can_fail(source: str, span: int) -> tuple[bool, str]:
    """Plant a calendar-span `days_observed` and require the arm to catch it."""
    try:
        broken = plant(
            source,
            (
                (
                    "days_observed=len(observed),",
                    "days_observed=len(_grid_days(first, through, grid)) + 1,",
                ),
            ),
            "ema_thin_plant",
        )
    except PlantFailed as exc:
        return False, str(exc)
    if not thin_data_defects(broken, span):
        return False, (
            "an engine reporting days_observed as the CALENDAR span produced no "
            "finding — the thin-data arm cannot see a score claiming history it "
            "does not have, so its silence is blind"
        )
    return True, ""


def activity_arm_can_fail(source: str, span: int) -> tuple[bool, str]:
    """Plant the per-day reduction out (count trades) and require a finding."""
    try:
        broken = plant(
            source,
            (
                (
                    "day_map[close.day] = day_map.get(close.day, 0.0) + close.realized",
                    "day_map[close.day] = day_map.get(close.day, 0.0) + 1.0",
                ),
            ),
            "ema_activity_plant",
        )
    except PlantFailed as exc:
        return False, str(exc)
    if not activity_defects(broken, span):
        return False, (
            "an engine whose daily advance counts TRADES rather than summing "
            "realized P&L produced no finding — the activity arm cannot see the "
            "hyperactive pair winning, which is §6.6:438's whole subject"
        )
    return True, ""


# ---------------------------------------------------------------------------


def _arms_can_fail(source: str, span: int) -> tuple[str, str]:
    """The first arm that cannot demonstrate a defect, or ("", "")."""
    controls = (
        ("span-ast", span_ast_arm_can_fail),
        ("leak", lambda: leak_arm_can_fail(source)),
        ("activity", lambda: activity_arm_can_fail(source, span)),
        ("decay", lambda: decay_arm_can_fail(source, span)),
        ("thin-data", lambda: thin_arm_can_fail(source, span)),
    )
    for label, control in controls:
        try:
            ok, why = control()
        except PlantFailed as exc:
            return label, str(exc)
        if not ok:
            return label, why
    return "", ""


def _read(home: Path, relative: str) -> tuple[str, str]:
    """One tree file as text, or ("", error)."""
    try:
        return (home / relative).read_text(encoding="utf-8"), ""
    except (OSError, UnicodeDecodeError) as exc:
        return "", f"cannot read {relative}: {exc!r}"


def _static_findings(source: str) -> list[Finding]:
    """The AST arm plus its own non-vacuity floor."""
    findings, seen = carved_span_defects(source)
    if seen == 0:
        findings.append(
            Finding(
                f"{NAME}:non-vacuity",
                f"the carved-span scan found NO span-shaped name in {EMA_MODULE} "
                f"(it looks for {', '.join(sorted(SPAN_NAMES))}). A scan over "
                "nothing cannot report a carved constant, and a rename would "
                "have orphaned it silently",
            )
        )
    return findings


def _evidence(ema: Any, span: int, source: str, sql: str) -> str:
    """What was actually measured this run, in numbers."""
    _, seen = carved_span_defects(source)
    days = grid_days(dt.date(2026, 8, 3), 20)
    sample = ema.score_pairs(_activity_history(ema, days), span, days[-1])[FEW]
    return (
        f"{EMA_MODULE}: scanned {seen} span-shaped binding(s) for a carved "
        f"constant; built engines from written configs at span {SPAN_A} and "
        f"{SPAN_B} and required the smoothing to differ; drove both unrealized "
        f"doors (event type `filled`, payload field) plus the absent-figure "
        f"refusal and the honest fold; ranked two pairs whose close counts "
        f"disagree with their realized-per-day by 20:1 and two more with "
        f"identical totals and counts; checked the zero-advance decay against "
        f"(1-alpha)^N to {TOL} under span {span}; compared "
        f"{len(ema.CLASSIFIED_EVENT_TYPES)} classified event type(s) against "
        f"{len(schema_enum_members(sql))} in {SCHEMA_FILE}; all five plant-driven "
        f"arms proved they can fail on mutated copies this run. The winning "
        f"pair's own account of its evidence, verbatim from the engine: "
        f"{sample.key_facts}"
    )


@dataclasses.dataclass(frozen=True)
class Subject:
    """Everything the arms need, or the reason they cannot run (§17)."""

    ema: Any = None
    source: str = ""
    sql: str = ""
    span: int = 0
    error: str = ""


def _subject(home: Path) -> Subject:
    """Load the engine, its source, the frozen DDL and the configured span.

    Any failure here is CANNOT_MEASURE and never a Pass: §17 — a property proven
    while its subject is unavailable is not proven.
    """
    ema, error = _load_ema(home)
    if ema is None:
        return Subject(error=error)
    source, error = _read(home, EMA_MODULE)
    if error:
        return Subject(error=error)
    sql, error = _read(home, SCHEMA_FILE)
    if error:
        return Subject(error=error)
    return Subject(
        ema=ema, source=source, sql=sql, span=ema.span_days_from_config(home)
    )


def _drive(label: str, arm: Any) -> list[Finding]:
    """One arm, driven, with a raise turned into a finding rather than a crash.

    An engine that raises while being driven is a finding about the ENGINE, not
    an instrument outage: the caller here is the Scoring process's own
    arithmetic, and something that cannot be smoothed without an exception
    cannot produce a ranking either. The exception TYPE and message are carried
    into the reason (§18) so the arm is distinguishable from a gate bug — which
    is what the clean-tree test in `test_check_scoring_ema.py` pins down.
    """
    try:
        return arm()
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return [
            Finding(
                f"{EMA_MODULE}:{label}",
                f"raised {type(exc).__name__} while being driven: {str(exc)[:200]}",
            )
        ]


def _all_findings(subject: Subject, home: Path) -> list[Finding]:
    """Every arm, driven. None short-circuits: a defect must not hide the rest."""
    ema, span = subject.ema, subject.span
    findings = _static_findings(subject.source)
    findings += _drive("span-config", lambda: span_config_defects(ema, home))
    findings += _drive("leak", lambda: leak_defects(ema))
    findings += _drive("activity", lambda: activity_defects(ema, span))
    findings += _drive("decay", lambda: decay_defects(ema, span))
    findings += _drive("totality", lambda: totality_defects(ema, subject.sql))
    findings += _drive("thin-data", lambda: thin_data_defects(ema, span))
    return findings


def run(  # pylint: disable=unused-argument
    mode: Mode, ctx: Context
) -> CheckResult:
    """Measure it. See the module docstring for what and why."""
    try:
        home = ctx.nix_home
        subject = _subject(home)
        if subject.error:
            return CheckResult(
                name=NAME, status=Status.CANNOT_MEASURE, detail=subject.error
            )
        # THE ARMS RUN BEFORE THE CONTROLS, AND THE ORDER IS LOAD-BEARING.
        #
        # Every can-fail control here plants a defect INTO THE SHIPPED SOURCE.
        # So an engine that already carries that defect has no anchor left to
        # plant on, and the control reports itself blind — on the one tree where
        # the arm it guards has just observed the real thing. Measured: six of
        # this gate's own plant tests came back CANNOT_MEASURE with the defect
        # sitting in the detail of an arm that never got to run.
        #
        # A POSITIVELY-OBSERVED DEFECT OUTRANKS AN INSTRUMENT THAT CANNOT
        # SELF-TEST — check contract rule 10's principle one layer over: the
        # attempt is the claim, and masking a real finding behind "my control is
        # broken" is the reading that loses the finding. A blind control still
        # withholds the GREEN: with no findings, a blind arm is CANNOT_MEASURE
        # and never a Pass.
        findings = _all_findings(subject, home)
        evidence = _evidence(subject.ema, subject.span, subject.source, subject.sql)
        blind, why = _arms_can_fail(subject.source, subject.span)
        if findings:
            return CheckResult(
                name=NAME,
                status=Status.FAIL_NEEDS_OPERATOR,
                site="; ".join(sorted({f.site for f in findings})),
                evidence=evidence
                + (f"; the {blind} control is BLIND: {why}" if blind else ""),
                detail="; ".join(f"{f.site}: {f.why}" for f in findings),
            )
        if blind:
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                site=f"{NAME}:{blind}-arm",
                detail=f"the {blind} arm cannot fail: {why}",
            )
        return CheckResult(name=NAME, status=Status.PASS, evidence=evidence)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return CheckResult(
            name=NAME,
            status=Status.CANNOT_MEASURE,
            detail=f"gate raised {type(exc).__name__}: {exc}",
        )


# pylint: disable=duplicate-code
if __name__ == "__main__":
    from nixverify.actuation import standalone_main

    sys.exit(standalone_main(Path(__file__).resolve(), run, NAME))
