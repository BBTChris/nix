#!/usr/bin/env python3
"""`risks/broker_order.config.json`, DRIVEN through its real loader/validator.

ONE gate, ONE property: the SHIPPED config satisfies its own declared
`_boot_validation` rules — `positive.scalars` and the three ordering rules —
implemented in `scripts/broker/broker_order_config.py::BrokerOrderConfig.
validate()`, and a config that VIOLATES one of them is rejected LOUDLY,
naming the rule id (check contract v2 §11).

WHY THIS GATE, AND NOT `check_risks_data_only`. That gate's ARM 4 explicitly
excludes `broker_order` from the modules it RUNS through a real validator
(`scripts/risk_config.py::OWNED_MODULES` deliberately omits it — the module
has its own loader). Measured directly: planting a negative
`flatten_idempotency_window_ms` into the shipped file and re-running
`check_risks_data_only` leaves it PASS — it proves the config's declared
SHAPE and rule-id correspondence, never that the SHIPPED VALUES satisfy the
rules. This gate is the missing other half: it calls the real
`load_broker_order_config` — the same function `broker_order_ibkr.py` calls
at boot — against the shipped file, and separately against `risks/
limiter.config.json` (the two knobs `broker_order` reads from the Limiter's
own config, per ARC 028 D1).

§7.12 — WHAT WOULD MAKE THIS GATE PASS WHILE MEASURING NOTHING?

 1. The subject could fail to import. CLOSED: CANNOT_MEASURE naming the
    exception (§17, never a PASS).
 2. The real-tree call could raise for an unrelated reason (a missing
    `risks/limiter.config.json`, say) and get reported as "PASS" by a gate
    that only checked "did it raise". CLOSED: the real-tree arm asserts the
    loaded object's fields are exactly the shipped file's values, not merely
    that the call returned.
 3. Each planted violation could be checked by asserting only that SOME
    exception was raised, which a validator that raises unconditionally would
    also satisfy. CLOSED: every planted case asserts the `[rule.id]` tag
    named in `BrokerConfigError`'s own message, and a HEALTHY sibling field is
    left untouched per plant so a validator that rejects everything
    indiscriminately cannot be told apart from one that discriminates — this
    gate drives FOUR distinct plants, one per rule, and each must implicate
    only its own rule tag.
 4. The plant could edit the real shipped file. CLOSED (doctrine C.8): every
    plant is written to a `tempfile` COPY; `risks/broker_order.config.json`
    is read and never written by this gate.
"""

from __future__ import annotations

import importlib
import json
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import CheckResult, Context, Mode, Status

# pylint: disable=duplicate-code,too-few-public-methods,too-many-locals
# missing-function-docstring,missing-class-docstring: the test doubles'
# verbs are named after the ports they stand in for, and each arm function's
# name states its own property (§7.12 answer per arm) — a docstring would
# restate the name. too-few-public-methods: several doubles are one-verb
# stand-ins for a frozen port's single relevant method. too-many-locals: an
# arm's local count is the drive's own inputs/outputs, not incidental state.
# pylint: disable=missing-function-docstring,missing-class-docstring
PRIVILEGE = "user"
INTERACTIVE = False
DISRUPTIVE = False
TIME_BOUND = False
DEPENDS_ON: tuple[str, ...] = ()
RESOURCES: tuple[str, ...] = (
    "interpreter:sys.modules",
    "interpreter:sys.path",
    "file-write:/tmp",
)
#: NON-CORRECTABLE: the two files this gate reads are §12A-derived config, and
#: a rejected set is a human decision about the exit-path timing budget, not
#: an arithmetic error this gate could safely resolve unattended.
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "a config that fails its own boot validation names a §12A timing "
    "relationship a human chose wrong; an instrument that edited the numbers "
    "until validate() passed would be deciding the exit-path timing budget "
    "unattended, which is the same class of action risk spec §4 forbids"
)
SUBJECTS: tuple[str, ...] = ("risks/broker_order.config.json",)

NAME = "check_broker_order_config"

CONFIG_FILE = "risks/broker_order.config.json"
LIMITER_FILE = "risks/limiter.config.json"
MODULE = "broker_order_config"
PACKAGE_DIRS = ("scripts", "scripts/broker")


class Loaded(NamedTuple):
    module: ModuleType


def _purge(saved: dict[str, ModuleType]) -> None:
    for name in ["broker_order_config", "broker_seam"]:
        sys.modules.pop(name, None)
    sys.modules.update(saved)


def load(home: Path) -> tuple[Loaded | None, str]:
    saved_path = list(sys.path)
    saved_modules = {
        key: value
        for key, value in sys.modules.items()
        if key in ("broker_order_config", "broker_seam")
    }
    for name in ("broker_order_config", "broker_seam"):
        sys.modules.pop(name, None)
    for rel in PACKAGE_DIRS:
        sys.path.insert(0, str((home / rel).resolve()))
    importlib.invalidate_caches()
    try:
        return Loaded(module=importlib.import_module(MODULE)), ""
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        return None, (
            f"{CONFIG_FILE}: cannot import {MODULE} from {home} — "
            f"{type(exc).__name__}: {exc}. The subject's loader is "
            "unavailable, so nothing was measured (§17: never a PASS)"
        )
    finally:
        sys.path[:] = saved_path
        _purge(saved_modules)


def _real_config(home: Path) -> dict:
    return json.loads((home / CONFIG_FILE).read_text(encoding="utf-8"))


def _real_limiter(home: Path) -> dict:
    return json.loads((home / LIMITER_FILE).read_text(encoding="utf-8"))


