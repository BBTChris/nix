#!/usr/bin/env python3
"""§12.4's ladder, measured against a Postgres that really stopped.

Subjects: `scripts/nixrisk/degraded.py`, `scripts/plane1_degraded_drill.py`.

Authority — `docs/nics_risk_subsystem_spec_v1.3.md` §12.10 (Plane 1, **Limiter
sole writer, no new writers, ever**), §12.4 (*Degraded persistence ≠ degraded
trading*; **disk-critical** ⇒ HALT new entries, open positions remain
protected), §12.9 (the push alert tiers), §9 (the event-sourced write path).

Schema — `databases/schema/plane1.sql`, frozen by `docs/nix_plane1_schema_spec.md`;
that document's §2.2 is the ordering authority and the exactly-once key. Kept in
its own paragraph deliberately: `check_spec_citations` attributes a `§x` to the
NEAREST document alias in the enclosing block, and with both files named in one
paragraph it read `§12.10` against the schema spec, which has no such section.

Instrument doctrine — `docs/nix_check_contract.md` §4, §5, §17, §18.

ONE property (§5.5): *§12.4's ladder holds against a Postgres that really went
away — the RECORD degrading does not stop the trading, a WAL that cannot append
stops new entries at the gate while an armed stop still fires, and a reconnect
flushes the backlog in WAL order, exactly once.*

**What this gate does NOT own, and must not be read as covering.**
`check_plane1_wal` owns the WAL's own behaviour — the observed `fsync` syscall,
a SIGKILLed process, a torn tail, and §12.4's two states told apart **against an
in-memory `RecordingSink`**. `check_plane1_schema` owns the catalog: append-only
by privilege, the §12.10 inventory, the unique index's EXISTENCE. Neither of them
ever stops a server. This gate is the one that does, and it is the only one whose
greens are about a real outage.

---

## debug.md §7.12 — WHAT WOULD HAVE TO BE TRUE FOR THIS GATE TO PASS WHILE
## MEASURING NOTHING

1. **POSTGRES NEVER GOES DOWN.** The outage in this tree before this arc was
   `RecordingSink.fail_with = RuntimeError("planted Postgres outage: connection
   refused")` — an attribute, not a server. Closed by ARM 1, which does not take
   the drill's word for it: the postmaster's PID must be **absent from `/proc`**
   after the stop, the unix socket must be gone, and psql's own connect must
   have failed with an error naming that socket.

2. **THE OUTAGE IS A COURTEOUS SHUTDOWN.** `pg_ctl stop -m fast` checkpoints and
   flushes, so *"no rows were lost"* across it is true **by construction** — the
   SIGKILL/fsync trap one layer up. Closed by ARM 7: the stop mode must be
   `immediate` **and the restarted server must have actually run recovery**, with
   a CONTROL — a graceful stop whose next boot must print **no** recovery banner.
   Without that control, `recovered()` could be a matcher that matches anything.

3. **"TRADING CONTINUES" IS ONE `if` OVER AN ENUM.** `admits_new_entries()`
   returning True proves the enum, not the business. Closed by ARM 2, which
   requires **approvals out of `gate.GatePass.evaluate`**, **reservations taken
   by the real `ReservationLedger`**, and a **stop that ratcheted and then
   breached**, all while the server is down.

4. **"OPEN STOPS STILL FIRE" IS `protective_exit_allowed()`.** That method is
   `return True, "..."` with no branch in it — it cannot answer False in any
   state, so an assertion over it is an assertion over a literal (`CHECK-A7`: a
   classifier whose output is a constant decides nothing). **This gate never
   reads it.** ARM 6 requires instead that, at the instant an append probe
   raises `DiskCritical`, an armed stop is breached and returned.

5. **EVERYTHING IS DENIED.** A gate that denied every order would satisfy ARM 4
   and be worthless. Closed by ARM 5: the identical child, differing in one
   `setrlimit` call, must APPROVE the identical order and take a reservation.

6. **THE FLUSH IS NEVER SHOWN A DUPLICATE.** Closed by ARM 9 in both directions:
   a plain re-INSERT of a committed row must come back **SQLSTATE 23505 naming
   the `(natural_key, occurred_at)` key** — the code alone is a shared namespace
   and `plane1_positions_pkey` is a 23505 too — and a re-delivered committed
   group through the real sink must insert **0** rows with the log's count
   unchanged.

7. **ORDERING IS ASSERTED FROM THE WRONG AUTHORITY.** `event_id` is assigned at
   INSERT; commit order under group-commit is batch order. Closed by ARM 8,
   which requires the `natural_key` sequence read `ORDER BY wal_seq` to equal the
   sequence `recover()` reads off the WAL's own bytes.

8. **THE POPULATION IS EMPTY.** Zero rows committed, zero buffered, zero
   approvals — every arm then reports clean over nothing. Closed by the
   non-vacuity floors below, checked BEFORE any arm contributes a verdict.

9. **THE CLUSTER CANNOT BE BUILT.** `initdb`/`pg_ctl` are not on PATH on Debian
   derivatives and may not be installed at all. `CANNOT_MEASURE` naming the
   missing binaries — §17, deliberately never PASS.

---

## WHAT THIS GATE CANNOT PROVE, STATED RATHER THAN IMPLIED

**IT IS NOT A POWER CUT, AND THE EVIDENCE SAYS SO IN THE FSTYPE.** The ephemeral
datadir lives in the scratch tree, which on this node is a **tmpfs**, where an
`fsync` is a no-op. `-m immediate` proves the postmaster died, its shared buffers
were lost, and crash recovery replayed the WAL; it proves nothing about bytes
reaching a platter. The verdict prints the filesystem so the reach of the claim
is read off the evidence rather than assumed.

**IT IS NOT THE PRODUCTION SINK.** The drill's `PsqlCommitSink` is a
`CommitSinkPort` over the `psql` binary, connecting as **`nix_limiter`** at the
end of the Limiter's own path. It adds no writer (§12.10) and it is not a claim
that the shipped Limiter is wired to a Postgres sink — that wiring is a separate
subject and no green here covers it.

**IT IS NOT THE LIVE DATABASE.** `nix_plane1` on the system cluster is never
touched, started or stopped. Every claim is about a throwaway cluster running the
same frozen `databases/schema/plane1.sql`.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import _preamble  # noqa: F401  pylint: disable=unused-import,wrong-import-order
from nixverify.contract import (
    CheckResult,
    Context,
    Mode,
    Status,
    result_from_defects,
)

# Deliberately duplicated across every checks/check_*.py: `nix_check_contract.md`
# §4.2 requires each check be independently runnable and map status -> exit code
# identically, and doctrine B.2 requires the crash path return CANNOT_MEASURE in
# both. Those blocks are MANDATED to be the same text.
# pylint: disable=duplicate-code
PRIVILEGE = "user"
INTERACTIVE = False
#: Builds, crashes and deletes its OWN ephemeral cluster in a `mkdtemp`. It never
#: stops, starts, reconfigures or connects to the system PostgreSQL cluster, and
#: the cluster it builds sets `listen_addresses=''` so it has no TCP socket at
#: all. Nothing outside the temporary directory changes, so this is not
#: DISRUPTIVE in the contract's sense — and the distinction is worth stating,
#: because "this check kills Postgres" is true and would be alarming without it.
DISRUPTIVE = False

# --- orchestration declarations (read statically, never imported) ---
#: The drill re-executes itself under the venv interpreter for the §12.4
#: disk-critical child.
DEPENDS_ON: tuple[str, ...] = ("check_venv",)
#: Declared honestly and FALSIFIABLY (D3.152: 24 checks already carry a token no
#: observation could contradict). Every one of these is a process this check
#: really spawns, matched by BASENAME:
#: * `subprocess:initdb` / `subprocess:pg_ctl` / `subprocess:postgres` — the
#:   server-side binaries, found under `/usr/lib/postgresql/*/bin` because they
#:   are NOT on PATH on this distribution.
#: * `subprocess:psql` / `subprocess:createdb` — every SQL statement and the
#:   scratch database. Shared with `check_plane1_schema`, which the planner
#:   already reads as non-disjoint.
#: * `subprocess:python3` / `subprocess:python` — the two C2 children, through
#:   `sys.executable`. BOTH spellings: that is `.venv/bin/python` under pytest
#:   and `/usr/bin/python3` under `nix-verify.service`.
#: * `file-write:/tmp` — the scratch root, the ephemeral datadir inside it, and
#:   the WAL files. Removed by absolute-path unlinks, never `shutil.rmtree`.
#: A `postgres:<db>` token was considered and REFUSED for the same reason
#: `check_plane1_schema` refused one: no observation could ever falsify it.
RESOURCES: tuple[str, ...] = (
    "subprocess:initdb",
    "subprocess:pg_ctl",
    "subprocess:postgres",
    "subprocess:psql",
    "subprocess:createdb",
    "subprocess:python3",
    "subprocess:python",
    "file-write:/tmp",
)
TIME_BOUND = True
#: MEASURED on this node (tmpfs scratch, PostgreSQL 18.4): ~2 s for an `initdb`,
#: three postmaster boots, two stops, fourteen trades and two children. Budgeted
#: four times that because an `initdb` on a spinning scratch volume is not 2 s.
EXPECTED_S = 8.0
ON_FAIL = "continue"
CORRECTABLE = False
NON_CORRECTABLE_REASON = (
    "the subject is what the Limiter DOES while its record is degraded. There is "
    "no state on disk to repair, and a 'correction' would mean editing the "
    "persistence path while it is the thing under measurement"
)
ANCHOR = "scripts/nixrisk/degraded.py"
SUBJECTS: tuple[str, ...] = (
    "scripts/nixrisk/degraded.py",
    "scripts/plane1_degraded_drill.py",
)

NAME = "check_plane1_degraded"

#: Non-vacuity floors (`debug.md` §7.12). FLOORS, not today's numbers — a floor
#: that tracked the measurement would move every time the drill did and would
#: never fail.
MIN_COMMITTED_BEFORE_OUTAGE = 8
MIN_BUFFERED_DURING_OUTAGE = 8
MIN_APPROVALS_DURING_OUTAGE = 4
MIN_RESERVATIONS = 4
MIN_DUPLICATES_PLANTED = 1

#: `unique_violation`. Never the whole assertion — see ARM 9.
SQLSTATE_UNIQUE_VIOLATION = "23505"

_SITE_CRASH = "scripts/plane1_degraded_drill.py:EphemeralCluster.crash"
_SITE_GATE = "scripts/nixrisk/degraded.py:PersistenceHaltFlag.is_set"
_SITE_ALERT = "scripts/nixrisk/degraded.py:PersistenceAlerts.__call__"
_SITE_STOPS = "scripts/nixrisk/stops.py:StopBook.breached"
_SITE_SINK = "scripts/plane1_degraded_drill.py:PsqlCommitSink.commit"
_SITE_ORDER = "scripts/nixrisk/degraded.py:Plane1Enqueuer.enqueue"


def _cannot(detail: str, evidence: list[str]) -> CheckResult:
    """CANNOT_MEASURE with whatever was learned before the wall."""
    return CheckResult(
        name=NAME,
        status=Status.CANNOT_MEASURE,
        detail=detail,
        evidence="; ".join(evidence),
    )


def _import_drill() -> tuple[Any, str]:
    """Lazy import so an unimportable subject is CANNOT_MEASURE, not a load error."""
    try:
        import plane1_degraded_drill  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        return None, (
            f"cannot import plane1_degraded_drill under {sys.executable}: {exc!r}"
        )
    return plane1_degraded_drill, ""


# ---------------------------------------------------------------------------
# Arms — each appends `(site, why)` to `defects` or a narration line to `ev`
# ---------------------------------------------------------------------------


def _arm1_the_outage_was_real(result: dict[str, Any], defects: list, ev: list) -> None:
    """ARM 1: the server GONE, proven four ways, not asserted by the drill."""
    crash = result["c1"]["crash"]
    if crash["mode"] != "immediate":
        defects.append(
            (
                _SITE_CRASH,
                (
                    f"the outage was produced with `-m {crash['mode']}`, not "
                    "`immediate`. A graceful shutdown checkpoints and flushes, so "
                    "'no rows were lost' across it is true BY CONSTRUCTION and "
                    "measures nothing — the SIGKILL/fsync trap one layer up"
                ),
            )
        )
        return
    if crash["pid_alive_after_stop"] or crash["socket_present_after_stop"]:
        defects.append(
            (
                _SITE_CRASH,
                (
                    f"postmaster {crash['postmaster_pid']} is still in /proc "
                    f"({crash['pid_alive_after_stop']}) or its socket still exists "
                    f"({crash['socket_present_after_stop']}) after the stop — the "
                    "server did not go away, so nothing below is about an outage"
                ),
            )
        )
        return
    if crash["connect_returncode"] == 0 or "socket" not in crash["connect_stderr"]:
        defects.append(
            (
                _SITE_CRASH,
                (
                    f"psql still connected after the stop "
                    f"(rc={crash['connect_returncode']}, "
                    f"stderr={crash['connect_stderr'][:160]!r}) — the ATTEMPT is "
                    "the claim, and an outage nobody's client noticed is not one"
                ),
            )
        )
        return
    ev.append(
        f"OUTAGE REAL: postmaster {crash['postmaster_pid']} stopped -m immediate, "
        f"absent from /proc, socket gone, psql rc={crash['connect_returncode']} "
        f"({crash['connect_stderr'].splitlines()[0][:90] if crash['connect_stderr'] else ''}); "
        f"datadir filesystem {crash['datadir_filesystem']} — NOT a power cut"
    )


def _arm2_trading_continued(result: dict[str, Any], defects: list, ev: list) -> None:
    """ARM 2: §12.4's headline, and the direction people get backwards."""
    c1 = result["c1"]
    approvals = [
        d
        for d in c1["decisions_during_outage"] + c1["decisions_after_state_degraded"]
        if d["decision"] == "approve"
    ]
    denials = [
        d
        for d in c1["decisions_during_outage"] + c1["decisions_after_state_degraded"]
        if d["decision"] != "approve"
    ]
    if denials:
        defects.append(
            (
                _SITE_GATE,
                (
                    f"§3's pass DENIED {len(denials)} proposal(s) while Postgres was "
                    f"down: {denials[:2]!r}. §12.4's whole sentence is 'degraded "
                    "persistence ≠ degraded trading' — halting here turns a "
                    "Postgres restart into a stopped business, and it is the "
                    "direction this gets got backwards"
                ),
            )
        )
        return
    if len(approvals) < MIN_APPROVALS_DURING_OUTAGE:
        defects.append(
            (
                _SITE_GATE,
                (
                    f"only {len(approvals)} proposal(s) were evaluated during the "
                    f"outage, below the floor of {MIN_APPROVALS_DURING_OUTAGE} — "
                    "'trading continued' would be a statement about a small set"
                ),
            )
        )
        return
    if (
        c1["state_during_outage"] != c1["expected_state"]
        or not c1["admits_new_entries"]
    ):
        defects.append(
            (
                _SITE_GATE,
                (
                    f"with the server gone the WAL reported state "
                    f"{c1['state_during_outage']!r} (expected "
                    f"{c1['expected_state']!r}) and admits_new_entries="
                    f"{c1['admits_new_entries']} — a real Postgres outage did not "
                    "reach §12.4's SINK_DEGRADED branch"
                ),
            )
        )
        return
    if c1["backlog_during_outage"] < MIN_BUFFERED_DURING_OUTAGE:
        defects.append(
            (
                _SITE_SINK,
                (
                    f"the outage produced a backlog of "
                    f"{c1['backlog_during_outage']}, below the floor of "
                    f"{MIN_BUFFERED_DURING_OUTAGE} — §12.4 says the WAL BUFFERS "
                    "through a Postgres outage, and an empty backlog means "
                    "nothing was buffered"
                ),
            )
        )
        return
    if c1["reservations_outstanding"] < MIN_RESERVATIONS:
        defects.append(
            (
                _SITE_GATE,
                (
                    f"{c1['reservations_outstanding']} reservation(s) were "
                    f"outstanding, below the floor of {MIN_RESERVATIONS} — §3's "
                    "reservation take is part of 'trading continues', and a gate "
                    "that approved without reserving approved nothing real"
                ),
            )
        )
        return
    if not c1["stop_ratcheted"] or not c1["stop_breached_during_outage"]:
        defects.append(
            (
                _SITE_STOPS,
                (
                    f"the live stop ratcheted {c1['stop_ratcheted']} time(s) and "
                    f"breached {c1['stop_breached_during_outage']!r} with the "
                    "server down — 'stops read memory, not disk' has to be "
                    "MOVEMENT and a TRIGGER, not a method that returns True"
                ),
            )
        )
        return
    ev.append(
        f"TRADING CONTINUED: {len(approvals)} approval(s) out of GatePass with "
        f"Postgres gone, {c1['reservations_outstanding']} reservation(s) held "
        f"(Σ {c1['sum_reserved']}), {c1['backlog_during_outage']} row(s) buffering, "
        f"stop ratcheted {c1['stop_armed_level']}→{c1['stop_level_after_ratchet']} "
        f"and breached {c1['stop_breached_during_outage']}"
    )


