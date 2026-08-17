# dashboard.py — Technical Architecture Reference

**Subject:** `~/titan/dashboard.py` v1.18.153 (2026-07-04), 35,997 lines, single-file appliance dashboard for Titan Control 2.0 (Node01, macOS).
**Source basis:** direct read of the uploaded file (MEASURED unless noted).
**Purpose of this doc:** factual technical description — packages, process/network topology, connection surfaces, auth, frontend model, data contracts, and the runtime expectations the module assumes.

---

## 1. Identity and shape

- One Python file contains the entire dashboard: FastAPI backend (~100 REST endpoints, 1 WebSocket, 2 SSE streams), the full React SPA emitted as a server-side Python f-string, both CSS theme palettes, a Prometheus metrics side-server, and all SQL.
- App: `FastAPI(title="Titan Control 2.0", docs_url=None, redoc_url=None, lifespan=_lifespan)` — OpenAPI docs deliberately disabled.
- Versioned `X.Y.Z` per edit; the `__version__` line carries the full inline changelog (150+ entries). Canonical product version lives separately in `config/titan_version.json`.

## 2. Python packages

| Package | Role |
|---|---|
| `fastapi` | HTTP app, routing, WebSocket, uploads (`Form`, `File`, `UploadFile`), response types (`HTMLResponse`, `FileResponse`, `StreamingResponse`, `RedirectResponse`, `JSONResponse`) |
| `uvicorn` | ASGI server, run in-process from `main()` |
| `asyncpg` | PostgreSQL access via a shared async pool |
| `pyzmq` (`zmq`, `zmq.asyncio`) | SUB sockets into the appliance's IPC event buses |
| `PyJWT` (`jwt`) | session token encode/verify |
| `orjson` | fast JSON serialization |
| `reportlab` | PDF generation (performance report), imported lazily inside the endpoint |
| `parent_death_watcher` (local module) | kills the dashboard if its supervisor (titan_init) dies |
| stdlib | `asyncio`, `subprocess` (async exec), `threading` (TSOS orchestrator singleton lock), `hmac`/`hashlib` (timing-safe auth compare), `zoneinfo`, `pathlib`, `collections.deque`, etc. |

Frontend packages are **not** installed — they are CDN loads (see §6).

## 3. Process & network topology

```
Browser ──HTTPS──> NGINX :9443 (TLS termination, sole ingress)
                     │ reverse-proxy, sets X-Real-IP / X-Forwarded-Proto
                     ▼
              uvicorn 127.0.0.1:3000  (dashboard.py — this module)
                     │
   ┌─────────────────┼──────────────────────────────┐
   ▼                 ▼                              ▼
asyncpg pool    ZMQ SUB ipc://…/run/titan_events.sock   ZMQ SUB ipc://…/run/titan_capture_events_{pair}.sock
(titan_paper     (risk_engine PUB: ticks, account,       (capture PUB: candle_complete events)
 or titan_live)   trade events; SUBSCRIBE ""; RCVHWM 500)

Side server: /metrics on 127.0.0.1:9104 (Prometheus text; separate tiny HTTP server, non-fatal if it fails)
```

- **Bind posture:** app binds loopback only (`127.0.0.1:3000`). TLS, LAN exposure, and remote-IP identification are NGINX's job; the app trusts `X-Real-IP` only because loopback-proxy is the contracted sole ingress.
- **DB selection:** `config/broker.json` `environment` → `PRACTICE` ⇒ `titan_paper`, else `titan_live`; host/port from config; single `asyncpg.create_pool` at startup (lifespan).
- **ZMQ:** subscriber-only. No REP/REQ surface; the dashboard never commands the risk engine over ZMQ. Reconnect logic re-creates SUB sockets; `RCVHWM 500` bounds stale queue growth.
- **Supervision:** run as a titan_init child on macOS; `parent_death_watcher` enforces death-on-orphan.

## 4. Auth, session, and request security

- **Login:** username (`admin`) + password. Password is **not stored in the app or config** — fetched from the macOS Keychain (`security find-generic-password -s titan_admin_password -w`) via `asyncio.create_subprocess_exec` (a sync `subprocess.run` here previously deadlocked the event loop — fixed; blocking calls moved off-loop). Comparison is timing-safe (`hmac.compare_digest`; plain `==` was an audit finding).
- **Session:** JWT (`jwt.encode`/`jwt.decode`, fixed algorithm allowlist) carried in a cookie; expiry enforced server-side on verify; `secure` flag honors the proxy-TLS contract (`X-Forwarded-Proto: https` or localhost dev).
- **Mutation protection:** CSRF header (`X-Titan-CSRF: 1`) required on POST/PUT/DELETE + same-origin checks; admin-gated endpoint class on top of authenticated class.
- **Path-param hardening:** `/media/{filename}` and `/api/logs/{daemon}` both resolve through allowlists + containment checks (`Path(name).name`, `relative_to(base)`) against traversal.
- **Metrics cardinality defense:** route-label middleware collapses any path whose 2-segment prefix isn't a registered route to `/other`, bounding Prometheus label cardinality against scanner/404 fuzz.

## 5. Data surfaces consumed (expectations on the rest of the appliance)

The module assumes these exist and behave; each degrades honestly (flagged/empty payloads) rather than erroring when absent:

- **PostgreSQL tables:** `trade_lifecycle` (P&L, trades; canonical net-P&L SQL expression `gross_profit+commission+financing`), `renko_bricks` (`source='live'|'backfill'`, `sequence_num` authoritative over `formed_ts`), `candles_1s` + `candles_tf_*` (21-TF polymorphic set), `strategy_events` (decision-funnel rows), `overview_sets` (tile layouts; factory row server-side immutable), `economic_calendar`. Migrations for dashboard-owned tables live in `~/titan/migrations/*.sql`, applied lockstep with code.
- **ZMQ producers:** risk_engine event PUB (ticks: bid/ask → in-memory spread accumulator; account/trade events) and capture candle PUB. No stored tick table exists — the spread history is real-samples-since-process-start, by design.
- **Filesystem:** `~/titan/logs/*` (curated 8-daemon registry for the Logs tab; in-process byte-offset follower with inode-stable SSE ids replaced per-connection `tail -F`), `~/titan/media/` (FileResponse), `~/titan/reports/` (journal output), `~/titan/config/*.json`, `~/titan/tsos/**` (optional; TSOS tab reads run state, launches the orchestrator in-process behind a threading lock, dispatches council work as **detached subprocesses in the TSOS venv** — heavy work never runs in the dashboard process).
- **External hosts (best-effort):** `titan-updates` via SSH `BatchMode` cat for the self-update badge; unreachable ⇒ `nas_reachable=false`, never an error.
- **Config files read (fail-open to defaults unless noted):** `dashboard.json`, `broker.json`, `chart_features.json` (fail-**closed**: `wick_enabled:false` on any error), `news.json`, `overview_widgets.json`, `metrics.json`, `strategy.json`, `stages.json`, `tax.json`, `titan_version.json`, `tsos_council_settings.json` (atomic temp+rename writes).

## 6. Frontend model (the defining architectural choice)

- **Server-emitted SPA:** one `HTMLResponse` contains the entire React application (~17k lines of JSX) inside a **Python f-string**. Consequence: every literal JSX/JS brace must be doubled (`{{ }}`) — a measured recurring defect class across ~150 versions, policed by a standing rule ("all injected JSX braces DOUBLED") and a round-trip-exact check.
- **In-browser transpilation:** `<script type="text/babel">` + **babel-standalone 7.23.9** compiles JSX at page load. No build step, no bundler, no node toolchain on the appliance.
- **CDN dependencies (page load requires internet):** React 18.2.0 UMD, ReactDOM 18.2.0, babel-standalone, prop-types 15.8.1, Recharts 2.12.7, Tailwind 2.2.19 CSS, lucide icon font — all from cdnjs.cloudflare.com. Offline LAN ⇒ blank shell.
- **Rendering:** Overview = registry-driven tile grid (29 tiles, drag/hide/sets persisted per user in PG + localStorage); Live chart = raw `<canvas>` with a RAF render loop reading refs (hot-path state kept in refs, not React state — codified as an anti-feedback-loop rule "L#131"); Recharts/inline SVG for panels; theming via dual CSS-var palettes on `:root[data-theme]` with system-preference auto mode.
- **Client state:** JWT cookie; per-username `localStorage` keys for prefs/layout; URL query params for shareable ranges.

## 7. Realtime delivery to the browser

| Channel | Use |
|---|---|
| WebSocket (1) | live data push (ticks/account state to the Live tab) |
| SSE `/api/logs/{daemon}/stream` | live log tail; stable `<inode>:<offset>` event ids + `Last-Event-ID` resume; rotation/truncation/gap handling; client-side dedup ring |
| SSE (TSOS) | orchestrator progress |
| Polling | most tiles/status (5–10 s intervals with unmount cleanup); `/api/system/status` server-side 5 s cache |

## 8. Operational expectations & conventions (how changes are made safely)

- **Restart to activate:** the process serves the code loaded at boot; every change ships with "operator restarts to activate."
- **Never test on the live process:** UI proof runs in an **isolated Playwright harness on :8899** with synthetic fixtures (rule ADV-003); every interactive element carries a `data-testid`; both themes proven via `getComputedStyle`; screenshots archived per version.
- **Additive discipline:** `.bak == HEAD` before edit, surgical diffs, `py_compile`, round-trip-exact re-read, per-change version bump, SESSION.md wrap.
- **Honest-degrade doctrine:** endpoints return `has_data:false` / `stale` / `degraded_note` instead of fabricating values (empty producers render idle states, synthetic/backfill provenance is surfaced, all-zero realities are stated).
- **Money/format rules:** prices 5 decimal places, lots 2 decimal places, canonical P&L expression shared across endpoints; timestamps stored UTC, session TZ `America/Los_Angeles` applied explicitly at query time.

## 9. Known load-bearing constraints (measured, for anyone modeling this design)

1. **The f-string monolith is the tax.** Brace-doubling, no syntax tooling over the embedded JSX, and 36k-line file navigation are permanent costs; multiple shipped defects trace to it.
2. **CDN dependence** makes first paint internet-dependent on an otherwise self-contained appliance.
3. **Babel-in-browser** means the SPA recompiles on every load (seconds of parse cost) and caps the usable React idiom set.
4. **Platform coupling:** Keychain (`security`) for secrets and titan_init/launchd supervision are macOS-specific; the auth layer does not port to Linux as-is.
5. **Loopback+NGINX contract** is a real security boundary only while NGINX is the sole ingress; the app itself performs no TLS and trusts proxy headers.
6. **Read-mostly by design:** the dashboard subscribes and queries; it never mutates trading state. The few mutating endpoints (settings, overview sets, TSOS staging) are CSRF+admin-gated, atomic-write, and fail-closed — the live `strategy.py` is never writable from any dashboard endpoint (two-key install staging only).
