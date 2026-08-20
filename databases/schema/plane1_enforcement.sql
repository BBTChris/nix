-- ============================================================================
-- Nix — PLANE 1: SOLE-WRITER ENFORCEMENT  (v1.0.0, ARC 043 / I8)
--
-- Authority: docs/nics_risk_subsystem_spec_v1.3.md §9 (Persistence Model —
-- "Limiter = sole writer") and §12.10 ("Plane 1 … NO NEW WRITERS, EVER").
-- Companion: databases/schema/plane1.sql (the schema and the grants),
--            databases/schema/plane1_hba.conf (the connection-layer half).
--
-- ----------------------------------------------------------------------------
-- WHAT WAS WRONG, MEASURED BEFORE THIS FILE EXISTED (ARC 043 / S1)
-- ----------------------------------------------------------------------------
-- `plane1.sql`'s grants are correct and they DO bite. Measured on the live
-- cluster: a statement that declares a non-writer identity is refused with
-- SQLSTATE 42501, `permission denied for table plane1_event_log`.
--
-- They bite only a writer polite enough to DECLARE one. `Plane1PostgresSink`
-- connected as the ambient OS/database identity — `bbt`, a SUPERUSER — and then
-- voluntarily issued `SET LOCAL ROLE nix_limiter`. A second process that simply
-- omits that line inherits superuser and bypasses every grant in the database.
-- Measured, on the real `nix_plane1`, from a plain script that imports nothing
-- from `nixrisk`:
--
--   INSERT  -> LANDED (event_id 1445, event_type 'filled', indistinguishable
--                      from a real row)
--   UPDATE  -> SUCCEEDED (§9's "never overwrite", violated by a second process)
--   TRUNCATE-> SUCCEEDED
--
-- That is ARC 038's finding in one sentence: the sole-writer invariant was
-- CONVENTION, enforced by the writer's own cooperation, and a rogue is by
-- definition not cooperating.
--
-- ----------------------------------------------------------------------------
-- WHY A GRANT CANNOT BE THE WHOLE FIX, AND WHAT CARRIES THE REST
-- ----------------------------------------------------------------------------
-- A SUPERUSER bypasses every privilege check in the executor. No REVOKE, no
-- GRANT, no row-level policy and no ownership change binds one. There is
-- exactly one mechanism in PostgreSQL that a superuser does NOT bypass:
-- `pg_hba.conf`, which the postmaster evaluates BEFORE a role's privileges
-- exist. So the enforcement is in two layers and neither is decorative:
--
--   LAYER 1 (connection, plane1_hba.conf) — a connection to `nix_plane1` that
--     does not explicitly assume `nix_limiter` or `nix_reader` is REJECTED by
--     the postmaster. The ambient identity every process in this tree connects
--     with today, superuser included, can no longer reach the record at all.
--   LAYER 2 (privilege, this file + plane1.sql) — of the two identities that
--     can reach it, only `nix_limiter` holds INSERT, and NOBODY holds UPDATE,
--     DELETE or TRUNCATE on the log.
--
-- A write to Plane 1 therefore requires deliberately assuming the sole-writer
-- identity. It can no longer happen by ambient default, which is how every
-- non-Limiter process in this tree connects.
--
-- WHAT THIS DOES NOT CLAIM, stated here rather than discovered later. Any
-- process running as OS user `bbt` may still deliberately authenticate as
-- `nix_limiter` (the ident map below permits it, and it must, because the
-- sanctioned writer runs as that OS user). Distinguishing the Limiter PROCESS
-- from another process of the SAME OS USER is not something the database can
-- do; it needs a dedicated service account and an ident map restricted to it,
-- which is provisioning scope. Recorded as CHECK-DEBT, not papered over.
--
-- ----------------------------------------------------------------------------
-- NO TRIGGER, AND THAT IS `plane1.sql`'s OWN RULING, KEPT
-- ----------------------------------------------------------------------------
-- ARC 043's brief allows a BEFORE-INSERT trigger rejecting non-writer identity
-- as acceptable hardening. `plane1.sql` already argued against exactly that and
-- the argument still holds: a trigger is droppable by the owner, disableable by
-- one ALTER TABLE, skipped wholesale under `session_replication_role = replica`,
-- and blind to TRUNCATE. Adding one here would make the weaker mechanism look
-- like the guarantee. Refused, deliberately, with the reason recorded.
--
-- IDEMPOTENT. Safe to re-apply; every statement is a re-assertion.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- The two Plane-1 roles become LOGIN roles.
--
-- They were NOLOGIN because nothing ever connected AS them — the sink connected
-- as the ambient superuser and assumed one. That is the defect. A role that can
-- be connected as is a role the postmaster can be told to require.
--
-- NO PASSWORD, and that is a decision rather than an omission. Authentication
-- is `peer` + an ident map (plane1_hba.conf): the kernel tells the postmaster
-- which OS user is on the socket, and the map says which database roles that OS
-- user may become. A password stored 0600 under the SAME OS user a rogue would
-- run as adds no structural strength — the process that could read it is the
-- process it would defend against — while costing a secret no fresh checkout
-- has. Two lines instead of one is not enforcement, and calling it enforcement
-- is the failure mode this whole file exists to end.
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nix_limiter') THEN
        CREATE ROLE nix_limiter;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nix_reader') THEN
        CREATE ROLE nix_reader;
    END IF;
END
$$;

ALTER ROLE nix_limiter LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
ALTER ROLE nix_reader  LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;

-- Neither role may become the other. `NOINHERIT` above is not enough on its own
-- — membership is what `SET ROLE` consults — so the membership is REVOKED
-- explicitly. Without this, a reader that is somehow a member of the writer
-- could `SET ROLE nix_limiter` and the two-identity split would be cosmetic.
REVOKE nix_limiter FROM nix_reader;
REVOKE nix_reader  FROM nix_limiter;

-- ----------------------------------------------------------------------------
-- LAYER 2, re-asserted. `plane1.sql` issues these at create time; a database
-- that has drifted since is repaired here, and a gate reads the CATALOG rather
-- than this file.
-- ----------------------------------------------------------------------------
REVOKE ALL ON plane1_event_log             FROM PUBLIC;
REVOKE ALL ON plane1_event_log_2026_08     FROM PUBLIC;
REVOKE ALL ON plane1_event_log_2026_09     FROM PUBLIC;
REVOKE ALL ON plane1_event_log_default     FROM PUBLIC;
REVOKE ALL ON plane1_positions             FROM PUBLIC;
REVOKE ALL ON plane1_projection_meta       FROM PUBLIC;
REVOKE ALL ON SEQUENCE plane1_event_id_seq FROM PUBLIC;

-- The log is append-only. Named as a REVOKE and not merely as an ungranted
-- privilege, because "we never granted it" is a claim about history and this is
-- a statement about now.
REVOKE UPDATE, DELETE, TRUNCATE ON plane1_event_log         FROM nix_limiter, nix_reader;
REVOKE UPDATE, DELETE, TRUNCATE ON plane1_event_log_2026_08 FROM nix_limiter, nix_reader;
REVOKE UPDATE, DELETE, TRUNCATE ON plane1_event_log_2026_09 FROM nix_limiter, nix_reader;
REVOKE UPDATE, DELETE, TRUNCATE ON plane1_event_log_default FROM nix_limiter, nix_reader;
REVOKE INSERT ON plane1_event_log         FROM nix_reader;
REVOKE INSERT ON plane1_event_log_2026_08 FROM nix_reader;
REVOKE INSERT ON plane1_event_log_2026_09 FROM nix_reader;
REVOKE INSERT ON plane1_event_log_default FROM nix_reader;

GRANT USAGE ON SCHEMA public TO nix_limiter, nix_reader;
GRANT SELECT, INSERT ON plane1_event_log         TO nix_limiter;
GRANT SELECT, INSERT ON plane1_event_log_2026_08 TO nix_limiter;
GRANT SELECT, INSERT ON plane1_event_log_2026_09 TO nix_limiter;
GRANT SELECT, INSERT ON plane1_event_log_default TO nix_limiter;
GRANT USAGE  ON SEQUENCE plane1_event_id_seq     TO nix_limiter;
GRANT SELECT ON plane1_event_log         TO nix_reader;
GRANT SELECT ON plane1_event_log_2026_08 TO nix_reader;
GRANT SELECT ON plane1_event_log_2026_09 TO nix_reader;
GRANT SELECT ON plane1_event_log_default TO nix_reader;

-- The projection is derived and rebuildable (§9), so the writer owns it whole.
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON plane1_positions       TO nix_limiter;
GRANT SELECT, INSERT, UPDATE, DELETE           ON plane1_projection_meta TO nix_limiter;
GRANT SELECT ON plane1_positions       TO nix_reader;
GRANT SELECT ON plane1_projection_meta TO nix_reader;

COMMIT;