def _arm3_operator_alerted(result: dict[str, Any], defects: list, ev: list) -> None:
    """ARM 3: §12.9's Warning tier, carrying the cause and the snapshot."""
    warnings = result["c1"]["warning_alerts"]
    if not warnings:
        tiers = [(a["tier"], a["event"]) for a in result["c1"]["all_alerts"]]
        defects.append(
            (
                _SITE_ALERT,
                (
                    f"no `wal_sink_degraded` alert fired for a real Postgres "
                    f"outage; what fired was {tiers!r}. §12.4 requires the "
                    "operator be alerted, and silent buffering is how a backlog "
                    "becomes a surprise"
                ),
            )
        )
        return
    alert = warnings[0]
    if alert["tier"] != "warning":
        defects.append(
            (
                _SITE_ALERT,
                (
                    f"the Postgres-outage alert was raised at tier "
                    f"{alert['tier']!r}. §12.9's Warning list ends with 'Postgres "
                    "down ⇒ degraded persistence' verbatim — this tier is "
                    "transcribed, not chosen, and moving it is a spec change"
                ),
            )
        )
        return
    snapshot = alert["snapshot"]
    missing = [k for k in ("cause", "wal_state", "backlog_rows") if k not in snapshot]
    if missing:
        defects.append(
            (
                _SITE_ALERT,
                (
                    f"the alert carries no {missing!r}. §12.9: alerts carry 'the "
                    "cause and the relevant snapshot values, not just a code, so "
                    "the operator can triage without logging into the box' — a "
                    "tier plus an event name is not that"
                ),
            )
        )
        return
    ev.append(
        f"ALERTED: tier={alert['tier']} event={alert['event']} "
        f"({snapshot.get('citation', '')}), snapshot carries wal_state="
        f"{snapshot.get('wal_state')} backlog_rows={snapshot.get('backlog_rows')}"
    )


