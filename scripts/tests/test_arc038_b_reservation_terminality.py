"""ARC 038 / B — §14's exactly-once reservation lifecycle, attacked.

The ULTRAREVIEW suite for the invariant `nics_risk_subsystem_spec_v1.3.md`
§14:965 states verbatim: *"Every reservation reaches exactly one terminal
release."* Not a second copy of `test_reservations.py`, which owns the ledger's
own guards and the frozen-port conformance. Everything here is a control over a
defect this arc MEASURED in the shipped tree, and each one runs the UNPROTECTED
half first so the bad outcome is seen to appear before it is seen to be gone
(the ARC 035 self-masking lesson).

## What would have to be true for this file to measure nothing (`debug.md` §7.12)

1. **The raising-sink control could use a sink that raises before `_book`
   mutates anything.** Then the "no leak" assertion is about a ledger that never
   booked, which is `test_limiter_gate.py::test_a_LEDGER_THAT_CANNOT_TAKE_...`'s
   position and is exactly why that test did not catch F-B1. *Closed:* the
   raising sink here raises from `enqueue`, which `_book` reaches only AFTER the
   four stores and Σ are mutated, and the unprotected half proves the leak
   appears there.
2. **The real-boundary control could import the production module instead of the
   tree under test.** D3.344: a `subprocess.run` with no `env=` inherits
   `PYTHONPATH` and defeats every plant. *Closed:* the child is given an explicit
   `env=` built by filtering the real tree's entries out and keeping the rest,
   and the child PRINTS the `__file__` it imported, which is asserted here.
3. **The Σ-drift control could assert a bound it computed from the same run.**
   *Closed:* the bound asserted is `AUDIT_TOLERANCE` as the module ships it, and
   the control's claim is that the tolerance is CROSSED — a falsifiable
   direction, with the op count reported rather than compared to itself.
4. **The path census could derive its expected set from `TerminalPath`.** Then it
   would prove the enum covers the enum. *Closed:* the expected set is the
   RECORDED baseline of what production wires today (D3.358), the census reads
   call sites by AST, and the can-fail half synthesises a release site for an
   uncovered path and requires the census to SEE it.
5. **The race control could be single-threaded.** *Closed:* real
   `threading.Thread`s over a real `threading.Barrier`, with the switch interval
   driven to its floor, and the iteration count reported.

Every control asserts the REASON — a message, a field or the arithmetic — never
the exception type or an exit code alone (check contract v2 §11).
"""
# pylint: disable=invalid-name,redefined-outer-name,protected-access

from __future__ import annotations

import ast
import math
import os
import random
import subprocess
import sys
import threading
from pathlib import Path

import pytest  # pylint: disable=import-error

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from nixrisk.reservations import (  # pylint: disable=wrong-import-position
    AUDIT_TOLERANCE,
    MIN_MARGIN,
    Reservation,
    ReservationLedger,
)
from nixrisk.seam import (  # pylint: disable=wrong-import-position
    EventKind,
    ProposedOrder,
    Side,
    StopMode,
    TerminalPath,
)

NIXRISK = REPO / "scripts" / "nixrisk"
LEDGER_SITE = "scripts/nixrisk/reservations.py"


class Recorder:
    """A Plane-1 sink that keeps every row. §9's `enqueue`, no durability."""

    def __init__(self) -> None:
        self.rows: list[object] = []

    def enqueue(self, row: object) -> None:
        """§9's hot half: a bounded append, no durability."""
        self.rows.append(row)

    def sync_to_disk(self) -> int:
        """Nothing is made durable here."""
        return 0

    def pending(self) -> int:
        """Every row is pending — this sink never syncs."""
        return len(self.rows)


class RefusingSink(Recorder):
    """A Plane-1 sink that REFUSES the take row, the way a full WAL does.

    `nixrisk.wal.Plane1Wal.enqueue` raises `DiskCritical` when the WAL is
    disk-critical or the append fails (§12.4). The message is asserted by the
    controls below, so a refusal from anywhere else cannot pass for this one.
    """

    def __init__(self, refuse: EventKind) -> None:
        super().__init__()
        self.refuse = refuse

    def enqueue(self, row: object) -> None:
        """Refuse one §12.10 kind; record the rest."""
        if getattr(row, "kind", None) is self.refuse:
            raise OSError("WAL is DISK-CRITICAL: refusing to append")
        super().enqueue(row)


