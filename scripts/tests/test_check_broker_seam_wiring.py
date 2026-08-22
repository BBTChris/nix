"""The can-fail suite for `checks/check_broker_seam_wiring.py` (Module 2, B12-1).

Structure follows `nix_check_contract.md` §5.1: **non-vacuity FIRST** (the gate is
green on the real tree, and it really compared types, verbs and events), then one
planted defect PER ARM — each of which must turn the gate red **and NAME the
site**, never merely move the exit code (check-contract rule 11) — then the plants
removed and the same tree passing again.

**NO PLANT TOUCHES A PRODUCTION FILE** (doctrine C.8 / Part C rule 8). Every
control builds a throwaway `nix_home` under `tmp_path` holding COPIES of
`scripts/limiterd.py`, `scripts/broker/`, `scripts/nixrisk/`,
`scripts/nixsentinel/`, `scripts/risk_config.py` and `risks/`, and a plant is an
APPEND to, or a substitution inside, a COPY. The real files are read and never
written — `test_the_REAL_SOURCES_are_byte_identical_after_the_suite` re-hashes
them at the end to prove it.

PLANT A is the fail-open trap itself: it strips the adapter copy's canonical-seam
aliasing, which is the D3.485 regression, and asserts the substitution actually
happened — so if the aliasing is ever renamed this suite goes red rather than
quietly planting nothing.
"""

# pylint: disable=missing-function-docstring,missing-module-docstring
# pylint: disable=use-implicit-booleaness-not-comparison
# missing-function-docstring: every test's NAME is its assertion, which is the
# convention this suite tree uses throughout. use-implicit-booleaness-not-
# comparison: `gate.DEPENDS_ON == ()` is asserting the declaration is EXACTLY the
# empty tuple, not merely falsey — the declaration's TYPE is part of what
# verify.py reads.
# pylint: disable=invalid-name,redefined-outer-name,duplicate-code

from __future__ import annotations

import hashlib
import importlib
import re
import shutil
import sys
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "broker"))
sys.path.append(str(REPO / "checks"))

import check_broker_seam_wiring as gate  # pylint: disable=wrong-import-position
from nixverify.contract import (  # pylint: disable=wrong-import-position
    Context,
    Mode,
    Status,
)

LIMITER = "scripts/limiterd.py"
ADAPTER = "scripts/broker/broker_order_ibkr.py"
SEAM = "scripts/broker/broker_seam.py"

#: Everything `limiterd.py` needs to import, and nothing else. Directories are
#: copied without their `__pycache__`, so a stale `.pyc` cannot answer for a
#: plant.
COPY_DIRS = (
    "scripts/broker",
    "scripts/nixrisk",
    "scripts/nixsentinel",
    "risks",
)
COPY_FILES = ("scripts/limiterd.py", "scripts/risk_config.py")

#: The production files this suite must not touch. Hashed BEFORE any test runs
#: and compared AFTER — the freeze, measured.
FROZEN = (
    LIMITER,
    *sorted(
        str(p.relative_to(REPO)) for p in (REPO / "scripts" / "broker").glob("*.py")
    ),
)
_BEFORE = {rel: hashlib.sha256((REPO / rel).read_bytes()).hexdigest() for rel in FROZEN}