def _arm4_disk_critical_halts(result: dict[str, Any], defects: list, ev: list) -> None:
    """ARM 4: §12.4's halting branch, produced by the KERNEL and read at the GATE."""
    critical = result["c2_critical"]
    if critical["state"] != "disk_critical" or "errno=" not in critical["refusal"]:
        defects.append(
            (
                _SITE_GATE,
                (
                    f"the WAL accepted {critical['accepted']} row(s) under "
                    f"RLIMIT_FSIZE and reported state {critical['state']!r} with "
                    f"refusal {critical['refusal'][:120]!r} — a filesystem that "
                    "really said EFBIG did not reach §12.4's disk-critical branch"
                ),
            )
        )
        return
    if critical["gate_decision"] != "deny":
        defects.append(
            (
                _SITE_GATE,
                (
                    f"with the WAL unable to append, §3's pass answered "
                    f"{critical['gate_decision']!r} for a well-formed proposal. "
                    "§12.4 HALTs new entries when there is no audit trail: no "
                    "audit trail, no new risk. A WAL that reports disk-critical "
                    "while the gate keeps approving has reported it to nobody"
                ),
            )
        )
        return
    reason = critical["gate_reason"]
    if "persistence_disk_critical" not in reason or "errno=" not in reason:
        defects.append(
            (
                _SITE_GATE,
                (
                    f"the denial's reason was {reason[:160]!r} — it must NAME the "
                    "rule and carry the errno. §3 and §5 both require a denial to "
                    "name the blocking rule, and a deny whose cause is unnamed is "
                    "indistinguishable from a deny for any other reason"
                ),
            )
        )
        return
    tiers = [(a["tier"], a["event"]) for a in critical["alerts"]]
    if ("critical", "wal_disk_critical") not in tiers:
        defects.append(
            (
                _SITE_ALERT,
                (
                    f"disk-critical raised {tiers!r}, not a CRITICAL "
                    "`wal_disk_critical`. §12.9 names NO tier for disk-critical, "
                    "so this one is derived — but the HALTING failure of the two "
                    "cannot be quieter than the non-halting one"
                ),
            )
        )
        return
    ev.append(
        f"DISK-CRITICAL HALTS: the kernel refused after {critical['accepted']} "
        f"row(s) ({critical['refusal'][-70:]}); GatePass answered "
        f"{critical['gate_decision']} naming {reason[:90]!r}; alert tier "
        f"{[t for t, _ in tiers]}"
    )