class _Silent:
    """A Plane-1 sink that accepts everything and keeps nothing."""

    def enqueue(self, row: object) -> None:
        """Accept and discard. Used only to suspend the append, never to test."""

    def sync_to_disk(self) -> int:
        """Nothing to sync."""
        return 0

    def pending(self) -> int:
        """Nothing pending."""
        return 0


class PreRepairLedger(ReservationLedger):
    """The ledger as it BEHAVED before F-B1: stores mutated, then the append fails.

    The UNPROTECTED half. A control that only ever runs the repaired half proves
    nothing (ARC 035, measured three times).

    Reconstructed from the parent's own pieces rather than by copying its `_book`
    body: a second copy of the money arithmetic in a test file is exactly what
    pylint R0801 is right about, and it would go stale silently. The parent now
    withdraws on a refused append, so the append is SUSPENDED for the parent's
    call — nothing raises, the four stores and Σ are mutated exactly as before —
    and the refusal the real sink would have raised is then raised from the real
    sink. The observable state is identical: mutated stores, Σ incremented, and
    an exception out of `take`.
    """

    def _book(self, order: ProposedOrder, margin: float, now: float) -> Reservation:
        """Book with the append suspended, then let the real sink refuse."""
        real, self._plane1 = self._plane1, _Silent()
        try:
            reservation = super()._book(order, margin, now)
        finally:
            self._plane1 = real
        self._emit(EventKind.RESERVATION_TAKEN, reservation, "approved", now)
        return reservation


def order(tag: str, qty: int = 4, per_contract: float = 1234.5) -> ProposedOrder:
    """One §3 proposal, already sized, with a non-round positive margin."""
    return ProposedOrder(
        client_order_id=tag,
        strategy_id="strat-1",
        symbol="ESZ6",
        side=Side.LONG,
        qty=qty,
        margin_per_contract=per_contract,
        stop_ticks=20,
        stop_mode=StopMode.FIXED,
        signal_ts=1000.0,
    )


# ==========================================================================
# F-B1 — a `take` whose Plane-1 append REFUSES must take nothing
# ==========================================================================


def test_a_REFUSED_PLANE1_APPEND_LEAKS_the_reservation_BEFORE_the_repair() -> None:
    """THE UNPROTECTED HALF. The bad outcome must be seen, or nothing is proven.

    `gate.py::GatePass._settle` turns any exception from `take` into a DENY, so a
    ledger that mutated its stores and then raised holds a reservation for an
    order that will never be sent — zero terminal releases, §14 broken in the
    LEAK direction, and `audit()` blind to it.
    """
    ledger = PreRepairLedger(RefusingSink(EventKind.RESERVATION_TAKEN))

    with pytest.raises(OSError, match="DISK-CRITICAL"):
        ledger.take(order("c-1"), 1.0)

    assert len(ledger.outstanding()) == 1, (
        "the pre-repair leak did not reproduce, so the repaired half below is "
        "not being compared against anything"
    )
    assert ledger.total_reserved() == pytest.approx(4938.0), ledger.audit()
    audit = ledger.audit()
    assert audit.drift == 0.0 and audit.material is False, (
        f"a LEAK must break NO arithmetic identity — drift {audit.drift!r} — "
        "which is why §11.7's reconcile could never have caught this one"
    )