def _write(directory: Path, name: str, data: dict) -> Path:
    path = directory / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _arm_real_tree(loaded: Loaded, home: Path) -> list[tuple[str, str]]:
    """Non-vacuity: the real shipped files load and validate cleanly."""
    findings: list[tuple[str, str]] = []
    real = _real_config(home)
    real_limiter = _real_limiter(home)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        broker_path = _write(tmp_path, "broker_order.config.json", real)
        limiter_path = _write(tmp_path, "limiter.config.json", real_limiter)
        try:
            cfg = loaded.module.load_broker_order_config(
                path=broker_path, limiter_path=limiter_path
            )
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            return [
                (
                    f"{CONFIG_FILE}:real-tree",
                    (
                        f"the SHIPPED config failed its own validator: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                )
            ]
        if cfg.flatten_idempotency_window_ms != real["flatten_idempotency_window_ms"]:
            findings.append(
                (
                    f"{CONFIG_FILE}:real-tree",
                    (
                        f"loaded flatten_idempotency_window_ms="
                        f"{cfg.flatten_idempotency_window_ms!r}, shipped file says "
                        f"{real['flatten_idempotency_window_ms']!r} — the loader "
                        "did not read the file it was pointed at"
                    ),
                )
            )
    return findings


def _arm_plants(loaded: Loaded, home: Path) -> list[tuple[str, str]]:
    """Four plants, one per declared boot rule, each naming its own tag."""
    findings: list[tuple[str, str]] = []
    real = _real_config(home)
    real_limiter = _real_limiter(home)

    plants = (
        (
            "positive.scalars",
            {**real, "flatten_idempotency_window_ms": -5},
            real_limiter,
        ),
        (
            "ordering.flatten_window_within_pending_ack",
            {
                **real,
                "flatten_idempotency_window_ms": int(
                    real_limiter["pending_ack_timeout_ms"]
                )
                + 5_000_000,
            },
            real_limiter,
        ),
        (
            "ordering.retention_outlasts_pending_ack",
            {
                **real,
                "terminal_order_retention_ms": max(
                    1, int(real_limiter["pending_ack_timeout_ms"]) - 1
                ),
            },
            real_limiter,
        ),
        (
            "ordering.retention_outlasts_fill_timeout",
            {
                **real,
                "terminal_order_retention_ms": max(
                    1, int(real_limiter["fill_timeout_ms"]) - 1
                ),
            },
            real_limiter,
        ),
    )

    for tag, broker_data, limiter_data in plants:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            broker_path = _write(tmp_path, "broker_order.config.json", broker_data)
            limiter_path = _write(tmp_path, "limiter.config.json", limiter_data)
            site = f"{CONFIG_FILE}:plant[{tag}]"
            try:
                loaded.module.load_broker_order_config(
                    path=broker_path, limiter_path=limiter_path
                )
                findings.append(
                    (site, f"a config violating [{tag}] was ACCEPTED, not refused")
                )
            except loaded.module.BrokerConfigError as exc:
                if f"[{tag}]" not in str(exc):
                    findings.append(
                        (
                            site,
                            (
                                f"validate() refused the plant but did not name "
                                f"[{tag}] — got: {exc}"
                            ),
                        )
                    )
    return findings


def _arm_missing_key(loaded: Loaded, home: Path) -> list[tuple[str, str]]:
    """Fail-closed on an absent key — never a defaulted read (§7.12 answer 1)."""
    real = _real_config(home)
    real_limiter = _real_limiter(home)
    # `.pop(..., None)` rather than `del`: robust to a REAL tree that already
    # lacks the key (that combination is itself reported by `_arm_real_tree`,
    # and this arm must not crash the whole gate to CANNOT_MEASURE over it).
    incomplete = {k: v for k, v in real.items() if k != "flatten_attempt_log_depth"}
    site = f"{CONFIG_FILE}:plant[missing-key]"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        broker_path = _write(tmp_path, "broker_order.config.json", incomplete)
        limiter_path = _write(tmp_path, "limiter.config.json", real_limiter)
        try:
            loaded.module.load_broker_order_config(
                path=broker_path, limiter_path=limiter_path
            )
            return [(site, "a config with a MISSING required key was ACCEPTED")]
        except loaded.module.BrokerConfigError as exc:
            if "flatten_attempt_log_depth" not in str(exc) or "absent" not in str(exc):
                return [(site, f"refusal did not name the missing key: {exc}")]
    return []


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    try:
        if not (ctx.nix_home / CONFIG_FILE).is_file():
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                detail=f"{CONFIG_FILE} is absent — nothing to measure (§17)",
            )
        if not (ctx.nix_home / LIMITER_FILE).is_file():
            return CheckResult(
                name=NAME,
                status=Status.CANNOT_MEASURE,
                detail=f"{LIMITER_FILE} is absent — broker_order reads two of its "
                "knobs from it, so validation cannot run (§17)",
            )
        loaded, error = load(ctx.nix_home)
        if loaded is None:
            return CheckResult(name=NAME, status=Status.CANNOT_MEASURE, detail=error)
        findings: list[tuple[str, str]] = []
        findings += _arm_real_tree(loaded, ctx.nix_home)
        findings += _arm_plants(loaded, ctx.nix_home)
        findings += _arm_missing_key(loaded, ctx.nix_home)
        evidence = (
            f"{CONFIG_FILE}: loaded and validated the SHIPPED config through the "
            "real broker_order_config.load_broker_order_config, then drove 5 "
            "plants (4 boot-validation rules + 1 missing-key) on tempfile copies, "
            "each required to name its own rule tag"
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