def _arm5_the_control(result: dict[str, Any], defects: list, ev: list) -> None:
    """ARM 5: the same child, one syscall different, must APPROVE."""
    control = result["c2_control"]
    if control["state"] != "healthy" or control["refusal"]:
        defects.append(
            (
                _SITE_GATE,
                (
                    f"THE CONTROL FAILED: with no RLIMIT_FSIZE the WAL still "
                    f"reported {control['state']!r} / {control['refusal'][:120]!r} "
                    "— if the control also goes critical, 'the disk refused' "
                    "discriminates nothing"
                ),
            )
        )
        return
    if control["gate_decision"] != "approve" or control["reservations_taken"] < 1:
        defects.append(
            (
                _SITE_GATE,
                (
                    f"THE CONTROL FAILED: the unmutated child's proposal was "
                    f"{control['gate_decision']!r} with "
                    f"{control['reservations_taken']} reservation(s) taken. ARM 4's "
                    "deny is only evidence about the disk beside an approval that "
                    "works — a gate that denies everything satisfies ARM 4 and is "
                    "worthless"
                ),
            )
        )
        return
    ev.append(
        f"CONTROL: identical child without setrlimit ⇒ state {control['state']}, "
        f"gate {control['gate_decision']}, {control['accepted']} row(s) appended, "
        f"{control['reservations_taken']} reservation(s). Plant and control differ "
        "in ONE syscall"
    )