def test_a_REFUSED_PLANE1_APPEND_TAKES_NOTHING() -> None:
    """THE REPAIRED HALF (F-B1). `take` is all-or-nothing.

    Σ is compared BIT-IDENTICALLY, not approximately: the undo assigns the saved
    value rather than subtracting the margin back, because `+=` then `-=` over
    binary floats does not return to the same bits and a repair for a leak must
    not introduce the drift §11.7 exists to watch.
    """
    sink = RefusingSink(EventKind.CANCEL)  # nothing refused yet
    ledger = ReservationLedger(sink)
    held = ledger.take(order("c-held", qty=3, per_contract=987.25), 1.0)
    sink.refuse = EventKind.RESERVATION_TAKEN  # now the WAL goes disk-critical
    sigma_before = ledger.total_reserved()

    with pytest.raises(OSError, match="DISK-CRITICAL"):
        ledger.take(order("c-refused"), 2.0)

    assert [res.client_order_id for res in ledger.outstanding()] == ["c-held"], (
        "a take whose §12.10 row was refused left a reservation behind — no "
        "terminal event can ever arrive for an order the gate then DENIED"
    )
    assert ledger.total_reserved() == sigma_before, (
        f"Σ is {ledger.total_reserved()!r} and was {sigma_before!r} — the undo "
        "must restore the exact bits, not re-derive them"
    )
    assert held.reservation_id in {res.reservation_id for res in ledger.outstanding()}
    audit = ledger.audit()
    assert audit.drift == 0.0 and audit.taken == 1, audit


def test_a_WITHDRAWN_TAKE_frees_the_CLIENT_ORDER_ID_for_a_retry() -> None:
    """The withdrawal is complete: the id is not left poisoned by a refusal.

    A rollback that forgot `_by_order` would leave the id looking live, so the
    §12.4 retry after the disk recovers would be refused as a duplicate and the
    strategy would be locked out of that order forever.
    """
    sink = RefusingSink(EventKind.RESERVATION_TAKEN)
    ledger = ReservationLedger(sink)
    with pytest.raises(OSError, match="DISK-CRITICAL"):
        ledger.take(order("c-1"), 1.0)

    sink.refuse = EventKind.CANCEL  # the disk recovered
    taken = ledger.take(order("c-1"), 2.0)

    assert taken.client_order_id == "c-1"
    assert ledger.total_reserved() == pytest.approx(4938.0)
    assert len(ledger.outstanding()) == 1, ledger.outstanding()