#: §2A seam types whose IDENTITY the seam's own `is` comparisons rest on. The
#: gate derives its list by shape and must never need this one; the floor lives
#: HERE, in the control, so a derivation that silently narrows is caught by a
#: failing test rather than by a green gate that compared three types.
REQUIRED_TYPES = (
    "SessionState",
    "Side",
    "OrderType",
    "RejectCategory",
    "AckStatus",
    "TimeInForce",
)
DROPPED_VERB = "get_margin"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A throwaway `nix_home` holding COPIES of everything the Limiter imports."""
    (tmp_path / "scripts").mkdir(parents=True)
    for rel in COPY_DIRS:
        shutil.copytree(
            REPO / rel, tmp_path / rel, ignore=shutil.ignore_patterns("__pycache__")
        )
    for rel in COPY_FILES:
        shutil.copy(REPO / rel, tmp_path / rel)
    return tmp_path


def _run(nix_home: Path):
    return gate.run(Mode.VERIFY, Context(nix_home=nix_home, mode=Mode.VERIFY))


def _append(nix_home: Path, rel: str, source: str) -> None:
    with (nix_home / rel).open("a", encoding="utf-8") as handle:
        handle.write("\n\n" + source.strip() + "\n")


def _strip_canonical_seam(nix_home: Path) -> None:
    """PLANT A: reintroduce D3.485 by removing the adapter copy's aliasing call.

    The substitution count is ASSERTED. If `_canonicalise_seam()` is ever renamed
    or moved this raises here, rather than planting nothing and letting the gate
    pass over an un-planted control (Part C rule 2's second half).
    """
    target = nix_home / ADAPTER
    source = target.read_text(encoding="utf-8")
    planted, count = re.subn(
        r"(?m)^_canonicalise_seam\(\)[ \t]*$",
        "pass  # PLANT A: canonical-seam aliasing stripped (D3.485)",
        source,
    )
    assert count == 1, f"the canonical-seam call was not found in {ADAPTER}"
    target.write_text(planted, encoding="utf-8")


# --------------------------------------------------------------------------
# NON-VACUITY FIRST — the gate is GREEN on the real tree, and it really measured
# --------------------------------------------------------------------------


def test_the_REAL_TREE_passes() -> None:
    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert "adapter constructed=True" in result.evidence, result.evidence
    assert "really called" in result.evidence, result.evidence
    assert "really driven" in result.evidence, result.evidence


def test_the_REAL_TREE_run_COMPARED_SOMETHING(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule 3: a run that compared zero types or zero verbs proves nothing."""
    seen: list[gate.Measured] = []
    real = gate.evidence

    def recording(measured: gate.Measured) -> str:
        seen.append(measured)
        return real(measured)

    monkeypatch.setattr(gate, "evidence", recording)

    result = _run(REPO)

    assert result.status is Status.PASS, result
    assert seen, "the gate produced no evidence record"
    assert seen[-1].types_compared > 0, seen[-1]
    assert seen[-1].verbs_checked > 0, seen[-1]
    assert seen[-1].session_events > 0, seen[-1]
    assert seen[-1].constructed is True, seen[-1]


def test_the_COPIED_TREE_passes_so_a_PLANT_is_the_only_variable(home: Path) -> None:
    result = _run(home)

    assert result.status is Status.PASS, result


def test_the_SEAM_TYPE_DERIVATION_SEES_THE_TYPES_IDENTITY_DEPENDS_ON() -> None:
    """The by-shape derivation must cover the enums the seam's `is` rules use."""
    seam = importlib.import_module("broker_seam")

    derived = gate.seam_types(seam)

    for name in REQUIRED_TYPES:
        assert name in derived, (
            f"{name!r} is invisible to seam_types() — the derivation is narrower "
            f"than the seam and would compare {len(derived)} types while missing "
            "the ones the identity guard actually rests on"
        )


def test_the_VERB_LIST_IS_DERIVED_and_covers_the_roster() -> None:
    seam = importlib.import_module("broker_seam")

    derived = gate.port_verbs(seam)

    assert set(seam.ORDER_PORT_VERBS) <= set(derived), derived
    assert DROPPED_VERB in derived, derived


def test_the_ROSTER_IS_NOT_A_LITERAL_IN_THE_GATE() -> None:
    """§7.12 answer 3: no hardcoded verb or type roster lives in the gate's code."""
    source = Path(gate.__file__).read_text(encoding="utf-8")
    body = source.split('"""', 2)[2]  # everything after the module docstring

    for spelled in ("place_order", "cancel_order", "query_order_status", "on_fill"):
        assert spelled not in body, (
            f"{spelled!r} is spelled out in the gate's code — the verb set must be "
            "derived by introspection, not typed here (D3.426)"
        )
    for spelled in ("Side", "OrderType", "RejectCategory", "AckStatus"):
        assert f'"{spelled}"' not in body, (
            f"{spelled!r} is spelled out in the gate's code — the seam type set "
            "must be derived by shape (D3.426)"
        )


def test_the_GATE_DECLARES_ITS_SUBJECTS_and_refuses_to_correct() -> None:
    for rel in (LIMITER, ADAPTER, SEAM):
        assert rel in gate.SUBJECTS, gate.SUBJECTS
    assert gate.CORRECTABLE is False
    assert gate.NON_CORRECTABLE_REASON
    assert gate.DEPENDS_ON == ()
    assert "interpreter:sys.modules" in gate.RESOURCES
    assert "interpreter:sys.path" in gate.RESOURCES


# --------------------------------------------------------------------------
# PLANT A (ARM 1 + ARM 2) — the D3.485 fail-open trap, reintroduced
# --------------------------------------------------------------------------


def test_a_DOUBLE_LOADED_SEAM_fails_and_NAMES_BOTH_SPELLINGS(home: Path) -> None:
    _strip_canonical_seam(home)

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "DOUBLE-LOADED SEAM" in result.detail, result.detail
    assert "'broker_seam'" in result.detail, result.detail
    assert "'broker.broker_seam'" in result.detail, result.detail
    assert "TWO DISTINCT module objects" in result.detail, result.detail


def test_a_DOUBLE_LOADED_SEAM_names_the_SPLIT_TYPES(home: Path) -> None:
    _strip_canonical_seam(home)

    result = _run(home)

    assert "SPLIT SEAM TYPES" in result.detail, result.detail
    for name in REQUIRED_TYPES:
        assert name in result.detail, (
            f"{name} is a split class object and the gate did not name it"
        )


def test_the_DEAD_IDENTITY_GUARD_is_DRIVEN_and_the_TWO_DOWNS_NAMED(
    home: Path,
) -> None:
    """ARM 2, and this is the arm that is a PROPERTY rather than a proxy."""
    _strip_canonical_seam(home)

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "DEAD IDENTITY GUARD" in result.detail, result.detail
    assert "emitted 2 on_session(DOWN) events" in result.detail, result.detail
    assert "transport disconnected" in result.detail, result.detail
    assert "requested" in result.detail, result.detail
    assert "_publish_session" in result.site, result.site
    assert "1 of them DOWN" not in result.evidence, result.evidence
    assert "2 of them DOWN" in result.evidence, result.evidence


# --------------------------------------------------------------------------
# PLANT B (ARM 3) — no construction site
# --------------------------------------------------------------------------


def test_a_MISSING_CONSTRUCTION_SITE_fails_and_NAMES_it(home: Path) -> None:
    _append(home, LIMITER, f"del {gate.CONSTRUCTOR}")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "NO CONSTRUCTION SITE" in result.detail, result.detail
    assert gate.CONSTRUCTOR in result.detail, result.detail
    assert LIMITER in result.site, result.site
    assert "adapter constructed=False" in result.evidence, result.evidence


def test_a_CONSTRUCTION_SITE_RETURNING_NONE_fails_and_NAMES_it(home: Path) -> None:
    _append(
        home,
        LIMITER,
        f"def {gate.CONSTRUCTOR}():  # PLANT B2\n    return None",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert gate.CONSTRUCTOR in result.detail, result.detail
    assert "NO ADAPTER BEHIND THE PORT" in result.detail, result.detail
    assert "adapter constructed=False" in result.evidence, result.evidence


def test_a_STAND_IN_ADAPTER_fails_and_NAMES_the_WRONG_CLASS(home: Path) -> None:
    """§7.12 answer 5: the seam's own stub satisfies the port by construction."""
    _append(
        home,
        LIMITER,
        "from broker_seam import StubBrokerOrder as _Stand_in  # PLANT B3\n"
        f"def {gate.CONSTRUCTOR}():\n"
        "    _sink = UnwiredOrderEventSink()\n"
        "    return _Stand_in(_sink), _sink",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "WRONG CLASS" in result.detail, result.detail
    assert "StubBrokerOrder" in result.detail, result.detail
    assert "OUT-OF-TREE ADAPTER" not in result.detail, result.detail


# --------------------------------------------------------------------------
# PLANT C (ARM 3) — the adapter does not satisfy one DERIVED port verb
# --------------------------------------------------------------------------


def test_an_UNSATISFIED_VERB_fails_and_NAMES_THE_VERB(home: Path) -> None:
    _append(home, ADAPTER, f"del {gate.ADAPTER_CLASS}.{DROPPED_VERB}")

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert f"UNSATISFIED VERB '{DROPPED_VERB}'" in result.detail, result.detail
    assert "NOT A BrokerOrderPort" in result.detail, result.detail
    assert DROPPED_VERB in result.site, result.site


# --------------------------------------------------------------------------
# PLANT D (ARM 4) — a live connect on the construction path
# --------------------------------------------------------------------------


def test_a_LIVE_CONNECT_ON_THE_CONSTRUCTION_PATH_fails_and_NAMES_it(
    home: Path,
) -> None:
    _append(
        home,
        LIMITER,
        "_real_construct = " + gate.CONSTRUCTOR + "  # PLANT D\n"
        f"def {gate.CONSTRUCTOR}():\n"
        "    import socket as _s\n"
        "    _probe = _s.socket()\n"
        "    try:\n"
        "        _probe.connect(('127.0.0.1', 4002))\n"
        "    except OSError:\n"
        "        pass\n"
        "    finally:\n"
        "        _probe.close()\n"
        "    return _real_construct()",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "LIVE CONNECT ON THE CONSTRUCTION PATH" in result.detail, result.detail
    assert "socket.socket.connect" in result.detail, result.detail
    assert "4002" in result.detail, result.detail
    assert "1 socket dial(s) attempted" in result.evidence, result.evidence


def test_an_INJECTED_CLIENT_fails_and_NAMES_the_STRUCTURAL_HALF(home: Path) -> None:
    """ARM 4(a): `_ib is None` is the adapter's own no-connect guarantee."""
    _append(
        home,
        LIMITER,
        "_real_construct2 = " + gate.CONSTRUCTOR + "  # PLANT D2\n"
        "class _FakeClient:\n"
        "    pass\n"
        f"def {gate.CONSTRUCTOR}():\n"
        "    port, sink = _real_construct2()\n"
        "    port._ib = _FakeClient()\n"
        "    return port, sink",
    )

    result = _run(home)

    assert result.status is Status.FAIL_NEEDS_OPERATOR, result
    assert "CLIENT INJECTED AT CONSTRUCTION" in result.detail, result.detail
    assert "_FakeClient" in result.detail, result.detail


# --------------------------------------------------------------------------
# THE THIRD STEP — the plants removed, the same tree passing again
# --------------------------------------------------------------------------


def test_the_SEAM_PLANT_APPLIED_AND_REVERTED_leaves_the_gate_GREEN(
    home: Path,
) -> None:
    before = (home / ADAPTER).read_bytes()
    _strip_canonical_seam(home)

    planted = _run(home)
    (home / ADAPTER).write_bytes(before)
    restored = _run(home)

    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted
    assert restored.status is Status.PASS, restored
    assert (home / ADAPTER).read_bytes() == before, "the control was not restored"


def test_EVERY_LIMITER_PLANT_REVERTS_to_GREEN(home: Path) -> None:
    before = (home / LIMITER).read_bytes()
    _append(home, LIMITER, f"del {gate.CONSTRUCTOR}")

    planted = _run(home)
    (home / LIMITER).write_bytes(before)
    restored = _run(home)

    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted
    assert restored.status is Status.PASS, restored


def test_the_VERB_PLANT_REVERTS_to_GREEN(home: Path) -> None:
    before = (home / ADAPTER).read_bytes()
    _append(home, ADAPTER, f"del {gate.ADAPTER_CLASS}.{DROPPED_VERB}")

    planted = _run(home)
    (home / ADAPTER).write_bytes(before)
    restored = _run(home)

    assert planted.status is Status.FAIL_NEEDS_OPERATOR, planted
    assert restored.status is Status.PASS, restored


# --------------------------------------------------------------------------
# CANNOT_MEASURE, never PASS — and the interpreter left as found
# --------------------------------------------------------------------------


def test_an_ABSENT_LIMITER_is_CANNOT_MEASURE(home: Path) -> None:
    (home / LIMITER).unlink()

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "absent" in result.detail, result.detail
    assert LIMITER in result.site, result.site


def test_an_UNIMPORTABLE_LIMITER_is_CANNOT_MEASURE_naming_the_exception(
    home: Path,
) -> None:
    _append(home, LIMITER, "raise RuntimeError('planted: the Limiter will not import')")

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "RuntimeError" in result.detail, result.detail
    assert "never a PASS" in result.detail, result.detail


def test_a_SEAM_WITHOUT_THE_SESSION_ENUM_MEMBER_is_CANNOT_MEASURE(home: Path) -> None:
    """A probe that cannot be driven is §17's unavailable subject, not a PASS."""
    _append(
        home,
        ADAPTER,
        "import broker_seam as _bs  # PLANT: the probe's subject removed\n"
        "class _Hollow:\n"
        "    pass\n"
        "_bs.SessionState = _Hollow",
    )

    result = _run(home)

    assert result.status is Status.CANNOT_MEASURE, result
    assert "SessionState" in result.detail, result.detail
    assert "carries no member" in result.detail, result.detail


def test_the_GATE_LEAVES_THE_INTERPRETER_AS_IT_FOUND_IT(home: Path) -> None:
    paths_before = list(sys.path)
    modules_before = dict(sys.modules)
    connect_before = sys.modules["socket"].socket.__dict__.get("connect")

    _run(home)

    assert sys.path == paths_before, "the gate leaked a sys.path entry"
    assert sys.modules["socket"].socket.__dict__.get("connect") is connect_before, (
        "the gate left its venue sentinel installed on socket.socket"
    )
    leaked = [name for name in sys.modules if name not in modules_before]
    assert not leaked, f"the gate left the tmp_path tree in sys.modules: {leaked}"
    for name, module in modules_before.items():
        assert sys.modules.get(name) is module, f"the gate replaced sys.modules[{name}]"


# --------------------------------------------------------------------------
# THE FREEZE, MEASURED
# --------------------------------------------------------------------------


def test_the_REAL_SOURCES_are_byte_identical_after_the_suite() -> None:
    after = {
        rel: hashlib.sha256((REPO / rel).read_bytes()).hexdigest() for rel in FROZEN
    }

    assert after == _BEFORE, "a plant reached a production file (Part C rule 8)"