def _arm6_the_stop_still_fires(result: dict[str, Any], defects: list, ev: list) -> None:
    """ARM 6: the half that is easy to fake, measured where it actually lives."""
    critical = result["c2_critical"]
    if critical["append_probe_raised"] != "DiskCritical":
        defects.append(
            (
                _SITE_STOPS,
                (
                    f"at the instant the stop was tested, an append probe raised "
                    f"{critical['append_probe_raised']!r}, not DiskCritical — the "
                    "WAL was not actually refusing, so 'the stop fired anyway' is "
                    "about a healthy system"
                ),
            )
        )
        return
    if not critical["breached_ids"]:
        defects.append(
            (
                _SITE_STOPS,
                (
                    f"a price of {critical['breach_price']} against a stop armed "
                    f"at {critical['armed_level']} breached NOTHING while the WAL "
                    "was disk-critical. §12.4: open positions remain protected "
                    "because stops read MEMORY, not disk — an exit blocked by a "
                    "full disk leaves the book unhedged exactly when the system "
                    "is least able to report it"
                ),
            )
        )
        return
    ev.append(
        f"STOP FIRED ANYWAY: with an append probe raising DiskCritical in the same "
        f"instant, price {critical['breach_price']} breached "
        f"{critical['breached_ids']} armed at {critical['armed_level']}. NOTE: "
        "`Plane1Wal.protective_exit_allowed()` is an unconditional True and this "
        "gate deliberately never reads it"
    )