def test_the_REAL_PLANE1_WAL_under_a_REAL_KERNEL_REFUSAL_takes_nothing(
    tmp_path: Path,
) -> None:
    """F-B1 at the REAL boundary: `Plane1Wal`, a real `write(2)`, a real EFBIG.

    Driven in a CHILD PROCESS because `RLIMIT_FSIZE` is process-wide and would
    otherwise refuse pytest's own writes. The child is handed an EXPLICIT `env=`
    with the real tree's `scripts` filtered out of `PYTHONPATH` and everything
    else kept (D3.344: an inherited `PYTHONPATH` defeated every plant in ARC 037;
    replacing it wholesale drops the binding census's `sitecustomize`), and it
    PRINTS the `__file__` it imported so this assertion is a measurement.
    """
    child = tmp_path / "drive.py"
    child.write_text(
        "import os, resource, signal, sys\n"
        f"sys.path.insert(0, {str(REPO / 'scripts')!r})\n"
        "from nixrisk import reservations as R\n"
        "from nixrisk.wal import Plane1Wal, DiskCritical\n"
        "from nixrisk.seam import ProposedOrder, Side, StopMode\n"
        "print('IMPORTED', R.__file__)\n"
        "signal.signal(signal.SIGXFSZ, signal.SIG_IGN)\n"
        "soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)\n"
        "resource.setrlimit(resource.RLIMIT_FSIZE, (400, hard))\n"
        f"wal = Plane1Wal({str(tmp_path / 'plane1.wal')!r})\n"
        "led = R.ReservationLedger(wal)\n"
        "def o(tag):\n"
        "    return ProposedOrder(client_order_id=tag, strategy_id='s', symbol='ES',\n"
        "        side=Side.LONG, qty=4, margin_per_contract=1000.0, stop_ticks=40,\n"
        "        stop_mode=StopMode.FIXED, signal_ts=1.0)\n"
        "refused = 0\n"
        "for i in range(6):\n"
        "    try:\n"
        "        led.take(o(f'c-{i}'), 1.0)\n"
        "    except DiskCritical as exc:\n"
        "        refused += 1\n"
        "        big = 'errno=27' in str(exc) or 'File too large' in str(exc)\n"
        "        print('REFUSED', type(exc).__name__, big)\n"
        "print('WAL_STATE', wal._state.value)\n"
        "print('REFUSED_COUNT', refused)\n"
        "print('OUTSTANDING', len(led.outstanding()))\n"
        "print('SIGMA', repr(led.total_reserved()))\n"
        "print('ENQUEUED', wal.enqueued)\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    real = str(Path("/home/bbt/nix") / "scripts")
    kept = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p and p != real]
    env["PYTHONPATH"] = os.pathsep.join(kept)
    done = subprocess.run(
        [sys.executable, str(child)],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    out = dict(
        line.split(" ", 1) for line in done.stdout.strip().splitlines() if " " in line
    )
    assert out["IMPORTED"] == str(REPO / "scripts" / "nixrisk" / "reservations.py"), (
        f"the child imported {out['IMPORTED']} — D3.344's staged-tree defeat, "
        "and every figure below would be about the wrong tree"
    )
    assert out["WAL_STATE"] == "disk_critical", done.stdout
    assert int(out["REFUSED_COUNT"]) >= 1, done.stdout
    assert int(out["OUTSTANDING"]) == int(out["ENQUEUED"]), (
        f"the real WAL accepted {out['ENQUEUED']} take row(s) and the ledger "
        f"holds {out['OUTSTANDING']} reservation(s) — every reservation the "
        "ledger holds must have a §12.10 row, and every refused row must have "
        "withdrawn its reservation (§14, F-B1)"
    )
    assert float(out["SIGMA"]) == pytest.approx(4000.0 * int(out["ENQUEUED"]))


# ==========================================================================
# F-B3 — the TERMINAL-PATH CENSUS: which release paths does production wire?
# ==========================================================================

#: The RECORDED baseline of §3 release paths a PRODUCTION module actually books,
#: measured by AST over `scripts/nixrisk/*.py`. NOT derived from `TerminalPath` —
#: deriving it from the code and then proving the code covers it is circular. A
#: one-way ratchet: a path that gains a production release site is a FAIL telling
#: you to move it here, and a path that LOSES one is the leak.
#:
#: **MOVED IN ARC 044, in the progress direction, and this is the second half of
#: the ratchet doing its job.** ARC 038 / B recorded three wired paths and three
#: with no production caller at all (CHECK-DEBT D3.358). ARC 044 landed
#: `scripts/nixrisk/outcomes.py` — the Limiter's non-fill terminal-event handler
#: — and the ratchet FAILED first, naming the three paths that had gained a
#: caller and refusing to pass until this line moved. It is recorded here, not
#: computed, for exactly the reason above: a baseline that derives itself from
#: the tree agrees with any tree.
WIRED_PATHS: frozenset[str] = frozenset(
    {
        "FILL",
        "BLACKOUT_ONSET",
        "HALT_ONSET",
        # ARC 044: outcomes.py::OrderOutcomes.
        "CANCEL",
        "REJECT",
        "PENDING_TIMEOUT",
    }
)

#: EMPTY since ARC 044: every release path §3:151 names now has at least one
#: production release site. It stays as a NAMED, ASSERTED set rather than being
#: deleted, because the assertion `declared - wired == UNWIRED_PATHS` is what
#: turns a path that LOSES its caller back into a loud failure — deleting the
#: empty set would delete the leak detector with it. D3.358 is discharged; a
#: non-empty set here again is a regression on §14's at-least-one half.
UNWIRED_PATHS: frozenset[str] = frozenset()


def _via_argument(node: ast.Call) -> ast.expr | None:
    """The `via` argument of a `resolve`/`release` call, or `None` if not one."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    if func.attr not in ("resolve", "release") or len(node.args) < 2:
        return None
    return node.args[1]


def _literal_member(via: ast.expr) -> str | None:
    """`TerminalPath.X` spelled literally at the call site, or `None`."""
    if (
        isinstance(via, ast.Attribute)
        and isinstance(via.value, ast.Name)
        and via.value.id == "TerminalPath"
    ):
        return via.attr
    return None


def _onset_members(tree: ast.Module) -> list[str]:
    """The onset causes a guarded, non-literal `via` can carry in this module.

    `flatten.py::cancel_entries_on_onset` takes `cause` and refuses anything
    outside its module-level `_ONSET_CAUSES` frozenset before calling `resolve`,
    so those two members — and only those — are credited for that call site.
    """
    named = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "TerminalPath"
    }
    return sorted(named & {"BLACKOUT_ONSET", "HALT_ONSET"})


def _sites_in(path: Path, found: dict[str, list[str]]) -> None:
    """Add one module's release call sites to `found`, in place."""
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    onset = _onset_members(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        via = _via_argument(node)
        if via is None:
            continue
        site = f"{path.name}:{node.lineno}"
        member = _literal_member(via)
        if member is not None:
            found.setdefault(member, []).append(site)
        elif path.name == "flatten.py":
            for cause in onset:
                found.setdefault(cause, []).append(site)
        else:
            found.setdefault("<unresolved>", []).append(site)


def _release_sites(root: Path) -> dict[str, list[str]]:
    """`TerminalPath` member -> production `resolve`/`release` call sites.

    Reads the `via` argument STATICALLY. Anything neither literal nor resolved
    through the frozenset that constrains it is reported under `"<unresolved>"`,
    so it cannot be silently credited to nothing.
    """
    found: dict[str, list[str]] = {}
    for path in sorted(root.glob("*.py")):
        _sites_in(path, found)
    return found


def test_the_PRODUCTION_RELEASE_PATH_SET_matches_the_RECORDED_baseline() -> None:
    """§14 needs a release on every path §3 names; three paths have no caller.

    The ratchet, in both directions. This is NOT a claim that the ledger leaks —
    it does not — it is the measurement that §14 is only WIRED for three of the
    six paths the frozen seam declares, which is the half `check_reservation_
    lifecycle` says in its own evidence it cannot see.
    """
    sites = _release_sites(NIXRISK)
    assert "<unresolved>" not in sites, (
        f"a production release call whose cause this census cannot resolve: "
        f"{sites['<unresolved>']} — an unreadable site would be credited to "
        "nothing and the ratchet would silently loosen"
    )
    wired = frozenset(sites)
    declared = frozenset(member.name for member in TerminalPath)

    assert wired <= declared, f"a release booked under a non-member: {wired - declared}"
    assert wired == WIRED_PATHS, (
        f"production wires {sorted(wired)} and this file records "
        f"{sorted(WIRED_PATHS)}. A path that GAINED a caller is progress and the "
        "baseline must move (D3.358); a path that LOST one is a §14 leak on that "
        f"path. Sites: {dict(sites)}"
    )
    assert declared - wired == UNWIRED_PATHS, (
        f"the unwired set moved to {sorted(declared - wired)} — D3.358 enumerates "
        f"{sorted(UNWIRED_PATHS)}"
    )
    for member in sorted(WIRED_PATHS):
        assert sites[member], member


def test_the_CENSUS_SEES_a_release_site_APPEAR(tmp_path: Path) -> None:
    """§0a: the census's can-fail proof, in the direction that matters.

    A census whose answer never changes is furniture. A synthesised production
    module booking `TerminalPath.REJECT` must show up as REJECT covered — if it
    does not, the empty entries above are about the instrument and not the tree.
    """
    staged = tmp_path / "nixrisk"
    staged.mkdir()
    (staged / "rejects.py").write_text(
        "from nixrisk.seam import TerminalPath\n"
        "def on_reject(ledger, coid, now):\n"
        "    return ledger.resolve(coid, TerminalPath.REJECT, now)\n",
        encoding="utf-8",
    )

    sites = _release_sites(staged)

    assert "REJECT" in sites, f"the census cannot see a release site at all: {sites}"
    assert sites["REJECT"] == ["rejects.py:3"], sites
    assert frozenset(sites) != WIRED_PATHS, (
        "the census returned the recorded baseline over a staged tree that does "
        "not contain it — it is reading the wrong directory"
    )


def test_the_CENSUS_SEES_a_release_site_DISAPPEAR(tmp_path: Path) -> None:
    """The other direction: removing §3's FILL release must drop FILL."""
    staged = tmp_path / "nixrisk"
    staged.mkdir()
    body = (NIXRISK / "fills.py").read_text(encoding="utf-8")
    assert "TerminalPath.FILL," in body, "the FILL site moved; this control is stale"
    (staged / "fills.py").write_text(
        body.replace("TerminalPath.FILL,", "None,", 1), encoding="utf-8"
    )

    sites = _release_sites(staged)

    assert "FILL" not in sites, (
        f"the census still credits FILL after its only production site was "
        f"removed: {sites}"
    )
    assert "<unresolved>" in sites, sites


# ==========================================================================
# F-B4 — AUDIT_TOLERANCE is not a BOUND on Σ's float drift
# ==========================================================================


def test_SIGMA_DRIFT_CROSSES_the_AUDIT_TOLERANCE_with_NO_DEFECT_present() -> None:
    """F-B4. `material` goes True on float noise alone, at 1-5 instruments.

    `reservations.py`'s module docstring claims the drift *"is bounded at ~1e-13
    for account-scale figures"*. It is not bounded: `_sigma` is an incremental
    aggregate whose lifetime is the process's, so its representation error is a
    RANDOM WALK that grows without limit, while `AUDIT_TOLERANCE` is a fixed
    absolute floor. Measured here over a legitimate drive — every margin a real
    futures figure, at most five concurrent reservations (`CLAUDE.md`'s scope),
    every take released exactly once, no defect anywhere.

    The direction is what makes this falsifiable: the control REQUIRES the
    crossing. A ledger whose drift really were bounded at 1e-13 would fail it.
    """
    rnd = random.Random(1)  # nosec B311 — a REPRODUCIBLE drive, not a secret
    ledger = ReservationLedger(Recorder())
    live: list[str] = []
    crossed_at = 0
    for step in range(200_000):
        if len(live) < 5 and (not live or rnd.random() < 0.5):
            tag = f"c-{step}"
            ledger.take(
                order(tag, rnd.randint(1, 5), rnd.uniform(1200.0, 24000.0)),
                float(step),
            )
            live.append(tag)
        elif live:
            ledger.resolve(
                live.pop(rnd.randrange(len(live))), TerminalPath.FILL, float(step)
            )
        if ledger.audit().material:
            crossed_at = step + 1
            break

    audit = ledger.audit()
    assert crossed_at, (
        "200000 legitimate operations did not cross AUDIT_TOLERANCE — if the "
        "aggregate really is bounded, this control is the thing that is stale "
        "and D3.359 can be discharged"
    )
    assert abs(audit.drift) > AUDIT_TOLERANCE, audit
    assert abs(audit.drift) > 1e-13 * 100, (
        f"drift {audit.drift!r} against the module docstring's claimed ~1e-13 "
        f"bound, reached after {crossed_at} operations (D3.359)"
    )
    assert len(ledger.outstanding()) == len(live), "the drive itself leaked"
    assert audit.released == audit.taken - len(live), audit


def test_the_TOLERANCE_still_CANNOT_HIDE_the_smallest_double_release() -> None:
    """The other side of F-B4: the floor is too tight, never too loose.

    D3.359 is a FALSE-POSITIVE risk, not a false-negative one, and saying so is
    the difference between a finding and a scare. A double release of the
    SMALLEST admissible reservation is six orders above the tolerance.
    """
    assert MIN_MARGIN > AUDIT_TOLERANCE * 1e5, (MIN_MARGIN, AUDIT_TOLERANCE)
    ledger = ReservationLedger(Recorder())
    ledger.take(order("c-1", qty=1, per_contract=MIN_MARGIN), 1.0)
    ledger._sigma -= MIN_MARGIN  # the arithmetic footprint of a double release

    audit = ledger.audit()

    assert audit.material is True, audit
    assert abs(audit.drift) == pytest.approx(MIN_MARGIN), audit


# ==========================================================================
# §15 C1 — the double-spend race, driven with REAL THREADS
# ==========================================================================

RACE_ITERATIONS = 600


def _race_fill(
    ledger: ReservationLedger, sync: threading.Barrier, out: dict[str, object]
) -> None:
    """`fills.py`'s shape: `resolve` keyed on the client_order_id.

    At MODULE scope, not a closure in the loop: a closure over a loop variable is
    a real defect class (ruff B023) and the two callers must be the shapes
    production uses, not two spellings of one.
    """
    sync.wait()
    try:
        out["fill"] = ledger.resolve("c-1", TerminalPath.FILL, 2.0)
    except BaseException as exc:  # noqa: BLE001  # pylint: disable=broad-except
        out["fill"] = exc


def _race_cancel(
    ledger: ReservationLedger,
    reservation_id: str,
    sync: threading.Barrier,
    out: dict[str, object],
) -> None:
    """`blackout.py`'s shape: `release` keyed on the reservation_id."""
    sync.wait()
    try:
        out["cancel"] = ledger.release(reservation_id, TerminalPath.BLACKOUT_ONSET, 2.0)
    except BaseException as exc:  # noqa: BLE001  # pylint: disable=broad-except
        out["cancel"] = exc


def test_a_FILL_RACING_a_BLACKOUT_CANCEL_releases_EXACTLY_ONCE() -> None:
    """§15 C1: *"release on every terminal path (double-spend race closed)"*.

    Two production shapes on ONE reservation, concurrently: `fills.py`'s
    `resolve(client_order_id, FILL, …)` and `blackout.py`'s
    `release(reservation_id, BLACKOUT_ONSET, …)`. Both callers believe they own
    the terminal transition. Real threads, a real barrier, the switch interval at
    its floor to maximise interleaving.

    What is asserted is the ARITHMETIC, not which caller won: Σ back to zero, one
    RELEASED record, nothing outstanding, and §11.7 immaterial. A caller may
    legitimately see a refusal, a `DoubleRelease`, an `UnknownReservation` or —
    D3.360 — a bare `KeyError` from the window between `_settle`'s two `del`s.
    None of those may move Σ twice.
    """
    original = sys.getswitchinterval()
    sys.setswitchinterval(1e-9)
    outcomes: dict[str, int] = {}
    try:
        for _ in range(RACE_ITERATIONS):
            ledger = ReservationLedger(Recorder())
            taken = ledger.take(order("c-1"), 1.0)
            barrier = threading.Barrier(2)
            results: dict[str, object] = {}

            threads = [
                threading.Thread(target=_race_fill, args=(ledger, barrier, results)),
                threading.Thread(
                    target=_race_cancel,
                    args=(ledger, taken.reservation_id, barrier, results),
                ),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
                assert not thread.is_alive(), "a racing caller wedged"

            key = "+".join(sorted(type(v).__name__ for v in results.values()))
            outcomes[key] = outcomes.get(key, 0) + 1
            released = ledger.released()
            audit = ledger.audit()
            assert len(released) == 1, (
                f"{len(released)} RELEASED record(s) for one reservation — §14 "
                f"says exactly one. outcomes {results}"
            )
            assert not ledger.outstanding(), (
                f"the reservation is still TAKEN after two terminal events: "
                f"{ledger.outstanding()} / {results}"
            )
            assert ledger.total_reserved() == 0.0, (
                f"Σ is {ledger.total_reserved()!r} with nothing outstanding — a "
                f"negative figure is the DOUBLE RELEASE §15 C1 closed. {results}"
            )
            assert audit.material is False, (audit, results)
            assert audit.released == 1 and audit.taken == 1, (audit, results)
    finally:
        sys.setswitchinterval(original)

    assert sum(outcomes.values()) == RACE_ITERATIONS, outcomes
    assert len(outcomes) >= 1, outcomes


def test_the_RACE_CONTROL_would_SEE_a_double_release() -> None:
    """§0a for the race: the assertions above must be able to fail.

    The race itself cannot be made to break the ledger on demand, so the control
    is proven against the ARITHMETIC FOOTPRINT a won race would leave — Σ
    decremented twice for one commitment — introduced directly. If this passes
    silently the loop above is asserting nothing.
    """
    ledger = ReservationLedger(Recorder())
    taken = ledger.take(order("c-1"), 1.0)
    ledger.resolve("c-1", TerminalPath.FILL, 2.0)
    ledger._sigma -= taken.margin  # what a second settle would have done

    audit = ledger.audit()

    assert ledger.total_reserved() != 0.0
    assert ledger.total_reserved() == pytest.approx(-taken.margin)
    assert audit.material is True, audit
    assert audit.drift == pytest.approx(-taken.margin), audit
    assert math.isclose(abs(audit.drift), taken.margin), audit