def _arm7_the_crash_and_what_survived(
    result: dict[str, Any], defects: list, ev: list
) -> None:
    """ARM 7: recovery really ran — with the control that makes that falsifiable."""
    c3 = result["c3"]
    if not c3["recovery_observed"]:
        defects.append(
            (
                _SITE_CRASH,
                (
                    "the restarted server printed no recovery banner, so the "
                    "`-m immediate` stop was indistinguishable from a clean one. "
                    f"log tail: {c3['server_log_tail'][-200:]!r}"
                ),
            )
        )
        return
    if c3["graceful_control"].get("recovery_observed_after_graceful_stop"):
        defects.append(
            (
                _SITE_CRASH,
                (
                    "THE CONTROL FAILED: a graceful `-m fast` stop ALSO produced a "
                    "recovery banner on the next boot, so 'recovery was observed' "
                    "matches anything and discriminates nothing"
                ),
            )
        )
        return
    before = c3["rows_committed_before_outage"]
    if before < MIN_COMMITTED_BEFORE_OUTAGE:
        defects.append(
            (
                _SITE_SINK,
                (
                    f"only {before} row(s) were committed before the crash, below "
                    f"the floor of {MIN_COMMITTED_BEFORE_OUTAGE} — 'the committed "
                    "rows survived' would be a statement about a small set"
                ),
            )
        )
        return
    if c3["rows_surviving_the_crash"] != before:
        defects.append(
            (
                _SITE_SINK,
                (
                    f"{before} row(s) were committed before the crash and "
                    f"{c3['rows_surviving_the_crash']} were there after it. A "
                    "transaction Postgres acknowledged under synchronous_commit=on "
                    "must survive an immediate stop; a Plane-1 row that does not "
                    "is a hole in the auditable record of money truth"
                ),
            )
        )
        return
    ev.append(
        f"CRASH RECOVERY: recovery banner present after -m immediate and ABSENT "
        f"after the -m fast control; {before} committed row(s) all present after "
        f"the restart"
    )


def _arm8_flushed_in_wal_order(result: dict[str, Any], defects: list, ev: list) -> None:
    """ARM 8: the backlog drains, in the WAL's order, with no gaps."""
    c3 = result["c3"]
    if c3["backlog_after_flush"] or c3["state_after_reconnect"] != "healthy":
        defects.append(
            (
                _SITE_SINK,
                (
                    f"after the reconnect, backlog {c3['backlog_after_flush']} "
                    f"remained in state {c3['state_after_reconnect']!r} — the "
                    "buffered rows must reach Postgres, or the WAL is a shredder "
                    "with a delay"
                ),
            )
        )
        return
    if c3["rows_after_flush"] != c3["durable_wal_rows"]:
        defects.append(
            (
                _SITE_SINK,
                (
                    f"the WAL holds {c3['durable_wal_rows']} durable row(s) and "
                    f"Postgres holds {c3['rows_after_flush']} after the flush — "
                    "§12.4's reconnect heal claims no rows lost"
                ),
            )
        )
        return
    if not c3["order_matches_wal"]:
        defects.append(
            (
                _SITE_ORDER,
                (
                    "the natural-key sequence read ORDER BY wal_seq does NOT equal "
                    "the sequence recover() reads off the WAL's own bytes. The WAL "
                    "is the only place ordering is authoritative — event_id is "
                    f"assigned at INSERT and commit order is BATCH order. "
                    f"postgres={c3['order_in_postgres'][:4]!r} "
                    f"wal={c3['order_in_wal'][:4]!r}"
                ),
            )
        )
        return
    if not c3["wal_seq_contiguous"]:
        defects.append(
            (
                _SITE_ORDER,
                (
                    "the committed wal_seq values are not the contiguous range "
                    "0..N-1 — a gap is a Plane-1 row that was enqueued and never "
                    "landed, which is exactly what the reconnect heal must not "
                    "leave behind"
                ),
            )
        )
        return
    ev.append(
        f"FLUSHED IN WAL ORDER: {c3['rows_after_flush']} row(s) in Postgres equal "
        f"the WAL's {c3['durable_wal_rows']} durable row(s); ORDER BY wal_seq "
        f"reproduces the WAL's own byte order exactly; wal_seq contiguous; "
        f"event_id agrees (bool_and={c3['wal_seq_monotone_with_event_id']!r})"
    )


def _arm9_exactly_once(result: dict[str, Any], defects: list, ev: list) -> None:
    """ARM 9: THE PLANTED DUPLICATE, refused and absorbed. Both directions."""
    c3 = result["c3"]
    if c3["duplicate_rows_offered"] < MIN_DUPLICATES_PLANTED:
        defects.append(
            (
                _SITE_SINK,
                (
                    f"{c3['duplicate_rows_offered']} duplicate(s) were planted, "
                    f"below the floor of {MIN_DUPLICATES_PLANTED} — a flush with "
                    "no duplicate in it exercises no unique index, and "
                    "exactly-once would be a claim about a path never taken"
                ),
            )
        )
        return
    if (
        c3["duplicate_rows_inserted"] != 0
        or c3["rows_after_redelivery"] != c3["rows_after_flush"]
    ):
        defects.append(
            (
                _SITE_SINK,
                (
                    f"re-delivering {c3['duplicate_rows_offered']} already-committed "
                    f"row(s) inserted {c3['duplicate_rows_inserted']} and moved the "
                    f"log from {c3['rows_after_flush']} to "
                    f"{c3['rows_after_redelivery']} row(s). §12.4's reconnect heal "
                    "claims exactly-once, and a duplicated Plane-1 row is a "
                    "duplicated record of money"
                ),
            )
        )
        return
    probe = c3["duplicate_probe"]
    if probe.get("returncode") == 0:
        defects.append(
            (
                _SITE_SINK,
                (
                    f"a PLAIN re-INSERT of committed row "
                    f"{probe.get('natural_key')!r} SUCCEEDED. `ON CONFLICT DO "
                    "NOTHING` would have hidden this: with no unique index at all "
                    "the flush path looks identical, so the mechanism has to be "
                    "probed without the clause"
                ),
            )
        )
        return
    if probe.get("sqlstate") != SQLSTATE_UNIQUE_VIOLATION:
        defects.append(
            (
                _SITE_SINK,
                (
                    f"the duplicate was refused with SQLSTATE "
                    f"{probe.get('sqlstate') or 'NONE REPORTED'}, not "
                    f"{SQLSTATE_UNIQUE_VIOLATION} (unique_violation). A refusal for "
                    "the wrong reason is not evidence about dedup — a typo, an "
                    "absent table and a dead server all refuse just as loudly. "
                    f"stderr: {probe.get('stderr', '')[:200]}"
                ),
            )
        )
        return
    stderr = probe.get("stderr", "")
    if "Key (natural_key, occurred_at)=" not in stderr:
        defects.append(
            (
                _SITE_SINK,
                (
                    "the duplicate carried the right SQLSTATE for an unnamed key: "
                    f"{stderr[:220]!r}. 23505 is a shared namespace — "
                    "`plane1_positions_pkey` is a 23505 too — and only a refusal "
                    "naming (natural_key, occurred_at) is evidence about the "
                    "exactly-once index"
                ),
            )
        )
        return
    if c3["rows_after_probe"] != c3["rows_after_flush"]:
        defects.append(
            (
                _SITE_SINK,
                (
                    f"the duplicate PROBE changed the log from "
                    f"{c3['rows_after_flush']} to {c3['rows_after_probe']} row(s) "
                    "— a gate that writes to its subject is not measuring it"
                ),
            )
        )
        return
    constraint = next(
        (
            line.strip()
            for line in stderr.splitlines()
            if line.startswith("CONSTRAINT NAME:")
        ),
        "",
    )
    ev.append(
        f"EXACTLY ONCE: re-delivering {c3['duplicate_rows_offered']} committed "
        f"row(s) inserted 0 and left the log at {c3['rows_after_redelivery']}; a "
        f"plain re-INSERT was refused SQLSTATE {probe['sqlstate']} naming "
        f"(natural_key, occurred_at) [{constraint}]"
    )


# ---------------------------------------------------------------------------


def _nonvacuity(result: dict[str, Any], evidence: list[str]) -> CheckResult | None:
    """Every floor, checked BEFORE any arm contributes a verdict."""
    if not result.get("available", False):
        return _cannot(
            f"{result.get('reason', 'the ephemeral cluster could not be built')} "
            "§17: a safety property proven while its subject cannot be reached is "
            "not proven — CANNOT_MEASURE, deliberately never PASS",
            evidence,
        )
    for arm in ("c1", "c3", "c2_critical", "c2_control"):
        if arm not in result:
            return _cannot(f"the drill produced no {arm!r} arm", evidence)
    if result["c2_critical"]["reap_status"] or result["c2_control"]["reap_status"]:
        return _cannot(
            f"a C2 child exited non-zero "
            f"(critical={result['c2_critical']['reap_status']}, "
            f"control={result['c2_control']['reap_status']}) — its announcement "
            "cannot be read as a measurement",
            evidence,
        )
    evidence.append(
        f"nonce {result['nonce']}; {result['postgres_version']}; scratch database "
        f"{result['database']}"
    )
    return None


def run(mode: Mode, ctx: Context) -> CheckResult:  # pylint: disable=unused-argument
    """Build a cluster, kill it mid-trade, starve a disk, bring it back."""
    evidence: list[str] = []
    drill, complaint = _import_drill()
    if complaint:
        return _cannot(complaint, evidence)
    root = Path(tempfile.mkdtemp(prefix="nixp1c-"))
    try:
        result = drill.run_drill(root)
    except Exception as exc:  # noqa: BLE001 pylint: disable=broad-except
        return _cannot(
            f"the degraded-persistence drill could not be run: {exc!r}", evidence
        )
    finally:
        drill.remove_tree(root)

    return verdict(result, evidence)


def verdict(result: dict[str, Any], evidence: list[str] | None = None) -> CheckResult:
    """Turn one set of drill observations into a verdict.

    Split from `run` so the can-fail suite can drive the SHIPPED arms against a
    DOCTORED COPY of a real drill's observations — one field changed per plant,
    with the real drill run once for the whole module.
    """
    ev = evidence if evidence is not None else []
    refusal = _nonvacuity(result, ev)
    if refusal is not None:
        return refusal
    defects: list[tuple[str, str]] = []
    _arm1_the_outage_was_real(result, defects, ev)
    _arm2_trading_continued(result, defects, ev)
    _arm3_operator_alerted(result, defects, ev)
    _arm4_disk_critical_halts(result, defects, ev)
    _arm5_the_control(result, defects, ev)
    _arm6_the_stop_still_fires(result, defects, ev)
    _arm7_the_crash_and_what_survived(result, defects, ev)
    _arm8_flushed_in_wal_order(result, defects, ev)
    _arm9_exactly_once(result, defects, ev)
    return result_from_defects(NAME, defects, "; ".join(ev))


# Deliberately duplicated across every checks/check_*.py: the check
# contract (§4.2) requires each module be independently runnable, so this
# block cannot be factored into a shared helper without breaking that.
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
